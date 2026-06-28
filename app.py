#!/usr/bin/env python3
"""
Thread Group Certified Products - Flask Backend
Serves the dashboard, provides REST API, and manages scheduled scraping.
"""

import os
import json
import threading
import logging
import subprocess
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file
from flask_apscheduler import APScheduler

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ── Flask App ──────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'thread-group-dashboard-2024')

# Detect cloud environment (set IS_CLOUD=true in render.yaml)
IS_CLOUD = os.environ.get('IS_CLOUD', '').lower() == 'true'

# APScheduler config
app.config['SCHEDULER_API_ENABLED'] = True

scheduler = APScheduler()
scheduler.init_app(app)

# ── Global scrape state ────────────────────────────────────
scrape_state = {
    'running': False,
    'progress': 0,
    'total': 100,
    'message': 'Ready',
    'last_run': None,
    'last_status': None,
}
scrape_lock = threading.Lock()

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
PRODUCTS_FILE = os.path.join(DATA_DIR, 'products.json')


# ── Helper functions ───────────────────────────────────────
def send_mac_notification(title, message):
    """Send macOS desktop notification."""
    try:
        script = f'display notification "{message}" with title "{title}" sound name "Ping"'
        subprocess.run(['osascript', '-e', script], check=True, timeout=5)
        logger.info(f"Notification sent: {title}")
    except Exception as e:
        logger.warning(f"Failed to send notification: {e}")


def progress_callback(step, total, msg):
    with scrape_lock:
        scrape_state['progress'] = step
        scrape_state['total'] = total
        scrape_state['message'] = msg


