"""Pilot quantity take-off, BOQ/EBOM approval and procurement references.

Registers are atomic workflow aggregates. Other collections are idempotent
projections recovered on reads/retries; startup does not seed or initialize DBs.
"""
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator

from . import documents_reviews as documents
from .approval_release import digest

router = APIRouter(prefix="/ewp/quantities-procurement")
db = documents.db
registers = db["ewp_quantity_register"]
items = db["ewp_quantity_item"]
boqs = db["ewp_boq"]
boq_items = db["ewp_boq_item"]
handoffs = db["ewp_procurement_handoff"]


class RegisterCreate(BaseModel):
    ewp_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1, max_length=200)

    @validator("ewp_id", "name")
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("A value is required")
        return value.strip()


class Versioned(BaseModel):
    version: int = Field(..., ge=1)


class QuantityWrite(Versioned):
    item: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=5000)
    specification: str = Field("", max_length=5000)
    quantity: float = Field(..., gt=0, allow_inf_nan=False)
    unit: str = Field(..., min_length=1, max_length=30)
    source_revision_id: str = Field(..., min_length=1)
    source_reference: str = Field(..., min_length=1, max_length=500)
    derivation: str = Field("", max_length=5000)

    @validator("item", "unit", "source_revision_id", "source_reference")
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("A value is required")
        return value.strip()


class ActorAction(Versioned):
    actor: str = Field(..., min_length=1, max_length=200)
    comment: str = Field("", max_length=5000)

    @validator("actor")
    def actor_required(cls, value):
        if not value.strip():
            raise ValueError("Name is required")
        return value.strip()


class Generate(ActorAction):
    type: Literal["BOQ", "EBOM"]


class Review(ActorAction):
    decision: Literal["ACCEPT", "CHANGE_REQUIRED"]


class Approval(ActorAction):
    decision: Literal["APPROVE", "CHANGE_REQUIRED", "REJECT"]


class HandoffCreate(ActorAction):
    system: str = Field(..., min_length=1, max_length=200)
    reference: str = Field(..., min_length=1, max_length=200)
    url: Optional[str] = Field(None, max_length=2000)

    @validator("system", "reference")
    def reference_required(cls, value):
        if not value.strip():
            raise ValueError("Procurement system and reference are required")
        return value.strip()

    @validator("url")
    def safe_url(cls, value):
        value = (value or "").strip()
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("Use an http or https URL")
        return value or None


