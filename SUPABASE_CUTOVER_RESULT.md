# CatSense AI／Meow一下 Supabase 正式切換結果

> 執行日期：2026-10-29（Asia/Taipei）  
> 結果：**受控切換成功；正式 `DATABASE_URL` 已指向 Supabase PostgreSQL。**

## 1. 授權資料基準

本次依使用者明確授權採用：

- Supabase PostgreSQL 20 張應用資料表為正式資料基準。
- 保留 `audit_logs.id=19`；它是原始 SQLite 搬移來源中的有效 `LOGIN` 紀錄。
- `pre_supabase_final_20261029_001011.db` 為原始 20 表核對基準。
- 現行 16 表 SQLite、切換前備份及所有歷史備份均保留。

沒有重跑資料搬移，沒有使用 `DROP`、`TRUNCATE`、DELETE 或清空資料庫。

## 2. 切換前最終驗證

| 檢查項目 | 結果 |
|---|---|
| 本機 Python／Uvicorn 程序 | 0 |
| 8000、8010、8080、8765 監聽程序 | 0 |
| SQLite 寫入鎖可取得 | 通過 |
| 原始 20 表快照 `integrity_check` | `ok` |
| 原始快照資料表數 | 20 |
| Supabase 與原始快照完整列內容 | 20 表完全一致 |
| PK、FK、unique、indexes、sequences | 通過 |
| Alembic revision | `20261028_0002` |
| PostgreSQL 預先 Engine 測試 | dialect=`postgresql`、`SELECT 1=1` |
| 現行 SQLite 是否有 Supabase 缺少的表 | 無 |
| 現行 SQLite 是否有 Supabase 缺少的列 | 無 |
| `audit_logs.id=19` | 依授權保留於 Supabase |

原始 20 表快照：

- 路徑：`C:/Users/sinyu/Documents/Codex/MeowHouseBackups/pre_supabase_final_20261029_001011.db`
- SHA-256：`4793D7744266051A74F2D52C1C973D998DDBF59CC09AA1FCE2306F06CED2B3C1`
- `PRAGMA integrity_check`：`ok`

Supabase 與此快照重新執行逐表驗證，20 張表的內容、日期時間、主鍵、外鍵、唯一性與自動編號序列均通過。

## 3. 現行 SQLite 子集驗證

切換前現行 `database/app.db` 為 16 表版本。所有現行 SQLite 資料都完整存在於 Supabase：

- 共同主鍵的欄位內容一致。
- 沒有 SQLite-only 資料表。
- 沒有 SQLite-only 資料列。
- Supabase 額外保留四張 IoT 表：`iot_devices`、`sensor_calibrations`、`sensor_readings`、`feeding_events`。
- Supabase 額外保留已核准的 `audit_logs.id=19`。

這不是無條件忽略 `audit_logs`；例外只精確套用於經調查核准的主鍵 `id=19`。

## 4. 最後 SQLite 備份

切換前再次使用 SQLite Backup API 建立一致性備份：

- 路徑：`C:/Users/sinyu/Documents/Codex/MeowHouseBackups/cutover_final_20261029_003118.db`
- 大小：188,416 bytes
- SHA-256：`C48099DEEF4B9658B9A142563CB15E3BBB2CBAB7ABC0596B635BAE243D302067`
- `PRAGMA integrity_check`：`ok`

較早的 `pre_cutover_20261029_001903.db`、原始 20 表快照及正式專案中的 `database/app.db` 也都保留，未刪除或覆蓋。

## 5. `.env` 安全切換

切換前 `.env` 已備份至專案外：

- `C:/Users/sinyu/Documents/Codex/MeowHouseBackups/env_pre_cutover_20261029_003209.bak`

此備份不位於專案 Git 目錄，不應上傳或公開分享。

切換結果：

| 設定 | 結果 |
|---|---|
| `DATABASE_URL` | 已設定為既有 `SUPABASE_DATABASE_URL` 的值 |
| `AUTO_CREATE_SCHEMA` | `false` |
| 實際 SQLAlchemy dialect | `postgresql` |
| SQLite fallback | 未發生 |
| 連線資訊輸出 | 未輸出 |

`app/config.py` 只有在 `DATABASE_URL` 缺少時才會使用 SQLite 預設值；連線 PostgreSQL 失敗時不會靜默切回 SQLite。專案中未找到啟動時以舊資料庫檔覆蓋 `app.db` 的機制。

