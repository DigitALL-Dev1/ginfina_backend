from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
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

# SEB Collections
seb_baseline_collection = db["seb_baseline"]
seb_revision_collection = db["seb_revision"]
seb_item_collection = db["seb_item"]
seb_item_source_collection = db["seb_item_source"]
seb_evidence_manifest_collection = db["seb_evidence_manifest"]
seb_discipline_summary_collection = db["seb_discipline_summary"]
seb_crag_item_collection = db["seb_crag_item"]
seb_preparation_status_collection = db["seb_preparation_status"]

router = APIRouter()

# ═════════════════════════════════════════════════════════
# SEB BASELINE — Models
# ═════════════════════════════════════════════════════════

class SEBBaselineCreate(BaseModel):
    sia_case_id: str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id: Optional[str] = Field(None, description="FK → site._id")
    project_id: Optional[str] = Field(None, description="FK → project._id")
    seb_code: str = Field(..., max_length=50, description="varchar(50) NOT NULL")
    assessment_stage: Optional[str] = Field(None, max_length=50, description="varchar(50)")
    current_revision_no: Optional[str] = Field(None, max_length=20, description="varchar(20)")
    status: Optional[str] = Field("DRAFT", max_length=50, description="DRAFT | IN_PREPARATION | READY_FOR_REVIEW | RELEASED | SUPERSEDED")
    created_by: str = Field(..., description="FK → users._id (NOT NULL)")

class SEBBaselineResponse(BaseModel):
    id: str
    sia_case_id: str
    site_id: Optional[str]
    project_id: Optional[str]
    seb_code: str
    assessment_stage: Optional[str]
    current_revision_no: Optional[str]
    status: str
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime]


class VerifiedSiteResponse(BaseModel):
    id: str
    sia_case_id: str
    site_code: str
    site_name: Optional[str]
    site_type: Optional[str]
    address: Optional[str]
    status: str


class VerifiedSIACaseResponse(BaseModel):
    id: str
    project_id: str
    case_code: str
    assessment_purpose: Optional[str]
    assessment_stage: Optional[str]
    status: str
    sites: List[VerifiedSiteResponse]

# ═════════════════════════════════════════════════════════
# SEB REVISION — Models
# ═════════════════════════════════════════════════════════

class SEBRevisionCreate(BaseModel):
    seb_id: str = Field(..., description="FK → seb_baseline._id (NOT NULL)")
    revision_no: str = Field(..., max_length=20, description="varchar(20) NOT NULL, e.g., R01, R02, R03A")
    previous_revision_id: Optional[str] = Field(None, description="FK → seb_revision._id")
    revision_reason: Optional[str] = Field(None, description="text")
    revision_status: Optional[str] = Field("DRAFT", max_length=50, description="varchar(50)")
    issue_date: Optional[str] = Field(None, description="date in YYYY-MM-DD format")
    prepared_by: Optional[str] = Field(None, description="FK → users._id")

class SEBRevisionResponse(BaseModel):
    id: str
    seb_id: str
    revision_no: str
    previous_revision_id: Optional[str]
    revision_reason: Optional[str]
    revision_status: str
    issue_date: Optional[str]
    prepared_by: Optional[str]
    prepared_at: Optional[datetime]

# ═════════════════════════════════════════════════════════
# SEB ITEM — Models
# ═════════════════════════════════════════════════════════

class LegacyDetailedSEBItemCreate(BaseModel):
    seb_revision_id: str = Field(..., description="FK → seb_revision._id (NOT NULL)")
    item_code: str = Field(..., max_length=50, description="varchar(50) NOT NULL")
    item_type: Optional[str] = Field(None, max_length=100, description="varchar(100)")
    discipline: Optional[str] = Field(None, max_length=100, description="varchar(100), e.g., ELECTRICAL, CIVIL, STRUCTURAL")
    item_name: Optional[str] = Field(None, max_length=200, description="varchar(200)")
    item_value: Optional[str] = Field(None, description="text")
    unit: Optional[str] = Field(None, max_length=50, description="varchar(50)")
    reliability_status: Optional[str] = Field(None, max_length=50, description="VERIFIED | PROVISIONAL | ASSUMED | UNVERIFIED | SUPERSEDED")
    source_record_type: Optional[str] = Field(None, max_length=100, description="varchar(100)")
    source_record_id: Optional[str] = Field(None, description="FK to source record")
    inclusion_status: Optional[str] = Field("INCLUDED", max_length=50, description="varchar(50)")
    remarks: Optional[str] = Field(None, description="text")

class LegacyDetailedSEBItemResponse(BaseModel):
    id: str
    seb_revision_id: str
    item_code: str
    item_type: Optional[str]
    discipline: Optional[str]
    item_name: Optional[str]
    item_value: Optional[str]
    unit: Optional[str]
    reliability_status: Optional[str]
    source_record_type: Optional[str]
    source_record_id: Optional[str]
    inclusion_status: str
    remarks: Optional[str]

# ═════════════════════════════════════════════════════════
# SEB ITEM SOURCE — Models
# ═════════════════════════════════════════════════════════

class SEBItemCreate(BaseModel):
    """Fields accepted from a user when creating an SEB item."""
    fact_id: str = Field(..., description="ID of the selected engineering fact")
    seb_id: str = Field(..., description="FK to seb_baseline._id")
    seb_revision_id: str = Field(..., description="FK to seb_revision._id")
    status: str = Field(..., max_length=50, description="Item status")


class SEBItemResponse(BaseModel):
    id: str
    fact_id: str
    fact_name: Optional[str] = None
    discipline: Optional[str] = None
    seb_id: str
    seb_revision_id: str
    status: str
    decision: Optional[str] = None
    fact_collection: Optional[str] = None
    fact_data: Optional[Dict[str, Any]] = None
    discipline_readiness: Optional[Dict[str, Any]] = None
    approval: Optional[Dict[str, Any]] = None


