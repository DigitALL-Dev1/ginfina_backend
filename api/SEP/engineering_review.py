from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import os
import uuid
from dotenv import load_dotenv

load_dotenv(override=True)

# MongoDB Configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]

# SEB Review Collections
seb_review_collection = db["seb_review"]
seb_review_assignment_collection = db["seb_review_assignment"]
seb_review_item_collection = db["seb_review_item"]
seb_review_comment_collection = db["seb_review_comment"]
seb_review_disposition_collection = db["seb_review_disposition"]
seb_review_issue_collection = db["seb_review_issue"]
seb_review_verification_collection = db["seb_review_verification"]

router = APIRouter()

# ═════════════════════════════════════════════════════════
# SEB REVIEW — Models
# ═════════════════════════════════════════════════════════

class SEBReviewCreate(BaseModel):
    seb_revision_id: str = Field(..., description="FK → seb_revision._id (NOT NULL)")
    review_code: str = Field(..., max_length=50, description="varchar(50) NOT NULL")
    review_type: Optional[str] = Field(None, max_length=50, description="varchar(50)")
    review_status: Optional[str] = Field("DRAFT", max_length=50, description="DRAFT | IN_REVIEW | CHANGES_REQUIRED | COMPLETED | CANCELLED")
    initiated_by: str = Field(..., description="FK → users._id (NOT NULL)")

class SEBReviewResponse(BaseModel):
    id: str
    seb_revision_id: str
    review_code: str
    review_type: Optional[str]
    review_status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    initiated_by: str

# ═════════════════════════════════════════════════════════
# SEB REVIEW ASSIGNMENT — Models
# ═════════════════════════════════════════════════════════

class SEBReviewAssignmentCreate(BaseModel):
    seb_review_id: str = Field(..., description="FK → seb_review._id (NOT NULL)")
    reviewer_user_id: str = Field(..., description="FK → users._id (NOT NULL)")
    discipline: str = Field(..., max_length=100, description="ELECTRICAL | CIVIL | STRUCTURAL | MECHANICAL | WATER_PUMPING | SCADA | HSE | CLIMATE_ENVIRONMENT | LOGISTICS")
    reviewer_role: Optional[str] = Field(None, max_length=100, description="varchar(100)")
    due_date: Optional[str] = Field(None, description="date in YYYY-MM-DD format")
    assignment_status: Optional[str] = Field("ASSIGNED", max_length=50, description="varchar(50)")

class SEBReviewAssignmentResponse(BaseModel):
    id: str
    seb_review_id: str
    reviewer_user_id: str
    discipline: str
    reviewer_role: Optional[str]
    assigned_at: datetime
    due_date: Optional[str]
    assignment_status: str

# ═════════════════════════════════════════════════════════
# SEB REVIEW ITEM — Models
# ═════════════════════════════════════════════════════════

class SEBReviewItemCreate(BaseModel):
    review_assignment_id: str = Field(..., description="FK → seb_review_assignment._id (NOT NULL)")
    seb_item_id: str = Field(..., description="FK → seb_item._id (NOT NULL)")
    item_review_status: Optional[str] = Field("PENDING", max_length=50, description="PENDING | ACCEPTED | CHANGE_REQUIRED | REJECTED | NOT_APPLICABLE")
    requires_action: Optional[bool] = Field(False, description="boolean")

class SEBReviewItemResponse(BaseModel):
    id: str
    review_assignment_id: str
    seb_item_id: str
    item_review_status: str
    requires_action: bool
    reviewed_at: Optional[datetime]

# ═════════════════════════════════════════════════════════
# SEB REVIEW COMMENT — Models
# ═════════════════════════════════════════════════════════

class SEBReviewCommentCreate(BaseModel):
    seb_review_id: str = Field(..., description="FK → seb_review._id (NOT NULL)")
    review_assignment_id: Optional[str] = Field(None, description="FK → seb_review_assignment._id")
    seb_item_id: Optional[str] = Field(None, description="FK → seb_item._id")
    commented_by: str = Field(..., description="FK → users._id (NOT NULL)")
    comment_type: Optional[str] = Field("GENERAL", max_length=50, description="GENERAL | TECHNICAL | CLARIFICATION | CHANGE_REQUEST | CONDITION")
    comment_text: str = Field(..., description="text NOT NULL")

