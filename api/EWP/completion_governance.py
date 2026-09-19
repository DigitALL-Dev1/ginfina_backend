"""Completion gates derived from persisted EWP records; no startup initialization.

The EWP holds the atomic completion state. The four reporting collections are
idempotent projections, repaired on subsequent reads after interrupted writes.
Actors are explicitly self-declared in the existing unauthenticated pilot.
"""
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator
from . import documents_reviews as documents
from .approval_release import digest

router = APIRouter(prefix="/ewp/completion-governance")
db = documents.db


class Action(BaseModel):
    version: int = Field(..., ge=0)
    actor: str = Field(..., min_length=1, max_length=200)
    comment: str = Field(..., min_length=1, max_length=5000)

    @validator("actor", "comment")
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("A value is required")
        return value.strip()


class Verification(Action):
    summary_hash: str = Field(..., min_length=64, max_length=64)


class Resolution(Action):
    obligation_id: str
    source_hash: str
    status: Literal["CLOSED", "ACCEPTED"]


class ActionCreate(Action):
    title: str = Field(..., min_length=1, max_length=500)

    @validator("title")
    def title_required(cls, value):
        if not value.strip():
            raise ValueError("An action title is required")
        return value.strip()


async def rows(name, query):
    return await db[name].find(query).sort("_id", 1).to_list(length=None)


async def require_ewp(identity):
    row = await db["ewp"].find_one({"_id": identity})
    if not row:
        raise HTTPException(404, "EWP not found")
    return row


def control(ewp):
    return ewp.get("completion_control") or {"version": 0, "completion_status": "ACTIVE", "actions": [], "resolutions": [], "history": []}


async def project(ewp):
    state = control(ewp)
    if not state["version"]:
        return
    base = {"ewp_id": str(ewp["_id"]), "version": state["version"]}
    async def put(collection, identity, data):
        data = {**base, **data}
        await db[collection].update_one({"_id": identity}, {"$setOnInsert": data}, upsert=True)
        await db[collection].update_one({"_id": identity, "version": {"$lte": state["version"]}}, {"$set": data})
    await put("ewp_completion", ewp["_id"], state)
    for check in state.get("checks", []):
        await put("ewp_completion_check", f"{ewp['_id']}:{check['id']}", check)
    for event in state.get("history", []):
        await put("ewp_governance_check", event["id"], event)
    if state.get("closure"):
        await db["ewp_closure"].update_one({"_id": ewp["_id"]},
            {"$setOnInsert": {"ewp_id": ewp["_id"], **state["closure"]}}, upsert=True)


