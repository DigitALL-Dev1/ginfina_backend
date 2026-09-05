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
sia_case_collection             = db["sia_case"]
assessment_pack_collection      = db["sia_assessment_pack"]
case_assessment_pack_collection = db["sia_case_assessment_pack"]

router = APIRouter()

# ═════════════════════════════════════════════════════════
# SIA CASE — Models
# ═════════════════════════════════════════════════════════

class SIACaseCreate(BaseModel):
    project_id: str = Field(..., description="FK → ginfina_project._id (NOT NULL)")
    owner_user_id: Optional[str] = Field(None, description="FK → users._id")
    case_code: str = Field(..., max_length=50, description="varchar(50) NOT NULL")
    assessment_purpose: Optional[str] = Field(None, max_length=255, description="varchar(255)")
    assessment_stage: Optional[str] = Field(None, max_length=50, description="varchar(50)")
    crm_reference_id: Optional[str] = Field(None, description="FK → CRM reference")
    opportunity_id: Optional[str] = Field(None, description="CRM opportunity_id selected by user")

class SIACaseResponse(BaseModel):
    id: str
    project_id: str
    owner_user_id: Optional[str]
    case_code: str
    assessment_purpose: Optional[str]
    assessment_stage: Optional[str]
    crm_reference_id: Optional[str]
    opportunity_id: Optional[str]
    created_at: datetime

# ═════════════════════════════════════════════════════════
# SIA ASSESSMENT PACK — Models
# ═════════════════════════════════════════════════════════

class AssessmentPackResponse(BaseModel):
    id: str
    pack_code: str          # varchar(50) NOT NULL
    pack_name: str          # varchar(150) NOT NULL
    pack_type: Optional[str]  # varchar(50)
    is_active: bool

# ═════════════════════════════════════════════════════════
# SIA CASE ASSESSMENT PACK — Models
# ═════════════════════════════════════════════════════════

class CaseAssessmentPackCreate(BaseModel):
    sia_case_id: str = Field(..., description="FK → sia_case._id (NOT NULL)")
    assessment_pack_id: str = Field(..., description="FK → sia_assessment_pack._id (NOT NULL)")
    is_applicable: Optional[bool] = Field(True, description="boolean")
    selected_by: Optional[str] = Field(None, description="FK → users._id")

class CaseAssessmentPackResponse(BaseModel):
    id: str
    sia_case_id: str
    assessment_pack_id: str
    is_applicable: bool
    selected_by: Optional[str]
    created_at: datetime

# ═════════════════════════════════════════════════════════
# Serializers
# ═════════════════════════════════════════════════════════

def serialize_case(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "project_id": doc["project_id"],
        "owner_user_id": doc.get("owner_user_id"),
        "case_code": doc["case_code"],
        "assessment_purpose": doc.get("assessment_purpose"),
        "assessment_stage": doc.get("assessment_stage"),
        "crm_reference_id": doc.get("crm_reference_id"),
        "opportunity_id": doc.get("opportunity_id"),
        "created_at": doc["created_at"],
    }

def serialize_pack(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "pack_code": doc["pack_code"],
        "pack_name": doc["pack_name"],
        "pack_type": doc.get("pack_type"),
        "is_active": doc.get("is_active", True),
    }

def serialize_case_assessment_pack(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "sia_case_id": doc["sia_case_id"],
        "assessment_pack_id": doc["assessment_pack_id"],
        "is_applicable": doc.get("is_applicable", True),
        "selected_by": doc.get("selected_by"),
        "created_at": doc["created_at"],
    }

# ═════════════════════════════════════════════════════════
# Init — indexes + seed dummy data
# ═════════════════════════════════════════════════════════

