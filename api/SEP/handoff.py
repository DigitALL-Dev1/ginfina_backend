"""
SEB EWB / EWP Handoff API
Pass exact released SEB revision and selected baseline items into downstream engineering work
without losing traceability or silently switching to newer data.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
from uuid import uuid4

router = APIRouter()

# MongoDB connection
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[os.getenv("DATABASE_NAME", "ginfina")]

# Collections
ewb_handoffs = db["seb_ewb_handoff"]
ewb_handoff_items = db["seb_ewb_handoff_item"]
ewb_handoff_conditions = db["seb_ewb_handoff_condition"]
ewb_handoff_evidence = db["seb_ewb_handoff_evidence"]
ewb_handoff_readiness = db["seb_ewb_handoff_readiness"]
ewb_handoff_acceptances = db["seb_ewb_handoff_acceptance"]
ewb_change_subscriptions = db["seb_ewb_change_subscription"]
seb_releases = db["seb_release"]
seb_revisions = db["seb_revision"]
seb_baselines = db["seb_baseline"]
seb_items = db["seb_item"]

# ============================================================
# PYDANTIC MODELS
# ============================================================

# ── SEB EWB Handoff ─────────────────────────────────────────
class SEBEWBHandoffCreate(BaseModel):
    seb_release_id: str
    seb_revision_id: str
    project_id: str
    handoff_code: str
    ewp_reference_id: Optional[str] = None
    ewp_code: Optional[str] = None
    ewp_discipline: Optional[str] = None
    handoff_status: Optional[str] = "DRAFT"
    prepared_by: str
    prepared_at: Optional[str] = None
    sent_at: Optional[str] = None

class SEBEWBHandoffResponse(SEBEWBHandoffCreate):
    id: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    review_comment: Optional[str] = None
    permanent_link: Optional[Dict[str, Any]] = None


class SEBEWBHandoffReviewCreate(BaseModel):
    reviewed_by: str
    review_comment: Optional[str] = None

# ── SEB EWB Handoff Item ────────────────────────────────────
class SEBEWBHandoffItemCreate(BaseModel):
    ewb_handoff_id: str
    seb_item_id: str
    discipline: Optional[str] = None
    applicability: Optional[str] = None
    item_value_snapshot: Optional[str] = None
    unit: Optional[str] = None
    reliability_status: Optional[str] = None
    is_mandatory: Optional[bool] = False
    handoff_status: Optional[str] = "INCLUDED"

class SEBEWBHandoffItemResponse(SEBEWBHandoffItemCreate):
    id: str

# ── SEB EWB Handoff Condition ───────────────────────────────
class SEBEWBHandoffConditionCreate(BaseModel):
    ewb_handoff_id: str
    condition_type: Optional[str] = None  # CONSTRAINT, ASSUMPTION, GAP, RFI, APPROVED_CONDITION
    discipline: Optional[str] = None
    description: str
    impact: Optional[str] = None
    severity: Optional[str] = None  # LOW, MEDIUM, HIGH, CRITICAL
    owner_user_id: Optional[str] = None
    status: Optional[str] = "OPEN"

class SEBEWBHandoffConditionResponse(SEBEWBHandoffConditionCreate):
    id: str

# ── SEB EWB Handoff Evidence ────────────────────────────────
class SEBEWBHandoffEvidenceCreate(BaseModel):
    ewb_handoff_id: str
    handoff_item_id: Optional[str] = None
    sia_evidence_id: str
    evidence_type: Optional[str] = None
    evidence_reference: Optional[str] = None
    evidence_hash: Optional[str] = None
    access_mode: Optional[str] = "READ_ONLY"

class SEBEWBHandoffEvidenceResponse(SEBEWBHandoffEvidenceCreate):
    id: str

# ── SEB EWB Handoff Readiness ───────────────────────────────
class SEBEWBHandoffReadinessCreate(BaseModel):
    ewb_handoff_id: str
    discipline: str
    readiness_status: str  # READY, CONDITIONAL, BLOCKED, NOT_APPLICABLE
    authorising_decision: Optional[str] = None
    authorised_by: Optional[str] = None
    readiness_comment: Optional[str] = None

class SEBEWBHandoffReadinessResponse(SEBEWBHandoffReadinessCreate):
    id: str

# ── SEB EWB Handoff Acceptance ──────────────────────────────
class SEBEWBHandoffAcceptanceCreate(BaseModel):
    ewb_handoff_id: str
    accepted_by: str
    acceptance_decision: Optional[str] = None  # ACCEPT, ACCEPT_WITH_CONDITION, RETURN_FOR_CLARIFICATION, REJECT
    acceptance_comment: Optional[str] = None
    accepted_at: Optional[str] = None

class SEBEWBHandoffAcceptanceResponse(SEBEWBHandoffAcceptanceCreate):
    id: str

# ── SEB EWB Change Subscription ─────────────────────────────
class SEBEWBChangeSubscriptionCreate(BaseModel):
    ewb_handoff_id: str
    subscriber_type: Optional[str] = None  # EWP, EWB, PROJECT_TEAM
    subscriber_reference: Optional[str] = None
    is_active: Optional[bool] = True
    subscribed_at: Optional[str] = None
    last_notified_at: Optional[str] = None

class SEBEWBChangeSubscriptionResponse(SEBEWBChangeSubscriptionCreate):
    id: str

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def serialize_doc(doc):
    """Convert MongoDB document to response format"""
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def find_by_id(collection, document_id: Optional[str]):
    """Find documents whose IDs may be stored as UUID strings or Mongo ObjectIds."""
    if not document_id:
        return None
    candidates = [document_id]
    if ObjectId.is_valid(document_id):
        candidates.append(ObjectId(document_id))
    return await collection.find_one({"_id": {"$in": candidates}})

# ============================================================
# EWB HANDOFF ENDPOINTS
# ============================================================

@router.post("/ewb-handoffs", response_model=SEBEWBHandoffResponse)
async def create_ewb_handoff(handoff: SEBEWBHandoffCreate):
    """Create a new EWB handoff"""
    doc = handoff.dict()
    doc["_id"] = str(uuid4())
    doc["prepared_at"] = doc.get("prepared_at") or datetime.utcnow().isoformat()
    await ewb_handoffs.insert_one(doc)
    return serialize_doc(doc)

@router.get("/ewb-handoffs", response_model=List[SEBEWBHandoffResponse])
async def get_ewb_handoffs(
    seb_release_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    ewp_code: Optional[str] = Query(None),
    handoff_status: Optional[str] = Query(None)
):
    """Get EWB handoffs with optional filters"""
    query = {}
    if seb_release_id:
        query["seb_release_id"] = seb_release_id
    if project_id:
        query["project_id"] = project_id
    if ewp_code:
        query["ewp_code"] = ewp_code
    if handoff_status:
        query["handoff_status"] = handoff_status
    
    cursor = ewb_handoffs.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

@router.get("/ewb-handoffs/{handoff_id}", response_model=SEBEWBHandoffResponse)
async def get_ewb_handoff(handoff_id: str):
    """Get a specific EWB handoff"""
    doc = await ewb_handoffs.find_one({"_id": handoff_id})
    if not doc:
        raise HTTPException(status_code=404, detail="EWB handoff not found")
    return serialize_doc(doc)

@router.patch("/ewb-handoffs/{handoff_id}/send")
async def send_handoff(handoff_id: str):
    """Mark a handoff as sent"""
    result = await ewb_handoffs.update_one(
        {"_id": handoff_id},
        {
            "$set": {
                "handoff_status": "SENT",
                "sent_at": datetime.utcnow().isoformat()
            }
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Handoff not found")
    
    doc = await ewb_handoffs.find_one({"_id": handoff_id})
    return serialize_doc(doc)


@router.patch("/ewb-handoffs/{handoff_id}/review", response_model=SEBEWBHandoffResponse)
async def complete_handoff_review(handoff_id: str, review: SEBEWBHandoffReviewCreate):
    """Record the EWP user's review before an acceptance decision is allowed."""
    handoff = await ewb_handoffs.find_one({"_id": handoff_id})
    if not handoff:
        raise HTTPException(status_code=404, detail="Handoff not found")
    if handoff.get("handoff_status") in {"ACCEPTED", "REJECTED"}:
        raise HTTPException(status_code=409, detail="A completed handoff cannot be reviewed again")

    now = datetime.utcnow().isoformat()
    await ewb_handoffs.update_one(
        {"_id": handoff_id},
        {"$set": {
            "handoff_status": "REVIEWED",
            "reviewed_by": review.reviewed_by,
            "reviewed_at": now,
            "review_comment": review.review_comment,
        }},
    )
    return serialize_doc(await ewb_handoffs.find_one({"_id": handoff_id}))

