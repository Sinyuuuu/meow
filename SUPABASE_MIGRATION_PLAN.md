# Meow一下 Supabase PostgreSQL 安全搬移計畫

> 日期：2026-10-28  
> 本階段範圍：本機備份、Schema／Migration 準備、唯讀檢查與本機測試。  
> 本階段沒有對 Supabase 執行 DDL、DML、Migration、搬移或正式切換。

## 1. 執行結論

桌面正式專案已具備可重複驗證的 Migration 與搬移流程，並已完成 Supabase 唯讀 Gate。遠端 `SELECT 1` 成功，`public` Schema 目前是 0 張資料表。正式寫入仍需先確認 Supabase 回復方式並取得明確授權，本階段沒有執行遠端 Migration 或資料搬移。

- 桌面正式專案以 SQLAlchemy + psycopg 執行 `SELECT 1`，結果為 1。
- 唯讀查詢確認 Supabase `public` Schema 目前有 0 張 base table。
- 專案虛擬環境已補齊 `psycopg 3.3.6`、binary driver 與 Alembic 1.20.1，未更改 `DATABASE_URL`。
- 原 SQLite 仍是正式使用來源，完整性為 `ok`，檔案雜湊未改變。
- 新 Alembic 鏈可從空白資料庫建立 16 張舊表，再建立 4 張 IoT 表；也能安全辨識已存在的完整 16 表。
- 搬移腳本已改成「Alembic 必須先完成」，不再自行 `create_all()` 或自行 stamp Migration。

## 2. Supabase 目前有哪些資料表

### 本次實際檢查結果

| 項目 | 結果 |
|---|---|
| 桌面正式專案 `SELECT 1` | 成功，結果 1 |
| 桌面正式專案 `.env` 解析 | `SUPABASE_DATABASE_URL` 非空；未輸出內容 |
| 本次遠端唯讀查詢 | 成功；交易設為 READ ONLY 並 rollback |
| `public` 資料表名稱與數量 | 0 張 |

因此目前可判定 Supabase `public` Schema 沒有應用資料表衝突。安全工具 `scripts/check_supabase_readonly.py` 只會：

1. 以 SQLAlchemy + psycopg 建立獨立連線。
2. 在交易中執行 `SET TRANSACTION READ ONLY`。
3. 執行 `SELECT 1`。
4. 查詢 `information_schema.tables` 的 `public` base tables。
5. 對現有表執行 `COUNT(*)`。
6. Rollback 交易，且不輸出 URL、主機、帳號或密碼。

設定可被目前工作區讀取後，執行：

```powershell
.\.venv\Scripts\python.exe scripts\check_supabase_readonly.py
```

只有此工具回報 `Status: OK` 並列出遠端表後，才能填入本節的正式表清單。

## 3. 原本 16 張資料表與 PostgreSQL 相容性

### 相容性驗證摘要

- 16 張表全部成功用 SQLAlchemy PostgreSQL dialect 編譯。
- 共成功編譯 24 個索引。
- 共 17 條外鍵關聯。
- 每張表都有主鍵，共 16 個主鍵。
- 12 張表在 PostgreSQL 會使用自動編號／sequence：`system_tasks`、`users`、`audit_logs`、`pets`、`activity_records`、`alerts`、`care_logs`、`care_tasks`、`cat_houses`、`pet_access`、`boarding_orders`、`camera_devices`。
- 共 3 組主要唯一性規則：`users.email`、`cat_houses.room_number`、`pet_access(user_id, pet_id)`。
- SQLite boolean 會在搬移時正規化成 Python boolean；無時區的舊 datetime 會標記為 UTC 後寫入 PostgreSQL。
- 搬移後會以 `pg_get_serial_sequence()` 與 `setval()` 校正 sequence，避免保留舊 ID 後下一筆新增發生衝突。

### 16 張舊表

