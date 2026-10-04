"""SIA Climate Module - Climate resource data including solar, temperature, rainfall, wind, and environmental parameters."""
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

# Climate Collections
climate_col = db["sia_climate_resource"]

router = APIRouter()

# ════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════

CLIMATE_TYPES = [
    "SOLAR_RESOURCE",
    "SOLAR_IRRADIANCE", 
    "SOLAR_GHI",
    "SOLAR_DNI",
    "SOLAR_DHI",
    "TEMPERATURE",
    "TEMPERATURE_AMBIENT",
    "TEMPERATURE_MIN",
    "TEMPERATURE_MAX",
    "RAINFALL",
    "PRECIPITATION",
    "WIND",
    "WIND_SPEED",
    "WIND_DIRECTION",
    "HUMIDITY",
    "RELATIVE_HUMIDITY",
    "MARINE_CORROSION",
    "CORROSIVITY_CATEGORY",
    "SEISMIC_ZONE",
    "FLOOD_RISK",
    "DROUGHT_INDEX",
    "SNOW_LOAD",
    "ICE_ACCUMULATION"
]

RELIABILITY_LEVELS = [
    "MEASURED",           # Direct site measurement
    "VERIFIED",           # Verified from reliable source
    "PROVISIONAL",        # From reputable source, not verified
    "INTERPOLATED",       # Interpolated from nearby stations
    "MODELED",            # Climate model output
    "ASSUMED",            # Engineering assumption
    "UNVERIFIED"          # Uncertain origin
]

# ════════════════════════════════════════════════════════════
# INIT
# ════════════════════════════════════════════════════════════

async def init_climate_collections():
    """Initialize indexes for climate collections."""
    await climate_col.create_index("sia_case_id")
    await climate_col.create_index("site_id")
    await climate_col.create_index("external_geo_source_id")
    await climate_col.create_index("resource_type")
    await climate_col.create_index("parameter_name")
    await climate_col.create_index([("site_id", 1), ("resource_type", 1)])

    print("✓ Climate collections initialized")

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
# SIA_CLIMATE_RESOURCE
# ════════════════════════════════════════════════════════════

class ClimateResourceCreate(SIAScope):
    """Create climate resource - sia_case_id and site_id MUST be provided from frontend."""
    external_geo_source_id: Optional[str] = Field(None, description="FK → sia_external_geo_source._id (if from external source)")
    resource_type:          str = Field(..., max_length=100,
                                description=f"Climate parameter type. One of: {', '.join(CLIMATE_TYPES[:10])}... (see docs for full list)")
    parameter_name:         str = Field(..., max_length=100, description="Parameter name (e.g., Annual GHI, Mean Temperature)")
    parameter_value:        Optional[float] = Field(None, description="Numeric value")
    parameter_text:         Optional[str] = Field(None, max_length=255, description="Text value if not numeric (e.g., 'Corrosivity C3')")
    unit:                   Optional[str] = Field(None, max_length=50, description="Unit of measurement (e.g., kWh/m²/day, °C, mm/year, m/s)")
    period_from:            Optional[str] = Field(None, description="YYYY-MM-DD - Start of measurement/analysis period")
    period_to:              Optional[str] = Field(None, description="YYYY-MM-DD - End of measurement/analysis period")
    temporal_granularity:   Optional[str] = Field(None, max_length=50, description="ANNUAL | MONTHLY | DAILY | HOURLY")
    measurement_height:     Optional[float] = Field(None, description="Measurement height in meters (for wind, temperature)")
    spatial_reference:      Optional[str] = Field(None, max_length=255, description="Location reference (e.g., Site Center, Weather Station XYZ)")
    distance_from_site:     Optional[float] = Field(None, description="Distance from site in km (if from nearby station)")
    source_name:            Optional[str] = Field(None, max_length=150, description="Data source (e.g., NASA POWER, NREL, Local Met Station)")
    source_reference:       Optional[str] = Field(None, max_length=255, description="URL, report reference, or dataset ID")
    reliability_status:     str = Field("PROVISIONAL", max_length=50, 
                                description=f"One of: {', '.join(RELIABILITY_LEVELS)}")
    confidence_level:       Optional[str] = Field(None, max_length=50, description="HIGH | MEDIUM | LOW")
    measurement_method:     Optional[str] = Field(None, max_length=150, description="Measurement or estimation method")
    remarks:                Optional[str] = Field(None, description="Additional notes, limitations, or context")

class ClimateResourceResponse(ClimateResourceCreate):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

class ClimateResourceSummary(BaseModel):
    """Summary of climate resources by type."""
    resource_type: str
    parameter_count: int
    latest_updated: Optional[datetime] = None

@router.post("/sia/climate-resources", response_model=ClimateResourceResponse,
             status_code=201, tags=["SIA - Climate"])
async def create_climate_resource(data: ClimateResourceCreate):
    """Create a climate resource record. Requires sia_case_id and site_id from frontend."""
    doc = {"_id": new_id(), **data.model_dump(), "created_at": datetime.utcnow(), "updated_at": None}
    await apply_scope(db, doc, "sia_climate_resource")
    await climate_col.insert_one(doc)
    return serialize_doc(doc)

@router.get("/sia/climate-resources/{resource_id}", response_model=ClimateResourceResponse,
            tags=["SIA - Climate"])
