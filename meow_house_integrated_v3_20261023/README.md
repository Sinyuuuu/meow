# Meow一下：AI 智慧貓咪寄養照護 Prototype

「人負責照顧，AI 負責記錄，飼主遠端掌握。」

這是一個可執行的大專專題 MVP：OpenCV 讀取 Webcam 或 MP4、Ultralytics YOLO 偵測 `cat`、以 Bounding Box 中心點判斷五個 ROI、經過時間型防抖後，把進入／離開／停留時間寫入 SQLite，FastAPI Dashboard 再顯示即時畫面與活動資料。

> 本系統只提供活動異常提醒與建議確認，不提供疾病或健康診斷。

## 使用 VS Code 開啟完整專案

雙擊根目錄的 `meow-house.code-workspace`，或在 VS Code 選擇「檔案 → 開啟工作區」。左側 Explorer 會顯示完整的 `app`、`data`、`docs`、`scripts` 與 `tests`。按 `F5` 並選擇「啟動 Meow一下網站」即可從整合終端啟動 FastAPI。

## 已完成範圍

- Webcam／MP4 輸入與斷線處理
- YOLO 預訓練模型，只取 `cat`（COCO class 15）最高信心偵測
- 五區 polygon ROI，使用 `data/rois.json` 的 0–1 正規化座標
- 可設定秒數的 zone-change 防抖
- SQLite + SQLAlchemy 活動區段紀錄
- Bounding Box、confidence、中心點、ROI 與 Current Zone 標註影片
- FastAPI API、會員登入、主人 Dashboard、活動 Timeline、區域分析、Rule-based 提醒
- OWNER／CAREGIVER／ADMIN 三種角色工作台
- 照護任務勾選、真人照護留言、管理員完整營運中心
- 帳號停用、照護員指派、裝置心跳、ROI 線上設定、稽核紀錄
- Rule-based 提醒門檻、處理狀態與系統維運待辦
- Service Key 保護的未來邊緣攝影機資料接收 API
- 私密 API／即時影像登入保護；Monitor 啟停限 CAREGIVER、ADMIN
- 決定性測試影片與 detector，供沒有貓咪影片時驗證整條資料管線

## 專案結構

```text
app/
  main.py                 FastAPI 與頁面路由
  config.py               環境設定
  database.py             SQLAlchemy engine / seed
  api/                    API 與登入路由
  ai/
    detector.py           YOLO cat detector、測試 detector
    zones.py              ROI 讀取與中心點判斷
    tracker.py            時間型防抖狀態機
    monitor.py            影像→偵測→ROI→DB→標註畫面
  models/                 會員、貓咪、寄養、活動、提醒資料表
  services/               活動區段、提醒、密碼雜湊
  templates/              Jinja2 頁面
  static/                 Dashboard CSS / JavaScript / live frame
data/rois.json             五區 ROI 設定
scripts/                   CLI monitor 與測試影片產生器
tests/                     ROI、防抖、資料庫、登入測試
database/app.db            首次啟動建立
outputs/annotated_demo.mp4 標註後展示影片
```

## 安裝與啟動（PowerShell）

Windows 使用者也可以直接雙擊專案根目錄的 `start_meow.bat`（或中文捷徑 `啟動網站.bat`）；請保持開啟後的黑色終端視窗，按 `Ctrl+C` 或關閉視窗就會停止網站。

若是第一次拿到 ZIP、尚未建立 `.venv`，請先雙擊 `install_and_start.bat`（或中文捷徑 `第一次安裝並啟動.bat`）。它只需執行一次；之後直接雙擊 `start_meow.bat`。英文批次檔刻意只使用 ASCII 內容，避免 Windows 在中文路徑下發生編碼解析錯誤。啟動器會依序尋找 8000、8010、8080、8765 的可用連接埠並自動開啟正確網址。

首次從 ZIP 解壓縮啟動時，系統會自動建立 `database/` 與 SQLite 資料庫，不需要手動建立資料表。

Python 3.11 以上：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

共用展示環境請務必替換 `.env` 的 `APP_SECRET_KEY`；未設定時系統會使用每次啟動重新產生的安全暫時值，既有登入工作階段會在重啟後失效。

啟動網站：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

開啟 <http://127.0.0.1:8000>，示範帳號：

