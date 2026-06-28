#!/usr/bin/env python3
"""
Playwright-based Device Type and Sub Category scanner.

Uses real Chromium browser to handle ASP.NET UpdatePanel correctly.
Global scan approach:
  - For each DT (9): check globally → paginate through ALL results → uncheck
  - For each SC (30): same approach
  - No company filter → no "empty results broken session" issue

Uses expect_response to reliably wait for AJAX POST to complete.
Total: ~39 filter tests, handles pagination automatically.
"""

import json
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_URL = "https://threadgroup.org/Certified-Products"
PRODUCTS_FILE = "/Users/yoyolin/project/Thread/data/products.json"

DEVICE_TYPES = [
    (0, "Automation control"), (1, "Chipset"), (2, "HVAC"),
    (3, "Infrastructure"), (4, "Lighting"), (5, "Module"),
    (6, "Safety"), (7, "Sensor"), (8, "Window covering"),
]

SUB_CATEGORIES = [
    (0, "Agricultural"), (1, "Air"), (2, "Air conditioning"),
    (3, "Blind"), (4, "Bulb"), (5, "Contact"),
    (6, "Curtain"), (7, "Door lock"), (8, "Gas alarm"),
    (9, "Gateway"), (10, "Heating"), (11, "Hub"),
    (12, "Irrigation"), (13, "Light"), (14, "Lighting"),
    (15, "Lightstrip"), (16, "Media streamer"), (17, "Presence"),
    (18, "Pump"), (19, "Shutter"), (20, "Smart display"),
    (21, "Smart plug"), (22, "Smart speaker"), (23, "Smoke alarm"),
    (24, "Switch"), (25, "Temperature"), (26, "Water"),
    (27, "Weather"), (28, "Wi-Fi Access Point"), (29, "Window lock"),
]

def _is_ajax_response(r):
    return 'Certified-Products' in r.url and r.request.method == 'POST'


def dismiss_cookie_popup(page):
    """Dismiss the cookie consent popup if present."""
    try:
        btn = page.query_selector('text=AGREE & DISMISS')
        if btn:
            btn.click()
            page.wait_for_timeout(500)
            print("  Cookie popup dismissed.")
    except Exception:
        pass


def extract_products_from_page(page):
    """Extract product names from prod-sec2 divs.
    Uses eval_on_selector_all for atomic DOM access (avoids stale ElementHandle after AJAX).
    """
    try:
        names = page.eval_on_selector_all(
            'div[id="prod-sec2"] h1',
            'els => els.map(e => e.textContent.trim()).filter(t => t.length > 0)'
        )
        return names
    except Exception:
        return []


def click_and_wait(page, action_fn, timeout=15000):
    """Perform an action, wait for the AJAX POST response, then wait for DOM update.

    Key fix: use expect_response so we NEVER read the DOM before the AJAX completes.
    wait_for_load_state('networkidle') would return immediately if page is already idle
    (before the click-triggered AJAX starts), causing stale reads.
    """
    try:
        with page.expect_response(_is_ajax_response, timeout=timeout) as resp_info:
            action_fn()
        # Wait for JavaScript to process the AJAX delta and update the DOM
        page.wait_for_timeout(700)
    except Exception:
        # If no AJAX triggered (e.g., no matching response), just wait
        page.wait_for_timeout(1500)


def get_all_filtered_products(page):
    """Collect ALL products across all pages for the current filter state."""
    all_names = set()
    page_num = 1
    MAX_PAGES = 30  # Safety limit

    while page_num <= MAX_PAGES:
        names = extract_products_from_page(page)
        if not names:
            break
        prev_count = len(all_names)
        all_names.update(names)

        # KEY FIX: if no new products were added, the ❯ click didn't navigate
        # (disabled link = last page, or filter was cleared). Stop immediately.
        if len(all_names) == prev_count:
            break

        # Find the ❯ (next page) anchor link in the pager.
        # The site uses Unicode ❯ (U+276F), NOT ASCII '>'
        next_link = None
        try:
            anchors = page.query_selector_all('a')
            for a in anchors:
                txt = a.text_content().strip()
                # ❯ = U+276F HEAVY RIGHT-POINTING ANGLE QUOTATION MARK
                if txt in ['❯', '>', '›', '»'] and a.is_visible():
                    next_link = a
                    break
        except Exception:
            pass

        if next_link:
            click_and_wait(page, lambda: next_link.click())
            page_num += 1
        else:
            break

    return all_names


