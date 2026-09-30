"""Persist validated case/site ownership on SIA records and their children."""
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel


class SIAScope(BaseModel):
    # Optional on input for children: ownership is derived from their parent.
    # Optional on responses for records written before scope was persisted.
    sia_case_id: Optional[str] = None
    site_id: Optional[str] = None


PARENTS = {
    "building_id": "sia_building",
    "room_area_id": "sia_room_area",
    "poi_id": "sia_poi",
    "survey_visit_id": "sia_survey_visit",
    "survey_requirement_id": "sia_survey_requirement",
    "engineering_assessment_id": "sia_engineering_assessment",
    "drone_mission_id": "sia_drone_mission",
    "gis_layer_id": "sia_gis_layer",
    "external_geo_source_id": "sia_external_geo_source",
    "evidence_id": "sia_evidence",
    "ai_observation_id": "sia_ai_observation",
    "conflict_id": "sia_conflict",
    "data_gap_id": "sia_data_gap",
    "discipline_readiness_id": "sia_discipline_readiness",
    "field_case_download_id": "sia_field_case_download",
    "field_session_id": "sia_field_session",
    "sync_batch_id": "sia_sync_batch",
}

# These records may describe a shared device rather than a site visit.
GLOBAL_COLLECTIONS = {
    "sia_mobile_device", "sia_mobile_storage_status", "sia_sync_queue",
    "sia_sync_batch", "sia_sync_conflict", "sia_sync_integrity_receipt",
    "sia_device_audit",
}


async def apply_scope(db, doc, collection, *, _seen=None):
    """Resolve legacy parent chains without changing those parent documents."""
    seen = set() if _seen is None else set(_seen)
    key = (collection, doc.get("_id"))
    if key in seen:
        raise HTTPException(422, "Circular SIA parent reference")
    seen.add(key)
    scope = {}

    def merge(values):
        for field in ("sia_case_id", "site_id"):
            value = values.get(field)
            if value is None:
                continue
            if not isinstance(value, str) or not value.strip():
                raise HTTPException(422, f"{field} must be a non-empty string")
            if scope.get(field) and scope[field] != value:
                raise HTTPException(422, f"{field} does not match the linked SIA record")
            scope[field] = value

    merge(doc)
    for field, parent_collection in PARENTS.items():
        if not doc.get(field):
            continue
        parent = await db[parent_collection].find_one({"_id": doc[field]})
        if parent is None:
            raise HTTPException(404, f"{field} '{doc[field]}' not found")
        parent = dict(parent)
        await apply_scope(db, parent, parent_collection, _seen=seen)
        merge(parent)

    if collection == "sia_site":
        merge({"site_id": doc["_id"]})
    elif scope.get("site_id"):
        site = await db["sia_site"].find_one({"_id": scope["site_id"]})
        if site is None:
            raise HTTPException(404, "Selected SIA site not found")
        merge({"sia_case_id": site.get("sia_case_id")})

    if scope.get("sia_case_id"):
        if not await db["sia_case"].find_one({"_id": scope["sia_case_id"]}):
            raise HTTPException(404, "Selected SIA case not found")

    if collection not in GLOBAL_COLLECTIONS or scope:
        if not scope.get("site_id") or not scope.get("sia_case_id"):
            raise HTTPException(422, "Select an SIA case and site before saving this record")
    doc.update(scope)
    return doc