async def init_sia_case_collection():
    """Create indexes for all SIA collections and seed assessment pack dummy data."""

    # sia_case indexes
    await sia_case_collection.create_index("project_id")
    await sia_case_collection.create_index("owner_user_id")
    await sia_case_collection.create_index("case_code")
    await sia_case_collection.create_index("crm_reference_id")
    print("sia_case collection initialized")

    # sia_assessment_pack indexes
    await assessment_pack_collection.create_index("pack_code")
    await assessment_pack_collection.create_index("is_active")

    # sia_case_assessment_pack indexes
    await case_assessment_pack_collection.create_index("sia_case_id")
    await case_assessment_pack_collection.create_index("assessment_pack_id")
    await case_assessment_pack_collection.create_index("selected_by")

    # Seed assessment pack dummy data only if collection is empty
    count = await assessment_pack_collection.count_documents({})
    if count == 0:
        dummy_packs = [
            {
                "_id": str(uuid.uuid4()),
                "pack_code": "AP-001",
                "pack_name": "Initial Site Assessment Pack",
                "pack_type": "Standard",
                "is_active": True,
            },
            {
                "_id": str(uuid.uuid4()),
                "pack_code": "AP-002",
                "pack_name": "Environmental Impact Assessment Pack",
                "pack_type": "Environmental",
                "is_active": True,
            },
            {
                "_id": str(uuid.uuid4()),
                "pack_code": "AP-003",
                "pack_name": "Structural Engineering Assessment Pack",
                "pack_type": "Structural",
                "is_active": True,
            },
            {
                "_id": str(uuid.uuid4()),
                "pack_code": "AP-004",
                "pack_name": "Geotechnical Survey Pack",
                "pack_type": "Geotechnical",
                "is_active": False,
            },
            {
                "_id": str(uuid.uuid4()),
                "pack_code": "AP-005",
                "pack_name": "Electrical Infrastructure Assessment Pack",
                "pack_type": "Electrical",
                "is_active": True,
            },
        ]
        await assessment_pack_collection.insert_many(dummy_packs)
        print("sia_assessment_pack seeded with 5 dummy records")
    else:
        print("sia_assessment_pack collection initialized")

# ═════════════════════════════════════════════════════════
# SIA CASE — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/sia/cases",
    response_model=SIACaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SIA Case",
    description="Creates a new SIA case linked to a project.",
)
async def create_sia_case(case_data: SIACaseCreate):
    new_case = {
        "_id": str(uuid.uuid4()),
        "project_id": case_data.project_id,
        "owner_user_id": case_data.owner_user_id,
        "case_code": case_data.case_code,
        "assessment_purpose": case_data.assessment_purpose,
        "assessment_stage": case_data.assessment_stage,
        "crm_reference_id": case_data.crm_reference_id,
        "opportunity_id": case_data.opportunity_id,
        "created_at": datetime.utcnow(),
    }
    await sia_case_collection.insert_one(new_case)
    return serialize_case(new_case)


@router.get(
    "/sia/cases",
    response_model=List[SIACaseResponse],
    summary="Get All SIA Cases",
    description="Returns all SIA cases, optionally filtered by project_id.",
)
async def get_all_sia_cases(project_id: Optional[str] = None):
    query = {"project_id": project_id} if project_id else {}
    cursor = sia_case_collection.find(query).sort("created_at", -1)
    cases = await cursor.to_list(length=1000)
    return [serialize_case(c) for c in cases]


@router.get(
    "/sia/cases/{case_id}",
    response_model=SIACaseResponse,
    summary="Get SIA Case by ID",
    description="Fetch a single SIA case by its ID.",
)
async def get_sia_case(case_id: str):
    case = await sia_case_collection.find_one({"_id": case_id})
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SIA case with id '{case_id}' not found",
        )
    return serialize_case(case)

# ═════════════════════════════════════════════════════════
# SIA ASSESSMENT PACK — Endpoints
# ═════════════════════════════════════════════════════════

@router.get(
    "/sia/assessment-packs",
    response_model=List[AssessmentPackResponse],
    summary="Get All Assessment Packs",
    description="Returns all records from sia_assessment_pack collection.",
)
async def get_all_assessment_packs():
    cursor = assessment_pack_collection.find({})
    packs = await cursor.to_list(length=1000)
    return [serialize_pack(p) for p in packs]

# ═════════════════════════════════════════════════════════
# SIA CASE ASSESSMENT PACK — Endpoints
# ═════════════════════════════════════════════════════════

@router.post(
    "/sia/case-assessment-packs",
    response_model=CaseAssessmentPackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SIA Case Assessment Pack",
    description="Links an assessment pack to a SIA case (junction record).",
)
async def create_case_assessment_pack(data: CaseAssessmentPackCreate):
    # Validate sia_case exists
    case = await sia_case_collection.find_one({"_id": data.sia_case_id})
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SIA case '{data.sia_case_id}' not found",
        )

    # Validate assessment_pack exists
    pack = await assessment_pack_collection.find_one({"_id": data.assessment_pack_id})
    if not pack:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment pack '{data.assessment_pack_id}' not found",
        )

    new_record = {
        "_id": str(uuid.uuid4()),
        "sia_case_id": data.sia_case_id,
        "assessment_pack_id": data.assessment_pack_id,
        "is_applicable": data.is_applicable if data.is_applicable is not None else True,
        "selected_by": data.selected_by,
        "created_at": datetime.utcnow(),
    }
    await case_assessment_pack_collection.insert_one(new_record)
    return serialize_case_assessment_pack(new_record)
