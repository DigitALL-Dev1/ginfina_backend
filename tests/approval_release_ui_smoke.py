"""Browser smoke test against Vite, routing API calls to an isolated test database.

Start the frontend on port 5173, then from backend run:
python -B tests/approval_release_ui_smoke.py
"""
import asyncio
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright, expect
from test_ewp_approval_release import ApprovalReleaseTests


async def main():
    fixture = ApprovalReleaseTests()
    await fixture.asyncSetUp()
    calls, errors = [], []
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            async def api_route(route):
                req = route.request
                headers = {"access-control-allow-origin": "*", "access-control-allow-headers": "*",
                           "access-control-allow-methods": "GET,POST,PUT,OPTIONS"}
                if req.method == "OPTIONS":
                    await route.fulfill(status=204, headers=headers)
                    return
                path = "/api/" + req.url.split("/api/", 1)[1]
                assert "authorization" not in req.headers
                response = await fixture.client.request(req.method, path, content=req.post_data,
                    headers={"content-type": "application/json"})
                calls.append((req.method, path, response.status_code))
                await route.fulfill(status=response.status_code, content_type="application/json",
                    body=response.text, headers=headers)

            await page.route("**/api/ewp/approval-release/**", api_route)
            await page.goto("http://127.0.0.1:5173/ginfina/ewp/approval-release")

            async def choose(label, option):
                await page.get_by_role("combobox", name=re.compile("^" + label + r"\s*\*?$")).click()
                await page.get_by_role("option", name=option).click()

            await choose("EWP", "EWP-001")
            await choose("Document", "SLD-001")
            await choose("Reviewed revision", "D03")
            await expect(page.get_by_role("heading", name="SLD-001 / D03")).to_be_visible()
            await choose("Engineering approver", "Engineering Manager")
            await page.get_by_role("button", name="Assign approver", exact=True).click()
            await expect(page.get_by_text("Assigned to:")).to_be_visible()
            await choose("Decision", "APPROVE WITH CONDITION")
            await page.get_by_role("textbox", name=re.compile(r"^Comment\s*\*?$" )).fill("Approved for controlled release")
            await page.get_by_role("textbox", name=re.compile(r"^Approval condition\s*\*?$" )).fill("Verify roof loading before installation")
            await page.get_by_role("checkbox").check()
            await page.get_by_role("button", name="Submit approval", exact=True).click()
            await expect(page.get_by_text("Ready for controlled release", exact=True)).to_be_visible()
            await page.get_by_role("button", name="Release D03", exact=True).click()
            await page.get_by_role("textbox", name="Release comment").fill("Controlled issue")
            await page.get_by_role("button", name="Confirm release", exact=True).click()
            await expect(page.get_by_text("D03 released and locked", exact=True)).to_be_visible()
            await page.get_by_role("button", name="Refresh", exact=True).click()
            await expect(page.get_by_text("D03 released and locked", exact=True)).to_be_visible()
            await page.get_by_role("tab", name="Design inputs & conditions").click()
            await page.get_by_role("button", name="Transformer Capacity").click()
            await expect(page.get_by_text("Verify equipment", exact=True)).to_be_visible()
            await page.get_by_role("tab", name="Traceability").click()
            await expect(page.get_by_text("REL-d03", exact=True)).to_be_visible()
            output = Path(__file__).parents[2] / ".tmp"
            output.mkdir(exist_ok=True)
            await page.screenshot(path=str(output / "approval-release-desktop.png"), full_page=True)
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.wait_for_timeout(300)  # Allow the existing shell's responsive transition to finish.
            await page.evaluate("window.scrollTo(0, 0)")
            await page.screenshot(path=str(output / "approval-release-mobile.png"), full_page=True)
            assert not errors, errors
            assert all(code < 400 for _, _, code in calls), calls
            assert len(fixture.db["ewp_document_release"].rows) == 1
            print(json.dumps({"result": "passed", "api_requests": len(calls), "javascript_errors": errors,
                              "release_status": fixture.db["ewp_document_revision"].rows["d03"]["status"]}))
            await browser.close()
    finally:
        await fixture.client.aclose()
        fixture.doCleanups()


if __name__ == "__main__":
    asyncio.run(main())