| 資料表 | 主鍵 | 主要外鍵／唯一性 | PostgreSQL 判定 |
|---|---|---|---|
| `users` | `id` | `email` unique | 相容 |
| `user_states` | `user_id` | `user_id → users.id` | 相容；共用 PK，不建立獨立 sequence |
| `pets` | `id` | `owner_id → users.id` | 相容 |
| `pet_access` | `id` | user、pet 外鍵；組合 unique | 相容 |
| `cat_houses` | `id` | `current_pet_id → pets.id`；房號 unique | 相容 |
| `boarding_orders` | `id` | pet、cat_house 外鍵 | 相容 |
| `care_tasks` | `id` | `pet_id → pets.id` | 相容 |
| `care_logs` | `id` | pet、caregiver 外鍵 | 相容 |
| `camera_devices` | `id` | `cat_house_id → cat_houses.id` | 相容 |
| `device_heartbeats` | `camera_device_id` | `→ camera_devices.id` | 相容；共用 PK |
| `activity_records` | `id` | `pet_id → pets.id`；pet/time 複合索引 | 相容 |
| `alerts` | `id` | `pet_id → pets.id` | 相容 |
| `alert_handling` | `alert_id` | alert、handled_by 外鍵 | 相容；共用 PK |
| `audit_logs` | `id` | `actor_id → users.id` 可空 | 相容 |
| `system_settings` | `key` | 字串主鍵 | 相容，不需要 sequence |
| `system_tasks` | `id` | status 索引 | 相容 |

目前 Model 另外包含 4 張 IoT 表：`iot_devices`、`sensor_calibrations`、`sensor_readings`、`feeding_events`。它們由後續 `0002` Revision 建立，不混入舊 16 表 bootstrap。

## 4. Migration 設計

### Alembic Revision 鏈

| Revision | 檔案 | 行為 |
|---|---|---|
| `20261028_0000` | `migrations/versions/20261028_0000_create_existing_schema.py` | 空白時建立舊 16 表；完整存在時不動；部分存在時拒絕；不建立 Demo 資料 |
| `20261028_0001` | `migrations/versions/20261028_0001_baseline_existing_schema.py` | 再次驗證 16 表完整，缺表即停止 |
| `20261028_0002` | `migrations/versions/20261028_0002_add_iot_foundation.py` | 新增 IoT 裝置、校正、讀值與攝食事件 4 表 |

`0000` 有固定的 16 表與欄位 manifest，若未來 Model 欄位改變，會要求新增 Revision，不會悄悄用不同結構重建舊版本。所有 baseline downgrade 都故意不刪除舊 16 表，避免把匯入資料當成可自動回滾的測試資料。

### 已完成的本機 Migration 測試

1. **完全空白 SQLite 複本**：成功依序執行 `0000 → 0001 → 0002`，得到 20 張 Model 表及 `alembic_version`。
2. **既有正式 SQLite 複本**：`0000` 不動原 16 表，`0001` 通過，`0002` 新增四表；共同資料表筆數全部一致。
3. **只存在 `users` 的部分 Schema**：Migration 正確拒絕並列出缺表，沒有繼續建立混合 Schema。
4. **Alembic head**：`20261028_0002`。

## 5. SQLite 原始資料庫與備份

### 原始資料庫狀態

- 路徑：`C:/Users/sinyu/Documents/Codex/MeowHouseData/app.db`
- 讀取方式：SQLite URI `mode=ro`。
- `PRAGMA integrity_check`：`ok`。
- 資料表數量：16。

| 表 | 筆數 |
|---|---:|
| `activity_records` | 9 |
| `alert_handling` | 0 |
| `alerts` | 1 |
| `audit_logs` | 18 |
| `boarding_orders` | 1 |
| `camera_devices` | 1 |
| `care_logs` | 0 |
| `care_tasks` | 5 |
| `cat_houses` | 1 |
| `device_heartbeats` | 1 |
| `pet_access` | 1 |
| `pets` | 1 |
| `system_settings` | 2 |
| `system_tasks` | 3 |
| `user_states` | 3 |
| `users` | 3 |

### 本階段一致性備份