async def get_climate_resource(resource_id: str):
    """Get a specific climate resource by ID."""
    doc = await climate_col.find_one({"_id": resource_id})
    if not doc:
        not_found("Climate Resource", resource_id)
    return serialize_doc(doc)

@router.get("/sia/sites/{site_id}/climate-resources",
            response_model=List[ClimateResourceResponse],
            tags=["SIA - Climate"])
async def get_climate_resources_by_site(
    site_id: str,
    resource_type: Optional[str] = None,
    reliability_status: Optional[str] = None
):
    """Get all climate resources for a specific site with optional filtering."""
    query = {"site_id": site_id}
    
    if resource_type:
        query["resource_type"] = resource_type
    
    if reliability_status:
        query["reliability_status"] = reliability_status
    
    docs = await climate_col.find(query).to_list(1000)
    return [serialize_doc(d) for d in docs]

@router.get("/sia/cases/{case_id}/climate-resources",
            response_model=List[ClimateResourceResponse],
            tags=["SIA - Climate"])
async def get_climate_resources_by_case(
    case_id: str,
    resource_type: Optional[str] = None
):
    """Get all climate resources for a specific SIA case."""
    query = {"sia_case_id": case_id}
    
    if resource_type:
        query["resource_type"] = resource_type
    
    docs = await climate_col.find(query).to_list(1000)
    return [serialize_doc(d) for d in docs]

@router.get("/sia/sites/{site_id}/climate-summary",
            response_model=List[ClimateResourceSummary],
            tags=["SIA - Climate"])
async def get_climate_summary_by_site(site_id: str):
    """Get summary of climate resources grouped by type for a site."""
    pipeline = [
        {"$match": {"site_id": site_id}},
        {"$group": {
            "_id": "$resource_type",
            "parameter_count": {"$sum": 1},
            "latest_updated": {"$max": "$updated_at"}
        }},
        {"$project": {
            "resource_type": "$_id",
            "parameter_count": 1,
            "latest_updated": 1,
            "_id": 0
        }},
        {"$sort": {"resource_type": 1}}
    ]
    
    results = await climate_col.aggregate(pipeline).to_list(100)
    return results

@router.patch("/sia/climate-resources/{resource_id}", response_model=ClimateResourceResponse,
              tags=["SIA - Climate"])
async def update_climate_resource(resource_id: str, updates: Dict[str, Any]):
    """Update climate resource properties."""
    doc = await climate_col.find_one({"_id": resource_id})
    if not doc:
        not_found("Climate Resource", resource_id)
    
    # Don't allow updating scope fields
    updates.pop("sia_case_id", None)
    updates.pop("site_id", None)
    updates.pop("_id", None)
    updates.pop("created_at", None)
    
    if updates:
        updates["updated_at"] = datetime.utcnow()
        await climate_col.update_one({"_id": resource_id}, {"$set": updates})
        doc = await climate_col.find_one({"_id": resource_id})
    
    return serialize_doc(doc)

@router.delete("/sia/climate-resources/{resource_id}", status_code=204,
               tags=["SIA - Climate"])
async def delete_climate_resource(resource_id: str):
    """Delete a climate resource record."""
    result = await climate_col.delete_one({"_id": resource_id})
    if result.deleted_count == 0:
        not_found("Climate Resource", resource_id)
    return None


# ════════════════════════════════════════════════════════════
# BULK OPERATIONS
# ════════════════════════════════════════════════════════════

class BulkClimateResourceCreate(BaseModel):
    """Bulk create climate resources for a site."""
    sia_case_id: str = Field(..., description="SIA Case ID (required)")
    site_id: str = Field(..., description="Site ID (required)")
    resources: List[Dict[str, Any]] = Field(..., min_items=1, description="List of climate resource data")

class BulkClimateResourceResponse(BaseModel):
    """Response for bulk creation."""
    created_count: int
    created_ids: List[str]

@router.post("/sia/climate-resources/bulk", response_model=BulkClimateResourceResponse,
             status_code=201, tags=["SIA - Climate"])
async def bulk_create_climate_resources(data: BulkClimateResourceCreate):
    """
    Bulk create multiple climate resources for a site.
    Useful for importing climate datasets or batch data entry.
    """
    created_ids = []
    
    for resource_data in data.resources:
        # Ensure scope is set
        resource_data["sia_case_id"] = data.sia_case_id
        resource_data["site_id"] = data.site_id
        
        doc = {
            "_id": new_id(),
            **resource_data,
            "created_at": datetime.utcnow(),
            "updated_at": None
        }
        
        await apply_scope(db, doc, "sia_climate_resource")
        await climate_col.insert_one(doc)
        created_ids.append(doc["_id"])
    
    return {
        "created_count": len(created_ids),
        "created_ids": created_ids
    }


# ════════════════════════════════════════════════════════════
# HELPER ENDPOINTS
# ════════════════════════════════════════════════════════════

@router.get("/sia/climate-resource-types", response_model=List[str],
            tags=["SIA - Climate"])
async def get_climate_resource_types():
    """Get list of supported climate resource types."""
    return CLIMATE_TYPES

@router.get("/sia/climate-reliability-levels", response_model=List[str],
            tags=["SIA - Climate"])
async def get_climate_reliability_levels():
    """Get list of supported reliability levels."""
    return RELIABILITY_LEVELS
