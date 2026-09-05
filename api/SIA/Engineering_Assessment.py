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

ea_col          = db["sia_engineering_assessment"]
elec_col        = db["sia_electrical_assessment"]
civil_col       = db["sia_civil_assessment"]
struct_col      = db["sia_structural_assessment"]
mech_col        = db["sia_mechanical_assessment"]
water_col       = db["sia_water_pumping_assessment"]
scada_col       = db["sia_scada_communication_assessment"]
hse_col         = db["sia_hse_environment_assessment"]
industrial_col  = db["sia_industrial_assessment"]
finding_col     = db["sia_engineering_finding"]
gap_col         = db["sia_engineering_gap"]
review_col      = db["sia_engineering_review"]

router = APIRouter()

# ════════════════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════════════════

async def init_engineering_assessment_collections():
    await ea_col.create_index("sia_case_id")
    await ea_col.create_index("site_id")
    await ea_col.create_index("assessment_code")

    for col in [elec_col, civil_col, struct_col, mech_col,
                water_col, scada_col, hse_col, industrial_col,
                finding_col, gap_col, review_col]:
        await col.create_index("engineering_assessment_id")

    await finding_col.create_index("poi_id")
    await gap_col.create_index("owner_user_id")
    await review_col.create_index("reviewer_user_id")
    print("engineering_assessment collections initialized")


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def new_id() -> str:
    return str(uuid.uuid4())

def not_found(entity: str, eid: str):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{entity} '{eid}' not found"
    )

async def require_ea(ea_id: str):
    doc = await ea_col.find_one({"_id": ea_id})
    if not doc:
        not_found("Engineering Assessment", ea_id)
    return doc


# ════════════════════════════════════════════════════════════
# SIA_ENGINEERING_ASSESSMENT  (parent)
# ════════════════════════════════════════════════════════════

class EngineeringAssessmentCreate(BaseModel):
    sia_case_id:       str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_id:           str = Field(..., description="FK → sia_site._id (NOT NULL)")
    assessment_code:   str = Field(..., max_length=50)
    discipline:        str = Field(..., max_length=100)
    assessment_date:   Optional[str] = None          # YYYY-MM-DD string
    assessed_by:       Optional[str] = None          # FK → users._id
    reliability_status: Optional[str] = Field(None, max_length=50)
    status:            Optional[str] = Field(None, max_length=50)
    summary:           Optional[str] = None

class EngineeringAssessmentResponse(BaseModel):
    id: str
    sia_case_id:       str
    site_id:           str
    assessment_code:   str
    discipline:        str
    assessment_date:   Optional[str]
    assessed_by:       Optional[str]
    reliability_status: Optional[str]
    status:            Optional[str]
    summary:           Optional[str]
    created_at:        datetime

def _ea(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "sia_case_id": doc["sia_case_id"], "site_id": doc["site_id"],
        "assessment_code": doc["assessment_code"], "discipline": doc["discipline"],
        "assessment_date": doc.get("assessment_date"), "assessed_by": doc.get("assessed_by"),
        "reliability_status": doc.get("reliability_status"), "status": doc.get("status"),
        "summary": doc.get("summary"), "created_at": doc["created_at"],
    }

