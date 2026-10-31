# CatSense AI／Meow一下 Supabase 正式資料庫搬移結果

> 搬移日期：2026-10-29（Asia/Taipei）  
> 正式專案：`C:/Users/sinyu/OneDrive/桌面/meow_house_integrated_v3_20261023`  
> 結果：**Migration、資料搬移與驗證成功；正式網站尚未切換。**

## 1. 安全界線

- 原本 `DATABASE_URL` 仍指向 SQLite，沒有切換成 Supabase。
- 沒有對原 SQLite 執行建表、更新、刪除或覆蓋。
- 沒有使用 `DROP`、`TRUNCATE` 或清除 Supabase 既有資料。
- Supabase 搬移前 `public` Schema 為 0 張表；未發現衝突後才開始建表。
- 所有連線字串、帳號、密碼與 Token 均未寫入輸出或本報告。
- UI、YOLO、ROI、影片、模型權重及其他無關功能均未修改。

## 2. 搬移來源與回復資料

本次使用 SQLite Backup API 建立的一致性快照作為唯一搬移來源：

- 檔案：`C:/Users/sinyu/Documents/Codex/MeowHouseBackups/pre_supabase_final_20261029_001011.db`
- SHA-256：`4793D7744266051A74F2D52C1C973D998DDBF59CC09AA1FCE2306F06CED2B3C1`
- SQLite `PRAGMA integrity_check`：`ok`
- 來源資料表：20 張

搬移完成後再次透過 SQLite Backup API 建立線上快照：

- 檔案：`C:/Users/sinyu/Documents/Codex/MeowHouseBackups/post_migration_live_check_20261029_001406.db`
- SHA-256：`4793D7744266051A74F2D52C1C973D998DDBF59CC09AA1FCE2306F06CED2B3C1`
- 與搬移來源雜湊相同，20 張表筆數差異為 0。

因此原 SQLite 在整個遠端搬移期間沒有新增、刪除或變更資料，可繼續作為立即回復來源。

## 3. Supabase 搬移前檢查

| 項目 | 結果 |
|---|---|
| PostgreSQL 連線 | 成功 |
| `SELECT 1` | 1 |
| `public` base tables | 0 |
| 既有應用資料 | 無 |
| SQLite 完整性 | `ok` |
| SQLAlchemy PostgreSQL DDL compile | 20 張表通過 |
| Model indexes | 43 個宣告索引通過 compile |
| Model foreign keys | 28 條通過檢查 |

## 4. 執行的 Migration

Alembic 使用 PostgreSQL transactional DDL 依序完成：

| Revision | 作用 | 結果 |
|---|---|---|
| `20261028_0000` | 建立原本 16 張應用資料表 | 成功 |
| `20261028_0001` | 驗證 16 表 baseline | 成功 |
| `20261028_0002` | 建立 4 張 IoT／重量／攝食資料表 | 成功 |

目前 Supabase `alembic_version`：`20261028_0002`。

## 5. 建立的資料庫物件

### 資料表

共 21 張 `public` base tables：20 張應用表加 1 張 `alembic_version`。

1. `users`
2. `user_states`
3. `pets`
4. `pet_access`
5. `cat_houses`
6. `boarding_orders`
7. `care_tasks`
8. `care_logs`
9. `camera_devices`
10. `device_heartbeats`
11. `activity_records`
12. `alerts`
13. `alert_handling`
14. `audit_logs`
15. `system_settings`
16. `system_tasks`
17. `iot_devices`
18. `sensor_calibrations`
19. `sensor_readings`
20. `feeding_events`
21. `alembic_version`

### Schema 統計

| 物件 | 數量 |
|---|---:|
| Public tables | 21 |
| Indexes（含 PK／unique 所需索引） | 68 |
| PostgreSQL sequences | 16 |
| Foreign-key constraints | 28 |
| Unique constraints | 4 |
| Primary-key constraints | 21 |

## 6. 搬移資料筆數

| 資料表 | SQLite | Supabase | 完整列內容 |
|---|---:|---:|---|
| `system_settings` | 2 | 2 | 一致 |
| `system_tasks` | 3 | 3 | 一致 |
| `users` | 3 | 3 | 一致 |
| `audit_logs` | 19 | 19 | 一致 |
| `pets` | 1 | 1 | 一致 |
| `user_states` | 3 | 3 | 一致 |
| `activity_records` | 9 | 9 | 一致 |
| `alerts` | 1 | 1 | 一致 |
| `care_logs` | 0 | 0 | 一致 |
| `care_tasks` | 5 | 5 | 一致 |
| `cat_houses` | 1 | 1 | 一致 |
| `pet_access` | 1 | 1 | 一致 |
| `alert_handling` | 0 | 0 | 一致 |
| `boarding_orders` | 1 | 1 | 一致 |
| `camera_devices` | 1 | 1 | 一致 |
| `iot_devices` | 1 | 1 | 一致 |
| `device_heartbeats` | 1 | 1 | 一致 |
| `sensor_calibrations` | 0 | 0 | 一致 |
| `sensor_readings` | 0 | 0 | 一致 |
| `feeding_events` | 0 | 0 | 一致 |

