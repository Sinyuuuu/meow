# Meow一下專案完整分析報告

> 分析日期：2026-10-27  
> 分析範圍：目前工作區根目錄的正式程式、測試與既有說明文件。  
> 安全界線：本次未讀取 `.env` 內容、資料庫資料列、密碼、API Key、Token、影片內容或模型權重；未執行可能寫入資料庫／快取的測試。除本報告外，未修改任何既有檔案。

## 1. 執行摘要

目前專案不是只有靜態網站，而是一個可執行的 FastAPI + SQLAlchemy + OpenCV/YOLO 原型。既有核心已包含：

- OWNER、CAREGIVER、ADMIN 三角色登入與權限邊界。
- 飼主、照護員、管理員三套頁面與 Vanilla JavaScript API 串接。
- Webcam／影片來源、YOLO11 COCO `cat` 偵測、Bounding Box、confidence、ROI、時間式防抖。
- FOOD、WATER、LITTER 三個功能區的進入／離開／停留時間紀錄。
- 照護任務、照護留言、規則式活動提醒、裝置心跳、稽核紀錄。
- SQLite 執行，以及 PostgreSQL／Supabase 連線與搬移工具的程式準備。

目前系統仍以「單一預設貓咪、單一監視器、單一 AI Monitor」為核心。ESP32、HX711 時序重量資料、攝食事件、多貓偵測／追蹤／Re-ID 尚未實作。現有架構可以擴充，但必須先解除 `DEFAULT_PET_ID`、單一 Detection、全域 ROI 檔案及單一 MonitorManager 等限制。

## 2. 專案目錄結構

以下是正式執行程式的精簡結構；`work/` 和 `outputs/` 中的複本、壓縮檔與展示產物不應視為正式來源碼。

```text
專案根目錄/
├─ app/
│  ├─ main.py                    # FastAPI 入口、頁面路由、router 註冊
│  ├─ config.py                  # 環境設定、SQLite/PostgreSQL URL 正規化
│  ├─ database.py                # SQLAlchemy engine/session、建表與 Demo seed
│  ├─ runtime.py                 # 單一 AI Monitor 背景執行緒管理
│  ├─ ai/
│  │  ├─ detector.py             # YOLO cat 與 demo-color detector
│  │  ├─ monitor.py              # OpenCV 影像迴圈、標註、活動寫入
│  │  ├─ tracker.py              # 區域時間防抖；不是多物件 tracker
│  │  └─ zones.py                # ROI polygon 與 point-in-polygon
│  ├─ api/                       # auth/activities/alerts/boarding/care/ingest/monitor/pets/admin
│  ├─ models/                    # user/pet/boarding/activity/alert/governance
│  ├─ services/                  # auth/activity/alert/governance 業務邏輯
│  ├─ templates/                 # 9 個 Jinja2 頁面／基底模板
│  └─ static/                    # CSS 與 7 個頁面 JS 控制器
├─ data/
│  ├─ rois.json                  # 三區正規化 polygon
│  └─ demo.mp4                   # Demo 測試影片
├─ database/                     # 本機 runtime DB、WAL、狀態與影格
├─ scripts/                      # 啟動、AI、影片分析、DB 與 Supabase 搬移工具
├─ tests/                        # 18 個靜態可辨識的 pytest test cases
├─ docs/                         # 架構、YOLO、資料庫及整合說明
├─ outputs/                      # 標註影片、截圖、舊封裝與輸出
├─ work/                         # 匯入來源、驗證複本、工具 runtime
├─ requirements.txt
├─ .env.example
└─ 多個 Windows 一鍵啟動／DB 工具 .bat
```

### 目錄治理注意事項

- `app/` 才是正式程式來源。
- `work/import_meow_codex_v2_20261023/` 是先前匯入版本；`work/verify_integrated_v3_20261023/` 是驗證副本。兩者與根目錄程式重複，搜尋或人工修改時容易改錯份。
- `outputs/` 除展示媒體外還包含多份封裝目錄及 ZIP，建議未來移到專案外的封存區；本次沒有移動。
- `.gitignore` 已排除 `.env`、資料庫、影片、YOLO 權重、即時影格與 outputs 內容，方向正確。

## 3. 開發技術與版本

