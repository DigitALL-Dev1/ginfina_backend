"""Project sync tests with mocked upstream HTTP and an in-memory collection."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
import httpx


PROJECT = {
    'id': 5, 'project_name': 'Lae Operations', 'project_code': 'Lae',
    'customer': 'GREEN Limited', 'currency_name': None,
    'start_date': '30-Apr-2024', 'target_end_date': '30-Dec-2024',
    'project_status': 'In Progress', 'project_type': 'Solar Engineering Projects',
    'business_domain': 'GREEN Infra', 'sub_domain': 'Design Engineering',
    'last_updated': '20-Sep-2024 04:47 AM', 'updated_by': 'Janet James',
    'budget': '0.00', 'priority': 'High', 'contract_reference': 'N/A',
}


class Collection:
    def __init__(self):
        self.rows = []

    async def update_one(self, query, update, upsert=False):
        row = next((r for r in self.rows if all(r.get(k) == v for k, v in query.items())), None)
        if row is None:
            if not upsert:
                return
            row = {**query, **copy.deepcopy(update.get('$setOnInsert', {}))}
            self.rows.append(row)
        row.update(copy.deepcopy(update['$set']))

    async def find_one(self, query):
        return next((r for r in self.rows if all(r.get(k) == v for k, v in query.items())), None)

    def find(self, query):
        rows = [r for r in self.rows if all(r.get(k) == v for k, v in query.items())]

        class Cursor:
            def sort(self, *args):
                return self

            async def to_list(self, length):
                return copy.deepcopy(rows[:length])

        return Cursor()


class ProjectSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        spec = importlib.util.spec_from_file_location('project_sync_test_api', Path(__file__).parents[1] / 'api' / 'project.py')
        self.api = importlib.util.module_from_spec(spec)
        with patch('dotenv.load_dotenv'), patch('motor.motor_asyncio.AsyncIOMotorClient'):
            spec.loader.exec_module(self.api)
        self.api.projects_collection = self.collection = Collection()
        app = FastAPI()
        app.include_router(self.api.router, prefix='/api')
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)
        self.upstream = AsyncMock()
        self.upstream.__aenter__.return_value = self.upstream
        p = patch.object(self.api.httpx, 'AsyncClient', return_value=self.upstream)
        p.start(); self.addCleanup(p.stop)
        self.respond({'code': '001', 'project_list': [PROJECT]})

    def respond(self, payload, status=200):
        self.upstream.post.return_value = httpx.Response(status, json=payload, request=httpx.Request('POST', 'https://upstream.test/projects/'))

    async def test_get_syncs_all_fields_and_detail_reads_database(self):
        response = await self.client.get('/api/projects')
        self.assertEqual(response.status_code, 200, response.text)
        row = response.json()[0]
        for key, value in PROJECT.items():
            self.assertEqual(row['gsolve_project_id' if key == 'id' else key], value)
        self.assertIsNone(row['user_id'])
        self.assertEqual(len(self.collection.rows), 1)
        self.assertEqual(self.upstream.post.call_args.kwargs['json'], {'source': 'GInfina', 'project_type': 2})
        for path in ['/api/projects?refresh=false', f"/api/projects/{row['id']}", '/api/projects/by-gsolve/5']:
            self.assertEqual((await self.client.get(path)).status_code, 200)
        self.assertEqual(self.upstream.post.await_count, 1)

    async def test_repeat_sync_updates_existing_id_and_preserves_owner(self):
        await self.client.post('/api/projects/sync')
        saved = self.collection.rows[0]
        saved['_id'] = 'existing-local-id'
        saved['user_id'] = 'local-owner'
        created_at = saved['created_at']
        self.respond({'code': '001', 'project_list': [{**PROJECT, 'project_name': 'Updated'}]})
        response = await self.client.post('/api/projects/sync')
        self.assertEqual(response.json()['synced_count'], 1)
        self.assertEqual(len(self.collection.rows), 1)
        self.assertEqual((saved['_id'], saved['user_id'], saved['created_at']), ('existing-local-id', 'local-owner', created_at))
        self.assertEqual(saved['project_name'], 'Updated')

    async def test_invalid_batch_writes_nothing(self):
        for payload in [
            {'code': '999', 'project_list': [PROJECT]},
            {'code': '001', 'project_list': [PROJECT, {'id': None}]},
            {'code': '001', 'project_list': [PROJECT, PROJECT]},
            {'code': '001', 'project_list': {}},
        ]:
            self.respond(payload)
            response = await self.client.post('/api/projects/sync')
            self.assertEqual(response.status_code, 502, response.text)
            self.assertEqual(self.collection.rows, [])

    async def test_upstream_failure_preserves_cached_records(self):
        await self.client.post('/api/projects/sync')
        for error, status in [(httpx.ConnectError('private details'), 502), (httpx.ReadTimeout('private details'), 504)]:
            self.upstream.post.side_effect = error
            response = await self.client.get('/api/projects')
            self.assertEqual(response.status_code, status)
            self.assertNotIn('private details', response.text)
            cached = await self.client.get('/api/projects?refresh=false')
            self.assertEqual(cached.status_code, 200)
            self.assertEqual(len(cached.json()), 1)

    async def test_empty_response_does_not_delete_local_projects(self):
        await self.client.post('/api/projects/sync')
        self.respond({'code': '001', 'project_list': []})
        response = await self.client.post('/api/projects/sync')
        self.assertEqual(response.json()['synced_count'], 0)
        self.assertEqual(len(self.collection.rows), 1)
