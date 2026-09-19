"""Inputs and deliverables workflow backed by persisted EWP engineering work."""

from datetime import datetime, timezone
import os
from typing import List, Optional
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field


router = APIRouter()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]

ewp_collection = db["ewp"]
engineering_work_collection = db["ewp_engineering_work"]
ewp_seb_input_collection = db["ewp_seb_input"]
frozen_item_collection = db["seb_ewp_frozen_item"]
input_confirmation_collection = db["ewp_input_confirmation"]
deliverable_collection = db["ewp_deliverable"]

DELIVERABLE_STATUSES = {"NOT_STARTED", "DRAFT", "IN_PROGRESS", "READY_FOR_REVIEW"}
DELIVERABLE_TYPES = {"DRAWING", "CALCULATION", "SCHEDULE", "SPECIFICATION", "REPORT", "DATASHEET", "MODEL", "OTHER"}


class InputConfirmationWrite(BaseModel):
    input_ids: List[str] = Field(..., min_items=1)
    confirmed_by: Optional[str] = None


class DeliverableWrite(BaseModel):
    code: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    deliverable_type: str = Field(..., min_length=1)
    discipline: str = Field(..., min_length=1)
    responsible_engineer: str = Field(..., min_length=1)
    planned_issue_date: Optional[str] = None
    review_required: bool = True
    approval_required: bool = True
    status: str = "NOT_STARTED"


def json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def serialize(document: dict) -> dict:
    result = json_safe(document)
    result["id"] = str(result.pop("_id"))
    return result


async def require_ewp(ewp_id: str) -> dict:
    ewp = await ewp_collection.find_one({"_id": ewp_id})
    if not ewp:
        raise HTTPException(status_code=404, detail="EWP not found")
    return ewp


async def require_ready_work_item(work_item_id: str) -> dict:
    work_item = await engineering_work_collection.find_one({"_id": work_item_id})
    if not work_item:
        raise HTTPException(status_code=404, detail="Engineering work activity not found")
    if work_item.get("status") != "READY_FOR_OUTPUT":
        raise HTTPException(status_code=409, detail="Engineering work activity is not READY_FOR_OUTPUT")
    return work_item


def normalize_deliverable(request: DeliverableWrite) -> dict:
    deliverable_status = request.status.strip().upper()
    deliverable_type = request.deliverable_type.strip().upper()
    if deliverable_status not in DELIVERABLE_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid deliverable status")
    if deliverable_type not in DELIVERABLE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid deliverable type")
    return {
        "code": request.code.strip(),
        "name": request.name.strip(),
        "deliverable_type": deliverable_type,
        "discipline": request.discipline.strip(),
        "responsible_engineer": request.responsible_engineer.strip(),
        "planned_issue_date": request.planned_issue_date,
        "review_required": request.review_required,
        "approval_required": request.approval_required,
        "status": deliverable_status,
    }


@router.get("/ewp/inputs-deliverables/ready-work")
async def get_ready_engineering_work():
    """Return engineering activities that are ready to produce deliverables."""
    work_items = await engineering_work_collection.find({"status": "READY_FOR_OUTPUT"}).sort("updated_at", -1).to_list(length=10000)
    results = []
    for work_item in work_items:
        ewp = await ewp_collection.find_one({"_id": work_item.get("ewp_id")})
        if not ewp:
            continue
        results.append({
            **serialize(work_item),
            "ewp": {
                "id": str(ewp["_id"]),
                "code": ewp.get("ewp_code"),
                "name": ewp.get("ewp_name"),
                "discipline": ewp.get("discipline"),
                "project_id": ewp.get("project_id"),
                "seb_id": ewp.get("seb_id"),
                "seb_revision_id": ewp.get("seb_revision_id"),
                "freeze_snapshot_id": ewp.get("freeze_snapshot_id"),
                "release_code": ewp.get("release_code"),
                "release_hash": ewp.get("release_hash"),
            },
        })
    return results


@router.get("/ewp/inputs-deliverables/work-items/{work_item_id}")
async def get_inputs_deliverables_context(work_item_id: str):
    """Load the frozen inputs, confirmation, and deliverables for a ready work activity."""
    work_item = await require_ready_work_item(work_item_id)
    ewp = await require_ewp(str(work_item.get("ewp_id")))
    links = await ewp_seb_input_collection.find({"ewp_id": str(ewp["_id"])}).sort("position", 1).to_list(length=10000)
    snapshot = await frozen_item_collection.find_one({"_id": ewp.get("freeze_snapshot_id")}) or {}
    frozen_by_id = {
        str(item.get("release_item_id") or item.get("seb_item_id") or item.get("id") or ""): item
        for item in snapshot.get("released_seb_items") or []
    }
    revision = snapshot.get("released_revision") or {}
    seb = snapshot.get("seb") or {}
    inputs = []
    for link in links:
        release_item_id = str(link.get("release_item_id") or "")
        frozen = frozen_by_id.get(release_item_id, {})
        readiness = frozen.get("readiness")
        readiness_status = readiness if isinstance(readiness, str) else (readiness or {}).get("status")
        inputs.append({
            **serialize(link),
            "name": frozen.get("display_value") or frozen.get("item_name") or link.get("source_item_code") or release_item_id,
            "source": f"{seb.get('code') or ewp.get('seb_id')} / {revision.get('revision_no') or ewp.get('seb_revision_id')}",
            "reference": release_item_id,
            "status": "CONDITIONAL" if readiness_status == "CONDITIONAL" else "AVAILABLE",
            "required": True,
            "locked": True,
        })
    confirmation = await input_confirmation_collection.find_one({
        "ewp_id": str(ewp["_id"]),
        "engineering_work_item_id": work_item_id,
    })
    deliverables = await deliverable_collection.find({
        "ewp_id": str(ewp["_id"]),
        "engineering_work_item_id": work_item_id,
    }).sort("created_at", 1).to_list(length=10000)
    return {
        "ewp": serialize(ewp),
        "work_item": serialize(work_item),
        "inputs": inputs,
        "confirmation": serialize(confirmation) if confirmation else None,
        "deliverables": [serialize(document) for document in deliverables],
    }