class SEBRevisionSubmitForReview(BaseModel):
    seb_id: str = Field(..., description="FK to seb_baseline._id")


class SEBItemReviewUpdate(BaseModel):
    seb_id: str
    seb_revision_id: str
    fact_id: str
    decision: str = Field(..., description="ACCEPT | CHANGE_REQUIRED | ACCEPT_WITH_CONDITION | REJECT")
    discipline: Optional[str] = None
    reviewer: Optional[str] = None
    comment: Optional[str] = None


class SEBItemReadinessUpdate(BaseModel):
    discipline_readiness: str
    condition: Optional[str] = None
    required_action: Optional[str] = None
    owner: Optional[str] = None
    target_date: Optional[str] = None
    blocker: Optional[str] = None
    blocker_reason: Optional[str] = None
    related_fact_or_gap: Optional[str] = None


class SEBItemSourceCreate(BaseModel):
    seb_item_id: str = Field(..., description="FK → seb_item._id (NOT NULL)")
    source_type: Optional[str] = Field(None, max_length=100, description="FIELD_MEASUREMENT | ENGINEERING_ASSESSMENT | SOURCE_FACT | DRONE | GIS | DOCUMENT | SPECIALIST_REPORT")
    source_reference: Optional[str] = Field(None, max_length=255, description="varchar(255)")
    source_record_id: Optional[str] = Field(None, description="FK to original source record")
    source_date: Optional[datetime] = Field(None, description="datetime")
    source_description: Optional[str] = Field(None, description="text")

class SEBItemSourceResponse(BaseModel):
    id: str
    seb_item_id: str
    source_type: Optional[str]
    source_reference: Optional[str]
    source_record_id: Optional[str]
    source_date: Optional[datetime]
    source_description: Optional[str]

# ═════════════════════════════════════════════════════════
# SEB EVIDENCE MANIFEST — Models
# ═════════════════════════════════════════════════════════

class SEBEvidenceManifestCreate(BaseModel):
    seb_revision_id: str = Field(..., description="FK → seb_revision._id (NOT NULL)")
    seb_item_id: Optional[str] = Field(None, description="FK → seb_item._id")
    sia_evidence_id: Optional[str] = Field(None, description="FK → sia_evidence._id (optional)")
    evidence_type: Optional[str] = Field(None, max_length=100, description="PHOTO | VIDEO | MEASUREMENT | DOCUMENT | DRONE | GIS | INSTRUMENT")
    evidence_hash: Optional[str] = Field(None, max_length=255, description="varchar(255)")
    is_primary: Optional[bool] = Field(True, description="boolean")

class SEBEvidenceManifestResponse(BaseModel):
    id: str
    seb_revision_id: str
    seb_item_id: Optional[str]
    sia_evidence_id: Optional[str]
    evidence_type: Optional[str]
    evidence_hash: Optional[str]
    is_primary: bool
    included_at: datetime

# ═════════════════════════════════════════════════════════
# SEB DISCIPLINE SUMMARY — Models
# ═════════════════════════════════════════════════════════

class SEBDisciplineSummaryCreate(BaseModel):
    seb_revision_id: str = Field(..., description="FK → seb_revision._id (NOT NULL)")
    discipline: str = Field(..., max_length=100, description="ELECTRICAL | CIVIL | STRUCTURAL | MECHANICAL | WATER_PUMPING | SCADA | HSE | CLIMATE_ENVIRONMENT | LOGISTICS")
    summary: Optional[str] = Field(None, description="text")
    key_findings: Optional[str] = Field(None, description="text")
    readiness_status: Optional[str] = Field(None, max_length=50, description="varchar(50)")
    item_count: Optional[int] = Field(0, description="int")
    verified_item_count: Optional[int] = Field(0, description="int")
    open_gap_count: Optional[int] = Field(0, description="int")

class SEBDisciplineSummaryResponse(BaseModel):
    id: str
    seb_revision_id: str
    discipline: str
    summary: Optional[str]
    key_findings: Optional[str]
    readiness_status: Optional[str]
    item_count: int
    verified_item_count: int
    open_gap_count: int

# ═════════════════════════════════════════════════════════
# SEB CRAG ITEM — Models
# ═════════════════════════════════════════════════════════

class SEBCRAGItemCreate(BaseModel):
    seb_revision_id: str = Field(..., description="FK → seb_revision._id (NOT NULL)")
    record_type: str = Field(..., max_length=50, description="CONSTRAINT | RISK | ASSUMPTION | GAP | RFI")
    discipline: Optional[str] = Field(None, max_length=100, description="varchar(100)")
    source_record_id: Optional[str] = Field(None, description="FK to source record")
    description: Optional[str] = Field(None, description="text")
    impact: Optional[str] = Field(None, description="text")
    severity: Optional[str] = Field(None, max_length=50, description="varchar(50)")
    status: Optional[str] = Field("OPEN", max_length=50, description="varchar(50)")
    approved_exception: Optional[bool] = Field(False, description="boolean")

class SEBCRAGItemResponse(BaseModel):
    id: str
    seb_revision_id: str
    record_type: str
    discipline: Optional[str]
    source_record_id: Optional[str]
    description: Optional[str]
    impact: Optional[str]
    severity: Optional[str]
    status: str
    approved_exception: bool

# ═════════════════════════════════════════════════════════
# SEB PREPARATION STATUS — Models
# ═════════════════════════════════════════════════════════

