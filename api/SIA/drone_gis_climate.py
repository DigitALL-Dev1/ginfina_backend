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

mission_col       = db["sia_drone_mission"]
operator_col      = db["sia_drone_operator"]
platform_col      = db["sia_drone_platform"]
capture_plan_col  = db["sia_drone_capture_plan"]
gcp_col           = db["sia_ground_control_point"]
field_cond_col    = db["sia_drone_field_condition"]
raw_data_col      = db["sia_drone_raw_data"]
quality_col       = db["sia_drone_quality_check"]
derived_col       = db["sia_drone_derived_product"]
gis_layer_col     = db["sia_gis_layer"]
gis_feature_col   = db["sia_gis_feature"]
ext_geo_col       = db["sia_external_geo_source"]
climate_col       = db["sia_climate_resource"]

router = APIRouter()

# ════════════════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════════════════

async def init_drone_gis_climate_collections():
    await mission_col.create_index("site_id")
    await mission_col.create_index("survey_visit_id")
    await mission_col.create_index("mission_code")

    for col in [operator_col, platform_col, capture_plan_col,
                gcp_col, field_cond_col, raw_data_col,
                quality_col, derived_col]:
        await col.create_index("drone_mission_id")

    await operator_col.create_index("user_id")
    await quality_col.create_index("checked_by")

    await gis_layer_col.create_index("site_id")
    await gis_feature_col.create_index("gis_layer_id")
    await gis_feature_col.create_index("poi_id")

    await ext_geo_col.create_index("site_id")
    await climate_col.create_index("site_id")
    await climate_col.create_index("external_geo_source_id")

    print("drone_gis_climate collections initialized")

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


# ════════════════════════════════════════════════════════════
# SIA_DRONE_MISSION
# ════════════════════════════════════════════════════════════

class DroneMissionCreate(BaseModel):
    site_id:            str = Field(..., description="FK → sia_site._id (NOT NULL)")
    survey_visit_id:    Optional[str] = None
    mission_code:       str = Field(..., max_length=50)
    mission_purpose:    Optional[str] = Field(None, max_length=255)
    target_discipline:  Optional[str] = Field(None, max_length=100)
    planned_date:       Optional[str] = None
    actual_date:        Optional[str] = None
    mission_status:     Optional[str] = Field(None, max_length=50)
    remarks:            Optional[str] = None

class DroneMissionResponse(DroneMissionCreate):
    id: str
    created_at: datetime

def _mission(doc) -> dict:
    d = {k: doc.get(k) for k in doc if k != "_id"}
    d["id"] = str(doc["_id"])
    return d

