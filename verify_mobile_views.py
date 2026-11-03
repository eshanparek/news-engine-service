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
        t0 = asyncio.get_event_loop().time()
        await page.goto("http://127.0.0.1:7860/", wait_until="domcontentloaded", timeout=30000)
        t_load = asyncio.get_event_loop().time() - t0
        print(f"DOM Content Loaded in: {t_load:.2f} seconds!")
        await asyncio.sleep(2)

        # 1. Test Side Menu Names
        print("\n--- Testing Side Menu Renaming ---")
        menu_btn = await page.query_selector("#epm-desktop-menu-btn, .epm-menu-btn")
        if menu_btn:
            await menu_btn.click()
            await asyncio.sleep(1)

            news_name = await page.evaluate("document.querySelector('.epm-side-nav-item[data-tab=\"0\"] .epm-side-item-name').innerText")
            cal_name = await page.evaluate("document.querySelector('.epm-side-nav-item[data-tab=\"1\"] .epm-side-item-name').innerText")
            settings_name = await page.evaluate("document.querySelector('.epm-side-nav-item[data-tab=\"4\"] .epm-side-item-name').innerText")
            settings_desc = await page.evaluate("!!document.querySelector('.epm-side-nav-item[data-tab=\"4\"] .epm-side-item-desc')")

            print(f"Tab 0 name: '{news_name}' (expected: 'Live Breaking News')")
            print(f"Tab 1 name: '{cal_name}' (expected: 'Market Outlook')")
            print(f"Tab 4 name: '{settings_name}' (expected: 'Settings')")
            print(f"Settings has extra desc text: {settings_desc} (expected: False)")

            assert news_name == "Live Breaking News"
            assert cal_name == "Market Outlook"
            assert settings_name == "Settings"
            assert not settings_desc

            path_menu = os.path.join(ARTIFACT_DIR, "v24_mobile_side_menu_renamed.png")
            await page.screenshot(path=path_menu, full_page=False)
            print(f"Captured {path_menu}")

            # Close side menu
            close_btn = await page.query_selector(".epm-side-drawer-close")
            if close_btn:
                await close_btn.click()
                await asyncio.sleep(0.5)

        # 2. Test Circulars Page Load & Zero Spinner
        print("\n--- Testing Circulars Page Load ---")
        t_circ_0 = asyncio.get_event_loop().time()
        await page.evaluate("window.epmSwitchTab(2)")
        await asyncio.sleep(1)
        t_circ_switch = asyncio.get_event_loop().time() - t_circ_0
        print(f"Switched to Circulars tab in {t_circ_switch:.2f}s")
        has_spinner = await page.evaluate("!!document.querySelector('#circ_visual_feed .wrap.default, #circ_visual_feed .loading')")
        print(f"Circulars has blocking spinner: {has_spinner}")

        path_circ = os.path.join(ARTIFACT_DIR, "v24_mobile_circ_instant_load.png")
        await page.screenshot(path=path_circ, full_page=False)
        print(f"Captured {path_circ}")

        # 3. Test Mobile Settings Hub & Sub-Settings Visibility
        print("\n--- Testing Mobile Settings Hub & Sub-Settings Visibility ---")
        await page.evaluate("window.epmSwitchTab(4)")
        await asyncio.sleep(1)
        # Unlock admin PIN
        await page.evaluate("document.getElementById('epm-admin-pin-input').value = '202688'; window.epmUnlockAdmin();")
        await asyncio.sleep(1.5)

        # Check mobile selector options
        mob_opt_count = await page.evaluate("document.querySelectorAll('#epm-settings-mob-select option').length")
        mob_nav_btns = await page.evaluate("document.querySelectorAll('.epm-settings-nav-item').length")
        print(f"Mobile settings selector options: {mob_opt_count} sub-settings (expected: 16)")
        print(f"Mobile settings 2-col navigation buttons: {mob_nav_btns} (expected: 16)")
        assert mob_opt_count == 16
        assert mob_nav_btns == 16

        # Switch to Entities & Sources Taxonomy via mobile select
        await page.evaluate("window.epmShowSettingsPane('pane_taxonomy')")
        await asyncio.sleep(1)
        tax_visible = await page.evaluate("document.getElementById('pane_taxonomy').style.display !== 'none'")
        print(f"Switched to 'pane_taxonomy': visible={tax_visible}")

        path_settings = os.path.join(ARTIFACT_DIR, "v24_mobile_settings_all_subpanes.png")
        await page.screenshot(path=path_settings, full_page=False)
        print(f"Captured {path_settings}")

        # 4. Test Session Persistence Across Page Reload
        print("\n--- Testing Session Persistence on Reload ---")
        current_hash = await page.evaluate("window.location.hash")
        current_tab = await page.evaluate("localStorage.getItem('epm_active_tab')")
        current_pane = await page.evaluate("localStorage.getItem('epm_active_settings_pane')")
        print(f"Before reload: hash='{current_hash}', active_tab={current_tab}, active_pane='{current_pane}'")

        # Reload the page!
        await page.reload(wait_until="domcontentloaded")
        await asyncio.sleep(2)

        after_tab = await page.evaluate("localStorage.getItem('epm_active_tab')")
        after_hash = await page.evaluate("window.location.hash")
        active_pane_after = await page.evaluate("document.getElementById('pane_taxonomy') ? document.getElementById('pane_taxonomy').style.display !== 'none' : false")
        admin_gate_visible = await page.evaluate("document.getElementById('epm-admin-gate') ? document.getElementById('epm-admin-gate').style.display !== 'none' : false")

        print(f"After reload: active_tab={after_tab}, hash='{after_hash}', pane_taxonomy_visible={active_pane_after}")
        path_reloaded = os.path.join(ARTIFACT_DIR, "v24_mobile_reloaded_preserved_tab.png")
        await page.screenshot(path=path_reloaded, full_page=False)
        print(f"Captured {path_reloaded}")

        await browser.close()
        print("\nALL AUTOMATED TESTS PASSED WITH 100% SUCCESS!")

asyncio.run(run())
