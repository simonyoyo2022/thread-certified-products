# Thread Group Certified Products Dashboard

即時查看 Thread Group 官方認證產品資料的互動式 Dashboard。

🌐 **Live Demo**: https://thread-certified-products.onrender.com

## 功能特色

- 📊 **Dashboard 總覽** — 產品數量統計、Device Type / Sub Category 分佈圖表
- 🏢 **公司列表** — 128 家公司，含各公司產品分類詳情
- 📦 **產品目錄** — 447 個認證產品，可按公司/DT/SC 篩選
- 📈 **分析圖表** — 互動式圓餅圖、長條圖
- 🔄 **手動刷新** — 一鍵重新抓取 Thread Group 最新認證資料
- 📅 **每月自動更新** — 每月底 23:00 自動抓取並發送通知
- 📱 **手機友善** — 支援 iPhone / Android，可加入主畫面

## 資料來源

[Thread Group Certified Products](https://threadgroup.org/Certified-Products)

## 技術架構

| 組件 | 技術 |
|------|------|
| 後端 | Python Flask + APScheduler |
| 爬蟲 | Playwright (Chromium) |
| 前端 | Vanilla HTML/CSS/JS + Chart.js |
| 部署 | Render.com (Singapore region) |
| 報表 | openpyxl |

## 本地開發

```bash
# 安裝依賴
pip install -r requirements.txt
python -m playwright install chromium

# 啟動開發伺服器
python app.py
# 打開 http://localhost:5001
```

## 更新資料

```bash
# 重新抓取所有 Device Type 和 Sub Category
python fix_dt_sc_playwright.py

# 重新生成 Excel 報表
python generate_excel_all.py

# 推送到 GitHub（Render 會自動重新部署）
git add data/products.json Thread_Certified_Products_All.xlsx
git commit -m "Update data: $(date +%Y-%m-%d)"
git push
```

## 授權

MIT License
