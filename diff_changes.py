#!/usr/bin/env python3
"""
diff_changes.py — Compare new vs previous products.json and save changes.json.

Called after each full scrape to detect:
  - New companies
  - New products
  - Removed products / companies
  - Products whose device_type / sub_category changed

Saves result to data/changes.json and also marks is_new / company_is_new
flags inside products.json for the dashboard to highlight.
"""

import json
import os
from datetime import datetime

_BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_FILE  = os.path.join(_BASE_DIR, "data", "products.json")
PREVIOUS_FILE  = os.path.join(_BASE_DIR, "data", "products_previous.json")
CHANGES_FILE   = os.path.join(_BASE_DIR, "data", "changes.json")


def compute_diff():
    """Load current + previous data, compute diff, save changes.json."""

    # ── Load current data ──────────────────────────────────────
    with open(PRODUCTS_FILE, encoding='utf-8') as f:
        new_data = json.load(f)

    new_products  = {p['product_name']: p for p in new_data['products']}
    new_companies = set(p['company'] for p in new_data['products'])
    current_date  = new_data.get('last_updated', datetime.now().isoformat())

    # ── Load previous data (if exists) ────────────────────────
    if not os.path.exists(PREVIOUS_FILE):
        print("ℹ️  No previous snapshot found — treating this as the baseline.")
        changes = {
            'generated_at':       datetime.now().isoformat(),
            'previous_date':      None,
            'is_first_run':       True,
            'new_companies':      [],
            'removed_companies':  [],
            'new_products':       [],
            'removed_products':   [],
            'changed_products':   [],
            'stats': {
                'total_products_new':       len(new_products),
                'total_products_old':       0,
                'total_companies_new':      len(new_companies),
                'total_companies_old':      0,
                'new_products_count':       0,
                'removed_products_count':   0,
                'new_companies_count':      0,
                'removed_companies_count':  0,
                'changed_products_count':   0,
            }
        }
        _write_changes(changes, new_data, set(), set())
        return changes

    with open(PREVIOUS_FILE, encoding='utf-8') as f:
        old_data = json.load(f)

    old_products  = {p['product_name']: p for p in old_data['products']}
    old_companies = set(p['company'] for p in old_data['products'])
    prev_date     = old_data.get('last_updated')

    # ── New / removed companies ────────────────────────────────
    added_companies   = sorted(new_companies - old_companies)
    removed_companies = sorted(old_companies - new_companies)

    # ── New / removed products ────────────────────────────────
    added_products = []
    for name, p in new_products.items():
        if name not in old_products:
            added_products.append({
                'company':      p['company'],
                'product_name': name,
                'device_type':  p.get('device_type', '-'),
                'sub_category': p.get('sub_category', '-'),
                'product_type': p.get('product_type', '-'),
            })
    added_products.sort(key=lambda x: (x['company'], x['product_name']))

    removed_products = []
    for name, p in old_products.items():
        if name not in new_products:
            removed_products.append({
                'company':      p['company'],
                'product_name': name,
            })
    removed_products.sort(key=lambda x: (x['company'], x['product_name']))

    # ── Changed products ───────────────────────────────────────
    changed_products = []
    watch_fields = ['device_type', 'sub_category', 'product_type']
    for name in set(new_products) & set(old_products):
        np, op = new_products[name], old_products[name]
        diffs = []
        for field in watch_fields:
            old_val = op.get(field, '-') or '-'
            new_val = np.get(field, '-') or '-'
            if old_val != new_val:
                diffs.append({'field': field, 'old': old_val, 'new': new_val})
        if diffs:
            changed_products.append({
                'company':      np['company'],
                'product_name': name,
                'changes':      diffs,
            })
    changed_products.sort(key=lambda x: (x['company'], x['product_name']))

    changes = {
        'generated_at':       datetime.now().isoformat(),
        'previous_date':      prev_date,
        'is_first_run':       False,
        'new_companies':      added_companies,
        'removed_companies':  removed_companies,
        'new_products':       added_products,
        'removed_products':   removed_products,
        'changed_products':   changed_products,
        'stats': {
            'total_products_new':      len(new_products),
            'total_products_old':      len(old_products),
            'total_companies_new':     len(new_companies),
            'total_companies_old':     len(old_companies),
            'new_products_count':      len(added_products),
            'removed_products_count':  len(removed_products),
            'new_companies_count':     len(added_companies),
            'removed_companies_count': len(removed_companies),
            'changed_products_count':  len(changed_products),
        }
    }

    new_product_names  = {p['product_name'] for p in added_products}
    new_company_names  = set(added_companies)
    _write_changes(changes, new_data, new_product_names, new_company_names)
    return changes


def _write_changes(changes, new_data, new_product_names, new_company_names):
    """Mark is_new / company_is_new in products.json and save changes.json."""
    for p in new_data['products']:
        p['is_new']         = p['product_name'] in new_product_names
        p['company_is_new'] = p['company'] in new_company_names

    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=2)

    with open(CHANGES_FILE, 'w', encoding='utf-8') as f:
        json.dump(changes, f, ensure_ascii=False, indent=2)

    # ── Print summary ──────────────────────────────────────────
    s = changes['stats']
    print("\n" + "="*55)
    print("📊 CHANGE SUMMARY")
    print("="*55)
    print(f"  Products : {s.get('total_products_old',0):4d} → {s['total_products_new']:4d}  "
          f"(+{s['new_products_count']} / -{s['removed_products_count']})")
    print(f"  Companies: {s.get('total_companies_old',0):4d} → {s['total_companies_new']:4d}  "
          f"(+{s['new_companies_count']} / -{s['removed_companies_count']})")
    print(f"  Changed  : {s['changed_products_count']} products updated")

    if changes['new_companies']:
        print(f"\n🆕 New companies ({len(changes['new_companies'])}):")
        for c in changes['new_companies']:
            print(f"     • {c}")

    if changes['removed_companies']:
        print(f"\n➖ Removed companies ({len(changes['removed_companies'])}):")
        for c in changes['removed_companies']:
            print(f"     • {c}")

    if changes['new_products']:
        print(f"\n🆕 New products ({len(changes['new_products'])}):")
        for p in changes['new_products'][:15]:
            print(f"     • [{p['company']}]  {p['product_name']}")
        if len(changes['new_products']) > 15:
            print(f"     ... and {len(changes['new_products'])-15} more")

    if changes['removed_products']:
        print(f"\n➖ Removed products ({len(changes['removed_products'])}):")
        for p in changes['removed_products'][:10]:
            print(f"     • [{p['company']}]  {p['product_name']}")

    if changes['changed_products']:
        print(f"\n🔄 Changed products ({len(changes['changed_products'])}):")
        for p in changes['changed_products'][:10]:
            for d in p['changes']:
                print(f"     • [{p['company']}] {p['product_name']}")
                print(f"       {d['field']}: \"{d['old']}\" → \"{d['new']}\"")
    print("="*55)


if __name__ == '__main__':
    compute_diff()