async def summary(ewp):
    state = control(ewp)
    if state.get("closure"):
        return {**state["closure"]["summary"], "ewp": documents.serialize({k: v for k, v in ewp.items() if k != "completion_control"}), "control": state,
                "completion_status": "CLOSED", "governance_valid": True}
    eid = str(ewp["_id"])
    work = await rows("ewp_engineering_work", {"ewp_id": eid})
    deliverables = await rows("ewp_deliverable", {"ewp_id": eid})
    docs = await rows("ewp_document", {"ewp_id": eid})
    doc_ids = [d["_id"] for d in docs]
    revisions = await rows("ewp_document_revision", {"document_id": {"$in": doc_ids}})
    comments = await rows("ewp_document_review_comment", {"document_id": {"$in": doc_ids}})
    reviewers = await rows("ewp_document_reviewer", {"document_id": {"$in": doc_ids}})
    registers = await rows("ewp_quantity_register", {"ewp_id": eid})
    links = await rows("ewp_seb_input", {"ewp_id": eid})
    frozen = await db["seb_ewp_frozen_item"].find_one({"_id": ewp.get("freeze_snapshot_id")})
    revision_by_id = {r["_id"]: r for r in revisions}
    checks = []
    def check(identity, kind, name, issues, total, mandatory=True):
        checks.append({"id": identity, "check_type": kind, "check_name": name, "mandatory": mandatory,
            "status": "FAILED" if issues else "PASSED", "issue_count": len(issues),
            "total": total, "remarks": f"{len(issues)} issue(s)" if issues else "Requirements satisfied",
            "issues": issues})
    def label(row):
        return row.get("work_code") or row.get("code") or row.get("document_code") or row.get("name") or str(row["_id"])
    required_work = [w for w in work if w.get("mandatory", True)]
    check("work", "ENGINEERING_WORK", "Required engineering work completed",
          [f"{label(w)}: {w.get('status', 'unknown')}" for w in required_work if w.get("status") != "COMPLETED"]
          + ([] if required_work else ["No required engineering work recorded"]), len(required_work))
    required_deliverables = [d for d in deliverables if d.get("mandatory", True)]
    deliverable_issues = []
    for d in required_deliverables:
        linked = [doc for doc in docs if doc.get("deliverable_id") == d["_id"]]
        if not linked or any(revision_by_id.get(doc.get("current_revision_id"), {}).get("status") != "RELEASED" for doc in linked):
            deliverable_issues.append(f"{label(d)}: required document release incomplete")
    check("deliverables", "DELIVERABLES", "Mandatory deliverables released", deliverable_issues
          + ([] if required_deliverables else ["No mandatory deliverables recorded"]), len(required_deliverables))
    review_issues, approval_issues = [], []
    obligations = []
    def obligation(identity, kind, title, source):
        record = {"id": identity, "kind": kind, "title": title, "source": documents.json_safe(source)}
        record["source_hash"] = digest(record)
        resolution = next((r for r in reversed(state.get("resolutions", [])) if r["obligation_id"] == identity
                           and r["source_hash"] == record["source_hash"]), None)
        record.update(status=resolution["status"] if resolution else "OPEN", resolution=resolution)
        obligations.append(record)
    for doc in docs:
        rev = revision_by_id.get(doc.get("current_revision_id"), {})
        assignments = [r for r in reviewers if r.get("revision_id") == rev.get("_id")]
        if rev.get("status") not in {"REVIEW_COMPLETED", "READY_FOR_RELEASE", "RELEASED"} or not assignments or any(
                r.get("status") != "COMPLETED" or r.get("decision") not in {"ACCEPT", "ACCEPT_WITH_COMMENT"} for r in assignments):
            review_issues.append(f"{label(doc)}: current revision review incomplete")
        release = rev.get("release_record") or {}
        approval = rev.get("approval") or {}
        if rev.get("status") != "RELEASED" or release.get("status") != "RELEASED" or release.get("revision_id") != rev.get("_id") or release.get("ewp_id") != eid or approval.get("decision") not in {"APPROVE", "APPROVE_WITH_CONDITION"}:
            approval_issues.append(f"{label(doc)}: approved release record missing for current revision")
        if approval.get("decision") == "APPROVE_WITH_CONDITION":
            obligation(f"approval:{rev['_id']}", "CONDITION", approval.get("condition") or "Approval condition requires resolution",
                       {"document_id": doc["_id"], "revision_id": rev["_id"], "approval": approval})
    check("reviews", "DOCUMENT_REVIEW", "Required technical reviews completed", review_issues + ([] if docs else ["No engineering documents recorded"]), len(docs))
    check("comments", "DOCUMENT_REVIEW", "No unresolved review comments", [f"{c['_id']}: {c.get('text', 'Open comment')}" for c in comments if c.get("status") != "CLOSED"], len(comments))
    check("releases", "APPROVAL_RELEASE", "Current document revisions approved and released", approval_issues + ([] if docs else ["No engineering releases recorded"]), len(docs))
    quantity_issues, procurement_issues = [], []
    for reg in registers:
        boq = next((b for b in reg.get("boqs", []) if b.get("id") == reg.get("current_boq_id")), {})
        if reg.get("status") not in {"APPROVED", "PROCUREMENT_READY", "HANDOFF_REFERENCED"} or not reg.get("items") or (boq.get("approval") or {}).get("decision") != "APPROVE" or boq.get("content_hash") != digest(reg.get("items", [])):
            quantity_issues.append(f"{label(reg)}: current BOQ / EBOM not approved")
        for item in reg.get("items", []):
            source = item.get("source") or {}
            source_revision = revision_by_id.get(source.get("revision_id"), {})
            release = source_revision.get("release_record") or {}
            if source_revision.get("status") != "RELEASED" or release.get("ewp_id") != eid or not source.get("release_id") or release.get("id") != source.get("release_id") or release.get("release_hash") != source.get("release_hash"):
                quantity_issues.append(f"{label(reg)}: quantity source no longer matches its controlled release")
        handoff = reg.get("handoff") or {}
        if handoff.get("status") != "COMPLETED" or handoff.get("boq_id") != boq.get("id") or not handoff.get("reference"):
            procurement_issues.append(f"{label(reg)}: procurement handoff incomplete")
    check("quantities", "QUANTITIES", "BOQ / EBOM approved", quantity_issues + ([] if registers else ["No quantity register recorded"]), len(registers))
    check("procurement", "PROCUREMENT", "Procurement handoff completed", procurement_issues + ([] if registers else ["No procurement handoff recorded"]), len(registers))
    basis_issues = []
    if not frozen or frozen.get("status") != "RELEASED" or not links:
        basis_issues.append("Released SEB input basis is missing")
    frozen_items = {str(i.get("release_item_id") or i.get("seb_item_id") or i.get("id")): i for i in (frozen or {}).get("released_seb_items", [])}
    for link in links:
        item = frozen_items.get(str(link.get("release_item_id")))
        if not item or link.get("freeze_snapshot_id") != ewp.get("freeze_snapshot_id"):
            basis_issues.append(f"Selected input {link['_id']} is missing from the frozen release")
            continue
        readiness = item.get("readiness") or item.get("discipline_readiness") or {}
        readiness = readiness if isinstance(readiness, dict) else {"status": readiness}
        for key, kind, text in [("conditional", "CONDITION", "condition"), ("blocked", "BLOCKER", "blocker")]:
            detail = readiness.get(key) or {}
            detail = detail if isinstance(detail, dict) else {"enabled": bool(detail)}
            if detail.get("enabled") or readiness.get("status") == ("CONDITIONAL" if key == "conditional" else "BLOCKED"):
                obligation(f"input:{link['_id']}:{key}", kind, detail.get(text) or readiness.get(text) or f"SEB input {kind.lower()}",
                           {"release_item_id": link.get("release_item_id"), "readiness": readiness, "freeze_snapshot_id": ewp.get("freeze_snapshot_id")})
    check("basis", "CONDITIONS", "Frozen SEB basis available", basis_issues, len(links))
    for action in state.get("actions", []):
        obligation(action["id"], "ACTION", action["title"], action)
    for identity, kind, title in [("conditions", "CONDITION", "Conditions closed or formally accepted"), ("blockers", "BLOCKER", "No open blockers"), ("actions", "ACTION", "No outstanding actions")]:
        selected = [o for o in obligations if o["kind"] == kind]
        check(identity, "CONDITIONS" if kind != "ACTION" else "ACTIONS", title, [o["title"] for o in selected if o["status"] == "OPEN"], len(selected))
    source_hash = digest({"ewp": {k: v for k, v in ewp.items() if k not in {"completion_control", "status", "updated_at"}}, "work": work, "deliverables": deliverables, "documents": docs, "revisions": revisions,
        "comments": comments, "reviewers": reviewers, "registers": registers, "links": links, "frozen": frozen,
        "actions": state.get("actions", []), "resolutions": state.get("resolutions", [])})
    blockers = [c for c in checks if c["mandatory"] and c["status"] == "FAILED"]
    valid = bool(state.get("governance") and state["governance"]["summary_hash"] == source_hash and not blockers)
    return {"ewp": documents.serialize({k: v for k, v in ewp.items() if k != "completion_control"}), "control": state,
        "checks": checks, "obligations": obligations, "blockers": blockers, "summary_hash": source_hash,
        "sources": {"engineering_work_ids": [w["_id"] for w in work], "deliverable_ids": [d["_id"] for d in deliverables],
            "documents": [{"document_id": d["_id"], "revision_id": d.get("current_revision_id"),
                "release_id": (revision_by_id.get(d.get("current_revision_id"), {}).get("release_record") or {}).get("id")} for d in docs],
            "registers": [{"register_id": r["_id"], "boq_id": r.get("current_boq_id"), "handoff": r.get("handoff")} for r in registers],
            "freeze_snapshot_id": ewp.get("freeze_snapshot_id"), "release_item_ids": [l.get("release_item_id") for l in links]},
        "governance_valid": valid, "ready_for_closure": not blockers,
        "completion_status": "BLOCKED" if blockers else "COMPLETION_REVIEW" if state["completion_status"] == "COMPLETION_REVIEW" and valid else "READY_FOR_CLOSURE"}


