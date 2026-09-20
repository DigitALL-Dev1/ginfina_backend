"""Cross-EWP management workspace. No startup writes or collection initialization.

The EWP management_control aggregate provides atomic changes with reconstructable
before/after audit events. Named collections are idempotent reporting projections.
"""
from datetime import date, timedelta
from typing import Literal, Optional
from uuid import uuid4
from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from . import documents_reviews as documents

router = APIRouter(prefix="/ewp/management-administration")
db = documents.db
Kind = Literal["team", "milestones", "issues", "risks", "actions", "access"]
COLLECTIONS = {"team": "ewp_team_member", "milestones": "ewp_milestone", "issues": "ewp_issue",
               "risks": "ewp_risk", "actions": "ewp_action", "access": "ewp_access"}


class StrictModel(BaseModel):
    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class ActorWrite(StrictModel):
    version: int = Field(..., ge=0)
    actor: str = Field(..., min_length=1, max_length=200)
    comment: str = Field(..., min_length=1, max_length=5000)


class RecordWrite(ActorWrite):
    data: dict


class Team(StrictModel):
    user_id: str = Field(..., min_length=1)
    role: Literal["Lead Engineer", "Design Engineer", "Engineer", "Reviewer", "Approver", "Consultant"]
    discipline: str = Field(..., min_length=1, max_length=100)
    organization: str = Field("", max_length=200)
    assignment: str = Field("", max_length=2000)
    active: bool = True


class Milestone(StrictModel):
    name: str = Field(..., min_length=1, max_length=200)
    target_date: date
    owner: str = Field(..., min_length=1, max_length=200)
    status: Literal["UPCOMING", "IN_PROGRESS", "COMPLETE"] = "UPCOMING"
    note: str = Field("", max_length=5000)


