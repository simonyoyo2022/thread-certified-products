#!/usr/bin/env python3
"""
Phase 2+3 Fix: Company-specific Device Type and Sub Category scan.

Strategy:
  For each company (already in products.json):
    1. Filter by company → confirm products
    2. For each Device Type (9): filter company+DT → get intersection
    3. For each Sub Category (30): filter company+SC → get intersection
    4. Map product_name → device_type, sub_categories
  
  Updates products.json in place.
  
  Total requests: 128 companies × (1 + 9 + 30) = ~5120 requests (~25 min)
"""

import urllib.request
import urllib.parse
import re
import json
import http.cookiejar
import time
import os
import sys

BASE_URL = "https://threadgroup.org/Certified-Products"
PRODUCTS_FILE = "/Users/yoyolin/project/Thread/data/products.json"

# Device types from HTML (index → name)
DEVICE_TYPES = [
    (0, "Automation control"),
    (1, "Chipset"),
    (2, "HVAC"),
    (3, "Infrastructure"),
    (4, "Lighting"),
    (5, "Module"),
    (6, "Safety"),
    (7, "Sensor"),
    (8, "Window covering"),
]

# Sub categories from HTML (all 30)
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


def create_session():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [
        ('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'),
        ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
    ]
    return opener


def extract_viewstate(html):
    vs  = re.search(r'id="__VIEWSTATE"[^>]*value="([^"]*)"', html)
    vsg = re.search(r'id="__VIEWSTATEGENERATOR"[^>]*value="([^"]*)"', html)
    ev  = re.search(r'id="__EVENTVALIDATION"[^>]*value="([^"]*)"', html)
    return {
        '__VIEWSTATE':          vs.group(1)  if vs  else '',
        '__VIEWSTATEGENERATOR': vsg.group(1) if vsg else 'CA0B0334',
        '__EVENTVALIDATION':    ev.group(1)  if ev  else '',
    }


def update_vs(vs, ajax_html):
    for field in ['__VIEWSTATE', '__EVENTVALIDATION', '__VIEWSTATEGENERATOR']:
        m = re.search(rf'\d+\|hiddenField\|{re.escape(field)}\|([^|]+)', ajax_html)
        if m:
            vs[field] = m.group(1)


def extract_product_names(html):
    """Extract product names from HTML (just names, no logo needed)."""
    tag_re = re.compile(r'<[^>]+>')
    names = []
    parts = re.split(r'<div id="prod-sec1">', html)
    for part in parts[1:]:
        h1_m = re.search(r'<h1[^>]*>(.*?)</h1>', part, re.DOTALL)
        if not h1_m:
            continue
        name = tag_re.sub('', h1_m.group(1)).strip()
        if name and name.lower() != 'filters':
            names.append(name)
    return names


def ajax_post(opener, vs, event_target, extra=None, retries=3):
    post = {
        '__EVENTTARGET': event_target,
        '__EVENTARGUMENT': '',
        '__LASTFOCUS': '',
        '__VIEWSTATE': vs['__VIEWSTATE'],
        '__VIEWSTATEGENERATOR': vs['__VIEWSTATEGENERATOR'],
        '__VIEWSTATEENCRYPTED': '',
        '__EVENTVALIDATION': vs['__EVENTVALIDATION'],
        'ScriptManager': f'dnn$ctr1641$Default$ctl00$UpdatePanel1|{event_target}',
        '__ASYNCPOST': 'true',
        'dnn$ctr1641$Default$ctl00$ddlPageSize': '20',
    }
    if extra:
        post.update(extra)

    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE_URL,
                                         data=urllib.parse.urlencode(post).encode('utf-8'))
            req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8')
            req.add_header('X-MicrosoftAjax', 'Delta=true')
            req.add_header('X-Requested-With', 'XMLHttpRequest')
            req.add_header('Referer', BASE_URL)
            req.add_header('Origin', 'https://threadgroup.org')
            with opener.open(req, timeout=30) as resp:
                html = resp.read().decode('utf-8', errors='replace')
            update_vs(vs, html)
            return html
        except Exception as e:
            if attempt < retries - 1:
                print(f"    Retry {attempt+1}/{retries}: {e}")
                time.sleep(2 ** attempt)
            else:
                print(f"    Failed after {retries} attempts: {e}")
                return ''


def get_company_index_map(html):
    """Get mapping from company_name → (index, value) from initial page."""
    pattern = re.compile(
        r'<input[^>]*name="dnn\$ctr1641\$Default\$ctl00\$chkCompanyName\$(\d+)"'
        r'[^>]*value="(\d+)"[^>]*/>'
        r'<label[^>]*>([^<]+)</label>',
        re.IGNORECASE
    )
    mapping = {}
    for m in pattern.finditer(html):
        name = re.sub(r'&amp;', '&', m.group(3).strip())
        mapping[name] = (int(m.group(1)), int(m.group(2)))
    return mapping