class SEBPreparationStatusCreate(BaseModel):
    seb_revision_id: str = Field(..., description="FK → seb_revision._id (NOT NULL)")
    section_name: str = Field(..., max_length=100, description="CONTROL_HEADER | SITE_CONTEXT | GEOSPATIAL_CONTEXT | ASSESSMENT_METHOD | EVIDENCE_MANIFEST | ENGINEERING_FACTS | DISCIPLINE_RESULTS | CRAG | READINESS")
    completion_status: Optional[str] = Field("PENDING", max_length=50, description="varchar(50)")
    mandatory: Optional[bool] = Field(True, description="boolean")
    issue_count: Optional[int] = Field(0, description="int")
    checked_by: Optional[str] = Field(None, description="FK → users._id")

class SEBPreparationStatusResponse(BaseModel):
    id: str
    seb_revision_id: str
    section_name: str
    completion_status: str
    mandatory: bool
    issue_count: int
    checked_by: Optional[str]
    checked_at: Optional[datetime]

# ═════════════════════════════════════════════════════════
# Serializers
# ═════════════════════════════════════════════════════════

def serialize_seb_baseline(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "sia_case_id": doc["sia_case_id"],
        "site_id": doc.get("site_id"),
        "project_id": doc.get("project_id"),
        "seb_code": doc["seb_code"],
        "assessment_stage": doc.get("assessment_stage"),
        "current_revision_no": doc.get("current_revision_no"),
        "status": doc.get("status", "DRAFT"),
        "created_by": doc["created_by"],
        "created_at": doc["created_at"],
        "updated_at": doc.get("updated_at"),
    }

def serialize_seb_revision(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_id": doc["seb_id"],
        "revision_no": doc["revision_no"],
        "previous_revision_id": doc.get("previous_revision_id"),
        "revision_reason": doc.get("revision_reason"),
        "revision_status": doc.get("revision_status", "DRAFT"),
        "issue_date": doc.get("issue_date"),
        "prepared_by": doc.get("prepared_by"),
        "prepared_at": doc.get("prepared_at"),
    }

def serialize_seb_item(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "fact_id": doc.get("fact_id") or doc.get("source_record_id") or str(doc["_id"]),
        "fact_name": doc.get("fact_name") or doc.get("item_name"),
        "discipline": doc.get("review_discipline") or doc.get("discipline"),
        "seb_id": doc.get("seb_id"),
        "seb_revision_id": doc["seb_revision_id"],
        "status": doc.get("status") or doc.get("inclusion_status", "DRAFT"),
        "decision": doc.get("decision"),
        "fact_collection": doc.get("fact_collection"),
        "fact_data": None,
        "discipline_readiness": doc.get("discipline_readiness"),
        "approval": doc.get("approval"),
    }


async def serialize_review_seb_item(doc: dict) -> dict:
    """Return a review item together with the SIA fact it references."""
    item = serialize_seb_item(doc)
    collection_name = item["fact_collection"]
    if not collection_name:
        collection_name = await resolve_fact_collection(item["fact_id"])
        item["fact_collection"] = collection_name
    if not collection_name:
        return item

    fact = await db[collection_name].find_one({"_id": item["fact_id"]})
    if fact:
        item["fact_data"] = {
            **{key: value for key, value in fact.items() if key != "_id"},
            "id": str(fact["_id"]),
        }
        if not item["fact_name"]:
            for field in (
                "fact_name", "item_name", "parameter_name", "name", "title",
                "description", "gap_description", "finding", "observation",
                "equipment_name", "asset_name", "component_name",
            ):
                value = fact.get(field)
                if isinstance(value, str) and value.strip():
                    item["fact_name"] = value.strip()
                    break
        if not item["discipline"]:
            item["discipline"] = fact.get("discipline") or fact.get("target_discipline")
    if not item["fact_name"]:
        item["fact_name"] = f"Fact {item['fact_id']}"
    if not item["discipline"]:
        item["discipline"] = "UNASSIGNED"
    return item


async def resolve_fact_collection(fact_id: str) -> Optional[str]:
    """Find the SIA collection that owns a selected source fact."""
    collection_names = await db.list_collection_names()
    for collection_name in collection_names:
        if not collection_name.startswith("sia_"):
            continue
        if await db[collection_name].find_one({"_id": fact_id}, {"_id": 1}):
            return collection_name
    return None

def serialize_seb_item_source(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_item_id": doc["seb_item_id"],
        "source_type": doc.get("source_type"),
        "source_reference": doc.get("source_reference"),
        "source_record_id": doc.get("source_record_id"),
        "source_date": doc.get("source_date"),
        "source_description": doc.get("source_description"),
    }

def serialize_seb_evidence_manifest(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_revision_id": doc["seb_revision_id"],
        "seb_item_id": doc.get("seb_item_id"),
        "sia_evidence_id": doc.get("sia_evidence_id"),
        "evidence_type": doc.get("evidence_type"),
        "evidence_hash": doc.get("evidence_hash"),
        "is_primary": doc.get("is_primary", True),
        "included_at": doc["included_at"],
    }

def serialize_seb_discipline_summary(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_revision_id": doc["seb_revision_id"],
        "discipline": doc["discipline"],
        "summary": doc.get("summary"),
        "key_findings": doc.get("key_findings"),
        "readiness_status": doc.get("readiness_status"),
        "item_count": doc.get("item_count", 0),
        "verified_item_count": doc.get("verified_item_count", 0),
        "open_gap_count": doc.get("open_gap_count", 0),
    }

def serialize_seb_crag_item(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_revision_id": doc["seb_revision_id"],
        "record_type": doc["record_type"],
        "discipline": doc.get("discipline"),
        "source_record_id": doc.get("source_record_id"),
        "description": doc.get("description"),
        "impact": doc.get("impact"),
        "severity": doc.get("severity"),
        "status": doc.get("status", "OPEN"),
        "approved_exception": doc.get("approved_exception", False),
    }

