"""
SEB – Readiness & Conditions Module
Determines engineering discipline readiness for downstream design.
Records conditions, blockers, rule results, exceptions, and reviews.
"""

from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import os

router = APIRouter()

# MongoDB connection
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGODB_URL)
db = client["ginfina"]

# Collections
readiness_collection = db["seb_readiness"]
condition_collection = db["seb_readiness_condition"]
blocker_collection = db["seb_readiness_blocker"]
rule_result_collection = db["seb_readiness_rule_result"]
exception_collection = db["seb_readiness_exception"]
review_collection = db["seb_readiness_review"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. SEB_READINESS
# ═══════════════════════════════════════════════════════════════════════════

class SEBReadinessCreate(BaseModel):
    seb_revision_id: str
    discipline: str
    readiness_status: str = "NOT_ASSESSED"
    engineering_use: Optional[str] = None
    readiness_summary: Optional[str] = None
    assessed_by: Optional[str] = None

class SEBReadinessResponse(BaseModel):
    id: str
    seb_revision_id: str
    discipline: str
    readiness_status: str
    engineering_use: Optional[str]
    readiness_summary: Optional[str]
    assessed_at: str
    assessed_by: Optional[str]


@router.post("/seb/readiness", response_model=SEBReadinessResponse)
async def create_readiness(data: SEBReadinessCreate):
    """Create a new readiness record for a discipline in a SEB revision."""
    doc = {
        "seb_revision_id": data.seb_revision_id,
        "discipline": data.discipline,
        "readiness_status": data.readiness_status,
        "engineering_use": data.engineering_use,
        "readiness_summary": data.readiness_summary,
        "assessed_at": datetime.utcnow().isoformat(),
        "assessed_by": data.assessed_by,
    }
    result = await readiness_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBReadinessResponse(**doc)


@router.get("/seb/readiness", response_model=List[SEBReadinessResponse])
async def get_readiness(seb_revision_id: Optional[str] = None, discipline: Optional[str] = None):
    """Get readiness records, optionally filtered by revision or discipline."""
    query = {}
    if seb_revision_id:
        query["seb_revision_id"] = seb_revision_id
    if discipline:
        query["discipline"] = discipline
    
    cursor = readiness_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBReadinessResponse(**doc))
    return results


