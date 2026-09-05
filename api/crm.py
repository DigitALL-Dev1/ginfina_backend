from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

# ─────────────────────────────────────────────
# Pydantic Model
# ─────────────────────────────────────────────

class CRMResponse(BaseModel):
    crm_reference_id: str
    opportunity_id: Optional[str]
    reference_type: Optional[str]
    client_id: Optional[str]
    source_system: Optional[str]

# ─────────────────────────────────────────────
# Dummy Data
# ─────────────────────────────────────────────

DUMMY_CRM = [
    {
        "crm_reference_id": "CRM-DUMMY-001",
        "opportunity_id": "OPP-10001",
        "reference_type": "Solar",
        "client_id": "CLIENT-001",
        "source_system": "Salesforce",
    },
    {
        "crm_reference_id": "CRM-DUMMY-002",
        "opportunity_id": "OPP-10002",
        "reference_type": "Hydro",
        "client_id": "CLIENT-002",
        "source_system": "HubSpot",
    },
    {
        "crm_reference_id": "CRM-DUMMY-003",
        "opportunity_id": "OPP-10003",
        "reference_type": "Wind",
        "client_id": "CLIENT-003",
        "source_system": "Salesforce",
    },
    {
        "crm_reference_id": "CRM-DUMMY-004",
        "opportunity_id": "OPP-10004",
        "reference_type": "Substation",
        "client_id": "CLIENT-001",
        "source_system": "Dynamics365",
    },
    {
        "crm_reference_id": "CRM-DUMMY-005",
        "opportunity_id": "OPP-10005",
        "reference_type": "Grid",
        "client_id": "CLIENT-004",
        "source_system": "Salesforce",
    },
]

# ─────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────

@router.get(
    "/crm",
    response_model=List[CRMResponse],
    summary="Get All CRM Records",
    description="Returns dummy CRM reference records.",
)
def get_crm_records():
    return DUMMY_CRM
