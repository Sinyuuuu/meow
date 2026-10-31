# CatSense AI／Meow一下 audit_logs 差異調查

> 調查日期：2026-10-29（Asia/Taipei）  
> 調查方式：Supabase 唯讀交易、SQLite 唯讀查詢、程式碼靜態追蹤  
> 結果：**`audit_logs.id=19` 可確認為原始搬移來源中已存在的登入稽核，不是 Supabase 切換後新增。**

## 1. 安全界線

- 沒有修改、刪除或新增 SQLite／Supabase 資料。
- 沒有刪除 `audit_logs.id=19`。
- 沒有修改 `DATABASE_URL` 或 `AUTO_CREATE_SCHEMA`。
- 沒有啟動正式切換或網站。
- 沒有輸出資料庫密碼、Token、完整連線字串或 `detail` 內容。
- 所有 Supabase 查詢均在 `SET TRANSACTION READ ONLY` 交易內完成並 rollback。

## 2. audit_logs.id=19 安全欄位

| 欄位 | 結果 |
|---|---|
| `id` | `19` |
| 建立時間（UTC） | `2026-10-28 16:01:46.556476+00:00` |
| 建立時間（Asia/Taipei） | `2026-10-29 00:01:46.556476+08:00` |
| 動作類型 | `LOGIN` |
| `actor_id` | `1` |
| 使用者外鍵 | 有效，`users.id=1` 存在 |
| `detail` | 有值；僅在資料庫內比對模板，未輸出或記錄內容 |
| Alembic revision | `20261028_0002` |

`detail` 僅以資料庫布林比較確認符合登入端點的固定 `role={user.role}` 模板；本報告不保存其實際文字。

## 3. 可能產生來源

### 3.1 程式碼路徑

登入成功時，`app/api/auth.py:29` 執行：

```python
audit(db, user.id, "LOGIN", f"role={user.role}")
```

接著在 `app/api/auth.py:30` commit。`app/services/governance_service.py:15` 至 `17` 負責建立 `AuditLog`；資料模型位於 `app/models/governance.py:52`。

### 3.2 證據

- 動作類型為 `LOGIN`。
- `actor_id=1` 的使用者外鍵有效。
- `detail` 與登入端點固定模板比對結果為 true，但未輸出內容。
- `id=19` 已存在於正式搬移來源：
  `C:/Users/sinyu/Documents/Codex/MeowHouseBackups/pre_supabase_final_20261029_001011.db`。
- 原始 SQLite 搬移來源與 Supabase 的 `id=19` 所有欄位完全一致。
- 該事件建立於正式搬移來源備份之前，不是搬移完成後由 Supabase 產生。

### 3.3 可信程度

**高。**

可確認它是原始 SQLite 中的一次成功登入稽核，並由資料搬移程序保留至 Supabase。無法只靠現有資料判斷當時登入者是否由人員手動操作或由 smoke test 觸發，但兩者都會使用相同的正式登入端點；沒有證據顯示它是偽造、孤兒或資料庫異常產生的紀錄。

## 4. 關聯、序列與系統影響

| 檢查 | 結果 |
|---|---|
| `audit_logs.actor_id -> users.id` | 有效 |
| 指向 `audit_logs` 的其他外鍵 | 0 個 |
| `audit_logs` 最大 ID | 19 |
| `audit_logs_id_seq.last_value` | 19 |
| Sequence `is_called` | true；下一筆可安全使用 20 |
| 對權限判斷的影響 | 無；登入權限由 `users`、`user_states` 等資料判斷 |
| 可見行為 | 管理員稽核頁多顯示一筆歷史登入紀錄 |

保留此紀錄不會改變角色、會員權限、貓咪關聯、活動紀錄或 IoT 裝置關聯。

## 5. SQLite 再確認與重要額外發現

最新 SQLite 與切換前備份均沒有 `audit_logs.id=19`：

- 現行 `database/app.db`：`audit_logs` 18 筆，沒有 `id=19`。
- `pre_cutover_20261029_001903.db`：`audit_logs` 18 筆，沒有 `id=19`。

但是，完整掃描另發現現行 SQLite 已不再是原始搬移時的 20 表版本：

| 資料來源 | 應用資料表數 | `audit_logs` | IoT 四表 |
|---|---:|---:|---|
| 原始搬移快照 `pre_supabase_final_20261029_001011.db` | 20 | 19 | 存在 |
| Supabase | 20 | 19 | 存在 |
| 現行 SQLite `database/app.db` | 16 | 18 | 不存在 |
| 最新切換前備份 `pre_cutover_20261029_001903.db` | 16 | 18 | 不存在 |