def run_scrape_task():
    """Run scraping in background thread using Playwright-based scraper."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    with scrape_lock:
        if scrape_state['running']:
            return
        scrape_state['running'] = True
        scrape_state['progress'] = 0
        scrape_state['message'] = '開始抓取資料...'

    try:
        if IS_CLOUD:
            # ── Cloud mode: Playwright scrapes on the cloud server ──
            scraper_path = os.path.join(base_dir, 'fix_dt_sc_playwright.py')
            with scrape_lock:
                scrape_state['progress'] = 10
                scrape_state['message'] = '☁️ 雲端抓取中（約 15 分鐘）...'
        else:
            # ── Local mode: same Playwright scraper ──
            scraper_path = os.path.join(base_dir, 'fix_dt_sc_playwright.py')
            with scrape_lock:
                scrape_state['progress'] = 10
                scrape_state['message'] = '🖥️ 本地抓取 Device Type & Sub Category...'

        result = subprocess.run(
            ['python3', scraper_path],
            cwd=base_dir, capture_output=True, text=True, timeout=1800
        )
        logger.info(f"Playwright scraper stdout:\n{result.stdout[-2000:]}")
        if result.returncode != 0:
            raise RuntimeError(f"Playwright scraper failed: {result.stderr[-500:]}")

        # Regenerate Excel
        with scrape_lock:
            scrape_state['progress'] = 85
            scrape_state['message'] = '正在生成 Excel 報表...'
        excel_path = os.path.join(base_dir, 'generate_excel_all.py')
        result2 = subprocess.run(
            ['python3', excel_path],
            cwd=base_dir, capture_output=True, text=True, timeout=120
        )
        if result2.returncode != 0:
            raise RuntimeError(f"Excel generation failed: {result2.stderr[-300:]}")

        with open(PRODUCTS_FILE, encoding='utf-8') as f:
            final_data = json.load(f)
        n_products  = len(final_data.get('products', []))
        n_companies = len(set(p['company'] for p in final_data.get('products', [])))

        with scrape_lock:
            scrape_state['running'] = False
            scrape_state['last_run'] = datetime.now().isoformat()
            scrape_state['last_status'] = 'success'
            scrape_state['progress'] = 100
            scrape_state['message'] = f"✅ 完成！{n_products} 個產品 / {n_companies} 家公司"

        send_mac_notification(
            "Thread Group Dashboard",
            f"✅ 資料更新完成！共 {n_products} 個產品 / {n_companies} 家公司"
        )
        logger.info("Scrape completed successfully")

    except Exception as e:
        with scrape_lock:
            scrape_state['running'] = False
            scrape_state['last_status'] = 'error'
            scrape_state['message'] = f'❌ 錯誤：{str(e)}'
        send_mac_notification(
            "Thread Group Dashboard",
            f"❌ 資料更新失敗：{str(e)[:80]}"
        )
        logger.error(f"Scrape failed: {e}", exc_info=True)


# ── Scheduled jobs ─────────────────────────────────────────
@scheduler.task('cron', id='monthly_scrape', day='last', hour=23, minute=0)
def monthly_scrape():
    """Run scrape on last day of each month at 23:00."""
    logger.info("Monthly auto-scrape triggered")
    send_mac_notification(
        "Thread Group Dashboard",
        "🔄 開始每月自動更新認證產品資料..."
    )
    thread = threading.Thread(target=run_scrape_task, daemon=True)
    thread.start()


# ── REST API Routes ────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/data')
def api_data():
    """Return current cached data."""
    if not os.path.exists(PRODUCTS_FILE):
        return jsonify({'error': 'No data available. Please run a scrape first.'}), 404
    
    with open(PRODUCTS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    
    return jsonify(data)


@app.route('/api/status')
def api_status():
    """Return current scrape status."""
    with scrape_lock:
        state = dict(scrape_state)
    
    # Add next scheduled run info
    try:
        job = scheduler.get_job('monthly_scrape')
        if job:
            state['next_run'] = str(job.next_run_time)
        else:
            state['next_run'] = None
    except:
        state['next_run'] = None
    
    return jsonify(state)


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """Trigger manual data refresh."""
    with scrape_lock:
        if scrape_state['running']:
            return jsonify({'error': 'Scrape already in progress'}), 409
    
    thread = threading.Thread(target=run_scrape_task, daemon=True)
    thread.start()
    
    return jsonify({'message': 'Scrape started', 'status': 'running'})


@app.route('/api/cancel', methods=['POST'])
def api_cancel():
    """Cancel ongoing scrape."""
    import scraper as sc
    sc.cancel_scrape()
    return jsonify({'message': 'Cancel signal sent'})


@app.route('/api/download/excel')
def api_download_excel():
    """Download the latest Excel file."""
    excel_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'Thread_Certified_Products_All.xlsx')
    if not os.path.exists(excel_path):
        return jsonify({'error': 'Excel file not found. Run a scrape first.'}), 404
    return send_file(excel_path, as_attachment=True,
                     download_name='Thread_Certified_Products_All.xlsx')


@app.route('/api/logs')
def api_logs():
    """Return scrape log history."""
    log_file = os.path.join(DATA_DIR, 'scrape_log.json')
    if not os.path.exists(log_file):
        return jsonify([])
    with open(log_file) as f:
        return jsonify(json.load(f))


@app.route('/api/companies')
def api_companies():
    """Return summary data grouped by company."""
    if not os.path.exists(PRODUCTS_FILE):
        return jsonify([])
    
    with open(PRODUCTS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    
    products = data.get('products', [])
    
    # Group by company
    companies = {}
    for p in products:
        co = p['company']
        if co not in companies:
            companies[co] = {
                'name': co,
                'total': 0,
                'device_types': set(),
                'sub_categories': set(),
                'product_types': set(),
            }
        companies[co]['total'] += 1
        if p.get('device_type') and p['device_type'] != '-':
            companies[co]['device_types'].add(p['device_type'])
        if p.get('sub_category') and p['sub_category'] != '-':
            for sc in p['sub_category'].split(', '):
                companies[co]['sub_categories'].add(sc)
        if p.get('product_type'):
            companies[co]['product_types'].add(p['product_type'])
    
    # Convert sets to sorted lists
    result = []
    for co, info in sorted(companies.items(), key=lambda x: -x[1]['total']):
        result.append({
            'name': co,
            'total': info['total'],
            'device_types': sorted(info['device_types']),
            'sub_categories': sorted(info['sub_categories']),
            'product_types': sorted(info['product_types']),
        })
    
    return jsonify(result)


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    scheduler.start()
    logger.info("Thread Group Dashboard starting on http://localhost:5001")
    logger.info("Monthly auto-scrape scheduled for last day of each month at 23:00")
    app.run(host='0.0.0.0', port=5001, debug=False)