class ControlItem(StrictModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field("", max_length=5000)
    owner: str = Field(..., min_length=1, max_length=200)
    due_date: date
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    status: Literal["OPEN", "IN_PROGRESS", "CLOSED"] = "OPEN"
    blocking: bool = True
    resolution: str = Field("", max_length=5000)

    @model_validator(mode="after")
    def closed_requires_evidence(self):
        if self.status == "CLOSED" and not self.resolution:
            raise ValueError("Add a resolution / evidence reference before closing this record")
        return self


class Access(StrictModel):
    user_id: str = Field(..., min_length=1)
    permissions: list[Literal["VIEW", "EDIT", "REVIEW", "APPROVE", "ADMIN"]] = Field(..., min_length=1)
    active: bool = True

    @field_validator("permissions")
    @classmethod
    def unique_permissions(cls, value):
        return sorted(set(value))


class Settings(ActorWrite):
    discipline: str = Field(..., min_length=1, max_length=100)
    planned_start: Optional[date] = None
    planned_finish: Optional[date] = None
    status: Optional[Literal["DRAFT", "NOT_STARTED", "IN_PROGRESS", "ON_HOLD", "READY_FOR_OUTPUT", "COMPLETED"]] = None

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.planned_start and self.planned_finish and self.planned_finish < self.planned_start:
            raise ValueError("Planned finish cannot precede planned start")
        return self


SCHEMAS = {"team": Team, "milestones": Milestone, "issues": ControlItem, "risks": ControlItem, "actions": ControlItem, "access": Access}


async def rows(name, query):
    return await db[name].find(query).sort("_id", 1).to_list(length=None)


def state_of(ewp):
    return ewp.get("management_control") or {"version": 0, **{key: [] for key in COLLECTIONS}, "history": []}


async def require_ewp(identity):
    ewp = await db["ewp"].find_one({"_id": identity})
    if not ewp:
        raise HTTPException(404, "EWP not found")
    return ewp


def check_write(ewp, request):
    if ewp.get("status") == "CLOSED" or (ewp.get("completion_control") or {}).get("closure"):
        raise HTTPException(409, "This EWP is closed. Management records are read-only")
    state = state_of(ewp)
    if request.version != state["version"]:
        raise HTTPException(409, "Management records changed. Refresh before saving")
    return state


async def project(ewp):
    state = state_of(ewp)
    for kind, collection in COLLECTIONS.items():
        for record in state[kind]:
            data = {**record, "ewp_id": str(ewp["_id"]), "management_version": state["version"]}
            await db[collection].update_one({"_id": record["id"]}, {"$setOnInsert": data}, upsert=True)
            await db[collection].update_one({"_id": record["id"], "management_version": {"$lte": state["version"]}}, {"$set": data})
    for event in state["history"]:
        await db["ewp_activity_log"].update_one({"_id": event["id"]},
            {"$setOnInsert": {**event, "ewp_id": str(ewp["_id"])}}, upsert=True)


async def commit(ewp, state, request, action, before, after, patch=None):
    old = state_of(ewp)
    timestamp = documents.now_iso()
    event = {"id": str(uuid4()), "action": action, "actor": request.actor, "comment": request.comment,
        "at": timestamp, "before": before, "after": after, "actor_mode": "PROTOTYPE_PILOT"}
    state = {**state, "version": old["version"] + 1, "history": old["history"] + [event]}
    query = {"_id": ewp["_id"], "status": {"$ne": "CLOSED"}}
    query.update({"management_control.version": old["version"]} if old["version"] else {"management_control": {"$exists": False}})
    completion = ewp.get("completion_control")
    query.update({"completion_control.version": completion["version"]} if completion else {"completion_control": {"$exists": False}})
    changes = {**(patch or {}), "management_control": state, "updated_at": timestamp}
    result = await db["ewp"].update_one(query, {"$set": changes})
    if not result.matched_count:
        raise HTTPException(409, "The EWP or completion review changed. Refresh before saving")
    latest = {**ewp, **changes}
    await project(latest)
    return await overview(latest)


async def user_name(identity, active=True):
    ids = [identity] + ([ObjectId(identity)] if ObjectId.is_valid(identity) else [])
    user = await db["users"].find_one({"_id": {"$in": ids}})
    if not user or (active and user.get("is_active") is False):
        raise HTTPException(400, "Select an active user")
    return user.get("name") or user.get("email") or str(user["_id"])


@router.get("/projects")
async def list_projects():
    projects = await rows("ginfina_project", {})
    ewps = await rows("ewp", {})
    return [{"id": str(p["_id"]), "code": p.get("project_code"), "name": p.get("project_name"),
        "ewp_count": sum(str(e.get("project_id")) == str(p["_id"]) for e in ewps)} for p in projects]


@router.get("/ewps")
async def list_ewps(project_id: str):
    return [{"id": str(e["_id"]), "code": e.get("ewp_code"), "name": e.get("ewp_name"), "status": e.get("status")}
            for e in await rows("ewp", {"project_id": project_id})]


@router.get("/users")
async def list_users():
    users = await db["users"].find({"is_active": {"$ne": False}}, {"name": 1, "email": 1}).sort("name", 1).to_list(length=None)
    return [{"id": str(u["_id"]), "name": u.get("name") or u.get("email") or str(u["_id"])} for u in users]


@router.get("/ewps/{ewp_id}/overview")
async def get_overview(ewp_id: str):
    ewp = await require_ewp(ewp_id)
    await project(ewp)
    return await overview(ewp)


async def overview(ewp):
    eid = str(ewp["_id"]); state = state_of(ewp)
    work = await rows("ewp_engineering_work", {"ewp_id": eid})
    deliverables = await rows("ewp_deliverable", {"ewp_id": eid})
    docs = await rows("ewp_document", {"ewp_id": eid})
    doc_ids = [d["_id"] for d in docs]
    revisions = await rows("ewp_document_revision", {"document_id": {"$in": doc_ids}})
    reviewers = await rows("ewp_document_reviewer", {"document_id": {"$in": doc_ids}})
    comments = await rows("ewp_document_review_comment", {"document_id": {"$in": doc_ids}})
    registers = await rows("ewp_quantity_register", {"ewp_id": eid})
    current = {d["_id"]: next((r for r in revisions if r["_id"] == d.get("current_revision_id") and r["document_id"] == d["_id"]), {}) for d in docs}
    released = {d["_id"] for d in docs if current[d["_id"]].get("status") == "RELEASED" and
        (current[d["_id"]].get("release_record") or {}).get("status") == "RELEASED" and
        (current[d["_id"]].get("release_record") or {}).get("revision_id") == current[d["_id"]].get("_id")}
    def reviewed(doc):
        revision = current[doc["_id"]]
        assigned = [r for r in reviewers if r.get("revision_id") == revision.get("_id")]
        return revision.get("status") in {"REVIEW_COMPLETED", "READY_FOR_RELEASE", "RELEASED"} and bool(assigned) and all(
            r.get("status") == "COMPLETED" and r.get("decision") in {"ACCEPT", "ACCEPT_WITH_COMMENT"} for r in assigned)
    def metric(label, complete, total):
        return {"label": label, "complete": complete, "total": total, "percent": round(complete / total * 100) if total else 0}
    metrics = [metric("Engineering Work", sum(w.get("status") in {"READY_FOR_OUTPUT", "COMPLETED"} for w in work), len(work)),
        metric("Deliverables Prepared", sum(d.get("status") in {"READY_FOR_REVIEW", "COMPLETED", "RELEASED"} for d in deliverables), len(deliverables)),
        metric("Document Reviews", sum(reviewed(d) for d in docs), len(docs)),
        metric("Released Outputs", len(released), len(docs)),
        metric("Procurement Handoff", sum((r.get("handoff") or {}).get("status") == "COMPLETED" and
            (r.get("handoff") or {}).get("boq_id") == r.get("current_boq_id") and bool((r.get("handoff") or {}).get("reference")) for r in registers), len(registers))]
    today = date.today(); upcoming_until = today + timedelta(days=30)
    def date_value(value):
        try: return date.fromisoformat(str(value)[:10])
        except (ValueError, TypeError): return None
    def overdue(value):
        parsed = date_value(value)
        return bool(parsed and parsed < today)
    attention = []
    for w in work:
        if w.get("status") not in {"READY_FOR_OUTPUT", "COMPLETED"} and overdue(w.get("planned_finish")):
            attention.append({"kind": "OVERDUE_WORK", "title": w.get("title") or w.get("work_code"), "owner": ", ".join(w.get("assigned_engineers", [])), "date": w.get("planned_finish"), "status": w.get("status")})
    for d in docs:
        rev = current[d["_id"]]; state_name = rev.get("status")
        if state_name in {"SUBMITTED_FOR_REVIEW", "UNDER_REVIEW", "CHANGE_REQUIRED"}:
            attention.append({"kind": "PENDING_REVIEW", "title": f"{d.get('document_code')} / {rev.get('revision_no')}", "status": state_name})
        if state_name == "REVIEW_COMPLETED":
            attention.append({"kind": "PENDING_APPROVAL", "title": f"{d.get('document_code')} / {rev.get('revision_no')}", "status": state_name})
    for d in deliverables:
        due = date_value(d.get("planned_issue_date"))
        linked = [doc for doc in docs if doc.get("deliverable_id") == d["_id"]]
        if due and today <= due <= upcoming_until and not (linked and all(doc["_id"] in released for doc in linked)):
            attention.append({"kind": "UPCOMING_DELIVERABLE", "title": d.get("name") or d.get("code"), "owner": d.get("responsible_engineer"), "date": d.get("planned_issue_date"), "status": d.get("status")})
    counts = {"open_" + kind: sum(row["status"] != "CLOSED" for row in state[kind]) for kind in ["issues", "risks", "actions"]}
    counts["overdue_actions"] = sum(row["status"] != "CLOSED" and overdue(row.get("due_date")) for row in state["actions"])
    counts.update({key.lower(): sum(a["kind"] == key for a in attention) for key in ["OVERDUE_WORK", "PENDING_REVIEW", "PENDING_APPROVAL", "UPCOMING_DELIVERABLE"]})
    counts["open_review_comments"] = sum(c.get("status") != "CLOSED" for c in comments)
    history = [{**event, "module": "Management"} for event in state["history"]]
    history.extend({**event, "module": "Completion & Governance"} for event in (ewp.get("completion_control") or {}).get("history", []))
    for reg in registers:
        history.extend({**event, "id": f"quantity:{reg['_id']}:{i}", "module": "Quantities & Procurement"} for i, event in enumerate(reg.get("history", [])))
    for rev in revisions:
        for key, when, actor, title in [("approval", "decided_at", "approver", "DOCUMENT_APPROVAL"), ("release_record", "released_at", "released_by", "DOCUMENT_RELEASED")]:
            record = rev.get(key) or {}
            if record.get(when):
                history.append({"id": f"{key}:{rev['_id']}", "at": record[when], "actor": record.get(actor) or record.get("recorded_by"),
                    "action": title, "comment": record.get("comment"), "module": "Approval & Release", "revision_id": str(rev["_id"])})
    history.sort(key=lambda h: str(h.get("at") or ""), reverse=True)
    active_metrics = [m["percent"] for m in metrics if m["total"]]
    return {"ewp": documents.serialize({k: v for k, v in ewp.items() if k not in {"management_control", "completion_control"}}),
        "version": state["version"], **{k: state[k] for k in COLLECTIONS}, "metrics": metrics,
        "overall_progress": round(sum(active_metrics) / len(active_metrics)) if active_metrics else 0,
        "counts": counts, "attention": attention, "history": documents.json_safe(history),
        "read_only": ewp.get("status") == "CLOSED" or bool((ewp.get("completion_control") or {}).get("closure")),
        "access_mode": "PROTOTYPE_PILOT"}


async def write_record(ewp_id, kind, request, record_id=None):
    ewp = await require_ewp(ewp_id); state = check_write(ewp, request)
    old = next((r for r in state[kind] if r["id"] == record_id), None)
    if record_id and not old:
        raise HTTPException(404, "This management record does not belong to the selected EWP")
    try: data = SCHEMAS[kind](**request.data).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(422, [{"loc": ["body", "data", *e["loc"]], "msg": e["msg"], "type": e["type"]} for e in exc.errors()])
    if kind in {"team", "access"}:
        data["name"] = await user_name(data["user_id"], data["active"])
        if any(r["id"] != record_id and r["user_id"] == data["user_id"] for r in state[kind]):
            raise HTTPException(409, "This user already has a record. Edit the existing assignment")
    if kind == "team" and data["active"] and data["role"] == "Lead Engineer" and any(r["id"] != record_id and r["active"] and r["role"] == "Lead Engineer" for r in state[kind]):
        raise HTTPException(409, "An active lead engineer already exists. Update that assignment first")
    if kind == "actions":
        data["blocking"] = True
    timestamp = documents.now_iso()
    record = {**data, "id": record_id or str(uuid4()), "created_at": old["created_at"] if old else timestamp, "updated_at": timestamp}
    state = {**state, kind: [record if r["id"] == record_id else r for r in state[kind]] if record_id else state[kind] + [record]}
    patch = {}
    if kind == "team":
        lead = next((r for r in state["team"] if r["active"] and r["role"] == "Lead Engineer"), None)
        previous_lead = next((r for r in state_of(ewp)["team"] if r["active"] and r["role"] == "Lead Engineer"), None)
        if lead or previous_lead:
            patch = {"lead_engineer": lead["name"] if lead else None, "lead_engineer_id": lead["user_id"] if lead else None}
    return await commit(ewp, state, request, kind.upper() + ("_UPDATED" if record_id else "_CREATED"), old, record, patch)


@router.post("/ewps/{ewp_id}/records/{kind}", status_code=201)
async def create_record(ewp_id: str, kind: Kind, request: RecordWrite):
    return await write_record(ewp_id, kind, request)


@router.patch("/ewps/{ewp_id}/records/{kind}/{record_id}")
async def update_record(ewp_id: str, kind: Kind, record_id: str, request: RecordWrite):
    return await write_record(ewp_id, kind, request, record_id)


@router.patch("/ewps/{ewp_id}/settings")
async def update_settings(ewp_id: str, request: Settings):
    ewp = await require_ewp(ewp_id); state = check_write(ewp, request)
    patch = request.model_dump(mode="json", exclude={"version", "actor", "comment", "status"})
    if request.status is not None:
        if ewp.get("status") == "COMPLETION_REVIEW":
            raise HTTPException(409, "Completion status is controlled by Completion & Governance")
        if request.status in {"READY_FOR_OUTPUT", "COMPLETED"}:
            work = await rows("ewp_engineering_work", {"ewp_id": ewp_id})
            allowed = {"COMPLETED"} if request.status == "COMPLETED" else {"READY_FOR_OUTPUT", "COMPLETED"}
            if not work or any(w.get("status") not in allowed for w in work):
                raise HTTPException(409, "Finish the required engineering activities before selecting this status")
        patch["status"] = request.status
    return await commit(ewp, state, request, "SETTINGS_UPDATED", {key: ewp.get(key) for key in patch}, patch, patch)