# ============================================================
# HANDOFF ITEM ENDPOINTS
# ============================================================

@router.post("/ewb-handoff-items", response_model=SEBEWBHandoffItemResponse)
async def create_handoff_item(item: SEBEWBHandoffItemCreate):
    """Create a new handoff item"""
    doc = item.dict()
    doc["_id"] = str(uuid4())
    await ewb_handoff_items.insert_one(doc)
    return serialize_doc(doc)

@router.get("/ewb-handoff-items", response_model=List[SEBEWBHandoffItemResponse])
async def get_handoff_items(
    ewb_handoff_id: Optional[str] = Query(None),
    discipline: Optional[str] = Query(None),
    is_mandatory: Optional[bool] = Query(None)
):
    """Get handoff items with optional filters"""
    query = {}
    if ewb_handoff_id:
        query["ewb_handoff_id"] = ewb_handoff_id
    if discipline:
        query["discipline"] = discipline
    if is_mandatory is not None:
        query["is_mandatory"] = is_mandatory
    
    cursor = ewb_handoff_items.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# HANDOFF CONDITION ENDPOINTS
# ============================================================

@router.post("/ewb-handoff-conditions", response_model=SEBEWBHandoffConditionResponse)
async def create_handoff_condition(condition: SEBEWBHandoffConditionCreate):
    """Create a new handoff condition"""
    doc = condition.dict()
    doc["_id"] = str(uuid4())
    await ewb_handoff_conditions.insert_one(doc)
    return serialize_doc(doc)