| 類別 | 技術 | 目前宣告／觀察 |
|---|---|---|
| 語言 | Python | 安裝器接受 3.11／3.12；目前 `.venv` 是 Python 3.12.14 |
| Backend | FastAPI | `>=0.115,<1.0` |
| Server | Uvicorn Standard | `>=0.34,<1.0` |
| ORM | SQLAlchemy | `>=2.0,<3.0` |
| Validation | Pydantic | 由 FastAPI 相依；程式使用 v2 `field_validator` |
| Template | Jinja2 | `>=3.1,<4.0` |
| Frontend | HTML/CSS/Vanilla JS | 無 React；以 `fetch()` 呼叫 JSON API |
| Session | Starlette SessionMiddleware | Cookie session、`same_site="lax"` |
| AI | Ultralytics YOLO11 nano | `yolo11n.pt`、COCO class 15 `cat` |
| Vision | OpenCV | `>=4.10,<5.0` |
| Array | NumPy | `>=2.0,<3.0` |
| Local DB | SQLite | WAL、foreign key、busy timeout |
| Cloud DB | PostgreSQL/Supabase | `psycopg[binary]>=3.2,<4.0`；程式已準備但未在本次確認實際連線 |
| Optional DB | MySQL | `PyMySQL>=1.1,<2.0`，目前沒有 MySQL migration 流程 |
| Tests | pytest + HTTPX | `pytest>=8,<9`、`httpx>=0.28,<1.0` |
| Timezone | zoneinfo + tzdata | 預設 Asia/Taipei |

相依套件只設定範圍，沒有 lock file；Ultralytics 的 PyTorch 等大型傳遞相依套件也沒有固定版本，重裝後可能出現效能或相容性差異。

## 4. 系統架構