class SEBReviewCommentResponse(BaseModel):
    id: str
    seb_review_id: str
    review_assignment_id: Optional[str]
    seb_item_id: Optional[str]
    commented_by: str
    comment_type: str
    comment_text: str
    created_at: datetime

# ═════════════════════════════════════════════════════════
# SEB REVIEW DISPOSITION — Models
# ═════════════════════════════════════════════════════════

class SEBReviewDispositionCreate(BaseModel):
    review_assignment_id: str = Field(..., description="FK → seb_review_assignment._id (NOT NULL)")
    seb_item_id: Optional[str] = Field(None, description="FK → seb_item._id")
    disposition: str = Field(..., max_length=50, description="ACCEPT | REJECT | MODIFY | ESCALATE | REQUEST_EVIDENCE")
    disposition_reason: Optional[str] = Field(None, description="text")
    proposed_value: Optional[str] = Field(None, description="text")
    dispositioned_by: str = Field(..., description="FK → users._id (NOT NULL)")

class SEBReviewDispositionResponse(BaseModel):
    id: str
    review_assignment_id: str
    seb_item_id: Optional[str]
    disposition: str
    disposition_reason: Optional[str]
    proposed_value: Optional[str]
    dispositioned_by: str
    dispositioned_at: datetime

# ═════════════════════════════════════════════════════════
# SEB REVIEW ISSUE — Models
# ═════════════════════════════════════════════════════════

class SEBReviewIssueCreate(BaseModel):
    seb_review_id: str = Field(..., description="FK → seb_review._id (NOT NULL)")
    seb_item_id: Optional[str] = Field(None, description="FK → seb_item._id")
    issue_code: Optional[str] = Field(None, max_length=50, description="varchar(50)")
    discipline: Optional[str] = Field(None, max_length=100, description="varchar(100)")
    issue_type: Optional[str] = Field(None, max_length=100, description="MISSING_EVIDENCE | CONFLICT | TECHNICAL_ERROR | UNVERIFIED_VALUE | READINESS_BLOCKER | CLARIFICATION")
    issue_description: Optional[str] = Field(None, description="text")
    severity: Optional[str] = Field(None, max_length=50, description="varchar(50)")
    owner_user_id: Optional[str] = Field(None, description="FK → users._id")
    target_date: Optional[str] = Field(None, description="date in YYYY-MM-DD format")
    issue_status: Optional[str] = Field("OPEN", max_length=50, description="varchar(50)")
    resolution_note: Optional[str] = Field(None, description="text")

class SEBReviewIssueResponse(BaseModel):
    id: str
    seb_review_id: str
    seb_item_id: Optional[str]
    issue_code: Optional[str]
    discipline: Optional[str]
    issue_type: Optional[str]
    issue_description: Optional[str]
    severity: Optional[str]
    owner_user_id: Optional[str]
    target_date: Optional[str]
    issue_status: str
    resolution_note: Optional[str]
    resolved_at: Optional[datetime]

# ═════════════════════════════════════════════════════════
# SEB REVIEW VERIFICATION — Models
# ═════════════════════════════════════════════════════════

class SEBReviewVerificationCreate(BaseModel):
    review_assignment_id: str = Field(..., description="FK → seb_review_assignment._id (NOT NULL)")
    discipline: str = Field(..., max_length=100, description="varchar(100) NOT NULL")
    verification_status: Optional[str] = Field("PENDING", max_length=50, description="VERIFIED | VERIFIED_WITH_CONDITION | NOT_VERIFIED | REVIEW_REQUIRED")
    verification_comment: Optional[str] = Field(None, description="text")
    verified_by: str = Field(..., description="FK → users._id (NOT NULL)")

class SEBReviewVerificationResponse(BaseModel):
    id: str
    review_assignment_id: str
    discipline: str
    verification_status: str
    verification_comment: Optional[str]
    verified_by: str
    verified_at: datetime

# ═════════════════════════════════════════════════════════
# Serializers
# ═════════════════════════════════════════════════════════

