import asyncio
import os
from playwright.async_api import async_playwright
from app import TERMINAL_CLIENT_JS

ARTIFACT_DIR = "/Users/eshanparek/.gemini/antigravity/brain/41b33619-0995-408e-b34b-4351da675341"
TARGET_URL = "https://p01--news-engine-service--dkhqtlpvx6bh.code.run/"
RESOLVE_IP = "35.193.113.78"

async def run_verification():
    print("[Playwright] Launching Chromium with host resolver...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                f"--host-resolver-rules=MAP p01--news-engine-service--dkhqtlpvx6bh.code.run {RESOLVE_IP}",
                "--ignore-certificate-errors",
                "--no-sandbox"
            ]
        )
        
        # 1. Desktop Verification (1440x900)
        context_desktop = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            ignore_https_errors=True
        )
        page = await context_desktop.new_page()
        print(f"[Desktop] Navigating to {TARGET_URL}...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("#top_news_table", timeout=45000)
        await page.wait_for_selector("#epm-top-navbar", timeout=45000)
        await page.add_script_tag(content=TERMINAL_CLIENT_JS)
        await page.wait_for_timeout(4000)
        
        # Capture Tab 1 Desktop (Breaking Wire)
        p1 = os.path.join(ARTIFACT_DIR, "desktop_tab1_verified.png")
        await page.screenshot(path=p1)
        print(f"[Desktop] Saved Tab 1 to {p1}")
        
        # Switch to Tab 2 (Market Calendar)
        print("[Desktop] Switching to Tab 2 (Market Calendar)...")
        await page.evaluate("window.epmSwitchTab(1)")
        await page.wait_for_selector(".epm-dossier-table", timeout=20000)
        await page.wait_for_timeout(3000)
        p2 = os.path.join(ARTIFACT_DIR, "desktop_tab2_verified.png")
        await page.screenshot(path=p2)
        print(f"[Desktop] Saved Tab 2 to {p2}")
        
        # Open Side Menu
        print("[Desktop] Opening Side Menu...")
        await page.evaluate("window.epmOpenSideMenu()")
        await page.wait_for_timeout(1000)
        p_menu = os.path.join(ARTIFACT_DIR, "desktop_side_menu_verified.png")
        await page.screenshot(path=p_menu)
        print(f"[Desktop] Saved Side Menu to {p_menu}")
        await page.evaluate("window.epmCloseSideMenu()")
        await page.wait_for_timeout(800)
        await context_desktop.close()
        
        # 2. Mobile Verification (iPhone 14 Pro: 393x852)
        context_mobile = await browser.new_context(
            viewport={"width": 393, "height": 852},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
            ignore_https_errors=True
        )
        mobile_page = await context_mobile.new_page()
        print(f"[Mobile] Navigating to {TARGET_URL}...")
        await mobile_page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        await mobile_page.wait_for_selector("#top_news_table", timeout=45000)
        await mobile_page.add_script_tag(content=TERMINAL_CLIENT_JS)
        await mobile_page.wait_for_timeout(4000)
        
        p_mob_feed = os.path.join(ARTIFACT_DIR, "mobile_feed_verified.png")
        await mobile_page.screenshot(path=p_mob_feed)
        print(f"[Mobile] Saved Mobile Feed to {p_mob_feed}")
        
        # Open Inshorts Drawer on mobile
        print("[Mobile] Opening Inshorts Drawer...")
        await mobile_page.evaluate("""
        window.epmOpenInshortsDrawer({
            title: "Govt proposes rules to allow 85-100% ethanol-blended fuels in vehicles",
            source: "INSHORTS / REUTERS",
            time: "14:30 IST",
            sentiment: "BULLISH",
            score: "AI 9/10",
            impact: "HIGH",
            sectors: ["AUTO", "ENERGY", "COMMODITIES"],
            reasoning: "The government has issued a draft notification proposing amendments to allow higher ethanol-blended fuels (E85 and E100) in vehicles, accelerating green energy transition and expanding domestic refining capacity.",
            url: "https://reuters.com",
            isCalendar: false
        })
        """)
        await mobile_page.wait_for_timeout(1500)
        p_mob_inshorts = os.path.join(ARTIFACT_DIR, "mobile_inshorts_verified.png")
        await mobile_page.screenshot(path=p_mob_inshorts)
        print(f"[Mobile] Saved Mobile Inshorts to {p_mob_inshorts}")
        
        await context_mobile.close()
        await browser.close()
        print("[Playwright] All verifications completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_verification())
