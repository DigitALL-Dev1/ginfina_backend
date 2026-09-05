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

seb_col             = db["sia_seb"]
seb_rev_col         = db["sia_seb_revision"]
seb_item_col        = db["sia_seb_item"]
seb_evidence_col    = db["sia_seb_evidence"]
seb_disc_col        = db["sia_seb_discipline_result"]
seb_cg_col          = db["sia_seb_constraint_gap"]
seb_review_col      = db["sia_seb_review"]
seb_approval_col    = db["sia_seb_approval"]
seb_release_col     = db["sia_seb_release"]
seb_change_col      = db["sia_seb_change_impact"]
ewb_handoff_col     = db["sia_ewb_handoff"]
ewb_item_col        = db["sia_ewb_handoff_item"]
ewb_cond_col        = db["sia_ewb_handoff_condition"]

router = APIRouter()

# ════════════════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════════════════

async def init_seb_ewb_handoff_collections():
    # SEB
    await seb_col.create_index("sia_case_id")
    await seb_col.create_index("site_id")
    await seb_col.create_index("seb_code")
    await seb_col.create_index("created_by")

    # SEB Revision
    await seb_rev_col.create_index("seb_id")
    await seb_rev_col.create_index("previous_revision_id")
    await seb_rev_col.create_index("created_by")

    # SEB Item
    await seb_item_col.create_index("seb_revision_id")

    # SEB Evidence
    await seb_evidence_col.create_index("seb_revision_id")
    await seb_evidence_col.create_index("seb_item_id")
    await seb_evidence_col.create_index("evidence_id")

    # SEB Discipline Result
    await seb_disc_col.create_index("seb_revision_id")

    # SEB Constraint/Gap
    await seb_cg_col.create_index("seb_revision_id")

    # SEB Review / Approval / Release / Change Impact
    for col in [seb_review_col, seb_approval_col, seb_release_col, seb_change_col]:
        await col.create_index("seb_revision_id")
    await seb_review_col.create_index("reviewer_user_id")
    await seb_approval_col.create_index("approver_user_id")
    await seb_release_col.create_index("released_by")
    await seb_change_col.create_index("reviewed_by")
    await seb_change_col.create_index("previous_revision_id")

    # EWB Handoff
    await ewb_handoff_col.create_index("seb_revision_id")
    await ewb_handoff_col.create_index("project_id")
    await ewb_handoff_col.create_index("prepared_by")
    await ewb_item_col.create_index("ewb_handoff_id")
    await ewb_item_col.create_index("seb_item_id")
    await ewb_cond_col.create_index("ewb_handoff_id")
    await ewb_cond_col.create_index("owner_user_id")

    print("seb_ewb_handoff collections initialized")

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
# SIA_SEB  (parent)
# ════════════════════════════════════════════════════════════

class SEBCreate(BaseModel):
    sia_case_id:       str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id:           str = Field(..., description="FK → sia_site._id (NOT NULL)")
    seb_code:          str = Field(..., max_length=50)
    assessment_stage:  Optional[str] = Field(None, max_length=50)
    current_revision:  Optional[str] = Field(None, max_length=20)
    status:            Optional[str] = Field(None, max_length=50)
    created_by:        Optional[str] = Field(None, description="FK → users._id")