def serialize_seb_review(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_revision_id": doc["seb_revision_id"],
        "review_code": doc["review_code"],
        "review_type": doc.get("review_type"),
        "review_status": doc.get("review_status", "DRAFT"),
        "started_at": doc.get("started_at"),
        "completed_at": doc.get("completed_at"),
        "initiated_by": doc["initiated_by"],
    }

def serialize_seb_review_assignment(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_review_id": doc["seb_review_id"],
        "reviewer_user_id": doc["reviewer_user_id"],
        "discipline": doc["discipline"],
        "reviewer_role": doc.get("reviewer_role"),
        "assigned_at": doc["assigned_at"],
        "due_date": doc.get("due_date"),
        "assignment_status": doc.get("assignment_status", "ASSIGNED"),
    }

def serialize_seb_review_item(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "review_assignment_id": doc["review_assignment_id"],
        "seb_item_id": doc["seb_item_id"],
        "item_review_status": doc.get("item_review_status", "PENDING"),
        "requires_action": doc.get("requires_action", False),
        "reviewed_at": doc.get("reviewed_at"),
    }

def serialize_seb_review_comment(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_review_id": doc["seb_review_id"],
        "review_assignment_id": doc.get("review_assignment_id"),
        "seb_item_id": doc.get("seb_item_id"),
        "commented_by": doc["commented_by"],
        "comment_type": doc.get("comment_type", "GENERAL"),
        "comment_text": doc["comment_text"],
        "created_at": doc["created_at"],
    }

def serialize_seb_review_disposition(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "review_assignment_id": doc["review_assignment_id"],
        "seb_item_id": doc.get("seb_item_id"),
        "disposition": doc["disposition"],
        "disposition_reason": doc.get("disposition_reason"),
        "proposed_value": doc.get("proposed_value"),
        "dispositioned_by": doc["dispositioned_by"],
        "dispositioned_at": doc["dispositioned_at"],
    }

def serialize_seb_review_issue(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_review_id": doc["seb_review_id"],
        "seb_item_id": doc.get("seb_item_id"),
        "issue_code": doc.get("issue_code"),
        "discipline": doc.get("discipline"),
        "issue_type": doc.get("issue_type"),
        "issue_description": doc.get("issue_description"),
        "severity": doc.get("severity"),
        "owner_user_id": doc.get("owner_user_id"),
        "target_date": doc.get("target_date"),
        "issue_status": doc.get("issue_status", "OPEN"),
        "resolution_note": doc.get("resolution_note"),
        "resolved_at": doc.get("resolved_at"),
    }

def serialize_seb_review_verification(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "review_assignment_id": doc["review_assignment_id"],
        "discipline": doc["discipline"],
        "verification_status": doc.get("verification_status", "PENDING"),
        "verification_comment": doc.get("verification_comment"),
        "verified_by": doc["verified_by"],
        "verified_at": doc["verified_at"],
    }

# ═════════════════════════════════════════════════════════
# Init — indexes
# ═════════════════════════════════════════════════════════