def serialize_seb_preparation_status(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "seb_revision_id": doc["seb_revision_id"],
        "section_name": doc["section_name"],
        "completion_status": doc.get("completion_status", "PENDING"),
        "mandatory": doc.get("mandatory", True),
        "issue_count": doc.get("issue_count", 0),
        "checked_by": doc.get("checked_by"),
        "checked_at": doc.get("checked_at"),
    }

# ═════════════════════════════════════════════════════════
# Init — indexes
# ═════════════════════════════════════════════════════════

async def init_seb_collections():
    """Create indexes for all SEB collections."""
    
    # seb_baseline indexes
    await seb_baseline_collection.create_index("sia_case_id")
    await seb_baseline_collection.create_index("site_id")
    await seb_baseline_collection.create_index("project_id")
    await seb_baseline_collection.create_index("seb_code")
    await seb_baseline_collection.create_index("status")
    await seb_baseline_collection.create_index("created_by")
    print("seb_baseline collection initialized")
    
    # seb_revision indexes
    await seb_revision_collection.create_index("seb_id")
    await seb_revision_collection.create_index("revision_no")
    await seb_revision_collection.create_index("revision_status")
    await seb_revision_collection.create_index("prepared_by")
    print("seb_revision collection initialized")
    
    # seb_item indexes
    await seb_item_collection.create_index("seb_revision_id")
    await seb_item_collection.create_index("fact_id")
    await seb_item_collection.create_index("seb_id")
    await seb_item_collection.create_index("fact_collection")
    await seb_item_collection.create_index("item_code")
    await seb_item_collection.create_index("discipline")
    await seb_item_collection.create_index("reliability_status")
    print("seb_item collection initialized")
    
    # seb_item_source indexes
    await seb_item_source_collection.create_index("seb_item_id")
    await seb_item_source_collection.create_index("source_type")
    print("seb_item_source collection initialized")
    
    # seb_evidence_manifest indexes
    await seb_evidence_manifest_collection.create_index("seb_revision_id")
    await seb_evidence_manifest_collection.create_index("seb_item_id")
    await seb_evidence_manifest_collection.create_index("sia_evidence_id")
    print("seb_evidence_manifest collection initialized")
    
    # seb_discipline_summary indexes
    await seb_discipline_summary_collection.create_index("seb_revision_id")
    await seb_discipline_summary_collection.create_index("discipline")
    print("seb_discipline_summary collection initialized")
    
    # seb_crag_item indexes
    await seb_crag_item_collection.create_index("seb_revision_id")
    await seb_crag_item_collection.create_index("record_type")
    await seb_crag_item_collection.create_index("discipline")
    print("seb_crag_item collection initialized")
    
    # seb_preparation_status indexes
    await seb_preparation_status_collection.create_index("seb_revision_id")
    await seb_preparation_status_collection.create_index("section_name")
    print("seb_preparation_status collection initialized")

# ═════════════════════════════════════════════════════════
# SEB BASELINE — Endpoints
# ═════════════════════════════════════════════════════════

@router.get(
    "/seb/verified-sia-cases",
    response_model=List[VerifiedSIACaseResponse],
    summary="Get verified SIA cases and sites",
    description="Returns SIA cases with status=verified and their sites with status=verified.",
)
async def get_verified_sia_cases():
    """Return the verified SIA case/site context available for SEB preparation."""
    sia_case_collection = db["sia_case"]
    sia_site_collection = db["sia_site"]

    cases = await sia_case_collection.find({"status": "verified"}).sort("created_at", -1).to_list(1000)
    verified_cases = []
    for case in cases:
        sites = await sia_site_collection.find({
            "sia_case_id": str(case["_id"]),
            "status": "verified",
        }).sort("created_at", -1).to_list(1000)
        verified_cases.append({
            "id": str(case["_id"]),
            "project_id": case["project_id"],
            "case_code": case["case_code"],
            "assessment_purpose": case.get("assessment_purpose"),
            "assessment_stage": case.get("assessment_stage"),
            "status": case.get("status", "verified"),
            "sites": [{
                "id": str(site["_id"]),
                "sia_case_id": site["sia_case_id"],
                "site_code": site["site_code"],
                "site_name": site.get("site_name"),
                "site_type": site.get("site_type"),
                "address": site.get("address"),
                "status": site.get("status", "verified"),
            } for site in sites],
        })
    return verified_cases

@router.post(
    "/seb/baselines",
    response_model=SEBBaselineResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SEB Baseline",
    description="Creates a new Site Engineering Baseline record linked to a SIA case. Project ID is automatically fetched from the SIA case.",
)
async def create_seb_baseline(data: SEBBaselineCreate):
    # Fetch SIA case to get project_id
    sia_case_collection = db["sia_case"]
    sia_case = await sia_case_collection.find_one({"_id": data.sia_case_id})
    if not sia_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SIA case with id '{data.sia_case_id}' not found",
        )
    
    # Use project_id from SIA case, override any provided value
    project_id = sia_case.get("project_id")
    
    new_baseline = {
        "_id": str(uuid.uuid4()),
        "sia_case_id": data.sia_case_id,
        "site_id": data.site_id,
        "project_id": project_id,  # Automatically set from SIA case
        "seb_code": data.seb_code,
        "assessment_stage": data.assessment_stage,
        "current_revision_no": data.current_revision_no,
        "status": data.status,
        "created_by": data.created_by,
        "created_at": datetime.utcnow(),
        "updated_at": None,
    }
    await seb_baseline_collection.insert_one(new_baseline)
    return serialize_seb_baseline(new_baseline)

