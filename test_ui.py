"""
Playwright UI test for AIMS
Run: python3 test_ui.py

Requires: pip install playwright && playwright install chromium
"""

import asyncio
from playwright.async_api import async_playwright

URL = "http://localhost:8501"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headless=False so you can see it
        page    = await browser.new_page(viewport={"width": 1280, "height": 800})

        print(f"Opening {URL} ...")
        await page.goto(URL)
        await page.wait_for_timeout(3000)  # wait for Streamlit to load

        # ── Screenshot 1: initial state ────────────────────────────────────────
        await page.screenshot(path="screenshot_01_initial.png")
        print("screenshot_01_initial.png saved")

        # ── Check if login form is visible ─────────────────────────────────────
        username_field = page.get_by_label("Username")
        if await username_field.is_visible():
            print("✓ Login page is showing correctly")

            # ── Test login with Priyanka credentials ───────────────────────────
            await username_field.fill("Priyanka")
            await page.get_by_label("Password").fill("Priyanka")
            await page.screenshot(path="screenshot_02_filled.png")
            print("screenshot_02_filled.png saved")

            await page.get_by_role("button", name="Login").click()
            await page.wait_for_timeout(2000)

            await page.screenshot(path="screenshot_03_after_login.png")
            print("screenshot_03_after_login.png saved")

            # Check tabs are visible
            if await page.get_by_text("My Tickets").is_visible():
                print("✓ Login successful — main app loaded")
            else:
                print("✗ Login may have failed — check screenshot_03_after_login.png")

        else:
            # Login not showing — capture what IS showing
            content = await page.content()
            print("✗ Login page NOT found. Page content snippet:")
            print(content[:500])
            await page.screenshot(path="screenshot_debug.png")
            print("screenshot_debug.png saved — check what's on screen")

        await browser.close()
        print("\nDone. Check the PNG files in your AIMS folder.")


asyncio.run(main())
