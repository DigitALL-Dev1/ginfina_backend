"""
SEB – Approval & Release Module
Manages approval process and release of immutable controlled SEB baselines.
AI is NOT permitted to release SEBs - only authorized human approvers.
"""

from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
from datetime import datetime
import os
import hashlib
import json

router = APIRouter()

# MongoDB connection
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[os.getenv("DATABASE_NAME", "ginfina")]

# Collections
approval_request_collection = db["seb_approval_request"]
approval_assignment_collection = db["seb_approval_assignment"]
approval_decision_collection = db["seb_approval_decision"]
approval_condition_collection = db["seb_approval_condition"]
seb_item_collection = db["seb_item"]
seb_baseline_collection = db["seb_baseline"]
seb_revision_collection = db["seb_revision"]
seb_item_source_collection = db["seb_item_source"]
seb_evidence_manifest_collection = db["seb_evidence_manifest"]
release_collection = db["seb_release"]
release_manifest_collection = db["seb_release_manifest"]
release_rendition_collection = db["seb_release_rendition"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. SEB_APPROVAL_REQUEST
# ═══════════════════════════════════════════════════════════════════════════

class SEBApprovalRequestCreate(BaseModel):
    seb_revision_id: str
    approval_code: str
    approval_status: str = "DRAFT"
    submitted_by: str
    submission_comment: Optional[str] = None

class SEBApprovalRequestResponse(BaseModel):
    id: str
    seb_revision_id: str
    approval_code: str
    approval_status: str
    submitted_by: str
    submitted_at: str
    completed_at: Optional[str]
    submission_comment: Optional[str]


@router.post("/seb/approval-requests", response_model=SEBApprovalRequestResponse)
async def create_approval_request(data: SEBApprovalRequestCreate):
    """Create a new approval request for an SEB revision."""
    doc = {
        "seb_revision_id": data.seb_revision_id,
        "approval_code": data.approval_code,
        "approval_status": data.approval_status,
        "submitted_by": data.submitted_by,
        "submitted_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "submission_comment": data.submission_comment,
    }
    result = await approval_request_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBApprovalRequestResponse(**doc)


@router.get("/seb/approval-requests", response_model=List[SEBApprovalRequestResponse])
async def get_approval_requests(
    seb_revision_id: Optional[str] = None,
    approval_status: Optional[str] = None
):
    """Get approval requests, optionally filtered."""
    query = {}
    if seb_revision_id:
        query["seb_revision_id"] = seb_revision_id
    if approval_status:
        query["approval_status"] = approval_status
    
    cursor = approval_request_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBApprovalRequestResponse(**doc))
    return results


