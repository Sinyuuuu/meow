# Database migrations

- `20261028_0000` 是原本 16 張資料表的安全 bootstrap：完全空白時建立、完整存在時不動、部分存在時拒絕。
- `20261028_0001` 驗證 16 張既有資料表完整。
- `20261028_0002` 新增 IoT 四表。
- 既有資料庫：先備份，再執行 `alembic upgrade head`。baseline 驗證通過後才會建立新表。
- 空白資料庫可從 `0000` 開始完整建立 schema；Migration 不會寫入 Demo 資料。
- 遠端 Supabase 未經明確授權不得執行 migration。
