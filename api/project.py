from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
import os
import uuid
import httpx
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv

load_dotenv(override=True)

# MongoDB Configuration
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]
projects_collection = db["ginfina_project"]

router = APIRouter()

# ─────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────

class ProjectCreate(BaseModel):
    gsolve_project_id: int                                        # comes from gsolve (NOT NULL)
    project_code: str = Field(..., max_length=50)                 # varchar(50) NOT NULL
    project_name: str = Field(..., max_length=255)                # varchar(255) NOT NULL
    project_status: Optional[str] = Field(None, max_length=50)   # varchar(50) nullable
    user_id: str                                                  # FK → users._id (passed in body)

class ProjectUpdate(BaseModel):
    gsolve_project_id: Optional[int] = None
    project_code: Optional[str] = Field(None, max_length=50)
    project_name: Optional[str] = Field(None, max_length=255)
    project_status: Optional[str] = Field(None, max_length=50)

class ProjectDetails(BaseModel):
    customer: Optional[str] = None
    currency_name: Optional[str] = None
    start_date: Optional[str] = None
    target_end_date: Optional[str] = None
    project_type: Optional[str] = None
    business_domain: Optional[str] = None
    sub_domain: Optional[str] = None
    last_updated: Optional[str] = None
    updated_by: Optional[str] = None
    budget: Optional[str] = None
    priority: Optional[str] = None
    contract_reference: Optional[str] = None


class ExternalProject(ProjectDetails):
    id: int = Field(..., strict=True, gt=0)
    project_code: str = Field(..., min_length=1, max_length=50)
    project_name: str = Field(..., min_length=1, max_length=255)
    project_status: Optional[str] = Field(None, max_length=50)


class ProjectResponse(ProjectDetails):
    id: str
    gsolve_project_id: int
    project_code: str
    project_name: str
    project_status: Optional[str]
    user_id: Optional[str] = None
    synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def serialize_project(doc: dict) -> dict:
    """Convert MongoDB document to serializable dict."""
    return {
        **{field: doc.get(field) for field in ProjectDetails.model_fields},
        "id": str(doc["_id"]),
        "gsolve_project_id": doc["gsolve_project_id"],
        "project_code": doc["project_code"],
        "project_name": doc["project_name"],
        "project_status": doc.get("project_status"),
        "user_id": str(doc["user_id"]) if doc.get("user_id") is not None else None,
        "synced_at": doc.get("synced_at"),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }

async def init_projects_collection():
    """Create indexes for ginfina_project collection."""
    await projects_collection.create_index("user_id")
    await projects_collection.create_index("gsolve_project_id")
    await projects_collection.create_index("project_code")
    print("ginfina_project collection initialized")


async def sync_gsolve_projects() -> int:
    """Validate the complete upstream response, then upsert by external ID."""
    url = os.getenv("GSOLVE_PROJECTS_URL", "https://app-gsolve.green.com.pg/api/v1/projects/")
    headers = {"Accept": "application/json"}
    token = os.getenv("GSOLVE_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as upstream:
            response = await upstream.post(url, json={"source": "GInfina", "project_type": 2}, headers=headers)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(504, "Gsolve projects request timed out") from None
    except httpx.HTTPError:
        raise HTTPException(502, "Unable to fetch projects from Gsolve") from None

    try:
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != "001" or not isinstance(payload.get("project_list"), list):
            raise ValueError("Unexpected projects response")
        projects = [ExternalProject.model_validate(row) for row in payload["project_list"]]
        if len({project.id for project in projects}) != len(projects):
            raise ValueError("Duplicate external project IDs")
    except (ValueError, ValidationError):
        raise HTTPException(502, "Gsolve returned an invalid projects response; no projects were synced") from None

    now = datetime.utcnow()
    for project in projects:
        values = project.model_dump(exclude={"id"})
        values.update(gsolve_project_id=project.id, updated_at=now, synced_at=now)
        query = {"gsolve_project_id": project.id}
        update = {
            "$set": values,
            "$setOnInsert": {
                # Deterministic ID prevents duplicate inserts during concurrent syncs.
                "_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"gsolve:project:{project.id}")),
                "user_id": None,
                "created_at": now,
            },
        }
        try:
            await projects_collection.update_one(query, update, upsert=True)
        except DuplicateKeyError:
            await projects_collection.update_one(query, {"$set": values})
    return len(projects)

# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(project_data: ProjectCreate):
    """Create a new project."""
    now = datetime.utcnow()
    new_project = {
        "_id": str(uuid.uuid4()),
        "gsolve_project_id": project_data.gsolve_project_id,
        "project_code": project_data.project_code,
        "project_name": project_data.project_name,
        "project_status": project_data.project_status,
        "user_id": project_data.user_id,
        "created_at": now,
        "updated_at": now,
    }
    await projects_collection.insert_one(new_project)
    return serialize_project(new_project)


@router.get("/projects", response_model=List[ProjectResponse])
async def get_all_projects(refresh: bool = True):
    """Sync Gsolve into MongoDB and return stored projects. Set refresh=false for DB-only reads."""
    if refresh:
        await sync_gsolve_projects()
    cursor = projects_collection.find({}).sort("created_at", -1)
    projects = await cursor.to_list(length=1000)
    return [serialize_project(p) for p in projects]


@router.post("/projects/sync")
async def sync_projects():
    """Import source=GInfina, project_type=2 projects without deleting local records."""
    count = await sync_gsolve_projects()
    return {"message": "Projects synced successfully", "synced_count": count}


@router.get("/projects/by-gsolve/{gsolve_project_id}", response_model=List[ProjectResponse])
async def get_projects_by_gsolve_id(gsolve_project_id: int):
    """Fetch all projects matching a given gsolve_project_id."""
    cursor = projects_collection.find({"gsolve_project_id": gsolve_project_id}).sort("created_at", -1)
    projects = await cursor.to_list(length=1000)
    if not projects:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No projects found for given gsolve_project_id")
    return [serialize_project(p) for p in projects]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    """Get a single project by ID."""
    project = await projects_collection.find_one({"_id": project_id})
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return serialize_project(project)


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, project_data: ProjectUpdate):
    """Update a project."""
    project = await projects_collection.find_one({"_id": project_id})
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    update_fields = {k: v for k, v in project_data.model_dump().items() if v is not None}
    if not update_fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update")

    update_fields["updated_at"] = datetime.utcnow()
    await projects_collection.update_one({"_id": project_id}, {"$set": update_fields})

    updated = await projects_collection.find_one({"_id": project_id})
    return serialize_project(updated)


@router.delete("/projects/{project_id}", status_code=status.HTTP_200_OK)
async def delete_project(project_id: str):
    """Delete a project."""
    project = await projects_collection.find_one({"_id": project_id})
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    await projects_collection.delete_one({"_id": project_id})
    return {"message": f"Project '{project['project_name']}' deleted successfully"}
