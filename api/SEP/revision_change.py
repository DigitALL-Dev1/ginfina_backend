"""
SEB – Revision & Change Control Module
Manages changes after SEB release. Released SEBs are immutable - new material creates new revisions.
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
revision_change_collection = db["seb_revision_change"]
change_item_collection = db["seb_change_item"]
change_source_collection = db["seb_change_source"]
comparison_collection = db["seb_revision_comparison"]
supersession_collection = db["seb_revision_supersession"]
change_review_collection = db["seb_change_review"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. SEB_REVISION_CHANGE
# ═══════════════════════════════════════════════════════════════════════════

class SEBRevisionChangeCreate(BaseModel):
    seb_id: str
    current_revision_id: str
    proposed_revision_id: Optional[str] = None
    change_code: str
    change_type: Optional[str] = None
    change_reason: str
    change_description: Optional[str] = None
    materiality: str = "NON_MATERIAL"
    change_status: str = "DRAFT"
    raised_by: str

class SEBRevisionChangeResponse(BaseModel):
    id: str
    seb_id: str
    current_revision_id: str
    proposed_revision_id: Optional[str]
    change_code: str
    change_type: Optional[str]
    change_reason: str
    change_description: Optional[str]
    materiality: str
    change_status: str
    raised_by: str
    raised_at: str


@router.post("/seb/revision-changes", response_model=SEBRevisionChangeResponse)
async def create_revision_change(data: SEBRevisionChangeCreate):
    """Create a new revision change request."""
    doc = {
        "seb_id": data.seb_id,
        "current_revision_id": data.current_revision_id,
        "proposed_revision_id": data.proposed_revision_id,
        "change_code": data.change_code,
        "change_type": data.change_type,
        "change_reason": data.change_reason,
        "change_description": data.change_description,
        "materiality": data.materiality,
        "change_status": data.change_status,
        "raised_by": data.raised_by,
        "raised_at": datetime.utcnow().isoformat(),
    }
    result = await revision_change_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBRevisionChangeResponse(**doc)


@router.get("/seb/revision-changes", response_model=List[SEBRevisionChangeResponse])
async def get_revision_changes(
    seb_id: Optional[str] = None,
    current_revision_id: Optional[str] = None,
    change_status: Optional[str] = None
):
    """Get revision changes, optionally filtered."""
    query = {}
    if seb_id:
        query["seb_id"] = seb_id
    if current_revision_id:
        query["current_revision_id"] = current_revision_id
    if change_status:
        query["change_status"] = change_status
    
    cursor = revision_change_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBRevisionChangeResponse(**doc))
    return results


@router.get("/seb/revision-changes/{change_id}", response_model=SEBRevisionChangeResponse)
async def get_revision_change_by_id(change_id: str):
    """Get a single revision change by ID."""
    from bson import ObjectId
    doc = await revision_change_collection.find_one({"_id": ObjectId(change_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Revision change not found")
    doc["id"] = str(doc.pop("_id"))
    return SEBRevisionChangeResponse(**doc)


@router.put("/seb/revision-changes/{change_id}")
async def update_revision_change(change_id: str, data: SEBRevisionChangeCreate):
    """Update an existing revision change."""
    from bson import ObjectId
    update_doc = {
        "seb_id": data.seb_id,
        "current_revision_id": data.current_revision_id,
        "proposed_revision_id": data.proposed_revision_id,
        "change_code": data.change_code,
        "change_type": data.change_type,
        "change_reason": data.change_reason,
        "change_description": data.change_description,
        "materiality": data.materiality,
        "change_status": data.change_status,
        "raised_by": data.raised_by,
    }
    result = await revision_change_collection.update_one(
        {"_id": ObjectId(change_id)},
        {"$set": update_doc}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Revision change not found")
    return {"message": "Revision change updated successfully"}


@router.delete("/seb/revision-changes/{change_id}")
async def delete_revision_change(change_id: str):
    """Delete a revision change."""
    from bson import ObjectId
    result = await revision_change_collection.delete_one({"_id": ObjectId(change_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Revision change not found")
    return {"message": "Revision change deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 2. SEB_CHANGE_ITEM
# ═══════════════════════════════════════════════════════════════════════════

class SEBChangeItemCreate(BaseModel):
    revision_change_id: str
    old_seb_item_id: Optional[str] = None
    new_seb_item_id: Optional[str] = None
    change_action: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    discipline: Optional[str] = None
    change_reason: Optional[str] = None

class SEBChangeItemResponse(BaseModel):
    id: str
    revision_change_id: str
    old_seb_item_id: Optional[str]
    new_seb_item_id: Optional[str]
    change_action: str
    old_value: Optional[str]
    new_value: Optional[str]
    discipline: Optional[str]
    change_reason: Optional[str]


@router.post("/seb/change-items", response_model=SEBChangeItemResponse)
async def create_change_item(data: SEBChangeItemCreate):
    """Create a change item record."""
    doc = {
        "revision_change_id": data.revision_change_id,
        "old_seb_item_id": data.old_seb_item_id,
        "new_seb_item_id": data.new_seb_item_id,
        "change_action": data.change_action,
        "old_value": data.old_value,
        "new_value": data.new_value,
        "discipline": data.discipline,
        "change_reason": data.change_reason,
    }
    result = await change_item_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBChangeItemResponse(**doc)


@router.get("/seb/change-items", response_model=List[SEBChangeItemResponse])
async def get_change_items(revision_change_id: Optional[str] = None):
    """Get change items, optionally filtered by revision_change_id."""
    query = {}
    if revision_change_id:
        query["revision_change_id"] = revision_change_id
    
    cursor = change_item_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBChangeItemResponse(**doc))
    return results


@router.delete("/seb/change-items/{item_id}")
async def delete_change_item(item_id: str):
    """Delete a change item."""
    from bson import ObjectId
    result = await change_item_collection.delete_one({"_id": ObjectId(item_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Change item not found")
    return {"message": "Change item deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 3. SEB_CHANGE_SOURCE
# ═══════════════════════════════════════════════════════════════════════════

class SEBChangeSourceCreate(BaseModel):
    revision_change_id: str
    source_type: str
    source_record_id: Optional[str] = None
    source_reference: Optional[str] = None
    source_description: Optional[str] = None
    received_at: Optional[str] = None

class SEBChangeSourceResponse(BaseModel):
    id: str
    revision_change_id: str
    source_type: str
    source_record_id: Optional[str]
    source_reference: Optional[str]
    source_description: Optional[str]
    received_at: Optional[str]


@router.post("/seb/change-sources", response_model=SEBChangeSourceResponse)
async def create_change_source(data: SEBChangeSourceCreate):
    """Create a change source record."""
    doc = {
        "revision_change_id": data.revision_change_id,
        "source_type": data.source_type,
        "source_record_id": data.source_record_id,
        "source_reference": data.source_reference,
        "source_description": data.source_description,
        "received_at": data.received_at or datetime.utcnow().isoformat(),
    }
    result = await change_source_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBChangeSourceResponse(**doc)


@router.get("/seb/change-sources", response_model=List[SEBChangeSourceResponse])
async def get_change_sources(revision_change_id: Optional[str] = None):
    """Get change sources, optionally filtered by revision_change_id."""
    query = {}
    if revision_change_id:
        query["revision_change_id"] = revision_change_id
    
    cursor = change_source_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBChangeSourceResponse(**doc))
    return results


@router.delete("/seb/change-sources/{source_id}")
async def delete_change_source(source_id: str):
    """Delete a change source."""
    from bson import ObjectId
    result = await change_source_collection.delete_one({"_id": ObjectId(source_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Change source not found")
    return {"message": "Change source deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 4. SEB_REVISION_COMPARISON
# ═══════════════════════════════════════════════════════════════════════════

class SEBRevisionComparisonCreate(BaseModel):
    revision_change_id: str
    old_revision_id: str
    new_revision_id: str
    section_name: Optional[str] = None
    changed_item_count: int = 0
    added_item_count: int = 0
    modified_item_count: int = 0
    superseded_item_count: int = 0
    comparison_summary: Optional[str] = None

class SEBRevisionComparisonResponse(BaseModel):
    id: str
    revision_change_id: str
    old_revision_id: str
    new_revision_id: str
    section_name: Optional[str]
    changed_item_count: int
    added_item_count: int
    modified_item_count: int
    superseded_item_count: int
    comparison_summary: Optional[str]


@router.post("/seb/revision-comparisons", response_model=SEBRevisionComparisonResponse)
async def create_revision_comparison(data: SEBRevisionComparisonCreate):
    """Create a revision comparison record."""
    doc = {
        "revision_change_id": data.revision_change_id,
        "old_revision_id": data.old_revision_id,
        "new_revision_id": data.new_revision_id,
        "section_name": data.section_name,
        "changed_item_count": data.changed_item_count,
        "added_item_count": data.added_item_count,
        "modified_item_count": data.modified_item_count,
        "superseded_item_count": data.superseded_item_count,
        "comparison_summary": data.comparison_summary,
    }
    result = await comparison_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBRevisionComparisonResponse(**doc)


@router.get("/seb/revision-comparisons", response_model=List[SEBRevisionComparisonResponse])
async def get_revision_comparisons(revision_change_id: Optional[str] = None):
    """Get revision comparisons, optionally filtered by revision_change_id."""
    query = {}
    if revision_change_id:
        query["revision_change_id"] = revision_change_id
    
    cursor = comparison_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBRevisionComparisonResponse(**doc))
    return results


@router.delete("/seb/revision-comparisons/{comparison_id}")
async def delete_revision_comparison(comparison_id: str):
    """Delete a revision comparison."""
    from bson import ObjectId
    result = await comparison_collection.delete_one({"_id": ObjectId(comparison_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Revision comparison not found")
    return {"message": "Revision comparison deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 5. SEB_REVISION_SUPERSESSION
# ═══════════════════════════════════════════════════════════════════════════

class SEBRevisionSupersessionCreate(BaseModel):
    old_revision_id: str
    new_revision_id: str
    supersession_reason: Optional[str] = None
    superseded_by: str
    status: str = "ACTIVE"

class SEBRevisionSupersessionResponse(BaseModel):
    id: str
    old_revision_id: str
    new_revision_id: str
    supersession_reason: Optional[str]
    superseded_by: str
    superseded_at: str
    status: str


@router.post("/seb/revision-supersessions", response_model=SEBRevisionSupersessionResponse)
async def create_revision_supersession(data: SEBRevisionSupersessionCreate):
    """Create a revision supersession record."""
    doc = {
        "old_revision_id": data.old_revision_id,
        "new_revision_id": data.new_revision_id,
        "supersession_reason": data.supersession_reason,
        "superseded_by": data.superseded_by,
        "superseded_at": datetime.utcnow().isoformat(),
        "status": data.status,
    }
    result = await supersession_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBRevisionSupersessionResponse(**doc)


@router.get("/seb/revision-supersessions", response_model=List[SEBRevisionSupersessionResponse])
async def get_revision_supersessions(
    old_revision_id: Optional[str] = None,
    new_revision_id: Optional[str] = None
):
    """Get revision supersessions, optionally filtered."""
    query = {}
    if old_revision_id:
        query["old_revision_id"] = old_revision_id
    if new_revision_id:
        query["new_revision_id"] = new_revision_id
    
    cursor = supersession_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBRevisionSupersessionResponse(**doc))
    return results


@router.delete("/seb/revision-supersessions/{supersession_id}")
async def delete_revision_supersession(supersession_id: str):
    """Delete a revision supersession."""
    from bson import ObjectId
    result = await supersession_collection.delete_one({"_id": ObjectId(supersession_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Revision supersession not found")
    return {"message": "Revision supersession deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# 6. SEB_CHANGE_REVIEW
# ═══════════════════════════════════════════════════════════════════════════

class SEBChangeReviewCreate(BaseModel):
    revision_change_id: str
    reviewer_user_id: str
    discipline: str
    review_status: str = "PENDING"
    review_decision: Optional[str] = None
    review_comment: Optional[str] = None

class SEBChangeReviewResponse(BaseModel):
    id: str
    revision_change_id: str
    reviewer_user_id: str
    discipline: str
    review_status: str
    review_decision: Optional[str]
    review_comment: Optional[str]
    reviewed_at: Optional[str]


@router.post("/seb/change-reviews", response_model=SEBChangeReviewResponse)
async def create_change_review(data: SEBChangeReviewCreate):
    """Create a change review record."""
    doc = {
        "revision_change_id": data.revision_change_id,
        "reviewer_user_id": data.reviewer_user_id,
        "discipline": data.discipline,
        "review_status": data.review_status,
        "review_decision": data.review_decision,
        "review_comment": data.review_comment,
        "reviewed_at": datetime.utcnow().isoformat() if data.review_decision else None,
    }
    result = await change_review_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return SEBChangeReviewResponse(**doc)


@router.get("/seb/change-reviews", response_model=List[SEBChangeReviewResponse])
async def get_change_reviews(revision_change_id: Optional[str] = None):
    """Get change reviews, optionally filtered by revision_change_id."""
    query = {}
    if revision_change_id:
        query["revision_change_id"] = revision_change_id
    
    cursor = change_review_collection.find(query)
    results = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        results.append(SEBChangeReviewResponse(**doc))
    return results


@router.delete("/seb/change-reviews/{review_id}")
async def delete_change_review(review_id: str):
    """Delete a change review."""
    from bson import ObjectId
    result = await change_review_collection.delete_one({"_id": ObjectId(review_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Change review not found")
    return {"message": "Change review deleted successfully"}


# ═══════════════════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

async def init_revision_change_collections():
    """Initialize collections and indexes."""
    # Revision change indexes
    await revision_change_collection.create_index("seb_id")
    await revision_change_collection.create_index("current_revision_id")
    await revision_change_collection.create_index("change_code")
    
    # Change item indexes
    await change_item_collection.create_index("revision_change_id")
    
    # Change source indexes
    await change_source_collection.create_index("revision_change_id")
    
    # Comparison indexes
    await comparison_collection.create_index("revision_change_id")
    await comparison_collection.create_index([("old_revision_id", 1), ("new_revision_id", 1)])
    
    # Supersession indexes
    await supersession_collection.create_index("old_revision_id")
    await supersession_collection.create_index("new_revision_id")
    
    # Change review indexes
    await change_review_collection.create_index("revision_change_id")
    
    print("✓ SEB Revision & Change Control collections initialized")
