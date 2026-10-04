"""SIA Drone Module - Drone survey missions, operators, platforms, and data capture."""
from .scope import SIAScope, apply_scope
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

# Drone Collections
mission_col       = db["sia_drone_mission"]
operator_col      = db["sia_drone_operator"]
platform_col      = db["sia_drone_platform"]
capture_plan_col  = db["sia_drone_capture_plan"]
gcp_col           = db["sia_ground_control_point"]
field_cond_col    = db["sia_drone_field_condition"]
raw_data_col      = db["sia_drone_raw_data"]
quality_col       = db["sia_drone_quality_check"]
derived_col       = db["sia_drone_derived_product"]

router = APIRouter()

# ════════════════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════════════════

async def init_drone_collections():
    """Initialize indexes for drone collections."""
    await mission_col.create_index("sia_case_id")
    await mission_col.create_index("site_id")
    await mission_col.create_index("survey_visit_id")
    await mission_col.create_index("mission_code")

    for col in [operator_col, platform_col, capture_plan_col,
                gcp_col, field_cond_col, raw_data_col,
                quality_col, derived_col]:
        await col.create_index("drone_mission_id")
        await col.create_index("sia_case_id")
        await col.create_index("site_id")

    await operator_col.create_index("user_id")
    await quality_col.create_index("checked_by")

    print("✓ Drone collections initialized")

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

async def require_mission(mid: str):
    doc = await mission_col.find_one({"_id": mid})
    if not doc:
        not_found("Drone Mission", mid)
    return doc