class HandoffUpdate(ActorAction):
    status: Literal["SENT", "ACKNOWLEDGED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]


def exposed(row):
    return documents.serialize(row)


async def project_register(row):
    """Version filters prevent an older reader from overwriting a newer projection."""
    async def project(collection, identity, data):
        data = {**data, "register_id": row["_id"], "register_version": row["version"]}
        await collection.update_one({"_id": identity}, {"$setOnInsert": data}, upsert=True)
        await collection.update_one({"_id": identity, "register_version": {"$lte": row["version"]}}, {"$set": data})
    for item in row["items"]:
        item_status = "PROCUREMENT_READY" if row["status"] == "HANDOFF_REFERENCED" else row["status"]
        await project(items, item["id"], {**item, "ewp_id": row["ewp_id"], "status": item_status})
    for identity in row.get("removed_item_ids", []):
        await project(items, identity, {"ewp_id": row["ewp_id"], "status": "REMOVED"})
    for boq in row.get("boqs", []):
        await project(boqs, boq["id"], {key: value for key, value in boq.items() if key != "items"})
        for item in boq["items"]:
            await project(boq_items, f"{boq['id']}:{item['id']}", {**item, "boq_id": boq["id"], "ewp_id": row["ewp_id"]})
    if row.get("handoff"):
        await project(handoffs, row["handoff"]["id"], row["handoff"])


async def require_register(identity):
    row = await registers.find_one({"_id": identity})
    if not row:
        raise HTTPException(404, "Quantity register not found")
    return row


def require_state(row, request, allowed):
    if row["version"] != request.version:
        raise HTTPException(409, "This register changed. Refresh before saving")
    if row["status"] not in allowed:
        raise HTTPException(409, f"This action is not available while the register is {row['status']}")


async def save(row, patch, action, actor="Prototype pilot", comment=""):
    timestamp = documents.now_iso()
    patch = {**patch, "version": row["version"] + 1, "updated_at": timestamp,
             "history": row.get("history", []) + [{"action": action, "actor": actor,
                "comment": comment, "at": timestamp, "actor_mode": "PROTOTYPE_PILOT"}]}
    result = await registers.update_one({"_id": row["_id"], "version": row["version"]}, {"$set": patch})
    if not result.matched_count:
        raise HTTPException(409, "This register changed. Refresh before saving")
    latest = {**row, **patch}
    await project_register(latest)
    return exposed(latest)


async def released_source(ewp_id, revision_id):
    revision = await documents.revision_collection.find_one({"_id": revision_id, "status": "RELEASED"})
    release = (revision or {}).get("release_record")
    if not release or release.get("status") != "RELEASED" or release.get("ewp_id") != ewp_id:
        raise HTTPException(409, "Select a released document revision belonging to this EWP")
    package = release["package"]
    return {"revision_id": revision_id, "revision_no": release["revision_no"], "release_id": release["id"],
        "release_code": release["release_code"], "release_hash": release["release_hash"],
        "document_id": release["document_id"], "document_code": package["document"]["code"],
        "document_title": package["document"]["title"], "deliverable": package["deliverable"],
        "file_hash": package["file"]["sha256"], "seb_basis": package["seb_basis"],
        "released_at": release["released_at"]}


async def verify_sources(row):
    if not row["items"]:
        raise HTTPException(409, "Add at least one quantity item")
    for item in row["items"]:
        source = await released_source(row["ewp_id"], item["source"]["revision_id"])
        if source != item["source"]:
            raise HTTPException(409, "A quantity source no longer matches its frozen release")


@router.get("/ewps")
async def list_ewps():
    rows = await documents.ewp_collection.find({}).sort("ewp_code", 1).to_list(length=None)
    return [{"id": str(row["_id"]), "code": row.get("ewp_code"), "name": row.get("ewp_name")} for row in rows]


@router.get("/released-outputs")
async def list_outputs(ewp_id: str):
    docs = await documents.document_collection.find({"ewp_id": ewp_id}).to_list(length=None)
    result = []
    for doc in docs:
        revisions = await documents.revision_collection.find({"document_id": doc["_id"], "status": "RELEASED"}).sort("created_at", -1).to_list(length=None)
        for revision in revisions:
            if revision.get("release_record"):
                result.append(await released_source(ewp_id, str(revision["_id"])))
    return result


@router.get("/registers")
async def list_registers(ewp_id: str):
    rows = await registers.find({"ewp_id": ewp_id}).sort("created_at", -1).to_list(length=None)
    return [{"id": str(row["_id"]), "name": row["name"], "status": row["status"]} for row in rows]


@router.post("/registers", status_code=201)
async def create_register(request: RegisterCreate):
    ewp = await documents.ewp_collection.find_one({"_id": request.ewp_id})
    if not ewp:
        raise HTTPException(404, "EWP not found")
    if not await list_outputs(request.ewp_id):
        raise HTTPException(409, "Release an engineering document before creating a quantity take-off")
    timestamp = documents.now_iso()
    row = {"_id": str(uuid4()), "ewp_id": request.ewp_id, "project_id": ewp.get("project_id"),
           "name": request.name, "status": "DRAFT", "version": 1, "items": [], "boqs": [],
           "current_boq_id": None, "handoff": None, "history": [], "created_at": timestamp, "updated_at": timestamp}
    await registers.insert_one(row)
    return exposed(row)


@router.get("/registers/{register_id}")
async def get_register(register_id: str):
    row = await require_register(register_id)
    await project_register(row)
    return exposed(row)


async def write_item(register_id, request, item_id=None):
    row = await require_register(register_id)
    require_state(row, request, {"DRAFT"})
    if item_id and not any(item["id"] == item_id for item in row["items"]):
        raise HTTPException(404, "Quantity item not found in this register")
    source = await released_source(row["ewp_id"], request.source_revision_id)
    item = {key: value for key, value in request.dict().items() if key not in {"version", "source_revision_id"}}
    item.update(id=item_id or str(uuid4()), source=source)
    updated = [item if prior["id"] == item_id else prior for prior in row["items"]] if item_id else row["items"] + [item]
    return await save(row, {"items": updated}, "ITEM_UPDATED" if item_id else "ITEM_ADDED")


@router.post("/registers/{register_id}/items")
async def add_item(register_id: str, request: QuantityWrite):
    return await write_item(register_id, request)


@router.put("/registers/{register_id}/items/{item_id}")
async def update_item(register_id: str, item_id: str, request: QuantityWrite):
    return await write_item(register_id, request, item_id)


@router.delete("/registers/{register_id}/items/{item_id}")
async def remove_item(register_id: str, item_id: str, request: Versioned):
    row = await require_register(register_id)
    require_state(row, request, {"DRAFT"})
    if not any(item["id"] == item_id for item in row["items"]):
        raise HTTPException(404, "Quantity item not found in this register")
    return await save(row, {"items": [item for item in row["items"] if item["id"] != item_id],
        "removed_item_ids": row.get("removed_item_ids", []) + [item_id]}, "ITEM_REMOVED")


@router.post("/registers/{register_id}/validate")
async def validate(register_id: str, request: ActorAction):
    row = await require_register(register_id)
    require_state(row, request, {"DRAFT"})
    await verify_sources(row)
    return await save(row, {"status": "VALIDATED", "validation": {"by": request.actor, "at": documents.now_iso()}},
                      "VALIDATED", request.actor, request.comment)


@router.post("/registers/{register_id}/reopen")
async def reopen(register_id: str, request: ActorAction):
    row = await require_register(register_id)
    require_state(row, request, {"VALIDATED"})
    return await save(row, {"status": "DRAFT", "validation": None}, "REOPENED", request.actor, request.comment)


@router.post("/registers/{register_id}/generate")
async def generate(register_id: str, request: Generate):
    row = await require_register(register_id)
    require_state(row, request, {"VALIDATED"})
    await verify_sources(row)
    number = len(row["boqs"]) + 1
    boq = {"id": str(uuid4()), "ewp_id": row["ewp_id"], "type": request.type, "revision_no": f"R{number:02d}",
           "status": "UNDER_REVIEW", "items": row["items"], "content_hash": digest(row["items"]),
           "generated_by": request.actor, "generated_at": documents.now_iso(), "validation": row["validation"]}
    return await save(row, {"boqs": row["boqs"] + [boq], "current_boq_id": boq["id"], "status": "UNDER_REVIEW"},
                      f"{request.type}_GENERATED", request.actor, request.comment)


def patch_boq(row, changes):
    return [dict(boq, **changes) if boq["id"] == row["current_boq_id"] else boq for boq in row["boqs"]]


@router.post("/registers/{register_id}/review")
async def review(register_id: str, request: Review):
    row = await require_register(register_id)
    require_state(row, request, {"UNDER_REVIEW"})
    if request.decision == "CHANGE_REQUIRED" and not request.comment.strip():
        raise HTTPException(400, "Explain the required changes")
    next_status = "UNDER_APPROVAL" if request.decision == "ACCEPT" else "DRAFT"
    record = {"decision": request.decision, "by": request.actor, "comment": request.comment, "at": documents.now_iso()}
    return await save(row, {"status": next_status, "boqs": patch_boq(row, {"status":
        "UNDER_APPROVAL" if request.decision == "ACCEPT" else "CHANGE_REQUIRED", "review": record})},
        "REVIEW_" + request.decision, request.actor, request.comment)


@router.post("/registers/{register_id}/approve")
async def approve(register_id: str, request: Approval):
    row = await require_register(register_id)
    require_state(row, request, {"UNDER_APPROVAL"})
    if request.decision != "APPROVE" and not request.comment.strip():
        raise HTTPException(400, "Explain the approval decision")
    await verify_sources(row)
    next_status = "APPROVED" if request.decision == "APPROVE" else "DRAFT"
    record = {"decision": request.decision, "by": request.actor, "comment": request.comment, "at": documents.now_iso()}
    return await save(row, {"status": next_status, "boqs": patch_boq(row, {"status":
        "APPROVED" if request.decision == "APPROVE" else request.decision, "approval": record})},
        "APPROVAL_" + request.decision, request.actor, request.comment)


@router.post("/registers/{register_id}/procurement-ready")
async def mark_ready(register_id: str, request: ActorAction):
    row = await require_register(register_id)
    require_state(row, request, {"APPROVED"})
    await verify_sources(row)
    return await save(row, {"status": "PROCUREMENT_READY", "boqs": patch_boq(row, {"status": "PROCUREMENT_READY"})},
                      "PROCUREMENT_READY", request.actor, request.comment)


@router.post("/registers/{register_id}/handoff")
async def create_handoff(register_id: str, request: HandoffCreate):
    row = await require_register(register_id)
    # Retry after an interrupted response returns the original reference.
    if row.get("handoff") and all(row["handoff"].get(key) == getattr(request, key) for key in ("system", "reference", "url")):
        return await get_register(register_id)
    require_state(row, request, {"PROCUREMENT_READY"})
    await verify_sources(row)
    boq = next(item for item in row["boqs"] if item["id"] == row["current_boq_id"])
    handoff = {"id": row["_id"], "ewp_id": row["ewp_id"], "boq_id": boq["id"], "boq_type": boq["type"],
        "boq_content_hash": boq["content_hash"], "quantity_item_ids": [item["id"] for item in boq["items"]],
        "source_release_ids": sorted({item["source"]["release_id"] for item in boq["items"]}),
        "system": request.system, "reference": request.reference, "url": request.url, "status": "REFERENCED",
        "recorded_by": request.actor, "created_at": documents.now_iso(), "actor_mode": "PROTOTYPE_PILOT"}
    return await save(row, {"status": "HANDOFF_REFERENCED", "handoff": handoff}, "PROCUREMENT_REFERENCED", request.actor, request.comment)


@router.patch("/registers/{register_id}/handoff")
async def update_handoff(register_id: str, request: HandoffUpdate):
    row = await require_register(register_id)
    require_state(row, request, {"HANDOFF_REFERENCED"})
    transitions = {"REFERENCED": {"SENT", "CANCELLED"}, "SENT": {"ACKNOWLEDGED", "CANCELLED"},
                   "ACKNOWLEDGED": {"IN_PROGRESS", "CANCELLED"}, "IN_PROGRESS": {"COMPLETED", "CANCELLED"}}
    if request.status not in transitions.get(row["handoff"]["status"], set()):
        raise HTTPException(409, "Invalid procurement status transition")
    if not request.comment.strip():
        raise HTTPException(400, "Add a tracking note or evidence reference")
    handoff = {**row["handoff"], "status": request.status, "updated_by": request.actor, "updated_at": documents.now_iso(), "tracking_note": request.comment}
    return await save(row, {"handoff": handoff}, "PROCUREMENT_" + request.status, request.actor, request.comment)