@router.post("/ewp/inputs-deliverables/work-items/{work_item_id}/confirm-inputs")
async def confirm_engineering_inputs(work_item_id: str, request: InputConfirmationWrite):
    """Confirm all controlled EWP inputs required by the selected work activity."""
    work_item = await require_ready_work_item(work_item_id)
    ewp_id = str(work_item.get("ewp_id"))
    await require_ewp(ewp_id)
    links = await ewp_seb_input_collection.find({"ewp_id": ewp_id}).to_list(length=10000)
    required_ids = {str(link["_id"]) for link in links}
    selected_ids = {item_id.strip() for item_id in request.input_ids if item_id.strip()}
    if not required_ids:
        raise HTTPException(status_code=409, detail="The EWP has no controlled engineering inputs")
    missing = sorted(required_ids - selected_ids)
    if missing:
        raise HTTPException(status_code=400, detail="Confirm every required engineering input before continuing")

    existing = await input_confirmation_collection.find_one({
        "ewp_id": ewp_id,
        "engineering_work_item_id": work_item_id,
    })
    now = datetime.now(timezone.utc).isoformat()
    document = {
        "_id": str(existing["_id"]) if existing else str(uuid4()),
        "ewp_id": ewp_id,
        "engineering_work_item_id": work_item_id,
        "input_ids": sorted(selected_ids),
        "confirmed": True,
        "confirmed_by": request.confirmed_by,
        "confirmed_at": now,
        "updated_at": now,
    }
    if existing:
        await input_confirmation_collection.update_one(
            {"_id": document["_id"]},
            {"$set": {key: value for key, value in document.items() if key != "_id"}},
        )
    else:
        await input_confirmation_collection.insert_one(document)
    return serialize(document)


@router.post(
    "/ewp/inputs-deliverables/work-items/{work_item_id}/deliverables",
    status_code=status.HTTP_201_CREATED,
)
async def create_deliverable(work_item_id: str, request: DeliverableWrite):
    """Create a deliverable permanently linked to a ready engineering activity."""
    work_item = await require_ready_work_item(work_item_id)
    ewp_id = str(work_item.get("ewp_id"))
    await require_ewp(ewp_id)
    confirmation = await input_confirmation_collection.find_one({
        "ewp_id": ewp_id,
        "engineering_work_item_id": work_item_id,
        "confirmed": True,
    })
    if not confirmation:
        raise HTTPException(status_code=409, detail="Confirm required engineering inputs before creating a deliverable")
    normalized = normalize_deliverable(request)
    duplicate = await deliverable_collection.find_one({"ewp_id": ewp_id, "code": normalized["code"]})
    if duplicate:
        raise HTTPException(status_code=409, detail=f"Deliverable code '{normalized['code']}' already exists in this EWP")
    now = datetime.now(timezone.utc).isoformat()
    document = {
        "_id": str(uuid4()),
        "ewp_id": ewp_id,
        "engineering_work_item_id": work_item_id,
        **normalized,
        "created_at": now,
        "updated_at": now,
    }
    await deliverable_collection.insert_one(document)
    return serialize(document)


@router.patch("/ewp/inputs-deliverables/deliverables/{deliverable_id}")
async def update_deliverable(deliverable_id: str, request: DeliverableWrite):
    """Update deliverable ownership, preparation details, or lifecycle status."""
    existing = await deliverable_collection.find_one({"_id": deliverable_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    await require_ready_work_item(str(existing.get("engineering_work_item_id")))
    normalized = normalize_deliverable(request)
    duplicate = await deliverable_collection.find_one({
        "ewp_id": existing.get("ewp_id"),
        "code": normalized["code"],
        "_id": {"$ne": deliverable_id},
    })
    if duplicate:
        raise HTTPException(status_code=409, detail=f"Deliverable code '{normalized['code']}' already exists in this EWP")
    normalized["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await deliverable_collection.update_one({"_id": deliverable_id}, {"$set": normalized})
    if result.matched_count != 1:
        raise HTTPException(status_code=500, detail="Deliverable update was not persisted")
    return serialize({**existing, **normalized})


@router.get("/ewp/inputs-deliverables/deliverables/ready-for-review")
async def get_deliverables_ready_for_review():
    """Return controlled deliverables ready to enter Documents & Reviews."""
    documents = await deliverable_collection.find({"status": "READY_FOR_REVIEW"}).sort("updated_at", -1).to_list(length=10000)
    return [serialize(document) for document in documents]
