# CatSense AI／Meow一下 — ESP32 智慧貓食碗整合計畫

> 階段：Step 1（無 HX711 實體硬體）  
> 原則：沿用現有 FastAPI、SQLAlchemy 與 IoT 四表；不建立第二套 API，不修改既有 UI、YOLO、ROI 或會員功能。

## 1. 現有上傳 API

### 1.1 路徑與 Method

- Method：`POST`
- 路徑：`/api/ingest/measurements`
- 實作：`app/api/ingest.py`
- 新資料成功：HTTP 201
- 重複資料：HTTP 200，回應 `duplicate=true`

### 1.2 Header

優先方式：

```text
Content-Type: application/json
X-Device-Key: <裝置專屬金鑰>
```

若裝置尚未設定 `auth_key_hash`，現有程式仍支援 `X-Service-Key`／`MEOW_SERVICE_KEY` 作為相容性 fallback。但正式 ESP32 建議每台使用不同的 `X-Device-Key`，不要共用全系統金鑰。

### 1.3 JSON 規格

| 欄位 | 型別 | 必填 | 單位／限制 |
|---|---|---:|---|
| `device_uid` | string | 是 | 3–120 字元；對應 `iot_devices.device_uid` |
| `sequence_no` | integer | 是 | 0–9,223,372,036,854,775,807；裝置範圍內唯一事件 ID |
| `measured_at` | ISO 8601 datetime | 是 | 必須含 timezone；UTC 建議使用 `Z` |
| `raw_value` | integer | 是 | HX711 24-bit 原始值，-8,388,608–8,388,607 |
| `raw_weight_grams` | number | 是 | 克；-500–20,000 g |
| `filtered_weight_grams` | number | 是 | 克；-500–20,000 g |
| `quality` | enum | 是 | `GOOD`、`UNSTABLE`、`OUT_OF_RANGE`、`CALIBRATING`、`ERROR` |
| `firmware_version` | string/null | 否 | 最長 80 字元 |
| `simulated` | boolean | 否 | Python 模擬資料必須為 `true`；實機為 `false` |

時間限制：不得超過伺服器時間未來 5 分鐘，也不得早於 7 天離線緩衝範圍。

範例（無任何金鑰）：

```json
{
  "device_uid": "ESP32-HX711-A01",
  "sequence_no": 1051,
  "measured_at": "2026-10-29T01:00:00Z",
  "raw_value": 412345,
  "raw_weight_grams": 99.2,
  "filtered_weight_grams": 99.0,
  "quality": "GOOD",
  "firmware_version": "catsense-hx711-0.1.0",
  "simulated": false
}
```

## 2. 裝置驗證與金鑰安全

`iot_devices.auth_key_hash` 只保存 PBKDF2-HMAC-SHA256 salted hash，實作沿用 `app/services/auth_service.py`：

- 原始裝置金鑰不應寫入資料庫。
- FastAPI 使用 `verify_password()` 驗證 `X-Device-Key`。
- 比對使用 constant-time digest comparison。
- Arduino 的原始金鑰只放在未提交的 `hardware/esp32_hx711/secrets.h`。
- `.gitignore` 已排除 `.env` 與所有 `hardware/**/secrets.h`。
- ESP32 不得直接取得 Supabase 密碼、Service Role Key 或管理連線字串。

目前尚無「裝置金鑰自助註冊 API」。實機上線前應用受控管理腳本或管理員功能為指定裝置寫入 hash；不可把明文金鑰記錄在報告或 Git。

## 3. device、cat house、pet 關聯

```text
iot_devices.device_uid
        │
        ▼
iot_devices.id ───────────────► sensor_readings.device_id
        │
        └── cat_house_id ─────► cat_houses.id
                                  │
                                  └── current_pet_id ─► pets.id
                                                           │
                                                           └── sensor_readings.pet_id
```

上傳 payload 不接受 `pet_id` 或 `cat_house_id`，避免 ESP32 偽造關聯。伺服器依 `device_uid` 找到 `IotDevice`，再由 `device.cat_house_id` 找到智慧貓屋，最後將當時 `cat_houses.current_pet_id` 快照到 `sensor_readings.pet_id`。

`feeding_events` 同時保存 `device_id`、`cat_house_id`、`pet_id` 及起訖 reading ID，便於追溯。

## 4. sensor_readings 寫入流程

