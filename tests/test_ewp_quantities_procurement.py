"""Module 5 workflow tests using isolated collections; no application DB writes."""
import copy
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from api.EWP import quantities_procurement as api
from test_ewp_approval_release import Collection, Database


class QuantitiesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database()
        self.db["ewp"] = Collection([{"_id": "ewp", "ewp_code": "EWP-001", "ewp_name": "Electrical", "project_id": "project"}])
        self.db["ewp_document"] = Collection([{"_id": "doc", "ewp_id": "ewp"}])
        release = {"id": "d03", "document_id": "doc", "revision_no": "D03", "release_code": "REL-D03",
            "ewp_id": "ewp", "status": "RELEASED", "release_hash": "release-hash", "released_at": "2026-09-19",
            "package": {"document": {"code": "SLD", "title": "Single Line Diagram"},
                        "deliverable": {"id": "deliverable", "code": "DEL-001", "name": "SLD"},
                        "file": {"sha256": "file-hash"}, "seb_basis": {"seb_id": "seb", "revision_id": "r01", "freeze_snapshot_id": "frozen"}}}
        self.db["ewp_document_revision"] = Collection([
            {"_id": "d03", "document_id": "doc", "status": "RELEASED", "release_record": release},
            {"_id": "d04", "document_id": "doc", "status": "READY_FOR_RELEASE"},
            {"_id": "other", "document_id": "other-doc", "status": "RELEASED", "release_record": {**release, "ewp_id": "other-ewp"}},
        ])
        for attr, name in {"ewp_collection": "ewp", "document_collection": "ewp_document", "revision_collection": "ewp_document_revision"}.items():
            patcher = patch.object(api.documents, attr, self.db[name]); patcher.start(); self.addCleanup(patcher.stop)
        for attr, name in {"registers": "ewp_quantity_register", "items": "ewp_quantity_item", "boqs": "ewp_boq",
                           "boq_items": "ewp_boq_item", "handoffs": "ewp_procurement_handoff"}.items():
            patcher = patch.object(api, attr, self.db[name]); patcher.start(); self.addCleanup(patcher.stop)
        app = FastAPI(); app.include_router(api.router, prefix="/api")
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        self.row = await api.create_register(api.RegisterCreate(ewp_id="ewp", name="Electrical QTO"))

    def quantity(self, **changes):
        return api.QuantityWrite(version=self.row["version"], **{
            "item": "Cable", "description": "DC cable", "specification": "6 mm2", "quantity": 4200, "unit": "m",
            "source_revision_id": "d03", "source_reference": "Sheet 2 / row 8", "derivation": "42 runs x 100 m", **changes})

    def actor(self, cls=api.ActorAction, **kwargs):
        return cls(version=self.row["version"], actor="Engineer A", **kwargs)

    async def add(self):
        self.row = await api.add_item(self.row["id"], self.quantity())

    async def generate(self, kind="BOQ"):
        self.row = await api.validate(self.row["id"], self.actor())
        self.row = await api.generate(self.row["id"], self.actor(api.Generate, type=kind))

    async def ready(self):
        await self.add(); await self.generate()
        self.row = await api.review(self.row["id"], self.actor(api.Review, decision="ACCEPT"))
        self.row = await api.approve(self.row["id"], self.actor(api.Approval, decision="APPROVE"))
        self.row = await api.mark_ready(self.row["id"], self.actor())

    async def test_complete_workflow_persists_five_collections_and_traceability(self):
        await self.ready()
        request = self.actor(api.HandoffCreate, system="Procurement", reference="PO-001", url="https://example.com/PO-001")
        self.row = await api.create_handoff(self.row["id"], request)
        self.assertEqual(self.row["status"], "HANDOFF_REFERENCED")
        self.assertEqual(self.row["handoff"]["status"], "REFERENCED")
        self.assertEqual(self.row["handoff"]["source_release_ids"], ["d03"])
        item = self.row["items"][0]
        self.assertEqual(self.db["ewp_quantity_item"].rows[item["id"]]["status"], "PROCUREMENT_READY")
        self.assertEqual(item["source"]["seb_basis"]["revision_id"], "r01")
        self.assertEqual(item["source"]["file_hash"], "file-hash")
        for name in ["ewp_quantity_register", "ewp_quantity_item", "ewp_boq", "ewp_boq_item", "ewp_procurement_handoff"]:
            self.assertEqual(len(self.db[name].rows), 1, name)
        original = copy.deepcopy(self.row["handoff"])
        self.row = await api.create_handoff(self.row["id"], request)
        self.assertEqual(original, self.row["handoff"])
        for status in ["SENT", "ACKNOWLEDGED", "IN_PROGRESS", "COMPLETED"]:
            self.row = await api.update_handoff(self.row["id"], self.actor(api.HandoffUpdate, status=status, comment="Verified externally"))
        self.assertEqual(self.row["handoff"]["status"], "COMPLETED")

    async def test_only_released_sources_from_selected_ewp(self):
        outputs = await api.list_outputs("ewp")
        self.assertEqual([row["revision_id"] for row in outputs], ["d03"])
        for revision in ["d04", "other", "missing"]:
            with self.assertRaises(HTTPException) as error:
                await api.add_item(self.row["id"], self.quantity(source_revision_id=revision))
            self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(await api.list_registers("other-ewp"), [])

    async def test_empty_and_invalid_quantities_are_blocked(self):
        with self.assertRaises(HTTPException):
            await api.validate(self.row["id"], self.actor())
        for value in [0, -1, float("nan"), float("inf")]:
            with self.assertRaises(ValidationError):
                self.quantity(quantity=value)
        for field in ["item", "unit", "source_reference"]:
            with self.assertRaises(ValidationError):
                self.quantity(**{field: "  "})

    async def test_stale_version_and_approved_edits_are_blocked(self):
        stale = self.quantity()
        await self.ready()
        with self.assertRaises(HTTPException):
            await api.add_item(self.row["id"], stale)
        with self.assertRaises(HTTPException):
            await api.update_item(self.row["id"], self.row["items"][0]["id"], self.quantity(quantity=5000))
        with self.assertRaises(HTTPException):
            await api.remove_item(self.row["id"], self.row["items"][0]["id"], api.Versioned(version=self.row["version"]))
        with self.assertRaises(HTTPException):
            await api.reopen(self.row["id"], self.actor())

    async def test_rework_creates_new_boq_snapshot(self):
        await self.add(); await self.generate("EBOM")
        self.row = await api.review(self.row["id"], self.actor(api.Review, decision="CHANGE_REQUIRED", comment="Change cable length"))
        self.assertEqual(self.row["status"], "DRAFT")
        self.row = await api.update_item(self.row["id"], self.row["items"][0]["id"], self.quantity(quantity=5000))
        await self.generate("EBOM")
        self.assertEqual(self.row["boqs"][0]["items"][0]["quantity"], 4200)
        self.assertEqual(self.row["boqs"][1]["items"][0]["quantity"], 5000)
        self.assertEqual(self.row["boqs"][1]["revision_no"], "R02")
        self.assertEqual(self.row["boqs"][1]["content_hash"], api.digest(self.row["items"]))

    async def test_rejected_quantity_set_cannot_be_procured(self):
        await self.add(); await self.generate()
        self.row = await api.review(self.row["id"], self.actor(api.Review, decision="ACCEPT"))
        self.row = await api.approve(self.row["id"], self.actor(api.Approval, decision="REJECT", comment="Wrong design quantities"))
        self.assertEqual(self.row["boqs"][0]["status"], "REJECT")
        with self.assertRaises(HTTPException):
            await api.mark_ready(self.row["id"], self.actor())
        with self.assertRaises(HTTPException):
            await api.create_handoff(self.row["id"], self.actor(api.HandoffCreate, system="P", reference="PO-1"))

    async def test_projection_write_failure_recovers_without_duplicate_item(self):
        with patch.object(api.items, "update_one", side_effect=RuntimeError("temporary write failure")):
            with self.assertRaises(RuntimeError):
                await self.add()
        self.row = await api.get_register(self.row["id"])
        self.assertEqual(len(self.row["items"]), 1)
        self.assertEqual(len(self.db["ewp_quantity_item"].rows), 1)
        self.row = await api.remove_item(self.row["id"], self.row["items"][0]["id"], api.Versioned(version=self.row["version"]))
        self.assertEqual(len(self.row["items"]), 0)
        self.assertEqual(next(iter(self.db["ewp_quantity_item"].rows.values()))["status"], "REMOVED")

    async def test_handoff_requires_sequence_and_safe_reference(self):
        await self.ready()
        with self.assertRaises(ValidationError):
            self.actor(api.HandoffCreate, system="P", reference="PO-1", url="javascript:alert(1)")
        self.row = await api.create_handoff(self.row["id"], self.actor(api.HandoffCreate, system="P", reference="PO-1"))
        with self.assertRaises(HTTPException):
            await api.update_handoff(self.row["id"], self.actor(api.HandoffUpdate, status="COMPLETED", comment="Skipped acknowledgement"))

    async def test_source_release_never_silently_advances(self):
        await self.add()
        newer = copy.deepcopy(self.db["ewp_document_revision"].rows["d03"])
        newer["_id"] = "d04"; newer["release_record"].update(id="d04", revision_no="D04", release_hash="new-hash")
        self.db["ewp_document_revision"].rows["d04"] = newer
        await self.generate()
        self.assertEqual(self.row["items"][0]["source"]["revision_no"], "D03")
        self.db["ewp_document_revision"].rows["d03"]["release_record"]["release_hash"] = "modified"
        self.row = await api.review(self.row["id"], self.actor(api.Review, decision="ACCEPT"))
        with self.assertRaises(HTTPException):
            await api.approve(self.row["id"], self.actor(api.Approval, decision="APPROVE"))

    async def test_http_pilot_endpoints_without_auth(self):
        response = await self.client.get("/api/ewp/quantities-procurement/ewps")
        self.assertEqual(response.status_code, 200)
        response = await self.client.post(f"/api/ewp/quantities-procurement/registers/{self.row['id']}/items", json=self.quantity().dict())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["items"]), 1)


if __name__ == "__main__":
    unittest.main()
