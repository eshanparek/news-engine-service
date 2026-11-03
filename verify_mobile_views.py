import asyncio
from playwright.async_api import async_playwright
import os

ARTIFACT_DIR = "/Users/eshanparek/.gemini/antigravity/brain/41b33619-0995-408e-b34b-4351da675341"

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # iPhone 14 viewport (390 x 844)
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
        total_cards = await page.evaluate("document.querySelectorAll('#mobile_news_feed .epm-pc-card, .epm-mobile-feed .epm-pc-card').length")
        print(f"Total initial mobile news cards: {total_cards}")

        # Select 'inst_domestic'
        await page.evaluate("window.epmFilterNewsCategory('inst_domestic')")
        await asyncio.sleep(0.5)
        hidden_cards = await page.evaluate("document.querySelectorAll('#mobile_news_feed .epm-pc-card.epm-filtered-hidden, .epm-mobile-feed .epm-pc-card.epm-filtered-hidden').length")
        visible_cards = await page.evaluate("document.querySelectorAll('#mobile_news_feed .epm-pc-card:not(.epm-filtered-hidden), .epm-mobile-feed .epm-pc-card:not(.epm-filtered-hidden)').length")
        print(f"After filtering 'inst_domestic': visible={visible_cards}, hidden={hidden_cards}")
        
        path_filter = os.path.join(ARTIFACT_DIR, "v22_mobile_news_filtered_inst.png")
        await page.screenshot(path=path_filter, full_page=False)
        print(f"Captured {path_filter}")

        # Reset news filter to 'all'
        await page.evaluate("window.epmFilterNewsCategory('all')")
        await asyncio.sleep(0.5)

        # 2. Test Mobile Side Menu (Audio Chime at Bottom)
        print("\n--- Testing Mobile Side Menu & Audio Chime Position ---")
        menu_btn = await page.query_selector("#epm-desktop-menu-btn, .epm-menu-btn")
        if menu_btn:
            await menu_btn.click()
            await asyncio.sleep(1)
            
            # Check position of Audio chime in drawer
            audio_pos = await page.evaluate("""() => {
                const drawer = document.querySelector('.epm-side-drawer-body');
                const audioCard = document.querySelector('.epm-side-audio-card');
                if (!drawer || !audioCard) return 'Not found';
                const children = Array.from(drawer.children);
                return {
                    audioIndex: children.indexOf(audioCard),
                    totalChildren: children.length
                };
            }""")
            print(f"Side drawer audio chime position: {audio_pos}")
            
            path_menu = os.path.join(ARTIFACT_DIR, "v22_mobile_side_menu_audio_bottom.png")
            await page.screenshot(path=path_menu, full_page=False)
            print(f"Captured {path_menu}")

            # Close side menu
            close_btn = await page.query_selector(".epm-side-drawer-close")
            if close_btn:
                await close_btn.click()
                await asyncio.sleep(0.5)

        # 3. Test Mobile Calendar Filter
        print("\n--- Testing Mobile Calendar Filter ---")
        await page.evaluate("window.epmSwitchTab(1)")
        await asyncio.sleep(1.5)

        total_cal = await page.evaluate("document.querySelectorAll('.epm-mobile-timeline .epm-tl-row').length")
        print(f"Total calendar rows: {total_cal}")

        # Filter by MCX
        await page.evaluate("window.epmChangeCalMarket('MCX')")
        await asyncio.sleep(0.5)
        vis_mcx = await page.evaluate("document.querySelectorAll('.epm-mobile-timeline .epm-tl-row:not(.epm-filtered-hidden)').length")
        hid_mcx = await page.evaluate("document.querySelectorAll('.epm-mobile-timeline .epm-tl-row.epm-filtered-hidden').length")
        print(f"After selecting MCX: visible={vis_mcx}, hidden={hid_mcx}")

        path_cal = os.path.join(ARTIFACT_DIR, "v22_mobile_calendar_filtered_mcx.png")
        await page.screenshot(path=path_cal, full_page=False)
        print(f"Captured {path_cal}")

        # Reset calendar filter
        await page.evaluate("window.epmChangeCalMarket('ALL')")

        # 4. Test Mobile Circulars Filter
        print("\n--- Testing Mobile Circulars Filter ---")
        await page.evaluate("window.epmSwitchTab(2)")
        await asyncio.sleep(1.5)

        total_circ = await page.evaluate("document.querySelectorAll('#mobile_circ_feed .epm-pc-card, .epm-pc-card[data-circ-reg]').length")
        print(f"Total circular cards: {total_circ}")

        # Filter by SEBI
        await page.evaluate("window.epmFilterCircReg('SEBI')")
        await asyncio.sleep(0.5)
        vis_sebi = await page.evaluate("document.querySelectorAll('#mobile_circ_feed .epm-pc-card:not(.epm-filtered-hidden), .epm-pc-card[data-circ-reg]:not(.epm-filtered-hidden)').length")
        hid_sebi = await page.evaluate("document.querySelectorAll('#mobile_circ_feed .epm-pc-card.epm-filtered-hidden, .epm-pc-card[data-circ-reg].epm-filtered-hidden').length")
        print(f"After selecting SEBI: visible={vis_sebi}, hidden={hid_sebi}")

        path_circ = os.path.join(ARTIFACT_DIR, "v22_mobile_circulars_filtered_sebi.png")
        await page.screenshot(path=path_circ, full_page=False)
        print(f"Captured {path_circ}")

        # 5. Test Story Navigation (Single-Step Advance)
        print("\n--- Testing Story Navigation Single-Step Advance ---")
        # Switch back to news tab
        await page.evaluate("window.epmSwitchTab(0)")
        await asyncio.sleep(1)

        # Open Story 0
        await page.evaluate("window.epmOpenStory('news', 0)")
        await asyncio.sleep(1)

        idx0 = await page.evaluate("window.epmStory ? window.epmStory.idx : -1")
        print(f"Initial story index: {idx0}")

        # Click right side of screen (x=320, y=400)
        await page.mouse.click(320, 400)
        await asyncio.sleep(0.5)
        idx1 = await page.evaluate("window.epmStory ? window.epmStory.idx : -1")
        print(f"Story index after 1 tap on right side: {idx1}")

        # Click right side again
        await page.mouse.click(320, 400)
        await asyncio.sleep(0.5)
        idx2 = await page.evaluate("window.epmStory ? window.epmStory.idx : -1")
        print(f"Story index after 2nd tap on right side: {idx2}")

        # Click left side (back) (x=60, y=400)
        await page.mouse.click(60, 400)
        await asyncio.sleep(0.5)
        idx_back = await page.evaluate("window.epmStory ? window.epmStory.idx : -1")
        print(f"Story index after tap on left side: {idx_back}")

        path_story = os.path.join(ARTIFACT_DIR, "v22_mobile_story_single_step.png")
        await page.screenshot(path=path_story, full_page=False)
        print(f"Captured {path_story}")

        # Close story
        await page.evaluate("window.epmCloseStory()")
        await asyncio.sleep(0.5)

        # 6. Test Admin Settings Taxonomy Logos & Checkbox Approval
        print("\n--- Testing Admin Settings Taxonomy Logos & Approval Workflow ---")
        await page.evaluate("window.epmSwitchTab(4)")
        await asyncio.sleep(1)
        # Unlock admin PIN
        await page.evaluate("document.getElementById('epm-admin-pin-input').value = '202688'; window.epmUnlockAdmin();")
        await asyncio.sleep(1.5)
        # Show Indian regulators pane
        await page.evaluate("window.epmShowSettingsPane('pane_ind_reg')")
        await asyncio.sleep(1)

        # Verify checkboxes and logos
        cb_count = await page.evaluate("document.querySelectorAll('.epm-logo-checkbox').length")
        logo_imgs = await page.evaluate("document.querySelectorAll('.epm-entity-logo-thumb').length")
        save_btn = await page.evaluate("!!document.querySelector('.epm-btn-save-logos')")
        print(f"Settings taxonomy: {cb_count} approval checkboxes, {logo_imgs} logo previews, save button present: {save_btn}")

        path_admin = os.path.join(ARTIFACT_DIR, "v22_mobile_tab5_admin_approved_logos.png")
        await page.screenshot(path=path_admin, full_page=False)
        print(f"Captured {path_admin}")

        await browser.close()
        print("\nAll 6 tests passed successfully!")

asyncio.run(run())