- OWNER：`owner@meow.local`
- CAREGIVER：`caregiver@meow.local`
- ADMIN：`admin@meow.local`
- 三個帳號的 Prototype 密碼：`Meow123!`

## Milestone 1：實際 YOLO + Webcam／MP4

完整的相機設定、ROI 校正、參數調整、測試資料與評估方式請見 [YOLO 實作指南](docs/YOLO實作指南.md)。系統角色、資料責任與展示流程請見 [專題系統架構](docs/PROJECT_ARCHITECTURE.md)。

Webcam 0：

```powershell
python scripts/run_monitor.py --source 0 --detector yolo --display
```

自己的貓咪影片：

```powershell
python scripts/run_monitor.py --source data/my-cat.mp4 --detector yolo --display
```

第一次使用 `yolo11n.pt` 時 Ultralytics 會下載官方預訓練權重。按 `Q` 結束視窗。標註影片預設輸出到 `outputs/annotated_demo.mp4`。

## 無攝影機時的完整管線測試

這個模式不宣稱是 YOLO；它以明確標記建立可重現測試，專門驗證 ROI、防抖、活動區段、SQLite 與 Dashboard 是否全部接通：

```powershell
python scripts/generate_demo_video.py
python scripts/run_monitor.py --source data/demo.mp4 --detector demo-color
```

影片依序停留 REST → FOOD → WATER → LITTER → ACTIVITY，每區 3.2 秒，並故意插入一個錯區影格驗證防抖。

## 從網站啟動 Monitor

```http
POST /api/monitor/start
Content-Type: application/json

{"source":"data/my-cat.mp4","detector":"yolo","save_annotated_video":true}
```

Monitor 啟停 API 需使用 `CAREGIVER` 或 `ADMIN` 登入工作階段。為避免 Webcam 長時間監測產生過大的影片，`save_annotated_video` 預設為 `false`，Demo 時再明確開啟。

其他 API：

- `GET /api/monitor/status`
- `POST /api/monitor/stop`
- `GET /api/activities/summary`
- `GET /api/activities/recent`
- `GET /api/activities?day=2026-09-15`
- `GET /api/alerts`
- `POST /api/alerts/evaluate`
- `GET /api/pets/current`
- `GET /api/boarding/current`
- `GET /api/admin/users`（ADMIN）
- `GET /api/admin/devices`（ADMIN）
- `GET/PUT /api/admin/rois/{zone}`（ADMIN）
- `GET /api/admin/audit`（ADMIN）
- `POST /api/ingest/heartbeat`（需 `MEOW_SERVICE_KEY`）

FastAPI 互動文件：<http://127.0.0.1:8000/docs>

## 調整 ROI 與防抖

- `data/rois.json`：每個 polygon 點為 `[x比例, y比例]`，範圍 0–1。
- `.env` 的 `ZONE_SWITCH_SECONDS`：新區域需持續多久才確認切換，預設 2 秒。
- `.env` 的 `YOLO_CONFIDENCE`：cat 最低信心，預設 0.35。
- `.env` 的 `CAMERA_SOURCE`：攝影機 index 或影片路徑。
- `.env` 的 `MISSING_CAT_ALERT_SECONDS`：多久未偵測到貓咪後關閉目前區段並提醒。
- `.env` 的 `LONG_STAY_ALERT_SECONDS`：同區停留多久後建立建議確認提醒。

正式 Demo 前，請依實際攝影機視角重新量測 `data/rois.json`。目前配置是適合快速說明流程的五區示意。

管理員也可以在網站的「ROI 區域設定」直接更新 polygon；新啟動的 AI Monitor 會讀取最新設定。

## SQLite 與 MySQL

Prototype 預設使用 SQLite，不需要另外安裝資料庫。日後切換 MySQL 時，先建立空資料庫，再把 `.env` 改為：

```env
DATABASE_URL=mysql+pymysql://使用者:密碼@127.0.0.1:3306/meow_house?charset=utf8mb4
```

SQLAlchemy models 與 API 不需改寫。正式遷移資料時仍建議加入 Alembic migration。

## 測試

```powershell
pytest -q
```

## 下一階段

多房間管理、寄養日記照片上傳與正式 Alembic 遷移可沿現有 models/API 結構擴充；第一階段刻意不做多貓 Re-ID、醫療診斷、金流或複雜 IoT。此次來源檔整合判定與測試結果請見 [整合檢查報告](docs/INTEGRATION_REPORT.md)。