@router.get(
    "/seb/baselines",
    response_model=List[SEBBaselineResponse],
    summary="Get All SEB Baselines",
    description="Returns all SEB baselines, optionally filtered by sia_case_id.",
)
async def get_all_seb_baselines(sia_case_id: Optional[str] = None):
    query = {"sia_case_id": sia_case_id} if sia_case_id else {}
    cursor = seb_baseline_collection.find(query).sort("created_at", -1)
    baselines = await cursor.to_list(length=1000)
    return [serialize_seb_baseline(b) for b in baselines]

@router.get(
    "/seb/baselines/{baseline_id}",
    response_model=SEBBaselineResponse,
    summary="Get SEB Baseline by ID",
    description="Fetch a single SEB baseline by its ID.",
)
async def get_seb_baseline(baseline_id: str):
    baseline = await seb_baseline_collection.find_one({"_id": baseline_id})
    if not baseline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB baseline with id '{baseline_id}' not found",
        )
    return serialize_seb_baseline(baseline)

# ═════════════════════════════════════════════════════════
# SEB REVISION — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/revisions",
    response_model=SEBRevisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SEB Revision",
    description="Creates a new controlled revision for a SEB baseline (e.g., R01, R02, R03A).",
)
async def create_seb_revision(data: SEBRevisionCreate):
    # Validate seb_baseline exists
    baseline = await seb_baseline_collection.find_one({"_id": data.seb_id})
    if not baseline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB baseline '{data.seb_id}' not found",
        )
    
    new_revision = {
        "_id": str(uuid.uuid4()),
        "seb_id": data.seb_id,
        "revision_no": data.revision_no,
        "previous_revision_id": data.previous_revision_id,
        "revision_reason": data.revision_reason,
        "revision_status": "DRAFT" if data.revision_no == "R01" else data.revision_status,
        "issue_date": data.issue_date,
        "prepared_by": data.prepared_by,
        "prepared_at": datetime.utcnow(),
    }
    await seb_revision_collection.insert_one(new_revision)
    
    # Update current_revision_no in baseline
    await seb_baseline_collection.update_one(
        {"_id": data.seb_id},
        {"$set": {"current_revision_no": data.revision_no, "updated_at": datetime.utcnow()}}
    )
    
    return serialize_seb_revision(new_revision)

@router.get(
    "/seb/revisions",
    response_model=List[SEBRevisionResponse],
    summary="Get All SEB Revisions",
    description="Returns SEB revisions, optionally filtered by SEB ID and revision status.",
)
async def get_all_seb_revisions(
    seb_id: Optional[str] = None,
    revision_status: Optional[str] = None,
):
    query = {}
    if seb_id:
        query["seb_id"] = seb_id
    if revision_status:
        query["revision_status"] = revision_status
    cursor = seb_revision_collection.find(query).sort("prepared_at", -1)
    revisions = await cursor.to_list(length=1000)
    return [serialize_seb_revision(r) for r in revisions]

@router.get(
    "/seb/revisions/{revision_id}",
    response_model=SEBRevisionResponse,
    summary="Get SEB Revision by ID",
    description="Fetch a single SEB revision by its ID.",
)
async def get_seb_revision(revision_id: str):
    revision = await seb_revision_collection.find_one({"_id": revision_id})
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB revision with id '{revision_id}' not found",
        )
    return serialize_seb_revision(revision)

# ═════════════════════════════════════════════════════════
# SEB ITEM — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/items",
    response_model=SEBItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SEB Item",
    description="Creates a new engineering fact item for a SEB revision.",
)
async def create_seb_item(data: SEBItemCreate):
    # Validate seb_revision exists
    revision = await seb_revision_collection.find_one({"_id": data.seb_revision_id})
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB revision '{data.seb_revision_id}' not found",
        )
    if revision.get("revision_status") == "RELEASED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Released SEB revisions are immutable")
    if revision["seb_id"] != data.seb_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The SEB revision does not belong to the supplied SEB",
        )

    fact_collection = await resolve_fact_collection(data.fact_id)
    if not fact_collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SIA fact '{data.fact_id}' not found",
        )
    
    new_item = {
        "_id": str(uuid.uuid4()),
        "fact_id": data.fact_id,
        "fact_collection": fact_collection,
        "seb_id": data.seb_id,
        "seb_revision_id": data.seb_revision_id,
        "status": data.status,
    }
    await seb_item_collection.insert_one(new_item)
    return serialize_seb_item(new_item)

@router.get(
    "/seb/items",
    response_model=List[SEBItemResponse],
    summary="Get All SEB Items",
    description="Returns SEB items, optionally filtered by revision, fact ID, or source collection.",
)
async def get_all_seb_items(
    seb_id: Optional[str] = None,
    seb_revision_id: Optional[str] = None,
    fact_id: Optional[str] = None,
    fact_collection: Optional[str] = None,
    status: Optional[str] = None,
):
    query = {}
    if seb_id:
        query["seb_id"] = seb_id
    if seb_revision_id:
        query["seb_revision_id"] = seb_revision_id
    if fact_id:
        query["fact_id"] = fact_id
    if fact_collection:
        query["fact_collection"] = fact_collection
    if status:
        query["status"] = status
    
    cursor = seb_item_collection.find(query)
    items = await cursor.to_list(length=5000)
    return [serialize_seb_item(i) for i in items]


@router.get(
    "/seb/items/review",
    response_model=List[SEBItemResponse],
    summary="Get SEB items ready for engineering review",
)
async def get_review_seb_items(seb_id: str, seb_revision_id: str):
    """Return only review-status items for one SEB revision."""
    cursor = seb_item_collection.find({
        "seb_id": seb_id,
        "seb_revision_id": seb_revision_id,
        "status": "review",
    })
    return [await serialize_review_seb_item(item) for item in await cursor.to_list(length=5000)]


