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

site_col          = db["sia_site"]
building_col      = db["sia_building"]
room_area_col     = db["sia_room_area"]
poi_col           = db["sia_poi"]
survey_visit_col  = db["sia_survey_visit"]
survey_team_col   = db["sia_survey_team"]
site_access_col   = db["sia_site_access"]
site_safety_col   = db["sia_site_safety"]
survey_req_col    = db["sia_survey_requirement"]
survey_inst_col   = db["sia_survey_instrument"]

router = APIRouter()


# ════════════════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════════════════

async def init_site_survey_collections():
    await site_col.create_index("sia_case_id")
    await site_col.create_index("site_code")

    await building_col.create_index("site_id")
    await building_col.create_index("building_code")

    await room_area_col.create_index("building_id")
    await room_area_col.create_index("site_id")

    await poi_col.create_index("site_id")
    await poi_col.create_index("room_area_id")

    await survey_visit_col.create_index("site_id")
    await survey_visit_col.create_index("visit_code")

    await survey_team_col.create_index("survey_visit_id")
    await survey_team_col.create_index("user_id")

    await site_access_col.create_index("site_id")
    await site_safety_col.create_index("site_id")

    await survey_req_col.create_index("survey_visit_id")
    await survey_req_col.create_index("assessment_pack_id")

    await survey_inst_col.create_index("survey_visit_id")

    print("site_survey collections initialized")


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def new_id() -> str:
    return str(uuid.uuid4())

def not_found(entity: str, id: str):
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{entity} '{id}' not found"
    )


# ════════════════════════════════════════════════════════════
# SIA_SITE
# ════════════════════════════════════════════════════════════

class SitCreate(BaseModel):
    sia_case_id:   str = Field(..., description="FK → sia_case._id (NOT NULL)")
    site_code:     str = Field(..., max_length=50)
    site_name:     Optional[str] = Field(None, max_length=255)
    site_type:     Optional[str] = Field(None, max_length=100)
    address:       Optional[str] = None
    contact_name:  Optional[str] = Field(None, max_length=150)
    contact_phone: Optional[str] = Field(None, max_length=50)
    latitude:      Optional[float] = None
    longitude:     Optional[float] = None
    status:        Optional[str] = Field(None, max_length=50)

class SiteResponse(BaseModel):
    id: str
    sia_case_id:   str
    site_code:     str
    site_name:     Optional[str]
    site_type:     Optional[str]
    address:       Optional[str]
    contact_name:  Optional[str]
    contact_phone: Optional[str]
    latitude:      Optional[float]
    longitude:     Optional[float]
    status:        Optional[str]
    created_at:    datetime

def _site(doc) -> dict:
    return {
        "id": str(doc["_id"]), "sia_case_id": doc["sia_case_id"],
        "site_code": doc["site_code"], "site_name": doc.get("site_name"),
        "site_type": doc.get("site_type"), "address": doc.get("address"),
        "contact_name": doc.get("contact_name"), "contact_phone": doc.get("contact_phone"),
        "latitude": doc.get("latitude"), "longitude": doc.get("longitude"),
        "status": doc.get("status"), "created_at": doc["created_at"],
    }

