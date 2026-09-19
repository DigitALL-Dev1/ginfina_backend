"""Controlled engineering documents, revisions, and technical reviews."""

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
from typing import Optional
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field


router = APIRouter()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ginfina")
DOCUMENT_UPLOAD_DIR = Path(os.getenv("EWP_DOCUMENT_UPLOAD_DIR", "uploads/ewp_documents"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

client = AsyncIOMotorClient(MONGODB_URL)
db = client[DATABASE_NAME]
ewp_collection = db["ewp"]
deliverable_collection = db["ewp_deliverable"]
document_collection = db["ewp_document"]
revision_collection = db["ewp_document_revision"]
reviewer_collection = db["ewp_document_reviewer"]
decision_collection = db["ewp_document_review_decision"]
comment_collection = db["ewp_document_review_comment"]

DECISIONS = {"ACCEPT", "ACCEPT_WITH_COMMENT", "CHANGE_REQUIRED", "REJECT"}


class ReviewerCreate(BaseModel):
    reviewer_name: str = Field(..., min_length=1)
    reviewer_role: str = Field(..., min_length=1)


class ReviewDecisionCreate(BaseModel):
    decision: str = Field(..., min_length=1)
    comment: Optional[str] = None


class ReviewCommentCreate(BaseModel):
    text: str = Field(..., min_length=1)
    raised_by: str = Field(..., min_length=1)
    markup_reference: Optional[str] = None


class CommentResponseUpdate(BaseModel):
    response: str = Field(..., min_length=1)
    responded_by: Optional[str] = None
    close: bool = True


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def serialize(document: dict) -> dict:
    result = json_safe(document)
    result["id"] = str(result.pop("_id"))
    return result


async def require_deliverable(deliverable_id: str) -> dict:
    deliverable = await deliverable_collection.find_one({"_id": deliverable_id})
    if not deliverable:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    if deliverable.get("status") != "READY_FOR_REVIEW":
        raise HTTPException(status_code=409, detail="Deliverable is not READY_FOR_REVIEW")
    return deliverable


async def require_document(document_id: str) -> dict:
    document = await document_collection.find_one({"_id": document_id})
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def require_editable_review(document: dict, revision_id: Optional[str] = None):
    """Completed review material is sealed; changes require a new revision."""
    for target in {document.get("current_revision_id"), revision_id} - {None}:
        revision = await revision_collection.find_one({"_id": target})
        if not revision:
            raise HTTPException(409, "Document revision was not found")
        if revision.get("status") in {"REVIEW_COMPLETED", "READY_FOR_RELEASE", "RELEASED"} or revision.get("approval", {}).get("decision"):
            raise HTTPException(409, "This revision is locked. Create a new revision for engineering changes")


async def save_upload(upload: Optional[UploadFile], document_id: str, revision_no: str) -> dict:
    if not upload or not upload.filename:
        return {"file_name": None, "content_type": None, "file_size": 0, "storage_path": None}
    content = await upload.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Document file exceeds the 25 MB upload limit")
    suffix = Path(upload.filename).suffix.lower()
    safe_revision = re.sub(r"[^A-Za-z0-9_-]", "_", revision_no)
    folder = DOCUMENT_UPLOAD_DIR / document_id
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{safe_revision}_{uuid4().hex}{suffix}"
    destination = folder / stored_name
    destination.write_bytes(content)
    return {
        "file_name": upload.filename,
        "content_type": upload.content_type,
        "file_size": len(content),
        "storage_path": str(destination),
    }


async def document_detail(document: dict) -> dict:
    document_id = str(document["_id"])
    revisions = await revision_collection.find({"document_id": document_id}).sort("created_at", 1).to_list(length=1000)
    reviewers = await reviewer_collection.find({
        "document_id": document_id,
        "revision_id": document.get("current_revision_id"),
    }).sort("created_at", 1).to_list(length=1000)
    comments = await comment_collection.find({"document_id": document_id}).sort("created_at", 1).to_list(length=1000)
    return {
        **serialize(document),
        "revisions": [serialize(item) for item in revisions],
        "reviewers": [serialize(item) for item in reviewers],
        "comments": [serialize(item) for item in comments],
    }


@router.get("/ewp/documents-reviews/deliverables")
async def get_review_ready_deliverables():
    """Return Module 2 deliverables that can start document preparation."""
    deliverables = await deliverable_collection.find({"status": "READY_FOR_REVIEW"}).sort("updated_at", -1).to_list(length=10000)
    results = []
    for deliverable in deliverables:
        ewp = await ewp_collection.find_one({"_id": deliverable.get("ewp_id")})
        if not ewp:
            continue
        results.append({
            **serialize(deliverable),
            "ewp": {
                "id": str(ewp["_id"]),
                "code": ewp.get("ewp_code"),
                "name": ewp.get("ewp_name"),
                "discipline": ewp.get("discipline"),
            },
        })
    return results


@router.get("/ewp/documents-reviews/deliverables/{deliverable_id}/documents")
async def get_deliverable_documents(deliverable_id: str):
    await require_deliverable(deliverable_id)
    documents = await document_collection.find({"deliverable_id": deliverable_id}).sort("created_at", 1).to_list(length=1000)
    return [serialize(document) for document in documents]


@router.post(
    "/ewp/documents-reviews/deliverables/{deliverable_id}/documents",
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    deliverable_id: str,
    document_code: str = Form(...),
    title: str = Form(...),
    revision_no: str = Form("D01"),
    revision_note: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    deliverable = await require_deliverable(deliverable_id)
    document_code = document_code.strip()
    title = title.strip()
    revision_no = revision_no.strip()
    if not document_code or not title or not revision_no:
        raise HTTPException(status_code=400, detail="Document code, title, and revision are required")
    duplicate = await document_collection.find_one({"ewp_id": deliverable.get("ewp_id"), "document_code": document_code})
    if duplicate:
        raise HTTPException(status_code=409, detail=f"Document code '{document_code}' already exists in this EWP")
    timestamp = now_iso()
    document_id = str(uuid4())
    revision_id = str(uuid4())
    file_data = await save_upload(file, document_id, revision_no)
    document = {
        "_id": document_id,
        "ewp_id": str(deliverable.get("ewp_id")),
        "deliverable_id": deliverable_id,
        "engineering_work_item_id": str(deliverable.get("engineering_work_item_id")),
        "document_code": document_code,
        "title": title,
        "current_revision_id": revision_id,
        "current_revision_no": revision_no,
        "status": "DRAFT",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    revision = {
        "_id": revision_id,
        "document_id": document_id,
        "revision_no": revision_no,
        "revision_note": revision_note.strip() if revision_note else None,
        "status": "DRAFT",
        **file_data,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    await document_collection.insert_one(document)
    try:
        await revision_collection.insert_one(revision)
    except Exception:
        await document_collection.delete_one({"_id": document_id})
        if file_data.get("storage_path"):
            Path(file_data["storage_path"]).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Unable to persist the initial document revision")
    return await document_detail(document)


@router.get("/ewp/documents-reviews/documents/{document_id}")
async def get_document(document_id: str):
    return await document_detail(await require_document(document_id))


@router.get("/ewp/documents-reviews/documents/{document_id}/revisions/{revision_id}/file")
async def open_document_revision_file(document_id: str, revision_id: str):
    await require_document(document_id)
    revision = await revision_collection.find_one({"_id": revision_id, "document_id": document_id})
    if not revision:
        raise HTTPException(status_code=404, detail="Document revision not found")
    storage_path = revision.get("storage_path")
    if not storage_path or not Path(storage_path).is_file():
        raise HTTPException(status_code=404, detail="Uploaded document file not found")
    release = revision.get("release_record")
    if release:
        with Path(storage_path).open("rb") as stream:
            current_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if current_hash != release["package"]["file"]["sha256"]:
            raise HTTPException(409, "Released file integrity check failed")
    return FileResponse(
        path=storage_path,
        media_type=revision.get("content_type") or "application/octet-stream",
        filename=revision.get("file_name") or Path(storage_path).name,
    )


@router.post("/ewp/documents-reviews/documents/{document_id}/revisions")
async def create_document_revision(
    document_id: str,
    revision_no: str = Form(...),
    revision_note: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    document = await require_document(document_id)
    revision_no = revision_no.strip()
    if not revision_no:
        raise HTTPException(status_code=400, detail="Revision number is required")
    duplicate = await revision_collection.find_one({"document_id": document_id, "revision_no": revision_no})
    if duplicate:
        raise HTTPException(status_code=409, detail=f"Revision '{revision_no}' already exists for this document")
    timestamp = now_iso()
    revision_id = str(uuid4())
    file_data = await save_upload(file, document_id, revision_no)
    revision = {
        "_id": revision_id,
        "document_id": document_id,
        "revision_no": revision_no,
        "revision_note": revision_note.strip() if revision_note else None,
        "status": "REVISED",
        **file_data,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    await revision_collection.insert_one(revision)
    await document_collection.update_one(
        {"_id": document_id},
        {"$set": {
            "current_revision_id": revision_id,
            "current_revision_no": revision_no,
            "status": "REVISED",
            "updated_at": timestamp,
        }},
    )
    return await document_detail({
        **document,
        "current_revision_id": revision_id,
        "current_revision_no": revision_no,
        "status": "REVISED",
        "updated_at": timestamp,
    })


@router.post("/ewp/documents-reviews/documents/{document_id}/submit")
async def submit_document_for_review(document_id: str):
    document = await require_document(document_id)
    await require_editable_review(document)
    if document.get("status") not in {"DRAFT", "REVISED"}:
        raise HTTPException(status_code=409, detail="This document cannot be submitted from its current status")
    revision = await revision_collection.find_one({"_id": document.get("current_revision_id")})
    if not revision:
        raise HTTPException(status_code=409, detail="Current document revision was not found")
    if not revision.get("file_name"):
        raise HTTPException(status_code=409, detail="Upload a document file before submitting for review")
    timestamp = now_iso()
    await revision_collection.update_one({"_id": revision["_id"]}, {"$set": {"status": "SUBMITTED_FOR_REVIEW", "submitted_at": timestamp, "updated_at": timestamp}})
    await document_collection.update_one({"_id": document_id}, {"$set": {"status": "SUBMITTED_FOR_REVIEW", "updated_at": timestamp}})
    return await document_detail({**document, "status": "SUBMITTED_FOR_REVIEW", "updated_at": timestamp})


@router.post("/ewp/documents-reviews/documents/{document_id}/reviewers")
async def assign_document_reviewer(document_id: str, request: ReviewerCreate):
    document = await require_document(document_id)
    await require_editable_review(document)
    if document.get("status") not in {"SUBMITTED_FOR_REVIEW", "UNDER_REVIEW"}:
        raise HTTPException(status_code=409, detail="Submit the document before assigning reviewers")
    duplicate = await reviewer_collection.find_one({
        "document_id": document_id,
        "revision_id": document.get("current_revision_id"),
        "reviewer_name": request.reviewer_name.strip(),
        "reviewer_role": request.reviewer_role.strip(),
    })
    if duplicate:
        raise HTTPException(status_code=409, detail="This reviewer is already assigned to the current revision")
    timestamp = now_iso()
    assignment = {
        "_id": str(uuid4()),
        "document_id": document_id,
        "revision_id": str(document.get("current_revision_id")),
        "reviewer_name": request.reviewer_name.strip(),
        "reviewer_role": request.reviewer_role.strip(),
        "status": "PENDING",
        "decision": None,
        "decision_comment": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    await reviewer_collection.insert_one(assignment)
    await document_collection.update_one({"_id": document_id}, {"$set": {"status": "UNDER_REVIEW", "updated_at": timestamp}})
    return serialize(assignment)


@router.post("/ewp/documents-reviews/reviewers/{assignment_id}/decision")
async def record_review_decision(assignment_id: str, request: ReviewDecisionCreate):
    assignment = await reviewer_collection.find_one({"_id": assignment_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="Reviewer assignment not found")
    decision = request.decision.strip().upper()
    comment = request.comment.strip() if request.comment else None
    if decision not in DECISIONS:
        raise HTTPException(status_code=400, detail="Invalid technical review decision")
    if decision in {"ACCEPT_WITH_COMMENT", "CHANGE_REQUIRED", "REJECT"} and not comment:
        raise HTTPException(status_code=400, detail="A reviewer comment is required for this decision")
    document = await require_document(str(assignment.get("document_id")))
    await require_editable_review(document, str(assignment.get("revision_id")))
    if str(document.get("current_revision_id")) != str(assignment.get("revision_id")):
        raise HTTPException(status_code=409, detail="This reviewer assignment belongs to an older revision")
    timestamp = now_iso()
    decision_record = {
        "_id": str(uuid4()),
        "assignment_id": assignment_id,
        "document_id": str(assignment.get("document_id")),
        "revision_id": str(assignment.get("revision_id")),
        "decision": decision,
        "comment": comment,
        "decided_at": timestamp,
    }
    await decision_collection.insert_one(decision_record)
    await reviewer_collection.update_one(
        {"_id": assignment_id},
        {"$set": {"status": "COMPLETED", "decision": decision, "decision_comment": comment, "updated_at": timestamp}},
    )
    next_status = "CHANGE_REQUIRED" if decision in {"CHANGE_REQUIRED", "REJECT"} else "UNDER_REVIEW"
    await document_collection.update_one({"_id": document["_id"]}, {"$set": {"status": next_status, "updated_at": timestamp}})
    return serialize({**assignment, "status": "COMPLETED", "decision": decision, "decision_comment": comment, "updated_at": timestamp})


@router.post("/ewp/documents-reviews/documents/{document_id}/comments")
async def create_review_comment(document_id: str, request: ReviewCommentCreate):
    document = await require_document(document_id)
    await require_editable_review(document)
    timestamp = now_iso()
    comment = {
        "_id": str(uuid4()),
        "document_id": document_id,
        "revision_id": str(document.get("current_revision_id")),
        "text": request.text.strip(),
        "raised_by": request.raised_by.strip(),
        "markup_reference": request.markup_reference.strip() if request.markup_reference else None,
        "status": "OPEN",
        "response": None,
        "responded_by": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    await comment_collection.insert_one(comment)
    return serialize(comment)


@router.patch("/ewp/documents-reviews/comments/{comment_id}/response")
async def respond_to_review_comment(comment_id: str, request: CommentResponseUpdate):
    comment = await comment_collection.find_one({"_id": comment_id})
    if not comment:
        raise HTTPException(status_code=404, detail="Review comment not found")
    document = await require_document(comment["document_id"])
    await require_editable_review(document, comment.get("revision_id"))
    timestamp = now_iso()
    patch = {
        "response": request.response.strip(),
        "responded_by": request.responded_by,
        "status": "CLOSED" if request.close else "OPEN",
        "updated_at": timestamp,
        "closed_at": timestamp if request.close else None,
    }
    await comment_collection.update_one({"_id": comment_id}, {"$set": patch})
    return serialize({**comment, **patch})


@router.post("/ewp/documents-reviews/documents/{document_id}/comments/close-all")
async def close_all_review_comments(document_id: str):
    document = await require_document(document_id)
    await require_editable_review(document)
    timestamp = now_iso()
    comments = await comment_collection.find({"document_id": document_id, "status": "OPEN",
                                             "response": {"$nin": [None, ""]}}).to_list(length=None)
    for comment in comments:
        await require_editable_review(document, comment.get("revision_id"))
    result = await comment_collection.update_many({"_id": {"$in": [row["_id"] for row in comments]}},
        {"$set": {"status": "CLOSED", "closed_at": timestamp, "updated_at": timestamp}})
    return {"document_id": document_id, "closed_count": result.modified_count}


@router.post("/ewp/documents-reviews/documents/{document_id}/complete-review")
async def complete_document_review(document_id: str):
    document = await require_document(document_id)
    await require_editable_review(document)
    if document.get("status") not in {"UNDER_REVIEW", "SUBMITTED_FOR_REVIEW"}:
        raise HTTPException(409, "Submit the current revision and complete its technical review first")
    assignments = await reviewer_collection.find({
        "document_id": document_id,
        "revision_id": document.get("current_revision_id"),
    }).to_list(length=1000)
    if not assignments:
        raise HTTPException(status_code=409, detail="Assign at least one reviewer before completing review")
    if any(item.get("status") != "COMPLETED" for item in assignments):
        raise HTTPException(status_code=409, detail="Every assigned reviewer must complete a decision")
    if any(item.get("decision") in {"CHANGE_REQUIRED", "REJECT"} for item in assignments):
        raise HTTPException(status_code=409, detail="Resolve blocking review decisions through a new revision")
    open_comments = await comment_collection.count_documents({"document_id": document_id, "status": "OPEN"})
    if open_comments:
        raise HTTPException(status_code=409, detail="Close all review comments before completing review")
    timestamp = now_iso()
    await revision_collection.update_one({"_id": document.get("current_revision_id")}, {"$set": {"status": "REVIEW_COMPLETED", "review_completed_at": timestamp, "updated_at": timestamp}})
    await document_collection.update_one({"_id": document_id}, {"$set": {"status": "REVIEW_COMPLETED", "review_completed_at": timestamp, "updated_at": timestamp}})
    return await document_detail({**document, "status": "REVIEW_COMPLETED", "review_completed_at": timestamp, "updated_at": timestamp})


@router.get("/ewp/documents-reviews/review-completed-documents")
async def get_review_completed_documents():
    documents = await document_collection.find({"status": "REVIEW_COMPLETED"}).sort("review_completed_at", -1).to_list(length=10000)
    return [serialize(document) for document in documents]
