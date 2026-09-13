"""
SEB Impact Assessment API
Determines what downstream engineering work is affected when an SEB item changes.
Manages impact graph across affected SEB items, EWP inputs, design documents, EBOM, BOQ, and procurement.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import os
from uuid import uuid4

router = APIRouter()

# MongoDB connection
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGODB_URL)
db = client["ginfina"]

# Collections
impact_assessments = db["seb_impact_assessment"]
impact_items = db["seb_impact_item"]
impact_disciplines = db["seb_impact_discipline"]
impact_downstreams = db["seb_impact_downstream"]
impact_actions = db["seb_impact_action"]
impact_reviews = db["seb_impact_review"]
impact_notifications = db["seb_impact_notification"]

# ============================================================
# PYDANTIC MODELS
# ============================================================

# ── SEB Impact Assessment ───────────────────────────────────
class SEBImpactAssessmentCreate(BaseModel):
    revision_change_id: str
    source_revision_id: str
    proposed_revision_id: Optional[str] = None
    impact_code: str
    materiality: Optional[str] = None  # EDITORIAL, NON_MATERIAL, MATERIAL
    overall_impact_level: Optional[str] = None  # NONE, LOW, MEDIUM, HIGH, CRITICAL
    impact_summary: Optional[str] = None
    assessment_status: Optional[str] = "DRAFT"
    assessed_by: str
    assessed_at: Optional[str] = None

class SEBImpactAssessmentResponse(SEBImpactAssessmentCreate):
    id: str

# ── SEB Impact Item ─────────────────────────────────────────
class SEBImpactItemCreate(BaseModel):
    impact_assessment_id: str
    old_seb_item_id: Optional[str] = None
    new_seb_item_id: Optional[str] = None
    change_type: Optional[str] = None  # ADDED, REMOVED, MODIFIED, SUPERSEDED
    discipline: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    impact_level: Optional[str] = None  # NONE, LOW, MEDIUM, HIGH, CRITICAL
    impact_description: Optional[str] = None

class SEBImpactItemResponse(SEBImpactItemCreate):
    id: str

# ── SEB Impact Discipline ───────────────────────────────────
class SEBImpactDisciplineCreate(BaseModel):
    impact_assessment_id: str
    discipline: str
    is_affected: Optional[bool] = False
    impact_level: Optional[str] = None  # NONE, LOW, MEDIUM, HIGH, CRITICAL
    readiness_recheck: Optional[bool] = False
    reassessment_required: Optional[bool] = False
    reason: Optional[str] = None

class SEBImpactDisciplineResponse(SEBImpactDisciplineCreate):
    id: str

# ── SEB Impact Downstream ───────────────────────────────────
class SEBImpactDownstreamCreate(BaseModel):
    impact_assessment_id: str
    impact_item_id: Optional[str] = None
    downstream_type: str  # EWP, EWB_INPUT, DESIGN_DOCUMENT, DESIGN_RELEASE, EBOM, BOQ, PROCUREMENT_REFERENCE
    downstream_reference: str
    downstream_name: Optional[str] = None
    current_revision: Optional[str] = None
    impact_level: Optional[str] = None  # NONE, LOW, MEDIUM, HIGH, CRITICAL
    impact_description: Optional[str] = None
    action_required: Optional[bool] = False
    status: Optional[str] = "IDENTIFIED"

class SEBImpactDownstreamResponse(SEBImpactDownstreamCreate):
    id: str

# ── SEB Impact Action ───────────────────────────────────────
class SEBImpactActionCreate(BaseModel):
    impact_assessment_id: str
    downstream_impact_id: Optional[str] = None
    action_code: Optional[str] = None
    action_type: Optional[str] = None  # REVIEW_EWP, UPDATE_DESIGN, RECALCULATE, etc.
    action_description: str
    owner_user_id: Optional[str] = None
    priority: Optional[str] = None  # P0, P1, P2, P3
    target_date: Optional[str] = None
    action_status: Optional[str] = "OPEN"
    completion_comment: Optional[str] = None
    completed_at: Optional[str] = None

class SEBImpactActionResponse(SEBImpactActionCreate):
    id: str

# ── SEB Impact Review ───────────────────────────────────────
class SEBImpactReviewCreate(BaseModel):
    impact_assessment_id: str
    reviewer_user_id: str
    discipline: Optional[str] = None
    review_decision: Optional[str] = None  # IMPACT_CONFIRMED, NO_IMPACT, REASSESSMENT_REQUIRED, etc.
    review_comment: Optional[str] = None
    reviewed_at: Optional[str] = None

class SEBImpactReviewResponse(SEBImpactReviewCreate):
    id: str

# ── SEB Impact Notification ─────────────────────────────────
class SEBImpactNotificationCreate(BaseModel):
    impact_assessment_id: str
    downstream_impact_id: Optional[str] = None
    recipient_type: Optional[str] = None  # EWB, EWP_OWNER, PROJECT_ENGINEER, etc.
    recipient_reference: Optional[str] = None
    recipient_user_id: Optional[str] = None
    notification_type: Optional[str] = None  # EMAIL, SYSTEM, SMS
    notification_status: Optional[str] = "PENDING"
    sent_at: Optional[str] = None
    acknowledged_at: Optional[str] = None

class SEBImpactNotificationResponse(SEBImpactNotificationCreate):
    id: str

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def serialize_doc(doc):
    """Convert MongoDB document to response format"""
    if doc and "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc

# ============================================================
# IMPACT ASSESSMENT ENDPOINTS
# ============================================================

@router.post("/impact-assessments", response_model=SEBImpactAssessmentResponse)
async def create_impact_assessment(assessment: SEBImpactAssessmentCreate):
    """Create a new impact assessment"""
    doc = assessment.dict()
    doc["_id"] = str(uuid4())
    doc["assessed_at"] = doc.get("assessed_at") or datetime.utcnow().isoformat()
    await impact_assessments.insert_one(doc)
    return serialize_doc(doc)

@router.get("/impact-assessments", response_model=List[SEBImpactAssessmentResponse])
async def get_impact_assessments(
    revision_change_id: Optional[str] = Query(None),
    source_revision_id: Optional[str] = Query(None),
    assessment_status: Optional[str] = Query(None)
):
    """Get impact assessments with optional filters"""
    query = {}
    if revision_change_id:
        query["revision_change_id"] = revision_change_id
    if source_revision_id:
        query["source_revision_id"] = source_revision_id
    if assessment_status:
        query["assessment_status"] = assessment_status
    
    cursor = impact_assessments.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

@router.get("/impact-assessments/{assessment_id}", response_model=SEBImpactAssessmentResponse)
async def get_impact_assessment(assessment_id: str):
    """Get a specific impact assessment"""
    doc = await impact_assessments.find_one({"_id": assessment_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Impact assessment not found")
    return serialize_doc(doc)

# ============================================================
# IMPACT ITEM ENDPOINTS
# ============================================================

@router.post("/impact-items", response_model=SEBImpactItemResponse)
async def create_impact_item(item: SEBImpactItemCreate):
    """Create a new impact item"""
    doc = item.dict()
    doc["_id"] = str(uuid4())
    await impact_items.insert_one(doc)
    return serialize_doc(doc)

@router.get("/impact-items", response_model=List[SEBImpactItemResponse])
async def get_impact_items(
    impact_assessment_id: Optional[str] = Query(None),
    discipline: Optional[str] = Query(None)
):
    """Get impact items with optional filters"""
    query = {}
    if impact_assessment_id:
        query["impact_assessment_id"] = impact_assessment_id
    if discipline:
        query["discipline"] = discipline
    
    cursor = impact_items.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# IMPACT DISCIPLINE ENDPOINTS
# ============================================================

@router.post("/impact-disciplines", response_model=SEBImpactDisciplineResponse)
async def create_impact_discipline(discipline: SEBImpactDisciplineCreate):
    """Create a new impact discipline"""
    doc = discipline.dict()
    doc["_id"] = str(uuid4())
    await impact_disciplines.insert_one(doc)
    return serialize_doc(doc)

@router.get("/impact-disciplines", response_model=List[SEBImpactDisciplineResponse])
async def get_impact_disciplines(
    impact_assessment_id: Optional[str] = Query(None),
    is_affected: Optional[bool] = Query(None)
):
    """Get impact disciplines with optional filters"""
    query = {}
    if impact_assessment_id:
        query["impact_assessment_id"] = impact_assessment_id
    if is_affected is not None:
        query["is_affected"] = is_affected
    
    cursor = impact_disciplines.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# IMPACT DOWNSTREAM ENDPOINTS
# ============================================================

@router.post("/impact-downstreams", response_model=SEBImpactDownstreamResponse)
async def create_impact_downstream(downstream: SEBImpactDownstreamCreate):
    """Create a new impact downstream record"""
    doc = downstream.dict()
    doc["_id"] = str(uuid4())
    await impact_downstreams.insert_one(doc)
    return serialize_doc(doc)

@router.get("/impact-downstreams", response_model=List[SEBImpactDownstreamResponse])
async def get_impact_downstreams(
    impact_assessment_id: Optional[str] = Query(None),
    downstream_type: Optional[str] = Query(None),
    action_required: Optional[bool] = Query(None)
):
    """Get impact downstream records with optional filters"""
    query = {}
    if impact_assessment_id:
        query["impact_assessment_id"] = impact_assessment_id
    if downstream_type:
        query["downstream_type"] = downstream_type
    if action_required is not None:
        query["action_required"] = action_required
    
    cursor = impact_downstreams.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# IMPACT ACTION ENDPOINTS
# ============================================================

@router.post("/impact-actions", response_model=SEBImpactActionResponse)
async def create_impact_action(action: SEBImpactActionCreate):
    """Create a new impact action"""
    doc = action.dict()
    doc["_id"] = str(uuid4())
    await impact_actions.insert_one(doc)
    return serialize_doc(doc)

@router.get("/impact-actions", response_model=List[SEBImpactActionResponse])
async def get_impact_actions(
    impact_assessment_id: Optional[str] = Query(None),
    action_status: Optional[str] = Query(None),
    owner_user_id: Optional[str] = Query(None)
):
    """Get impact actions with optional filters"""
    query = {}
    if impact_assessment_id:
        query["impact_assessment_id"] = impact_assessment_id
    if action_status:
        query["action_status"] = action_status
    if owner_user_id:
        query["owner_user_id"] = owner_user_id
    
    cursor = impact_actions.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# IMPACT REVIEW ENDPOINTS
# ============================================================

@router.post("/impact-reviews", response_model=SEBImpactReviewResponse)
async def create_impact_review(review: SEBImpactReviewCreate):
    """Create a new impact review"""
    doc = review.dict()
    doc["_id"] = str(uuid4())
    doc["reviewed_at"] = doc.get("reviewed_at") or datetime.utcnow().isoformat()
    await impact_reviews.insert_one(doc)
    return serialize_doc(doc)

@router.get("/impact-reviews", response_model=List[SEBImpactReviewResponse])
async def get_impact_reviews(
    impact_assessment_id: Optional[str] = Query(None),
    reviewer_user_id: Optional[str] = Query(None),
    discipline: Optional[str] = Query(None)
):
    """Get impact reviews with optional filters"""
    query = {}
    if impact_assessment_id:
        query["impact_assessment_id"] = impact_assessment_id
    if reviewer_user_id:
        query["reviewer_user_id"] = reviewer_user_id
    if discipline:
        query["discipline"] = discipline
    
    cursor = impact_reviews.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

# ============================================================
# IMPACT NOTIFICATION ENDPOINTS
# ============================================================

@router.post("/impact-notifications", response_model=SEBImpactNotificationResponse)
async def create_impact_notification(notification: SEBImpactNotificationCreate):
    """Create a new impact notification"""
    doc = notification.dict()
    doc["_id"] = str(uuid4())
    await impact_notifications.insert_one(doc)
    return serialize_doc(doc)

@router.get("/impact-notifications", response_model=List[SEBImpactNotificationResponse])
async def get_impact_notifications(
    impact_assessment_id: Optional[str] = Query(None),
    recipient_user_id: Optional[str] = Query(None),
    notification_status: Optional[str] = Query(None)
):
    """Get impact notifications with optional filters"""
    query = {}
    if impact_assessment_id:
        query["impact_assessment_id"] = impact_assessment_id
    if recipient_user_id:
        query["recipient_user_id"] = recipient_user_id
    if notification_status:
        query["notification_status"] = notification_status
    
    cursor = impact_notifications.find(query)
    results = await cursor.to_list(length=1000)
    return [serialize_doc(doc) for doc in results]

@router.patch("/impact-notifications/{notification_id}/acknowledge")
async def acknowledge_notification(notification_id: str):
    """Mark a notification as acknowledged"""
    result = await impact_notifications.update_one(
        {"_id": notification_id},
        {
            "$set": {
                "notification_status": "ACKNOWLEDGED",
                "acknowledged_at": datetime.utcnow().isoformat()
            }
        }
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    doc = await impact_notifications.find_one({"_id": notification_id})
    return serialize_doc(doc)