- 使用 `sqlite3.Connection.backup()`，會包含已提交的 WAL 內容，不是單純複製正在使用的 DB 檔。
- 備份：`C:/Users/sinyu/Documents/Codex/MeowHouseBackups/pre_supabase_stage2_20261028_020632.db`
- SHA-256：`C48099DEEF4B9658B9A142563CB15E3BBB2CBAB7ABC0596B635BAE243D302067`
- 備份雜湊與原資料庫一致。

再次建立備份的安全指令：

```powershell
.\.venv\Scripts\python.exe scripts\database_admin.py backup `
  --destination C:\Users\sinyu\Documents\Codex\MeowHouseBackups\pre_migration_<timestamp>.db
```

不得覆蓋既有備份；腳本遇到同名檔會拒絕。

## 6. 搬移腳本執行條件

`scripts/migrate_sqlite_to_supabase.py` 現在必須同時符合：

1. `SUPABASE_DATABASE_URL` 是 PostgreSQL，database 名稱為 `postgres`，並使用 SSL。
2. 遠端連線先通過 `SELECT 1`。
3. Alembic 已建立目前全部 20 張 Model 表；缺少任一表即停止。
4. 20 張目標應用表全部是 0 筆；任一表有資料即停止。
5. SQLite 來源檔存在且可讀。
6. SQLite 至少有舊 16 表；尚未存在的 4 張 IoT 表會在目標保持空白。
7. 插入依 SQLAlchemy 外鍵順序進行，整批資料在一個 PostgreSQL transaction 中處理。
8. 插入後校正 integer sequence，再比對所有共同表筆數。

腳本不再執行 `Base.metadata.create_all()`，也不再用 `alembic stamp` 假裝遠端已完成 Migration。Schema 與資料搬移已分成兩個可分別驗證的步驟。

## 7. 正式建立資料表與搬移資料的操作

以下是**取得明確遠端寫入授權後**才可執行的 Runbook；本階段沒有執行。

### A. 搬移前唯讀檢查

```powershell
.\.venv\Scripts\python.exe scripts\check_supabase_readonly.py
```

停止條件：

- 無法連線或認證失敗。
- `public` 已出現未知應用表。
- 任一 Meow 應用表有資料。
- 無法先取得 Supabase 備份／可回復點或匯出目前 Schema。

### B. 建立第二份最新 SQLite 備份

停止網站寫入或選擇維護時段，再使用 Backup API 建立新檔並執行 integrity check。記錄檔案大小與 SHA-256。

### C. 建立 Supabase Schema

只在確認目標沒有衝突後，暫時把 Migration 連線放在目前 PowerShell process，不修改正式 `DATABASE_URL`：

```powershell
$env:ALEMBIC_DATABASE_URL = $env:SUPABASE_DATABASE_URL
.\.venv\Scripts\python.exe -m alembic upgrade head
Remove-Item Env:ALEMBIC_DATABASE_URL
```

再執行唯讀工具，預期得到 20 張空應用表與 `alembic_version`。

### D. 搬移資料

```powershell
.\.venv\Scripts\python.exe scripts\migrate_sqlite_to_supabase.py `
  --source C:\Users\sinyu\Documents\Codex\MeowHouseBackups\pre_migration_<timestamp>.db
```

腳本會自行檢查空表、外鍵順序、sequence 與筆數。任何失敗都必須保留完整錯誤紀錄，但不得記錄連線字串。

### E. 搬移後驗證

1. 再執行 `scripts/check_supabase_readonly.py`。
2. 比對本報告的 16 表筆數；IoT 四表若來源沒有則應為 0。
3. 驗證 `alembic current` 為 `20261028_0002`。
4. 抽查外鍵 orphan 數量必須為 0。
5. 抽查 `users.email`、房號與 `pet_access` 唯一性。
6. 驗證 12 個 sequence 的 next value 大於目前最大 ID。
7. 先保持網站使用 SQLite，不立刻切換。

### F. 正式切換（另一個明確授權階段）

