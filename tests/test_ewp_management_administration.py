"""Management API regression tests; all database operations use in-memory fixtures."""
import copy
import unittest
from datetime import date, timedelta
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from api.EWP import management_administration as api, completion_governance as completion
from test_ewp_approval_release import Collection, Database

ROOT = '/api/ewp/management-administration'


def fixture():
    db = Database()
    db['ginfina_project'] = Collection([{'_id': 'project', 'project_code': 'P01', 'project_name': 'Hospital Solar'}])
    db['ewp'] = Collection([{'_id': 'ewp', 'project_id': 'project', 'ewp_code': 'EWP-001', 'ewp_name': 'Electrical Design', 'discipline': 'ELECTRICAL', 'status': 'IN_PROGRESS'},
                            {'_id': 'other', 'project_id': 'elsewhere', 'status': 'DRAFT'}])
    db['users'] = Collection([{'_id': 'user', 'name': 'Engineer A', 'is_active': True, 'password_hash': 'never return'},
                              {'_id': 'second', 'name': 'Engineer B'}, {'_id': 'disabled', 'name': 'Former user', 'is_active': False}])
    return db


class ManagementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = fixture()
        for module in [api, completion]:
            patcher = patch.object(module, 'db', self.db); patcher.start(); self.addCleanup(patcher.stop)
        app = FastAPI(); app.include_router(api.router, prefix='/api'); app.include_router(completion.router, prefix='/api')
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    async def overview(self):
        result = await self.client.get(ROOT + '/ewps/ewp/overview')
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    async def write(self, kind, data, identity=None, expected=None, version=None):
        if version is None: version = (await self.overview())['version']
        result = await self.client.request('PATCH' if identity else 'POST', ROOT + f'/ewps/ewp/records/{kind}' + (f'/{identity}' if identity else ''),
            json={'version': version, 'actor': 'Manager', 'comment': 'Evidence REF-001', 'data': data})
        self.assertEqual(result.status_code, expected or (200 if identity else 201), result.text)
        return result.json()

    def action(self, **extra):
        return {'title': 'Verify roof load', 'owner': 'Engineer A', 'due_date': str(date.today() - timedelta(days=1)), **extra}

    async def test_project_scoping_safe_users_and_empty_overview(self):
        self.assertEqual((await self.client.get(ROOT + '/projects')).json()[0]['ewp_count'], 1)
        self.assertEqual([e['id'] for e in (await self.client.get(ROOT + '/ewps?project_id=project')).json()], ['ewp'])
        users = (await self.client.get(ROOT + '/users')).json()
        self.assertEqual({u['id'] for u in users}, {'user', 'second'})
        self.assertTrue(all(set(u) == {'id', 'name'} for u in users))
        overview = await self.overview()
        self.assertEqual(overview['overall_progress'], 0)
        self.assertFalse(overview['history'])
        self.assertFalse(self.db['ewp_activity_log'].rows)

    async def test_all_collections_persist_and_audit_before_after(self):
        examples = {'team': {'user_id': 'user', 'role': 'Lead Engineer', 'discipline': 'Electrical'},
                    'milestones': {'name': 'IFC release', 'owner': 'Manager', 'target_date': '2026-12-20'},
                    'access': {'user_id': 'user', 'permissions': ['VIEW', 'EDIT']},
                    **{kind: self.action() for kind in ['issues', 'risks', 'actions']}}
        for kind, fields in examples.items():
            result = await self.write(kind, fields)
            self.assertEqual(len(self.db[api.COLLECTIONS[kind]].rows), 1)
            identity = result[kind][0]['id']
            edited = {**fields, **({'active': False} if kind in {'team', 'access'} else {'status': 'COMPLETE'} if kind == 'milestones' else {'status': 'CLOSED', 'resolution': 'Verified REF-002'})}
            result = await self.write(kind, edited, identity)
            self.assertIsNotNone(result['history'][0]['before'])
            self.assertEqual(result['version'], len(self.db['ewp_activity_log'].rows))
        self.assertEqual((await self.overview())['version'], 12)

    async def test_invalid_records_and_closed_resolution_required(self):
        await self.write('actions', self.action(status='CLOSED'), expected=422)
        await self.write('milestones', {'name': 'x', 'owner': 'y', 'target_date': 'bad'}, expected=422)
        await self.write('team', {'user_id': 'disabled', 'role': 'Engineer', 'discipline': 'Civil'}, expected=400)
        await self.write('access', {'user_id': 'user', 'permissions': ['ROOT']}, expected=422)
        self.assertEqual((await self.overview())['version'], 0)

    async def test_duplicate_lead_membership_and_stale_versions(self):
        team = {'user_id': 'user', 'role': 'Lead Engineer', 'discipline': 'Electrical'}
        await self.write('team', team)
        self.assertEqual(self.db['ewp'].rows['ewp']['lead_engineer'], 'Engineer A')
        await self.write('team', {**team, 'role': 'Reviewer'}, expected=409)
        await self.write('team', {**team, 'user_id': 'second'}, expected=409)
        await self.write('actions', self.action(), expected=409, version=0)
        await self.write('actions', self.action(), 'another-ewp-record', expected=404)

    async def test_progress_and_attention_use_saved_records(self):
        self.db['ewp_engineering_work'] = Collection([{'_id': 'work', 'ewp_id': 'ewp', 'status': 'READY_FOR_OUTPUT'},
            {'_id': 'late', 'ewp_id': 'ewp', 'title': 'Late work', 'status': 'IN_PROGRESS', 'planned_finish': '2020-01-01'}])
        self.db['ewp_deliverable'] = Collection([{'_id': 'del', 'ewp_id': 'ewp', 'name': 'SLD', 'status': 'READY_FOR_REVIEW', 'planned_issue_date': str(date.today())}])
        self.db['ewp_document'] = Collection([{'_id': 'doc', 'ewp_id': 'ewp', 'document_code': 'SLD', 'current_revision_id': 'rev', 'deliverable_id': 'del'}])
        self.db['ewp_document_revision'] = Collection([{'_id': 'rev', 'document_id': 'doc', 'status': 'REVIEW_COMPLETED', 'revision_no': 'D01'}])
        self.db['ewp_document_reviewer'] = Collection([{'_id': 'review', 'document_id': 'doc', 'revision_id': 'rev', 'status': 'COMPLETED', 'decision': 'ACCEPT'}])
        result = await self.write('actions', self.action())
        self.assertEqual(result['metrics'][0]['percent'], 50)
        self.assertEqual(result['metrics'][2]['percent'], 100)
        self.assertEqual(result['metrics'][3]['percent'], 0)
        self.assertEqual({r['kind'] for r in result['attention']}, {'OVERDUE_WORK', 'PENDING_APPROVAL', 'UPCOMING_DELIVERABLE'})
        self.assertEqual(result['counts']['overdue_actions'], 1)

    async def test_settings_status_and_date_guards(self):
        payload = {'version': 0, 'actor': 'Manager', 'comment': 'Plan update', 'discipline': 'Civil'}
        for extra, code in [({'status': 'CLOSED'}, 422), ({'status': 'READY_FOR_OUTPUT'}, 409),
                            ({'planned_start': '2026-12-01', 'planned_finish': '2026-01-01'}, 422), ({'status': 'ON_HOLD'}, 200)]:
            result = await self.client.patch(ROOT + '/ewps/ewp/settings', json={**payload, **extra})
            self.assertEqual(result.status_code, code, result.text)
        self.assertEqual(self.db['ewp'].rows['ewp']['status'], 'ON_HOLD')
        self.db['ewp'].rows['ewp']['status'] = 'CLOSED'
        self.assertTrue((await self.overview())['read_only'])
        await self.write('actions', self.action(), expected=409)

    async def test_reporting_projections_recover_after_interrupted_save(self):
        with patch.object(api, 'project', side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):
                await api.create_record('ewp', 'actions', api.RecordWrite(version=0, actor='Manager', comment='Test', data=self.action()))
        result = await self.overview()
        self.assertEqual(result['version'], 1)
        self.assertEqual(len(self.db['ewp_action'].rows), 1)
        self.assertEqual(len(self.db['ewp_activity_log'].rows), 1)
        await self.overview()
        self.assertEqual(len(self.db['ewp_activity_log'].rows), 1)

    async def test_management_obligations_cannot_be_bypassed_in_completion(self):
        result = await self.write('actions', self.action(blocking=False))
        self.assertTrue(result['actions'][0]['blocking'])
        await self.write('issues', self.action(blocking=False))
        await self.write('risks', self.action(blocking=True))
        path = '/api/ewp/completion-governance/ewps/ewp'
        summary = (await self.client.get(path + '/summary')).json()
        managed = [o for o in summary['obligations'] if o.get('managed_in')]
        self.assertEqual(len(managed), 2)
        response = await self.client.post(path + '/resolutions', json={'version': 0, 'actor': 'Manager', 'comment': 'skip',
            'obligation_id': managed[0]['id'], 'source_hash': managed[0]['source_hash'], 'status': 'CLOSED'})
        self.assertEqual(response.status_code, 409)
        await self.write('actions', self.action(status='CLOSED', resolution='Verified'), result['actions'][0]['id'])
        summary = (await self.client.get(path + '/summary')).json()
        self.assertFalse(next(c for c in summary['checks'] if c['id'] == 'actions')['issues'])

    async def test_completion_commit_rejects_management_race(self):
        stale = copy.deepcopy(self.db['ewp'].rows['ewp'])
        await self.write('actions', self.action())
        request = completion.Action(version=0, actor='Manager', comment='Checked')
        with self.assertRaises(HTTPException) as error:
            await completion.save(stale, completion.control(stale), request, 'TEST')
        self.assertEqual(error.exception.status_code, 409)

    async def test_management_commit_rejects_concurrent_closure(self):
        stale = copy.deepcopy(self.db['ewp'].rows['ewp'])
        self.db['ewp'].rows['ewp']['completion_control'] = {'version': 1}
        with self.assertRaises(HTTPException) as error:
            await api.commit(stale, api.state_of(stale), api.ActorWrite(version=0, actor='Manager', comment='Checked'), 'TEST', None, {})
        self.assertEqual(error.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main()
