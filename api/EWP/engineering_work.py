"""Read-only Engineering Work selectors backed by immutable EWP handoff snapshots."""

from datetime import datetime, timezone
import os
from typing import Any, Dict, List, Optional
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field


router = APIRouter()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]
frozen_items = db["seb_ewp_frozen_item"]
ewp_collection = db["ewp"]
ewp_seb_input_collection = db["ewp_seb_input"]
ewp_engineering_work_collection = db["ewp_engineering_work"]

EWP_STATUSES = {"DRAFT", "NOT_STARTED", "IN_PROGRESS", "ON_HOLD", "READY_FOR_OUTPUT", "COMPLETED"}
WORK_STATUSES = {"DRAFT", "NOT_STARTED", "IN_PROGRESS", "ON_HOLD", "READY_FOR_OUTPUT", "COMPLETED"}


class ReleasedSEBProjectResponse(BaseModel):
    project_id: str
    project_code: Optional[str] = None
    project_name: str
    released_seb_count: int
    freeze_snapshot_count: int
    latest_frozen_at: Optional[str] = None


class ReleasedSEBResponse(BaseModel):
    freeze_snapshot_id: str
    freeze_snapshot_ids: List[str]
    ewb_handoff_id: str
    ewb_handoff_ids: List[str]
    project_id: str
    project_code: Optional[str] = None
    project_name: str
    sia_case_id: Optional[str] = None
    seb_id: str
    seb_code: str
    revision_id: str
    revision_no: str
    release_id: Optional[str] = None
    release_code: Optional[str] = None
    release_hash: Optional[str] = None
    released_at: Optional[str] = None
    item_count: int
    released_seb_items: List[Dict[str, Any]]
    handoff_count: int
    status: str
    frozen_at: Optional[str] = None
    snapshot_hash: Optional[str] = None


class EWPCreate(BaseModel):
    project_id: str = Field(..., min_length=1)
    seb_id: str = Field(..., min_length=1)
    revision_id: str = Field(..., min_length=1)
    freeze_snapshot_id: str = Field(..., min_length=1)
    release_item_ids: List[str] = Field(..., min_items=1)
    ewp_code: str = Field(..., min_length=1)
    ewp_name: str = Field(..., min_length=1)
    discipline: str = Field(..., min_length=1)
    scope: Optional[str] = None
    lead_engineer: Optional[str] = None
    planned_start: Optional[str] = None
    planned_finish: Optional[str] = None


class EngineeringWorkItemWrite(BaseModel):
    work_code: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    assigned_engineers: List[str] = Field(default_factory=list)
    status: str = "NOT_STARTED"
    progress: int = Field(default=0, ge=0, le=100)
    planned_start: Optional[str] = None
    planned_finish: Optional[str] = None


class EWPStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1)


def json_safe(value: Any) -> Any:
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


def serialize_record(document: dict) -> dict:
    serialized = json_safe(document)
    serialized["id"] = str(serialized.pop("_id"))
    return serialized


def frozen_release_item_id(item: dict) -> str:
    return str(item.get("release_item_id") or item.get("seb_item_id") or item.get("id") or "")


def project_id_from(snapshot: dict) -> Optional[str]:
    value = snapshot.get("project_id") or (snapshot.get("project") or {}).get("id")
    return str(value) if value is not None else None


def latest_snapshot(current: dict, candidate: dict) -> dict:
    return candidate if str(candidate.get("frozen_at") or "") > str(current.get("frozen_at") or "") else current