async def init_seb_review_collections():
    """Create indexes for all SEB Review collections."""
    
    # seb_review indexes
    await seb_review_collection.create_index("seb_revision_id")
    await seb_review_collection.create_index("review_code")
    await seb_review_collection.create_index("review_status")
    await seb_review_collection.create_index("initiated_by")
    print("seb_review collection initialized")
    
    # seb_review_assignment indexes
    await seb_review_assignment_collection.create_index("seb_review_id")
    await seb_review_assignment_collection.create_index("reviewer_user_id")
    await seb_review_assignment_collection.create_index("discipline")
    await seb_review_assignment_collection.create_index("assignment_status")
    print("seb_review_assignment collection initialized")
    
    # seb_review_item indexes
    await seb_review_item_collection.create_index("review_assignment_id")
    await seb_review_item_collection.create_index("seb_item_id")
    await seb_review_item_collection.create_index("item_review_status")
    print("seb_review_item collection initialized")
    
    # seb_review_comment indexes
    await seb_review_comment_collection.create_index("seb_review_id")
    await seb_review_comment_collection.create_index("review_assignment_id")
    await seb_review_comment_collection.create_index("seb_item_id")
    await seb_review_comment_collection.create_index("commented_by")
    print("seb_review_comment collection initialized")
    
    # seb_review_disposition indexes
    await seb_review_disposition_collection.create_index("review_assignment_id")
    await seb_review_disposition_collection.create_index("seb_item_id")
    await seb_review_disposition_collection.create_index("disposition")
    await seb_review_disposition_collection.create_index("dispositioned_by")
    print("seb_review_disposition collection initialized")
    
    # seb_review_issue indexes
    await seb_review_issue_collection.create_index("seb_review_id")
    await seb_review_issue_collection.create_index("seb_item_id")
    await seb_review_issue_collection.create_index("issue_code")
    await seb_review_issue_collection.create_index("issue_status")
    await seb_review_issue_collection.create_index("owner_user_id")
    print("seb_review_issue collection initialized")
    
    # seb_review_verification indexes
    await seb_review_verification_collection.create_index("review_assignment_id")
    await seb_review_verification_collection.create_index("discipline")
    await seb_review_verification_collection.create_index("verification_status")
    await seb_review_verification_collection.create_index("verified_by")
    print("seb_review_verification collection initialized")

# ═════════════════════════════════════════════════════════
# SEB REVIEW — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/reviews",
    response_model=SEBReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SEB Review",
    description="Creates a new engineering review cycle for a SEB revision.",
)
async def create_seb_review(data: SEBReviewCreate):
    # Validate seb_revision exists
    seb_revision_collection = db["seb_revision"]
    revision = await seb_revision_collection.find_one({"_id": data.seb_revision_id})
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB revision '{data.seb_revision_id}' not found",
        )
    
    new_review = {
        "_id": str(uuid.uuid4()),
        "seb_revision_id": data.seb_revision_id,
        "review_code": data.review_code,
        "review_type": data.review_type,
        "review_status": data.review_status,
        "started_at": datetime.utcnow() if data.review_status == "IN_REVIEW" else None,
        "completed_at": None,
        "initiated_by": data.initiated_by,
    }
    await seb_review_collection.insert_one(new_review)
    return serialize_seb_review(new_review)

@router.get(
    "/seb/reviews",
    response_model=List[SEBReviewResponse],
    summary="Get All SEB Reviews",
    description="Returns all SEB reviews, optionally filtered by seb_revision_id.",
)
async def get_all_seb_reviews(seb_revision_id: Optional[str] = None):
    query = {"seb_revision_id": seb_revision_id} if seb_revision_id else {}
    cursor = seb_review_collection.find(query).sort("started_at", -1)
    reviews = await cursor.to_list(length=1000)
    return [serialize_seb_review(r) for r in reviews]

@router.get(
    "/seb/reviews/{review_id}",
    response_model=SEBReviewResponse,
    summary="Get SEB Review by ID",
    description="Fetch a single SEB review by its ID.",
)
async def get_seb_review(review_id: str):
    review = await seb_review_collection.find_one({"_id": review_id})
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB review with id '{review_id}' not found",
        )
    return serialize_seb_review(review)

# ═════════════════════════════════════════════════════════
# SEB REVIEW ASSIGNMENT — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/review-assignments",
    response_model=SEBReviewAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Review Assignment",
    description="Assigns a discipline reviewer to a SEB review.",
)
async def create_review_assignment(data: SEBReviewAssignmentCreate):
    # Validate seb_review exists
    review = await seb_review_collection.find_one({"_id": data.seb_review_id})
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB review '{data.seb_review_id}' not found",
        )
    
    new_assignment = {
        "_id": str(uuid.uuid4()),
        "seb_review_id": data.seb_review_id,
        "reviewer_user_id": data.reviewer_user_id,
        "discipline": data.discipline,
        "reviewer_role": data.reviewer_role,
        "assigned_at": datetime.utcnow(),
        "due_date": data.due_date,
        "assignment_status": data.assignment_status,
    }
    await seb_review_assignment_collection.insert_one(new_assignment)
    return serialize_seb_review_assignment(new_assignment)

