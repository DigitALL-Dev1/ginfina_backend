"""Formal approval and immutable release of an exact reviewed document revision.

The revision is the atomic source of truth. Approval/release collections are
idempotent projections, repaired by reads/retries if a subsequent write fails.
No collections or indexes are created at application startup.
"""

import hashlib
import json
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import documents_reviews as documents
router = APIRouter(prefix="/ewp/approval-release")
db = documents.db
users_collection = db["users"]
approval_collection = db["ewp_document_approval"]
release_collection = db["ewp_document_release"]

# This module currently runs as an unauthenticated prototype pilot. Record that
# explicitly instead of treating the selected approver as an authenticated actor.
PILOT_ACTOR_ID = "prototype-pilot"

ELIGIBLE = {"REVIEW_COMPLETED", "READY_FOR_RELEASE", "RELEASED"}


class ApproverAssignment(BaseModel):
    approver_id: str = Field(..., min_length=1, max_length=200)


class ApprovalDecision(BaseModel):
    decision: Literal["APPROVE", "APPROVE_WITH_CONDITION", "CHANGE_REQUIRED", "REJECT"]
    comment: Optional[str] = Field(None, max_length=10000)
    condition: Optional[str] = Field(None, max_length=10000)
    package_reviewed: bool
    package_hash: str = Field(..., min_length=64, max_length=64)


class ReleaseRequest(BaseModel):
    comment: Optional[str] = Field(None, max_length=10000)