def writable(ewp, request):
    state = control(ewp)
    if ewp.get("status") == "CLOSED" or state.get("closure"):
        raise HTTPException(409, "This EWP is closed")
    if state["version"] != request.version:
        raise HTTPException(409, "Completion records changed. Refresh before saving")
    return state


async def save(ewp, state, request, action, checks=None, ewp_status=None):
    previous = control(ewp)
    timestamp = documents.now_iso()
    state = {**state, "version": previous["version"] + 1, "updated_at": timestamp,
             "checks": checks if checks is not None else previous.get("checks", []),
             "history": previous.get("history", []) + [{"id": str(uuid4()), "action": action,
                 "actor": request.actor, "comment": request.comment, "at": timestamp, "actor_mode": "PROTOTYPE_PILOT"}]}
    query = {"_id": ewp["_id"], "completion_control.version": previous["version"]} if previous["version"] else {"_id": ewp["_id"], "completion_control": {"$exists": False}}
    patch = {"completion_control": state, "updated_at": timestamp}
    if ewp_status:
        patch["status"] = ewp_status
    result = await db["ewp"].update_one(query, {"$set": patch})
    if not result.matched_count:
        raise HTTPException(409, "Completion records changed. Refresh before saving")
    latest = {**ewp, **patch}
    await project(latest)
    return await summary(latest)