@router.get(
    "/seb/review-assignments",
    response_model=List[SEBReviewAssignmentResponse],
    summary="Get All Review Assignments",
    description="Returns all review assignments, optionally filtered by seb_review_id or reviewer_user_id.",
)
async def get_all_review_assignments(
    seb_review_id: Optional[str] = None,
    reviewer_user_id: Optional[str] = None
):
    query = {}
    if seb_review_id:
        query["seb_review_id"] = seb_review_id
    if reviewer_user_id:
        query["reviewer_user_id"] = reviewer_user_id
    
    cursor = seb_review_assignment_collection.find(query).sort("assigned_at", -1)
    assignments = await cursor.to_list(length=1000)
    return [serialize_seb_review_assignment(a) for a in assignments]

# ═════════════════════════════════════════════════════════
# SEB REVIEW ITEM — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/review-items",
    response_model=SEBReviewItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Review Item",
    description="Links a SEB item to a review assignment for review.",
)
async def create_review_item(data: SEBReviewItemCreate):
    # Validate review_assignment exists
    assignment = await seb_review_assignment_collection.find_one({"_id": data.review_assignment_id})
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review assignment '{data.review_assignment_id}' not found",
        )
    
    new_item = {
        "_id": str(uuid.uuid4()),
        "review_assignment_id": data.review_assignment_id,
        "seb_item_id": data.seb_item_id,
        "item_review_status": data.item_review_status,
        "requires_action": data.requires_action,
        "reviewed_at": None,
    }
    await seb_review_item_collection.insert_one(new_item)
    return serialize_seb_review_item(new_item)

@router.get(
    "/seb/review-items",
    response_model=List[SEBReviewItemResponse],
    summary="Get All Review Items",
    description="Returns all review items, optionally filtered by review_assignment_id.",
)
async def get_all_review_items(review_assignment_id: Optional[str] = None):
    query = {"review_assignment_id": review_assignment_id} if review_assignment_id else {}
    cursor = seb_review_item_collection.find(query)
    items = await cursor.to_list(length=5000)
    return [serialize_seb_review_item(i) for i in items]

# ═════════════════════════════════════════════════════════
# SEB REVIEW COMMENT — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/review-comments",
    response_model=SEBReviewCommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Review Comment",
    description="Adds a reviewer comment to the SEB review.",
)
async def create_review_comment(data: SEBReviewCommentCreate):
    # Validate seb_review exists
    review = await seb_review_collection.find_one({"_id": data.seb_review_id})
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB review '{data.seb_review_id}' not found",
        )
    
    new_comment = {
        "_id": str(uuid.uuid4()),
        "seb_review_id": data.seb_review_id,
        "review_assignment_id": data.review_assignment_id,
        "seb_item_id": data.seb_item_id,
        "commented_by": data.commented_by,
        "comment_type": data.comment_type,
        "comment_text": data.comment_text,
        "created_at": datetime.utcnow(),
    }
    await seb_review_comment_collection.insert_one(new_comment)
    return serialize_seb_review_comment(new_comment)

@router.get(
    "/seb/review-comments",
    response_model=List[SEBReviewCommentResponse],
    summary="Get All Review Comments",
    description="Returns all review comments, optionally filtered by seb_review_id.",
)
async def get_all_review_comments(seb_review_id: Optional[str] = None):
    query = {"seb_review_id": seb_review_id} if seb_review_id else {}
    cursor = seb_review_comment_collection.find(query).sort("created_at", -1)
    comments = await cursor.to_list(length=5000)
    return [serialize_seb_review_comment(c) for c in comments]

# ═════════════════════════════════════════════════════════
# SEB REVIEW DISPOSITION — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/review-dispositions",
    response_model=SEBReviewDispositionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Review Disposition",
    description="Records a reviewer decision on a SEB item.",
)
async def create_review_disposition(data: SEBReviewDispositionCreate):
    # Validate review_assignment exists
    assignment = await seb_review_assignment_collection.find_one({"_id": data.review_assignment_id})
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review assignment '{data.review_assignment_id}' not found",
        )
    
    new_disposition = {
        "_id": str(uuid.uuid4()),
        "review_assignment_id": data.review_assignment_id,
        "seb_item_id": data.seb_item_id,
        "disposition": data.disposition,
        "disposition_reason": data.disposition_reason,
        "proposed_value": data.proposed_value,
        "dispositioned_by": data.dispositioned_by,
        "dispositioned_at": datetime.utcnow(),
    }
    await seb_review_disposition_collection.insert_one(new_disposition)
    return serialize_seb_review_disposition(new_disposition)

