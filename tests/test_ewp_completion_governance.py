"""Module 6 tests use only isolated in-memory collections."""
import copy
import unittest
from unittest.mock import patch
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from api.EWP import completion_governance as api, lifecycle, engineering_work, inputs_deliverables, documents_reviews, approval_release, quantities_procurement
from test_ewp_approval_release import Collection, Database

ROOT = "/api/ewp/completion-governance/ewps/ewp"


class CompletionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database()
        def seed(name, *records):
            self.db[name] = Collection(records)
        seed("ewp", {"_id": "ewp", "ewp_code": "EWP-001", "ewp_name": "Electrical", "status": "IN_PROGRESS", "freeze_snapshot_id": "freeze"},
             {"_id": "empty", "ewp_code": "EWP-EMPTY", "status": "DRAFT"})
        seed("ewp_engineering_work", {"_id": "work", "ewp_id": "ewp", "status": "COMPLETED", "work_code": "EWO-001"})
        seed("ewp_deliverable", {"_id": "del", "ewp_id": "ewp", "code": "DEL-001", "status": "READY_FOR_REVIEW"})
        seed("ewp_document", {"_id": "doc", "ewp_id": "ewp", "deliverable_id": "del", "current_revision_id": "d03", "document_code": "SLD"})
        seed("ewp_document_revision", {"_id": "d03", "document_id": "doc", "status": "RELEASED", "revision_no": "D03",
             "approval": {"decision": "APPROVE"}, "release_record": {"id": "release", "revision_id": "d03", "status": "RELEASED", "ewp_id": "ewp", "release_hash": "hash"}})
        seed("ewp_document_reviewer", {"_id": "reviewer", "document_id": "doc", "revision_id": "d03", "status": "COMPLETED", "decision": "ACCEPT"})
        seed("ewp_document_review_comment", {"_id": "comment", "document_id": "doc", "status": "CLOSED", "text": "Check rating"})
        items = [{"id": "qty", "item": "Cable", "quantity": 40, "source": {"revision_id": "d03", "release_id": "release", "release_hash": "hash"}}]
        seed("ewp_quantity_register", {"_id": "reg", "ewp_id": "ewp", "name": "Cable BOQ", "status": "HANDOFF_REFERENCED", "items": items, "current_boq_id": "boq",
             "boqs": [{"id": "boq", "approval": {"decision": "APPROVE"}, "content_hash": api.digest(items)}],
             "handoff": {"status": "COMPLETED", "boq_id": "boq", "reference": "PO-001"}})
        seed("ewp_seb_input", {"_id": "input", "ewp_id": "ewp", "release_item_id": "item", "freeze_snapshot_id": "freeze"})
        seed("seb_ewp_frozen_item", {"_id": "freeze", "status": "RELEASED", "released_seb_items": [{"release_item_id": "item", "readiness": {"status": "READY"}}]})
        for module in [api, lifecycle]:
            patcher = patch.object(module, "db", self.db); patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(engineering_work, "ewp_collection", self.db["ewp"]); patcher.start(); self.addCleanup(patcher.stop)
        app = FastAPI(); app.include_router(api.router, prefix="/api")
        for module in [engineering_work, inputs_deliverables, documents_reviews, approval_release, quantities_procurement]:
            app.include_router(module.router, prefix="/api", dependencies=[Depends(lifecycle.ensure_ewp_open)])
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def get(self):
        response = await self.client.get(ROOT + "/summary")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def post(self, action, expected=200, **fields):
        current = await self.get()
        payload = {"version": current["control"]["version"], "actor": "Engineer A", "comment": "Checked evidence REF-001", **fields}
        if action == "governance":
            payload.setdefault("summary_hash", current["summary_hash"])
        response = await self.client.post(ROOT + "/" + action, json=payload)
        self.assertEqual(response.status_code, expected, response.text)
        return response.json()

    async def test_complete_lifecycle_persists_and_locks(self):
        current = await self.get()
        self.assertEqual(current["completion_status"], "READY_FOR_CLOSURE")
        await self.post("close", expected=409)
        await self.post("submit", expected=409)
        await self.post("governance")
        await self.post("submit")
        result = await self.post("close")
        self.assertEqual(result["completion_status"], "CLOSED")
        self.assertEqual(self.db["ewp"].rows["ewp"]["status"], "CLOSED")
        for name in ["ewp_completion", "ewp_completion_check", "ewp_governance_check", "ewp_closure"]:
            self.assertTrue(self.db[name].rows, name)
        snapshot = copy.deepcopy(result["control"]["closure"])
        self.db["ewp_engineering_work"].rows["work"]["status"] = "IN_PROGRESS"
        self.assertEqual((await self.get())["control"]["closure"], snapshot)
        self.assertEqual((await self.post("close"))["control"]["closure"], snapshot)
        await self.post("actions", expected=409, title="Late edit")
        response = await self.client.patch("/api/ewp/engineering-work/ewps/ewp/status", json={"status": "DRAFT"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.db["ewp_closure"].rows), 1)

    async def test_closed_ewp_locks_related_mutation_routes(self):
        await self.post("governance"); await self.post("submit"); await self.post("close")
        for method, path, body in [
            ("POST", "/engineering-work/ewps/ewp/work-items", {}),
            ("PATCH", "/inputs-deliverables/deliverables/del", {}),
            ("POST", "/documents-reviews/documents/doc/revisions", {}),
            ("POST", "/documents-reviews/reviewers/reviewer/decision", {}),
            ("PATCH", "/documents-reviews/comments/comment/response", {}),
            ("POST", "/approval-release/revisions/d03/release", {}),
            ("POST", "/quantities-procurement/registers/reg/reopen", {}),
            ("POST", "/quantities-procurement/registers", {"ewp_id": "ewp"}),
        ]:
            with self.subTest(path=path):
                response = await self.client.request(method, "/api/ewp" + path, json=body)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertIn("closed", response.json()["detail"])

    async def test_empty_ewp_is_blocked_not_vacuously_complete(self):
        response = await self.client.get("/api/ewp/completion-governance/ewps/empty/summary")
        self.assertEqual(response.json()["completion_status"], "BLOCKED")
        self.assertGreater(len(response.json()["blockers"]), 5)

    async def test_each_source_gate_blocks_closure(self):
        cases = [("ewp_engineering_work", "work", "status", "IN_PROGRESS", "work"),
                 ("ewp_document_review_comment", "comment", "status", "OPEN", "comments"),
                 ("ewp_document_reviewer", "reviewer", "decision", "CHANGE_REQUIRED", "reviews"),
                 ("ewp_document_revision", "d03", "status", "UNDER_REVIEW", "releases"),
                 ("ewp_quantity_register", "reg", "status", "DRAFT", "quantities"),
                 ("ewp_quantity_register", "reg", "handoff", {"status": "REFERENCED"}, "procurement")]
        for collection, identity, key, value, gate in cases:
            with self.subTest(gate=gate):
                record = self.db[collection].rows[identity]; old = record[key]; record[key] = value
                result = await self.get()
                self.assertIn(gate, [c["id"] for c in result["blockers"]])
                await self.post("submit", expected=409)
                await self.post("close", expected=409)
                record[key] = old

    async def test_ready_for_output_activities_allow_closure_when_other_gates_pass(self):
        self.db["ewp"].rows["ewp"]["status"] = "READY_FOR_OUTPUT"
        self.db["ewp_engineering_work"].rows["work"]["status"] = "READY_FOR_OUTPUT"
        self.db["ewp_engineering_work"].rows["work2"] = {
            "_id": "work2", "ewp_id": "ewp", "status": "COMPLETED", "work_code": "EWO-002"
        }
        result = await self.get()
        self.assertEqual(next(c for c in result["checks"] if c["id"] == "work")["status"], "PASSED")
        await self.post("governance")
        await self.post("submit")
        self.assertEqual((await self.post("close"))["completion_status"], "CLOSED")

    async def test_ready_package_does_not_override_unfinished_activity(self):
        self.db["ewp"].rows["ewp"]["status"] = "READY_FOR_OUTPUT"
        for status in ["DRAFT", "NOT_STARTED", "IN_PROGRESS", "ON_HOLD"]:
            with self.subTest(status=status):
                self.db["ewp_engineering_work"].rows["work"]["status"] = status
                result = await self.get()
                self.assertIn("work", [c["id"] for c in result["blockers"]])
                await self.post("close", expected=409)

    async def test_ready_for_output_preserves_release_procurement_and_condition_gates(self):
        self.db["ewp_engineering_work"].rows["work"]["status"] = "READY_FOR_OUTPUT"
        self.db["ewp_document_revision"].rows["d03"]["status"] = "READY_FOR_RELEASE"
        self.db["ewp_quantity_register"].rows["reg"]["handoff"]["status"] = "SENT"
        item = self.db["seb_ewp_frozen_item"].rows["freeze"]["released_seb_items"][0]
        item["readiness"] = {"status": "CONDITIONAL", "conditional": {"enabled": True, "condition": "Verify loading"}}
        result = await self.get()
        blockers = {c["id"] for c in result["blockers"]}
        self.assertNotIn("work", blockers)
        self.assertTrue({"deliverables", "releases", "procurement", "conditions"}.issubset(blockers))
        await self.post("submit", expected=409)
        await self.post("close", expected=409)

    async def test_released_document_label_does_not_replace_missing_revision_release(self):
        self.db["ewp_document"].rows["doc"]["status"] = "RELEASED"
        revision = self.db["ewp_document_revision"].rows["d03"]
        revision["status"] = "REVIEW_COMPLETED"
        revision.pop("approval")
        revision.pop("release_record")
        result = await self.get()
        release_check = next(c for c in result["checks"] if c["id"] == "releases")
        self.assertEqual(release_check["status"], "FAILED")
        self.assertIn("SLD / D03", release_check["issues"][0])
        self.assertIn("REVIEW_COMPLETED", release_check["issues"][0])
        self.assertIn("Approval & Release", release_check["issues"][0])
        deliverable_check = next(c for c in result["checks"] if c["id"] == "deliverables")
        self.assertIn(release_check["issues"][0], deliverable_check["issues"][0])
        await self.post("close", expected=409)

    async def test_released_revision_requires_its_own_release_record(self):
        self.db["ewp_document_revision"].rows["d03"].pop("release_record")
        result = await self.get()
        self.assertTrue({"deliverables", "releases"}.issubset({c["id"] for c in result["blockers"]}))
        self.assertIn("controlled release record is missing", next(c for c in result["checks"] if c["id"] == "releases")["issues"][0])

    async def test_procurement_warning_names_current_status_and_next_step(self):
        handoff = self.db["ewp_quantity_register"].rows["reg"]["handoff"]
        for status, next_status in [("REFERENCED", "SENT"), ("SENT", "ACKNOWLEDGED"), ("ACKNOWLEDGED", "IN_PROGRESS"), ("IN_PROGRESS", "COMPLETED")]:
            with self.subTest(status=status):
                handoff["status"] = status
                result = await self.get()
                check = next(c for c in result["checks"] if c["id"] == "procurement")
                self.assertEqual(check["status"], "FAILED")
                self.assertIn(f"status is {status}, not COMPLETED", check["issues"][0])
                self.assertIn(f"next status is {next_status}", check["issues"][0])
        handoff["status"] = "COMPLETED"
        self.assertEqual(next(c for c in (await self.get())["checks"] if c["id"] == "procurement")["status"], "PASSED")

    async def test_completed_procurement_still_requires_reference_and_current_boq(self):
        handoff = self.db["ewp_quantity_register"].rows["reg"]["handoff"]
        handoff.update(reference="", boq_id="old-boq")
        check = next(c for c in (await self.get())["checks"] if c["id"] == "procurement")
        self.assertEqual(check["status"], "FAILED")
        self.assertTrue(any("reference is missing" in issue for issue in check["issues"]))
        self.assertTrue(any("current BOQ" in issue for issue in check["issues"]))

    async def test_new_current_revision_does_not_reuse_old_release(self):
        self.db["ewp_document_revision"].rows["d04"] = {"_id": "d04", "document_id": "doc", "status": "DRAFT"}
        self.db["ewp_document"].rows["doc"]["current_revision_id"] = "d04"
        result = await self.get()
        self.assertTrue({"deliverables", "reviews", "releases"}.issubset({c["id"] for c in result["blockers"]}))

    async def test_governance_invalidated_by_source_change_even_if_checks_pass(self):
        await self.post("governance"); await self.post("submit")
        self.db["ewp_engineering_work"].rows["work"]["title"] = "Changed scope"
        result = await self.get()
        self.assertTrue(result["ready_for_closure"])
        self.assertFalse(result["governance_valid"])
        await self.post("close", expected=409)
        await self.post("governance"); await self.post("submit"); await self.post("close")

    async def test_conditions_actions_and_stale_resolutions(self):
        item = self.db["seb_ewp_frozen_item"].rows["freeze"]["released_seb_items"][0]
        item["readiness"] = {"status": "CONDITIONAL", "conditional": {"enabled": True, "condition": "Verify roof loading"}}
        o = (await self.get())["obligations"][0]
        await self.post("resolutions", obligation_id=o["id"], source_hash=o["source_hash"], status="ACCEPTED")
        self.assertTrue((await self.get())["ready_for_closure"])
        item["readiness"]["conditional"]["condition"] = "New loading restriction"
        self.assertFalse((await self.get())["ready_for_closure"])
        await self.post("resolutions", expected=409, obligation_id=o["id"], source_hash=o["source_hash"], status="CLOSED")
        result = await self.post("actions", title="Verify procurement receipt")
        action = next(o for o in result["obligations"] if o["kind"] == "ACTION")
        await self.post("resolutions", expected=400, obligation_id=action["id"], source_hash=action["source_hash"], status="ACCEPTED")
        await self.post("resolutions", obligation_id=action["id"], source_hash=action["source_hash"], status="CLOSED")
        await self.post("resolutions", expected=409, obligation_id="other-ewp-action", source_hash=action["source_hash"], status="CLOSED")

    async def test_stale_version_and_blank_actor_rejected(self):
        result = await self.post("governance")
        await self.post("submit", expected=409, version=0)
        await self.post("submit", expected=422, actor=" ")
        await self.post("governance", expected=409, summary_hash="0" * 64)

    async def test_quantity_source_and_missing_basis_block(self):
        self.db["ewp_document_revision"].rows["d03"]["release_record"]["release_hash"] = "changed"
        self.db["ewp_seb_input"].rows["input"]["freeze_snapshot_id"] = "other"
        result = await self.get()
        self.assertTrue({"quantities", "basis"}.issubset({c["id"] for c in result["blockers"]}))

    async def test_projection_failure_recovers_without_duplicate_closure(self):
        await self.post("governance"); await self.post("submit")
        with patch.object(api, "project", side_effect=RuntimeError("Interrupted projection")):
            with self.assertRaises(RuntimeError):
                await api.close_ewp("ewp", api.Action(version=2, actor="Manager", comment="Closure approved"))
        result = await self.get()
        self.assertEqual(result["completion_status"], "CLOSED")
        await self.post("close")
        self.assertEqual(len(self.db["ewp_closure"].rows), 1)


if __name__ == "__main__":
    unittest.main()
