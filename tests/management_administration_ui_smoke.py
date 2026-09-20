"""Run with local Vite; browser requests use isolated fixtures, never MongoDB."""
import asyncio
import inspect
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright, expect
from test_ewp_management_administration import ManagementTests


async def main():
    fixture = ManagementTests(); await fixture.asyncSetUp()
    errors, calls = [], []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            async def intercept(route):
                req = route.request
                headers = {'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS'}
                if req.method == 'OPTIONS':
                    await route.fulfill(status=204, headers=headers); return
                path = '/api/' + req.url.split('/api/', 1)[1]
                if not path.startswith('/api/ewp/management-administration/'):
                    await route.fulfill(status=200, content_type='application/json', body='[]', headers=headers); return
                response = await fixture.client.request(req.method, path, content=req.post_data, headers={'content-type': 'application/json'})
                calls.append((req.method, path, response.status_code))
                await route.fulfill(status=response.status_code, content_type='application/json', body=response.text, headers=headers)
            await page.route('**/api/**', intercept)
            async def field(name, value):
                await page.get_by_label(re.compile('^' + re.escape(name) + r'\s*\*?$')).fill(value)
            async def select(name, value):
                await page.get_by_role('combobox', name=re.compile('^' + re.escape(name) + r'\s*\*?$')).click()
                await page.get_by_role('option', name=value, exact=True).click()
            async def save():
                await field('Recorded by', 'Engineering Manager')
                await field('Change note', 'Confirmed in coordination meeting')
                await page.get_by_role('button', name='Save changes', exact=True).click()
                await expect(page.get_by_role('dialog')).not_to_be_visible()
            async def select_ewp():
                await select('Project', 'P01 Hospital Solar')
                await select('Engineering Work Package', 'EWP-001 / Electrical Design')
                await expect(page.get_by_role('button', name='EWP settings')).to_be_visible()
            await page.goto('http://127.0.0.1:5173/ginfina/ewp/management-administration')
            await select_ewp()
            await page.get_by_role('tab', name='Team & assignments').click()
            await page.get_by_role('button', name='Add team member').click()
            await select('User', 'Engineer A'); await select('Role', 'Lead Engineer')
            await field('Assignment', 'Coordinate electrical design'); await save()
            await expect(page.get_by_role('cell', name='Engineer A', exact=True)).to_be_visible()
            await page.get_by_role('tab', name='Milestones', exact=True).click()
            await page.get_by_role('button', name='Add milestone').click()
            await field('Milestone name', 'IFC release'); await field('Owner', 'Engineer A')
            await field('Target date', '2026-12-20'); await page.get_by_label('Change note').click(); await save()
            await expect(page.get_by_role('cell', name='IFC release', exact=True)).to_be_visible()
            await page.get_by_role('tab', name='Issues, risks & actions').click()
            await page.get_by_role('button', name='Add action', exact=True).click()
            await field('Title', 'Verify roof load'); await field('Owner', 'Engineer B')
            await field('Due date', '2026-12-15'); await page.get_by_label('Change note').click(); await save()
            await page.get_by_role('button', name='Edit', exact=True).click()
            await select('Status', 'CLOSED'); await field('Resolution / evidence reference', 'Verified calculation REF-002'); await save()
            await expect(page.get_by_text('CLOSED', exact=True)).to_be_visible()
            await page.get_by_role('tab', name='Access', exact=True).click()
            await page.get_by_role('button', name='Assign access').click()
            await select('User', 'Engineer A'); await save()
            await page.get_by_role('button', name='EWP settings').click()
            await select('Status', 'ON_HOLD'); await save()
            await page.get_by_role('tab', name='Activity history').click()
            await expect(page.get_by_text('SETTINGS UPDATED', exact=True)).to_be_visible()
            await page.reload(); await select_ewp()
            await expect(page.get_by_text('ON HOLD', exact=True)).to_be_visible()
            await page.get_by_role('tab', name='Team & assignments').click()
            await expect(page.get_by_role('cell', name='Engineer A', exact=True)).to_be_visible()
            await page.get_by_role('tab', name='Overview', exact=True).click()
            await page.screenshot(path='../.tmp/management-desktop.png', full_page=True)
            await page.set_viewport_size({'width': 390, 'height': 844})
            await page.evaluate('window.scrollTo(0, 0)'); await page.wait_for_timeout(400)
            await page.screenshot(path='../.tmp/management-mobile.png', full_page=True)
            assert not errors, errors
            assert all(status in {200, 201} for _, _, status in calls), calls
            print(f'Management browser checks passed: create, edit, status, history and reload; {len(calls)} API requests; no browser errors.')
            await browser.close()
    finally:
        while fixture._cleanups:
            callback, args, kwargs = fixture._cleanups.pop()
            result = callback(*args, **kwargs)
            if inspect.isawaitable(result): await result


if __name__ == '__main__': asyncio.run(main())