def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to response format."""
    result = {k: doc.get(k) for k in doc if k != "_id"}
    result["id"] = str(doc["_id"])
    return result


# ════════════════════════════════════════════════════════════
# SIA_DRONE_MISSION
# ════════════════════════════════════════════════════════════

class DroneMissionCreate(SIAScope):
    """Create drone mission - sia_case_id and site_id MUST be provided from frontend."""
    survey_visit_id:    Optional[str] = Field(None, description="FK → sia_survey_visit._id")
    mission_code:       str = Field(..., max_length=50, description="Unique mission identifier")
    mission_purpose:    Optional[str] = Field(None, max_length=255, description="Purpose of drone mission")
    target_discipline:  Optional[str] = Field(None, max_length=100, description="ELECTRICAL | CIVIL | STRUCTURAL | MECHANICAL")
    planned_date:       Optional[str] = Field(None, description="YYYY-MM-DD")
    actual_date:        Optional[str] = Field(None, description="YYYY-MM-DD")
    mission_status:     Optional[str] = Field("PLANNED", max_length=50, description="PLANNED | IN_PROGRESS | COMPLETED | CANCELLED")
    remarks:            Optional[str] = Field(None, description="Additional notes")

class DroneMissionResponse(DroneMissionCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-missions", response_model=DroneMissionResponse,
             status_code=201, tags=["SIA - Drone"])
async def create_drone_mission(data: DroneMissionCreate):
    """Create a new drone mission. Requires sia_case_id and site_id from frontend."""
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_drone_mission")
    await mission_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/drone-missions/{mission_id}", response_model=DroneMissionResponse,
            tags=["SIA - Drone"])
async def get_drone_mission(mission_id: str):
    """Get a specific drone mission by ID."""
    doc = await mission_col.find_one({"_id": mission_id})
    if not doc: 
        not_found("Drone Mission", mission_id)
    return serialize_doc(doc)

@router.get("/sia/sites/{site_id}/drone-missions",
            response_model=List[DroneMissionResponse],
            tags=["SIA - Drone"])
async def get_missions_by_site(site_id: str):
    """Get all drone missions for a specific site."""
    docs = await mission_col.find({"site_id": site_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]

@router.get("/sia/cases/{case_id}/drone-missions",
            response_model=List[DroneMissionResponse],
            tags=["SIA - Drone"])
async def get_missions_by_case(case_id: str):
    """Get all drone missions for a specific SIA case."""
    docs = await mission_col.find({"sia_case_id": case_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_OPERATOR
# ════════════════════════════════════════════════════════════

class DroneOperatorCreate(SIAScope):
    """Drone operator assignment - sia_case_id and site_id inherited from mission or provided."""
    drone_mission_id:   str = Field(..., description="FK → sia_drone_mission._id (NOT NULL)")
    user_id:            Optional[str] = Field(None, description="FK → users._id")
    competency_ref:     Optional[str] = Field(None, max_length=100, description="License/competency reference")
    permission_ref:     Optional[str] = Field(None, max_length=100, description="Flight permission reference")
    regulatory_ref:     Optional[str] = Field(None, max_length=100, description="Regulatory approval reference")
    restriction_notes:  Optional[str] = Field(None, description="Flight restrictions or limitations")

class DroneOperatorResponse(DroneOperatorCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-operators", response_model=DroneOperatorResponse,
             status_code=201, tags=["SIA - Drone"])
async def create_drone_operator(data: DroneOperatorCreate):
    """Assign operator to a drone mission. Scope inherited from mission."""
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_drone_operator")
    await operator_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/drone-missions/{mission_id}/operators",
            response_model=List[DroneOperatorResponse],
            tags=["SIA - Drone"])
async def get_operators(mission_id: str):
    """Get all operators for a specific drone mission."""
    docs = await operator_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_PLATFORM
# ════════════════════════════════════════════════════════════

class DronePlatformCreate(SIAScope):
    """Drone hardware specification - sia_case_id and site_id inherited from mission or provided."""
    drone_mission_id:       str = Field(..., description="FK → sia_drone_mission._id")
    drone_make:             Optional[str] = Field(None, max_length=100, description="Manufacturer (e.g., DJI, Parrot)")
    drone_model:            Optional[str] = Field(None, max_length=100, description="Model name")
    serial_number:          Optional[str] = Field(None, max_length=100, description="Device serial number")
    sensor_type:            Optional[str] = Field(None, max_length=100, description="RGB | MULTISPECTRAL | THERMAL | LIDAR")
    camera_model:           Optional[str] = Field(None, max_length=100, description="Camera/sensor model")
    firmware_version:       Optional[str] = Field(None, max_length=50, description="Firmware version")
    rtk_ppk_capable:        Optional[bool] = Field(None, description="RTK/PPK positioning capable")
    thermal_capable:        Optional[bool] = Field(None, description="Thermal imaging capable")
    multispectral_capable:  Optional[bool] = Field(None, description="Multispectral imaging capable")

class DronePlatformResponse(DronePlatformCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-platforms", response_model=DronePlatformResponse,
             status_code=201, tags=["SIA - Drone"])
async def create_drone_platform(data: DronePlatformCreate):
    """Register drone platform/hardware for a mission. Scope inherited from mission."""
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_drone_platform")
    await platform_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/drone-missions/{mission_id}/platforms",
            response_model=List[DronePlatformResponse],
            tags=["SIA - Drone"])
async def get_platforms(mission_id: str):
    """Get all platforms used in a drone mission."""
    docs = await platform_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_CAPTURE_PLAN
# ════════════════════════════════════════════════════════════

class DroneCapturePlanCreate(SIAScope):
    """Flight and capture planning parameters - sia_case_id and site_id inherited from mission or provided."""
    drone_mission_id:   str = Field(..., description="FK → sia_drone_mission._id")
    crs:                Optional[str] = Field(None, max_length=100, description="Coordinate Reference System (e.g., EPSG:4326)")
    datum:              Optional[str] = Field(None, max_length=100, description="Horizontal datum (e.g., WGS84)")
    vertical_datum:     Optional[str] = Field(None, max_length=100, description="Vertical datum (e.g., EGM96)")
    gnss_method:        Optional[str] = Field(None, max_length=100, description="RTK | PPK | AUTONOMOUS")
    flight_altitude:    Optional[float] = Field(None, description="Flight altitude in meters")
    front_overlap:      Optional[float] = Field(None, description="Forward overlap percentage (e.g., 75.0)")
    side_overlap:       Optional[float] = Field(None, description="Side overlap percentage (e.g., 65.0)")
    camera_angle:       Optional[float] = Field(None, description="Camera angle in degrees (90 = nadir)")
    target_gsd:         Optional[float] = Field(None, description="Target Ground Sample Distance in cm/px")
    capture_type:       Optional[str] = Field(None, max_length=50, description="NADIR | OBLIQUE | CORRIDOR | 360")
    boundary_notes:     Optional[str] = Field(None, description="Flight boundary and coverage notes")

class DroneCapturePlanResponse(DroneCapturePlanCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-capture-plans", response_model=DroneCapturePlanResponse,
             status_code=201, tags=["SIA - Drone"])
async def create_capture_plan(data: DroneCapturePlanCreate):
    """Define capture plan for drone mission. Scope inherited from mission."""
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_drone_capture_plan")
    await capture_plan_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/drone-missions/{mission_id}/capture-plans",
            response_model=List[DroneCapturePlanResponse],
            tags=["SIA - Drone"])
async def get_capture_plans(mission_id: str):
    """Get all capture plans for a drone mission."""
    docs = await capture_plan_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_GROUND_CONTROL_POINT
# ════════════════════════════════════════════════════════════

class GroundControlPointCreate(SIAScope):
    """Ground Control Point (GCP) for georeferencing - sia_case_id and site_id inherited from mission or provided."""
    drone_mission_id:   str = Field(..., description="FK → sia_drone_mission._id")
    gcp_code:           Optional[str] = Field(None, max_length=50, description="GCP identifier (e.g., GCP-001)")
    point_type:         Optional[str] = Field(None, max_length=50, description="GCP | CHECKPOINT | TIE_POINT")
    latitude:           Optional[float] = Field(None, description="Latitude in decimal degrees")
    longitude:          Optional[float] = Field(None, description="Longitude in decimal degrees")
    elevation:          Optional[float] = Field(None, description="Elevation in meters")
    survey_method:      Optional[str] = Field(None, max_length=100, description="GNSS_RTK | TOTAL_STATION | LEVEL")
    accuracy:           Optional[float] = Field(None, description="Position accuracy in meters")
    status:             Optional[str] = Field("ACTIVE", max_length=50, description="ACTIVE | DAMAGED | LOST")

class GroundControlPointResponse(GroundControlPointCreate):
    id: str
    created_at: datetime

@router.post("/sia/ground-control-points", response_model=GroundControlPointResponse,
             status_code=201, tags=["SIA - Drone"])
async def create_gcp(data: GroundControlPointCreate):
    """Register GCP for drone mission. Scope inherited from mission."""
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_ground_control_point")
    await gcp_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/drone-missions/{mission_id}/ground-control-points",
            response_model=List[GroundControlPointResponse],
            tags=["SIA - Drone"])
async def get_gcps(mission_id: str):
    """Get all GCPs for a drone mission."""
    docs = await gcp_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_FIELD_CONDITION
# ════════════════════════════════════════════════════════════

class DroneFieldConditionCreate(SIAScope):
    """Field conditions during drone flight - sia_case_id and site_id inherited from mission or provided."""
    drone_mission_id:   str = Field(..., description="FK → sia_drone_mission._id")
    recorded_at:        Optional[str] = Field(None, description="YYYY-MM-DD HH:MM:SS")
    weather_condition:  Optional[str] = Field(None, max_length=100, description="CLEAR | PARTLY_CLOUDY | OVERCAST | HAZY")
    wind_speed:         Optional[float] = Field(None, description="Wind speed in m/s or km/h")
    temperature:        Optional[float] = Field(None, description="Temperature in °C")
    lighting_condition: Optional[str] = Field(None, max_length=100, description="BRIGHT | MODERATE | LOW | VARIABLE")
    visibility:         Optional[str] = Field(None, max_length=100, description="EXCELLENT | GOOD | MODERATE | POOR")
    rain_condition:     Optional[str] = Field(None, max_length=100, description="NONE | LIGHT | MODERATE | HEAVY")
    restriction_notes:  Optional[str] = Field(None, description="Flight restrictions or safety notes")

class DroneFieldConditionResponse(DroneFieldConditionCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-field-conditions", response_model=DroneFieldConditionResponse,
             status_code=201, tags=["SIA - Drone"])
async def create_field_condition(data: DroneFieldConditionCreate):
    """Record field conditions for drone mission. Scope inherited from mission."""
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_drone_field_condition")
    await field_cond_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/drone-missions/{mission_id}/field-conditions",
            response_model=List[DroneFieldConditionResponse],
            tags=["SIA - Drone"])
async def get_field_conditions(mission_id: str):
    """Get all field conditions recorded for a drone mission."""
    docs = await field_cond_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_RAW_DATA
# ════════════════════════════════════════════════════════════

class DroneRawDataCreate(SIAScope):
    """Raw drone data files - sia_case_id and site_id inherited from mission or provided."""
    drone_mission_id:   str = Field(..., description="FK → sia_drone_mission._id")
    data_type:          Optional[str] = Field(None, max_length=50, description="IMAGE | VIDEO | POINT_CLOUD | LIDAR | LOG")
    file_name:          Optional[str] = Field(None, max_length=255, description="Original file name")
    file_path:          Optional[str] = Field(None, description="Storage path or URL")
    file_hash:          Optional[str] = Field(None, max_length=255, description="SHA-256 hash for integrity")
    file_size:          Optional[int] = Field(None, description="File size in bytes")
    captured_at:        Optional[str] = Field(None, description="YYYY-MM-DD HH:MM:SS")
    import_status:      Optional[str] = Field("PENDING", max_length=50, description="PENDING | IMPORTED | VERIFIED | FAILED")

class DroneRawDataResponse(DroneRawDataCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-raw-data", response_model=DroneRawDataResponse,
             status_code=201, tags=["SIA - Drone"])
async def create_raw_data(data: DroneRawDataCreate):
    """Register raw data file from drone mission. Scope inherited from mission."""
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_drone_raw_data")
    await raw_data_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/drone-missions/{mission_id}/raw-data",
            response_model=List[DroneRawDataResponse],
            tags=["SIA - Drone"])
async def get_raw_data(mission_id: str):
    """Get all raw data files for a drone mission."""
    docs = await raw_data_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_QUALITY_CHECK
# ════════════════════════════════════════════════════════════

class DroneQualityCheckCreate(SIAScope):
    """Quality assurance checks - sia_case_id and site_id inherited from mission or provided."""
    drone_mission_id:       str = Field(..., description="FK → sia_drone_mission._id")
    coverage_status:        Optional[str] = Field(None, max_length=50, description="COMPLETE | PARTIAL | GAPS_DETECTED")
    gap_detected:           Optional[bool] = Field(None, description="Coverage gaps present")
    blur_status:            Optional[str] = Field(None, max_length=50, description="ACCEPTABLE | MINOR_BLUR | SIGNIFICANT_BLUR")
    exposure_status:        Optional[str] = Field(None, max_length=50, description="GOOD | OVEREXPOSED | UNDEREXPOSED")
    overlap_status:         Optional[str] = Field(None, max_length=50, description="SUFFICIENT | MARGINAL | INSUFFICIENT")
    gnss_status:            Optional[str] = Field(None, max_length=50, description="RTK_FIXED | RTK_FLOAT | AUTONOMOUS")
    control_point_status:   Optional[str] = Field(None, max_length=50, description="VERIFIED | PENDING | NOT_USED")
    qa_status:              Optional[str] = Field("PENDING", max_length=50, description="PENDING | PASSED | FAILED | CONDITIONAL")
    checked_by:             Optional[str] = Field(None, description="FK → users._id")
    checked_at:             Optional[str] = Field(None, description="YYYY-MM-DD HH:MM:SS")
    remarks:                Optional[str] = Field(None, description="QA notes and recommendations")

class DroneQualityCheckResponse(DroneQualityCheckCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-quality-checks", response_model=DroneQualityCheckResponse,
             status_code=201, tags=["SIA - Drone"])
async def create_quality_check(data: DroneQualityCheckCreate):
    """Create quality check for drone mission. Scope inherited from mission."""
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_drone_quality_check")
    await quality_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/drone-missions/{mission_id}/quality-checks",
            response_model=List[DroneQualityCheckResponse],
            tags=["SIA - Drone"])
async def get_quality_checks(mission_id: str):
    """Get all quality checks for a drone mission."""
    docs = await quality_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_DERIVED_PRODUCT
# ════════════════════════════════════════════════════════════

PRODUCT_TYPES = ["ORTHOMOSAIC", "POINT_CLOUD", "DSM", "DTM",
                 "CONTOUR", "3D_MESH", "THERMAL", "MULTISPECTRAL"]

class DroneDerivedProductCreate(SIAScope):
    """Processed drone outputs - sia_case_id and site_id inherited from mission or provided."""
    drone_mission_id:   str = Field(..., description="FK → sia_drone_mission._id")
    product_type:       Optional[str] = Field(None, max_length=100,
                            description=f"One of: {', '.join(PRODUCT_TYPES)}")
    file_name:          Optional[str] = Field(None, max_length=255, description="Output file name")
    file_path:          Optional[str] = Field(None, description="Storage path or URL")
    crs:                Optional[str] = Field(None, max_length=100, description="Coordinate Reference System")
    resolution:         Optional[float] = Field(None, description="Output resolution (e.g., cm/px for orthomosaic)")
    accuracy:           Optional[float] = Field(None, description="Accuracy assessment in meters")
    reliability_class:  Optional[str] = Field(None, max_length=50, description="VERIFIED | PROVISIONAL | PRELIMINARY")
    processing_version: Optional[str] = Field(None, max_length=100, description="Processing software and version")
    status:             Optional[str] = Field("DRAFT", max_length=50, description="DRAFT | PROCESSING | READY | APPROVED")

class DroneDerivedProductResponse(DroneDerivedProductCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-derived-products", response_model=DroneDerivedProductResponse,
             status_code=201, tags=["SIA - Drone"])
async def create_derived_product(data: DroneDerivedProductCreate):
    """Register derived product from drone mission. Scope inherited from mission."""
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_drone_derived_product")
    await derived_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/drone-missions/{mission_id}/derived-products",
            response_model=List[DroneDerivedProductResponse],
            tags=["SIA - Drone"])
async def get_derived_products(mission_id: str):
    """Get all derived products for a drone mission."""
    docs = await derived_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]