@router.get(
    "/seb/items/reviewed",
    response_model=List[SEBItemResponse],
    summary="Get completed engineering review SEB items",
)
async def get_reviewed_seb_items(seb_id: str, seb_revision_id: str):
    cursor = seb_item_collection.find({
        "seb_id": seb_id,
        "seb_revision_id": seb_revision_id,
        "status": "reviewed",
    })
    return [await serialize_review_seb_item(item) for item in await cursor.to_list(length=5000)]


@router.get(
    "/seb/items/reviewed/by-discipline",
    response_model=Dict[str, List[SEBItemResponse]],
    summary="Get reviewed SEB items grouped by discipline",
)
async def get_reviewed_seb_items_by_discipline(seb_id: str, seb_revision_id: str):
    """Return completed engineering review items grouped by discipline."""
    cursor = seb_item_collection.find({
        "seb_id": seb_id,
        "seb_revision_id": seb_revision_id,
        "status": "reviewed",
    })
    grouped: Dict[str, List[dict]] = {}
    for item in await cursor.to_list(length=5000):
        reviewed_item = await serialize_review_seb_item(item)
        fact_data = reviewed_item.get("fact_data") or {}
        discipline = item.get("review_discipline") or fact_data.get("discipline") or "UNASSIGNED"
        grouped.setdefault(str(discipline).upper(), []).append(reviewed_item)
    return grouped


@router.get(
    "/seb/items/review/by-discipline",
    response_model=Dict[str, List[SEBItemResponse]],
    summary="Get review SEB items grouped by discipline",
)
async def get_review_seb_items_by_discipline(seb_id: str, seb_revision_id: str):
    """Return review-status SEB items grouped by their engineering discipline."""
    cursor = seb_item_collection.find({
        "seb_id": seb_id,
        "seb_revision_id": seb_revision_id,
        "status": "review",
    })
    grouped: Dict[str, List[dict]] = {}
    for item in await cursor.to_list(length=5000):
        review_item = await serialize_review_seb_item(item)
        fact_data = review_item.get("fact_data") or {}
        discipline = item.get("review_discipline") or fact_data.get("discipline") or "UNASSIGNED"
        grouped.setdefault(str(discipline).upper(), []).append(review_item)
    return grouped


@router.post(
    "/seb/revisions/{revision_id}/submit-engineering-review",
    response_model=SEBRevisionResponse,
    summary="Submit an SEB revision for engineering review",
)
async def submit_seb_revision_for_engineering_review(
    revision_id: str,
    data: SEBRevisionSubmitForReview,
):
    revision = await seb_revision_collection.find_one({"_id": revision_id})
    if not revision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SEB revision '{revision_id}' not found")
    if revision["seb_id"] != data.seb_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The revision does not belong to the supplied SEB")
    review_item_count = await seb_item_collection.count_documents({
        "seb_id": data.seb_id,
        "seb_revision_id": revision_id,
        "status": "review",
    })
    if review_item_count == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Add at least one review-status SEB item before submitting")
    await seb_revision_collection.update_one(
        {"_id": revision_id},
        {"$set": {"revision_status": "IN_REVIEW"}},
    )
    return serialize_seb_revision(await seb_revision_collection.find_one({"_id": revision_id}))


