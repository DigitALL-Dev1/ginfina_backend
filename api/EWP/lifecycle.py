"""Keep a closed EWP read-only through the engineering workflow APIs."""
from fastapi import HTTPException, Request
from .documents_reviews import db


async def ensure_ewp_open(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    params = request.path_params
    ewp_id = params.get("ewp_id")
    for key, collection in [("work_item_id", "ewp_engineering_work"), ("deliverable_id", "ewp_deliverable"),
                            ("document_id", "ewp_document"), ("revision_id", "ewp_document_revision"),
                            ("assignment_id", "ewp_document_reviewer"), ("comment_id", "ewp_document_review_comment"),
                            ("register_id", "ewp_quantity_register")]:
        if ewp_id or key not in params:
            continue
        row = await db[collection].find_one({"_id": params[key]})
        if row:
            ewp_id = row.get("ewp_id")
            if not ewp_id and row.get("document_id"):
                doc = await db["ewp_document"].find_one({"_id": row["document_id"]})
                ewp_id = (doc or {}).get("ewp_id")
    if not ewp_id and request.headers.get("content-type", "").startswith("application/json"):
        body = await request.json()
        if isinstance(body, dict):
            ewp_id = body.get("ewp_id")
    if ewp_id:
        ewp = await db["ewp"].find_one({"_id": ewp_id})
        if ewp and (ewp.get("status") == "CLOSED" or (ewp.get("completion_control") or {}).get("closure")):
            raise HTTPException(409, "This EWP is closed. Its engineering records are read-only")