def scan_company(opener, vs, co_name, co_index, co_value, known_products):
    """
    For one company: scan all 9 DTs and 30 SCs to determine per-product types.
    Returns: dict {product_name: {device_type: str, sub_categories: list}}
    """
    result = {pname: {'device_type': '-', 'sub_categories': []} for pname in known_products}
    company_filter = {f'dnn$ctr1641$Default$ctl00$chkCompanyName${co_index}': str(co_value)}

    # Step 1: Apply company filter
    html = ajax_post(opener, vs,
                     f'dnn$ctr1641$Default$ctl00$chkCompanyName${co_index}',
                     company_filter)
    if not html:
        return result
    co_products = set(extract_product_names(html))
    if not co_products:
        # Uncheck and return
        ajax_post(opener, vs, f'dnn$ctr1641$Default$ctl00$chkCompanyName${co_index}')
        return result

    # Step 2: For each Device Type, check intersection
    for dt_idx, dt_name in DEVICE_TYPES:
        data = company_filter.copy()
        data[f'dnn$ctr1641$Default$ctl00$chkDeviceType${dt_idx}'] = str(dt_idx + 1)
        html = ajax_post(opener, vs, f'dnn$ctr1641$Default$ctl00$chkDeviceType${dt_idx}', data)
        if html:
            dt_products = set(extract_product_names(html))
            # Intersection with company products
            for pname in dt_products & co_products:
                if pname in result:
                    result[pname]['device_type'] = dt_name
        # Uncheck device type
        ajax_post(opener, vs, f'dnn$ctr1641$Default$ctl00$chkDeviceType${dt_idx}', company_filter)
        time.sleep(0.2)

    # Step 3: For each Sub Category, check intersection
    for sc_idx, sc_name in SUB_CATEGORIES:
        data = company_filter.copy()
        data[f'dnn$ctr1641$Default$ctl00$chkSubCategory${sc_idx}'] = str(sc_idx + 1)
        html = ajax_post(opener, vs, f'dnn$ctr1641$Default$ctl00$chkSubCategory${sc_idx}', data)
        if html:
            sc_products = set(extract_product_names(html))
            for pname in sc_products & co_products:
                if pname in result and sc_name not in result[pname]['sub_categories']:
                    result[pname]['sub_categories'].append(sc_name)
        # Uncheck sub category
        ajax_post(opener, vs, f'dnn$ctr1641$Default$ctl00$chkSubCategory${sc_idx}', company_filter)
        time.sleep(0.2)

    # Step 4: Uncheck company
    ajax_post(opener, vs, f'dnn$ctr1641$Default$ctl00$chkCompanyName${co_index}')
    time.sleep(0.3)

    return result


def main():
    # Load existing products
    print("Loading products.json...")
    with open(PRODUCTS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    products = data['products']

    # Build company → product_names mapping
    from collections import defaultdict
    company_products = defaultdict(list)
    for p in products:
        company_products[p['company']].append(p['product_name'])

    companies = sorted(company_products.keys())
    print(f"Companies to scan: {len(companies)}")
    print(f"Total products: {len(products)}")

    # Init fresh session
    print("\nInitializing session...")
    opener = create_session()
    req = urllib.request.Request(BASE_URL)
    req.add_header('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')
    with opener.open(req, timeout=30) as resp:
        html = resp.read().decode('utf-8', errors='replace')
    vs = extract_viewstate(html)
    co_index_map = get_company_index_map(html)
    print(f"Session ready. Companies in filter: {len(co_index_map)}")

    # product_map[company][product_name] = {device_type, sub_categories}
    product_map = {}

    total = len(companies)
    for i, co_name in enumerate(companies):
        print(f"\n[{i+1}/{total}] {co_name} ({len(company_products[co_name])} products)")

        if co_name not in co_index_map:
            print(f"  WARNING: Company not found in filter panel. Skipping.")
            product_map[co_name] = {
                pname: {'device_type': '-', 'sub_categories': []}
                for pname in company_products[co_name]
            }
            continue

        co_index, co_value = co_index_map[co_name]
        known = set(company_products[co_name])

        result = scan_company(opener, vs, co_name, co_index, co_value, known)
        product_map[co_name] = result

        # Show what we found
        dt_found  = sum(1 for r in result.values() if r['device_type'] != '-')
        sc_found  = sum(1 for r in result.values() if r['sub_categories'])
        print(f"  → DT mapped: {dt_found}/{len(known)} | SC mapped: {sc_found}/{len(known)}")

        # Save progress every 10 companies
        if (i + 1) % 10 == 0 or (i + 1) == total:
            _save_progress(products, product_map, data)

    # Final save
    _save_progress(products, product_map, data)
    print("\n✅ Done!")


def _save_progress(products, product_map, data):
    for p in products:
        co = p['company']
        name = p['product_name']
        if co in product_map and name in product_map[co]:
            r = product_map[co][name]
            p['device_type'] = r['device_type']
            sc = r['sub_categories']
            p['sub_category'] = ', '.join(sc) if sc else '-'

    data['products'] = products
    data['last_updated'] = __import__('datetime').datetime.now().isoformat()

    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [Saved] {PRODUCTS_FILE}")


if __name__ == '__main__':
    main()