@router.post("/sia/engineering-assessments", response_model=EngineeringAssessmentResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_engineering_assessment(data: EngineeringAssessmentCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ea_col.insert_one(doc)
    return _ea(doc)

@router.get("/sia/engineering-assessments/{ea_id}", response_model=EngineeringAssessmentResponse,
            tags=["SIA - Engineering Assessment"])
async def get_engineering_assessment(ea_id: str):
    doc = await ea_col.find_one({"_id": ea_id})
    if not doc: not_found("Engineering Assessment", ea_id)
    return _ea(doc)

@router.get("/sia/cases/{case_id}/engineering-assessments",
            response_model=List[EngineeringAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_assessments_by_case(case_id: str):
    docs = await ea_col.find({"sia_case_id": case_id}).to_list(1000)
    return [_ea(d) for d in docs]

@router.get("/sia/sites/{site_id}/engineering-assessments",
            response_model=List[EngineeringAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_assessments_by_site(site_id: str):
    docs = await ea_col.find({"site_id": site_id}).to_list(1000)
    return [_ea(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_ELECTRICAL_ASSESSMENT
# ════════════════════════════════════════════════════════════

class ElectricalAssessmentCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    supply_type:          Optional[str] = Field(None, max_length=100)
    voltage:              Optional[float] = None
    phase:                Optional[str] = Field(None, max_length=50)
    frequency:            Optional[float] = None
    transformer_details:  Optional[str] = None
    switchboard_details:  Optional[str] = None
    protection_details:   Optional[str] = None
    connected_load:       Optional[float] = None
    peak_load:            Optional[float] = None
    utility_condition:    Optional[str] = Field(None, max_length=100)
    remarks:              Optional[str] = None

class ElectricalAssessmentResponse(ElectricalAssessmentCreate):
    id: str
    created_at: datetime

def _child(col_name: str):
    """Generic serializer for discipline child tables."""
    def _s(doc) -> dict:
        result = {k: doc.get(k) for k in doc if k != "_id"}
        result["id"] = str(doc["_id"])
        return result
    return _s

_elec = _child("elec")

@router.post("/sia/electrical-assessments", response_model=ElectricalAssessmentResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_electrical_assessment(data: ElectricalAssessmentCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await elec_col.insert_one(doc)
    return _elec(doc)

@router.get("/sia/engineering-assessments/{ea_id}/electrical",
            response_model=List[ElectricalAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_electrical_assessments(ea_id: str):
    docs = await elec_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_elec(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_CIVIL_ASSESSMENT
# ════════════════════════════════════════════════════════════

class CivilAssessmentCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    ground_condition:     Optional[str] = Field(None, max_length=100)
    foundation_condition: Optional[str] = Field(None, max_length=100)
    drainage_condition:   Optional[str] = Field(None, max_length=100)
    road_condition:       Optional[str] = Field(None, max_length=100)
    trench_requirement:   Optional[str] = None
    route_constraint:     Optional[str] = None
    erosion_risk:         Optional[str] = Field(None, max_length=50)
    flood_risk:           Optional[str] = Field(None, max_length=50)
    remarks:              Optional[str] = None

class CivilAssessmentResponse(CivilAssessmentCreate):
    id: str
    created_at: datetime

_civil = _child("civil")

@router.post("/sia/civil-assessments", response_model=CivilAssessmentResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_civil_assessment(data: CivilAssessmentCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await civil_col.insert_one(doc)
    return _civil(doc)

@router.get("/sia/engineering-assessments/{ea_id}/civil",
            response_model=List[CivilAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_civil_assessments(ea_id: str):
    docs = await civil_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_civil(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_STRUCTURAL_ASSESSMENT
# ════════════════════════════════════════════════════════════

class StructuralAssessmentCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    structure_type:       Optional[str] = Field(None, max_length=100)
    roof_type:            Optional[str] = Field(None, max_length=100)
    material_type:        Optional[str] = Field(None, max_length=100)
    structural_condition: Optional[str] = Field(None, max_length=100)
    roof_condition:       Optional[str] = Field(None, max_length=100)
    support_condition:    Optional[str] = Field(None, max_length=100)
    visible_damage:       Optional[str] = None
    loading_constraint:   Optional[str] = None
    remarks:              Optional[str] = None

class StructuralAssessmentResponse(StructuralAssessmentCreate):
    id: str
    created_at: datetime

_struct = _child("struct")

@router.post("/sia/structural-assessments", response_model=StructuralAssessmentResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_structural_assessment(data: StructuralAssessmentCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await struct_col.insert_one(doc)
    return _struct(doc)

@router.get("/sia/engineering-assessments/{ea_id}/structural",
            response_model=List[StructuralAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_structural_assessments(ea_id: str):
    docs = await struct_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_struct(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_MECHANICAL_ASSESSMENT
# ════════════════════════════════════════════════════════════

class MechanicalAssessmentCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    equipment_zone:         Optional[str] = Field(None, max_length=150)
    plant_condition:        Optional[str] = Field(None, max_length=100)
    ventilation_condition:  Optional[str] = Field(None, max_length=100)
    lifting_access:         Optional[str] = Field(None, max_length=100)
    maintenance_access:     Optional[str] = Field(None, max_length=100)
    pipework_condition:     Optional[str] = Field(None, max_length=100)
    route_constraint:       Optional[str] = None
    operational_constraint: Optional[str] = None
    remarks:                Optional[str] = None

class MechanicalAssessmentResponse(MechanicalAssessmentCreate):
    id: str
    created_at: datetime

_mech = _child("mech")

@router.post("/sia/mechanical-assessments", response_model=MechanicalAssessmentResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_mechanical_assessment(data: MechanicalAssessmentCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await mech_col.insert_one(doc)
    return _mech(doc)

@router.get("/sia/engineering-assessments/{ea_id}/mechanical",
            response_model=List[MechanicalAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_mechanical_assessments(ea_id: str):
    docs = await mech_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_mech(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_WATER_PUMPING_ASSESSMENT
# ════════════════════════════════════════════════════════════

class WaterPumpingAssessmentCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    water_source_type:    Optional[str] = Field(None, max_length=100)
    daily_water_demand:   Optional[float] = None
    source_water_level:   Optional[float] = None
    delivery_elevation:   Optional[float] = None
    route_length:         Optional[float] = None
    pipe_diameter:        Optional[float] = None
    pipe_material:        Optional[str] = Field(None, max_length=100)
    pump_make_model:      Optional[str] = Field(None, max_length=150)
    pump_power_kw:        Optional[float] = None
    pump_condition:       Optional[str] = Field(None, max_length=100)
    tank_capacity:        Optional[float] = None
    required_pressure:    Optional[float] = None
    controller_type:      Optional[str] = Field(None, max_length=100)
    monitoring_available: Optional[bool] = None
    remarks:              Optional[str] = None

class WaterPumpingAssessmentResponse(WaterPumpingAssessmentCreate):
    id: str
    created_at: datetime

_water = _child("water")

@router.post("/sia/water-pumping-assessments", response_model=WaterPumpingAssessmentResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_water_pumping_assessment(data: WaterPumpingAssessmentCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await water_col.insert_one(doc)
    return _water(doc)

@router.get("/sia/engineering-assessments/{ea_id}/water-pumping",
            response_model=List[WaterPumpingAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_water_pumping_assessments(ea_id: str):
    docs = await water_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_water(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SCADA_COMMUNICATION_ASSESSMENT
# ════════════════════════════════════════════════════════════

class ScadaCommunicationAssessmentCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    control_system_type:   Optional[str] = Field(None, max_length=100)
    scada_available:       Optional[bool] = None
    communication_type:    Optional[str] = Field(None, max_length=100)
    network_available:     Optional[bool] = None
    telemetry_available:   Optional[bool] = None
    remote_monitoring:     Optional[bool] = None
    sensor_details:        Optional[str] = None
    protocol_details:      Optional[str] = Field(None, max_length=100)
    connectivity_condition: Optional[str] = Field(None, max_length=100)
    remarks:               Optional[str] = None

class ScadaCommunicationAssessmentResponse(ScadaCommunicationAssessmentCreate):
    id: str
    created_at: datetime

_scada = _child("scada")

@router.post("/sia/scada-assessments", response_model=ScadaCommunicationAssessmentResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_scada_assessment(data: ScadaCommunicationAssessmentCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await scada_col.insert_one(doc)
    return _scada(doc)

@router.get("/sia/engineering-assessments/{ea_id}/scada",
            response_model=List[ScadaCommunicationAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_scada_assessments(ea_id: str):
    docs = await scada_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_scada(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_HSE_ENVIRONMENT_ASSESSMENT
# ════════════════════════════════════════════════════════════

class HseEnvironmentAssessmentCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    environmental_condition:   Optional[str] = None
    hazard_level:              Optional[str] = Field(None, max_length=50)
    fire_risk:                 Optional[str] = Field(None, max_length=50)
    emergency_access:          Optional[str] = Field(None, max_length=100)
    electrical_safety:         Optional[str] = Field(None, max_length=100)
    roof_safety:               Optional[str] = Field(None, max_length=100)
    restricted_area:           Optional[bool] = None
    environmental_constraint:  Optional[str] = None
    hse_constraint:            Optional[str] = None
    remarks:                   Optional[str] = None

class HseEnvironmentAssessmentResponse(HseEnvironmentAssessmentCreate):
    id: str
    created_at: datetime

_hse = _child("hse")

@router.post("/sia/hse-assessments", response_model=HseEnvironmentAssessmentResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_hse_assessment(data: HseEnvironmentAssessmentCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await hse_col.insert_one(doc)
    return _hse(doc)

@router.get("/sia/engineering-assessments/{ea_id}/hse",
            response_model=List[HseEnvironmentAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_hse_assessments(ea_id: str):
    docs = await hse_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_hse(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_INDUSTRIAL_ASSESSMENT
# ════════════════════════════════════════════════════════════

class IndustrialAssessmentCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    equipment_name:     Optional[str] = Field(None, max_length=150)
    process_type:       Optional[str] = Field(None, max_length=100)
    operating_hours:    Optional[float] = None
    duty_cycle:         Optional[float] = None
    start_frequency:    Optional[str] = Field(None, max_length=100)
    diversity_factor:   Optional[float] = None
    throughput:         Optional[str] = Field(None, max_length=100)
    criticality:        Optional[str] = Field(None, max_length=50)
    operating_parameters: Optional[str] = None
    remarks:            Optional[str] = None

class IndustrialAssessmentResponse(IndustrialAssessmentCreate):
    id: str
    created_at: datetime

_industrial = _child("industrial")

@router.post("/sia/industrial-assessments", response_model=IndustrialAssessmentResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_industrial_assessment(data: IndustrialAssessmentCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await industrial_col.insert_one(doc)
    return _industrial(doc)

@router.get("/sia/engineering-assessments/{ea_id}/industrial",
            response_model=List[IndustrialAssessmentResponse],
            tags=["SIA - Engineering Assessment"])
async def get_industrial_assessments(ea_id: str):
    docs = await industrial_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_industrial(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_ENGINEERING_FINDING
# ════════════════════════════════════════════════════════════

class EngineeringFindingCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    poi_id:             Optional[str] = None
    finding_code:       Optional[str] = Field(None, max_length=50)
    finding_type:       Optional[str] = Field(None, max_length=100)
    description:        Optional[str] = None
    severity:           Optional[str] = Field(None, max_length=50)
    reliability_status: Optional[str] = Field(None, max_length=50)
    constraint:         Optional[str] = None
    recommendation:     Optional[str] = None
    status:             Optional[str] = Field(None, max_length=50)

class EngineeringFindingResponse(EngineeringFindingCreate):
    id: str
    created_at: datetime

_finding = _child("finding")

@router.post("/sia/engineering-findings", response_model=EngineeringFindingResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_engineering_finding(data: EngineeringFindingCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await finding_col.insert_one(doc)
    return _finding(doc)

@router.get("/sia/engineering-assessments/{ea_id}/findings",
            response_model=List[EngineeringFindingResponse],
            tags=["SIA - Engineering Assessment"])
async def get_findings(ea_id: str):
    docs = await finding_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_finding(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_ENGINEERING_GAP
# ════════════════════════════════════════════════════════════

class EngineeringGapCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    gap_code:       Optional[str] = Field(None, max_length=50)
    gap_type:       Optional[str] = Field(None, max_length=100)
    description:    Optional[str] = None
    impact:         Optional[str] = None
    priority:       Optional[str] = Field(None, max_length=50)
    owner_user_id:  Optional[str] = None
    target_date:    Optional[str] = None          # YYYY-MM-DD string
    status:         Optional[str] = Field(None, max_length=50)

class EngineeringGapResponse(EngineeringGapCreate):
    id: str
    created_at: datetime

_gap = _child("gap")

@router.post("/sia/engineering-gaps", response_model=EngineeringGapResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_engineering_gap(data: EngineeringGapCreate):
    await require_ea(data.engineering_assessment_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await gap_col.insert_one(doc)
    return _gap(doc)

@router.get("/sia/engineering-assessments/{ea_id}/gaps",
            response_model=List[EngineeringGapResponse],
            tags=["SIA - Engineering Assessment"])
async def get_gaps(ea_id: str):
    docs = await gap_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_gap(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_ENGINEERING_REVIEW
# ════════════════════════════════════════════════════════════

class EngineeringReviewCreate(BaseModel):
    engineering_assessment_id: str = Field(...)
    reviewer_user_id:    Optional[str] = None
    review_status:       Optional[str] = Field(None, max_length=50)
    review_comment:      Optional[str] = None
    verification_status: Optional[str] = Field(None, max_length=50)
    reviewed_at:         Optional[str] = None      # datetime string

class EngineeringReviewResponse(EngineeringReviewCreate):
    id: str
    created_at: datetime

_review = _child("review")

@router.post("/sia/engineering-reviews", response_model=EngineeringReviewResponse,
             status_code=201, tags=["SIA - Engineering Assessment"])
async def create_engineering_review(data: EngineeringReviewCreate):
    await require_ea(data.engineering_assessment_id)
    # auto-fill reviewer from payload; stamp reviewed_at if not provided
    payload = data.model_dump()
    if not payload.get("reviewed_at"):
        payload["reviewed_at"] = datetime.utcnow().isoformat()
    doc = {"_id": new_id(), **payload, "created_at": datetime.utcnow()}
    await review_col.insert_one(doc)
    return _review(doc)

@router.get("/sia/engineering-assessments/{ea_id}/reviews",
            response_model=List[EngineeringReviewResponse],
            tags=["SIA - Engineering Assessment"])
async def get_reviews(ea_id: str):
    docs = await review_col.find({"engineering_assessment_id": ea_id}).to_list(1000)
    return [_review(d) for d in docs]
