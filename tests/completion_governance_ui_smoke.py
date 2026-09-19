"""Run with local Vite; browser API calls use in-memory data, never MongoDB."""
import asyncio
import re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright, expect
from test_ewp_completion_governance import CompletionTests


async def main():
    fixture = CompletionTests()
    await fixture.asyncSetUp()
    errors = []; calls = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            async def intercept(route):
                req = route.request
                headers = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET,POST,OPTIONS"}
                if req.method == "OPTIONS":
                    await route.fulfill(status=204, headers=headers); return
                path = "/api/" + req.url.split("/api/", 1)[1]
                if not path.startswith("/api/ewp/completion-governance/"):
                    await route.fulfill(status=200, content_type="application/json", body="[]", headers=headers); return
                response = await fixture.client.request(req.method, path, content=req.post_data, headers={"content-type": "application/json"})
                calls.append((req.method, path, response.status_code))
                await route.fulfill(status=response.status_code, content_type="application/json", body=response.text, headers=headers)
            await page.route("**/api/**", intercept)
            await page.goto("http://127.0.0.1:5173/ginfina/ewp/completion-governance")
            async def choose_ewp(label):
                await page.get_by_role("combobox", name="Engineering Work Package").click()
                await page.get_by_role("option", name=re.compile(label)).click()
            async def action(button, actor_label):
                await page.get_by_role("button", name=button, exact=True).click()
                await page.get_by_label(actor_label, exact=False).fill("Engineering Manager")
                await page.get_by_label("Comment / evidence reference").fill("Checked controlled records REF-001")
                await page.get_by_role("button", name="Save decision", exact=True).click()
                await expect(page.get_by_role("dialog")).not_to_be_visible()
            await choose_ewp("EWP-EMPTY")
            await expect(page.get_by_text("Completion blockers", exact=True)).to_be_visible()
            await expect(page.get_by_role("button", name="Submit for Closure", exact=True)).to_be_disabled()
            await choose_ewp("EWP-001")
            await expect(page.get_by_role("button", name="Run governance checks", exact=True)).to_be_enabled()
            await page.get_by_role("button", name="Add action", exact=True).click()
            await page.get_by_label(re.compile(r"^Action\s*\*?$")).fill("Confirm final handoff")
            await page.get_by_label("Recorded by").fill("Engineer A")
            await page.get_by_label("Comment / evidence reference").fill("Receipt needed")
            await page.get_by_role("button", name="Save decision", exact=True).click()
            await expect(page.get_by_role("dialog")).not_to_be_visible()
            await expect(page.get_by_role("button", name="Run governance checks", exact=True)).to_be_disabled()
            await action("Resolve", "Recorded by")
            await action("Run governance checks", "Governance reviewer")
            await action("Submit for Closure", "Recorded by")
            await action("Approve Closure", "Closure approver")
            await expect(page.get_by_text("EWP closed", exact=True)).to_be_visible()
            await page.reload()
            await choose_ewp("EWP-001")
            await expect(page.get_by_text("EWP closed", exact=True)).to_be_visible()
            await page.screenshot(path="../.tmp/completion-governance-desktop.png", full_page=True)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.screenshot(path="../.tmp/completion-governance-mobile.png", full_page=True)
            assert not errors, errors
            assert all(status == 200 for _, _, status in calls), calls
            print(f"Browser lifecycle passed: blockers, action resolution, governance, submission, closure, reload; {len(calls)} API requests; no browser errors.")
            await browser.close()
    finally:
        import inspect
        while fixture._cleanups:
            callback, args, kwargs = fixture._cleanups.pop()
            result = callback(*args, **kwargs)
            if inspect.isawaitable(result):
                await result


if __name__ == "__main__":
    asyncio.run(main())