@router.get(
    "/ewp/engineering-work/released-projects",
    response_model=List[ReleasedSEBProjectResponse],
)
async def get_released_seb_projects():
    """Return distinct projects that have RELEASED records in the freeze collection."""
    documents = await frozen_items.find({"status": "RELEASED"}).to_list(length=10000)
    grouped: Dict[str, dict] = {}
    for document in documents:
        project_id = project_id_from(document)
        if not project_id:
            continue
        project = document.get("project") or {}
        seb = document.get("seb") or {}
        revision = document.get("released_revision") or {}
        group = grouped.setdefault(project_id, {
            "project_id": project_id,
            "project_code": project.get("code"),
            "project_name": project.get("name") or project_id,
            "released_keys": set(),
            "freeze_snapshot_count": 0,
            "latest_frozen_at": None,
        })
        group["freeze_snapshot_count"] += 1
        group["released_keys"].add((str(seb.get("id") or ""), str(revision.get("id") or "")))
        frozen_at = json_safe(document.get("frozen_at"))
        if frozen_at and (not group["latest_frozen_at"] or frozen_at > group["latest_frozen_at"]):
            group["latest_frozen_at"] = frozen_at

    return sorted([
        {
            "project_id": group["project_id"],
            "project_code": group["project_code"],
            "project_name": group["project_name"],
            "released_seb_count": len(group["released_keys"]),
            "freeze_snapshot_count": group["freeze_snapshot_count"],
            "latest_frozen_at": group["latest_frozen_at"],
        }
        for group in grouped.values()
    ], key=lambda item: (item["project_name"].lower(), item["project_id"]))


@router.get(
    "/ewp/engineering-work/released-sebs",
    response_model=List[ReleasedSEBResponse],
)
async def get_released_sebs_for_project(
    project_id: str = Query(..., min_length=1, description="Project ID returned by released-projects"),
):
    """Return unique released SEB revisions frozen for the selected project."""
    documents = await frozen_items.find({
        "status": "RELEASED",
        "$or": [
            {"project_id": project_id},
            {"project.id": project_id},
        ],
    }).to_list(length=10000)

    grouped: Dict[str, dict] = {}
    for document in documents:
        seb = document.get("seb") or {}
        revision = document.get("released_revision") or {}
        seb_id = str(seb.get("id") or "")
        revision_id = str(revision.get("id") or "")
        if not seb_id or not revision_id:
            continue
        key = f"{seb_id}:{revision_id}"
        if key not in grouped:
            grouped[key] = {"latest": document, "documents": [document]}
        else:
            grouped[key]["documents"].append(document)
            grouped[key]["latest"] = latest_snapshot(grouped[key]["latest"], document)

    results = []
    for group in grouped.values():
        latest = group["latest"]
        snapshots = group["documents"]
        project = latest.get("project") or {}
        seb = latest.get("seb") or {}
        revision = latest.get("released_revision") or {}
        freeze_snapshot_ids = [str(document["_id"]) for document in snapshots]
        handoff_ids = list(dict.fromkeys(
            str(document.get("ewb_handoff_id"))
            for document in snapshots
            if document.get("ewb_handoff_id") is not None
        ))
        results.append({
            "freeze_snapshot_id": str(latest["_id"]),
            "freeze_snapshot_ids": freeze_snapshot_ids,
            "ewb_handoff_id": str(latest.get("ewb_handoff_id") or ""),
            "ewb_handoff_ids": handoff_ids,
            "project_id": project_id,
            "project_code": project.get("code"),
            "project_name": project.get("name") or project_id,
            "sia_case_id": str(latest.get("sia_case_id")) if latest.get("sia_case_id") is not None else None,
            "seb_id": str(seb.get("id")),
            "seb_code": str(seb.get("code") or seb.get("id")),
            "revision_id": str(revision.get("id")),
            "revision_no": str(revision.get("revision_no") or revision.get("id")),
            "release_id": str(revision.get("release_id")) if revision.get("release_id") is not None else None,
            "release_code": revision.get("release_code"),
            "release_hash": revision.get("release_hash"),
            "released_at": json_safe(revision.get("released_at")),
            "item_count": len(latest.get("released_seb_items") or []),
            "released_seb_items": json_safe(latest.get("released_seb_items") or []),
            "handoff_count": len(handoff_ids),
            "status": latest.get("status") or "RELEASED",
            "frozen_at": json_safe(latest.get("frozen_at")),
            "snapshot_hash": latest.get("snapshot_hash"),
        })

    return sorted(results, key=lambda item: (item["seb_code"], item["revision_no"]), reverse=True)