def set_page_size(page, size=20):
    """Set the page size dropdown to the largest available value."""
    try:
        select = page.query_selector('select[name*="ddlPageSize"]')
        if select:
            options = select.query_selector_all('option')
            vals = [o.get_attribute('value') for o in options]
            print(f"  Page size options: {vals}")
            valid = [int(v) for v in vals if v and v.isdigit()]
            if valid:
                best = max(v for v in valid if v <= size)
                click_and_wait(page, lambda: select.select_option(str(best)))
                print(f"  Page size set to: {best}")
                return best
    except Exception as e:
        print(f"  Page size unchanged: {e}")
    return 8


def scan_filter(page, checkbox_name_pattern, label):
    """Apply a filter checkbox, collect ALL products across all pages, then uncheck."""
    try:
        cb = page.query_selector(f'input[name*="{checkbox_name_pattern}"]')
        if not cb:
            print(f"  [{label}] Checkbox not found!")
            return set()

        # CHECK the checkbox — wait for AJAX POST to complete
        click_and_wait(page, lambda: cb.click())

        # Collect all products across pages
        products = get_all_filtered_products(page)

        # UNCHECK: re-query (DOM was replaced by AJAX) then click again
        cb2 = page.query_selector(f'input[name*="{checkbox_name_pattern}"]')
        if cb2:
            click_and_wait(page, lambda: cb2.click())

        return products

    except Exception as e:
        print(f"  [{label}] Error: {e}")
        return set()


def run_phase(pw, phase_filters, phase_name, data_map, use_list=False):
    """Open a fresh browser session for one scanning phase (DT or SC)."""
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    )
    page = context.new_page()

    print(f"  Opening {BASE_URL}...")
    page.goto(BASE_URL, wait_until='networkidle', timeout=30000)
    page.wait_for_timeout(2000)
    dismiss_cookie_popup(page)
    set_page_size(page, 20)

    total = len(phase_filters)
    for idx, (filter_idx, filter_name) in enumerate(phase_filters):
        if 'Device' in phase_name:
            pattern = f'chkDeviceType${filter_idx}'
        else:
            pattern = f'chkSubCategory${filter_idx}'

        print(f"  [{idx+1}/{total}] {filter_name}...", end='', flush=True)
        prods = scan_filter(page, pattern, filter_name)
        print(f" {len(prods)} products")

        for pname in prods:
            if use_list:
                if pname not in data_map:
                    data_map[pname] = []
                if filter_name not in data_map[pname]:
                    data_map[pname].append(filter_name)
            else:
                # LAST-WINS: more specific/later DTs override earlier broad ones
                data_map[pname] = filter_name

    browser.close()
    return data_map


def main():
    # Load existing data
    with open(PRODUCTS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    products = data['products']
    print(f"Loaded {len(products)} products from {len(set(p['company'] for p in products))} companies")

    dt_map = {}   # product_name → device_type (last-wins)
    sc_map = {}   # product_name → [sub_categories]

    with sync_playwright() as pw:
        # ============================================================
        # Phase 1: Device Type scan (fresh browser session)
        # ============================================================
        print("\n=== Scanning Device Types (fresh browser) ===")
        run_phase(pw, DEVICE_TYPES, 'Device Type', dt_map, use_list=False)

        # ============================================================
        # Phase 2: Sub Category scan (separate fresh browser session)
        # ============================================================
        print("\n=== Scanning Sub Categories (fresh browser) ===")
        run_phase(pw, SUB_CATEGORIES, 'Sub Category', sc_map, use_list=True)

    # ============================================================
    # Update products.json
    # ============================================================
    print("\n=== Updating products.json ===")
    mapped_dt = 0
    mapped_sc = 0

    for p in products:
        name = p['product_name']
        dt = dt_map.get(name, '-')
        if dt != '-':
            p['device_type'] = dt
            mapped_dt += 1
        else:
            p['device_type'] = '-'
        sc = sc_map.get(name, [])
        if sc:
            p['sub_category'] = ', '.join(sc)
            mapped_sc += 1
        else:
            p['sub_category'] = '-'

    data['products'] = products
    data['last_updated'] = datetime.now().isoformat()

    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done!")
    print(f"  Device type mapped:   {mapped_dt}/{len(products)}")
    print(f"  Sub category mapped:  {mapped_sc}/{len(products)}")
    print(f"  Unique DT names:  {set(dt_map.values())}")

    unmapped = [p for p in products if p['device_type'] == '-']
    print(f"\n  Unmapped (device_type='-'): {len(unmapped)}")
    for p in unmapped[:5]:
        print(f"    {p['company'][:30]:30s} | {p['product_name'][:35]:35s}")


if __name__ == '__main__':
    main()
