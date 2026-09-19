"""Isolated lifecycle tests. No application MongoDB is read or written.

Run from backend: python -B -m unittest discover -s tests -v
"""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from api.EWP import approval_release as api
from api.EWP import documents_reviews as docs


MISSING = object()


def lookup(row, key):
    for part in key.split("."):
        if not isinstance(row, dict) or part not in row:
            return MISSING
        row = row[part]
    return row


def matches(row, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(matches(row, branch) for branch in expected):
                return False
            continue
        actual = lookup(row, key)
        if isinstance(expected, dict) and any(name.startswith("$") for name in expected):
            for op, value in expected.items():
                if op == "$exists" and (actual is not MISSING) != value:
                    return False
                if op == "$in" and actual not in value:
                    return False
                if op == "$nin" and actual in value:
                    return False
                if op == "$ne" and actual == value:
                    return False
                if op == "$lte" and (actual is MISSING or actual > value):
                    return False
        elif actual != expected:
            return False
    return True


class Cursor:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    def sort(self, key, direction):
        self.rows.sort(key=lambda row: str(row.get(key, "")), reverse=direction < 0)
        return self

    async def to_list(self, length=None):
        return self.rows if length is None else self.rows[:length]


class Collection:
    def __init__(self, rows=()):
        self.rows = {row["_id"]: copy.deepcopy(row) for row in rows}

    def find(self, query, projection=None):
        return Cursor([row for row in self.rows.values() if matches(row, query)])

    async def find_one(self, query):
        return next((copy.deepcopy(row) for row in self.rows.values() if matches(row, query)), None)

    async def insert_one(self, row):
        self.rows[row["_id"]] = copy.deepcopy(row)
        return SimpleNamespace(inserted_id=row["_id"])

    async def count_documents(self, query):
        return sum(matches(row, query) for row in self.rows.values())

    async def update_one(self, query, update, upsert=False):
        row = next((row for row in self.rows.values() if matches(row, query)), None)
        exists = row is not None
        if row is None and upsert:
            row = {"_id": query["_id"], **copy.deepcopy(update.get("$setOnInsert", {}))}
            self.rows[row["_id"]] = row
        if row is not None:
            row.update(copy.deepcopy(update.get("$set", {})))
        return SimpleNamespace(matched_count=int(exists), modified_count=int(exists))


class Database(dict):
    def __missing__(self, name):
        self[name] = Collection()
        return self[name]


class ApprovalReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "D03.pdf"
        self.file.write_bytes(b"Reviewed engineering document D03")
        self.user = {"_id": "engineer", "name": "Engineering Manager", "is_active": True, "role": "user"}
        self.db = Database()
        self.db["users"] = Collection([self.user, {"_id": "other", "name": "Other User", "is_active": True}])
        self.db["ewp"] = Collection([{"_id": "ewp", "ewp_code": "EWP-001", "ewp_name": "Electrical",
            "seb_id": "seb", "seb_revision_id": "r01", "freeze_snapshot_id": "snapshot", "project_id": "project"}])
        self.db["ewp_deliverable"] = Collection([{"_id": "deliverable", "ewp_id": "ewp", "code": "DEL-003",
            "name": "SLD", "responsible_engineer": "Engineer C", "engineering_work_item_id": "activity"}])
        self.db["ewp_document"] = Collection([{"_id": "doc", "ewp_id": "ewp", "deliverable_id": "deliverable",
            "document_code": "SLD-001", "title": "Single Line Diagram", "status": "REVIEW_COMPLETED",
            "current_revision_id": "d03", "current_revision_no": "D03"}])
        self.db["ewp_document_revision"] = Collection([{"_id": "d03", "document_id": "doc", "revision_no": "D03",
            "status": "REVIEW_COMPLETED", "review_completed_at": "2026-09-18", "storage_path": str(self.file),
            "file_name": "D03.pdf", "file_size": self.file.stat().st_size}])
        self.db["ewp_document_reviewer"] = Collection([{"_id": "reviewer", "document_id": "doc",
            "revision_id": "d03", "reviewer_name": "Electrical Lead", "status": "COMPLETED", "decision": "ACCEPT"}])
        self.db["ewp_document_review_comment"] = Collection([{"_id": "comment", "document_id": "doc", "revision_id": "d03",
            "text": "Confirm cable rating", "status": "CLOSED", "response": "Verified", "responded_by": "Engineer C"}])
        self.db["ewp_seb_input"] = Collection([{"_id": "input", "ewp_id": "ewp", "release_item_id": "item-101",
            "freeze_snapshot_id": "snapshot", "position": 1}])
        self.db["seb_ewp_frozen_item"] = Collection([{"_id": "snapshot", "status": "RELEASED", "snapshot_hash": "frozen",
            "seb": {"id": "seb", "code": "SEB-001"}, "released_revision": {"id": "r01", "revision_no": "R01"},
            "released_seb_items": [{"seb_item_id": "item-101", "item_name": "Transformer Capacity", "item_value": 500,
                "unit": "kVA", "fact_id": "fact", "readiness": {"status": "CONDITIONAL", "conditional": {
                    "enabled": True, "condition": "Verify equipment", "owner": "Lead"}}}]}])
        mappings = {"ewp_collection": "ewp", "deliverable_collection": "ewp_deliverable",
            "document_collection": "ewp_document", "revision_collection": "ewp_document_revision",
            "reviewer_collection": "ewp_document_reviewer", "comment_collection": "ewp_document_review_comment",
            "decision_collection": "ewp_document_review_decision"}
        for attribute, collection in mappings.items():
            patcher = patch.object(docs, attribute, self.db[collection])
            patcher.start(); self.addCleanup(patcher.stop)
        for attribute, value in {"db": self.db, "approval_collection": self.db["ewp_document_approval"],
            "release_collection": self.db["ewp_document_release"], "users_collection": self.db["users"]}.items():
            patcher = patch.object(api, attribute, value)
            patcher.start(); self.addCleanup(patcher.stop)
        app = FastAPI()
        app.include_router(api.router, prefix="/api")
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def assign(self):
        return await api.assign_approver("d03", api.ApproverAssignment(approver_id="engineer"))

    async def approve(self, decision="APPROVE", **kwargs):
        context = await self.assign()
        return await api.submit_approval("d03", api.ApprovalDecision(decision=decision, package_reviewed=True,
            package_hash=context["package_hash"], **kwargs))

    async def release(self):
        return await api.release_revision("d03", api.ReleaseRequest(comment="Controlled issue"))

    async def test_approve_release_freezes_exact_basis_and_is_idempotent(self):
        approved = await self.approve()
        self.assertEqual(approved["status"], "READY_FOR_RELEASE")
        self.assertEqual(self.db["ewp_document_approval"].rows["d03"]["status"], "APPROVED")
        released = await self.release()
        self.assertEqual(released["status"], "RELEASED")
        self.assertEqual(self.db["ewp_document"].rows["doc"]["status"], "RELEASED")
        snapshot = released["release"]
        self.assertEqual(snapshot["package"]["seb_basis"]["revision_id"], "r01")
        self.assertEqual(snapshot["package"]["inputs"][0]["release_item_id"], "item-101")
        self.assertEqual(snapshot["package"]["inputs"][0]["item"]["readiness"]["conditional"]["owner"], "Lead")
        self.assertEqual(snapshot["released_by_id"], "prototype-pilot")
        self.assertEqual(snapshot["release_hash"], api.digest({k: v for k, v in snapshot.items() if k != "release_hash"}))
        self.assertEqual((await self.release())["release"], snapshot)
        self.assertEqual(len(self.db["ewp_document_release"].rows), 1)

    async def test_conditional_approval_requires_and_preserves_condition(self):
        with self.assertRaises(HTTPException) as error:
            await self.approve("APPROVE_WITH_CONDITION", comment="Conditional issue")
        self.assertEqual(error.exception.status_code, 400)
        await self.approve("APPROVE_WITH_CONDITION", comment="Conditional issue", condition="Verify roof loading")
        result = await self.release()
        self.assertEqual(result["release"]["approval"]["condition"], "Verify roof loading")

    async def test_changes_and_rejection_cannot_release_or_reopen_review(self):
        for decision, expected in [("CHANGE_REQUIRED", "CHANGE_REQUIRED"), ("REJECT", "REJECTED")]:
            self.db["ewp_document_revision"].rows["d03"].pop("approval", None)
            self.db["ewp_document_revision"].rows["d03"]["status"] = "REVIEW_COMPLETED"
            result = await self.approve(decision, comment="Revise the design")
            self.assertEqual(result["status"], expected)
            with self.assertRaises(HTTPException):
                await self.release()
            with self.assertRaises(HTTPException):
                await docs.submit_document_for_review("doc")

    async def test_incomplete_review_and_open_comments_block_approval(self):
        self.db["ewp_document_review_comment"].rows["comment"]["status"] = "OPEN"
        with self.assertRaises(HTTPException):
            await self.approve()
        self.db["ewp_document_review_comment"].rows["comment"]["status"] = "CLOSED"
        self.db["ewp_document_reviewer"].rows["reviewer"]["decision"] = "CHANGE_REQUIRED"
        with self.assertRaises(HTTPException):
            await self.approve()
        self.assertEqual(self.db["ewp_document_revision"].rows["d03"]["status"], "REVIEW_COMPLETED")

    async def test_missing_or_changed_file_cannot_release(self):
        await self.approve()
        self.file.write_bytes(b"Different engineering design")
        with self.assertRaises(HTTPException) as error:
            await self.release()
        self.assertIn("changed", error.exception.detail)
        self.file.unlink()
        with self.assertRaises(HTTPException) as error:
            await self.release()
        self.assertIn("missing", error.exception.detail)
        self.assertEqual(len(self.db["ewp_document_release"].rows), 0)

    async def test_stale_package_cannot_be_approved(self):
        context = await self.assign()
        self.file.write_bytes(b"Changed after the user opened the package")
        with self.assertRaises(HTTPException) as error:
            await api.submit_approval("d03", api.ApprovalDecision(decision="APPROVE", package_reviewed=True,
                package_hash=context["package_hash"]))
        self.assertIn("Refresh", error.exception.detail)

    async def test_new_revision_preserves_release_and_old_comments_stay_locked(self):
        await self.approve()
        original = (await self.release())["release"]
        result = await docs.create_document_revision("doc", revision_no="D04", revision_note="New design", file=None)
        self.assertEqual(result["current_revision_no"], "D04")
        history = await api.get_package("d03")
        self.assertFalse(history["is_current"])
        self.assertEqual(history["release"], original)
        self.assertEqual(self.db["ewp_document"].rows["doc"]["status"], "REVISED")
        with self.assertRaises(HTTPException):
            await docs.respond_to_review_comment("comment", docs.CommentResponseUpdate(response="Overwrite D03"))

    async def test_released_revision_all_review_mutations_are_blocked(self):
        await self.approve()
        await self.release()
        calls = [
            lambda: docs.submit_document_for_review("doc"),
            lambda: docs.assign_document_reviewer("doc", docs.ReviewerCreate(reviewer_name="Other", reviewer_role="Lead")),
            lambda: docs.record_review_decision("reviewer", docs.ReviewDecisionCreate(decision="ACCEPT")),
            lambda: docs.create_review_comment("doc", docs.ReviewCommentCreate(text="Change", raised_by="Other")),
            lambda: docs.respond_to_review_comment("comment", docs.CommentResponseUpdate(response="Change")),
            lambda: docs.close_all_review_comments("doc"),
            lambda: docs.complete_document_review("doc"),
            self.assign,
        ]
        for call in calls:
            with self.assertRaises(HTTPException) as error:
                await call()
            self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db["ewp_document_revision"].rows["d03"]["status"], "RELEASED")

    async def test_released_download_checks_file_hash(self):
        await self.approve()
        await self.release()
        response = await docs.open_document_revision_file("doc", "d03")
        self.assertEqual(str(response.path), str(self.file))
        self.file.write_bytes(b"Corrupt release")
        with self.assertRaises(HTTPException):
            await docs.open_document_revision_file("doc", "d03")

    async def test_release_projection_failure_recovers_without_duplicate(self):
        await self.approve()
        with patch.object(api.release_collection, "update_one", side_effect=RuntimeError("temporary database failure")):
            with self.assertRaises(RuntimeError):
                await self.release()
        frozen = copy.deepcopy(self.db["ewp_document_revision"].rows["d03"]["release_record"])
        recovered = await self.release()
        self.assertEqual(recovered["release"], frozen)
        self.assertEqual(self.db["ewp_document_release"].rows["d03"]["release_hash"], frozen["release_hash"])

    async def test_http_pilot_approval_and_release_without_login(self):
        response = await self.client.get("/api/ewp/approval-release/documents?ewp_id=other")
        self.assertEqual(response.json(), [])
        response = await self.client.get("/api/ewp/approval-release/documents?ewp_id=ewp")
        self.assertEqual(response.json()[0]["revisions"][0]["id"], "d03")
        response = await self.client.get("/api/ewp/approval-release/approvers")
        self.assertEqual(response.status_code, 200)
        response = await self.client.put("/api/ewp/approval-release/revisions/d03/approver",
            json={"approver_id": "engineer"})
        self.assertEqual(response.status_code, 200)
        context = response.json()
        response = await self.client.post("/api/ewp/approval-release/revisions/d03/approval", json={
            "decision": "APPROVE", "package_reviewed": True, "package_hash": context["package_hash"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "READY_FOR_RELEASE")
        self.assertEqual(response.json()["approval"]["approver_id"], "engineer")
        self.assertEqual(response.json()["approval"]["recorded_by"], "prototype-pilot")
        response = await self.client.post("/api/ewp/approval-release/revisions/d03/release", json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "RELEASED")
        self.assertEqual(response.json()["release"]["actor_mode"], "PROTOTYPE_PILOT")

    async def test_http_pilot_loads_without_token_or_with_stale_token(self):
        for headers in [{}, {"Authorization": "Bearer expired-prototype-token"}]:
            response = await self.client.get("/api/ewp/approval-release/ewps", headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()[0]["id"], "ewp")


if __name__ == "__main__":
    unittest.main()