@router.get("/seb/approval-requests/{request_id}", response_model=SEBApprovalRequestResponse)
async def get_approval_request_by_id(request_id: str):
    """Get a single approval request by ID."""
    from bson import ObjectId
    doc = await approval_request_collection.find_one({"_id": ObjectId(request_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Approval request not found")
    doc["id"] = str(doc.pop("_id"))
    return SEBApprovalRequestResponse(**doc)


@router.put("/seb/approval-requests/{request_id}")
async def update_approval_request(request_id: str, data: SEBApprovalRequestCreate):
    """Update an existing approval request."""
    from bson import ObjectId
    update_doc = {
        "seb_revision_id": data.seb_revision_id,
        "approval_code": data.approval_code,
        "approval_status": data.approval_status,
        "submitted_by": data.submitted_by,
        "submission_comment": data.submission_comment,
    }
    if data.approval_status in ["APPROVED_FOR_RELEASE", "REJECTED", "CANCELLED"]:
        update_doc["completed_at"] = datetime.utcnow().isoformat()
    
    result = await approval_request_collection.update_one(
        {"_id": ObjectId(request_id)},
        {"$set": update_doc}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {"message": "Approval request updated successfully"}


@router.delete("/seb/approval-requests/{request_id}")
async def delete_approval_request(request_id: str):
    """Delete an approval request."""
    from bson import ObjectId
    result = await approval_request_collection.delete_one({"_id": ObjectId(request_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return {"message": "Approval request deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 2. SEB_APPROVAL_ASSIGNMENT
# ═══════════════════════════════════════════════════════════════════════════

class SEBApprovalAssignmentCreate(BaseModel):
    approval_request_id: str
    seb_item_id: Optional[str] = None
    approver_user_id: str
    approval_role: Optional[str] = None
    discipline: Optional[str] = None
    approval_sequence: int = 1
    is_mandatory: bool = True
    assignment_status: str = "PENDING"
    due_date: Optional[str] = None

class SEBApprovalAssignmentResponse(BaseModel):
    id: str
    approval_request_id: str
    seb_item_id: Optional[str] = None
    approver_user_id: str
    approval_role: Optional[str]
    discipline: Optional[str]
    approval_sequence: int
    is_mandatory: bool
    assignment_status: str
    assigned_at: str
    due_date: Optional[str]


@router.post("/seb/approval-assignments", response_model=SEBApprovalAssignmentResponse)
async def create_approval_assignment(data: SEBApprovalAssignmentCreate):
    """Assign an engineering approver to an approval request and optional SEB item."""
    from bson import ObjectId

    if not ObjectId.is_valid(data.approval_request_id):
        raise HTTPException(status_code=404, detail="Approval request not found")
    approval_request = await approval_request_collection.find_one(
        {"_id": ObjectId(data.approval_request_id)}
    )
    if not approval_request:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if data.seb_item_id:
        seb_item = await seb_item_collection.find_one({"_id": data.seb_item_id})
        if not seb_item:
            raise HTTPException(status_code=404, detail="SEB item not found")
        if seb_item.get("status") != "reviewed":
            raise HTTPException(status_code=400, detail="Only reviewed SEB items can be assigned for approval")
        if seb_item.get("frozen_at"):
            raise HTTPException(status_code=409, detail="Released SEB items are immutable")
        if seb_item.get("seb_revision_id") != approval_request.get("seb_revision_id"):
            raise HTTPException(
                status_code=400,
                detail="The selected SEB item does not belong to the approval request revision",
            )

    doc = {
        "approval_request_id": data.approval_request_id,
        "seb_item_id": data.seb_item_id,
        "approver_user_id": data.approver_user_id,
        "approval_role": data.approval_role,
        "discipline": data.discipline,
        "approval_sequence": data.approval_sequence,
        "is_mandatory": data.is_mandatory,
        "assignment_status": data.assignment_status,
        "assigned_at": datetime.utcnow().isoformat(),
        "due_date": data.due_date,
    }
    result = await approval_assignment_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)

    if data.seb_item_id:
        item_approval = {
            "approval_request_id": data.approval_request_id,
            "approval_assignment_id": doc["id"],
            "engineering_approver_id": data.approver_user_id,
            "role": data.approval_role or "ENGINEERING_APPROVER",
            "discipline": data.discipline,
            "assignment_status": data.assignment_status,
            "is_mandatory": data.is_mandatory,
            "assigned_at": doc["assigned_at"],
            "due_date": data.due_date,
            "decision": None,
            "comment": None,
            "decided_at": None,
        }
        item_update = await seb_item_collection.update_one(
            {"_id": data.seb_item_id},
            {"$set": {"approval": item_approval}},
        )
        if item_update.modified_count == 0:
            await approval_assignment_collection.delete_one({"_id": result.inserted_id})
            raise HTTPException(status_code=500, detail="Unable to update the SEB item approval")

    return SEBApprovalAssignmentResponse(**doc)


@router.get("/seb/approval-assignments", response_model=List[SEBApprovalAssignmentResponse])
async def get_approval_assignments(
    approval_request_id: Optional[str] = None,
    seb_item_id: Optional[str] = None,
):
    """Get approval assignments, optionally filtered by request or SEB item."""
    query = {}
    if approval_request_id:
        query["approval_request_id"] = approval_request_id
    if seb_item_id:
        query["seb_item_id"] = seb_item_id
    
    cursor = approval_assignment_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBApprovalAssignmentResponse(**doc))
    return results


@router.delete("/seb/approval-assignments/{assignment_id}")
async def delete_approval_assignment(assignment_id: str):
    """Delete an approval assignment."""
    from bson import ObjectId
    result = await approval_assignment_collection.delete_one({"_id": ObjectId(assignment_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Approval assignment not found")
    return {"message": "Approval assignment deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 3. SEB_APPROVAL_DECISION
# ═══════════════════════════════════════════════════════════════════════════

class SEBApprovalDecisionCreate(BaseModel):
    approval_assignment_id: str
    approval_decision: str
    approval_comment: Optional[str] = None
    decided_by: str

class SEBApprovalDecisionResponse(BaseModel):
    id: str
    approval_assignment_id: str
    approval_decision: str
    approval_comment: Optional[str]
    decided_by: str
    decided_at: str


class SEBRevisionApprovalCreate(BaseModel):
    seb_id: str
    approver_user_id: str
    decision: str
    comment: Optional[str] = None


class SEBControlledReleaseCreate(BaseModel):
    seb_id: str
    released_by: str
    release_comment: Optional[str] = None


@router.post("/seb/approval-decisions", response_model=SEBApprovalDecisionResponse)
async def create_approval_decision(data: SEBApprovalDecisionCreate):
    """Create an approval decision."""
    doc = {
        "approval_assignment_id": data.approval_assignment_id,
        "approval_decision": data.approval_decision,
        "approval_comment": data.approval_comment,
        "decided_by": data.decided_by,
        "decided_at": datetime.utcnow().isoformat(),
    }
    result = await approval_decision_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    
    # Update assignment status
    from bson import ObjectId
    await approval_assignment_collection.update_one(
        {"_id": ObjectId(data.approval_assignment_id)},
        {"$set": {"assignment_status": "COMPLETED"}}
    )
    
    return SEBApprovalDecisionResponse(**doc)


@router.get("/seb/approval-decisions", response_model=List[SEBApprovalDecisionResponse])
async def get_approval_decisions(approval_assignment_id: Optional[str] = None):
    """Get approval decisions, optionally filtered by approval_assignment_id."""
    query = {}
    if approval_assignment_id:
        query["approval_assignment_id"] = approval_assignment_id
    
    cursor = approval_decision_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBApprovalDecisionResponse(**doc))
    return results


@router.delete("/seb/approval-decisions/{decision_id}")
async def delete_approval_decision(decision_id: str):
    """Delete an approval decision."""
    from bson import ObjectId
    result = await approval_decision_collection.delete_one({"_id": ObjectId(decision_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Approval decision not found")
    return {"message": "Approval decision deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 4. SEB_APPROVAL_CONDITION
# ═══════════════════════════════════════════════════════════════════════════

class SEBApprovalConditionCreate(BaseModel):
    approval_decision_id: str
    condition_code: Optional[str] = None
    condition_description: str
    discipline: Optional[str] = None
    owner_user_id: Optional[str] = None
    target_date: Optional[str] = None
    condition_status: str = "OPEN"
    closure_comment: Optional[str] = None

class SEBApprovalConditionResponse(BaseModel):
    id: str
    approval_decision_id: str
    condition_code: Optional[str]
    condition_description: str
    discipline: Optional[str]
    owner_user_id: Optional[str]
    target_date: Optional[str]
    condition_status: str
    closure_comment: Optional[str]
    closed_at: Optional[str]


@router.post("/seb/approval-conditions", response_model=SEBApprovalConditionResponse)
async def create_approval_condition(data: SEBApprovalConditionCreate):
    """Create an approval condition."""
    doc = {
        "approval_decision_id": data.approval_decision_id,
        "condition_code": data.condition_code,
        "condition_description": data.condition_description,
        "discipline": data.discipline,
        "owner_user_id": data.owner_user_id,
        "target_date": data.target_date,
        "condition_status": data.condition_status,
        "closure_comment": data.closure_comment,
        "closed_at": None,
    }
    result = await approval_condition_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBApprovalConditionResponse(**doc)


@router.get("/seb/approval-conditions", response_model=List[SEBApprovalConditionResponse])
async def get_approval_conditions(approval_decision_id: Optional[str] = None):
    """Get approval conditions, optionally filtered by approval_decision_id."""
    query = {}
    if approval_decision_id:
        query["approval_decision_id"] = approval_decision_id
    
    cursor = approval_condition_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBApprovalConditionResponse(**doc))
    return results


@router.delete("/seb/approval-conditions/{condition_id}")
async def delete_approval_condition(condition_id: str):
    """Delete an approval condition."""
    from bson import ObjectId
    result = await approval_condition_collection.delete_one({"_id": ObjectId(condition_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Approval condition not found")
    return {"message": "Approval condition deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 5. SEB_RELEASE
# ═══════════════════════════════════════════════════════════════════════════

class SEBReleaseCreate(BaseModel):
    seb_revision_id: str
    approval_request_id: str
    release_code: str
    release_status: str = "PREPARED"
    effective_date: Optional[str] = None
    released_by: str
    release_comment: Optional[str] = None

class SEBReleaseResponse(BaseModel):
    id: str
    seb_revision_id: str
    approval_request_id: str
    release_code: str
    release_status: str
    release_hash: str
    effective_date: Optional[str]
    released_by: str
    released_at: str
    release_comment: Optional[str]


@router.post("/seb/releases", response_model=SEBReleaseResponse)
async def create_release(data: SEBReleaseCreate):
    """Create an SEB release (immutable controlled baseline)."""
    # Generate release hash
    hash_content = f"{data.seb_revision_id}_{data.approval_request_id}_{datetime.utcnow().isoformat()}"
    release_hash = hashlib.sha256(hash_content.encode()).hexdigest()
    
    doc = {
        "seb_revision_id": data.seb_revision_id,
        "approval_request_id": data.approval_request_id,
        "release_code": data.release_code,
        "release_status": data.release_status,
        "release_hash": release_hash,
        "effective_date": data.effective_date,
        "released_by": data.released_by,
        "released_at": datetime.utcnow().isoformat(),
        "release_comment": data.release_comment,
    }
    result = await release_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBReleaseResponse(**doc)


@router.get("/seb/releases", response_model=List[SEBReleaseResponse])
async def get_releases(
    seb_revision_id: Optional[str] = None,
    release_status: Optional[str] = None
):
    """Get releases, optionally filtered."""
    query = {}
    if seb_revision_id:
        query["seb_revision_id"] = seb_revision_id
    if release_status:
        query["release_status"] = release_status
    
    cursor = release_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBReleaseResponse(**doc))
    return results


@router.get("/seb/releases/{release_id}", response_model=SEBReleaseResponse)
async def get_release_by_id(release_id: str):
    """Get a single release by ID."""
    from bson import ObjectId
    doc = await release_collection.find_one({"_id": ObjectId(release_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Release not found")
    doc["id"] = str(doc.pop("_id"))
    return SEBReleaseResponse(**doc)


@router.delete("/seb/releases/{release_id}")
async def delete_release(release_id: str):
    """Delete a release."""
    from bson import ObjectId
    result = await release_collection.delete_one({"_id": ObjectId(release_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Release not found")
    return {"message": "Release deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 6. SEB_RELEASE_MANIFEST
# ═══════════════════════════════════════════════════════════════════════════

class SEBReleaseManifestCreate(BaseModel):
    seb_release_id: str
    seb_item_id: str
    source_record_type: Optional[str] = None
    source_record_id: Optional[str] = None
    item_hash: str
    evidence_hash: Optional[str] = None
    reliability_status: Optional[str] = None
    readiness_status: Optional[str] = None

class SEBReleaseManifestResponse(BaseModel):
    id: str
    seb_release_id: str
    seb_item_id: str
    source_record_type: Optional[str]
    source_record_id: Optional[str]
    item_hash: str
    evidence_hash: Optional[str]
    reliability_status: Optional[str]
    readiness_status: Optional[str]
    included_at: str


@router.post("/seb/release-manifests", response_model=SEBReleaseManifestResponse)
async def create_release_manifest(data: SEBReleaseManifestCreate):
    """Create a release manifest item (freezes exact SEB data)."""
    doc = {
        "seb_release_id": data.seb_release_id,
        "seb_item_id": data.seb_item_id,
        "source_record_type": data.source_record_type,
        "source_record_id": data.source_record_id,
        "item_hash": data.item_hash,
        "evidence_hash": data.evidence_hash,
        "reliability_status": data.reliability_status,
        "readiness_status": data.readiness_status,
        "included_at": datetime.utcnow().isoformat(),
    }
    result = await release_manifest_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBReleaseManifestResponse(**doc)


@router.get("/seb/release-manifests", response_model=List[SEBReleaseManifestResponse])
async def get_release_manifests(seb_release_id: Optional[str] = None):
    """Get release manifest items, optionally filtered by seb_release_id."""
    query = {}
    if seb_release_id:
        query["seb_release_id"] = seb_release_id
    
    cursor = release_manifest_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBReleaseManifestResponse(**doc))
    return results


@router.delete("/seb/release-manifests/{manifest_id}")
async def delete_release_manifest(manifest_id: str):
    """Delete a release manifest item."""
    from bson import ObjectId
    result = await release_manifest_collection.delete_one({"_id": ObjectId(manifest_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Release manifest item not found")
    return {"message": "Release manifest item deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 7. SEB_RELEASE_RENDITION
# ═══════════════════════════════════════════════════════════════════════════

class SEBReleaseRenditionCreate(BaseModel):
    seb_release_id: str
    rendition_type: str
    file_name: str
    file_path: str
    file_hash: str
    generated_by: str
    status: str = "GENERATING"

class SEBReleaseRenditionResponse(BaseModel):
    id: str
    seb_release_id: str
    rendition_type: str
    file_name: str
    file_path: str
    file_hash: str
    generated_at: str
    generated_by: str
    status: str


@router.post("/seb/release-renditions", response_model=SEBReleaseRenditionResponse)
async def create_release_rendition(data: SEBReleaseRenditionCreate):
    """Create a release rendition (PDF, report, etc.)."""
    doc = {
        "seb_release_id": data.seb_release_id,
        "rendition_type": data.rendition_type,
        "file_name": data.file_name,
        "file_path": data.file_path,
        "file_hash": data.file_hash,
        "generated_at": datetime.utcnow().isoformat(),
        "generated_by": data.generated_by,
        "status": data.status,
    }
    result = await release_rendition_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBReleaseRenditionResponse(**doc)


@router.get("/seb/release-renditions", response_model=List[SEBReleaseRenditionResponse])
async def get_release_renditions(seb_release_id: Optional[str] = None):
    """Get release renditions, optionally filtered by seb_release_id."""
    query = {}
    if seb_release_id:
        query["seb_release_id"] = seb_release_id
    
    cursor = release_rendition_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBReleaseRenditionResponse(**doc))
    return results


@router.delete("/seb/release-renditions/{rendition_id}")
async def delete_release_rendition(rendition_id: str):
    """Delete a release rendition."""
    from bson import ObjectId
    result = await release_rendition_collection.delete_one({"_id": ObjectId(rendition_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Release rendition not found")
    return {"message": "Release rendition deleted successfully"}


# ---------------------------------------------------------------------------
# Guided approval and controlled release workflow
# ---------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _document(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return None
    return {
        **{key: _json_safe(value) for key, value in doc.items() if key != "_id"},
        "id": str(doc["_id"]),
    }


async def _approval_item_row(item: dict) -> dict:
    fact = None
    collection_name = item.get("fact_collection")
    if collection_name and item.get("fact_id"):
        fact = await db[collection_name].find_one({"_id": item["fact_id"]})
    fact = fact or {}
    fact_name = item.get("fact_name") or item.get("item_name")
    if not fact_name:
        for field in (
            "fact_name", "item_name", "parameter_name", "name", "title",
            "description", "gap_description", "finding", "observation",
            "equipment_name", "asset_name", "component_name",
        ):
            value = fact.get(field)
            if isinstance(value, str) and value.strip():
                fact_name = value.strip()
                break
    readiness = item.get("discipline_readiness") or {}
    return {
        "id": str(item["_id"]),
        "fact_id": item.get("fact_id"),
        "fact_name": fact_name or f"Fact {item.get('fact_id', item['_id'])}",
        "fact_collection": collection_name,
        "discipline": item.get("review_discipline") or item.get("discipline") or fact.get("discipline") or fact.get("target_discipline") or "UNASSIGNED",
        "status": item.get("status"),
        "review_decision": item.get("decision"),
        "review_comment": item.get("review_comment"),
        "readiness": readiness.get("status"),
        "discipline_readiness": _json_safe(readiness),
        "approval": _json_safe(item.get("approval")),
    }


async def _build_approval_summary(seb_id: str, revision_id: str) -> dict:
    baseline = await seb_baseline_collection.find_one({"_id": seb_id})
    if not baseline:
        raise HTTPException(status_code=404, detail="SEB not found")
    revision = await seb_revision_collection.find_one({"_id": revision_id})
    if not revision:
        raise HTTPException(status_code=404, detail="SEB revision not found")
    if revision.get("seb_id") != seb_id:
        raise HTTPException(status_code=400, detail="The revision does not belong to the selected SEB")

    item_docs = await seb_item_collection.find({
        "seb_id": seb_id,
        "seb_revision_id": revision_id,
        "status": {"$in": ["reviewed", "approved"]},
    }).to_list(length=5000)
    items = [await _approval_item_row(item) for item in item_docs]
    item_ids = [item["id"] for item in items]
    source_docs = await seb_item_source_collection.find(
        {"seb_item_id": {"$in": item_ids}}
    ).to_list(length=10000) if item_ids else []
    evidence_docs = await seb_evidence_manifest_collection.find(
        {"seb_revision_id": revision_id}
    ).to_list(length=10000)

    decision_counts = {
        "total": len(items),
        "accepted": sum(item["review_decision"] == "ACCEPT" for item in items),
        "conditional": sum(item["review_decision"] == "ACCEPT_WITH_CONDITION" for item in items),
        "change_required": sum(item["review_decision"] == "CHANGE_REQUIRED" for item in items),
        "rejected": sum(item["review_decision"] == "REJECT" for item in items),
    }

    readiness_priority = {"BLOCKED": 4, "CONDITIONAL": 3, "READY": 2, "NOT_APPLICABLE": 1}
    readiness_by_discipline: Dict[str, str] = {}
    for item in items:
        discipline = str(item["discipline"] or "UNASSIGNED").upper()
        item_readiness = item["readiness"] or "PENDING"
        current = readiness_by_discipline.get(discipline)
        if current is None or readiness_priority.get(item_readiness, 5) > readiness_priority.get(current, 5):
            readiness_by_discipline[discipline] = item_readiness

    conditions = []
    blockers = []
    review_comments = []
    for item in items:
        readiness = item.get("discipline_readiness") or {}
        conditional = readiness.get("conditional") or {}
        blocked = readiness.get("blocked") or {}
        if conditional.get("enabled"):
            conditions.append({
                "item_id": item["id"], "fact_name": item["fact_name"],
                "discipline": item["discipline"], **conditional,
            })
        if blocked.get("enabled"):
            blockers.append({
                "item_id": item["id"], "fact_name": item["fact_name"],
                "discipline": item["discipline"], **blocked,
            })
        if item.get("review_comment"):
            review_comments.append({
                "item_id": item["id"], "fact_name": item["fact_name"],
                "discipline": item["discipline"], "comment": item["review_comment"],
            })

    revision_approval = revision.get("approval") or {}
    if revision_approval.get("decision") == "APPROVE_WITH_CONDITION" and revision_approval.get("comment"):
        conditions.append({
            "item_id": None,
            "fact_name": "Revision approval",
            "discipline": "APPROVAL",
            "condition": revision_approval["comment"],
            "required_action": None,
            "owner": revision_approval.get("engineering_approver_id"),
        })

    latest_release = await release_collection.find_one(
        {"seb_revision_id": revision_id}, sort=[("released_at", -1)]
    )
    return {
        "seb": _document(baseline),
        "revision": _document(revision),
        "engineering_review": decision_counts,
        "readiness": [
            {"discipline": discipline, "status": readiness_by_discipline[discipline]}
            for discipline in sorted(readiness_by_discipline)
        ],
        "conditions": conditions,
        "blockers": blockers,
        "items": items,
        "item_sources": [_document(doc) for doc in source_docs],
        "evidence_references": [_document(doc) for doc in evidence_docs],
        "review_comments": review_comments,
        "approval": _json_safe(revision_approval),
        "release": _document(latest_release),
    }


@router.get("/seb/approval-summary", response_model=Dict[str, Any])
async def get_approval_summary(seb_id: str, seb_revision_id: str):
    """Return the complete human-review summary used before approval and release."""
    return await _build_approval_summary(seb_id, seb_revision_id)


@router.post("/seb/revisions/{revision_id}/approval-decision", response_model=Dict[str, Any])
async def submit_revision_approval(revision_id: str, data: SEBRevisionApprovalCreate):
    """Assign the engineering approver, record a decision, and update every SEB item."""
    allowed_decisions = {"APPROVE", "APPROVE_WITH_CONDITION", "CHANGE_REQUIRED", "REJECT"}
    if data.decision not in allowed_decisions:
        raise HTTPException(status_code=400, detail="Invalid approval decision")
    if data.decision != "APPROVE" and not (data.comment or "").strip():
        raise HTTPException(status_code=400, detail="A comment is required for this decision")

    revision = await seb_revision_collection.find_one({"_id": revision_id})
    if not revision:
        raise HTTPException(status_code=404, detail="SEB revision not found")
    if revision.get("seb_id") != data.seb_id:
        raise HTTPException(status_code=400, detail="The revision does not belong to the selected SEB")
    if revision.get("revision_status") != "READINESS_COMPLETED":
        raise HTTPException(status_code=400, detail="Only a READINESS_COMPLETED revision can be approved")

    items = await seb_item_collection.find({
        "seb_id": data.seb_id,
        "seb_revision_id": revision_id,
        "status": "reviewed",
    }).to_list(length=5000)
    if not items:
        raise HTTPException(status_code=400, detail="No reviewed SEB items were found")
    if any(not (item.get("discipline_readiness") or {}).get("status") for item in items):
        raise HTTPException(status_code=400, detail="All SEB items must have discipline readiness before approval")

    now = datetime.utcnow().isoformat()
    approval_code = f"APR-{revision.get('revision_no', 'REV')}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    request_status = {
        "APPROVE": "APPROVED_FOR_RELEASE",
        "APPROVE_WITH_CONDITION": "APPROVED_FOR_RELEASE",
        "CHANGE_REQUIRED": "CHANGES_REQUIRED",
        "REJECT": "REJECTED",
    }[data.decision]
    request_doc = {
        "seb_revision_id": revision_id,
        "approval_code": approval_code,
        "approval_status": request_status,
        "submitted_by": data.approver_user_id,
        "submitted_at": now,
        "completed_at": now,
        "submission_comment": data.comment,
    }
    request_result = await approval_request_collection.insert_one(request_doc)
    request_id = str(request_result.inserted_id)

    assignment_doc = {
        "approval_request_id": request_id,
        "seb_item_id": None,
        "approver_user_id": data.approver_user_id,
        "approval_role": "ENGINEERING_APPROVER",
        "discipline": None,
        "approval_sequence": 1,
        "is_mandatory": True,
        "assignment_status": "COMPLETED",
        "assigned_at": now,
        "due_date": None,
    }
    assignment_result = await approval_assignment_collection.insert_one(assignment_doc)
    assignment_id = str(assignment_result.inserted_id)

    decision_doc = {
        "approval_assignment_id": assignment_id,
        "approval_decision": data.decision,
        "approval_comment": data.comment,
        "decided_by": data.approver_user_id,
        "decided_at": now,
    }
    decision_result = await approval_decision_collection.insert_one(decision_doc)
    decision_id = str(decision_result.inserted_id)

    approval = {
        "approval_request_id": request_id,
        "approval_assignment_id": assignment_id,
        "approval_decision_id": decision_id,
        "engineering_approver_id": data.approver_user_id,
        "role": "ENGINEERING_APPROVER",
        "assignment_status": "COMPLETED",
        "decision": data.decision,
        "comment": data.comment,
        "assigned_at": now,
        "decided_at": now,
    }
    revision_update: Dict[str, Any] = {"approval": approval}
    if data.decision in {"APPROVE", "APPROVE_WITH_CONDITION"}:
        revision_update["revision_status"] = "APPROVED_FOR_RELEASE"
    revision_result = await seb_revision_collection.update_one(
        {
            "_id": revision_id,
            "seb_id": data.seb_id,
            "revision_status": "READINESS_COMPLETED",
        },
        {"$set": revision_update},
    )
    if revision_result.matched_count != 1:
        await approval_decision_collection.delete_one({"_id": decision_result.inserted_id})
        await approval_assignment_collection.delete_one({"_id": assignment_result.inserted_id})
        await approval_request_collection.delete_one({"_id": request_result.inserted_id})
        current = await seb_revision_collection.find_one({"_id": revision_id})
        current_status = current.get("revision_status") if current else "NOT_FOUND"
        raise HTTPException(
            status_code=409,
            detail=f"Revision status changed before approval (current status: {current_status})",
        )

    expected_status = (
        "APPROVED_FOR_RELEASE"
        if data.decision in {"APPROVE", "APPROVE_WITH_CONDITION"}
        else "READINESS_COMPLETED"
    )
    stored_revision = await seb_revision_collection.find_one({"_id": revision_id})
    if not stored_revision or stored_revision.get("revision_status") != expected_status:
        raise HTTPException(status_code=500, detail="Revision approval status was not persisted")

    await seb_item_collection.update_many(
        {"seb_id": data.seb_id, "seb_revision_id": revision_id, "status": "reviewed"},
        {"$set": {"approval": approval}},
    )
    return await _build_approval_summary(data.seb_id, revision_id)


@router.post("/seb/revisions/{revision_id}/release", response_model=Dict[str, Any])
async def release_controlled_revision(revision_id: str, data: SEBControlledReleaseCreate):
    """Freeze the approved revision and move it to RELEASED."""
    revision = await seb_revision_collection.find_one({"_id": revision_id})
    if not revision:
        raise HTTPException(status_code=404, detail="SEB revision not found")
    if revision.get("seb_id") != data.seb_id:
        raise HTTPException(status_code=400, detail="The revision does not belong to the selected SEB")
    if revision.get("revision_status") == "RELEASED":
        raise HTTPException(status_code=409, detail="This SEB revision is already released")
    if revision.get("revision_status") != "APPROVED_FOR_RELEASE":
        raise HTTPException(status_code=400, detail="The revision must be APPROVED_FOR_RELEASE before release")

    baseline = await seb_baseline_collection.find_one({"_id": data.seb_id})
    items = await seb_item_collection.find({
        "seb_id": data.seb_id,
        "seb_revision_id": revision_id,
        "status": "reviewed",
    }).to_list(length=5000)
    if not items:
        raise HTTPException(status_code=400, detail="No reviewed SEB items were found to freeze")
    item_ids = [str(item["_id"]) for item in items]
    sources = await seb_item_source_collection.find(
        {"seb_item_id": {"$in": item_ids}}
    ).to_list(length=10000)
    evidence = await seb_evidence_manifest_collection.find(
        {"seb_revision_id": revision_id}
    ).to_list(length=10000)

    released_at = datetime.utcnow().isoformat()
    frozen_items = []
    for item in items:
        frozen_items.append({
            "seb_item_id": str(item["_id"]),
            "fact_id": item.get("fact_id"),
            "fact_collection": item.get("fact_collection"),
            "review_decision": item.get("decision"),
            "readiness": _json_safe(item.get("discipline_readiness")),
            "approval": _json_safe(item.get("approval")),
        })
    frozen_snapshot = {
        "seb_id": data.seb_id,
        "seb_revision_id": revision_id,
        "revision_no": revision.get("revision_no"),
        "item_ids": item_ids,
        "items": frozen_items,
        "fact_source_references": [
            {
                "seb_item_id": str(item["_id"]),
                "fact_id": item.get("fact_id"),
                "fact_collection": item.get("fact_collection"),
            }
            for item in items
        ],
        "item_sources": [_document(source) for source in sources],
        "evidence_references": [_document(record) for record in evidence],
        "approver": _json_safe(revision.get("approval")),
        "released_by": data.released_by,
        "release_timestamp": released_at,
    }
    canonical_snapshot = json.dumps(frozen_snapshot, sort_keys=True, separators=(",", ":"))
    release_hash = hashlib.sha256(canonical_snapshot.encode("utf-8")).hexdigest()
    release_code = f"REL-{baseline.get('seb_code', data.seb_id)}-{revision.get('revision_no', 'REV')}"
    release_doc = {
        "seb_revision_id": revision_id,
        "approval_request_id": (revision.get("approval") or {}).get("approval_request_id"),
        "release_code": release_code,
        "release_status": "RELEASED",
        "release_hash": release_hash,
        "effective_date": released_at[:10],
        "released_by": data.released_by,
        "released_at": released_at,
        "release_comment": data.release_comment,
        "frozen_snapshot": frozen_snapshot,
    }
    release_result = await release_collection.insert_one(release_doc)
    release_id = str(release_result.inserted_id)

    evidence_by_item: Dict[str, List[str]] = {}
    for record in evidence:
        item_id = record.get("seb_item_id")
        evidence_hash = record.get("evidence_hash")
        if item_id and evidence_hash:
            evidence_by_item.setdefault(item_id, []).append(evidence_hash)
    manifest_docs = []
    for frozen_item in frozen_items:
        item_json = json.dumps(frozen_item, sort_keys=True, separators=(",", ":"))
        evidence_hashes = sorted(evidence_by_item.get(frozen_item["seb_item_id"], []))
        manifest_docs.append({
            "seb_release_id": release_id,
            "seb_item_id": frozen_item["seb_item_id"],
            "source_record_type": frozen_item.get("fact_collection"),
            "source_record_id": frozen_item.get("fact_id"),
            "item_hash": hashlib.sha256(item_json.encode("utf-8")).hexdigest(),
            "evidence_hash": hashlib.sha256("|".join(evidence_hashes).encode("utf-8")).hexdigest() if evidence_hashes else None,
            "reliability_status": None,
            "readiness_status": (frozen_item.get("readiness") or {}).get("status"),
            "included_at": released_at,
        })
    if manifest_docs:
        await release_manifest_collection.insert_many(manifest_docs)

    await seb_item_collection.update_many(
        {"_id": {"$in": item_ids}},
        {"$set": {"frozen_at": released_at, "release_id": release_id, "release_hash": release_hash}},
    )
    revision_result = await seb_revision_collection.update_one(
        {
            "_id": revision_id,
            "seb_id": data.seb_id,
            "revision_status": "APPROVED_FOR_RELEASE",
        },
        {"$set": {
            "revision_status": "RELEASED", "released_at": released_at,
            "released_by": data.released_by, "release_id": release_id,
            "release_hash": release_hash,
        }},
    )
    if revision_result.matched_count != 1:
        await release_manifest_collection.delete_many({"seb_release_id": release_id})
        await release_collection.delete_one({"_id": release_result.inserted_id})
        await seb_item_collection.update_many(
            {"release_id": release_id},
            {"$unset": {"frozen_at": "", "release_id": "", "release_hash": ""}},
        )
        current = await seb_revision_collection.find_one({"_id": revision_id})
        current_status = current.get("revision_status") if current else "NOT_FOUND"
        raise HTTPException(
            status_code=409,
            detail=f"Revision status changed before release (current status: {current_status})",
        )

    stored_revision = await seb_revision_collection.find_one({"_id": revision_id})
    if not stored_revision or stored_revision.get("revision_status") != "RELEASED":
        raise HTTPException(status_code=500, detail="Revision release status was not persisted")
    await seb_baseline_collection.update_one(
        {"_id": data.seb_id},
        {"$set": {"status": "RELEASED", "updated_at": datetime.utcnow()}},
    )
    return await _build_approval_summary(data.seb_id, revision_id)


# ═══════════════════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

async def init_approval_release_collections():
    """Initialize collections and indexes."""
    # Approval request indexes
    await approval_request_collection.create_index("seb_revision_id")
    await approval_request_collection.create_index("approval_code")
    
    # Approval assignment indexes
    await approval_assignment_collection.create_index("approval_request_id")
    await approval_assignment_collection.create_index("seb_item_id")
    await approval_assignment_collection.create_index("approver_user_id")
    
    # Approval decision indexes
    await approval_decision_collection.create_index("approval_assignment_id")
    
    # Approval condition indexes
    await approval_condition_collection.create_index("approval_decision_id")
    
    # Release indexes
    await release_collection.create_index("seb_revision_id")
    await release_collection.create_index("release_code")
    await release_collection.create_index("release_hash")
    
    # Release manifest indexes
    await release_manifest_collection.create_index("seb_release_id")
    await release_manifest_collection.create_index("seb_item_id")
    
    # Release rendition indexes
    await release_rendition_collection.create_index("seb_release_id")
    
    print("✓ SEB Approval & Release collections initialized")