## 6. 切換後 FastAPI 驗證

### 6.1 真實 HTTP Server

使用本機 `127.0.0.1:8765` 暫時啟動 Uvicorn：

| 路徑 | HTTP 結果 |
|---|---:|
| `/login` | 200 |
| `/`（未登入） | 303，導向登入頁 |
| `/health` | 200 |
| `/docs` | 200 |

驗證完成後已停止臨時伺服器；目前沒有殘留的 Python／Uvicorn 程序或監聽連接埠。

### 6.2 三角色唯讀 smoke test

為避免正式 Supabase 新增測試稽核，沒有呼叫會寫入 `LOGIN` 的登入端點；測試使用依現有 SessionMiddleware 規格產生的簽章 Session，並只執行 GET。

通過項目：

- OWNER：首頁、貓咪資料、活動頁、分析頁、提醒頁。
- OWNER API：貓咪、活動摘要、最近活動、寄養狀態、提醒、寄養日記、Monitor 狀態。
- CAREGIVER：工作台、照護任務、照護紀錄、貓咪、提醒、IoT 裝置／量測、攝食事件。
- ADMIN：管理首頁、總覽、會員、裝置、設定、系統任務、稽核紀錄、IoT 裝置／量測、攝食事件。
- OWNER 存取 IoT 管理查詢回傳 403，符合既有角色權限設計。
- CAREGIVER 與 ADMIN 的 IoT 查詢回傳 200。

結果：`ROLE_AWARE_READONLY_SMOKE=PASS`。

測試過程只有一項既有套件警告：Starlette `TestClient` 對目前 httpx 相容層提出 deprecation warning；不影響本次功能結果。

## 7. IoT 四表驗證

| 資料表 | 唯讀查詢結果 |
|---|---:|
| `iot_devices` | 1 |
| `sensor_calibrations` | 0 |
| `sensor_readings` | 0 |
| `feeding_events` | 0 |

四張表均可透過 PostgreSQL ORM 查詢；CAREGIVER／ADMIN API 亦正常回應。沒有上傳假感測資料或建立假事件。

## 8. 正式資料未受測試污染

切換後測試前後比較所有 20 張應用資料表：

- `ROW_COUNTS_UNCHANGED=True`
- 變動資料表：無
- `audit_logs` 仍為 19 筆
- 其餘資料表筆數與搬移完成時一致

未執行會修改正式資料的完整測試套件。

## 9. 遇到的狀況與處理

第一次角色 smoke test 將 OWNER 存取 IoT 管理 API 的 403 當成失敗。檢查路由權限後確認這是正確的既有授權規則，遂以角色預期狀態重新執行；第二次測試全部通過，且兩次測試前後資料筆數都沒有變化。

沒有發生資料庫連線錯誤、Schema 錯誤或資料寫入，因此未執行 `.env` 回復。原 `.env` 備份與所有 SQLite 回復來源均保留。

## 10. 最終狀態

- [x] 正式 `DATABASE_URL` 已切換至 Supabase PostgreSQL。
- [x] `AUTO_CREATE_SCHEMA=false`。
- [x] SQLAlchemy Engine 實際 dialect 為 `postgresql`。
- [x] FastAPI 真實 HTTP 啟動成功。
- [x] OWNER、CAREGIVER、ADMIN 唯讀功能通過。
- [x] 貓咪、活動、提醒、照護、管理員、Dashboard API 通過。
- [x] IoT 四表與相關 API 可查詢。
- [x] 正式資料筆數未被測試改變。
- [x] 原始 SQLite、現行 SQLite、歷史備份與 `.env` 備份均保留。
- [x] UI、YOLO、ROI、影片與模型權重未修改。

## 11. ESP32 + HX711 準備狀態

**後端資料層與查詢層已準備完成，可進入 ESP32 + HX711 整合。**

已具備：

- `iot_devices`
- `sensor_calibrations`
- `sensor_readings`
- `feeding_events`
- 裝置／量測／攝食事件查詢 API
- 裝置上傳端點與既有裝置驗證設計

仍待硬體階段完成：

- 真實 ESP32 裝置金鑰配置
- HX711 與荷重元校正
- 網路斷線重送及去重實機驗證
- 真實重量資料品質門檻調整
- 攝食事件規則的實機驗收

本次切換完成後，啟動原本網站即會使用 Supabase；本報告不包含任何密碼、Token 或完整連線字串。
