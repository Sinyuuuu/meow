# Meow一下 Supabase 與 IoT 第一階段整合報告

> 執行日期：2026-10-28  
> 範圍：安全、非破壞性的本機程式開發、Migration 準備與測試。  
> 限制：本次沒有連線、建表、搬移或切換任何遠端 Supabase 資料庫，也沒有修改正式 SQLite 資料。

## 1. 目前資料庫實際使用狀態

- 應用程式目前實際設定的資料庫驅動為 **SQLite**，不是 Supabase。
- 目前 SQLite 檔案：`C:/Users/sinyu/Documents/Codex/MeowHouseData/app.db`。
- 以 `scripts/database_admin.py status` 執行完整性檢查，結果為 `ok`。
- 正式 SQLite 目前仍維持原本 16 張應用資料表；本次新增的 4 張 IoT 資料表尚未套用至正式檔案。
- 現有主要資料筆數包含：3 位使用者、1 隻貓、1 筆寄養單、9 筆活動紀錄、1 筆提醒、5 筆照護任務及 18 筆稽核紀錄。
- `SUPABASE_DATABASE_URL` 與主動的 PostgreSQL `DATABASE_URL` 在本次執行環境中都未設定，因此網站尚未使用 Supabase。
- `app/config.py` 已可將 `postgres://` 或 `postgresql://` 正規化成 `postgresql+psycopg://`，並自動加入 `sslmode=require`；SQLAlchemy 2 與 `psycopg[binary] 3.x` 的宣告相容。

### 開發前備份

修改前已建立可回復備份，且沒有覆蓋既有備份：

| 類型 | 路徑 | SHA-256 |
|---|---|---|
| 程式碼 ZIP | `C:/Users/sinyu/Documents/Codex/MeowHouseBackups/meow_house_code_20261028_012957.zip` | `14F1BF891E3CC504701F103EC557D9AA743E69A3337A35C0BF8F91BA24A8F0BB` |
| SQLite 線上備份 | `C:/Users/sinyu/Documents/Codex/MeowHouseBackups/meow_house_db_20261028_012957.db` | `C48099DEEF4B9658B9A142563CB15E3BBB2CBAB7ABC0596B635BAE243D302067` |

備份資料庫已通過 SQLite `PRAGMA integrity_check`。正式資料庫不需要也不應從這份備份還原，除非未來真的發生資料損壞。

## 2. Supabase 連線驗證結果

| 項目 | 結果 | 說明 |
|---|---|---|
| SQLite 連線 | 通過 | 完整性為 `ok`，既有資料可讀 |
| Supabase URL 格式支援 | 通過程式檢查 | 支援 psycopg、Shared Pooler 與 SSL |
| Supabase 真實網路連線 | **未執行** | 環境未設定連線字串，且本次未獲遠端操作授權 |
| Supabase Schema | **未建立** | 未執行遠端 Migration |
| Supabase 資料搬移 | **未執行** | 沒有讀取或猜測密碼，也沒有切換正式資料庫 |

敏感設定只應放在未提交的 `.env` 或作業系統環境變數。可從 `.env.example` 複製欄位名稱，但不可把實際密碼、Service Role Key 或完整連線字串提交到版本控制。

遮蔽後的設定形式：

```dotenv
# 平常仍使用 SQLite；未經驗證前不要更改這一行。
DATABASE_URL=sqlite:///C:/Users/<user>/Documents/Codex/MeowHouseData/app.db

# 由 Supabase Connect 畫面取得；密碼必須 URL percent-encode。
SUPABASE_DATABASE_URL=postgresql+psycopg://<user>:<password>@<pooler-host>:5432/postgres?sslmode=require

# 完成遠端 Migration 並驗證後，正式環境建議關閉啟動時 create_all。
AUTO_CREATE_SCHEMA=false
```

## 3. 新增及修改的檔案

### 新增