@router.patch(
    "/seb/items/{item_id}/review",
    response_model=SEBItemResponse,
    summary="Review a specific SEB fact",
)
async def review_seb_item(item_id: str, data: SEBItemReviewUpdate):
    item = await seb_item_collection.find_one({"_id": item_id})
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SEB item '{item_id}' not found")
    if item.get("frozen_at"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Released SEB items are immutable")
    if item.get("seb_id") != data.seb_id or item.get("seb_revision_id") != data.seb_revision_id or item.get("fact_id") != data.fact_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The SEB, revision, or fact does not match this item")
    allowed_decisions = {"ACCEPT", "CHANGE_REQUIRED", "ACCEPT_WITH_CONDITION", "REJECT"}
    if data.decision not in allowed_decisions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid engineering review decision")
    await seb_item_collection.update_one(
        {"_id": item_id},
        {"$set": {
            "status": "review",
            "decision": data.decision,
            "review_discipline": data.discipline,
            "reviewer": data.reviewer,
            "review_comment": data.comment,
        }},
    )
    return serialize_seb_item(await seb_item_collection.find_one({"_id": item_id}))


@router.patch("/seb/items/{item_id}/readiness", summary="Set readiness and conditions for an SEB item")
async def update_seb_item_readiness(item_id: str, data: SEBItemReadinessUpdate):
    item = await seb_item_collection.find_one({"_id": item_id})
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SEB item '{item_id}' not found")
    if item.get("frozen_at"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Released SEB items are immutable")
    allowed = {"READY", "CONDITIONAL", "BLOCKED", "NOT_APPLICABLE"}
    if data.discipline_readiness not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid discipline readiness")
    if data.discipline_readiness == "CONDITIONAL" and not all([data.condition, data.required_action, data.owner, data.target_date]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Condition, required action, owner, and target date are required")
    if data.discipline_readiness == "BLOCKED" and not all([data.blocker, data.blocker_reason, data.related_fact_or_gap, data.owner]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Blocker, reason, related fact or gap, and owner are required")
    is_conditional = data.discipline_readiness == "CONDITIONAL"
    is_blocked = data.discipline_readiness == "BLOCKED"
    readiness_document = {
        "status": data.discipline_readiness,
        "conditional": {
            "enabled": is_conditional,
            **({
                "condition": data.condition,
                "required_action": data.required_action,
                "owner": data.owner,
                "target_date": data.target_date,
            } if is_conditional else {}),
        },
        "blocked": {
            "enabled": is_blocked,
            **({
                "blocker": data.blocker,
                "reason": data.blocker_reason,
                "related_fact_or_gap": data.related_fact_or_gap,
                "owner": data.owner,
            } if is_blocked else {}),
        },
    }
    await seb_item_collection.update_one(
        {"_id": item_id},
        {
            "$set": {"discipline_readiness": readiness_document},
            "$unset": {
                "condition": "", "required_action": "", "owner": "", "target_date": "",
                "blocker": "", "blocker_reason": "", "related_fact_or_gap": "",
            },
        },
    )
    return serialize_seb_item(await seb_item_collection.find_one({"_id": item_id}))


@router.post(
    "/seb/revisions/{revision_id}/complete-engineering-review",
    response_model=SEBRevisionResponse,
    summary="Complete engineering review for an SEB revision",
)
async def complete_engineering_review(revision_id: str, data: SEBRevisionSubmitForReview):
    revision = await seb_revision_collection.find_one({"_id": revision_id})
    if not revision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SEB revision '{revision_id}' not found")
    if revision["seb_id"] != data.seb_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The revision does not belong to the supplied SEB")
    pending = await seb_item_collection.count_documents({
        "seb_id": data.seb_id, "seb_revision_id": revision_id, "status": "review",
        "$or": [{"decision": {"$exists": False}}, {"decision": None}, {"decision": ""}],
    })
    if pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="All review items need an engineering decision before completion")
    await seb_item_collection.update_many(
        {"seb_id": data.seb_id, "seb_revision_id": revision_id, "status": "review"},
        {"$set": {"status": "reviewed"}},
    )
    await seb_revision_collection.update_one({"_id": revision_id}, {"$set": {"revision_status": "REVIEW_COMPLETED"}})
    return serialize_seb_revision(await seb_revision_collection.find_one({"_id": revision_id}))


@router.post(
    "/seb/revisions/{revision_id}/complete-readiness",
    response_model=SEBRevisionResponse,
    summary="Complete readiness assessment for an SEB revision",
)
async def complete_readiness_assessment(revision_id: str, data: SEBRevisionSubmitForReview):
    revision = await seb_revision_collection.find_one({"_id": revision_id})
    if not revision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SEB revision '{revision_id}' not found")
    if revision["seb_id"] != data.seb_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The revision does not belong to the supplied SEB")
    if revision.get("revision_status") != "REVIEW_COMPLETED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Engineering review must be completed before readiness")
    pending = await seb_item_collection.count_documents({
        "seb_id": data.seb_id,
        "seb_revision_id": revision_id,
        "status": "reviewed",
        "$or": [
            {"discipline_readiness": {"$exists": False}},
            {"discipline_readiness.status": {"$exists": False}},
            {"discipline_readiness.status": ""},
        ],
    })
    if pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Every reviewed SEB item needs readiness before completion")
    await seb_revision_collection.update_one(
        {"_id": revision_id},
        {"$set": {"revision_status": "READINESS_COMPLETED"}},
    )
    return serialize_seb_revision(await seb_revision_collection.find_one({"_id": revision_id}))

@router.get(
    "/seb/items/{item_id}",
    response_model=SEBItemResponse,
    summary="Get SEB Item by ID",
    description="Fetch a single SEB item by its ID.",
)
async def get_seb_item(item_id: str):
    item = await seb_item_collection.find_one({"_id": item_id})
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB item with id '{item_id}' not found",
        )
    return serialize_seb_item(item)

# ═════════════════════════════════════════════════════════
# SEB ITEM SOURCE — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/item-sources",
    response_model=SEBItemSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SEB Item Source",
    description="Creates provenance record for a SEB item.",
)
async def create_seb_item_source(data: SEBItemSourceCreate):
    # Validate seb_item exists
    item = await seb_item_collection.find_one({"_id": data.seb_item_id})
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB item '{data.seb_item_id}' not found",
        )
    if item.get("frozen_at"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Released SEB items are immutable")
    
    new_source = {
        "_id": str(uuid.uuid4()),
        "seb_item_id": data.seb_item_id,
        "source_type": data.source_type,
        "source_reference": data.source_reference,
        "source_record_id": data.source_record_id,
        "source_date": data.source_date,
        "source_description": data.source_description,
    }
    await seb_item_source_collection.insert_one(new_source)
    return serialize_seb_item_source(new_source)

@router.get(
    "/seb/item-sources",
    response_model=List[SEBItemSourceResponse],
    summary="Get All SEB Item Sources",
    description="Returns all SEB item sources, optionally filtered by seb_item_id.",
)
async def get_all_seb_item_sources(seb_item_id: Optional[str] = None):
    query = {"seb_item_id": seb_item_id} if seb_item_id else {}
    cursor = seb_item_source_collection.find(query)
    sources = await cursor.to_list(length=5000)
    return [serialize_seb_item_source(s) for s in sources]

# ═════════════════════════════════════════════════════════
# SEB EVIDENCE MANIFEST — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/evidence-manifest",
    response_model=SEBEvidenceManifestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SEB Evidence Manifest",
    description="Links exact evidence used in the draft SEB.",
)
async def create_seb_evidence_manifest(data: SEBEvidenceManifestCreate):
    # Validate seb_revision exists
    revision = await seb_revision_collection.find_one({"_id": data.seb_revision_id})
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB revision '{data.seb_revision_id}' not found",
        )
    if revision.get("revision_status") == "RELEASED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Released SEB revisions are immutable")
    
    new_manifest = {
        "_id": str(uuid.uuid4()),
        "seb_revision_id": data.seb_revision_id,
        "seb_item_id": data.seb_item_id,
        "sia_evidence_id": data.sia_evidence_id,
        "evidence_type": data.evidence_type,
        "evidence_hash": data.evidence_hash,
        "is_primary": data.is_primary,
        "included_at": datetime.utcnow(),
    }
    await seb_evidence_manifest_collection.insert_one(new_manifest)
    return serialize_seb_evidence_manifest(new_manifest)

