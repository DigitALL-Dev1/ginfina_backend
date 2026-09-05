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

class ProjectResponse(BaseModel):
    id: str
    gsolve_project_id: int
    project_code: str
    project_name: str
    project_status: Optional[str]
    user_id: str
    created_at: datetime
    updated_at: datetime

# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def serialize_project(doc: dict) -> dict:
    """Convert MongoDB document to serializable dict."""
    return {
        "id": str(doc["_id"]),
        "gsolve_project_id": doc["gsolve_project_id"],
        "project_code": doc["project_code"],
        "project_name": doc["project_name"],
        "project_status": doc.get("project_status"),
        "user_id": str(doc["user_id"]),
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }

async def init_projects_collection():
    """Create indexes for ginfina_project collection."""
    await projects_collection.create_index("user_id")
    await projects_collection.create_index("gsolve_project_id")
    await projects_collection.create_index("project_code")
    print("ginfina_project collection initialized")

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
async def get_all_projects():
    """Get all projects."""
    cursor = projects_collection.find({}).sort("created_at", -1)
    projects = await cursor.to_list(length=1000)
    return [serialize_project(p) for p in projects]


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
