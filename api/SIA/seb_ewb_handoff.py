from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException, Path, status
from motor.motor_asyncio import AsyncIOMotorClient
import os

from dotenv import load_dotenv

load_dotenv(override=True)

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]

router = APIRouter()

SIA_PREFIX = "sia_"
SCOPE_FIELDS = (
    "sia_case_id",
    "site_id",
    "case_id",
    "engineering_assessment_id",
    "survey_visit_id",
    "building_id",
    "room_area_id",
    "poi_id",
    "seb_id",
    "seb_revision_id",
    "seb_item_id",
    "ewb_handoff_id",
    "evidence_id",
    "discipline_readiness_id",
    "data_gap_id",
    "ai_observation_id",
    "conflict_id",
    "rfi_action_id",
    "constraint_id",
    "source_fact_id",
)
PROTECTED_FIELDS = {"_id", "created_at", "updated_at"}


def serialize(doc: dict) -> dict:
    result = {key: value for key, value in doc.items() if key != "_id"}
    result["id"] = str(doc["_id"])
    return result


def not_found(entity: str, identifier: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{entity} '{identifier}' not found",
    )


async def sia_collection_names() -> List[str]:
    names = await db.list_collection_names()
    return sorted(name for name in names if name.startswith(SIA_PREFIX))


def scoped_query(known_ids: set[str]) -> dict:
    return {"$or": [{field: {"$in": list(known_ids)}} for field in SCOPE_FIELDS]}


async def collect_package(case_id: str, site_id: str) -> Dict[str, List[dict]]:
    """Collect direct case/site records and their SIA child records."""
    collection_names = await sia_collection_names()
    known_ids = {case_id, site_id}
    package: Dict[str, Dict[str, dict]] = {name: {} for name in collection_names}

    # Resolve parent-child collections such as visits -> evidence,
    # assessments -> discipline records, and SEB -> handoff items.
    for _ in range(4):
        before = len(known_ids)
        for name in collection_names:
            cursor = db[name].find(scoped_query(known_ids))
            for document in await cursor.to_list(length=5000):
                package[name][str(document["_id"])] = document
                known_ids.add(str(document["_id"]))
        if len(known_ids) == before:
            break

    return {
        name: [serialize(document) for document in records.values()]
        for name, records in package.items()
        if records
    }


async def require_case_and_site(case_id: str, site_id: str) -> None:
    if not await db["sia_case"].find_one({"_id": case_id}):
        not_found("SIA case", case_id)
    site = await db["sia_site"].find_one({"_id": site_id, "sia_case_id": case_id})
    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site '{site_id}' was not found under SIA case '{case_id}'",
        )


async def init_seb_ewb_handoff_collections():
    """Initialize indexes used by the case/site completion package."""
    for name in await sia_collection_names():
        collection = db[name]
        await collection.create_index("sia_case_id")
        await collection.create_index("site_id")
    print("SIA completion package indexes initialized")


@router.get(
    "/sia/cases/{case_id}/sites/{site_id}/completion",
    response_model=Dict[str, Any],
    tags=["SIA - Completion / SEB Input"],
    summary="Get all SIA data for a case and site",
)
async def get_sia_completion_package(case_id: str, site_id: str):
    """Return the selected case/site and all relevant records across SIA modules."""
    await require_case_and_site(case_id, site_id)
    case = await db["sia_case"].find_one({"_id": case_id})
    site = await db["sia_site"].find_one({"_id": site_id})
    return {
        "sia_case_id": case_id,
        "site_id": site_id,
        "loaded_at": datetime.utcnow(),
        "case": serialize(case),
        "site": serialize(site),
        "modules": await collect_package(case_id, site_id),
    }


@router.post(
    "/sia/cases/{case_id}/sites/{site_id}/completion/verify",
    response_model=Dict[str, Any],
    tags=["SIA - Completion / SEB Input"],
    summary="Verify an SIA case and site for SEB input",
)
async def verify_sia_completion_package(case_id: str, site_id: str):
    """Mark the selected SIA case and site as verified for SEB input."""
    await require_case_and_site(case_id, site_id)
    verified_at = datetime.utcnow()

    await db["sia_case"].update_one(
        {"_id": case_id},
        {"$set": {"status": "verified", "verified_at": verified_at}},
    )
    await db["sia_site"].update_one(
        {"_id": site_id, "sia_case_id": case_id},
        {"$set": {"status": "verified", "verified_at": verified_at}},
    )

    case = await db["sia_case"].find_one({"_id": case_id})
    site = await db["sia_site"].find_one({"_id": site_id, "sia_case_id": case_id})
    return {
        "sia_case_id": case_id,
        "site_id": site_id,
        "status": "verified",
        "verified_at": verified_at,
        "case": serialize(case),
        "site": serialize(site),
    }


@router.patch(
    "/sia/cases/{case_id}/sites/{site_id}/completion/{module}/{record_id}",
    response_model=Dict[str, Any],
    tags=["SIA - Completion / SEB Input"],
    summary="Edit one record in an SIA completion package",
)
@router.put(
    "/sia/cases/{case_id}/sites/{site_id}/completion/{module}/{record_id}",
    response_model=Dict[str, Any],
    tags=["SIA - Completion / SEB Input"],
    include_in_schema=False,
)
async def update_sia_completion_record(
    case_id: str,
    site_id: str,
    module: str = Path(..., pattern=r"^sia_[a-z0-9_]+$"),
    record_id: str = Path(..., min_length=1),
    update: Dict[str, Any] = Body(..., description="Editable fields and their new values"),
):
    """Update editable fields after proving the record belongs to case/site."""
    await require_case_and_site(case_id, site_id)
    if module not in await sia_collection_names():
        not_found("SIA module", module)
    if not update:
        raise HTTPException(status_code=400, detail="At least one field is required")
    if any(field in PROTECTED_FIELDS or field.startswith("_") for field in update):
        raise HTTPException(status_code=400, detail="System fields cannot be edited")

    package = await collect_package(case_id, site_id)
    if record_id not in {record["id"] for record in package.get(module, [])}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record '{record_id}' is not part of case '{case_id}' and site '{site_id}'",
        )

    values = dict(update)
    values["updated_at"] = datetime.utcnow()
    result = await db[module].update_one({"_id": record_id}, {"$set": values})
    if result.matched_count == 0:
        not_found("SIA record", record_id)
    document = await db[module].find_one({"_id": record_id})
    return {
        "sia_case_id": case_id,
        "site_id": site_id,
        "module": module,
        "record": serialize(document),
    }
