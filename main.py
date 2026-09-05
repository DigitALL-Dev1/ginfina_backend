from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.auth import router as auth_router, init_db
from api.project import router as project_router, init_projects_collection
from api.SIA.sia_case import router as sia_case_router, init_sia_case_collection
from api.SIA.site_survey import router as site_survey_router, init_site_survey_collections
from api.SIA.Engineering_Assessment import router as ea_router, init_engineering_assessment_collections
from api.SIA.drone_gis_climate import router as drone_gis_router, init_drone_gis_climate_collections
from api.SIA.evidence_ai_readiness import router as evidence_router, init_evidence_ai_readiness_collections
from api.SIA.seb_ewb_handoff import router as seb_router, init_seb_ewb_handoff_collections
from api.SIA.android_field_ops import router as android_router, init_android_field_ops_collections
from api.crm import router as crm_router
from pathlib import Path

app = FastAPI()

# Database initialization on startup
@app.on_event("startup")
async def startup_event():
    await init_db()
    await init_projects_collection()
    await init_sia_case_collection()
    await init_site_survey_collections()
    await init_engineering_assessment_collections()
    await init_drone_gis_climate_collections()
    await init_evidence_ai_readiness_collections()
    await init_seb_ewb_handoff_collections()
    await init_android_field_ops_collections()
    print("Database initialized successfully")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static directory for SVGs if it doesn't exist
SVG_DIR = Path("static/svgs")
SVG_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files for serving SVGs
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(project_router, prefix="/api", tags=["Projects"])
app.include_router(sia_case_router, prefix="/api", tags=["SIA"])
app.include_router(site_survey_router, prefix="/api", tags=["SIA - Sites & Survey"])
app.include_router(ea_router, prefix="/api", tags=["SIA - Engineering Assessment"])
app.include_router(drone_gis_router, prefix="/api", tags=["SIA - Drone, GIS & Climate"])
app.include_router(evidence_router, prefix="/api", tags=["SIA - Evidence, AI & Readiness"])
app.include_router(seb_router, prefix="/api", tags=["SIA - SEB & EWB Handoff"])
app.include_router(android_router, prefix="/api", tags=["SIA - Android Field Ops"])
app.include_router(crm_router, prefix="/api", tags=["CRM"])

@app.get("/")
async def root():
    return {"message": "Welcome to GINFINIA API - MongoDB Edition"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True)
