"""Run with Vite on 127.0.0.1:5173; API calls use isolated in-memory data."""
import asyncio
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright, expect
from test_ewp_quantities_procurement import QuantitiesTests


async def main():
    fixture = QuantitiesTests()
    await fixture.asyncSetUp()
    calls, errors = [], []
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            async def intercept(route):
                req = route.request
                headers = {"access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS"}
                if req.method == "OPTIONS":
                    await route.fulfill(status=204, headers=headers); return
                assert "authorization" not in req.headers
                path = "/api/" + req.url.split("/api/", 1)[1]
                response = await fixture.client.request(req.method, path, content=req.post_data, headers={"content-type": "application/json"})
                calls.append((req.method, path, response.status_code))
                await route.fulfill(status=response.status_code, content_type="application/json", body=response.text, headers=headers)

            await page.route("**/api/ewp/quantities-procurement/**", intercept)
            await page.goto("http://127.0.0.1:5173/ginfina/ewp/quantities-procurement")

            async def choose(label, option):
                await page.get_by_role("combobox", name=re.compile("^" + label + r"\s*\*?$")).click()
                await page.get_by_role("option", name=option).click()

            async def fill(label, value):
                await page.get_by_label(re.compile("^" + label + r"\s*\*?$")).fill(value)

            async def action(label, actor_label="Recorded by", option=None):
                await page.get_by_role("button", name=label, exact=True).click()
                await fill(actor_label, "Engineer A")
                if option:
                    await choose(*option)
                await page.get_by_role("button", name="Save decision", exact=True).click()
                await expect(page.get_by_role("dialog")).not_to_be_visible()

            await choose("EWP", "EWP-001")
            await page.get_by_role("button", name="Create QTO", exact=True).click()
            await fill("Register name", "Pilot cable quantities")
            await page.get_by_role("button", name="Create register", exact=True).click()
            await expect(page.get_by_role("heading", name="Pilot cable quantities", exact=True)).to_be_visible()
            await page.get_by_role("button", name="Add quantity item", exact=True).click()
            await fill("Item", "DC Cable 6 mm2")
            await fill("Quantity", "4200")
            await fill("Unit", "m")
            await choose("Released document revision", "SLD / D03")
            await fill("Drawing / schedule reference", "Sheet 2, row 8")
            await fill("Derivation / calculation notes", "42 runs x 100 m")
            await page.get_by_role("button", name="Save quantity", exact=True).click()
            await expect(page.get_by_role("cell", name="4,200", exact=True)).to_be_visible()
            await action("Validate quantities")
            await action("Create BOQ / EBOM", option=("Quantity set type", "EBOM"))
            await action("Review quantity set", "Reviewer name")
            await action("Approve quantity set", "Approver name")
            await action("Mark procurement ready")
            await page.get_by_role("button", name="Record procurement reference", exact=True).click()
            await fill("Recorded by", "Engineer A")
            await fill("Procurement system", "Pilot procurement")
            await fill("External reference", "PO-001")
            await page.get_by_role("button", name="Save reference", exact=True).click()
            await expect(page.get_by_text("PO-001", exact=True)).to_be_visible()
            await page.get_by_role("button", name="Update procurement status", exact=True).click()
            await fill("Recorded by", "Engineer A")
            await fill("Tracking note / evidence reference", "Sent manually, tracking ref TX-001")
            await page.get_by_role("button", name="Save status", exact=True).click()
            await expect(page.get_by_role("dialog")).not_to_be_visible()
            await page.get_by_role("button", name="Refresh", exact=True).click()
            await expect(page.get_by_text("PO-001", exact=True)).to_be_visible()
            await expect(page.get_by_text("Sent manually, tracking ref TX-001", exact=True).first).to_be_visible()
            await expect(page.get_by_role("button", name="Add quantity item", exact=True)).not_to_be_visible()
            await page.get_by_role("button", name="View snapshot", exact=True).click()
            await expect(page.get_by_role("dialog").get_by_role("cell", name="4,200", exact=True)).to_be_visible()
            await page.keyboard.press("Escape")
            folder = Path(__file__).parents[2] / ".tmp"; folder.mkdir(exist_ok=True)
            await page.screenshot(path=str(folder / "quantities-procurement.png"), full_page=True)
            assert not errors, errors
            assert all(code < 400 for _, _, code in calls), calls
            handoff = next(iter(fixture.db["ewp_procurement_handoff"].rows.values()))
            assert handoff["status"] == "SENT"
            assert handoff["source_release_ids"] == ["d03"]
            print(json.dumps({"result": "passed", "api_requests": len(calls), "javascript_errors": errors, "procurement_status": handoff["status"]}))
            await browser.close()
    finally:
        await fixture.client.aclose()
        fixture.doCleanups()


if __name__ == "__main__":
    asyncio.run(main())