@router.get("/ewb-handoff-conditions", response_model=List[SEBEWBHandoffConditionResponse])
async def get_handoff_conditions(
    ewb_handoff_id: Optional[str] = Query(None),
    condition_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
):
    """Get handoff conditions with optional filters"""
    query = {}
    if ewb_handoff_id:
        query["ewb_handoff_id"] = ewb_handoff_id
    if condition_type:
        query["condition_type"] = condition_type
    if status:
        query["status"] = status
    
    cursor = ewb_handoff_conditions.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# HANDOFF EVIDENCE ENDPOINTS
# ============================================================

@router.post("/ewb-handoff-evidence", response_model=SEBEWBHandoffEvidenceResponse)
async def create_handoff_evidence(evidence: SEBEWBHandoffEvidenceCreate):
    """Create a new handoff evidence link"""
    doc = evidence.dict()
    doc["_id"] = str(uuid4())
    await ewb_handoff_evidence.insert_one(doc)
    return serialize_doc(doc)

@router.get("/ewb-handoff-evidence", response_model=List[SEBEWBHandoffEvidenceResponse])
async def get_handoff_evidence(
    ewb_handoff_id: Optional[str] = Query(None),
    handoff_item_id: Optional[str] = Query(None)
):
    """Get handoff evidence with optional filters"""
    query = {}
    if ewb_handoff_id:
        query["ewb_handoff_id"] = ewb_handoff_id
    if handoff_item_id:
        query["handoff_item_id"] = handoff_item_id
    
    cursor = ewb_handoff_evidence.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# HANDOFF READINESS ENDPOINTS
# ============================================================

@router.post("/ewb-handoff-readiness", response_model=SEBEWBHandoffReadinessResponse)
async def create_handoff_readiness(readiness: SEBEWBHandoffReadinessCreate):
    """Create a new handoff readiness record"""
    doc = readiness.dict()
    doc["_id"] = str(uuid4())
    await ewb_handoff_readiness.insert_one(doc)
    return serialize_doc(doc)

@router.get("/ewb-handoff-readiness", response_model=List[SEBEWBHandoffReadinessResponse])
async def get_handoff_readiness(
    ewb_handoff_id: Optional[str] = Query(None),
    discipline: Optional[str] = Query(None),
    readiness_status: Optional[str] = Query(None)
):
    """Get handoff readiness with optional filters"""
    query = {}
    if ewb_handoff_id:
        query["ewb_handoff_id"] = ewb_handoff_id
    if discipline:
        query["discipline"] = discipline
    if readiness_status:
        query["readiness_status"] = readiness_status
    
    cursor = ewb_handoff_readiness.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# HANDOFF ACCEPTANCE ENDPOINTS
