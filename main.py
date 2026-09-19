from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.auth import router as auth_router
from api.project import router as project_router
from api.SIA.sia_case import router as sia_case_router
from api.SIA.site_survey import router as site_survey_router
from api.SIA.Engineering_Assessment import router as ea_router
from api.SIA.drone_gis_climate import router as drone_gis_router
from api.SIA.evidence_ai_readiness import router as evidence_router
from api.SIA.seb_ewb_handoff import router as seb_router
from api.SIA.android_field_ops import router as android_router
from api.SEP.seb_preparation import router as seb_prep_router
from api.SEP.engineering_review import router as eng_review_router
from api.SEP.readiness_conditions import router as readiness_router
from api.SEP.revision_change import router as revision_change_router
from api.SEP.approval_release import router as approval_release_router
from api.SEP.impact_assessment import router as impact_assessment_router
from api.SEP.handoff import router as handoff_router
from api.EWP.engineering_work import router as ewp_engineering_work_router
from api.EWP.inputs_deliverables import router as ewp_inputs_deliverables_router
from api.EWP.documents_reviews import router as ewp_documents_reviews_router
from api.EWP.approval_release import router as ewp_approval_release_router
from api.EWP.quantities_procurement import router as ewp_quantities_procurement_router
from api.EWP.lifecycle import ensure_ewp_open
from api.EWP.completion_governance import router as ewp_completion_governance_router
from api.crm import router as crm_router
from pathlib import Path

app = FastAPI()

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
app.include_router(seb_prep_router, prefix="/api", tags=["SEP - SEB Preparation"])
app.include_router(eng_review_router, prefix="/api", tags=["SEP - Engineering Review"])
app.include_router(readiness_router, prefix="/api", tags=["SEP - Readiness & Conditions"])
app.include_router(revision_change_router, prefix="/api", tags=["SEP - Revision & Change Control"])
app.include_router(approval_release_router, prefix="/api", tags=["SEP - Approval & Release"])
app.include_router(impact_assessment_router, prefix="/api", tags=["SEP - Impact Assessment"])
app.include_router(handoff_router, prefix="/api", tags=["SEP - EWB/EWP Handoff"])
app.include_router(ewp_engineering_work_router, prefix="/api", dependencies=[Depends(ensure_ewp_open)], tags=["EWP - Engineering Work"])
app.include_router(ewp_inputs_deliverables_router, prefix="/api", dependencies=[Depends(ensure_ewp_open)], tags=["EWP - Inputs & Deliverables"])
app.include_router(ewp_documents_reviews_router, prefix="/api", dependencies=[Depends(ensure_ewp_open)], tags=["EWP - Documents & Reviews"])
app.include_router(ewp_approval_release_router, prefix="/api", dependencies=[Depends(ensure_ewp_open)], tags=["EWP - Approval & Release"])
app.include_router(ewp_quantities_procurement_router, prefix="/api", dependencies=[Depends(ensure_ewp_open)], tags=["EWP - Quantities & Procurement"])
app.include_router(ewp_completion_governance_router, prefix="/api", tags=["EWP - Completion & Governance"])
app.include_router(crm_router, prefix="/api", tags=["CRM"])

@app.get("/")
async def root():
    return {"message": "Welcome to GINFINIA API - MongoDB Edition"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=8001, reload=True)