@router.get(
    "/seb/review-dispositions",
    response_model=List[SEBReviewDispositionResponse],
    summary="Get All Review Dispositions",
    description="Returns all review dispositions, optionally filtered by review_assignment_id.",
)
async def get_all_review_dispositions(review_assignment_id: Optional[str] = None):
    query = {"review_assignment_id": review_assignment_id} if review_assignment_id else {}
    cursor = seb_review_disposition_collection.find(query).sort("dispositioned_at", -1)
    dispositions = await cursor.to_list(length=5000)
    return [serialize_seb_review_disposition(d) for d in dispositions]

# ═════════════════════════════════════════════════════════
# SEB REVIEW ISSUE — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/review-issues",
    response_model=SEBReviewIssueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Review Issue",
    description="Tracks an issue raised during engineering review.",
)
async def create_review_issue(data: SEBReviewIssueCreate):
    # Validate seb_review exists
    review = await seb_review_collection.find_one({"_id": data.seb_review_id})
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB review '{data.seb_review_id}' not found",
        )
    
    new_issue = {
        "_id": str(uuid.uuid4()),
        "seb_review_id": data.seb_review_id,
        "seb_item_id": data.seb_item_id,
        "issue_code": data.issue_code,
        "discipline": data.discipline,
        "issue_type": data.issue_type,
        "issue_description": data.issue_description,
        "severity": data.severity,
        "owner_user_id": data.owner_user_id,
        "target_date": data.target_date,
        "issue_status": data.issue_status,
        "resolution_note": data.resolution_note,
        "resolved_at": None,
    }
    await seb_review_issue_collection.insert_one(new_issue)
    return serialize_seb_review_issue(new_issue)

@router.get(
    "/seb/review-issues",
    response_model=List[SEBReviewIssueResponse],
    summary="Get All Review Issues",
    description="Returns all review issues, optionally filtered by seb_review_id or issue_status.",
)
async def get_all_review_issues(
    seb_review_id: Optional[str] = None,
    issue_status: Optional[str] = None
):
    query = {}
    if seb_review_id:
        query["seb_review_id"] = seb_review_id
    if issue_status:
        query["issue_status"] = issue_status
    
    cursor = seb_review_issue_collection.find(query)
    issues = await cursor.to_list(length=5000)
    return [serialize_seb_review_issue(i) for i in issues]

# ═════════════════════════════════════════════════════════
# SEB REVIEW VERIFICATION — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/review-verifications",
    response_model=SEBReviewVerificationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Review Verification",
    description="Records formal engineering verification by an authorized reviewer.",
)
async def create_review_verification(data: SEBReviewVerificationCreate):
    # Validate review_assignment exists
    assignment = await seb_review_assignment_collection.find_one({"_id": data.review_assignment_id})
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review assignment '{data.review_assignment_id}' not found",
        )
    
    new_verification = {
        "_id": str(uuid.uuid4()),
        "review_assignment_id": data.review_assignment_id,
        "discipline": data.discipline,
        "verification_status": data.verification_status,
        "verification_comment": data.verification_comment,
        "verified_by": data.verified_by,
        "verified_at": datetime.utcnow(),
    }
    await seb_review_verification_collection.insert_one(new_verification)
    return serialize_seb_review_verification(new_verification)

@router.get(
    "/seb/review-verifications",
    response_model=List[SEBReviewVerificationResponse],
    summary="Get All Review Verifications",
    description="Returns all review verifications, optionally filtered by review_assignment_id.",
)
async def get_all_review_verifications(review_assignment_id: Optional[str] = None):
    query = {"review_assignment_id": review_assignment_id} if review_assignment_id else {}
    cursor = seb_review_verification_collection.find(query).sort("verified_at", -1)
    verifications = await cursor.to_list(length=1000)
    return [serialize_seb_review_verification(v) for v in verifications]