```text
OWNER / CAREGIVER / ADMIN Browser
        │ Jinja2 page + fetch JSON + session cookie
        ▼
FastAPI (`app/main.py`)
        ├─ API routers (`app/api/`)
        ├─ domain services (`app/services/`)
        ├─ SQLAlchemy (`app/database.py`)
        │      └─ SQLite 或 PostgreSQL/Supabase
        └─ global MonitorManager (`app/runtime.py`)
               └─ background thread → OpenCV → YOLO → ROI → debounce
                    → ActivityService → DB → dashboard polling

外部裝置 → `X-Service-Key` HTTP → `/api/ingest/*` → DB
```

### 前端架構

- 伺服器端 Jinja2 負責頁面殼與角色導覽，動態資料由各頁 JavaScript 使用 `fetch()` 讀取。
- 首頁與照護員頁每 2.5 秒輪詢 Monitor；即時畫面是持續更新的 JPEG，不是 WebSocket、MJPEG 或 WebRTC 串流。
- `app/static/css/style.css` 具有統一 design tokens、桌機／平板／手機斷點，風格與專題定位一致。
- 共用版面、導覽與角色顯示位於 `app/templates/base.html`。

### 後端架構

- `app/main.py` 在 lifespan 啟動時執行 `init_db()`，以 `create_all()` 建表並在空資料庫建立 Demo 資料。
- Private routers 在註冊時統一加上登入依賴，個別敏感操作再限制 CAREGIVER／ADMIN。
- 業務邏輯已有 services 分層，但部分管理邏輯仍集中於 `app/api/admin.py`。
- AI Monitor 是單一 process 內的全域執行緒；重啟服務後記憶體狀態會重置。

## 5. 已實作功能與完成度

以下「可正常使用」表示程式流程完整且有對應測試／既有驗證紀錄；本次依使用者限制沒有重新執行測試或連接真實硬體。

### 5.1 可正常使用

| 功能 | 證據與位置 |
|---|---|
| 一鍵安裝與啟動 | `install_and_start.bat`、`start_meow.bat`、`scripts/launch_app.py` |
| 登入／登出與三角色 | `app/api/auth.py`、`app/api/dependencies.py`、`app/templates/base.html` |
| 密碼雜湊驗證 | PBKDF2-HMAC-SHA256；`app/services/auth_service.py` |
| OWNER Dashboard | 即時影格、區域、今日次數、地圖、通知；`dashboard.html`／`dashboard.js` |
| CAREGIVER 工作台 | 任務勾選、AI Monitor 啟停、照護留言；`caregiver.html`／`caregiver.js` |
| ADMIN 營運中心 | 帳號、狀態、照護指派、設備、ROI、門檻、待辦、稽核；`admin.html`／`admin.js` |
| 貓咪照護資料檢視 | 基本資料、飲食、照護／醫療備註、照護留言；`pet.html`／`pet.js` |
| 活動 Timeline／分析 | 日期查詢、三區次數與停留時間；`activities.py`、`activities.js`、`analysis.js` |
| 規則式活動提醒 | 未進飲水／進食區、長停留、未偵測；`alert_service.py`、`alerts.py` |
| 真實 YOLO cat 偵測 | class 15、最高信心 bbox；`app/ai/detector.py` |
| ROI 與防抖 | 正規化 polygon、中心／底部中心、時間 threshold；`zones.py`、`tracker.py` |
| 活動區段持久化 | 切區關閉舊紀錄、建立新紀錄；`activity_service.py` |
| Webcam／影片與標註輸出 | `app/ai/monitor.py`、`scripts/run_monitor.py` |
| 基礎裝置心跳／遠端活動寫入 | Service Key 保護；`app/api/ingest.py` |
| SQLite 穩定性設定 | FK、WAL、busy timeout；`app/database.py` |

### 5.2 部分完成

| 功能 | 目前狀態與缺口 |
|---|---|
| Supabase | PostgreSQL driver、URL 正規化、搬移腳本與指南已存在；本次未讀取秘密設定，所以不能判定遠端 DB 是否已正式啟用／驗證。 |
| 寄養流程 | 只有「目前入住」讀取與 Demo seed；沒有申請、審核、Check-in、Check-out、歷史管理 API/UI。 |
| 貓咪管理 | 有 model 與目前貓咪讀取；沒有完整新增／編輯／刪除、照片上傳、多隻切換。 |
| 多房間 | DB 有 `cat_houses`、`camera_devices`，但程式使用單一 `DEFAULT_PET_ID` 與第一台 CameraDevice。 |
| 攝影機來源 | 支援 webcam index 與專案內影片；Web API 對非數字來源一律當成本機檔案，會拒絕 RTSP／HTTP 手機鏡頭 URL。 |
| 即時影像 | 有受登入保護的最新 JPEG，但不是低延遲影片串流。 |
| ROI 管理 | Admin 可改 raw JSON polygon；ROI 是單一全域檔案，不是每個房間／每台攝影機一份，亦無圖形化拖拉校正。 |
| 相機位移處理 | ROI 使用解析度無關座標，但鏡頭角度一變仍會失準；沒有 ArUco/homography 自動重定位。 |
| 健康紀錄 | 只有飼主 medical notes 與活動提醒，沒有生命徵象、體重時間序列、獸醫紀錄；系統正確標示不是醫療診斷。 |
| 睡眠推估 | 有 LONG_STAY 提醒，但不是姿態／睡眠辨識，且目前只對 FOOD/WATER/LITTER 長停留觸發。 |
| 裝置管理 | CameraDevice + heartbeat 可用，但沒有 ESP32 感測器類型、校正、韌體版本、讀值品質或裝置個別憑證。 |
| DB schema evolution | 只有 `create_all()`，沒有 Alembic migration；新增欄位不會自動正確遷移既有資料庫。 |

### 5.3 尚未實作

- ESP32 firmware、Wi-Fi provisioning、重連與離線緩衝。
- HX711／Load Cell 讀值、校正、tare、濾波、重量上傳。
- `sensor_readings`、`feeding_events`、感測器校正等資料表。
- 由重量變化推導「攝食開始／結束／估計克數」。
- 一個 frame 回傳多個 cat bbox。
- ByteTrack／DeepSORT 等多物件追蹤。
- 多貓視覺 Re-ID、embedding gallery、unknown 判斷與人工覆核。
- 貓咪身份與重量事件的 sensor fusion。
- MQTT broker、topic、QoS、Last Will；目前是 HTTP ingest。
- 模型訓練、資料標註、模型評估與版本管理。
- 真正的睡眠／姿態／行為分類模型。

## 6. 主要頁面與元件

| 路徑 | 角色 | 主要元件 | 主要檔案 |
|---|---|---|---|
| `/login` | 公開 | 登入表單、錯誤訊息 | `app/templates/login.html`、`app/api/auth.py` |
| `/` | 已登入；依角色導向不同 template | OWNER 照護總覽／CAREGIVER 工作台／ADMIN 總覽 | `app/main.py` |
| `/caregiver` | CAREGIVER | 今日任務、AI Monitor 控制、照護紀錄 | `caregiver.html`、`caregiver.js` |
| `/admin` | ADMIN | Metrics、AI pipeline、設備、帳號、指派、ROI、規則、稽核 | `admin.html`、`admin.js` |
| `/pet` | 已授權會員 | 貓咪資料、照護備註、最近留言 | `pet.html`、`pet.js` |
| `/activities` | 已登入 | 日期選擇與活動 Timeline | `activities.html`、`activities.js` |
| `/analysis` | 已登入 | 三區停留時間長條圖與摘要 | `analysis.html`、`analysis.js` |
| `/alerts` | 已登入 | 規則提醒、照護員確認 | `alerts.html`、`alerts.js` |
| `/docs` | ADMIN 導覽可進入 | FastAPI Swagger UI | FastAPI 內建 |
| `/health` | 公開 | 基礎 service health | `app/main.py` |

### 建議直接保留的 UI

- `app/templates/base.html` 的角色式側欄與共用 topbar。
- `app/static/css/style.css` 的奶油／木質／柔和色票、卡片、RWD 與手機底部導覽。
- OWNER 首頁「AI 客觀活動＋真人照護」的資訊層級。
- CAREGIVER 工作台的任務與留言流程。
- ADMIN 頁的裝置健康、設定、稽核與最小權限概念。
- Timeline、區域分析與「非醫療診斷」提示。

新感測器頁面應沿用這些 card、metric、timeline、status chip，不必重做整套視覺。

## 7. API 清單與關聯

目前程式共有 44 個 route decorators（包含頁面及 API）。主要 JSON／操作 API 如下：

| 群組 | Method／Path | 用途 |
|---|---|---|
| Auth | `POST /login`、`POST /logout` | Session 登入登出 |
| Pet | `GET /api/pets/current` | 目前預設貓咪資料 |
| Boarding | `GET /api/boarding/current` | 目前入住／房號 |
| Activity | `GET /api/activities` | 依日期列出區段 |
| Activity | `GET /api/activities/recent` | 最新功能區紀錄 |
| Activity | `GET /api/activities/summary` | 今日三區次數／秒數 |
| Alert | `GET /api/alerts` | 提醒與處理狀態 |
| Alert | `POST /api/alerts/evaluate` | CAREGIVER／ADMIN 執行規則 |
| Alert | `PATCH /api/alerts/{id}` | CAREGIVER 確認／解決 |
| Care | `GET /api/care/tasks` | 照護任務 |
| Care | `PATCH /api/care/tasks/{id}` | CAREGIVER 更新完成狀態 |
| Care | `GET /api/care/logs` | 真人照護留言 |
| Care | `POST /api/care/logs` | CAREGIVER 新增留言 |
| Monitor | `GET /api/monitor/status` | 執行狀態、區域、confidence |
| Monitor | `GET /api/monitor/frame` | 最新受保護 JPEG |
| Monitor | `POST /api/monitor/start` | CAREGIVER／ADMIN 啟動 |
| Monitor | `POST /api/monitor/stop` | CAREGIVER／ADMIN 停止 |
| Device ingest | `POST /api/ingest/heartbeat` | Service Key 裝置心跳 |
| Device ingest | `POST /api/ingest/activity` | Service Key 寫入區域活動 |
| Admin | `/api/admin/overview` | 系統摘要 |
| Admin | `/api/admin/users`、`/users/{id}/status` | 建立帳號與生命週期 |
| Admin | `/api/admin/assignments` | 照護員－貓咪指派 |
| Admin | `/api/admin/devices` | CameraDevice／heartbeat |
| Admin | `/api/admin/rois`、`/rois/{zone}` | ROI 查詢與修改 |
| Admin | `/api/admin/settings/{key}` | 規則門檻 |
| Admin | `/api/admin/tasks`、`/tasks/{id}` | 系統維運工作 |
| Admin | `/api/admin/audit` | 稽核紀錄 |

## 8. 資料庫結構

目前共有 16 張 SQLAlchemy 資料表。

| 資料表 | 主要欄位／外鍵 | 用途 |
|---|---|---|
| `users` | id, name, email, password_hash, role | 帳號與角色 |
| `user_states` | user_id→users, status, updated_at | ACTIVE／DISABLED |
| `pets` | owner_id→users, name, photo, gender, age, breed, weight, notes | 貓咪主檔；weight 只是單一靜態值 |
| `pet_access` | user_id→users, pet_id→pets, active | 照護員對貓咪授權 |
| `cat_houses` | room_number, camera_url, current_pet_id→pets | 智慧貓屋與目前入住貓 |
| `boarding_orders` | pet_id→pets, cat_house_id→cat_houses, dates, status | 寄養區段 |
| `care_tasks` | pet_id→pets, type, time, completed | 人工照護待辦 |
| `care_logs` | pet_id→pets, caregiver_id→users, type, note | 真人照護回報 |
| `camera_devices` | cat_house_id→cat_houses, name, source, status | 攝影機登錄 |
| `device_heartbeats` | camera_device_id→camera_devices, last_seen_at | 攝影機最近心跳 |
| `activity_records` | pet_id→pets, zone, entered_at, left_at, duration | AI 功能區活動區段 |
| `alerts` | pet_id→pets, type, message, resolved | 規則式提醒 |
| `alert_handling` | alert_id→alerts, handled_by→users, status, note | 人工處理結果 |
| `audit_logs` | actor_id→users, action, detail, created_at | 敏感操作稽核 |
| `system_settings` | key, value, updated_at | 活動規則門檻 |
| `system_tasks` | title, status, timestamps | 管理員維運待辦 |

### 核心關聯

```text
users ──< pets ──< boarding_orders >── cat_houses ──< camera_devices
  │        │              │                                  │
  │        ├──< activity_records                             └── device_heartbeats
  │        ├──< alerts ─── alert_handling >── users
  │        ├──< care_tasks
  │        └──< care_logs >── users(CAREGIVER)
  ├── user_states
  ├──< pet_access >── pets
  └──< audit_logs
```

### 資料庫現況判定

- `app/config.py` 能把 `postgres://`／`postgresql://` 正規化為 psycopg URL 並要求 SSL。
- `app/database.py` 已為非 SQLite 設定小型 connection pool。
- `scripts/migrate_sqlite_to_supabase.py` 會建立空表、搬移資料、校正 PostgreSQL sequence 並比對筆數；遇到目標已有資料會停止。
- `scripts/database_admin.py` 可以隱藏密碼後檢查 PostgreSQL 連線與重要表筆數。
- 因本次不得讀取秘密設定，無法宣稱目前網站已經實際使用 Supabase；應列為「程式準備完成、部署驗證未確認」。
- 正式擴充前應導入 Alembic，否則新增 sensor／feeding／identity 欄位後，`create_all()` 不會替舊表安全補欄或回滾。

## 9. AI 與影像處理分析

### 9.1 目前模型

- 權重：根目錄 `yolo11n.pt`。
- Framework：Ultralytics YOLO11 nano。
- 類別：COCO class 15 `cat`，見 `app/ai/detector.py`。
- 預設 confidence：0.35；預設 imgsz：960，皆由 `app/config.py` 設定。
- 每個 frame 只選 confidence 最高的 detection，回傳一個 `Detection`。
- 未自行訓練，沒有專題資料集、標註、mAP、precision/recall 或模型版本紀錄。

### 9.2 目前處理管線

1. `cv2.VideoCapture` 讀 webcam index 或檔案。
2. YOLO 只偵測 `cat`。
3. 取最高信心 bbox。
4. 取 bbox `center` 或 `bottom_center`。
5. `ZoneMapper` 用正規化 polygon 判定 FOOD／WATER／LITTER，其他畫面內位置為 GENERAL。
6. `ZoneDebouncer` 要求新區域連續維持指定秒數才切換。
7. `ActivityService` 關閉舊區段並建立新功能區區段。
8. 畫面疊加 ROI、bbox、anchor、confidence、Current Zone。
9. 最新 JPEG 由記憶體 callback 提供給網站，避免 Windows 檔案替換衝突。
10. 可選擇輸出標註 MP4。

### 9.3 可以直接沿用的 AI 程式

- `Detection.anchor()`：可保留給單一 bbox；多貓後仍可逐 detection 使用。
- `YoloCatDetector` 的模型載入與 classes/conf/imgsz 設定。
- `ZoneMapper` 的正規化 polygon 與 point-in-polygon。
- `ZoneDebouncer` 的時間型防抖概念；多貓時需改為每個 track 一個 debouncer。
- `ActivityService` 的「區段」資料設計；多貓時須以 `(pet_id, track/session)` 隔離。
- `AIMonitor._annotate()` 的 ROI 與標註風格。
- `scripts/analyze_lesson_videos.py` 的抽樣分析方式，可擴充為回歸評估工具。

### 9.4 影像功能限制

- `CatDetector.detect()` 回傳 `Detection | None`，這個介面本身阻止多貓。
- 所謂 `tracker.py` 只防止區域抖動，沒有 track ID、軌跡或遮擋恢復。
- 畫面標籤固定寫成 Momo；沒有任何身份推論。
- ROI 固定在影像座標，鏡頭移動後會錯位。
- 進入 FOOD/WATER/LITTER 只能表示「出現在該區」，不能證明真的吃、喝或排泄。
- LONG_STAY 是停留規則，不是睡眠辨識。
- 每個 frame 都執行 inference；`MONITOR_SAMPLE_FPS` 主要控制 publish 間隔，沒有真正節流 YOLO 推論。

## 10. 可直接沿用的程式與設計

### 建議原樣或小改沿用

- 三角色登入、role guard、pet access：`app/api/dependencies.py`、`app/services/governance_service.py`。
- 密碼雜湊：`app/services/auth_service.py`。
- 稽核、系統設定、裝置 heartbeat 的模式：`governance.py`／`governance_service.py`。
- Jinja + Vanilla JS：四天時程下不需要改成 React。
- 全套視覺與 RWD：`app/templates/`、`app/static/css/style.css`。
- Owner／Caregiver／Admin 的責任分工與「AI 非醫療診斷」文案。
- SQLAlchemy Session 與 PostgreSQL 支援。
- AI bbox、ROI、debounce、activity interval 的骨架。

### 應重構後再沿用

- `MonitorManager`：由單一 global monitor 改為 `camera_device_id -> monitor session` 管理；四天內可先維持一台，但 API 要預留 device ID。
- `settings.default_pet_id`：應由 boarding order／cat house 解出 pet，不可再作所有 API 的唯一目標。
- `CameraDevice`：保留攝影機用途；不要硬塞 HX711 欄位，另建一般 IoT device model。
- `activity_records`：可保留相容，但新事件應加入 source、camera、track、confidence 或另建 evidence table。
- ROI 檔案：Demo 可沿用；多房間正式版應存 DB 並以 camera／version 區分。

## 11. ESP32、HX711、多貓與攝食事件整合方案

### 11.1 建議總資料流

```text
ESP32 + HX711 + Load Cell
  └─ 讀取 raw → 校正 → median/EMA 濾波 → grams
       └─ HTTP JSON + device credential + sequence number
            └─ FastAPI `/api/ingest/measurements`
                 └─ sensor_readings (原始可追溯資料)
                      └─ FeedingEventService
                           ├─ 重量穩定／下降事件
                           ├─ FOOD ROI presence
                           ├─ track／pet identity（若可用）
                           └─ feeding_events
                                └─ Owner/Caregiver Dashboard
```

四天版建議使用 HTTP，不要同時引入 MQTT broker。既有 `app/api/ingest.py` 已提供 Service Key、heartbeat 與 audit 模式，最容易擴充。MQTT 可在第二階段用 adapter 接到同一 service，不要讓 MQTT 邏輯直接寫 DB。

### 11.2 建議新增資料表

| 建議表 | 重要欄位 | 說明 |
|---|---|---|
| `iot_devices` | id, cat_house_id, kind, serial_no, status, firmware_version, last_seen_at | ESP32／秤重裝置主檔 |
| `sensor_calibrations` | device_id, scale_factor, offset, calibrated_at, calibrated_by | HX711 校正與可追溯性 |
| `sensor_readings` | device_id, measured_at, sequence_no, value, unit, raw_value, quality | append-only 重量時序；`(device_id, sequence_no)` unique 防重送 |
| `feeding_events` | pet_id nullable, cat_house_id, start/end, before/after/delta_g, confidence, status | 推導後的攝食候選事件，可人工確認 |
| `vision_tracks` | camera_device_id, session_id, track_id, start/end, last_zone | 多物件短期 track |
| `pet_identity_profiles` | pet_id, model_version, reference_uri/vector, active | Re-ID 參考樣本與模型版本 |
| `event_evidence`（可延後） | feeding_event_id, sensor_reading／track reference | 解釋事件如何產生 |

### 11.3 建議新增程式位置

```text
app/models/iot.py
app/models/feeding.py
app/api/iot.py
app/api/feeding.py
app/services/sensor_service.py
app/services/feeding_service.py
app/ai/multi_tracker.py
app/ai/reid.py                 # 第二階段或限定 POC
firmware/esp32_hx711/          # Arduino/PlatformIO 專案
tests/test_sensor_service.py
tests/test_feeding_service.py
```

### 11.4 HX711 實作重點

- 啟動時不要把當下有碗／食物的重量誤當零點；校正與日常 tare 要分開。
- 每次上報至少包含 device ID、sequence、device timestamp、grams、raw、quality。
- 使用中位數加 EMA，並設定「穩定窗口」，不要每次 ADC 抖動都建立事件。
- 碗被整個拿走、照護員補飼料、貓踩到平台，重量變化都不是攝食；事件必須保留 `candidate/reviewed/rejected` 狀態。
- 估計攝食量應表述為「重量差估計」，不能宣稱精準攝取量。
- ESP32 斷網時需要 ring buffer；重送靠 sequence unique 做 idempotency。

### 11.5 攝食事件建議規則

四天內可採可解釋規則，不需要再訓練模型：

1. 重量先穩定至少 N 秒。
2. FOOD ROI 內有貓，或相近時間內有 FOOD zone activity。
3. 重量下降超過最小門檻，但低於「整碗被移走」門檻。
4. 重量再次穩定後結束事件。
5. `estimated_consumed_g = before - after`。
6. 若沒有可靠 identity，`pet_id` 留空或使用「單貓房目前入住貓」，不可硬猜。
7. 照護員可確認、修正或拒絕事件。

### 11.6 多貓個體辨識分階段

**第一層：多貓偵測**  
將 detector 改為 `detect_many(frame) -> list[Detection]`，不再只取最高 confidence。

**第二層：短期追蹤**  
導入 ByteTrack，產生 `track_id`；每個 track 擁有自己的 zone debouncer。這只能回答「同一段影片中的哪一隻」，不能回答牠是 Momo 還是另一隻貓。

**第三層：身份辨識／Re-ID**  
為每隻貓蒐集多角度、不同光線與姿勢的 reference gallery，使用 embedding + nearest-neighbor／classifier，必須設定 `UNKNOWN` 門檻與人工覆核。一般 COCO YOLO 不提供個體身份。

**四天 Demo 的務實選擇**  
完成多 bbox + ByteTrack，身份先採「一屋一貓」、RFID 項圈、不同顏色安全項圈或人工指定 track。真正純視覺 Re-ID 應列為後續研究，否則遮擋、相似花色與夜間畫面很容易誤認。

### 11.7 與攝影機位移相容

- 正規化 ROI 只能適應解析度，不能適應鏡頭移動。
- 可在貓屋固定 4 個 ArUco marker，偵測 marker 後計算 homography，將 frame 校正到固定「貓屋座標」，再套 ROI。
- 若 marker 遺失或 reprojection error 過高，應停止產生區域事件並建立 `CAMERA_CALIBRATION_LOST` 提醒，而不是繼續記錯資料。

## 12. 主要技術與整合風險

| 風險 | 影響 | 建議 |
|---|---|---|
| 單一 `DEFAULT_PET_ID`／Momo hard-code | 多貓、多房間資料會串錯 | 所有 monitor／API 以 boarding/cat_house/pet context 驅動 |
| detector 只回一個 bbox | 第二隻貓完全被忽略 | 先改 `detect_many`，再接 tracker |
| global `MonitorManager` | 只能跑一台 camera；多 worker 狀態不一致 | 四天內單 process；之後建立 monitor registry／worker service |
| ROI 是本機 JSON | 多台相機不能各自校正，雲端多 instance 不同步 | 轉 DB，含 camera_id、version、updated_at |
| 相機移動 | 固定 ROI 立刻失準 | 固定支架或 ArUco/homography；失準時 fail closed |
| 沒有 Alembic | 新增表尚可，改欄位／constraint 風險高 | 新功能前先建立 migration baseline |
| `init_db()` 自動 seed | 空的正式 Supabase 可能出現 Demo 帳號／資料 | seed 改為明確 dev command 或 `SEED_DEMO_DATA` flag |
| 固定開發帳號資料存在 seed | 正式部署安全風險 | 不在報告輸出憑證；正式環境禁用／強制改密碼 |
| Session secret fallback 隨機 | 未設定時重啟即登出；多 instance 互不認 cookie | 正式環境必設穩定高熵 secret |
| 無 CSRF token | Cookie session 的狀態改變請求有風險 | 加 CSRF，正式站設定 HTTPS-only cookie |
| Service Key 為單一全域值 | 一台 ESP32 洩漏影響所有裝置 | 每裝置 credential／可撤銷 hash；至少區分 device ID |
| Supabase 網路依賴 | 網路中斷時 monitor DB commit 失敗可中止影像流程 | 本機 durable queue + retry；AI 與 DB writer 解耦 |
| 無資料 migration version | 不同電腦 schema 可能不同 | Alembic + migration table + CI 檢查 |
| Broad dependency ranges | 重裝結果可能不同 | 建立經驗證 lock／constraints，固定 torch/ultralytics/opencv |
| YOLO imgsz 960 + CPU | 延遲高、掉 frame | 現場量測；必要時降 640、frame skipping 或 GPU/ONNX |
| HX711 漂移／機構干擾 | 誤判攝食克數 | 校正、溫漂測試、穩定窗口、人工覆核 |
| ESP32 時鐘與重送 | 重複／亂序事件 | NTP、server_received_at、sequence unique |
| 真實 Re-ID 資料不足 | 身份誤判，進而污染攝食紀錄 | UNKNOWN 類別、人工覆核、先做 constrained Demo |
| 舊 docs 提到五區，現碼只有三區 | 展示與報告口徑衝突 | 統一為 FOOD/WATER/LITTER；REST/ACTIVITY 僅歷史相容 |
| `work/`、`outputs/` 多份專案 | 容易編輯／執行錯版本 | 後續封存到專案外，只留根目錄正式來源 |
| 外部 Google Fonts | 離線展示字型可能不同 | Demo 前改本機字型或接受 system font fallback |

## 13. 四天內的優先順序與可交付範圍

### P0：四天一定先完成

1. 固定唯一正式專案與資料庫，確認 Supabase migration／連線；保留 SQLite rollback。
2. 導入 Alembic baseline，新增 IoT／sensor／feeding schema。
3. 以 HTTP 完成 ESP32 heartbeat + HX711 weight ingest；先可用模擬器驗證，再接真硬體。
4. 建立重量濾波、idempotency、穩定窗口與候選攝食事件。
5. 在 Caregiver／Owner 現有頁面新增重量趨勢、最近攝食候選與人工確認。
6. 完成斷線、重送、重啟後資料仍存在的整合測試。

### P1：有餘裕才做

1. YOLO `detect_many`。
2. ByteTrack 暫時 track ID。
3. 每個 track 獨立 ROI、防抖及事件 evidence。
4. 用單貓房入住關聯或 RFID／安全色標輔助 identity。

### P2：四天內不要承諾正式完成

- 純視覺多貓 Re-ID 的高準確率版本。
- 睡眠／進食／飲水姿態分類模型。
- MQTT broker、OTA、完整裝置佈署平台。
- 醫療或疾病判斷。

### 建議四日排程

| 日程 | 目標 | 驗收條件 |
|---|---|---|
| Day 1 | 資料庫 baseline、Supabase、IoT schema、ingest contract、感測模擬器 | 模擬重量可安全寫入，重送不重複；舊功能仍可讀 |
| Day 2 | ESP32 + HX711 校正、濾波、heartbeat、斷線重送 | 實機連續讀值、斷網恢復、重量誤差與漂移有紀錄 |
| Day 3 | 攝食事件規則、FOOD ROI fusion、Owner/Caregiver UI | 放入／取出食物可區分，產生 candidate 並可人工確認 |
| Day 4 | 整合測試、Demo 腳本、例外處理；有餘裕才做多 bbox + ByteTrack | 重啟資料不消失、裝置離線可見、事件可追溯、展示流程固定 |

### 四天可行性結論

- **ESP32 + HX711 + 重量時序 + 攝食候選事件 + 現有網站顯示：可行，但要凍結其他 UI 大改。**
- **多 bbox + 短期 track ID：有機會完成 POC。**
- **可靠純視覺多貓 Re-ID：四天風險極高，不應成為主要驗收條件。**

## 14. 建議下一步

1. 先決定四天成果採「單貓房 + HX711 + FOOD ROI sensor fusion」；這最符合既有架構與可驗收性。
2. 在修改程式前建立可回復的 DB／程式快照，並確認目前真正執行的是根目錄版本而非 `work/` 或 `outputs/` 複本。
3. 先設計 migration 與 API payload，再接 ESP32，避免硬體欄位反覆變動。
4. 對重量資料保留 raw、filtered、quality、sequence；衍生事件與原始資料分表。
5. UI 沿用現有 Owner/Caregiver/Admin 設計，只新增「重量／攝食候選／裝置狀態」卡片。
6. 多貓先改 detector interface 與 track ID；身份問題用 constrained 方法展示，視覺 Re-ID 列為後續研究。

整體而言，現有專案最有價值的資產是三角色網站、可解釋的 AI 區域管線、SQLAlchemy 資料層與裝置 ingest／audit 骨架。最需要避免的是同時重做前端、切換資料庫、接硬體、做多貓 Re-ID；四天內應把重點放在「可靠取得重量 → 與 FOOD ROI 對齊 → 產生可人工確認的攝食事件」。