| 相對路徑 | 用途 |
|---|---|
| `app/models/iot.py` | IoT 裝置、校正、重量讀值與攝食事件 ORM |
| `app/services/feeding_service.py` | 依穩定重量下降建立候選攝食事件 |
| `app/api/iot.py` | 裝置與重量資料查詢 API |
| `app/api/feeding.py` | 攝食事件查詢 API |
| `alembic.ini` | Alembic 主設定 |
| `migrations/env.py` | 從環境變數安全取得 Migration 連線 |
| `migrations/script.py.mako` | Alembic Revision 範本 |
| `migrations/README.md` | Migration 操作守則 |
| `migrations/versions/20261028_0001_baseline_existing_schema.py` | 原 16 表唯讀驗證基線 |
| `migrations/versions/20261028_0002_add_iot_foundation.py` | 新增 4 張 IoT 表與索引 |
| `scripts/validate_database_schema.py` | 資料表驗證與來源／目標筆數比對 |
| `scripts/simulate_weight_sensor.py` | 以 HTTP 模擬 ESP32/HX711 重量序列 |
| `tests/test_iot.py` | 認證、驗證、重複防護、事件與中斷測試 |

### 修改

| 相對路徑 | 內容 |
|---|---|
| `requirements.txt` | 加入 Alembic；保留 FastAPI、SQLAlchemy、psycopg、YOLO/OpenCV |
| `.env.example` | 加入 Schema 模式與攝食門檻範例，不含秘密 |
| `app/config.py` | 新增 `AUTO_CREATE_SCHEMA` 及攝食事件門檻設定與驗證 |
| `app/database.py` | 註冊 IoT Model；支援本機自動建表模式與模擬裝置種子 |
| `app/models/__init__.py` | 匯出 4 個 IoT Model |
| `app/api/ingest.py` | 新增經裝置驗證的重量上傳、去重、驗證、503 與事件判定 |
| `app/main.py` | 掛載 IoT 與 feeding Router，未更動現有 UI |
| `scripts/database_admin.py` | 狀態檢查加入 IoT 重要表 |
| `scripts/migrate_sqlite_to_supabase.py` | 支援舊 SQLite 尚無 IoT 表、筆數比對及 Alembic head 標記 |

未重新設計任何模板、CSS 或 JavaScript；OWNER、CAREGIVER、ADMIN、既有登入、YOLO11、FOOD/WATER/LITTER ROI、活動紀錄與提醒皆保留。

## 4. 新增資料庫結構

原本 16 張表不刪除、不改名；Migration `20261028_0002` 只新增以下 4 張表。

### `iot_devices`

- `device_uid`：裝置公開識別碼，唯一。
- `cat_house_id`：裝置所屬貓屋。
- `device_type`、`firmware_version`、`status`、`last_seen_at`：設備生命週期。
- `auth_key_hash`：只保存裝置金鑰的雜湊，不保存明碼。
- `simulated`：區分真實 ESP32 與模擬器。

### `sensor_calibrations`

- 保存 `scale_factor`、`offset`、參考重量、校正時間、校正人員與備註。
- 每次重新校正新增一筆，保留歷史追溯，不覆蓋舊校正。

### `sensor_readings`

- 保存 `raw_value`、`raw_weight_grams`、`filtered_weight_grams`、`quality` 與來源。
- `device_id + sequence_no` 為唯一條件，用於 ESP32 重送時的冪等防護。
- 在接收當下把該貓屋的 `current_pet_id` 快照到 `pet_id`，保留可追溯的貓咪關聯。
- `measured_at` 是裝置量測時間；`received_at` 是伺服器接收時間。

### `feeding_events`

- 關聯裝置、貓屋、貓咪、起訖讀值及起訖時間。
- 保存事件前後重量、估計攝食克數、信心值、狀態、來源、模擬旗標與人工審核資訊。
- 目前先產生 `CANDIDATE`，不直接宣稱貓咪已進食；後續可與 FOOD ROI 事件交叉驗證。

## 5. API 與權限

| Method / Path | 認證與角色 | 行為 |
|---|---|---|
| `POST /api/ingest/measurements` | 裝置金鑰；不使用 Supabase 管理帳密 | 驗證、去重、寫入重量、更新心跳並嘗試產生候選事件 |
| `GET /api/iot/devices` | CAREGIVER／ADMIN | 查詢裝置狀態，不回傳金鑰雜湊 |
| `GET /api/iot/measurements` | CAREGIVER／ADMIN | 依裝置與筆數限制查詢重量 |
| `GET /api/feeding/events` | 已登入且通過既有貓咪存取權限 | 查詢目前貓咪的攝食候選事件 |

裝置認證優先使用該裝置的 `auth_key_hash`；若尚未完成裝置配發，才沿用既有 `MEOW_SERVICE_KEY` 過渡。ESP32 僅呼叫 FastAPI ingest API，**不得持有 Supabase DB 密碼、anon/service role key 或直接連線 PostgreSQL**。