驗證工具不只比較筆數，也逐列比較所有欄位；SQLite naive datetime 以 UTC 正規化後與 PostgreSQL 時間內容一致。

## 7. 關聯、約束與 Sequence 驗證

唯讀後驗證工具：`scripts/verify_supabase_migration.py`

驗證結果：

- 20 張應用表完整列內容全部一致。
- 所有主鍵值集合保留，原 ID 沒有重新編號。
- 28 條 Foreign Key 沒有 orphan row。
- 所有 declared unique constraint／unique index 沒有重複群組。
- 16 個 PostgreSQL sequence 均未落後於對應資料表最大 ID。
- Alembic Revision 正確。
- 驗證交易使用 `SET TRANSACTION READ ONLY` 並 rollback。

最終狀態：

```text
Status: OK
Schema, rows, timestamps, keys, constraints, and sequences verified
```

## 8. 應用程式驗證

### Supabase 唯讀 ORM 煙霧測試

- SQLAlchemy ORM 可讀取 3 位使用者、1 隻貓與 9 筆活動資料。
- OWNER 密碼雜湊驗證成功；測試沒有輸出雜湊或個資。
- Owner → Pet → CatHouse → BoardingOrder 關聯正確。
- 測試交易為 READ ONLY，完成後 rollback。

結果：`SUPABASE_ORM_READONLY_SMOKE=OK`。

### 本機完整回歸

完整 FastAPI／ORM／AI／IoT 測試使用 SQLite 快照複本執行，避免測試資料污染 Supabase：

```text
22 passed, 1 warning in 4.12s
```

Warning 是既有 Starlette TestClient 對 HTTPX 的棄用提示，不是功能失敗。

## 9. 新增或調整的搬移工具

- `scripts/migrate_sqlite_to_supabase.py`
  - 不顯示連線字串或帳號。
  - 缺表或目標非空時拒絕執行。
  - 所有資料以單一 PostgreSQL transaction 搬移。
  - 搬移後校正 sequences 並比對筆數。
- `scripts/verify_supabase_migration.py`
  - 唯讀比較完整列內容、時間、PK、FK、unique 與 sequence。
  - 不輸出資料列、密碼或連線資訊。

## 10. 尚未執行與後續事項

- 尚未把正式 `DATABASE_URL` 切換到 Supabase。
- 尚未將 `AUTO_CREATE_SCHEMA` 設為 `false`；正式切換時必須一起設定。
- 未對 Supabase 執行會寫入測試資料的完整 Web/API 測試；已改用唯讀 ORM smoke，避免污染正式資料。
- `sensor_calibrations`、`sensor_readings`、`feeding_events` 目前是空表，需待 ESP32／HX711 或模擬器開始上傳。
- Supabase 平台層的 PITR／備份方案尚未在本次操作中設定；目前可由保留的 SQLite 快照重建。
- 切換前建議安排短暫維護時段，再做一次 SQLite Backup API 快照與 Supabase 唯讀筆數比對。

## 11. 是否具備安全切換條件

判定：**已具備受控切換的資料與 Schema 條件，但不應自動切換。**

已通過：

- [x] Supabase Schema 建立成功。
- [x] SQLite 資料完整搬移。
- [x] 完整列內容與時間一致。
- [x] PK、FK、unique 與 sequences 驗證通過。
- [x] Supabase ORM 唯讀驗證通過。
- [x] 22 項本機回歸測試通過。
- [x] 搬移期間 SQLite 沒有變化。
- [x] SQLite 備份與回復來源保留。
- [x] 正式 `DATABASE_URL` 仍為 SQLite。

切換時仍需：

1. 進入短暫維護時段，避免 SQLite 在最後比對後繼續產生新資料。
2. 再做一次最新 SQLite 快照與 Supabase 筆數／內容比對。
3. 將 `DATABASE_URL` 改為 Supabase URL，並設定 `AUTO_CREATE_SCHEMA=false`。
4. 啟動網站後執行登入、角色頁面與唯讀 Dashboard smoke test。
5. 若失敗，立即把 `DATABASE_URL` 改回 SQLite 並重新啟動。

本報告不代表已切換正式網站；正式切換必須是下一個明確授權的獨立步驟。
