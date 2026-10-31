# 桌面正式專案安全整合紀錄

> 整合日期：2026-10-28  
> 正式專案：`C:/Users/sinyu/OneDrive/桌面/meow_house_integrated_v3_20261023`

## 結果

- 已將 Supabase、Alembic、IoT Model、重量 API、模擬器與測試整合到桌面正式專案。
- 未覆蓋 `.env`、正式 SQLite、影片、ROI、YOLO 權重、模板、CSS 或 JavaScript。
- 桌面 `.env` 的 `SUPABASE_DATABASE_URL` 可被安全載入；`DATABASE_URL` 仍保持 SQLite。
- Supabase 唯讀驗證：`SELECT 1 = 1`，`public` base tables 為 0。
- 沒有執行遠端 Migration、建表、資料搬移或正式資料庫切換。

## 整合前備份

- 程式碼：`C:/Users/sinyu/Documents/Codex/MeowHouseBackups/desktop_project_premerge_code_20261028_023629.zip`
- 程式 SHA-256：`BC805FD6EE45EC83E07C17276FBAB73F868F1E6973DC345770D05C2FEDC43E4F`
- SQLite：`C:/Users/sinyu/Documents/Codex/MeowHouseBackups/desktop_project_premerge_db_20261028_023629.db`
- SQLite SHA-256：`C48099DEEF4B9658B9A142563CB15E3BBB2CBAB7ABC0596B635BAE243D302067`
- SQLite 備份由 `sqlite3.Connection.backup()` 建立並通過 integrity check。

## 本機驗證

- Migration 僅在 SQLite 備份複本執行。
- Alembic：`20261028_0002 (head)`。
- 預期 Model 表 20 張，加上 `alembic_version` 共 21 張。
- 既有 16 張表搬移前後筆數一致。
- 回歸測試：`22 passed, 1 warning in 6.87s`。
- Warning 是既有 Starlette TestClient／HTTPX 棄用提示，不是功能失敗。

## 待授權操作

在確認 Supabase 可回復方式前，不執行遠端寫入。下一階段需另行明確授權：

1. 建立或確認 Supabase 備份／回復點。
2. 遠端執行 `alembic upgrade head`。
3. 再次唯讀驗證 20 張空表。
4. 從 SQLite 一致性備份搬移資料並比對筆數。
5. 保持網站使用 SQLite，驗證完成後才另行決定是否切換。
