from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import os
import uuid
from dotenv import load_dotenv

load_dotenv(override=True)

# ── MongoDB ──────────────────────────────────────────────
MONGODB_URL   = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
client = AsyncIOMotorClient(MONGODB_URL)
db     = client[DATABASE_NAME]

evidence_col          = db["sia_evidence"]
evidence_verif_col    = db["sia_evidence_verification"]
source_fact_col       = db["sia_source_fact"]
ai_obs_col            = db["sia_ai_observation"]
ai_disp_col           = db["sia_ai_disposition"]
conflict_col          = db["sia_conflict"]
conflict_res_col      = db["sia_conflict_resolution"]
data_gap_col          = db["sia_data_gap"]
rfi_action_col        = db["sia_rfi_action"]
constraint_col        = db["sia_constraint_assumption"]
disc_ready_col        = db["sia_discipline_readiness"]
ready_cond_col        = db["sia_readiness_condition"]
ready_blocker_col     = db["sia_readiness_blocker"]
ready_review_col      = db["sia_readiness_review"]

router = APIRouter()

# ════════════════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════════════════

async def init_evidence_ai_readiness_collections():
    # evidence
    await evidence_col.create_index("sia_case_id")
    await evidence_col.create_index("site_id")
    await evidence_col.create_index("poi_id")
    await evidence_col.create_index("engineering_assessment_id")
    await evidence_verif_col.create_index("evidence_id")
    await evidence_verif_col.create_index("verified_by")

    # source facts
    await source_fact_col.create_index("sia_case_id")
    await source_fact_col.create_index("evidence_id")

    # AI
    await ai_obs_col.create_index("sia_case_id")
    await ai_disp_col.create_index("ai_observation_id")
    await ai_disp_col.create_index("reviewer_user_id")

    # conflicts
    await conflict_col.create_index("sia_case_id")
    await conflict_res_col.create_index("conflict_id")
    await conflict_res_col.create_index("resolved_by")

    # data gaps / RFI
    await data_gap_col.create_index("sia_case_id")
    await data_gap_col.create_index("owner_user_id")
    await rfi_action_col.create_index("sia_case_id")
    await rfi_action_col.create_index("data_gap_id")
    await rfi_action_col.create_index("assigned_to")

    # constraints / assumptions
    await constraint_col.create_index("sia_case_id")
    await constraint_col.create_index("recorded_by")

    # readiness
    await disc_ready_col.create_index("sia_case_id")
    await disc_ready_col.create_index("site_id")
    await disc_ready_col.create_index("assessed_by")
    await ready_cond_col.create_index("discipline_readiness_id")
    await ready_cond_col.create_index("owner_user_id")
    await ready_blocker_col.create_index("discipline_readiness_id")
    await ready_blocker_col.create_index("data_gap_id")
    await ready_review_col.create_index("discipline_readiness_id")
    await ready_review_col.create_index("reviewer_user_id")

    print("evidence_ai_readiness collections initialized")

# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def new_id() -> str:
    return str(uuid.uuid4())

def not_found(entity: str, eid: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"{entity} '{eid}' not found")

def ser(doc: dict) -> dict:
    d = {k: doc.get(k) for k in doc if k != "_id"}
    d["id"] = str(doc["_id"])
    return d

async def require(col, eid: str, name: str):
    doc = await col.find_one({"_id": eid})
    if not doc:
        not_found(name, eid)
    return doc

# ════════════════════════════════════════════════════════════
# SIA_EVIDENCE
# ════════════════════════════════════════════════════════════

class EvidenceCreate(BaseModel):
    sia_case_id:              str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id:                  Optional[str] = None
    poi_id:                   Optional[str] = None
    engineering_assessment_id: Optional[str] = None
    evidence_code:            str = Field(..., max_length=50)
    evidence_type:            Optional[str] = Field(None, max_length=100)
    source_type:              Optional[str] = Field(None, max_length=100)
    file_name:                Optional[str] = Field(None, max_length=255)
    file_path:                Optional[str] = None
    file_hash:                Optional[str] = Field(None, max_length=255)
    captured_at:              Optional[str] = None
    captured_by:              Optional[str] = Field(None, description="FK → users._id")
    reliability_status:       Optional[str] = Field(None, max_length=50)
    evidence_status:          Optional[str] = Field(None, max_length=50)