1. Pydantic 驗證 JSON、數值範圍、NaN/Inf 與時區。
2. 以 `device_uid` 查找裝置；不存在回傳 404，停用裝置回傳 403。
3. 驗證 `X-Device-Key`；錯誤回傳 401。
4. 以 `(device_id, sequence_no)` 查找既有資料。
5. 若已存在，回傳原 measurement ID、HTTP 200、`duplicate=true`。
6. 由裝置取得 cat house 與 current pet。
7. 寫入 raw／filtered 克數、quality、source 與 simulated 標記。
8. 更新裝置 `last_seen_at` 與 firmware version。
9. 執行保守的 feeding candidate 規則。
10. 新增稽核紀錄並 commit。

資料庫另有 `uq_sensor_device_sequence` 唯一約束，能處理同時重送造成的競態；IntegrityError 後會重新查找並以 duplicate 回應。

## 5. feeding_events 產生方式

實作：`app/services/feeding_service.py`。

目前規則要求同一裝置最近四筆都是 `GOOD`：

```text
穩定前 2 筆 → 合理重量下降 → 穩定後 2 筆
```

- 前兩筆差異不得超過 `FEEDING_STABLE_TOLERANCE_GRAMS`，預設 1 g。
- 後兩筆差異不得超過同一門檻。
- 平均重量下降必須介於 `FEEDING_MIN_DROP_GRAMS` 與 `FEEDING_MAX_DROP_GRAMS`，預設 2–200 g。
- `(device_id, start_reading_id)` 唯一，避免重複事件。
- 事件狀態固定建立為 `CANDIDATE`，confidence 0.75。
- 目前尚未將 YOLO 貓咪在 FOOD ROI 的活動證據加入事件規則。

因此重量變化只能稱為「攝食候選事件」或「建議確認」，不能直接宣稱貓咪確定進食。

## 6. 重送、去重與異常過濾

### 已支援

- 裝置範圍內 `sequence_no` 冪等去重。
- 資料庫唯一約束防競態重複。
- 時區、未來時間、超過 7 天離線資料驗證。
- HX711 signed 24-bit 原始值範圍。
- 重量 -500–20,000 g 範圍。
- NaN／Infinity 禁止。
- `quality != GOOD` 不參與 feeding candidate。
- SQLAlchemy 失敗回傳 503，裝置可保留相同 sequence 重送。

### Step 1 模擬器新增

- 有限重試。
- 指定一筆在第一次傳送前模擬網路中斷。
- 重送使用完全相同的 JSON 與 sequence。
- 完成後再回放同一事件，驗證 `duplicate=true`。
- 金鑰只讀取 `MEOW_DEVICE_KEY`，不接受 CLI 明文參數。

### 尚待實機驗證

- ESP32 長時間離線佇列與斷電後未送 payload 保存。
- HX711 漂移、震動、碗被移走、補飼料等情境分類。
- NTP 漂移與 Wi-Fi roaming。
- 重量規則與 FOOD ROI 的時間關聯。

## 7. 現有網站支援範圍

### 已有 API

- CAREGIVER／ADMIN：`GET /api/iot/devices`
- CAREGIVER／ADMIN：`GET /api/iot/measurements`
- 已登入且有貓咪存取權：`GET /api/feeding/events`

### 目前 UI

目前模板與 JavaScript 尚無專用「重量監測曲線」或「攝食事件列表」元件。原有照護員、管理員、Dashboard、活動分析與 AI Monitor 頁面均保留，這一階段只準備資料與 API，不重新設計 UI。

後續可在原 caregiver/admin 視覺風格中新增小型卡片：目前碗重、最後上線、最近攝食候選、資料品質；不應宣稱確定吃飯。

## 8. Step 1 交付程式

- Python 模擬器：`scripts/simulate_esp32_weight.py`
- ESP32 範例：`hardware/esp32_hx711/esp32_hx711.ino`
- Secrets 範本：`hardware/esp32_hx711/secrets.example.h`
- 硬體說明：`hardware/esp32_hx711/README.md`
- 接線校正：`ESP32_HX711_WIRING_AND_CALIBRATION.md`
- 隔離結果：`ISOLATED_IOT_TEST_REPORT.md`

## 9. 建議下一階段

1. HX711 到貨後確認荷重元規格與線色。
2. 在麵包板完成接線，先只輸出 Serial raw counts。
3. 執行 tare 與已知砝碼校正，取得每克 calibration factor。
4. 建立真實 ESP32 裝置資料與專屬 auth key hash。
5. 在同一區網使用本機 HTTP 驗證，確認 Windows 防火牆只開必要 port。
6. 外網部署必須改用有效 HTTPS 憑證與 root CA 驗證。
7. 先標記事件為 `CANDIDATE`，之後再將 FOOD ROI 活動紀錄作為佐證。
8. 實機完成後再設計 caregiver/admin 的重量 UI。