@router.post("/sia/drone-missions", response_model=DroneMissionResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_drone_mission(data: DroneMissionCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await mission_col.insert_one(doc)
    return _mission(doc)

@router.get("/sia/drone-missions/{mission_id}", response_model=DroneMissionResponse,
            tags=["SIA - Drone, GIS & Climate"])
async def get_drone_mission(mission_id: str):
    doc = await mission_col.find_one({"_id": mission_id})
    if not doc: not_found("Drone Mission", mission_id)
    return _mission(doc)

@router.get("/sia/sites/{site_id}/drone-missions",
            response_model=List[DroneMissionResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_missions_by_site(site_id: str):
    docs = await mission_col.find({"site_id": site_id}).to_list(1000)
    return [_mission(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_OPERATOR
# ════════════════════════════════════════════════════════════

class DroneOperatorCreate(BaseModel):
    drone_mission_id:   str = Field(..., description="FK → sia_drone_mission._id (NOT NULL)")
    user_id:            Optional[str] = Field(None, description="FK → users._id")
    competency_ref:     Optional[str] = Field(None, max_length=100)
    permission_ref:     Optional[str] = Field(None, max_length=100)
    regulatory_ref:     Optional[str] = Field(None, max_length=100)
    restriction_notes:  Optional[str] = None

class DroneOperatorResponse(DroneOperatorCreate):
    id: str
    created_at: datetime

def _generic(doc) -> dict:
    d = {k: doc.get(k) for k in doc if k != "_id"}
    d["id"] = str(doc["_id"])
    return d

@router.post("/sia/drone-operators", response_model=DroneOperatorResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_drone_operator(data: DroneOperatorCreate):
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await operator_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/drone-missions/{mission_id}/operators",
            response_model=List[DroneOperatorResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_operators(mission_id: str):
    docs = await operator_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_PLATFORM
# ════════════════════════════════════════════════════════════

class DronePlatformCreate(BaseModel):
    drone_mission_id:       str = Field(...)
    drone_make:             Optional[str] = Field(None, max_length=100)
    drone_model:            Optional[str] = Field(None, max_length=100)
    serial_number:          Optional[str] = Field(None, max_length=100)
    sensor_type:            Optional[str] = Field(None, max_length=100)
    camera_model:           Optional[str] = Field(None, max_length=100)
    firmware_version:       Optional[str] = Field(None, max_length=50)
    rtk_ppk_capable:        Optional[bool] = None
    thermal_capable:        Optional[bool] = None
    multispectral_capable:  Optional[bool] = None

class DronePlatformResponse(DronePlatformCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-platforms", response_model=DronePlatformResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_drone_platform(data: DronePlatformCreate):
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await platform_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/drone-missions/{mission_id}/platforms",
            response_model=List[DronePlatformResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_platforms(mission_id: str):
    docs = await platform_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_CAPTURE_PLAN
# ════════════════════════════════════════════════════════════

class DroneCapturePlanCreate(BaseModel):
    drone_mission_id:   str = Field(...)
    crs:                Optional[str] = Field(None, max_length=100)
    datum:              Optional[str] = Field(None, max_length=100)
    vertical_datum:     Optional[str] = Field(None, max_length=100)
    gnss_method:        Optional[str] = Field(None, max_length=100)
    flight_altitude:    Optional[float] = None
    front_overlap:      Optional[float] = None
    side_overlap:       Optional[float] = None
    camera_angle:       Optional[float] = None
    target_gsd:         Optional[float] = None
    capture_type:       Optional[str] = Field(None, max_length=50)
    boundary_notes:     Optional[str] = None

class DroneCapturePlanResponse(DroneCapturePlanCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-capture-plans", response_model=DroneCapturePlanResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_capture_plan(data: DroneCapturePlanCreate):
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await capture_plan_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/drone-missions/{mission_id}/capture-plans",
            response_model=List[DroneCapturePlanResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_capture_plans(mission_id: str):
    docs = await capture_plan_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_GROUND_CONTROL_POINT
# ════════════════════════════════════════════════════════════

class GroundControlPointCreate(BaseModel):
    drone_mission_id:   str = Field(...)
    gcp_code:           Optional[str] = Field(None, max_length=50)
    point_type:         Optional[str] = Field(None, max_length=50)
    latitude:           Optional[float] = None
    longitude:          Optional[float] = None
    elevation:          Optional[float] = None
    survey_method:      Optional[str] = Field(None, max_length=100)
    accuracy:           Optional[float] = None
    status:             Optional[str] = Field(None, max_length=50)

class GroundControlPointResponse(GroundControlPointCreate):
    id: str
    created_at: datetime

@router.post("/sia/ground-control-points", response_model=GroundControlPointResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_gcp(data: GroundControlPointCreate):
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await gcp_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/drone-missions/{mission_id}/ground-control-points",
            response_model=List[GroundControlPointResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_gcps(mission_id: str):
    docs = await gcp_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_FIELD_CONDITION
# ════════════════════════════════════════════════════════════

class DroneFieldConditionCreate(BaseModel):
    drone_mission_id:   str = Field(...)
    recorded_at:        Optional[str] = None
    weather_condition:  Optional[str] = Field(None, max_length=100)
    wind_speed:         Optional[float] = None
    temperature:        Optional[float] = None
    lighting_condition: Optional[str] = Field(None, max_length=100)
    visibility:         Optional[str] = Field(None, max_length=100)
    rain_condition:     Optional[str] = Field(None, max_length=100)
    restriction_notes:  Optional[str] = None

class DroneFieldConditionResponse(DroneFieldConditionCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-field-conditions", response_model=DroneFieldConditionResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_field_condition(data: DroneFieldConditionCreate):
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await field_cond_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/drone-missions/{mission_id}/field-conditions",
            response_model=List[DroneFieldConditionResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_field_conditions(mission_id: str):
    docs = await field_cond_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_RAW_DATA
# ════════════════════════════════════════════════════════════

class DroneRawDataCreate(BaseModel):
    drone_mission_id:   str = Field(...)
    data_type:          Optional[str] = Field(None, max_length=50)
    file_name:          Optional[str] = Field(None, max_length=255)
    file_path:          Optional[str] = None
    file_hash:          Optional[str] = Field(None, max_length=255)
    file_size:          Optional[int] = None
    captured_at:        Optional[str] = None
    import_status:      Optional[str] = Field(None, max_length=50)

class DroneRawDataResponse(DroneRawDataCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-raw-data", response_model=DroneRawDataResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_raw_data(data: DroneRawDataCreate):
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await raw_data_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/drone-missions/{mission_id}/raw-data",
            response_model=List[DroneRawDataResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_raw_data(mission_id: str):
    docs = await raw_data_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_QUALITY_CHECK
# ════════════════════════════════════════════════════════════

class DroneQualityCheckCreate(BaseModel):
    drone_mission_id:       str = Field(...)
    coverage_status:        Optional[str] = Field(None, max_length=50)
    gap_detected:           Optional[bool] = None
    blur_status:            Optional[str] = Field(None, max_length=50)
    exposure_status:        Optional[str] = Field(None, max_length=50)
    overlap_status:         Optional[str] = Field(None, max_length=50)
    gnss_status:            Optional[str] = Field(None, max_length=50)
    control_point_status:   Optional[str] = Field(None, max_length=50)
    qa_status:              Optional[str] = Field(None, max_length=50)
    checked_by:             Optional[str] = Field(None, description="FK → users._id")
    checked_at:             Optional[str] = None
    remarks:                Optional[str] = None

class DroneQualityCheckResponse(DroneQualityCheckCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-quality-checks", response_model=DroneQualityCheckResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_quality_check(data: DroneQualityCheckCreate):
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await quality_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/drone-missions/{mission_id}/quality-checks",
            response_model=List[DroneQualityCheckResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_quality_checks(mission_id: str):
    docs = await quality_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_DRONE_DERIVED_PRODUCT
# ════════════════════════════════════════════════════════════

PRODUCT_TYPES = ["ORTHOMOSAIC", "POINT_CLOUD", "DSM", "DTM",
                 "CONTOUR", "3D_MESH", "THERMAL"]

class DroneDerivedProductCreate(BaseModel):
    drone_mission_id:   str = Field(...)
    product_type:       Optional[str] = Field(None, max_length=100,
                            description=f"One of: {', '.join(PRODUCT_TYPES)}")
    file_name:          Optional[str] = Field(None, max_length=255)
    file_path:          Optional[str] = None
    crs:                Optional[str] = Field(None, max_length=100)
    resolution:         Optional[float] = None
    accuracy:           Optional[float] = None
    reliability_class:  Optional[str] = Field(None, max_length=50)
    processing_version: Optional[str] = Field(None, max_length=100)
    status:             Optional[str] = Field(None, max_length=50)

class DroneDerivedProductResponse(DroneDerivedProductCreate):
    id: str
    created_at: datetime

@router.post("/sia/drone-derived-products", response_model=DroneDerivedProductResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_derived_product(data: DroneDerivedProductCreate):
    await require_mission(data.drone_mission_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await derived_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/drone-missions/{mission_id}/derived-products",
            response_model=List[DroneDerivedProductResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_derived_products(mission_id: str):
    docs = await derived_col.find({"drone_mission_id": mission_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_GIS_LAYER
# ════════════════════════════════════════════════════════════

class GISLayerCreate(BaseModel):
    site_id:            str = Field(..., description="FK → sia_site._id (NOT NULL)")
    layer_name:         Optional[str] = Field(None, max_length=150)
    layer_type:         Optional[str] = Field(None, max_length=100)
    geometry_type:      Optional[str] = Field(None, max_length=50)
    source_name:        Optional[str] = Field(None, max_length=150)
    source_date:        Optional[str] = None
    crs:                Optional[str] = Field(None, max_length=100)
    resolution_scale:   Optional[str] = Field(None, max_length=100)
    licence_info:       Optional[str] = Field(None, max_length=255)
    reliability_status: Optional[str] = Field(None, max_length=50)
    is_active:          Optional[bool] = True

class GISLayerResponse(GISLayerCreate):
    id: str
    created_at: datetime

@router.post("/sia/gis-layers", response_model=GISLayerResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_gis_layer(data: GISLayerCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await gis_layer_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/gis-layers/{layer_id}", response_model=GISLayerResponse,
            tags=["SIA - Drone, GIS & Climate"])
async def get_gis_layer(layer_id: str):
    doc = await gis_layer_col.find_one({"_id": layer_id})
    if not doc: not_found("GIS Layer", layer_id)
    return _generic(doc)

@router.get("/sia/sites/{site_id}/gis-layers",
            response_model=List[GISLayerResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_gis_layers_by_site(site_id: str):
    docs = await gis_layer_col.find({"site_id": site_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_GIS_FEATURE
# ════════════════════════════════════════════════════════════

class GISFeatureCreate(BaseModel):
    gis_layer_id:       str = Field(..., description="FK → sia_gis_layer._id (NOT NULL)")
    poi_id:             Optional[str] = Field(None, description="FK → sia_poi._id")
    feature_code:       Optional[str] = Field(None, max_length=50)
    feature_name:       Optional[str] = Field(None, max_length=150)
    feature_type:       Optional[str] = Field(None, max_length=100)
    geometry_data:      Optional[str] = None
    description:        Optional[str] = None
    reliability_status: Optional[str] = Field(None, max_length=50)

class GISFeatureResponse(GISFeatureCreate):
    id: str
    created_at: datetime

@router.post("/sia/gis-features", response_model=GISFeatureResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_gis_feature(data: GISFeatureCreate):
    layer = await gis_layer_col.find_one({"_id": data.gis_layer_id})
    if not layer: not_found("GIS Layer", data.gis_layer_id)
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await gis_feature_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/gis-layers/{layer_id}/features",
            response_model=List[GISFeatureResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_gis_features(layer_id: str):
    docs = await gis_feature_col.find({"gis_layer_id": layer_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_EXTERNAL_GEO_SOURCE
# ════════════════════════════════════════════════════════════

class ExternalGeoSourceCreate(BaseModel):
    site_id:            str = Field(..., description="FK → sia_site._id (NOT NULL)")
    provider_name:      Optional[str] = Field(None, max_length=150)
    dataset_name:       Optional[str] = Field(None, max_length=150)
    source_type:        Optional[str] = Field(None, max_length=100)
    source_reference:   Optional[str] = Field(None, max_length=255)
    imported_at:        Optional[str] = None
    licence_info:       Optional[str] = Field(None, max_length=255)
    limitation_notes:   Optional[str] = None
    reliability_status: Optional[str] = Field(None, max_length=50)

class ExternalGeoSourceResponse(ExternalGeoSourceCreate):
    id: str
    created_at: datetime

@router.post("/sia/external-geo-sources", response_model=ExternalGeoSourceResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_external_geo_source(data: ExternalGeoSourceCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await ext_geo_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/sites/{site_id}/external-geo-sources",
            response_model=List[ExternalGeoSourceResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_external_geo_sources(site_id: str):
    docs = await ext_geo_col.find({"site_id": site_id}).to_list(1000)
    return [_generic(d) for d in docs]


# ════════════════════════════════════════════════════════════
# SIA_CLIMATE_RESOURCE
# ════════════════════════════════════════════════════════════

CLIMATE_TYPES = ["SOLAR_RESOURCE", "TEMPERATURE", "RAINFALL",
                 "WIND", "HUMIDITY", "MARINE_CORROSION"]

class ClimateResourceCreate(BaseModel):
    site_id:                str = Field(..., description="FK → sia_site._id (NOT NULL)")
    external_geo_source_id: Optional[str] = Field(None, description="FK → sia_external_geo_source._id")
    resource_type:          Optional[str] = Field(None, max_length=100,
                                description=f"One of: {', '.join(CLIMATE_TYPES)}")
    parameter_name:         Optional[str] = Field(None, max_length=100)
    parameter_value:        Optional[float] = None
    unit:                   Optional[str] = Field(None, max_length=50)
    period_from:            Optional[str] = None
    period_to:              Optional[str] = None
    source_name:            Optional[str] = Field(None, max_length=150)
    reliability_status:     Optional[str] = Field(None, max_length=50)
    remarks:                Optional[str] = None

class ClimateResourceResponse(ClimateResourceCreate):
    id: str
    created_at: datetime

@router.post("/sia/climate-resources", response_model=ClimateResourceResponse,
             status_code=201, tags=["SIA - Drone, GIS & Climate"])
async def create_climate_resource(data: ClimateResourceCreate):
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await climate_col.insert_one(doc)
    return _generic(doc)

@router.get("/sia/sites/{site_id}/climate-resources",
            response_model=List[ClimateResourceResponse],
            tags=["SIA - Drone, GIS & Climate"])
async def get_climate_resources(site_id: str):
    docs = await climate_col.find({"site_id": site_id}).to_list(1000)
    return [_generic(d) for d in docs]
