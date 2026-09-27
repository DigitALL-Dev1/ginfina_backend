"""Authentication response checks using mocked database and email services."""
import importlib.util
import unittest
import re
import smtplib
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient


class AuthenticationRolesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        spec = importlib.util.spec_from_file_location('auth_role_test_module', Path(__file__).parents[1] / 'api' / 'auth.py')
        self.api = importlib.util.module_from_spec(spec)
        # Import without opening a database connection or loading application secrets.
        with patch('dotenv.load_dotenv'), patch('motor.motor_asyncio.AsyncIOMotorClient'):
            spec.loader.exec_module(self.api)
        self.api.EMAIL_PROVIDER = 'smtp'
        self.api.RESEND_API_KEY = ''
        self.api.EMAIL_FROM = ''
        self.real_user_lookup = self.api.get_user_by_email_or_username
        self.user = dict(_id='test-user', name='Test Engineer', email='test@example.com', password_hash='mock', role='reviewer')
        self.api.get_user_by_email_or_username = AsyncMock(side_effect=lambda _: self.user)
        self.api.verify_password = lambda *_: True
        self.api.create_access_token = Mock(return_value='test-access-token')
        self.app = FastAPI()
        self.app.include_router(self.api.router, prefix='/auth')
        self.client = AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_every_role_requires_mfa(self):
        for role in ['reviewer', 'APPROVER', 'ADMIN', 'consultant', 'user', 'NEW_ROLE', '']:
            self.user['role'] = role
            with patch.object(self.api, 'send_email') as email, patch.object(self.api, 'create_temp_token', return_value='test-temp-token'):
                response = await self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['mfa_required'])
            self.assertEqual(response.json()['temp_token'], 'test-temp-token')
            self.assertNotIn('access_token', response.json())
            email.assert_called_once()
        self.api.create_access_token.assert_not_called()

    async def test_admin_mfa_returns_role_only_after_verification(self):
        self.user['role'] = 'ADMIN'
        with patch.object(self.api, 'send_email'), patch.object(self.api, 'create_temp_token', return_value='test-temp-token'):
            response = await self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'})
        self.assertTrue(response.json()['mfa_required'])
        self.assertNotIn('access_token', response.json())
        with patch.object(self.api.jwt, 'decode', return_value={'type': 'mfa_temp', 'sub': 'test@example.com', 'code': '123456'}):
            response = await self.client.post('/auth/verify-mfa', json={'temp_token': 'test-temp-token', 'code': '123456'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['role'], 'ADMIN')

    async def test_google_login_also_requires_mfa(self):
        with patch.object(self.api, 'send_email'), patch.object(self.api, 'create_temp_token', return_value='test-temp-token'):
            response = await self.client.post('/auth/google-login', json={'credential': 'test-google-token'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['mfa_required'])
        self.assertNotIn('access_token', response.json())
        self.api.create_access_token.assert_not_called()

    async def test_verified_reviewer_receives_role_and_access_token(self):
        with patch.object(self.api.jwt, 'decode', return_value={'type': 'mfa_temp', 'sub': 'test@example.com', 'code': '123456'}):
            response = await self.client.post('/auth/verify-mfa', json={'temp_token': 'test-temp-token', 'code': '123456'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['role'], 'REVIEWER')
        self.assertEqual(response.json()['access_token'], 'test-access-token')

    async def test_wrong_or_expired_code_never_issues_access_token(self):
        with patch.object(self.api.jwt, 'decode', return_value={'type': 'mfa_temp', 'sub': 'test@example.com', 'code': '123456'}):
            response = await self.client.post('/auth/verify-mfa', json={'temp_token': 'test-temp-token', 'code': '654321'})
        self.assertEqual(response.status_code, 400)
        with patch.object(self.api.jwt, 'decode', side_effect=self.api.jwt.ExpiredSignatureError):
            response = await self.client.post('/auth/verify-mfa', json={'temp_token': 'test-temp-token', 'code': '123456'})
        self.assertEqual(response.status_code, 401)
        self.api.create_access_token.assert_not_called()

    async def test_mfa_temp_token_cannot_be_used_as_access_token(self):
        with patch.object(self.api.jwt, 'decode', return_value={'type': 'mfa_temp', 'sub': 'test@example.com', 'code': '123456'}):
            with self.assertRaises(HTTPException) as error:
                self.api.verify_token('test-temp-token')
        self.assertEqual(error.exception.status_code, 401)

    async def test_invalid_password_never_sends_mfa_or_access_token(self):
        with patch.object(self.api, 'verify_password', return_value=False), patch.object(self.api, 'send_email') as email:
            response = await self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'wrong'})
        self.assertEqual(response.status_code, 401)
        email.assert_not_called()
        self.api.create_access_token.assert_not_called()

    async def test_email_failure_does_not_claim_code_was_sent(self):
        with patch.object(self.api, 'send_email', return_value=False), patch.object(self.api, 'create_temp_token') as token:
            response = await self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('temp_token', response.json())
        token.assert_not_called()
        self.api.create_access_token.assert_not_called()

    async def test_missing_smtp_returns_actionable_error(self):
        with patch.object(self.api, 'SMTP_USERNAME', ''), patch.object(self.api, 'SMTP_PASSWORD', ''):
            response = await self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'})
        self.assertEqual(response.status_code, 503)
        self.assertIn('not configured', response.json()['detail'])
        self.assertNotIn('temp_token', response.json())

    async def test_smtp_failures_return_503_without_sensitive_details(self):
        for failure in [TimeoutError('private detail'), smtplib.SMTPAuthenticationError(535, b'private detail')]:
            with patch.multiple(self.api, SMTP_USERNAME='test', SMTP_PASSWORD='test', SMTP_PORT=587), patch.object(self.api.smtplib, 'SMTP', side_effect=failure):
                response = await self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private detail', response.text)

    async def test_smtp_ssl_and_starttls_use_timeouts(self):
        for port in [465, 587]:
            with patch.multiple(self.api, SMTP_USERNAME='test', SMTP_PASSWORD='test', SMTP_PORT=port), patch.object(self.api.smtplib, 'SMTP') as smtp, patch.object(self.api.smtplib, 'SMTP_SSL') as smtp_ssl:
                self.assertTrue(self.api.send_email('test@example.com', 'Test', 'Test'))
                active, inactive = (smtp_ssl, smtp) if port == 465 else (smtp, smtp_ssl)
                inactive.assert_not_called()
                self.assertEqual(active.call_args.kwargs['timeout'], self.api.SMTP_TIMEOUT_SECONDS)
                server = active.return_value.__enter__.return_value
                self.assertEqual(server.starttls.call_count, 0 if port == 465 else 1)
                server.send_message.assert_called_once()

    async def test_real_generated_code_matches_issued_session(self):
        with patch.object(self.api, 'send_email', return_value=True) as email, patch.object(self.api, 'SECRET_KEY', 'isolated-test-secret-not-a-production-key'), patch.object(self.api.secrets, 'randbelow', return_value=123):
            login = await self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'})
            code = re.search(r'<strong>(\d{6})</strong>', email.call_args.args[2]).group(1)
            self.assertEqual(code, '000123')
            verified = await self.client.post('/auth/verify-mfa', json={'temp_token': login.json()['temp_token'], 'code': f' {code} '})
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json()['role'], 'REVIEWER')

    async def test_email_wait_is_bounded(self):
        async def stalled(*args):
            await asyncio.sleep(60)
        with patch.object(self.api, 'run_in_threadpool', side_effect=stalled), patch.object(self.api, 'EMAIL_DELIVERY_DEADLINE_SECONDS', 0.01):
            response = await asyncio.wait_for(self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'}), timeout=1)
        self.assertEqual(response.status_code, 503)
        self.assertIn('delivery timed out', response.json()['detail'])
        self.api.create_access_token.assert_not_called()

    async def test_database_wait_is_bounded(self):
        async def stalled(*args):
            await asyncio.sleep(60)
        with patch.object(self.api, 'get_user_by_email_or_username', self.real_user_lookup), patch.object(self.api.users_collection, 'find_one', side_effect=stalled), patch.object(self.api, 'AUTH_DATABASE_DEADLINE_SECONDS', 0.01):
            response = await asyncio.wait_for(self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'}), timeout=1)
        self.assertEqual(response.status_code, 503)
        self.assertIn('temporarily unavailable', response.json()['detail'])

    async def test_resend_uses_https_without_smtp(self):
        response = Mock(ok=True)
        response.json.return_value = {'id': 'provider-message-id'}
        with patch.multiple(self.api, EMAIL_PROVIDER='resend', RESEND_API_KEY='test-key', EMAIL_FROM='verified@example.com'), patch.object(self.api.requests, 'post', return_value=response) as post, patch.object(self.api.smtplib, 'SMTP') as smtp:
            result = await self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()['mfa_required'])
        smtp.assert_not_called()
        self.assertEqual(post.call_args.args[0], 'https://api.resend.com/emails')
        self.assertEqual(post.call_args.kwargs['json']['to'], ['test@example.com'])
        self.assertEqual(post.call_args.kwargs['timeout'], (5, 10))

    async def test_resend_failure_never_claims_delivery(self):
        rejected = Mock(ok=False, status_code=403)
        for failure in ['missing-key', 'provider-rejected', 'connection-timeout']:
            with patch.multiple(self.api, EMAIL_PROVIDER='resend', RESEND_API_KEY='' if failure == 'missing-key' else 'test-key', EMAIL_FROM='verified@example.com'), patch.object(self.api.requests, 'post', return_value=rejected, side_effect=self.api.requests.Timeout() if failure == 'connection-timeout' else None):
                response = await self.client.post('/auth/login', json={'email': 'test@example.com', 'password': 'test'})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('temp_token', response.json())