@router.get("/seb/readiness/{readiness_id}", response_model=SEBReadinessResponse)
async def get_readiness_by_id(readiness_id: str):
    """Get a single readiness record by ID."""
    from bson import ObjectId
    doc = await readiness_collection.find_one({"_id": ObjectId(readiness_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Readiness record not found")
    doc["id"] = str(doc.pop("_id"))
    return SEBReadinessResponse(**doc)


@router.put("/seb/readiness/{readiness_id}")
async def update_readiness(readiness_id: str, data: SEBReadinessCreate):
    """Update an existing readiness record."""
    from bson import ObjectId
    update_doc = {
        "seb_revision_id": data.seb_revision_id,
        "discipline": data.discipline,
        "readiness_status": data.readiness_status,
        "engineering_use": data.engineering_use,
        "readiness_summary": data.readiness_summary,
        "assessed_at": datetime.utcnow().isoformat(),
        "assessed_by": data.assessed_by,
    }
    result = await readiness_collection.update_one(
        {"_id": ObjectId(readiness_id)},
        {"$set": update_doc}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Readiness record not found")
    return {"message": "Readiness record updated successfully"}


@router.delete("/seb/readiness/{readiness_id}")
async def delete_readiness(readiness_id: str):
    """Delete a readiness record."""
    from bson import ObjectId
    result = await readiness_collection.delete_one({"_id": ObjectId(readiness_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Readiness record not found")
    return {"message": "Readiness record deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 2. SEB_READINESS_CONDITION
# ═══════════════════════════════════════════════════════════════════════════

class ReadinessConditionCreate(BaseModel):
    readiness_id: str
    condition_code: Optional[str] = None
    condition_description: str
    required_action: Optional[str] = None
    discipline: Optional[str] = None
    owner_user_id: Optional[str] = None
    target_date: Optional[str] = None
    condition_status: str = "OPEN"
    closure_evidence: Optional[str] = None

class ReadinessConditionResponse(BaseModel):
    id: str
    readiness_id: str
    condition_code: Optional[str]
    condition_description: str
    required_action: Optional[str]
    discipline: Optional[str]
    owner_user_id: Optional[str]
    target_date: Optional[str]
    condition_status: str
    closure_evidence: Optional[str]
    closed_at: Optional[str]


@router.post("/seb/readiness-conditions", response_model=ReadinessConditionResponse)
async def create_condition(data: ReadinessConditionCreate):
    """Create a readiness condition (for CONDITIONAL status)."""
    doc = {
        "readiness_id": data.readiness_id,
        "condition_code": data.condition_code,
        "condition_description": data.condition_description,
        "required_action": data.required_action,
        "discipline": data.discipline,
        "owner_user_id": data.owner_user_id,
        "target_date": data.target_date,
        "condition_status": data.condition_status,
        "closure_evidence": data.closure_evidence,
        "closed_at": None,
    }
    result = await condition_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return ReadinessConditionResponse(**doc)


@router.get("/seb/readiness-conditions", response_model=List[ReadinessConditionResponse])
async def get_conditions(readiness_id: Optional[str] = None):
    """Get readiness conditions, optionally filtered by readiness_id."""
    query = {}
    if readiness_id:
        query["readiness_id"] = readiness_id
    
    cursor = condition_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(ReadinessConditionResponse(**doc))
    return results


@router.delete("/seb/readiness-conditions/{condition_id}")
async def delete_condition(condition_id: str):
    """Delete a readiness condition."""
    from bson import ObjectId
    result = await condition_collection.delete_one({"_id": ObjectId(condition_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Condition not found")
    return {"message": "Condition deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 3. SEB_READINESS_BLOCKER
# ═══════════════════════════════════════════════════════════════════════════

class ReadinessBlockerCreate(BaseModel):
    readiness_id: str
    blocker_code: Optional[str] = None
    blocker_type: str
    blocker_description: str
    severity: str = "MEDIUM"
    source_record_type: Optional[str] = None
    source_record_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    blocker_status: str = "OPEN"
    target_date: Optional[str] = None

class ReadinessBlockerResponse(BaseModel):
    id: str
    readiness_id: str
    blocker_code: Optional[str]
    blocker_type: str
    blocker_description: str
    severity: str
    source_record_type: Optional[str]
    source_record_id: Optional[str]
    owner_user_id: Optional[str]
    blocker_status: str
    target_date: Optional[str]
    resolved_at: Optional[str]


@router.post("/seb/readiness-blockers", response_model=ReadinessBlockerResponse)
async def create_blocker(data: ReadinessBlockerCreate):
    """Create a readiness blocker (mandatory issue preventing design readiness)."""
    doc = {
        "readiness_id": data.readiness_id,
        "blocker_code": data.blocker_code,
        "blocker_type": data.blocker_type,
        "blocker_description": data.blocker_description,
        "severity": data.severity,
        "source_record_type": data.source_record_type,
        "source_record_id": data.source_record_id,
        "owner_user_id": data.owner_user_id,
        "blocker_status": data.blocker_status,
        "target_date": data.target_date,
        "resolved_at": None,
    }
    result = await blocker_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return ReadinessBlockerResponse(**doc)


@router.get("/seb/readiness-blockers", response_model=List[ReadinessBlockerResponse])
async def get_blockers(readiness_id: Optional[str] = None):
    """Get readiness blockers, optionally filtered by readiness_id."""
    query = {}
    if readiness_id:
        query["readiness_id"] = readiness_id
    
    cursor = blocker_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(ReadinessBlockerResponse(**doc))
    return results


@router.delete("/seb/readiness-blockers/{blocker_id}")
async def delete_blocker(blocker_id: str):
    """Delete a readiness blocker."""
    from bson import ObjectId
    result = await blocker_collection.delete_one({"_id": ObjectId(blocker_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blocker not found")
    return {"message": "Blocker deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 4. SEB_READINESS_RULE_RESULT
# ═══════════════════════════════════════════════════════════════════════════

class ReadinessRuleResultCreate(BaseModel):
    readiness_id: str
    rule_code: str
    rule_name: Optional[str] = None
    rule_type: Optional[str] = None
    is_mandatory: bool = False
    rule_result: str
    result_reason: Optional[str] = None

class ReadinessRuleResultResponse(BaseModel):
    id: str
    readiness_id: str
    rule_code: str
    rule_name: Optional[str]
    rule_type: Optional[str]
    is_mandatory: bool
    rule_result: str
    result_reason: Optional[str]
    evaluated_at: str


@router.post("/seb/readiness-rule-results", response_model=ReadinessRuleResultResponse)
async def create_rule_result(data: ReadinessRuleResultCreate):
    """Create a readiness rule result."""
    doc = {
        "readiness_id": data.readiness_id,
        "rule_code": data.rule_code,
        "rule_name": data.rule_name,
        "rule_type": data.rule_type,
        "is_mandatory": data.is_mandatory,
        "rule_result": data.rule_result,
        "result_reason": data.result_reason,
        "evaluated_at": datetime.utcnow().isoformat(),
    }
    result = await rule_result_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return ReadinessRuleResultResponse(**doc)


@router.get("/seb/readiness-rule-results", response_model=List[ReadinessRuleResultResponse])
async def get_rule_results(readiness_id: Optional[str] = None):
    """Get readiness rule results, optionally filtered by readiness_id."""
    query = {}
    if readiness_id:
        query["readiness_id"] = readiness_id
    
    cursor = rule_result_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(ReadinessRuleResultResponse(**doc))
    return results


@router.delete("/seb/readiness-rule-results/{rule_result_id}")
async def delete_rule_result(rule_result_id: str):
    """Delete a readiness rule result."""
    from bson import ObjectId
    result = await rule_result_collection.delete_one({"_id": ObjectId(rule_result_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule result not found")
    return {"message": "Rule result deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 5. SEB_READINESS_EXCEPTION
# ═══════════════════════════════════════════════════════════════════════════

class ReadinessExceptionCreate(BaseModel):
    readiness_id: str
    blocker_id: Optional[str] = None
    exception_type: str
    exception_reason: str
    condition_imposed: Optional[str] = None
    authorised_by: str
    valid_until: Optional[str] = None
    exception_status: str = "PROPOSED"

class ReadinessExceptionResponse(BaseModel):
    id: str
    readiness_id: str
    blocker_id: Optional[str]
    exception_type: str
    exception_reason: str
    condition_imposed: Optional[str]
    authorised_by: str
    authorised_at: str
    valid_until: Optional[str]
    exception_status: str


@router.post("/seb/readiness-exceptions", response_model=ReadinessExceptionResponse)
async def create_exception(data: ReadinessExceptionCreate):
    """Create a readiness exception (authorised waiver)."""
    doc = {
        "readiness_id": data.readiness_id,
        "blocker_id": data.blocker_id,
        "exception_type": data.exception_type,
        "exception_reason": data.exception_reason,
        "condition_imposed": data.condition_imposed,
        "authorised_by": data.authorised_by,
        "authorised_at": datetime.utcnow().isoformat(),
        "valid_until": data.valid_until,
        "exception_status": data.exception_status,
    }
    result = await exception_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return ReadinessExceptionResponse(**doc)


@router.get("/seb/readiness-exceptions", response_model=List[ReadinessExceptionResponse])
async def get_exceptions(readiness_id: Optional[str] = None):
    """Get readiness exceptions, optionally filtered by readiness_id."""
    query = {}
    if readiness_id:
        query["readiness_id"] = readiness_id
    
    cursor = exception_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(ReadinessExceptionResponse(**doc))
    return results


@router.delete("/seb/readiness-exceptions/{exception_id}")
async def delete_exception(exception_id: str):
    """Delete a readiness exception."""
    from bson import ObjectId
    result = await exception_collection.delete_one({"_id": ObjectId(exception_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Exception not found")
    return {"message": "Exception deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 6. SEB_READINESS_REVIEW
# ═══════════════════════════════════════════════════════════════════════════

class ReadinessReviewCreate(BaseModel):
    readiness_id: str
    reviewer_user_id: str
    review_decision: str
    review_comment: Optional[str] = None

class ReadinessReviewResponse(BaseModel):
    id: str
    readiness_id: str
    reviewer_user_id: str
    review_decision: str
    review_comment: Optional[str]
    reviewed_at: str


@router.post("/seb/readiness-reviews", response_model=ReadinessReviewResponse)
async def create_review(data: ReadinessReviewCreate):
    """Create a readiness review (human review of calculated readiness)."""
    doc = {
        "readiness_id": data.readiness_id,
        "reviewer_user_id": data.reviewer_user_id,
        "review_decision": data.review_decision,
        "review_comment": data.review_comment,
        "reviewed_at": datetime.utcnow().isoformat(),
    }
    result = await review_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return ReadinessReviewResponse(**doc)


@router.get("/seb/readiness-reviews", response_model=List[ReadinessReviewResponse])
async def get_reviews(readiness_id: Optional[str] = None):
    """Get readiness reviews, optionally filtered by readiness_id."""
    query = {}
    if readiness_id:
        query["readiness_id"] = readiness_id
    
    cursor = review_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(ReadinessReviewResponse(**doc))
    return results


@router.delete("/seb/readiness-reviews/{review_id}")
async def delete_review(review_id: str):
    """Delete a readiness review."""
    from bson import ObjectId
    result = await review_collection.delete_one({"_id": ObjectId(review_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"message": "Review deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

async def init_readiness_collections():
    """Initialize collections and indexes."""
    # Readiness indexes
    await readiness_collection.create_index("seb_revision_id")
    await readiness_collection.create_index("discipline")
    
    # Condition indexes
    await condition_collection.create_index("readiness_id")
    
    # Blocker indexes
    await blocker_collection.create_index("readiness_id")
    
    # Rule result indexes
    await rule_result_collection.create_index("readiness_id")
    
    # Exception indexes
    await exception_collection.create_index("readiness_id")
    
    # Review indexes
    await review_collection.create_index("readiness_id")
    
    print("✓ SEB Readiness & Conditions collections initialized")