目前事件演算法使用最近 4 筆 `GOOD` 資料，判斷「穩定前值 → 重量下降 → 穩定後值」，並套用：

- 最小下降量 `FEEDING_MIN_DROP_GRAMS`（預設 2 g）
- 最大合理下降量 `FEEDING_MAX_DROP_GRAMS`（預設 200 g）
- 穩定容許差 `FEEDING_STABLE_TOLERANCE_GRAMS`（預設 1 g）

這只是可測試的第一版規則，正式 HX711 到貨後必須依採樣噪聲重新校正。

## 6. Migration 檔案與版本

| Revision | 作用 | 破壞性 |
|---|---|---|
| `20261028_0001` | 確認既有 16 張表完整後建立版本基線 | 不修改既有表；缺表即拒絕 |
| `20261028_0002` | 新增 `iot_devices`、`sensor_calibrations`、`sensor_readings`、`feeding_events` 與索引 | Upgrade 僅新增；Downgrade 只會刪除這 4 張新表 |

本機驗證使用正式 SQLite 的**複本**：

- 驗證檔：`C:/Users/sinyu/Documents/Codex/MeowHouseBackups/migration_verify_20261028_013846.db`
- 驗證結果：Revision 到達 `20261028_0002 (head)`。
- 模型預期 20 張表，資料庫實際 21 張（額外 1 張是 Alembic 的 `alembic_version`）。
- 來源／目標所有共同資料表筆數一致。
- SHA-256：`4F97A4D4AE248A513FC7473705480326A6E1F13493759086CC93D630AA70FEEB`。

## 7. 測試結果及失敗原因

最終回歸測試在另一份已 Migration 的 SQLite 複本執行：

```text
22 passed, 2 warnings in 14.34s
Alembic current: 20261028_0002 (head)
```

涵蓋：

- 無金鑰、錯誤金鑰與正確裝置認證。
- 相同 `device_uid + sequence_no` 重送不新增第二筆資料。
- 負值／過大重量、無時區時間、未來時間與過舊時間拒絕。
- 模擬資料保存為 `SIMULATOR` 且 `simulated=true`。
- 重量序列可建立一筆 `CANDIDATE` 攝食事件。
- 關閉並重建 Session 後資料仍存在，模擬重啟保存。
- OWNER 無權讀取 IoT 管理端點；CAREGIVER／ADMIN 可讀。
- 人為注入資料庫 OperationalError 時，ingest 回傳 HTTP 503 且不洩漏資料庫細節。
- 原本登入、權限、照護、管理與 API 測試均回歸通過。

兩個 Warning 來自 Starlette TestClient 與目前 HTTPX/AnyIO 的棄用提示，不是測試失敗；四天期限內不應為消除 Warning 冒險升級整組 FastAPI 測試相依。

早期測試曾因命令層級注入測試 Service Key，讓一項「未設定 key 應拒絕」的既有測試失敗。已改為 IoT 測試自己隔離並還原環境變數，最終全套測試通過；這不是產品程式錯誤。

## 8. 舊功能相容性

- 現有頁面與視覺設計未修改。
- 現有 Session 登入、角色與 `pet_access` 授權繼續作為查詢 API 的權限來源。
- 現有 AI Monitor、YOLO11、OpenCV、ROI 與 Activity Record 流程未重構。
- IoT 資料透過外鍵附加到 `cat_houses` 與 `pets`，沒有把影像事件混寫成重量事件。
- 新增攝食事件只標示候選與估計克數；不將 FOOD ROI 次數錯稱為實際進食次數。
- SQLite 仍可作為離線／展示備援；PostgreSQL 採相同 SQLAlchemy Model。

注意：`AUTO_CREATE_SCHEMA=true` 是既有 Prototype 的本機相容模式。Supabase 或任何正式環境完成 Alembic 管理後應設定為 `false`，避免啟動時自動建表繞過版本流程。

## 9. 待執行的遠端操作

以下動作**尚未執行**，需要使用者明確授權後才可進行：

1. 在本機 `.env` 放入 Supabase Shared Pooler 連線字串；只驗證連線，不切換網站。
2. 對 Supabase 建立搬移前的可回復點／備份，記錄專案狀態與資料庫時間。
3. 唯讀檢查目標現有 Schema 與各表筆數；若任一應用表已有資料則停止。
4. 選擇其一：
   - 空 Supabase：執行安全搬移腳本建立 20 表、搬資料、校正 sequence、比對筆數並 stamp Alembic head。
   - 已有既有 16 表的 Supabase：先執行 `alembic upgrade head`，再做資料來源與目標比對。