def digest(value):
    return hashlib.sha256(json.dumps(documents.json_safe(value), sort_keys=True,
                                     separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


async def get_revision(revision_id):
    revision = await documents.revision_collection.find_one({"_id": revision_id})
    if not revision:
        raise HTTPException(404, "Document revision not found")
    document = await documents.require_document(revision["document_id"])
    return document, revision


async def sync_records(document, revision):
    """Deterministic IDs make retry after a partial multi-collection write safe."""
    approval = revision.get("approval")
    if approval:
        if approval.get("decision"):
            await approval_collection.update_one({"_id": approval["id"]},
                {"$set": {key: value for key, value in approval.items() if key != "id"}}, upsert=True)
        else:
            record = {key: value for key, value in approval.items() if key != "id"}
            await approval_collection.update_one({"_id": approval["id"]}, {"$setOnInsert": record}, upsert=True)
            await approval_collection.update_one({"_id": approval["id"], "status": "ASSIGNED",
                "assigned_at": {"$lte": approval["assigned_at"]}}, {"$set": record})
    release = revision.get("release_record")
    if release:
        await release_collection.update_one({"_id": release["id"]},
            {"$setOnInsert": {key: value for key, value in release.items() if key != "id"}}, upsert=True)
    if revision.get("status") in ELIGIBLE | {"CHANGE_REQUIRED", "REJECTED"}:
        predecessors = {
            "REVIEW_COMPLETED": ["UNDER_REVIEW", "SUBMITTED_FOR_REVIEW", "REVIEW_COMPLETED"],
            "READY_FOR_RELEASE": ["REVIEW_COMPLETED", "READY_FOR_RELEASE"],
            "RELEASED": ["REVIEW_COMPLETED", "READY_FOR_RELEASE", "RELEASED"],
            "CHANGE_REQUIRED": ["REVIEW_COMPLETED", "CHANGE_REQUIRED"],
            "REJECTED": ["REVIEW_COMPLETED", "REJECTED"],
        }
        await documents.document_collection.update_one(
            {"_id": document["_id"], "current_revision_id": revision["_id"],
             "status": {"$in": predecessors[revision["status"]]}},
            {"$set": {"status": revision["status"], "updated_at": revision.get("updated_at")}})


async def build_package(document, revision):
    ewp = await documents.ewp_collection.find_one({"_id": document.get("ewp_id")})
    deliverable = await documents.deliverable_collection.find_one({"_id": document.get("deliverable_id")})
    if not ewp or not deliverable:
        raise HTTPException(409, "The document's EWP or deliverable is missing")
    reviewers = await documents.reviewer_collection.find({"document_id": document["_id"],
        "revision_id": revision["_id"]}).sort("_id", 1).to_list(length=None)
    # Earlier comments are included because their closure is a Module 3 gate.
    comments = await documents.comment_collection.find({"document_id": document["_id"]}).sort("_id", 1).to_list(length=None)
    links = await db["ewp_seb_input"].find({"ewp_id": ewp["_id"]}).sort("position", 1).to_list(length=None)
    frozen = await db["seb_ewp_frozen_item"].find_one({"_id": ewp.get("freeze_snapshot_id")})
    if (links or ewp.get("freeze_snapshot_id")) and not frozen:
        raise HTTPException(409, "The frozen SEB design basis is missing")
    if frozen and frozen.get("status") != "RELEASED":
        raise HTTPException(409, "The SEB design basis must be a frozen release")
    frozen = frozen or {}
    item_by_id = {str(item.get("release_item_id") or item.get("seb_item_id") or item.get("id")): item
                  for item in frozen.get("released_seb_items", [])}
    inputs = []
    for link in links:
        item = item_by_id.get(str(link.get("release_item_id")))
        if not item:
            raise HTTPException(409, "A selected SEB input is missing from the frozen release")
        inputs.append({"link_id": str(link["_id"]), "release_item_id": link["release_item_id"],
                       "freeze_snapshot_id": link.get("freeze_snapshot_id"), "item": documents.json_safe(item)})
    confirmations = await db["ewp_input_confirmation"].find({"ewp_id": ewp["_id"],
        "engineering_work_item_id": deliverable.get("engineering_work_item_id")}).sort("_id", 1).to_list(length=None)
    file_path = Path(revision.get("storage_path") or "")
    file_hash = None
    if file_path.is_file():
        with file_path.open("rb") as stream:
            file_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "ewp": {"id": str(ewp["_id"]), "code": ewp.get("ewp_code"), "name": ewp.get("ewp_name"),
                "project_id": ewp.get("project_id")},
        "deliverable": {"id": str(deliverable["_id"]), "code": deliverable.get("code"), "name": deliverable.get("name"),
                        "engineering_work_item_id": deliverable.get("engineering_work_item_id")},
        "document": {"id": str(document["_id"]), "code": document.get("document_code"), "title": document.get("title")},
        "revision": {"id": str(revision["_id"]), "revision_no": revision.get("revision_no"),
                     "review_completed_at": revision.get("review_completed_at"), "note": revision.get("revision_note")},
        "prepared_by": deliverable.get("responsible_engineer"),
        "reviewers": [documents.serialize(row) for row in reviewers],
        "comments": [documents.serialize(row) for row in comments],
        "open_comments": sum(row.get("status") != "CLOSED" for row in comments),
        "file": {"name": revision.get("file_name"), "content_type": revision.get("content_type"),
                 "size": revision.get("file_size"), "sha256": file_hash},
        "seb_basis": {"seb_id": ewp.get("seb_id"), "revision_id": ewp.get("seb_revision_id"),
                      "freeze_snapshot_id": ewp.get("freeze_snapshot_id"), "snapshot_hash": frozen.get("snapshot_hash"),
                      "seb": frozen.get("seb"), "released_revision": frozen.get("released_revision")},
        "inputs": inputs,
        "input_confirmations": [documents.serialize(row) for row in confirmations],
    }


def validate_review(package):
    if not package["file"]["sha256"]:
        raise HTTPException(409, "The reviewed document file is missing")
    if package["open_comments"]:
        raise HTTPException(409, "Close all review comments before approval")
    reviewers = package["reviewers"]
    if not reviewers or any(row.get("status") != "COMPLETED" or
        row.get("decision") not in {"ACCEPT", "ACCEPT_WITH_COMMENT"} for row in reviewers):
        raise HTTPException(409, "All assigned reviewers must accept the revision before approval")


@router.get("/ewps")
async def list_ewps():
    rows = await documents.ewp_collection.find({}).sort("ewp_code", 1).to_list(length=None)
    return [{"id": str(row["_id"]), "code": row.get("ewp_code"), "name": row.get("ewp_name")} for row in rows]


@router.get("/approvers")
async def list_approvers():
    rows = await users_collection.find({"is_active": {"$ne": False}}, {"name": 1, "email": 1}).sort("name", 1).to_list(length=None)
    return {"users": [{"id": str(row["_id"]), "name": row.get("name") or row.get("email") or str(row["_id"])} for row in rows]}


@router.get("/documents")
async def list_documents(ewp_id: str):
    rows = await documents.document_collection.find({"ewp_id": ewp_id}).sort("document_code", 1).to_list(length=None)
    result = []
    for row in rows:
        revisions = await documents.revision_collection.find({"document_id": row["_id"],
            "$or": [{"status": {"$in": list(ELIGIBLE)}}, {"approval": {"$exists": True}}]
        }).sort("created_at", -1).to_list(length=None)
        if revisions:
            result.append({"id": str(row["_id"]), "code": row.get("document_code"), "title": row.get("title"),
                "revisions": [{"id": str(rev["_id"]), "revision_no": rev.get("revision_no"),
                               "status": rev.get("status")} for rev in revisions]})
    return result


@router.get("/revisions/{revision_id}/package")
async def get_package(revision_id: str):
    document, revision = await get_revision(revision_id)
    if revision.get("status") not in ELIGIBLE and not revision.get("approval"):
        raise HTTPException(409, "Complete technical review before opening the approval package")
    await sync_records(document, revision)
    release = revision.get("release_record")
    approval = revision.get("approval")
    # Once decided, always display the exact package the approver reviewed.
    package = release["package"] if release else (approval or {}).get("package")
    if package is None:
        package = await build_package(document, revision)
    return {"status": revision["status"], "is_current": document.get("current_revision_id") == revision_id,
            "package_hash": digest(package),
            "package": package, "approval": approval, "release": release}


@router.put("/revisions/{revision_id}/approver")
async def assign_approver(revision_id: str, request: ApproverAssignment):
    document, revision = await get_revision(revision_id)
    approver = await users_collection.find_one({"_id": request.approver_id, "is_active": {"$ne": False}})
    if not approver:
        raise HTTPException(400, "Select an active approver")
    if document.get("current_revision_id") != revision_id:
        raise HTTPException(409, "Assign an approver to the current revision")
    approval = {"id": revision_id, "document_id": document["_id"], "revision_id": revision_id,
                "ewp_id": document["ewp_id"], "approver_id": str(approver["_id"]),
                "approver": approver.get("name") or approver.get("email"),
                "assigned_by": PILOT_ACTOR_ID, "actor_mode": "PROTOTYPE_PILOT",
                "status": "ASSIGNED", "assigned_at": documents.now_iso()}
    result = await documents.revision_collection.update_one(
        {"_id": revision_id, "status": "REVIEW_COMPLETED", "approval.decision": {"$exists": False}},
        {"$set": {"approval": approval}})
    if not result.matched_count:
        raise HTTPException(409, "Approver assignment is locked after a decision")
    return await get_package(revision_id)


@router.post("/revisions/{revision_id}/approval")
async def submit_approval(revision_id: str, request: ApprovalDecision):
    document, revision = await get_revision(revision_id)
    if revision.get("status") != "REVIEW_COMPLETED" or document.get("current_revision_id") != revision_id:
        raise HTTPException(409, "Select the current REVIEW_COMPLETED revision")
    assigned = revision.get("approval") or {}
    if not assigned.get("approver") or assigned.get("decision"):
        raise HTTPException(409, "Assign an approver before submitting a decision")
    if not request.package_reviewed:
        raise HTTPException(400, "Confirm that the approval package has been reviewed")
    comment = (request.comment or "").strip()
    condition = (request.condition or "").strip()
    if request.decision != "APPROVE" and not comment:
        raise HTTPException(400, "A comment is required for this decision")
    if request.decision == "APPROVE_WITH_CONDITION" and not condition:
        raise HTTPException(400, "An approval condition is required")
    package = await build_package(document, revision)
    validate_review(package)
    if digest(package) != request.package_hash:
        raise HTTPException(409, "The approval package changed. Refresh and review it again")
    timestamp = documents.now_iso()
    approved = request.decision in {"APPROVE", "APPROVE_WITH_CONDITION"}
    next_status = "READY_FOR_RELEASE" if approved else ("REJECTED" if request.decision == "REJECT" else "CHANGE_REQUIRED")
    approval = {**assigned, "decision": request.decision, "comment": comment,
        "recorded_by": PILOT_ACTOR_ID, "actor_mode": "PROTOTYPE_PILOT",
        "condition": condition if request.decision == "APPROVE_WITH_CONDITION" else None,
        "status": "APPROVED" if approved else next_status, "decided_at": timestamp,
        "package": package, "package_hash": digest(package)}
    result = await documents.revision_collection.update_one(
        {"_id": revision_id, "status": "REVIEW_COMPLETED", "approval": assigned},
        {"$set": {"approval": approval, "status": next_status, "updated_at": timestamp}})
    if not result.matched_count:
        raise HTTPException(409, "The revision or approver changed; reload the package")
    return await get_package(revision_id)


@router.post("/revisions/{revision_id}/release")
async def release_revision(revision_id: str, request: ReleaseRequest):
    document, revision = await get_revision(revision_id)
    approval = revision.get("approval") or {}
    # An identical retry retrieves the original immutable release, never a new one.
    if revision.get("status") == "RELEASED" and revision.get("release_record"):
        return await get_package(revision_id)
    if document.get("current_revision_id") != revision_id or revision.get("status") != "READY_FOR_RELEASE":
        raise HTTPException(409, "Only the current READY_FOR_RELEASE revision can be released")
    if approval.get("decision") not in {"APPROVE", "APPROVE_WITH_CONDITION"}:
        raise HTTPException(409, "An approval decision is required before release")
    package = await build_package(document, revision)
    validate_review(package)
    if digest(package) != approval.get("package_hash"):
        raise HTTPException(409, "The approved package has changed. Create and review a new revision")
    timestamp = documents.now_iso()
    record = {"id": revision_id, "release_code": f"REL-{revision_id}", "status": "RELEASED",
              "ewp_id": document["ewp_id"], "document_id": document["_id"], "revision_id": revision_id,
              "revision_no": revision.get("revision_no"), "approval_id": approval["id"],
              "released_by": "Prototype pilot", "released_by_id": PILOT_ACTOR_ID, "actor_mode": "PROTOTYPE_PILOT",
              "released_at": timestamp, "comment": (request.comment or "").strip(),
              "package": package, "approval": {k: v for k, v in approval.items() if k != "package"}}
    record["release_hash"] = digest(record)
    result = await documents.revision_collection.update_one(
        {"_id": revision_id, "status": "READY_FOR_RELEASE", "approval.package_hash": approval["package_hash"]},
        {"$set": {"release_record": record, "status": "RELEASED", "released_at": timestamp, "updated_at": timestamp}})
    if not result.matched_count:
        _, latest = await get_revision(revision_id)
        if latest.get("status") != "RELEASED":
            raise HTTPException(409, "The revision changed; reload before releasing")
    return await get_package(revision_id)