現行 SQLite 缺少：

- `iot_devices`
- `sensor_calibrations`
- `sensor_readings`
- `feeding_events`

Supabase 已再次與原始 20 表搬移快照逐表驗證：20 張資料表、完整列內容、時間、PK、FK、unique 與 sequences 全部一致。

現行 SQLite 的檔案大小與修改時間也顯示它在原始搬移快照建立後被改寫或替換；目前沒有足夠證據確認是人工還原、舊版啟動流程或其他外部檔案操作。正常的 `init_db()` 使用 `create_all()`，不會刪除既有 IoT 表或稽核列；專案內也未發現自動用舊資料庫覆蓋正式 `app.db` 的啟動程式碼。

因此，先前「其他 19 張表與最新 SQLite 完全一致」需要更正：在雙方都存在的 16 張表中，除 `audit_logs.id=19` 外共同資料一致；但最新 SQLite 本身缺少四張 IoT 表。

## 6. 寫入程序檢查

| 檢查 | 結果 |
|---|---|
| 本機 Python／Uvicorn 程序 | 0 |
| 8000、8010、8080 監聽程序 | 0 |
| SQLite `BEGIN IMMEDIATE` | 成功，可取得寫入鎖 |
| Supabase 其他 client sessions | 7 個 idle pooler sessions |
| Supabase 其他 active sessions | 0 |

調查時未發現正在寫入 SQLite 或 Supabase 的應用程序。Idle pooler sessions 不代表正在執行交易。

## 7. 保留 id=19 的風險

整體風險：**低。**

- 該列是 append-only 稽核資料，不參與授權決策。
- 外鍵有效且沒有下游資料依賴。
- Sequence 已正確位於 19，不會造成下一筆主鍵衝突。
- 它與原始正式搬移快照完全一致，刪除反而會破壞歷史完整性。
- 唯一可見差異是管理員稽核頁多顯示一次歷史登入。

主要風險不是保留 `id=19`，而是把目前已退回 16 表的 SQLite 錯誤視為最完整資料來源。

## 8. 「允許核准額外稽核紀錄」策略評估

### 判定

**可以採用，但必須是明確、限縮的核准規則，不能無條件忽略整張 `audit_logs`。**

可接受規則：

1. 最新 SQLite 所有仍存在的列都必須在 Supabase 中逐欄完全一致。
2. `audit_logs` 只允許 Supabase 額外存在主鍵 `id=19`。
3. 額外列必須符合本報告記錄的建立時間、`LOGIN` 動作、`actor_id=1` 與有效外鍵。
4. 共同主鍵不得有任何內容差異。
5. 不允許其他未核准的額外、缺少或變更列。
6. 驗證仍須檢查整張 `audit_logs`，只對已核准的單一主鍵做精確例外。

不過，由於目前 SQLite 缺少四張 IoT 表，更可靠的正式切換基準是原始 20 表搬移快照。以該快照為基準時，Supabase 並沒有額外紀錄，而是 20 張表全部精確一致。

## 9. 建議正式切換步驟

1. 由使用者明確核准：以原始 20 表搬移快照與 Supabase 作為完整資料基準，保留 `audit_logs.id=19`。
2. 保留目前 16 表 SQLite 的最新備份，不刪除或覆蓋。
3. 進入維護狀態，再確認沒有本機網站程序及 Supabase active transaction。
4. 再次執行 Supabase 對原始 20 表搬移快照的精確逐表驗證。
5. 另外驗證目前 SQLite 所有共同資料均包含於 Supabase，且沒有 SQLite-only 新資料。
6. 安全備份 `.env`。
7. 將 `DATABASE_URL` 設為現有 `SUPABASE_DATABASE_URL`，設定 `AUTO_CREATE_SCHEMA=false`；不得輸出連線字串。
8. 啟動 FastAPI，確認實際 dialect 為 PostgreSQL，禁止 SQLite fallback。
9. 執行不寫入測試資料的首頁、角色頁、貓咪、活動、IoT、Dashboard 查詢 smoke test。
10. 若要執行真實登入，將新增的 `LOGIN` 稽核視為正式操作並記錄；切換後不得在不比對新增資料的情況下直接回退 SQLite。

## 10. 最終建議

建議保留 `audit_logs.id=19`，可信度高、資料風險低，並將它列為經核准的歷史登入稽核。

但下一次切換不應只把它當成「Supabase 多一筆」；更準確的情況是 Supabase 完整保留了原始 20 表搬移來源，而目前 SQLite 已退回較舊的 16 表狀態。正式切換應在使用者明確核准 Supabase／原始搬移快照為完整資料基準後再執行。