class EvidenceResponse(EvidenceCreate):
    id: str
    created_at: datetime

@router.post("/sia/evidence", response_model=EvidenceResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_evidence(data: EvidenceCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await evidence_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/evidence/{evidence_id}", response_model=EvidenceResponse,
            tags=["SIA - Evidence, AI & Readiness"])
async def get_evidence(evidence_id: str):
    doc = await evidence_col.find_one({"_id": evidence_id})
    if not doc: not_found("Evidence", evidence_id)
    return ser(doc)

@router.get("/sia/cases/{case_id}/evidence", response_model=List[EvidenceResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_evidence_by_case(case_id: str):
    docs = await evidence_col.find({"sia_case_id": case_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_EVIDENCE_VERIFICATION
# ════════════════════════════════════════════════════════════

class EvidenceVerificationCreate(BaseModel):
    evidence_id:          str = Field(..., description="FK → sia_evidence._id (NOT NULL)")
    verified_by:          Optional[str] = Field(None, description="FK → users._id")
    verification_status:  Optional[str] = Field(None, max_length=50)
    verification_comment: Optional[str] = None
    verified_at:          Optional[str] = None

class EvidenceVerificationResponse(EvidenceVerificationCreate):
    id: str
    created_at: datetime

@router.post("/sia/evidence-verifications", response_model=EvidenceVerificationResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_evidence_verification(data: EvidenceVerificationCreate):
    await require(evidence_col, data.evidence_id, "Evidence")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await evidence_verif_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/evidence/{evidence_id}/verifications",
            response_model=List[EvidenceVerificationResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_evidence_verifications(evidence_id: str):
    docs = await evidence_verif_col.find({"evidence_id": evidence_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SOURCE_FACT
# ════════════════════════════════════════════════════════════

class SourceFactCreate(BaseModel):
    sia_case_id:        str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id:            Optional[str] = None
    evidence_id:        Optional[str] = None
    fact_name:          Optional[str] = Field(None, max_length=150)
    fact_value:         Optional[str] = None
    unit:               Optional[str] = Field(None, max_length=50)
    source_type:        Optional[str] = Field(None, max_length=100)
    reliability_status: Optional[str] = Field(None, max_length=50)
    fact_status:        Optional[str] = Field(None, max_length=50)

class SourceFactResponse(SourceFactCreate):
    id: str
    created_at: datetime

@router.post("/sia/source-facts", response_model=SourceFactResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_source_fact(data: SourceFactCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await source_fact_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/cases/{case_id}/source-facts", response_model=List[SourceFactResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_source_facts_by_case(case_id: str):
    docs = await source_fact_col.find({"sia_case_id": case_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_AI_OBSERVATION
# ════════════════════════════════════════════════════════════

class AIObservationCreate(BaseModel):
    sia_case_id:        str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id:            Optional[str] = None
    observation_code:   str = Field(..., max_length=50)
    task_type:          Optional[str] = Field(None, max_length=100)
    model_name:         Optional[str] = Field(None, max_length=150)
    model_version:      Optional[str] = Field(None, max_length=100)
    input_reference:    Optional[str] = None
    output_value:       Optional[str] = None
    confidence_score:   Optional[float] = None
    reliability_status: Optional[str] = Field(None, max_length=50)

class AIObservationResponse(AIObservationCreate):
    id: str
    created_at: datetime

@router.post("/sia/ai-observations", response_model=AIObservationResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_ai_observation(data: AIObservationCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ai_obs_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/cases/{case_id}/ai-observations", response_model=List[AIObservationResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_ai_observations_by_case(case_id: str):
    docs = await ai_obs_col.find({"sia_case_id": case_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_AI_DISPOSITION
# ════════════════════════════════════════════════════════════

DISPOSITIONS = ["ACCEPTED", "REJECTED", "MODIFIED", "ESCALATED"]

class AIDispositionCreate(BaseModel):
    ai_observation_id:  str = Field(..., description="FK → sia_ai_observation._id (NOT NULL)")
    reviewer_user_id:   Optional[str] = Field(None, description="FK → users._id")
    disposition:        Optional[str] = Field(None, max_length=50,
                            description=f"One of: {', '.join(DISPOSITIONS)}")
    modified_value:     Optional[str] = None
    reviewer_comment:   Optional[str] = None
    disposition_at:     Optional[str] = None

class AIDispositionResponse(AIDispositionCreate):
    id: str
    created_at: datetime

@router.post("/sia/ai-dispositions", response_model=AIDispositionResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_ai_disposition(data: AIDispositionCreate):
    await require(ai_obs_col, data.ai_observation_id, "AI Observation")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ai_disp_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/ai-observations/{obs_id}/dispositions",
            response_model=List[AIDispositionResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_ai_dispositions(obs_id: str):
    docs = await ai_disp_col.find({"ai_observation_id": obs_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_CONFLICT
# ════════════════════════════════════════════════════════════

class ConflictCreate(BaseModel):
    sia_case_id:    str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id:        Optional[str] = None
    conflict_code:  Optional[str] = Field(None, max_length=50)
    discipline:     Optional[str] = Field(None, max_length=100)
    conflict_type:  Optional[str] = Field(None, max_length=100)
    source_a:       Optional[str] = Field(None, max_length=255)
    value_a:        Optional[str] = None
    source_b:       Optional[str] = Field(None, max_length=255)
    value_b:        Optional[str] = None
    description:    Optional[str] = None
    priority:       Optional[str] = Field(None, max_length=50)
    status:         Optional[str] = Field(None, max_length=50)

class ConflictResponse(ConflictCreate):
    id: str
    created_at: datetime

@router.post("/sia/conflicts", response_model=ConflictResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_conflict(data: ConflictCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await conflict_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/cases/{case_id}/conflicts", response_model=List[ConflictResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_conflicts_by_case(case_id: str):
    docs = await conflict_col.find({"sia_case_id": case_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_CONFLICT_RESOLUTION
# ════════════════════════════════════════════════════════════

class ConflictResolutionCreate(BaseModel):
    conflict_id:        str = Field(..., description="FK → sia_conflict._id (NOT NULL)")
    resolved_by:        Optional[str] = Field(None, description="FK → users._id")
    accepted_value:     Optional[str] = None
    resolution_reason:  Optional[str] = None
    resolution_status:  Optional[str] = Field(None, max_length=50)
    resolved_at:        Optional[str] = None

class ConflictResolutionResponse(ConflictResolutionCreate):
    id: str
    created_at: datetime

@router.post("/sia/conflict-resolutions", response_model=ConflictResolutionResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_conflict_resolution(data: ConflictResolutionCreate):
    await require(conflict_col, data.conflict_id, "Conflict")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await conflict_res_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/conflicts/{conflict_id}/resolutions",
            response_model=List[ConflictResolutionResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_conflict_resolutions(conflict_id: str):
    docs = await conflict_res_col.find({"conflict_id": conflict_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DATA_GAP
# ════════════════════════════════════════════════════════════

class DataGapCreate(BaseModel):
    sia_case_id:     str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id:         Optional[str] = None
    gap_code:        Optional[str] = Field(None, max_length=50)
    discipline:      Optional[str] = Field(None, max_length=100)
    gap_description: Optional[str] = None
    impact:          Optional[str] = None
    priority:        Optional[str] = Field(None, max_length=50)
    owner_user_id:   Optional[str] = Field(None, description="FK → users._id")
    target_date:     Optional[str] = None
    status:          Optional[str] = Field(None, max_length=50)

class DataGapResponse(DataGapCreate):
    id: str
    created_at: datetime

@router.post("/sia/data-gaps", response_model=DataGapResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_data_gap(data: DataGapCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await data_gap_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/data-gaps/{gap_id}", response_model=DataGapResponse,
            tags=["SIA - Evidence, AI & Readiness"])
async def get_data_gap(gap_id: str):
    doc = await data_gap_col.find_one({"_id": gap_id})
    if not doc: not_found("Data Gap", gap_id)
    return ser(doc)

@router.get("/sia/cases/{case_id}/data-gaps", response_model=List[DataGapResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_data_gaps_by_case(case_id: str):
    docs = await data_gap_col.find({"sia_case_id": case_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_RFI_ACTION
# ════════════════════════════════════════════════════════════

class RFIActionCreate(BaseModel):
    sia_case_id:  str = Field(..., description="FK → sia_case._id (NOT NULL)")
    data_gap_id:  Optional[str] = None
    action_code:  Optional[str] = Field(None, max_length=50)
    action_type:  Optional[str] = Field(None, max_length=50)
    subject:      Optional[str] = Field(None, max_length=255)
    description:  Optional[str] = None
    assigned_to:  Optional[str] = Field(None, description="FK → users._id")
    target_date:  Optional[str] = None
    response:     Optional[str] = None
    status:       Optional[str] = Field(None, max_length=50)
    completed_at: Optional[str] = None

class RFIActionResponse(RFIActionCreate):
    id: str
    created_at: datetime

@router.post("/sia/rfi-actions", response_model=RFIActionResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_rfi_action(data: RFIActionCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await rfi_action_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/cases/{case_id}/rfi-actions", response_model=List[RFIActionResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_rfi_actions_by_case(case_id: str):
    docs = await rfi_action_col.find({"sia_case_id": case_id}).to_list(1000)
    return [ser(d) for d in docs]

@router.get("/sia/data-gaps/{gap_id}/rfi-actions", response_model=List[RFIActionResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_rfi_actions_by_gap(gap_id: str):
    docs = await rfi_action_col.find({"data_gap_id": gap_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_CONSTRAINT_ASSUMPTION
# ════════════════════════════════════════════════════════════

class ConstraintAssumptionCreate(BaseModel):
    sia_case_id:        str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id:            Optional[str] = None
    record_type:        Optional[str] = Field(None, max_length=50,
                            description="CONSTRAINT or ASSUMPTION")
    discipline:         Optional[str] = Field(None, max_length=100)
    description:        Optional[str] = None
    impact:             Optional[str] = None
    reliability_status: Optional[str] = Field(None, max_length=50)
    recorded_by:        Optional[str] = Field(None, description="FK → users._id")
    status:             Optional[str] = Field(None, max_length=50)

class ConstraintAssumptionResponse(ConstraintAssumptionCreate):
    id: str
    created_at: datetime

@router.post("/sia/constraints-assumptions", response_model=ConstraintAssumptionResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_constraint_assumption(data: ConstraintAssumptionCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await constraint_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/cases/{case_id}/constraints-assumptions",
            response_model=List[ConstraintAssumptionResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_constraints_assumptions_by_case(case_id: str):
    docs = await constraint_col.find({"sia_case_id": case_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DISCIPLINE_READINESS
# ════════════════════════════════════════════════════════════

READINESS_STATUSES = ["NOT_ASSESSED", "READY", "CONDITIONAL", "BLOCKED", "NOT_APPLICABLE"]

class DisciplineReadinessCreate(BaseModel):
    sia_case_id:      str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id:          str = Field(..., description="FK → sia_site._id (NOT NULL)")
    discipline:       str = Field(..., max_length=100)
    readiness_status: Optional[str] = Field(None, max_length=50,
                          description=f"One of: {', '.join(READINESS_STATUSES)}")
    assessment_date:  Optional[str] = None
    summary:          Optional[str] = None
    assessed_by:      Optional[str] = Field(None, description="FK → users._id")

class DisciplineReadinessResponse(DisciplineReadinessCreate):
    id: str
    created_at: datetime

@router.post("/sia/discipline-readiness", response_model=DisciplineReadinessResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_discipline_readiness(data: DisciplineReadinessCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await disc_ready_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/discipline-readiness/{readiness_id}",
            response_model=DisciplineReadinessResponse,
            tags=["SIA - Evidence, AI & Readiness"])
async def get_discipline_readiness(readiness_id: str):
    doc = await disc_ready_col.find_one({"_id": readiness_id})
    if not doc: not_found("Discipline Readiness", readiness_id)
    return ser(doc)

@router.get("/sia/cases/{case_id}/discipline-readiness",
            response_model=List[DisciplineReadinessResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_discipline_readiness_by_case(case_id: str):
    docs = await disc_ready_col.find({"sia_case_id": case_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_READINESS_CONDITION
# ════════════════════════════════════════════════════════════

class ReadinessConditionCreate(BaseModel):
    discipline_readiness_id: str = Field(..., description="FK → sia_discipline_readiness._id (NOT NULL)")
    condition_description:   Optional[str] = None
    required_action:         Optional[str] = None
    owner_user_id:           Optional[str] = Field(None, description="FK → users._id")
    target_date:             Optional[str] = None
    status:                  Optional[str] = Field(None, max_length=50)

class ReadinessConditionResponse(ReadinessConditionCreate):
    id: str
    created_at: datetime

@router.post("/sia/readiness-conditions", response_model=ReadinessConditionResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_readiness_condition(data: ReadinessConditionCreate):
    await require(disc_ready_col, data.discipline_readiness_id, "Discipline Readiness")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ready_cond_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/discipline-readiness/{readiness_id}/conditions",
            response_model=List[ReadinessConditionResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_readiness_conditions(readiness_id: str):
    docs = await ready_cond_col.find({"discipline_readiness_id": readiness_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_READINESS_BLOCKER
# ════════════════════════════════════════════════════════════

class ReadinessBlockerCreate(BaseModel):
    discipline_readiness_id: str = Field(..., description="FK → sia_discipline_readiness._id (NOT NULL)")
    data_gap_id:             Optional[str] = Field(None, description="FK → sia_data_gap._id")
    blocker_type:            Optional[str] = Field(None, max_length=100)
    blocker_description:     Optional[str] = None
    severity:                Optional[str] = Field(None, max_length=50)
    owner_user_id:           Optional[str] = Field(None, description="FK → users._id")
    status:                  Optional[str] = Field(None, max_length=50)

class ReadinessBlockerResponse(ReadinessBlockerCreate):
    id: str
    created_at: datetime

@router.post("/sia/readiness-blockers", response_model=ReadinessBlockerResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_readiness_blocker(data: ReadinessBlockerCreate):
    await require(disc_ready_col, data.discipline_readiness_id, "Discipline Readiness")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ready_blocker_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/discipline-readiness/{readiness_id}/blockers",
            response_model=List[ReadinessBlockerResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_readiness_blockers(readiness_id: str):
    docs = await ready_blocker_col.find({"discipline_readiness_id": readiness_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_READINESS_REVIEW
# ════════════════════════════════════════════════════════════

class ReadinessReviewCreate(BaseModel):
    discipline_readiness_id: str = Field(..., description="FK → sia_discipline_readiness._id (NOT NULL)")
    reviewer_user_id:        Optional[str] = Field(None, description="FK → users._id")
    review_decision:         Optional[str] = Field(None, max_length=50)
    review_comment:          Optional[str] = None
    reviewed_at:             Optional[str] = None

class ReadinessReviewResponse(ReadinessReviewCreate):
    id: str
    created_at: datetime

@router.post("/sia/readiness-reviews", response_model=ReadinessReviewResponse,
             status_code=201, tags=["SIA - Evidence, AI & Readiness"])
async def create_readiness_review(data: ReadinessReviewCreate):
    await require(disc_ready_col, data.discipline_readiness_id, "Discipline Readiness")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ready_review_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/discipline-readiness/{readiness_id}/reviews",
            response_model=List[ReadinessReviewResponse],
            tags=["SIA - Evidence, AI & Readiness"])
async def get_readiness_reviews(readiness_id: str):
    docs = await ready_review_col.find({"discipline_readiness_id": readiness_id}).to_list(1000)
    return [ser(d) for d in docs]
