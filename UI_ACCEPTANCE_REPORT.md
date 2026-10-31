# CatSense AI／Meow一下 UI 實際驗收報告

驗收日期：2026-10-31  
正式專案：`C:\Users\sinyu\OneDrive\桌面\meow_house_integrated_v3_20261023`

## 驗收邊界

- 正式網站 `http://127.0.0.1:8000/health` 回應 HTTP 200，服務狀態為 `ok`。
- 所有會寫入資料的操作均在隔離 SQLite（`tests/.tmp/ui_acceptance.db`）與獨立 Port 8900 進行。
- 未對正式 Supabase 執行 Migration、測試寫入或資料搬移。
- 未修改 YOLO、ROI、模型權重、影片與既有監測流程。

## 四頁畫面結果

| 頁面 | 實際結果 | 主要確認項目 |
| --- | --- | --- |
| 首頁 | 通過 | 五項主導覽、真實直式攝影機比例、無純黑側邊、離線／等待辨識空狀態、設備離線狀態 |
| 我的貓咪 | 通過 | 大頭貼上傳、基本資料編輯、日期切換、今日總覽／每日紀錄／每日分析頁籤、真實空狀態 |
| 健康照護 | 隔離環境通過 | 行事曆、提醒新增、編輯、完成狀態；正式 Supabase 尚待 Migration 授權 |
| 活動分析 | 通過 | 7 天、30 天、自訂日期範圍、零資料統計與空狀態 |

桌面版以 1440×900 驗收，手機版以約 390×844 驗收。四頁在手機寬度的 `scrollWidth` 與 `clientWidth` 一致，未出現水平溢位；手機選單展開後仍為相同五個項目：首頁、我的貓咪、健康照護、活動分析、通知。

## 實際操作測試

- 貓咪大頭貼：隔離環境上傳成功，畫面顯示「貓咪照片已更新」。
- 上傳測試產生的圖片已移出正式靜態目錄，保存在 `work/ui_acceptance_artifacts/test_avatar_upload.png`，避免留下無資料庫關聯的公開檔案。
- 基本資料：編輯並儲存成功，畫面顯示「基本資料已儲存」。
- 日期切換：切換至 2026-10-30 後，當日無資料時顯示空狀態，未產生假紀錄。
- 我的貓咪頁籤：今日總覽、每日紀錄、每日分析皆可切換；長期趨勢仍導向活動分析。
- 健康提醒：隔離 SQLite 中新增、編輯、標記完成成功。
- 驗收用健康提醒在完成測試後已從隔離 SQLite 移除；正式 Supabase 從未收到該資料。
- 活動分析：近 7 天、近 30 天及 2026-10-20～2026-10-22 自訂區間皆正確更新狀態列。
- 瀏覽器 Console：四頁驗收期間沒有 error 等級訊息。
- 自動測試：`24 passed`；另有 1 項 Starlette TestClient 套件棄用警告，不影響本次功能。

## 真實資料與空狀態

- 無攝影機即時資料時顯示 `OFFLINE`、等待攝影機畫面或尚未更新，不顯示假 LIVE。
- 無有效 ROI 紀錄時顯示等待辨識／尚無事件，不宣稱實際進食或飲水。
- 無食碗量測時顯示 `—` 與尚無量測資料，不顯示假重量或進食量。
- 無健康歷史時顯示資料模型尚無歷史，不生成假疫苗、驅蟲或洗澡紀錄。
- 模擬裝置會明確標示為模擬裝置，且未回報時顯示離線。

## 健康照護 Migration（尚未套用正式 Supabase）

待審 Migration：`migrations/versions/20261031_0003_add_care_reminders.py`

新增資料表 `care_reminders`，欄位如下：

- `id`：主鍵
- `pet_id`：外鍵至 `pets.id`
- `owner_id`：外鍵至 `users.id`
- `category`、`title`
- `scheduled_at`、`recurrence`、`advance_minutes`
- `note`
- `completed`、`completed_at`
- `created_at`、`updated_at`

索引包含 pet、owner、category、scheduled time、completed，以及 `(pet_id, scheduled_at)` 複合索引。影響僅為新增一張表與索引，不修改或刪除既有 20 張正式資料表。隔離 SQLite 已由 SQLAlchemy 建表並完成 API 與 UI 新增／編輯／完成測試。正式 Supabase 仍需使用者另行授權後才可執行 Alembic upgrade。

## 截圖

- `outputs/ui_acceptance/home_1440.jpg`
- `outputs/ui_acceptance/pet_1440.jpg`
- `outputs/ui_acceptance/healthcare_1440.jpg`
- `outputs/ui_acceptance/analysis_1440.jpg`
- `outputs/ui_acceptance/home_mobile_390.jpg`

## 本輪相關程式檔案

- `app/templates/base.html`
- `app/templates/dashboard.html`
- `app/templates/pet.html`
- `app/templates/healthcare.html`
- `app/templates/analysis.html`
- `app/static/css/catsense.css`
- `app/static/js/common.js`
- `app/static/js/dashboard.js`
- `app/static/js/pet.js`
- `app/static/js/healthcare.js`
- `app/static/js/analysis.js`
- `app/api/pets.py`
- `app/api/activities.py`
- `app/api/healthcare.py`
- `app/api/iot.py`
- `app/models/healthcare.py`
- `app/models/__init__.py`
- `app/main.py`
- `migrations/versions/20261031_0003_add_care_reminders.py`
- `tests/test_app.py`

## 尚待人工／正式環境確認

1. 正式 Supabase 尚未套用 `care_reminders` Migration；正式健康提醒 API 會安全回報需要 Migration，而不是自動建表。
2. 真實攝影機長時間串流、手機實體瀏覽器與不同裝置字型仍建議在展示設備上做一次人工驗收。
3. 目前沒有真實 ROI／重量資料的日期會忠實顯示空狀態；待硬體或監測資料進入後再驗證有資料圖表。
4. Starlette TestClient 有棄用警告，後續可安排升級測試相依套件，但不宜在展示前臨時大改。