def require_ready(result):
    if result["blockers"]:
        raise HTTPException(409, {"message": "EWP cannot close: mandatory checks failed", "blockers": result["blockers"]})


@router.get("/ewps")
async def list_ewps():
    return [{"id": str(e["_id"]), "code": e.get("ewp_code"), "name": e.get("ewp_name"), "status": e.get("status")} for e in await rows("ewp", {})]


@router.get("/ewps/{ewp_id}/summary")
async def get_summary(ewp_id: str):
    ewp = await require_ewp(ewp_id)
    await project(ewp)
    return await summary(ewp)


@router.post("/ewps/{ewp_id}/actions")
async def create_action(ewp_id: str, request: ActionCreate):
    ewp = await require_ewp(ewp_id); state = writable(ewp, request)
    action = {"id": str(uuid4()), "title": request.title, "raised_by": request.actor, "comment": request.comment, "created_at": documents.now_iso()}
    return await save(ewp, {**state, "actions": state.get("actions", []) + [action], "governance": None, "completion_status": "ACTIVE"}, request, "ACTION_RAISED")


@router.post("/ewps/{ewp_id}/resolutions")
async def resolve_obligation(ewp_id: str, request: Resolution):
    ewp = await require_ewp(ewp_id); state = writable(ewp, request)
    result = await summary(ewp)
    obligation = next((o for o in result["obligations"] if o["id"] == request.obligation_id), None)
    if not obligation or obligation["source_hash"] != request.source_hash:
        raise HTTPException(409, "The source obligation changed or does not belong to this EWP")
    if request.status == "ACCEPTED" and obligation["kind"] != "CONDITION":
        raise HTTPException(400, "Actions and blockers must be closed; only conditions can be formally accepted")
    record = {**request.model_dump(exclude={"version"}), "at": documents.now_iso(), "actor_mode": "PROTOTYPE_PILOT"}
    return await save(ewp, {**state, "resolutions": state.get("resolutions", []) + [record], "governance": None, "completion_status": "ACTIVE"}, request, "OBLIGATION_RESOLVED")


@router.post("/ewps/{ewp_id}/governance")
async def verify_governance(ewp_id: str, request: Verification):
    ewp = await require_ewp(ewp_id); state = writable(ewp, request)
    result = await summary(ewp); require_ready(result)
    if result["summary_hash"] != request.summary_hash:
        raise HTTPException(409, "Source records changed. Reload and review the completion summary")
    record = {"reviewer": request.actor, "comment": request.comment, "at": documents.now_iso(), "summary_hash": result["summary_hash"], "actor_mode": "PROTOTYPE_PILOT"}
    return await save(ewp, {**state, "governance": record, "completion_status": "READY_FOR_CLOSURE"}, request, "GOVERNANCE_VERIFIED", result["checks"])


@router.post("/ewps/{ewp_id}/submit")
async def submit_completion(ewp_id: str, request: Action):
    ewp = await require_ewp(ewp_id); state = writable(ewp, request)
    result = await summary(ewp); require_ready(result)
    if not result["governance_valid"]:
        raise HTTPException(409, "Run governance checks against the current source records first")
    if state["completion_status"] == "COMPLETION_REVIEW":
        raise HTTPException(409, "Already submitted for closure")
    return await save(ewp, {**state, "completion_status": "COMPLETION_REVIEW", "submitted_by": request.actor,
        "submitted_at": documents.now_iso()}, request, "SUBMITTED", result["checks"], "COMPLETION_REVIEW")


@router.post("/ewps/{ewp_id}/close")
async def close_ewp(ewp_id: str, request: Action):
    ewp = await require_ewp(ewp_id)
    # Recover a previous successful closure without creating duplicate records.
    if control(ewp).get("closure"):
        await project(ewp)
        return await summary(ewp)
    state = writable(ewp, request)
    result = await summary(ewp); require_ready(result)
    if state["completion_status"] != "COMPLETION_REVIEW" or not result["governance_valid"]:
        raise HTTPException(409, "Submit the current verified completion summary before approving closure")
    timestamp = documents.now_iso()
    snapshot = {key: value for key, value in result.items() if key not in {"control", "ewp"}}
    closure = {"approved_by": request.actor, "approved_at": timestamp, "closed_at": timestamp,
        "comment": request.comment, "actor_mode": "PROTOTYPE_PILOT", "summary": snapshot, "snapshot_hash": digest(snapshot)}
    return await save(ewp, {**state, "completion_status": "CLOSED", "approved_by": request.actor,
        "approved_at": timestamp, "closed_at": timestamp, "closure": closure}, request, "CLOSED", result["checks"], "CLOSED")