@router.post(
    "/ewp/engineering-work/ewps",
    status_code=status.HTTP_201_CREATED,
)
async def create_engineering_work_package(request: EWPCreate):
    """Create an EWP and persist its exact frozen SEB input links."""
    project_id = request.project_id.strip()
    seb_id = request.seb_id.strip()
    revision_id = request.revision_id.strip()
    freeze_snapshot_id = request.freeze_snapshot_id.strip()
    ewp_code = request.ewp_code.strip()
    ewp_name = request.ewp_name.strip()
    release_item_ids = list(dict.fromkeys(
        item_id.strip() for item_id in request.release_item_ids if item_id.strip()
    ))

    if not release_item_ids:
        raise HTTPException(status_code=400, detail="Select at least one frozen release item")

    snapshot = await frozen_items.find_one({"_id": freeze_snapshot_id})
    if not snapshot:
        raise HTTPException(status_code=404, detail="Frozen release snapshot not found")
    if snapshot.get("status") != "RELEASED":
        raise HTTPException(status_code=409, detail="The selected freeze snapshot is no longer RELEASED")

    snapshot_project_id = project_id_from(snapshot)
    snapshot_seb = snapshot.get("seb") or {}
    snapshot_revision = snapshot.get("released_revision") or {}
    if snapshot_project_id != project_id:
        raise HTTPException(status_code=400, detail="The freeze snapshot does not belong to the selected project")
    if str(snapshot_seb.get("id") or "") != seb_id:
        raise HTTPException(status_code=400, detail="The freeze snapshot does not belong to the selected SEB")
    if str(snapshot_revision.get("id") or "") != revision_id:
        raise HTTPException(status_code=400, detail="The freeze snapshot does not belong to the selected revision")

    frozen_by_id = {
        frozen_release_item_id(item): item
        for item in snapshot.get("released_seb_items") or []
        if frozen_release_item_id(item)
    }
    missing_ids = [item_id for item_id in release_item_ids if item_id not in frozen_by_id]
    if missing_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Selected release item IDs are not part of this freeze snapshot: {', '.join(missing_ids)}",
        )

    existing = await ewp_collection.find_one({"ewp_code": ewp_code})
    if existing:
        raise HTTPException(status_code=409, detail=f"EWP code '{ewp_code}' already exists")

    now = datetime.now(timezone.utc).isoformat()
    ewp_id = str(uuid4())
    ewp_document = {
        "_id": ewp_id,
        "ewp_code": ewp_code,
        "ewp_name": ewp_name,
        "project_id": project_id,
        "seb_id": seb_id,
        "seb_revision_id": revision_id,
        "freeze_snapshot_id": freeze_snapshot_id,
        "ewb_handoff_id": str(snapshot.get("ewb_handoff_id") or ""),
        "release_id": str(snapshot_revision.get("release_id") or ""),
        "release_code": snapshot_revision.get("release_code"),
        "release_hash": snapshot_revision.get("release_hash"),
        "snapshot_hash": snapshot.get("snapshot_hash"),
        "discipline": request.discipline.strip(),
        "scope": request.scope.strip() if request.scope else None,
        "lead_engineer": request.lead_engineer.strip() if request.lead_engineer else None,
        "planned_start": request.planned_start,
        "planned_finish": request.planned_finish,
        "status": "DRAFT",
        "created_at": now,
        "updated_at": now,
    }
    input_documents = []
    for position, release_item_id in enumerate(release_item_ids, start=1):
        frozen_item = frozen_by_id[release_item_id]
        input_documents.append({
            "_id": str(uuid4()),
            "ewp_id": ewp_id,
            "release_item_id": release_item_id,
            "freeze_snapshot_id": freeze_snapshot_id,
            "project_id": project_id,
            "seb_id": seb_id,
            "seb_revision_id": revision_id,
            "position": position,
            "source_item_code": frozen_item.get("item_code"),
            "source_fact_id": frozen_item.get("fact_id"),
            "source_collection": frozen_item.get("fact_collection"),
            "created_at": now,
        })

    await ewp_collection.insert_one(ewp_document)
    try:
        await ewp_seb_input_collection.insert_many(input_documents)
    except Exception:
        await ewp_collection.delete_one({"_id": ewp_id})
        await ewp_seb_input_collection.delete_many({"ewp_id": ewp_id})
        raise HTTPException(status_code=500, detail="Unable to persist the EWP SEB input links")

    return {
        "ewp": serialize_record(ewp_document),
        "ewp_seb_inputs": [serialize_record(document) for document in input_documents],
    }