5. 驗證登入、三角色權限、活動／照護資料及 4 個 IoT API。
6. 保持 `DATABASE_URL` 指向 SQLite 進行觀察；驗證完成後才在維護時段切換成 Supabase。
7. 切換後保留原 SQLite 與備份，不刪除；若健康檢查失敗即把 `DATABASE_URL` 切回 SQLite。

在取得授權前，不應執行 `alembic upgrade` 指向遠端、不應執行搬移腳本，也不應修改正式 `DATABASE_URL`。

## 10. 感測模擬器使用方式

啟動既有網站後，在**另一個終端機**設定測試金鑰並執行：

```powershell
$env:MEOW_SERVICE_KEY = "<只存在本機的測試金鑰>"
python scripts/simulate_weight_sensor.py --base-url http://127.0.0.1:8010
```

模擬器會送出帶有唯一序號的穩定重量與下降序列；每筆資料都明確標成 `SIMULATED`。它不接觸 Supabase 帳密。正式 ESP32 上線時，只需讓韌體輸出相同 JSON 介面並改成 `simulated=false`，後端資料流不必重做。

## 11. 下一階段 ESP32／HX711 工作

### 建議順序

1. **裝置配發**：建立管理員配發流程，只在建立當下顯示一次裝置明碼，資料庫只存 hash。
2. **HX711 校正**：空秤歸零、已知砝碼求 scale factor，新增一筆 `sensor_calibrations`。
3. **韌體資料品質**：中位數或移動平均、斷線重送、單調遞增 sequence、NTP 時間與本機緩衝。
4. **事件調參**：用真實碗、飼料與貓咪資料調整穩定窗、下降門檻、震動排除與補飼料事件。
5. **AI + IoT 融合**：只有重量下降時間窗與 FOOD ROI 重疊時提高 confidence；不重疊時留給照護員確認。
6. **多貓辨識**：四天內先保留一屋一貓；後續再做追蹤器 + 外觀 embedding／項圈標記，不應只靠一般 YOLO cat class 宣稱身份辨識。
7. **介面整合**：沿用現有照護員頁面，新增裝置離線、待確認攝食事件與重量趨勢小卡，不重做整體 UI。

### 四天內優先順序

- P0：完成 Supabase 連線唯讀驗證、遠端備份、Migration／搬移演練、筆數驗證與可回復切換。
- P0：以模擬器 Demo「上傳 → 去重 → 儲存 → 查詢 → 候選攝食事件」。
- P0：維持原功能 22 項測試通過。
- P1：ESP32 在沒有 HX711 時先用固定／隨機測試值呼叫 FastAPI。
- P1：加入裝置配發與 caregiver 待確認事件操作。
- P2：真實 HX711 校正、精準攝食量與多貓 Re-ID；硬體與訓練資料不足時不可承諾四天內正式完成。

## 12. 已知風險

- Supabase 免費方案可能暫停、連線數有限；應使用 Shared Pooler、小型 SQLAlchemy pool 與 `pool_pre_ping`。
- 連線密碼含特殊字元時必須 percent-encode；不可把錯誤時的完整 URL 印到畫面或 log。
- SQLAlchemy Model 與 PostgreSQL 結構相容已由型別與 Migration 設計檢查，但真實 Supabase 仍需遠端驗證。
- 目前相依只鎖範圍，沒有完整 lock file；Ultralytics/PyTorch 重裝後可能產生不同版本或效能。
- SQLite 與 PostgreSQL 的時區行為不同；ingest 已強制裝置時間含時區，但舊資料仍需在搬移演練中抽查。
- `feeding_events` 是規則式候選，不是醫療判斷，也不是單憑重量即可百分之百確認哪隻貓吃了多少。
- 手機／攝影機位移會影響固定 ROI；現有 ROI 自動對位或基準點校正仍需另階段處理。

## 13. 結論

第一階段已把現有專案擴充為可版本管理的 20 表 SQLAlchemy 架構，完成裝置驗證重量 API、資料去重、模擬器、候選攝食事件與本機 Migration／回歸測試。正式網站、SQLite 與遠端 Supabase 均未被切換或破壞。下一個安全關卡是取得明確授權後，先做 Supabase **唯讀連線與備份驗證**，而不是直接搬移或切換。
