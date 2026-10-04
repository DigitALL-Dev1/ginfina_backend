"""SIA GIS Module - Geographic Information System layers, features, and external geo sources."""
from .scope import SIAScope, apply_scope
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
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

# GIS Collections
gis_layer_col     = db["sia_gis_layer"]
gis_feature_col   = db["sia_gis_feature"]
ext_geo_col       = db["sia_external_geo_source"]

router = APIRouter()

# ════════════════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════════════════

async def init_gis_collections():
    """Initialize indexes for GIS collections."""
    await gis_layer_col.create_index("sia_case_id")
    await gis_layer_col.create_index("site_id")
    await gis_layer_col.create_index("layer_name")
    await gis_layer_col.create_index("layer_type")
    
    await gis_feature_col.create_index("gis_layer_id")
    await gis_feature_col.create_index("sia_case_id")
    await gis_feature_col.create_index("site_id")
    await gis_feature_col.create_index("poi_id")
    await gis_feature_col.create_index("feature_code")
    
    await ext_geo_col.create_index("sia_case_id")
    await ext_geo_col.create_index("site_id")
    await ext_geo_col.create_index("provider_name")
    await ext_geo_col.create_index("source_type")

    print("✓ GIS collections initialized")

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

def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to response format."""
    result = {k: doc.get(k) for k in doc if k != "_id"}
    result["id"] = str(doc["_id"])
    return result


# ════════════════════════════════════════════════════════════
# SIA_GIS_LAYER
# ════════════════════════════════════════════════════════════

class GISLayerCreate(SIAScope):
    """Create GIS layer - sia_case_id and site_id MUST be provided from frontend."""
    layer_name:         str = Field(..., max_length=150, description="Layer name (e.g., Transmission Lines)")
    layer_type:         Optional[str] = Field(None, max_length=100, description="CADASTRAL | INFRASTRUCTURE | TOPOGRAPHIC | UTILITY | ENVIRONMENTAL | SURVEY")
    geometry_type:      Optional[str] = Field(None, max_length=50, description="POINT | LINE | POLYGON | MULTIPOINT | MULTILINE | MULTIPOLYGON")
    source_name:        Optional[str] = Field(None, max_length=150, description="Data source (e.g., Government Survey, Site Survey)")
    source_date:        Optional[str] = Field(None, description="YYYY-MM-DD - Date of source data")
    crs:                Optional[str] = Field(None, max_length=100, description="Coordinate Reference System (e.g., EPSG:4326, EPSG:32637)")
    resolution_scale:   Optional[str] = Field(None, max_length=100, description="Map scale or resolution (e.g., 1:5000, 10cm GSD)")
    licence_info:       Optional[str] = Field(None, max_length=255, description="License or usage restrictions")
    reliability_status: Optional[str] = Field("PROVISIONAL", max_length=50, description="VERIFIED | PROVISIONAL | ASSUMED | UNVERIFIED")
    is_active:          Optional[bool] = Field(True, description="Layer is active/visible")
    remarks:            Optional[str] = Field(None, description="Additional notes")

class GISLayerResponse(GISLayerCreate):
    id: str
    created_at: datetime

@router.post("/sia/gis-layers", response_model=GISLayerResponse,
             status_code=201, tags=["SIA - GIS"])
async def create_gis_layer(data: GISLayerCreate):
    """Create a new GIS layer. Requires sia_case_id and site_id from frontend."""
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_gis_layer")
    await gis_layer_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/gis-layers/{layer_id}", response_model=GISLayerResponse,
            tags=["SIA - GIS"])
async def get_gis_layer(layer_id: str):
    """Get a specific GIS layer by ID."""
    doc = await gis_layer_col.find_one({"_id": layer_id})
    if not doc: 
        not_found("GIS Layer", layer_id)
    return serialize_doc(doc)

@router.get("/sia/sites/{site_id}/gis-layers",
            response_model=List[GISLayerResponse],
            tags=["SIA - GIS"])
async def get_gis_layers_by_site(site_id: str):
    """Get all GIS layers for a specific site."""
    docs = await gis_layer_col.find({"site_id": site_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]

@router.get("/sia/cases/{case_id}/gis-layers",
            response_model=List[GISLayerResponse],
            tags=["SIA - GIS"])
async def get_gis_layers_by_case(case_id: str):
    """Get all GIS layers for a specific SIA case."""
    docs = await gis_layer_col.find({"sia_case_id": case_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]

@router.patch("/sia/gis-layers/{layer_id}", response_model=GISLayerResponse,
              tags=["SIA - GIS"])
async def update_gis_layer(layer_id: str, updates: Dict[str, Any]):
    """Update GIS layer properties."""
    doc = await gis_layer_col.find_one({"_id": layer_id})
    if not doc:
        not_found("GIS Layer", layer_id)
    
    # Don't allow updating scope fields
    updates.pop("sia_case_id", None)
    updates.pop("site_id", None)
    updates.pop("_id", None)
    
    if updates:
        updates["updated_at"] = datetime.utcnow()
        await gis_layer_col.update_one({"_id": layer_id}, {"$set": updates})
        doc = await gis_layer_col.find_one({"_id": layer_id})
    
    return serialize_doc(doc)


# ════════════════════════════════════════════════════════════
# SIA_GIS_FEATURE
# ════════════════════════════════════════════════════════════

class GISFeatureCreate(SIAScope):
    """GIS feature within a layer - sia_case_id and site_id inherited from layer or provided."""
    gis_layer_id:       str = Field(..., description="FK → sia_gis_layer._id (NOT NULL)")
    poi_id:             Optional[str] = Field(None, description="FK → sia_poi._id (link to POI if applicable)")
    feature_code:       Optional[str] = Field(None, max_length=50, description="Feature identifier (e.g., TL-001)")
    feature_name:       Optional[str] = Field(None, max_length=150, description="Feature name")
    feature_type:       Optional[str] = Field(None, max_length=100, description="POLE | TOWER | CABLE | SUBSTATION | BUILDING | ROAD | RIVER | BOUNDARY")
    geometry_data:      Optional[str] = Field(None, description="GeoJSON or WKT geometry")
    attributes:         Optional[Dict[str, Any]] = Field(None, description="Feature attributes as JSON")
    description:        Optional[str] = Field(None, description="Feature description")
    reliability_status: Optional[str] = Field("PROVISIONAL", max_length=50, description="VERIFIED | PROVISIONAL | ASSUMED | UNVERIFIED")
    remarks:            Optional[str] = Field(None, description="Additional notes")

class GISFeatureResponse(GISFeatureCreate):
    id: str
    created_at: datetime

@router.post("/sia/gis-features", response_model=GISFeatureResponse,
             status_code=201, tags=["SIA - GIS"])
async def create_gis_feature(data: GISFeatureCreate):
    """Add a feature to a GIS layer. Scope inherited from layer."""
    layer = await gis_layer_col.find_one({"_id": data.gis_layer_id})
    if not layer: 
        not_found("GIS Layer", data.gis_layer_id)
    
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_gis_feature")
    await gis_feature_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/gis-layers/{layer_id}/features",
            response_model=List[GISFeatureResponse],
            tags=["SIA - GIS"])
async def get_gis_features(layer_id: str):
    """Get all features in a GIS layer."""
    docs = await gis_feature_col.find({"gis_layer_id": layer_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]

@router.get("/sia/gis-features/{feature_id}", response_model=GISFeatureResponse,
            tags=["SIA - GIS"])
async def get_gis_feature(feature_id: str):
    """Get a specific GIS feature by ID."""
    doc = await gis_feature_col.find_one({"_id": feature_id})
    if not doc:
        not_found("GIS Feature", feature_id)
    return serialize_doc(doc)

@router.patch("/sia/gis-features/{feature_id}", response_model=GISFeatureResponse,
              tags=["SIA - GIS"])
async def update_gis_feature(feature_id: str, updates: Dict[str, Any]):
    """Update GIS feature properties."""
    doc = await gis_feature_col.find_one({"_id": feature_id})
    if not doc:
        not_found("GIS Feature", feature_id)
    
    # Don't allow updating scope fields
    updates.pop("sia_case_id", None)
    updates.pop("site_id", None)
    updates.pop("gis_layer_id", None)
    updates.pop("_id", None)
    
    if updates:
        updates["updated_at"] = datetime.utcnow()
        await gis_feature_col.update_one({"_id": feature_id}, {"$set": updates})
        doc = await gis_feature_col.find_one({"_id": feature_id})
    
    return serialize_doc(doc)


# ════════════════════════════════════════════════════════════
# SIA_EXTERNAL_GEO_SOURCE
# ════════════════════════════════════════════════════════════

SOURCE_TYPES = [
    "SATELLITE_IMAGERY",
    "AERIAL_PHOTOGRAPHY", 
    "TOPOGRAPHIC_MAP",
    "CADASTRAL_DATA",
    "UTILITY_NETWORK",
    "GEOLOGICAL_MAP",
    "LAND_USE",
    "ENVIRONMENTAL_DATA",
    "GOVERNMENT_DATASET",
    "COMMERCIAL_DATASET"
]

class ExternalGeoSourceCreate(SIAScope):
    """External geographic data source - sia_case_id and site_id MUST be provided from frontend."""
    provider_name:      str = Field(..., max_length=150, description="Provider/organization name")
    dataset_name:       str = Field(..., max_length=150, description="Dataset or product name")
    source_type:        Optional[str] = Field(None, max_length=100, 
                            description=f"One of: {', '.join(SOURCE_TYPES)}")
    source_reference:   Optional[str] = Field(None, max_length=255, description="URL, file reference, or API endpoint")
    imported_at:        Optional[str] = Field(None, description="YYYY-MM-DD HH:MM:SS")
    publication_date:   Optional[str] = Field(None, description="YYYY-MM-DD - Date of publication")
    coverage_area:      Optional[str] = Field(None, description="Geographic coverage description")
    spatial_resolution: Optional[str] = Field(None, max_length=100, description="Resolution (e.g., 30m, 1:50000)")
    temporal_resolution:Optional[str] = Field(None, max_length=100, description="Update frequency (e.g., Annual, Monthly)")
    licence_info:       Optional[str] = Field(None, max_length=255, description="License terms")
    access_conditions:  Optional[str] = Field(None, description="Access restrictions or conditions")
    cost_info:          Optional[str] = Field(None, max_length=255, description="Cost or pricing information")
    limitation_notes:   Optional[str] = Field(None, description="Data limitations and restrictions")
    reliability_status: Optional[str] = Field("PROVISIONAL", max_length=50, description="VERIFIED | PROVISIONAL | ASSUMED | UNVERIFIED")
    contact_info:       Optional[str] = Field(None, description="Provider contact information")

class ExternalGeoSourceResponse(ExternalGeoSourceCreate):
    id: str
    created_at: datetime

@router.post("/sia/external-geo-sources", response_model=ExternalGeoSourceResponse,
             status_code=201, tags=["SIA - GIS"])
async def create_external_geo_source(data: ExternalGeoSourceCreate):
    """Register an external geographic data source. Requires sia_case_id and site_id from frontend."""
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow()}
    await apply_scope(db, doc, "sia_external_geo_source")
    await ext_geo_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/external-geo-sources/{source_id}", response_model=ExternalGeoSourceResponse,
            tags=["SIA - GIS"])
async def get_external_geo_source(source_id: str):
    """Get a specific external geo source by ID."""
    doc = await ext_geo_col.find_one({"_id": source_id})
    if not doc:
        not_found("External Geo Source", source_id)
    return serialize_doc(doc)

@router.get("/sia/sites/{site_id}/external-geo-sources",
            response_model=List[ExternalGeoSourceResponse],
            tags=["SIA - GIS"])
async def get_external_geo_sources_by_site(site_id: str):
    """Get all external geo sources for a specific site."""
    docs = await ext_geo_col.find({"site_id": site_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]

@router.get("/sia/cases/{case_id}/external-geo-sources",
            response_model=List[ExternalGeoSourceResponse],
            tags=["SIA - GIS"])
async def get_external_geo_sources_by_case(case_id: str):
    """Get all external geo sources for a specific SIA case."""
    docs = await ext_geo_col.find({"sia_case_id": case_id}).to_list(1000)
    return [serialize_doc(d) for d in docs]

@router.patch("/sia/external-geo-sources/{source_id}", response_model=ExternalGeoSourceResponse,
              tags=["SIA - GIS"])
async def update_external_geo_source(source_id: str, updates: Dict[str, Any]):
    """Update external geo source properties."""
    doc = await ext_geo_col.find_one({"_id": source_id})
    if not doc:
        not_found("External Geo Source", source_id)
    
    # Don't allow updating scope fields
    updates.pop("sia_case_id", None)
    updates.pop("site_id", None)
    updates.pop("_id", None)
    
    if updates:
        updates["updated_at"] = datetime.utcnow()
        await ext_geo_col.update_one({"_id": source_id}, {"$set": updates})
        doc = await ext_geo_col.find_one({"_id": source_id})
    
    return serialize_doc(doc)
