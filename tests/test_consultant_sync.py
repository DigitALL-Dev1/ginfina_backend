import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import bcrypt
from fastapi import FastAPI
import httpx
from test_project_sync import Collection


PROFILE = {'consultant_id': 2262, 'salutation': 'Mr.', 'name': 'Test Consultant',
           'username': 'consultant@example.test', 'email': 'consultant@example.test',
           'password': 'test-only-password', 'consultant_company': 'Example', 'company_id': 1662}


class ConsultantSyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        spec = importlib.util.spec_from_file_location('consultant_test_api', Path(__file__).parents[1] / 'api' / 'consultant.py')
        self.api = importlib.util.module_from_spec(spec)
        with patch('dotenv.load_dotenv'), patch('motor.motor_asyncio.AsyncIOMotorClient'):
            spec.loader.exec_module(self.api)
        self.api.consultants_collection = self.collection = Collection()
        app = FastAPI(); app.include_router(self.api.router, prefix='/api')
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)
        self.upstream = AsyncMock(); self.upstream.__aenter__.return_value = self.upstream
        p = patch.object(self.api.httpx, 'AsyncClient', return_value=self.upstream)
        p.start(); self.addCleanup(p.stop)
        self.respond([PROFILE])

    def respond(self, rows):
        self.upstream.post.return_value = httpx.Response(200,
            json={'code': '001', 'status': 'success', 'data': rows},
            request=httpx.Request('POST', 'https://upstream.test/consultants/'))

    async def test_sync_stores_hash_and_get_never_exposes_credentials(self):
        response = await self.client.get('/api/consultants')
        self.assertEqual(response.status_code, 200, response.text)
        row = self.collection.rows[0]
        self.assertNotIn('password', row)
        self.assertTrue(bcrypt.checkpw(PROFILE['password'].encode(), row['password_hash'].encode()))
        self.assertEqual(self.upstream.post.call_args.kwargs['json'], {'user_type': 'Consultant', 'project_source': 'GInfina'})
        for path in ['/api/consultants?refresh=false', '/api/consultants/2262']:
            result = await self.client.get(path)
            self.assertEqual(result.status_code, 200)
            self.assertNotIn('password', result.text)
            self.assertNotIn(PROFILE['password'], result.text)
        self.assertEqual(self.upstream.post.await_count, 1)

    async def test_repeated_sync_preserves_id_and_creation_date(self):
        await self.client.post('/api/consultants/sync')
        original = dict(self.collection.rows[0])
        self.respond([{**PROFILE, 'name': 'Updated', 'password': None}])
        response = await self.client.post('/api/consultants/sync')
        self.assertEqual(response.json()['synced_count'], 1)
        self.assertEqual(len(self.collection.rows), 1)
        row = self.collection.rows[0]
        for field in ['_id', 'created_at', 'password_hash']:
            self.assertEqual(row[field], original[field])
        self.assertEqual(row['name'], 'Updated')

    async def test_invalid_batch_is_rejected_without_writes(self):
        for rows in [[PROFILE, {'consultant_id': None}], [PROFILE, PROFILE], [{**PROFILE, 'password': 'x' * 73}]]:
            self.respond(rows)
            response = await self.client.post('/api/consultants/sync')
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('test-only-password', response.text)
            self.assertEqual(self.collection.rows, [])

    async def test_failure_preserves_cache_and_missing_returns_404(self):
        await self.client.post('/api/consultants/sync')
        self.upstream.post.side_effect = httpx.ReadTimeout('private upstream details')
        response = await self.client.get('/api/consultants')
        self.assertEqual(response.status_code, 504)
        self.assertEqual((await self.client.get('/api/consultants?refresh=false')).status_code, 200)
        self.assertEqual((await self.client.get('/api/consultants/999')).status_code, 404)
