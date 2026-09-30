"""SIA ownership regression tests. No live database is used."""
import copy
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from api.SIA.scope import apply_scope
from api.SIA import (
    site_survey, Engineering_Assessment, drone_gis_climate,
    evidence_ai_readiness, android_field_ops, seb_ewb_handoff,
)


class Collection:
    def __init__(self):
        self.rows = []

    async def find_one(self, query):
        return next((copy.deepcopy(row) for row in self.rows
                     if all(row.get(k) == v for k, v in query.items())), None)

    async def insert_one(self, doc):
        self.rows.append(copy.deepcopy(doc))


class Database(dict):
    def __missing__(self, key):
        self[key] = Collection()
        return self[key]


class ScopeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database()
        fixtures = {
            'sia_case': [{'_id': 'case'}, {'_id': 'other-case'}],
            'sia_site': [{'_id': 'site', 'sia_case_id': 'case'},
                         {'_id': 'other-site', 'sia_case_id': 'case'}],
            'sia_drone_mission': [{'_id': 'mission', 'site_id': 'site'}],
            'sia_engineering_assessment': [{'_id': 'ea', 'site_id': 'site', 'sia_case_id': 'case'}],
            'sia_evidence': [{'_id': 'evidence', 'site_id': 'site', 'sia_case_id': 'case'}],
            'sia_field_case_download': [{'_id': 'download', 'site_id': 'site', 'sia_case_id': 'case'}],
            'sia_field_session': [{'_id': 'session', 'field_case_download_id': 'download'}],
        }
        for name, rows in fixtures.items():
            self.db[name].rows = rows
        app = FastAPI()
        for module in (site_survey, Engineering_Assessment, drone_gis_climate,
                       evidence_ai_readiness, android_field_ops):
            # Replace every module-level Motor collection as well as db.
            for name, value in list(vars(module).items()):
                if name.endswith('_col'):
                    p = patch.object(module, name, self.db[value.name])
                    p.start(); self.addCleanup(p.stop)
            p = patch.object(module, 'db', self.db)
            p.start(); self.addCleanup(p.stop)
            app.include_router(module.router)
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    async def test_creates_persist_and_return_scope_across_modules(self):
        examples = [
            ('/sia/sites', {'sia_case_id': 'case', 'site_code': 'S2'}, 'sia_site'),
            ('/sia/buildings', {'site_id': 'site', 'building_code': 'B1'}, 'sia_building'),
            ('/sia/electrical-assessments', {'engineering_assessment_id': 'ea'}, 'sia_electrical_assessment'),
            ('/sia/drone-missions', {'site_id': 'site', 'mission_code': 'M1'}, 'sia_drone_mission'),
            ('/sia/drone-platforms', {'drone_mission_id': 'mission'}, 'sia_drone_platform'),
            ('/sia/evidence', {'sia_case_id': 'case', 'site_id': 'site', 'evidence_code': 'E1'}, 'sia_evidence'),
            ('/sia/evidence-verifications', {'evidence_id': 'evidence'}, 'sia_evidence_verification'),
            ('/sia/rfi-actions', {'sia_case_id': 'case', 'site_id': 'site', 'action_code': 'R1'}, 'sia_rfi_action'),
            ('/sia/mobile-photo-captures', {'field_session_id': 'session'}, 'sia_mobile_photo_capture'),
        ]
        for path, body, collection in examples:
            with self.subTest(path=path):
                response = await self.client.post(path, json=body)
                self.assertEqual(response.status_code, 201, response.text)
                saved = self.db[collection].rows[-1]
                expected_site = saved['_id'] if collection == 'sia_site' else 'site'
                self.assertEqual(saved['site_id'], expected_site)
                self.assertEqual(saved['sia_case_id'], 'case')
                self.assertEqual(response.json()['site_id'], expected_site)
                self.assertEqual(response.json()['sia_case_id'], 'case')

    async def test_invalid_scope_does_not_insert(self):
        for body, status in [
            ({'sia_case_id': 'case'}, 422),
            ({'sia_case_id': 'other-case', 'site_id': 'site'}, 422),
            ({'sia_case_id': 'case', 'site_id': 'missing'}, 404),
            ({'sia_case_id': 'case', 'site_id': 'other-site', 'engineering_assessment_id': 'ea'}, 422),
        ]:
            response = await self.client.post('/sia/evidence', json={**body, 'evidence_code': 'BAD'})
            self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(len(self.db['sia_evidence'].rows), 1)

    async def test_legacy_parent_chain_is_resolved_without_mutating_parent(self):
        doc = {'_id': 'photo', 'field_session_id': 'session'}
        await apply_scope(self.db, doc, 'sia_mobile_photo_capture')
        self.assertEqual((doc['sia_case_id'], doc['site_id']), ('case', 'site'))
        self.assertNotIn('site_id', self.db['sia_field_session'].rows[0])

    async def test_shared_device_can_exist_before_site(self):
        doc = {'_id': 'device'}
        await apply_scope(self.db, doc, 'sia_mobile_device')
        self.assertNotIn('site_id', doc)

    async def test_circular_parent_chain_rejected(self):
        self.db['sia_evidence'].rows.append({'_id': 'cycle', 'evidence_id': 'cycle'})
        with self.assertRaises(HTTPException):
            await apply_scope(self.db, {'_id': 'child', 'evidence_id': 'cycle'}, 'sia_source_fact')

    async def test_completion_excludes_other_sites_in_same_case(self):
        class Cursor:
            async def to_list(self, length):
                return [
                    {'_id': 'included', 'sia_case_id': 'case', 'site_id': 'site'},
                    {'_id': 'excluded', 'sia_case_id': 'case', 'site_id': 'other-site'},
                ]

        class Records:
            def find(self, query):
                return Cursor()

        async def names():
            return ['sia_evidence']

        with patch.object(seb_ewb_handoff, 'db', {'sia_evidence': Records()}), \
                patch.object(seb_ewb_handoff, 'sia_collection_names', names):
            package = await seb_ewb_handoff.collect_package('case', 'site')
        self.assertEqual([row['id'] for row in package['sia_evidence']], ['included'])
        self.assertTrue({'sia_case_id', 'site_id', 'drone_mission_id'}.issubset(seb_ewb_handoff.PROTECTED_FIELDS))