@router.get(
    "/seb/evidence-manifest",
    response_model=List[SEBEvidenceManifestResponse],
    summary="Get All SEB Evidence Manifest Records",
    description="Returns all evidence manifest records, optionally filtered by seb_revision_id.",
)
async def get_all_seb_evidence_manifest(seb_revision_id: Optional[str] = None):
    query = {"seb_revision_id": seb_revision_id} if seb_revision_id else {}
    cursor = seb_evidence_manifest_collection.find(query)
    manifests = await cursor.to_list(length=5000)
    return [serialize_seb_evidence_manifest(m) for m in manifests]

# ═════════════════════════════════════════════════════════
# SEB DISCIPLINE SUMMARY — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/discipline-summaries",
    response_model=SEBDisciplineSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SEB Discipline Summary",
    description="Creates a summary for a specific discipline in the SEB revision.",
)
async def create_seb_discipline_summary(data: SEBDisciplineSummaryCreate):
    # Validate seb_revision exists
    revision = await seb_revision_collection.find_one({"_id": data.seb_revision_id})
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB revision '{data.seb_revision_id}' not found",
        )
    
    new_summary = {
        "_id": str(uuid.uuid4()),
        "seb_revision_id": data.seb_revision_id,
        "discipline": data.discipline,
        "summary": data.summary,
        "key_findings": data.key_findings,
        "readiness_status": data.readiness_status,
        "item_count": data.item_count,
        "verified_item_count": data.verified_item_count,
        "open_gap_count": data.open_gap_count,
    }
    await seb_discipline_summary_collection.insert_one(new_summary)
    return serialize_seb_discipline_summary(new_summary)

@router.get(
    "/seb/discipline-summaries",
    response_model=List[SEBDisciplineSummaryResponse],
    summary="Get All SEB Discipline Summaries",
    description="Returns all discipline summaries, optionally filtered by seb_revision_id.",
)
async def get_all_seb_discipline_summaries(seb_revision_id: Optional[str] = None):
    query = {"seb_revision_id": seb_revision_id} if seb_revision_id else {}
    cursor = seb_discipline_summary_collection.find(query)
    summaries = await cursor.to_list(length=1000)
    return [serialize_seb_discipline_summary(s) for s in summaries]

# ═════════════════════════════════════════════════════════
# SEB CRAG ITEM — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/crag-items",
    response_model=SEBCRAGItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SEB CRAG Item",
    description="Creates a Constraint, Risk, Assumption, Gap or RFI record for the SEB.",
)
async def create_seb_crag_item(data: SEBCRAGItemCreate):
    # Validate seb_revision exists
    revision = await seb_revision_collection.find_one({"_id": data.seb_revision_id})
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB revision '{data.seb_revision_id}' not found",
        )
    
    new_crag = {
        "_id": str(uuid.uuid4()),
        "seb_revision_id": data.seb_revision_id,
        "record_type": data.record_type,
        "discipline": data.discipline,
        "source_record_id": data.source_record_id,
        "description": data.description,
        "impact": data.impact,
        "severity": data.severity,
        "status": data.status,
        "approved_exception": data.approved_exception,
    }
    await seb_crag_item_collection.insert_one(new_crag)
    return serialize_seb_crag_item(new_crag)

@router.get(
    "/seb/crag-items",
    response_model=List[SEBCRAGItemResponse],
    summary="Get All SEB CRAG Items",
    description="Returns all CRAG items, optionally filtered by seb_revision_id or record_type.",
)
async def get_all_seb_crag_items(
    seb_revision_id: Optional[str] = None,
    record_type: Optional[str] = None
):
    query = {}
    if seb_revision_id:
        query["seb_revision_id"] = seb_revision_id
    if record_type:
        query["record_type"] = record_type
    
    cursor = seb_crag_item_collection.find(query)
    crags = await cursor.to_list(length=5000)
    return [serialize_seb_crag_item(c) for c in crags]

# ═════════════════════════════════════════════════════════
# SEB PREPARATION STATUS — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/seb/preparation-status",
    response_model=SEBPreparationStatusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SEB Preparation Status",
    description="Tracks completion status of required SEB preparation sections.",
)
async def create_seb_preparation_status(data: SEBPreparationStatusCreate):
    # Validate seb_revision exists
    revision = await seb_revision_collection.find_one({"_id": data.seb_revision_id})
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SEB revision '{data.seb_revision_id}' not found",
        )
    
    new_status = {
        "_id": str(uuid.uuid4()),
        "seb_revision_id": data.seb_revision_id,
        "section_name": data.section_name,
        "completion_status": data.completion_status,
        "mandatory": data.mandatory,
        "issue_count": data.issue_count,
        "checked_by": data.checked_by,
        "checked_at": datetime.utcnow() if data.checked_by else None,
    }
    await seb_preparation_status_collection.insert_one(new_status)
    return serialize_seb_preparation_status(new_status)

@router.get(
    "/seb/preparation-status",
    response_model=List[SEBPreparationStatusResponse],
    summary="Get All SEB Preparation Status Records",
    description="Returns all preparation status records, optionally filtered by seb_revision_id.",
)
async def get_all_seb_preparation_status(seb_revision_id: Optional[str] = None):
    query = {"seb_revision_id": seb_revision_id} if seb_revision_id else {}
    cursor = seb_preparation_status_collection.find(query)
    statuses = await cursor.to_list(length=1000)
    return [serialize_seb_preparation_status(s) for s in statuses]