async def require_ewp(ewp_id: str) -> dict:
    ewp = await ewp_collection.find_one({"_id": ewp_id})
    if not ewp:
        raise HTTPException(status_code=404, detail="EWP not found")
    return ewp


def normalize_work_item(request: EngineeringWorkItemWrite) -> dict:
    work_status = request.status.strip().upper()
    if work_status not in WORK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid engineering work status")
    progress = request.progress
    if work_status == "COMPLETED" or progress == 100:
        work_status = "COMPLETED"
        progress = 100
    engineers = list(dict.fromkeys(
        engineer.strip() for engineer in request.assigned_engineers if engineer.strip()
    ))
    return {
        "work_code": request.work_code.strip(),
        "title": request.title.strip(),
        "assigned_engineers": engineers,
        "status": work_status,
        "progress": progress,
        "planned_start": request.planned_start,
        "planned_finish": request.planned_finish,
    }


@router.get("/ewp/engineering-work/ewps/{ewp_id}/work-items")
async def get_engineering_work_items(ewp_id: str):
    """Return persisted engineering work activities for an EWP."""
    await require_ewp(ewp_id)
    documents = await ewp_engineering_work_collection.find({"ewp_id": ewp_id}).sort("created_at", 1).to_list(length=10000)
    return [serialize_record(document) for document in documents]


@router.post(
    "/ewp/engineering-work/ewps/{ewp_id}/work-items",
    status_code=status.HTTP_201_CREATED,
)
async def create_engineering_work_item(ewp_id: str, request: EngineeringWorkItemWrite):
    """Persist one engineering work order/activity under an EWP."""
    await require_ewp(ewp_id)
    normalized = normalize_work_item(request)
    duplicate = await ewp_engineering_work_collection.find_one({
        "ewp_id": ewp_id,
        "work_code": normalized["work_code"],
    })
    if duplicate:
        raise HTTPException(status_code=409, detail=f"Work order '{normalized['work_code']}' already exists in this EWP")

    now = datetime.now(timezone.utc).isoformat()
    document = {
        "_id": str(uuid4()),
        "ewp_id": ewp_id,
        **normalized,
        "created_at": now,
        "updated_at": now,
    }
    await ewp_engineering_work_collection.insert_one(document)
    return serialize_record(document)


@router.patch("/ewp/engineering-work/ewps/{ewp_id}/work-items/{work_item_id}")
async def update_engineering_work_item(
    ewp_id: str,
    work_item_id: str,
    request: EngineeringWorkItemWrite,
):
    """Update a persisted engineering work activity."""
    await require_ewp(ewp_id)
    existing = await ewp_engineering_work_collection.find_one({"_id": work_item_id, "ewp_id": ewp_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Engineering work item not found")
    normalized = normalize_work_item(request)
    duplicate = await ewp_engineering_work_collection.find_one({
        "ewp_id": ewp_id,
        "work_code": normalized["work_code"],
        "_id": {"$ne": work_item_id},
    })
    if duplicate:
        raise HTTPException(status_code=409, detail=f"Work order '{normalized['work_code']}' already exists in this EWP")

    normalized["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await ewp_engineering_work_collection.update_one(
        {"_id": work_item_id, "ewp_id": ewp_id},
        {"$set": normalized},
    )
    if result.matched_count != 1:
        raise HTTPException(status_code=500, detail="Engineering work update was not persisted")
    return serialize_record({**existing, **normalized})


@router.patch("/ewp/engineering-work/ewps/{ewp_id}/status")
async def update_ewp_status(ewp_id: str, request: EWPStatusUpdate):
    """Persist the EWP lifecycle status used by Engineering Work."""
    await require_ewp(ewp_id)
    next_status = request.status.strip().upper()
    if next_status not in EWP_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid EWP status")
    updated_at = datetime.now(timezone.utc).isoformat()
    result = await ewp_collection.update_one(
        {"_id": ewp_id},
        {"$set": {"status": next_status, "updated_at": updated_at}},
    )
    if result.matched_count != 1:
        raise HTTPException(status_code=500, detail="EWP status was not persisted")
    return {"id": ewp_id, "status": next_status, "updated_at": updated_at}