class SEBResponse(SEBCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb", response_model=SEBResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb(data: SEBCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb/{seb_id}", response_model=SEBResponse,
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb(seb_id: str):
    doc = await seb_col.find_one({"_id": seb_id})
    if not doc: not_found("SEB", seb_id)
    return ser(doc)

@router.get("/sia/cases/{case_id}/seb", response_model=List[SEBResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_by_case(case_id: str):
    docs = await seb_col.find({"sia_case_id": case_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SEB_REVISION
# ════════════════════════════════════════════════════════════

class SEBRevisionCreate(BaseModel):
    seb_id:               str = Field(..., description="FK → sia_seb._id (NOT NULL)")
    revision_no:          str = Field(..., max_length=20)
    revision_status:      Optional[str] = Field(None, max_length=50)
    issue_date:           Optional[str] = None
    revision_reason:      Optional[str] = None
    previous_revision_id: Optional[str] = Field(None, description="FK → sia_seb_revision._id")
    created_by:           Optional[str] = Field(None, description="FK → users._id")

class SEBRevisionResponse(SEBRevisionCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb-revisions", response_model=SEBRevisionResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb_revision(data: SEBRevisionCreate):
    await require(seb_col, data.seb_id, "SEB")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_rev_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}", response_model=SEBRevisionResponse,
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_revision(revision_id: str):
    doc = await seb_rev_col.find_one({"_id": revision_id})
    if not doc: not_found("SEB Revision", revision_id)
    return ser(doc)

@router.get("/sia/seb/{seb_id}/revisions", response_model=List[SEBRevisionResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_revisions_by_seb(seb_id: str):
    docs = await seb_rev_col.find({"seb_id": seb_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SEB_ITEM
# ════════════════════════════════════════════════════════════

class SEBItemCreate(BaseModel):
    seb_revision_id:   str = Field(..., description="FK → sia_seb_revision._id (NOT NULL)")
    item_type:         Optional[str] = Field(None, max_length=100)
    discipline:        Optional[str] = Field(None, max_length=100)
    item_name:         Optional[str] = Field(None, max_length=150)
    item_value:        Optional[str] = None
    unit:              Optional[str] = Field(None, max_length=50)
    reliability_status: Optional[str] = Field(None, max_length=50)
    source_record_type: Optional[str] = Field(None, max_length=100)
    source_record_id:   Optional[str] = None
    status:            Optional[str] = Field(None, max_length=50)

class SEBItemResponse(SEBItemCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb-items", response_model=SEBItemResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb_item(data: SEBItemCreate):
    await require(seb_rev_col, data.seb_revision_id, "SEB Revision")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_item_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}/items", response_model=List[SEBItemResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_items(revision_id: str):
    docs = await seb_item_col.find({"seb_revision_id": revision_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SEB_EVIDENCE
# ════════════════════════════════════════════════════════════

class SEBEvidenceCreate(BaseModel):
    seb_revision_id: str = Field(..., description="FK → sia_seb_revision._id (NOT NULL)")
    seb_item_id:     Optional[str] = Field(None, description="FK → sia_seb_item._id")
    evidence_id:     str = Field(..., description="FK → sia_evidence._id (NOT NULL)")
    evidence_hash:   Optional[str] = Field(None, max_length=255)
    is_primary:      Optional[bool] = False

class SEBEvidenceResponse(SEBEvidenceCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb-evidence", response_model=SEBEvidenceResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb_evidence(data: SEBEvidenceCreate):
    await require(seb_rev_col, data.seb_revision_id, "SEB Revision")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_evidence_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}/evidence", response_model=List[SEBEvidenceResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_evidence(revision_id: str):
    docs = await seb_evidence_col.find({"seb_revision_id": revision_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SEB_DISCIPLINE_RESULT
# ════════════════════════════════════════════════════════════

class SEBDisciplineResultCreate(BaseModel):
    seb_revision_id:    str = Field(..., description="FK → sia_seb_revision._id (NOT NULL)")
    discipline:         Optional[str] = Field(None, max_length=100)
    readiness_status:   Optional[str] = Field(None, max_length=50)
    assessment_summary: Optional[str] = None
    condition_summary:  Optional[str] = None
    status:             Optional[str] = Field(None, max_length=50)

class SEBDisciplineResultResponse(SEBDisciplineResultCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb-discipline-results", response_model=SEBDisciplineResultResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb_discipline_result(data: SEBDisciplineResultCreate):
    await require(seb_rev_col, data.seb_revision_id, "SEB Revision")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_disc_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}/discipline-results",
            response_model=List[SEBDisciplineResultResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_discipline_results(revision_id: str):
    docs = await seb_disc_col.find({"seb_revision_id": revision_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SEB_CONSTRAINT_GAP
# ════════════════════════════════════════════════════════════

CG_TYPES = ["CONSTRAINT", "RISK", "ASSUMPTION", "GAP", "RFI"]

class SEBConstraintGapCreate(BaseModel):
    seb_revision_id: str = Field(..., description="FK → sia_seb_revision._id (NOT NULL)")
    record_type:     Optional[str] = Field(None, max_length=50,
                         description=f"One of: {', '.join(CG_TYPES)}")
    discipline:      Optional[str] = Field(None, max_length=100)
    description:     Optional[str] = None
    impact:          Optional[str] = None
    status:          Optional[str] = Field(None, max_length=50)

class SEBConstraintGapResponse(SEBConstraintGapCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb-constraint-gaps", response_model=SEBConstraintGapResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb_constraint_gap(data: SEBConstraintGapCreate):
    await require(seb_rev_col, data.seb_revision_id, "SEB Revision")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_cg_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}/constraint-gaps",
            response_model=List[SEBConstraintGapResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_constraint_gaps(revision_id: str):
    docs = await seb_cg_col.find({"seb_revision_id": revision_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SEB_REVIEW
# ════════════════════════════════════════════════════════════

class SEBReviewCreate(BaseModel):
    seb_revision_id:  str = Field(..., description="FK → sia_seb_revision._id (NOT NULL)")
    reviewer_user_id: Optional[str] = Field(None, description="FK → users._id")
    review_status:    Optional[str] = Field(None, max_length=50)
    review_comment:   Optional[str] = None
    reviewed_at:      Optional[str] = None

class SEBReviewResponse(SEBReviewCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb-reviews", response_model=SEBReviewResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb_review(data: SEBReviewCreate):
    await require(seb_rev_col, data.seb_revision_id, "SEB Revision")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_review_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}/reviews", response_model=List[SEBReviewResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_reviews(revision_id: str):
    docs = await seb_review_col.find({"seb_revision_id": revision_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SEB_APPROVAL
# ════════════════════════════════════════════════════════════

class SEBApprovalCreate(BaseModel):
    seb_revision_id:   str = Field(..., description="FK → sia_seb_revision._id (NOT NULL)")
    approver_user_id:  Optional[str] = Field(None, description="FK → users._id")
    approval_decision: Optional[str] = Field(None, max_length=50)
    approval_condition: Optional[str] = None
    approval_comment:  Optional[str] = None
    approved_at:       Optional[str] = None

class SEBApprovalResponse(SEBApprovalCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb-approvals", response_model=SEBApprovalResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb_approval(data: SEBApprovalCreate):
    await require(seb_rev_col, data.seb_revision_id, "SEB Revision")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_approval_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}/approvals", response_model=List[SEBApprovalResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_approvals(revision_id: str):
    docs = await seb_approval_col.find({"seb_revision_id": revision_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SEB_RELEASE
# ════════════════════════════════════════════════════════════

class SEBReleaseCreate(BaseModel):
    seb_revision_id: str = Field(..., description="FK → sia_seb_revision._id (NOT NULL)")
    release_hash:    str = Field(..., max_length=255, description="NOT NULL — immutable baseline hash")
    release_status:  Optional[str] = Field(None, max_length=50)
    released_at:     Optional[str] = None
    released_by:     Optional[str] = Field(None, description="FK → users._id")

class SEBReleaseResponse(SEBReleaseCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb-releases", response_model=SEBReleaseResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb_release(data: SEBReleaseCreate):
    await require(seb_rev_col, data.seb_revision_id, "SEB Revision")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_release_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}/releases", response_model=List[SEBReleaseResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_releases(revision_id: str):
    docs = await seb_release_col.find({"seb_revision_id": revision_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SEB_CHANGE_IMPACT
# ════════════════════════════════════════════════════════════

class SEBChangeImpactCreate(BaseModel):
    seb_revision_id:      str = Field(..., description="FK → sia_seb_revision._id (NOT NULL)")
    previous_revision_id: Optional[str] = Field(None, description="FK → sia_seb_revision._id")
    change_type:          Optional[str] = Field(None, max_length=50)
    change_description:   Optional[str] = None
    materiality:          Optional[str] = Field(None, max_length=50)
    affected_discipline:  Optional[str] = Field(None, max_length=100)
    affected_ewp:         Optional[bool] = None
    impact_description:   Optional[str] = None
    reviewed_by:          Optional[str] = Field(None, description="FK → users._id")
    impact_status:        Optional[str] = Field(None, max_length=50)
    reviewed_at:          Optional[str] = None

class SEBChangeImpactResponse(SEBChangeImpactCreate):
    id: str
    created_at: datetime

@router.post("/sia/seb-change-impacts", response_model=SEBChangeImpactResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_seb_change_impact(data: SEBChangeImpactCreate):
    await require(seb_rev_col, data.seb_revision_id, "SEB Revision")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await seb_change_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}/change-impacts",
            response_model=List[SEBChangeImpactResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_seb_change_impacts(revision_id: str):
    docs = await seb_change_col.find({"seb_revision_id": revision_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_EWB_HANDOFF
# ════════════════════════════════════════════════════════════

class EWBHandoffCreate(BaseModel):
    seb_revision_id:  str = Field(..., description="FK → sia_seb_revision._id (NOT NULL)")
    project_id:       str = Field(..., description="FK → ginfina_project._id (NOT NULL)")
    handoff_code:     Optional[str] = Field(None, max_length=50)
    ewp_reference_id: Optional[str] = Field(None, max_length=100)
    handoff_status:   Optional[str] = Field(None, max_length=50)
    readiness_status: Optional[str] = Field(None, max_length=50)
    prepared_by:      Optional[str] = Field(None, description="FK → users._id")
    prepared_at:      Optional[str] = None
    accepted_at:      Optional[str] = None

class EWBHandoffResponse(EWBHandoffCreate):
    id: str
    created_at: datetime

@router.post("/sia/ewb-handoffs", response_model=EWBHandoffResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_ewb_handoff(data: EWBHandoffCreate):
    await require(seb_rev_col, data.seb_revision_id, "SEB Revision")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ewb_handoff_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/ewb-handoffs/{handoff_id}", response_model=EWBHandoffResponse,
            tags=["SIA - SEB & EWB Handoff"])
async def get_ewb_handoff(handoff_id: str):
    doc = await ewb_handoff_col.find_one({"_id": handoff_id})
    if not doc: not_found("EWB Handoff", handoff_id)
    return ser(doc)

@router.get("/sia/seb-revisions/{revision_id}/ewb-handoffs",
            response_model=List[EWBHandoffResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_ewb_handoffs_by_revision(revision_id: str):
    docs = await ewb_handoff_col.find({"seb_revision_id": revision_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_EWB_HANDOFF_ITEM
# ════════════════════════════════════════════════════════════

class EWBHandoffItemCreate(BaseModel):
    ewb_handoff_id: str = Field(..., description="FK → sia_ewb_handoff._id (NOT NULL)")
    seb_item_id:    str = Field(..., description="FK → sia_seb_item._id (NOT NULL)")
    discipline:     Optional[str] = Field(None, max_length=100)
    applicability:  Optional[str] = Field(None, max_length=100)
    is_mandatory:   Optional[bool] = False
    status:         Optional[str] = Field(None, max_length=50)

class EWBHandoffItemResponse(EWBHandoffItemCreate):
    id: str
    created_at: datetime

@router.post("/sia/ewb-handoff-items", response_model=EWBHandoffItemResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_ewb_handoff_item(data: EWBHandoffItemCreate):
    await require(ewb_handoff_col, data.ewb_handoff_id, "EWB Handoff")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ewb_item_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/ewb-handoffs/{handoff_id}/items",
            response_model=List[EWBHandoffItemResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_ewb_handoff_items(handoff_id: str):
    docs = await ewb_item_col.find({"ewb_handoff_id": handoff_id}).to_list(1000)
    return [ser(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_EWB_HANDOFF_CONDITION
# ════════════════════════════════════════════════════════════

class EWBHandoffConditionCreate(BaseModel):
    ewb_handoff_id:       str = Field(..., description="FK → sia_ewb_handoff._id (NOT NULL)")
    condition_type:       Optional[str] = Field(None, max_length=100)
    discipline:           Optional[str] = Field(None, max_length=100)
    condition_description: Optional[str] = None
    required_action:      Optional[str] = None
    owner_user_id:        Optional[str] = Field(None, description="FK → users._id")
    status:               Optional[str] = Field(None, max_length=50)

class EWBHandoffConditionResponse(EWBHandoffConditionCreate):
    id: str
    created_at: datetime

@router.post("/sia/ewb-handoff-conditions", response_model=EWBHandoffConditionResponse,
             status_code=201, tags=["SIA - SEB & EWB Handoff"])
async def create_ewb_handoff_condition(data: EWBHandoffConditionCreate):
    await require(ewb_handoff_col, data.ewb_handoff_id, "EWB Handoff")
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ewb_cond_col.insert_one(doc)
    return ser(doc)

@router.get("/sia/ewb-handoffs/{handoff_id}/conditions",
            response_model=List[EWBHandoffConditionResponse],
            tags=["SIA - SEB & EWB Handoff"])
async def get_ewb_handoff_conditions(handoff_id: str):
    docs = await ewb_cond_col.find({"ewb_handoff_id": handoff_id}).to_list(1000)
    return [ser(d) for d in docs]