# ============================================================

@router.post("/ewb-handoff-acceptances", response_model=SEBEWBHandoffAcceptanceResponse)
async def create_handoff_acceptance(acceptance: SEBEWBHandoffAcceptanceCreate):
    """Record the EWP decision and permanently link accepted work to its released SEB revision."""
    allowed_decisions = {"ACCEPT", "ACCEPT_WITH_CONDITION", "RETURN_FOR_CLARIFICATION", "REJECT"}
    if acceptance.acceptance_decision not in allowed_decisions:
        raise HTTPException(status_code=400, detail="A valid acceptance decision is required")

    handoff = await ewb_handoffs.find_one({"_id": acceptance.ewb_handoff_id})
    if not handoff:
        raise HTTPException(status_code=404, detail="Handoff not found")
    if handoff.get("handoff_status") != "REVIEWED":
        raise HTTPException(status_code=409, detail="The EWP user must complete the handoff review before deciding")

    release = revision = baseline = None
    seb_id = None
    selected_handoff_items = []
    selected_seb_item_ids = []
    if acceptance.acceptance_decision in {"ACCEPT", "ACCEPT_WITH_CONDITION"}:
        release = await find_by_id(seb_releases, handoff.get("seb_release_id"))
        if not release or release.get("release_status") != "RELEASED":
            raise HTTPException(status_code=409, detail="The handoff release record is missing or is no longer RELEASED")
        revision = await find_by_id(seb_revisions, handoff.get("seb_revision_id"))
        snapshot = release.get("frozen_snapshot") or {}
        seb_id = snapshot.get("seb_id") or (revision or {}).get("seb_id")
        baseline = await find_by_id(seb_baselines, seb_id) if seb_id else None
        selected_handoff_items = await ewb_handoff_items.find({
            "ewb_handoff_id": acceptance.ewb_handoff_id,
            "handoff_status": {"$in": ["INCLUDED", "APPROVED"]},
        }).to_list(length=5000)
        selected_seb_item_ids = list({item.get("seb_item_id") for item in selected_handoff_items if item.get("seb_item_id")})
        if not selected_seb_item_ids:
            raise HTTPException(status_code=409, detail="The handoff has no selected SEB items to approve")
        frozen_item_ids = set(snapshot.get("item_ids") or [])
        if frozen_item_ids and any(item_id not in frozen_item_ids for item_id in selected_seb_item_ids):
            raise HTTPException(status_code=409, detail="A selected handoff item is not part of the released revision")
        source_item_count = await seb_items.count_documents({
            "_id": {"$in": selected_seb_item_ids},
            "seb_revision_id": handoff.get("seb_revision_id"),
        })
        if source_item_count != len(selected_seb_item_ids):
            raise HTTPException(status_code=409, detail="One or more selected SEB items could not be verified")

    doc = acceptance.dict()
    doc["_id"] = str(uuid4())
    doc["accepted_at"] = doc.get("accepted_at") or datetime.utcnow().isoformat()
    await ewb_handoff_acceptances.insert_one(doc)

    if acceptance.acceptance_decision in {"ACCEPT", "ACCEPT_WITH_CONDITION"}:
        permanent_link = {
            "ewp_reference_id": handoff.get("ewp_reference_id"),
            "ewp_code": handoff.get("ewp_code"),
            "seb_id": seb_id,
            "seb_code": (baseline or {}).get("seb_code"),
            "seb_revision_id": handoff.get("seb_revision_id"),
            "revision_no": (revision or {}).get("revision_no") or snapshot.get("revision_no"),
            "seb_release_id": handoff.get("seb_release_id"),
            "release_code": release.get("release_code"),
            "release_hash": release.get("release_hash"),
            "acceptance_id": doc["_id"],
            "acceptance_decision": acceptance.acceptance_decision,
            "accepted_by": acceptance.accepted_by,
            "linked_at": doc["accepted_at"],
            "is_permanent": True,
        }
        await ewb_handoffs.update_one(
            {"_id": acceptance.ewb_handoff_id},
            {"$set": {"handoff_status": "ACCEPTED", "permanent_link": permanent_link}}
        )
        item_approval = {
            "status": "approved",
            "ewb_handoff_id": acceptance.ewb_handoff_id,
            "ewp_reference_id": handoff.get("ewp_reference_id"),
            "ewp_code": handoff.get("ewp_code"),
            "acceptance_id": doc["_id"],
            "decision": acceptance.acceptance_decision,
            "approved_by": acceptance.accepted_by,
            "approved_at": doc["accepted_at"],
        }
        await seb_items.update_many(
            {
                "_id": {"$in": selected_seb_item_ids},
                "seb_revision_id": handoff.get("seb_revision_id"),
            },
            {"$set": {"status": "approved", "ewp_handoff_approval": item_approval}},
        )
        await ewb_handoff_items.update_many(
            {"ewb_handoff_id": acceptance.ewb_handoff_id, "seb_item_id": {"$in": selected_seb_item_ids}},
            {"$set": {
                "handoff_status": "APPROVED",
                "approved_by": acceptance.accepted_by,
                "approved_at": doc["accepted_at"],
                "acceptance_id": doc["_id"],
            }},
        )
        await ewb_change_subscriptions.update_one(
            {
                "ewb_handoff_id": acceptance.ewb_handoff_id,
                "subscriber_type": "EWP",
                "subscriber_reference": handoff.get("ewp_reference_id"),
            },
            {"$set": {"is_active": True, "subscribed_at": doc["accepted_at"]}},
            upsert=True,
        )
    elif acceptance.acceptance_decision == "REJECT":
        await ewb_handoffs.update_one(
            {"_id": acceptance.ewb_handoff_id},
            {"$set": {"handoff_status": "REJECTED"}}
        )
    else:
        await ewb_handoffs.update_one(
            {"_id": acceptance.ewb_handoff_id},
            {"$set": {"handoff_status": "RETURNED"}}
        )
    
    return serialize_doc(doc)

