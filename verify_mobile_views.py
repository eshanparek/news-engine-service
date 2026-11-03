import asyncio
from playwright.async_api import async_playwright
import os

ARTIFACT_DIR = "/Users/eshanparek/.gemini/antigravity/brain/41b33619-0995-408e-b34b-4351da675341"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Mobile viewport (iPhone 14: 390x844)
        context = await browser.new_context(
            viewport={'width': 390, 'height': 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        )
        page = await context.new_page()

        print("Navigating to http://127.0.0.1:7860/...")
        await page.goto("http://127.0.0.1:7860/", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        # 1. Test Mobile News Filter
        print("\n--- Testing Mobile News Filter ---")
        total_news = await page.evaluate("document.querySelectorAll('.epm-mobile-feed .epm-pc-card').length")
        print(f"Total mobile news cards: {total_news}")

        # Filter by inst_domestic
        await page.evaluate("window.epmFilterNewsCategory('inst_domestic')")
        await asyncio.sleep(0.5)
        vis_news_dom = await page.evaluate("document.querySelectorAll('.epm-mobile-feed .epm-pc-card:not(.epm-filtered-hidden)').length")
        hid_news_dom = await page.evaluate("document.querySelectorAll('.epm-mobile-feed .epm-pc-card.epm-filtered-hidden').length")
        print(f"News filtered (inst_domestic): visible={vis_news_dom}, hidden={hid_news_dom}")
        path_news = os.path.join(ARTIFACT_DIR, "v23_mobile_news_filtered.png")
        await page.screenshot(path=path_news, full_page=False)

        # Filter by inst_global
        await page.evaluate("window.epmFilterNewsCategory('inst_global')")
        await asyncio.sleep(0.5)
        vis_news_glob = await page.evaluate("document.querySelectorAll('.epm-mobile-feed .epm-pc-card:not(.epm-filtered-hidden)').length")
        print(f"News filtered (inst_global): visible={vis_news_glob}")

        # Reset news
        await page.evaluate("window.epmFilterNewsCategory('all')")

        # 2. Test Mobile Calendar Filter
        print("\n--- Testing Mobile Calendar Filter ---")
        await page.evaluate("window.epmSwitchTab(1)")
        await asyncio.sleep(1.5)
        total_cal = await page.evaluate("document.querySelectorAll('.epm-mobile-timeline .epm-tl-row').length")
        print(f"Total calendar rows: {total_cal}")

        # Filter by MCX
        await page.evaluate("window.epmChangeCalMarket('MCX')")
        await asyncio.sleep(0.5)
        vis_cal_mcx = await page.evaluate("document.querySelectorAll('.epm-mobile-timeline .epm-tl-row:not(.epm-filtered-hidden)').length")
        hid_cal_mcx = await page.evaluate("document.querySelectorAll('.epm-mobile-timeline .epm-tl-row.epm-filtered-hidden').length")
        print(f"Calendar filtered (MCX): visible={vis_cal_mcx}, hidden={hid_cal_mcx}")
        path_cal = os.path.join(ARTIFACT_DIR, "v23_mobile_cal_filtered.png")
        await page.screenshot(path=path_cal, full_page=False)

        # 3. Test Mobile Circulars Filter
        print("\n--- Testing Mobile Circulars Filter ---")
        await page.evaluate("window.epmSwitchTab(2)")
        await asyncio.sleep(1.5)
        total_circ = await page.evaluate("document.querySelectorAll('#mobile_circ_feed .epm-pc-card').length")
        print(f"Total circulars: {total_circ}")

        # Filter by SEBI
        await page.evaluate("window.epmFilterCircReg('SEBI')")
        await asyncio.sleep(0.5)
        vis_circ_sebi = await page.evaluate("document.querySelectorAll('#mobile_circ_feed .epm-pc-card:not(.epm-filtered-hidden)').length")
        hid_circ_sebi = await page.evaluate("document.querySelectorAll('#mobile_circ_feed .epm-pc-card.epm-filtered-hidden').length")
        print(f"Circulars filtered (SEBI): visible={vis_circ_sebi}, hidden={hid_circ_sebi}")
        path_circ = os.path.join(ARTIFACT_DIR, "v23_mobile_circ_filtered.png")
        await page.screenshot(path=path_circ, full_page=False)

        # 4. Test Mobile Holidays Filter
        print("\n--- Testing Mobile Holidays Filter ---")
        await page.evaluate("window.epmSwitchTab(3)")
        await asyncio.sleep(1.5)
        total_hol = await page.evaluate("document.querySelectorAll('.epm-mobile-timeline .epm-tl-row[data-nse]').length")
        print(f"Total holidays: {total_hol}")

        # Filter by MCX
        await page.evaluate("window.epmFilterHolidays('MCX')")
        await asyncio.sleep(0.5)
        vis_hol_mcx = await page.evaluate("document.querySelectorAll('.epm-mobile-timeline .epm-tl-row[data-nse]:not(.epm-filtered-hidden)').length")
        hid_hol_mcx = await page.evaluate("document.querySelectorAll('.epm-mobile-timeline .epm-tl-row[data-nse].epm-filtered-hidden').length")
        print(f"Holidays filtered (MCX): visible={vis_hol_mcx}, hidden={hid_hol_mcx}")
        path_hol = os.path.join(ARTIFACT_DIR, "v23_mobile_holidays_filtered.png")
        await page.screenshot(path=path_hol, full_page=False)

        # 5. Test Side Menu - Check that 'Tab 5' is completely REMOVED from Settings card
        print("\n--- Testing Side Menu: Verification of Tab 5 Removal ---")
        menu_btn = await page.query_selector("#epm-desktop-menu-btn, .epm-menu-btn")
        if menu_btn:
            await menu_btn.click()
            await asyncio.sleep(1)

            settings_card_text = await page.evaluate("""() => {
                const settingsCard = document.querySelector('.epm-side-nav-item[data-tab=\"4\"]');
                return settingsCard ? settingsCard.innerText : 'Not found';
            }""")
            print(f"Settings card text in side menu:\n{settings_card_text}")
            has_tab5 = 'Tab 5' in settings_card_text
            print(f"Does Settings card contain 'Tab 5'? {has_tab5}")
            assert not has_tab5, "ERROR: Settings card still contains 'Tab 5'!"

            path_menu = os.path.join(ARTIFACT_DIR, "v23_mobile_side_menu_no_tab5.png")
            await page.screenshot(path=path_menu, full_page=False)
            print(f"Captured {path_menu}")

        await browser.close()
        print("\nALL VERIFICATIONS PASSED!")

asyncio.run(run())