@router.post("/sia/sites", response_model=SiteResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_site(data: SitCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await site_col.insert_one(doc)
    return _site(doc)

@router.get("/sia/sites/{site_id}", response_model=SiteResponse, tags=["SIA - Sites & Survey"])
async def get_site(site_id: str):
    doc = await site_col.find_one({"_id": site_id})
    if not doc: not_found("Site", site_id)
    return _site(doc)

@router.get("/sia/cases/{case_id}/sites", response_model=List[SiteResponse], tags=["SIA - Sites & Survey"])
async def get_sites_by_case(case_id: str):
    docs = await site_col.find({"sia_case_id": case_id}).to_list(1000)
    return [_site(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_BUILDING
# ════════════════════════════════════════════════════════════

class BuildingCreate(BaseModel):
    site_id:        str = Field(..., description="FK → sia_site._id (NOT NULL)")
    building_code:  Optional[str] = Field(None, max_length=50)
    building_name:  Optional[str] = Field(None, max_length=150)
    building_type:  Optional[str] = Field(None, max_length=100)
    floor_count:    Optional[int] = None
    description:    Optional[str] = None

class BuildingResponse(BaseModel):
    id: str
    site_id:       str
    building_code: Optional[str]
    building_name: Optional[str]
    building_type: Optional[str]
    floor_count:   Optional[int]
    description:   Optional[str]
    created_at:    datetime

def _building(doc) -> dict:
    return {
        "id": str(doc["_id"]), "site_id": doc["site_id"],
        "building_code": doc.get("building_code"), "building_name": doc.get("building_name"),
        "building_type": doc.get("building_type"), "floor_count": doc.get("floor_count"),
        "description": doc.get("description"), "created_at": doc["created_at"],
    }

@router.post("/sia/buildings", response_model=BuildingResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_building(data: BuildingCreate):
    if not await site_col.find_one({"_id": data.site_id}):
        not_found("Site", data.site_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await building_col.insert_one(doc)
    return _building(doc)

@router.get("/sia/buildings/{building_id}", response_model=BuildingResponse, tags=["SIA - Sites & Survey"])
async def get_building(building_id: str):
    doc = await building_col.find_one({"_id": building_id})
    if not doc: not_found("Building", building_id)
    return _building(doc)

@router.get("/sia/sites/{site_id}/buildings", response_model=List[BuildingResponse], tags=["SIA - Sites & Survey"])
async def get_buildings_by_site(site_id: str):
    docs = await building_col.find({"site_id": site_id}).to_list(1000)
    return [_building(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_ROOM_AREA
# ════════════════════════════════════════════════════════════

class RoomAreaCreate(BaseModel):
    building_id: Optional[str] = Field(None, description="FK → sia_building._id")
    site_id:     str = Field(..., description="FK → sia_site._id (NOT NULL)")
    area_code:   Optional[str] = Field(None, max_length=50)
    area_name:   Optional[str] = Field(None, max_length=150)
    area_type:   Optional[str] = Field(None, max_length=100)
    floor_level: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None

class RoomAreaResponse(BaseModel):
    id: str
    building_id: Optional[str]
    site_id:     str
    area_code:   Optional[str]
    area_name:   Optional[str]
    area_type:   Optional[str]
    floor_level: Optional[str]
    description: Optional[str]
    created_at:  datetime

def _room_area(doc) -> dict:
    return {
        "id": str(doc["_id"]), "building_id": doc.get("building_id"), "site_id": doc["site_id"],
        "area_code": doc.get("area_code"), "area_name": doc.get("area_name"),
        "area_type": doc.get("area_type"), "floor_level": doc.get("floor_level"),
        "description": doc.get("description"), "created_at": doc["created_at"],
    }

@router.post("/sia/room-areas", response_model=RoomAreaResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_room_area(data: RoomAreaCreate):
    if not await site_col.find_one({"_id": data.site_id}):
        not_found("Site", data.site_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await room_area_col.insert_one(doc)
    return _room_area(doc)

@router.get("/sia/room-areas/{area_id}", response_model=RoomAreaResponse, tags=["SIA - Sites & Survey"])
async def get_room_area(area_id: str):
    doc = await room_area_col.find_one({"_id": area_id})
    if not doc: not_found("Room/Area", area_id)
    return _room_area(doc)

@router.get("/sia/buildings/{building_id}/room-areas", response_model=List[RoomAreaResponse], tags=["SIA - Sites & Survey"])
async def get_room_areas_by_building(building_id: str):
    docs = await room_area_col.find({"building_id": building_id}).to_list(1000)
    return [_room_area(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_POI
# ════════════════════════════════════════════════════════════

class POICreate(BaseModel):
    site_id:     str = Field(..., description="FK → sia_site._id (NOT NULL)")
    room_area_id: Optional[str] = Field(None, description="FK → sia_room_area._id")
    poi_code:    Optional[str] = Field(None, max_length=50)
    poi_name:    Optional[str] = Field(None, max_length=150)
    poi_type:    Optional[str] = Field(None, max_length=50)
    category:    Optional[str] = Field(None, max_length=100)
    latitude:    Optional[float] = None
    longitude:   Optional[float] = None
    description: Optional[str] = None

class POIResponse(BaseModel):
    id: str
    site_id:      str
    room_area_id: Optional[str]
    poi_code:     Optional[str]
    poi_name:     Optional[str]
    poi_type:     Optional[str]
    category:     Optional[str]
    latitude:     Optional[float]
    longitude:    Optional[float]
    description:  Optional[str]
    created_at:   datetime

def _poi(doc) -> dict:
    return {
        "id": str(doc["_id"]), "site_id": doc["site_id"], "room_area_id": doc.get("room_area_id"),
        "poi_code": doc.get("poi_code"), "poi_name": doc.get("poi_name"),
        "poi_type": doc.get("poi_type"), "category": doc.get("category"),
        "latitude": doc.get("latitude"), "longitude": doc.get("longitude"),
        "description": doc.get("description"), "created_at": doc["created_at"],
    }

@router.post("/sia/pois", response_model=POIResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_poi(data: POICreate):
    if not await site_col.find_one({"_id": data.site_id}):
        not_found("Site", data.site_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await poi_col.insert_one(doc)
    return _poi(doc)

@router.get("/sia/pois/{poi_id}", response_model=POIResponse, tags=["SIA - Sites & Survey"])
async def get_poi(poi_id: str):
    doc = await poi_col.find_one({"_id": poi_id})
    if not doc: not_found("POI", poi_id)
    return _poi(doc)

@router.get("/sia/sites/{site_id}/pois", response_model=List[POIResponse], tags=["SIA - Sites & Survey"])
async def get_pois_by_site(site_id: str):
    docs = await poi_col.find({"site_id": site_id}).to_list(1000)
    return [_poi(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SURVEY_VISIT
# ════════════════════════════════════════════════════════════

class SurveyVisitCreate(BaseModel):
    site_id:            str = Field(..., description="FK → sia_site._id (NOT NULL)")
    visit_code:         Optional[str] = Field(None, max_length=50)
    visit_type:         Optional[str] = Field(None, max_length=100)
    purpose:            Optional[str] = Field(None, max_length=255)
    planned_date:       Optional[str] = Field(None, description="Date string YYYY-MM-DD")
    planned_start_time: Optional[str] = Field(None, description="Time string HH:MM")
    planned_end_time:   Optional[str] = Field(None, description="Time string HH:MM")
    actual_start:       Optional[str] = Field(None, description="Datetime string")
    actual_end:         Optional[str] = Field(None, description="Datetime string")
    status:             Optional[str] = Field(None, max_length=50)

class SurveyVisitResponse(BaseModel):
    id: str
    site_id:            str
    visit_code:         Optional[str]
    visit_type:         Optional[str]
    purpose:            Optional[str]
    planned_date:       Optional[str]
    planned_start_time: Optional[str]
    planned_end_time:   Optional[str]
    actual_start:       Optional[str]
    actual_end:         Optional[str]
    status:             Optional[str]
    created_at:         datetime

def _visit(doc) -> dict:
    return {
        "id": str(doc["_id"]), "site_id": doc["site_id"],
        "visit_code": doc.get("visit_code"), "visit_type": doc.get("visit_type"),
        "purpose": doc.get("purpose"), "planned_date": doc.get("planned_date"),
        "planned_start_time": doc.get("planned_start_time"), "planned_end_time": doc.get("planned_end_time"),
        "actual_start": doc.get("actual_start"), "actual_end": doc.get("actual_end"),
        "status": doc.get("status"), "created_at": doc["created_at"],
    }

@router.post("/sia/survey-visits", response_model=SurveyVisitResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_survey_visit(data: SurveyVisitCreate):
    if not await site_col.find_one({"_id": data.site_id}):
        not_found("Site", data.site_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await survey_visit_col.insert_one(doc)
    return _visit(doc)

@router.get("/sia/survey-visits/{visit_id}", response_model=SurveyVisitResponse, tags=["SIA - Sites & Survey"])
async def get_survey_visit(visit_id: str):
    doc = await survey_visit_col.find_one({"_id": visit_id})
    if not doc: not_found("Survey Visit", visit_id)
    return _visit(doc)

@router.get("/sia/sites/{site_id}/survey-visits", response_model=List[SurveyVisitResponse], tags=["SIA - Sites & Survey"])
async def get_visits_by_site(site_id: str):
    docs = await survey_visit_col.find({"site_id": site_id}).to_list(1000)
    return [_visit(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SURVEY_TEAM
# ════════════════════════════════════════════════════════════

class SurveyTeamCreate(BaseModel):
    survey_visit_id: str = Field(..., description="FK → sia_survey_visit._id (NOT NULL)")
    user_id:         Optional[str] = Field(None, description="FK → users._id")
    team_role:       Optional[str] = Field(None, max_length=100)
    is_lead:         Optional[bool] = False

class SurveyTeamResponse(BaseModel):
    id: str
    survey_visit_id: str
    user_id:         str
    team_role:       Optional[str]
    is_lead:         bool
    created_at:      datetime

def _team(doc) -> dict:
    return {
        "id": str(doc["_id"]), "survey_visit_id": doc["survey_visit_id"],
        "user_id": doc["user_id"], "team_role": doc.get("team_role"),
        "is_lead": doc.get("is_lead", False), "created_at": doc["created_at"],
    }

@router.post("/sia/survey-team", response_model=SurveyTeamResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_survey_team_member(data: SurveyTeamCreate):
    if not await survey_visit_col.find_one({"_id": data.survey_visit_id}):
        not_found("Survey Visit", data.survey_visit_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await survey_team_col.insert_one(doc)
    return _team(doc)

@router.get("/sia/survey-visits/{visit_id}/team", response_model=List[SurveyTeamResponse], tags=["SIA - Sites & Survey"])
async def get_team_by_visit(visit_id: str):
    docs = await survey_team_col.find({"survey_visit_id": visit_id}).to_list(1000)
    return [_team(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SITE_ACCESS
# ════════════════════════════════════════════════════════════

class SiteAccessCreate(BaseModel):
    site_id:              str = Field(..., description="FK → sia_site._id (NOT NULL)")
    access_type:          Optional[str] = Field(None, max_length=100)
    road_condition:       Optional[str] = Field(None, max_length=100)
    transport_method:     Optional[str] = Field(None, max_length=100)
    entry_permission:     Optional[bool] = None
    working_hours:        Optional[str] = Field(None, max_length=100)
    access_restriction:   Optional[str] = None
    logistics_notes:      Optional[str] = None

class SiteAccessResponse(BaseModel):
    id: str
    site_id:            str
    access_type:        Optional[str]
    road_condition:     Optional[str]
    transport_method:   Optional[str]
    entry_permission:   Optional[bool]
    working_hours:      Optional[str]
    access_restriction: Optional[str]
    logistics_notes:    Optional[str]
    created_at:         datetime

def _access(doc) -> dict:
    return {
        "id": str(doc["_id"]), "site_id": doc["site_id"],
        "access_type": doc.get("access_type"), "road_condition": doc.get("road_condition"),
        "transport_method": doc.get("transport_method"), "entry_permission": doc.get("entry_permission"),
        "working_hours": doc.get("working_hours"), "access_restriction": doc.get("access_restriction"),
        "logistics_notes": doc.get("logistics_notes"), "created_at": doc["created_at"],
    }

@router.post("/sia/site-access", response_model=SiteAccessResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_site_access(data: SiteAccessCreate):
    if not await site_col.find_one({"_id": data.site_id}):
        not_found("Site", data.site_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await site_access_col.insert_one(doc)
    return _access(doc)

@router.get("/sia/sites/{site_id}/access", response_model=List[SiteAccessResponse], tags=["SIA - Sites & Survey"])
async def get_site_access(site_id: str):
    docs = await site_access_col.find({"site_id": site_id}).to_list(1000)
    return [_access(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SITE_SAFETY
# ════════════════════════════════════════════════════════════

class SiteSafetyCreate(BaseModel):
    site_id:           str = Field(..., description="FK → sia_site._id (NOT NULL)")
    hazard_type:       Optional[str] = Field(None, max_length=100)
    risk_level:        Optional[str] = Field(None, max_length=50)
    description:       Optional[str] = None
    ppe_required:      Optional[str] = None
    restricted_area:   Optional[bool] = False
    emergency_contact: Optional[str] = Field(None, max_length=150)
    control_action:    Optional[str] = None

class SiteSafetyResponse(BaseModel):
    id: str
    site_id:           str
    hazard_type:       Optional[str]
    risk_level:        Optional[str]
    description:       Optional[str]
    ppe_required:      Optional[str]
    restricted_area:   Optional[bool]
    emergency_contact: Optional[str]
    control_action:    Optional[str]
    created_at:        datetime

def _safety(doc) -> dict:
    return {
        "id": str(doc["_id"]), "site_id": doc["site_id"],
        "hazard_type": doc.get("hazard_type"), "risk_level": doc.get("risk_level"),
        "description": doc.get("description"), "ppe_required": doc.get("ppe_required"),
        "restricted_area": doc.get("restricted_area", False),
        "emergency_contact": doc.get("emergency_contact"),
        "control_action": doc.get("control_action"), "created_at": doc["created_at"],
    }

@router.post("/sia/site-safety", response_model=SiteSafetyResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_site_safety(data: SiteSafetyCreate):
    if not await site_col.find_one({"_id": data.site_id}):
        not_found("Site", data.site_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await site_safety_col.insert_one(doc)
    return _safety(doc)

@router.get("/sia/sites/{site_id}/safety", response_model=List[SiteSafetyResponse], tags=["SIA - Sites & Survey"])
async def get_site_safety(site_id: str):
    docs = await site_safety_col.find({"site_id": site_id}).to_list(1000)
    return [_safety(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SURVEY_REQUIREMENT
# ════════════════════════════════════════════════════════════

class SurveyRequirementCreate(BaseModel):
    survey_visit_id:    str = Field(..., description="FK → sia_survey_visit._id (NOT NULL)")
    assessment_pack_id: Optional[str] = Field(None, description="FK → sia_assessment_pack._id")
    requirement_name:   Optional[str] = Field(None, max_length=255)
    requirement_type:   Optional[str] = Field(None, max_length=100)
    is_mandatory:       Optional[bool] = False
    status:             Optional[str] = Field(None, max_length=50)
    notes:              Optional[str] = None

class SurveyRequirementResponse(BaseModel):
    id: str
    survey_visit_id:    str
    assessment_pack_id: Optional[str]
    requirement_name:   Optional[str]
    requirement_type:   Optional[str]
    is_mandatory:       Optional[bool]
    status:             Optional[str]
    notes:              Optional[str]
    created_at:         datetime

def _req(doc) -> dict:
    return {
        "id": str(doc["_id"]), "survey_visit_id": doc["survey_visit_id"],
        "assessment_pack_id": doc.get("assessment_pack_id"),
        "requirement_name": doc.get("requirement_name"), "requirement_type": doc.get("requirement_type"),
        "is_mandatory": doc.get("is_mandatory", False), "status": doc.get("status"),
        "notes": doc.get("notes"), "created_at": doc["created_at"],
    }

@router.post("/sia/survey-requirements", response_model=SurveyRequirementResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_survey_requirement(data: SurveyRequirementCreate):
    if not await survey_visit_col.find_one({"_id": data.survey_visit_id}):
        not_found("Survey Visit", data.survey_visit_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await survey_req_col.insert_one(doc)
    return _req(doc)

@router.get("/sia/survey-visits/{visit_id}/requirements", response_model=List[SurveyRequirementResponse], tags=["SIA - Sites & Survey"])
async def get_requirements_by_visit(visit_id: str):
    docs = await survey_req_col.find({"survey_visit_id": visit_id}).to_list(1000)
    return [_req(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_SURVEY_INSTRUMENT
# ════════════════════════════════════════════════════════════

class SurveyInstrumentCreate(BaseModel):
    survey_visit_id:    str = Field(..., description="FK → sia_survey_visit._id (NOT NULL)")
    instrument_name:    Optional[str] = Field(None, max_length=150)
    instrument_type:    Optional[str] = Field(None, max_length=100)
    serial_number:      Optional[str] = Field(None, max_length=100)
    calibration_status: Optional[str] = Field(None, max_length=50)
    required:           Optional[bool] = False

class SurveyInstrumentResponse(BaseModel):
    id: str
    survey_visit_id:    str
    instrument_name:    Optional[str]
    instrument_type:    Optional[str]
    serial_number:      Optional[str]
    calibration_status: Optional[str]
    required:           Optional[bool]
    created_at:         datetime

def _instrument(doc) -> dict:
    return {
        "id": str(doc["_id"]), "survey_visit_id": doc["survey_visit_id"],
        "instrument_name": doc.get("instrument_name"), "instrument_type": doc.get("instrument_type"),
        "serial_number": doc.get("serial_number"), "calibration_status": doc.get("calibration_status"),
        "required": doc.get("required", False), "created_at": doc["created_at"],
    }

@router.post("/sia/survey-instruments", response_model=SurveyInstrumentResponse, status_code=201, tags=["SIA - Sites & Survey"])
async def create_survey_instrument(data: SurveyInstrumentCreate):
    if not await survey_visit_col.find_one({"_id": data.survey_visit_id}):
        not_found("Survey Visit", data.survey_visit_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await survey_inst_col.insert_one(doc)
    return _instrument(doc)

@router.get("/sia/survey-visits/{visit_id}/instruments", response_model=List[SurveyInstrumentResponse], tags=["SIA - Sites & Survey"])
async def get_instruments_by_visit(visit_id: str):
    docs = await survey_inst_col.find({"survey_visit_id": visit_id}).to_list(1000)
    return [_instrument(d) for d in docs]