@router.get("/ewb-handoff-acceptances", response_model=List[SEBEWBHandoffAcceptanceResponse])
async def get_handoff_acceptances(
    ewb_handoff_id: Optional[str] = Query(None),
    acceptance_decision: Optional[str] = Query(None)
):
    """Get handoff acceptances with optional filters"""
    query = {}
    if ewb_handoff_id:
        query["ewb_handoff_id"] = ewb_handoff_id
    if acceptance_decision:
        query["acceptance_decision"] = acceptance_decision
    
    cursor = ewb_handoff_acceptances.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# CHANGE SUBSCRIPTION ENDPOINTS
# ============================================================

@router.post("/ewb-change-subscriptions", response_model=SEBEWBChangeSubscriptionResponse)
async def create_change_subscription(subscription: SEBEWBChangeSubscriptionCreate):
    """Create a new change subscription"""
    doc = subscription.dict()
    doc["_id"] = str(uuid4())
    doc["subscribed_at"] = doc.get("subscribed_at") or datetime.utcnow().isoformat()
    await ewb_change_subscriptions.insert_one(doc)
    return serialize_doc(doc)

@router.get("/ewb-change-subscriptions", response_model=List[SEBEWBChangeSubscriptionResponse])
async def get_change_subscriptions(
    ewb_handoff_id: Optional[str] = Query(None),
    subscriber_reference: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None)
):
    """Get change subscriptions with optional filters"""
    query = {}
    if ewb_handoff_id:
        query["ewb_handoff_id"] = ewb_handoff_id
    if subscriber_reference:
        query["subscriber_reference"] = subscriber_reference
    if is_active is not None:
        query["is_active"] = is_active
    
    cursor = ewb_change_subscriptions.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

@router.patch("/ewb-change-subscriptions/{subscription_id}/notify")
async def notify_subscription(subscription_id: str):
    """Mark a subscription as notified"""
    result = await ewb_change_subscriptions.update_one(
        {"_id": subscription_id},
        {
            "$set": {
                "last_notified_at": datetime.utcnow().isoformat()
            }
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    doc = await ewb_change_subscriptions.find_one({"_id": subscription_id})
    return serialize_doc(doc)

@router.patch("/ewb-change-subscriptions/{subscription_id}/deactivate")
async def deactivate_subscription(subscription_id: str):
    """Deactivate a subscription"""
    result = await ewb_change_subscriptions.update_one(
        {"_id": subscription_id},
        {"$set": {"is_active": False}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    doc = await ewb_change_subscriptions.find_one({"_id": subscription_id})
    return serialize_doc(doc)
