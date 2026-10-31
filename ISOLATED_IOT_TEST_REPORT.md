# CatSense AI — ESP32 重量資料隔離測試報告

> 日期：2026-10-29（Asia/Taipei）  
> 結果：**隔離端對端測試通過；正式 Supabase 未寫入測試資料。**

## 1. 隔離保護

- 正式 `.env` 沒有修改。
- 正式 `DATABASE_URL` 仍為 Supabase，`AUTO_CREATE_SCHEMA=false`。
- 測試程序以 process environment 強制覆寫到獨立 SQLite。
- 隔離資料庫：`C:/Users/sinyu/Documents/Codex/MeowHouseBackups/esp32_step1_isolated_20261029_004000.db`。
- 測試裝置 UID：`TEST-ESP32-HX711-001`。
- 測試裝置原始金鑰未輸出；資料庫只保存 PBKDF2 hash。
- 隔離 Uvicorn 使用 `127.0.0.1:8766`，完成後已停止。

另外新增 `tests/conftest.py`：任何 `pytest` 執行都會在 `tests/.tmp/` 產生唯一 SQLite，避免正式 Supabase 被測試套件誤寫。

## 2. HTTP 端對端測試

### 正常重量上傳

使用 `scripts/simulate_esp32_weight.py` 上傳：

```text
100 g → 99 g → 97 g → 95 g → 90 g
```

結果：

- 5 次新資料回傳 HTTP 201。
- `sensor_readings` 共 5 筆。
- filtered weights 與輸入完全一致。
- `source=SIMULATOR` 且 `simulated=true`。
- 每筆 `quality=GOOD`。
- 時間依序增加且可解析。

### 無效裝置金鑰

- 回應：HTTP 401。
- 對應 sequence 在資料庫筆數：0。
- 金鑰未出現在程式輸出。

### 重複上傳

- 重播第三筆完全相同 payload。
- 回應：HTTP 200、`duplicate=true`。
- `sensor_readings` 仍只有 5 筆。
- 唯一 sequence 數仍為 5。

### 網路中斷與重送

- 第三筆第一次嘗試模擬 `NETWORK_ERROR`，沒有送出 HTTP。
- 第二次沿用相同 device UID、sequence、timestamp 與重量。
- 第二次回應 HTTP 201。
- 模擬器使用有限重試，沒有無限迴圈。

## 3. 資料完整性

| 檢查 | 結果 |
|---|---|
| sensor readings | 5 |
| unique sequences | 5 |
| weights | 100、99、97、95、90 g |
| timestamps strictly increasing | true |
| all source SIMULATOR | true |
| invalid-key row count | 0 |
| measurement audit logs | 5 |
| credential hash verification | true |

## 4. 攝食安全語意

第一個單調下降情境沒有穩定前後平台：

- activity evidence：0
- feeding event：0

另在同一隔離 DB 測試 `120.0、120.2、110.0、110.1 g` 穩定前後平台：

- activity evidence：0
- feeding event：1
- status：`CANDIDATE`
- `CONFIRMED` event：0

結果符合需求：沒有貓咪活動佐證時，不會把重量下降直接宣稱為確定進食。現有系統仍未把 FOOD ROI 活動自動加入 confidence；此項列為下一階段整合。

## 5. 專案回歸測試

新增 pytest 隔離設定後第一次執行遇到 Windows 沙箱 Temp 目錄無法建立 SQLite；修正為專案內已忽略版控的 `tests/.tmp/`。

第二次剩下一個舊測試依賴既有活動資料；已讓該測試在隔離 DB 建立自己的 ActivityRecord，不再依賴正式資料。

最終結果：

```text
22 passed, 1 warning
```

警告為既有 Starlette TestClient／httpx deprecation，不影響本階段功能結果。

## 6. 正式 Supabase 未污染證明

隔離測試後重新唯讀檢查正式 Supabase：

- `sensor_readings=0`
- `feeding_events=0`
- `iot_devices=1`
- `audit_logs=19`
- 其他既有資料表筆數未變。

因此測試重量、候選事件與測試稽核均只存在隔離 SQLite。

## 7. 尚未完成／未宣稱通過

- HX711、荷重元尚未到貨，未做實體讀值。
- 本機沒有 Arduino CLI 或 PlatformIO，`.ino` 尚未實際編譯。
- 尚未測試 ESP32 真實 Wi-Fi、NTP、NVS 與 TLS root CA。
- 尚未測試長時間斷線的持久 queue。
- 尚未建立重量監測專用 UI。
- 尚未將 YOLO FOOD ROI 活動與 feeding candidate 自動關聯。

以上項目不可標示為完成，應在硬體到貨後繼續驗收。