只有搬移驗證全部通過後，才安排維護時段修改 `DATABASE_URL`。正式 PostgreSQL 環境必須設定 `AUTO_CREATE_SCHEMA=false`，避免啟動時 `create_all()` 繞過 Alembic。

## 8. 驗證與測試結果

| 測試 | 結果 |
|---|---|
| SQLite integrity check | 通過 |
| SQLite 16 表唯讀筆數 | 通過 |
| 16 表 PostgreSQL DDL compile | 通過 |
| 24 個 PostgreSQL index compile | 通過 |
| 空白 DB Migration | 通過 |
| 既有 DB Migration 與筆數比對 | 通過 |
| 部分 Schema 拒絕 | 通過 |
| FastAPI／ORM／IoT 全套回歸 | `22 passed, 2 warnings in 5.09s` |
| Supabase 本次唯讀表清單 | 通過；`SELECT 1 = 1`，`public tables = 0` |

兩個 Warning 是既有 Starlette TestClient 對 HTTPX／AnyIO 的棄用提示，不是功能失敗。本機測試全部使用 SQLite 複本，沒有修改正式 SQLite 或 Supabase。

## 9. 回復方案

### 尚未切換網站時

- 最安全的回復就是不修改 `DATABASE_URL`；網站繼續使用原 SQLite。
- Migration 或搬移若失敗，停止後保留 SQLite 與備份，遠端保持隔離，不嘗試以未審核指令清除。
- 資料插入在 PostgreSQL transaction 中；中途錯誤應 rollback 該批資料。

### Schema 已建立但尚未搬資料時

- 不自動執行破壞性 downgrade。
- 先記錄遠端 Revision、表清單及備份，再決定是否保留空 Schema 或經另一次明確授權移除。

### 已搬資料但尚未切換時

- SQLite 仍是正式來源，使用者服務不受遠端搬移結果影響。
- 若筆數或關聯驗證失敗，不切換；重新建立新的空白 Supabase 專案或經備份後進行受控清理，再重新搬移。

### 未來已切換後

- 立即回復方式是把 `DATABASE_URL` 改回已保留的 SQLite 路徑並重新啟動服務。
- 切換後若兩邊都產生新寫入，不可直接覆蓋；必須先決定資料權威來源並做差異合併。

## 10. 是否可以安全進入正式搬移階段

目前判定：**技術上可進入正式搬移準備，但遠端寫入仍需 Supabase 回復方案與明確授權。**

進入正式搬移前必須全部滿足：

- [x] 桌面正式專案可安全載入非空的 `SUPABASE_DATABASE_URL`。
- [x] `scripts/check_supabase_readonly.py` 回報 `Status: OK`。
- [x] 已取得 Supabase `public` 表名與每表筆數；目前為 0 張表。
- [x] 已確認目標沒有未知／既有資料衝突。
- [ ] 已建立 Supabase 端備份、Schema 匯出或其他可回復點。
- [x] SQLite Backup API 備份與 SHA-256 已完成。
- [x] 16 表 PostgreSQL DDL、外鍵、索引、unique 與 sequence 已檢查。
- [x] Alembic 空白／既有／部分 Schema 測試已通過。
- [x] 搬移腳本會拒絕缺表或非空目標。
- [x] 完整本機回歸測試通過。

完成 Supabase 端備份／可回復點確認，並再次取得明確的「允許遠端 Migration／搬移」授權後，才可以進入正式寫入階段。

## 11. 本階段新增／修改檔案

- 新增 `migrations/versions/20261028_0000_create_existing_schema.py`
- 修改 `migrations/versions/20261028_0001_baseline_existing_schema.py`
- 修改 `migrations/README.md`
- 修改 `scripts/migrate_sqlite_to_supabase.py`
- 新增 `scripts/check_supabase_readonly.py`
- 新增本報告 `SUPABASE_MIGRATION_PLAN.md`

沒有修改 UI、正式 `DATABASE_URL`、正式 SQLite 資料或任何遠端 Supabase 物件。
