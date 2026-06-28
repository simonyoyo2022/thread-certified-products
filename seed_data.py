#!/usr/bin/env python3
"""Seed the data/products.json with Tuya sample data so the web app can start immediately."""
import json, os, datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

TUYA_DATA = [
    {"company": "Tuya Global Inc", "product_name": "Door Window Sensor",
     "product_type": "Built on Thread", "device_type": "Sensor", "sub_category": "Contact"},
    {"company": "Tuya Global Inc", "product_name": "Motion Sensor",
     "product_type": "Built on Thread", "device_type": "Sensor", "sub_category": "Presence"},
    {"company": "Tuya Global Inc", "product_name": "Smart Door Lock",
     "product_type": "Built on Thread", "device_type": "Safety", "sub_category": "Door lock"},
    {"company": "Tuya Global Inc", "product_name": "Smart Window Covering",
     "product_type": "Built on Thread", "device_type": "Window covering", "sub_category": "-"},
    {"company": "Tuya Global Inc", "product_name": "Thread Bulb",
     "product_type": "Built on Thread", "device_type": "Lighting", "sub_category": "Bulb"},
    {"company": "Tuya Global Inc", "product_name": "Thread Color Temperature Light Drive",
     "product_type": "Built on Thread", "device_type": "Lighting", "sub_category": "-"},
    {"company": "Tuya Global Inc", "product_name": "Thread Dimmable Light Drive",
     "product_type": "Built on Thread", "device_type": "Lighting", "sub_category": "-"},
    {"company": "Tuya Global Inc", "product_name": "TS24-LC5",
     "product_type": "Thread Certified Component", "device_type": "Module", "sub_category": "-"},
    {"company": "Tuya Global Inc", "product_name": "TS24-U",
     "product_type": "Thread Certified Component", "device_type": "Module", "sub_category": "-"},
    {"company": "Tuya Global Inc", "product_name": "TS24-U-IPEX",
     "product_type": "Thread Certified Component", "device_type": "Module", "sub_category": "-"},
]

output = {
    "last_updated": datetime.datetime.now().isoformat(),
    "total_products": len(TUYA_DATA),
    "total_companies": 1,
    "note": "Partial data (Tuya only). Run a full scrape to get all companies.",
    "products": TUYA_DATA,
}

out_path = os.path.join(DATA_DIR, 'products.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"Seeded {len(TUYA_DATA)} products to {out_path}")
