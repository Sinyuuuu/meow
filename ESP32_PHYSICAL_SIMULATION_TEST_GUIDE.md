# CatSense AI — ESP32 實體模擬重量傳輸教學

> 本教學只使用 tests/.tmp/esp32_hardware_test.db 隔離 SQLite。正式 .env、Supabase、網站 UI、YOLO 與 ROI 都不會被切換或覆蓋。

## 1. 既有 API 與驗證規則

- Method：POST
- Path：/api/ingest/measurements
- ESP32 Header：X-Device-Key
- Content-Type：application/json
- 測試裝置 UID：ESP32-SIM-A01

X-Service-Key 只是在裝置沒有 auth_key_hash 時的既有備援。隔離啟動器會替測試裝置建立 PBKDF2-SHA256 雜湊，因此本次使用 X-Device-Key，不使用正式服務金鑰。

| 欄位 | 型別與規則 |
|---|---|
| device_uid | 字串，去除前後空白後長度 3–120；必須存在於 iot_devices |
| sequence_no | 整數，0–9,223,372,036,854,775,807；同一裝置不可重複 |
| measured_at | 含時區 ISO 8601；不可晚於伺服器 5 分鐘，離線補傳最久 7 天 |
| raw_value | 整數，HX711 signed 24-bit：-8,388,608–8,388,607 |
| raw_weight_grams | 有限浮點數，-500–20,000 g |
| filtered_weight_grams | 有限浮點數，-500–20,000 g |
| quality | GOOD、UNSTABLE、OUT_OF_RANGE、CALIBRATING 或 ERROR |
| firmware_version | 可省略，最長 80 字元 |
| simulated | Boolean；本次固定 true |

去重鍵是資料庫約束 (device_id, sequence_no)。新資料回 201；同一筆重送回 200 且 duplicate=true，不會新增第二筆。

## 2. Arduino IDE 要開啟的檔案

直接開啟：

hardware/esp32_simulated_weight/esp32_simulated_weight.ino

同資料夾的 secrets.h 是本機設定檔，已由 .gitignore 排除。只在自己的電腦填入：

- Wi-Fi／iPhone 熱點名稱
- Wi-Fi 密碼
- 自訂的隔離測試裝置金鑰
- MEOW_DEVICE_UID（保留 ESP32-SIM-A01）
- MEOW_API_BASE_URL（目前為 http://172.20.10.5:8765）

請勿把 secrets.h、Wi-Fi 密碼或裝置金鑰貼到 Git、報告、聊天或截圖。若筆電熱點 IP 改變，先在 Windows 執行 ipconfig，再只修改本機 MEOW_API_BASE_URL。

Arduino IDE 設定：

1. Board：NodeMCU-32S
2. Port：選擇 ESP32 實際 COM Port
3. Serial Monitor：115200 baud
4. 先按 Verify；確認無錯誤後才按 Upload

本次已用 Arduino IDE 2.3.10、ESP32 core 3.3.12、NodeMCU-32S 完成 Verify：

- Flash：949,044 bytes（72%）
- Dynamic memory：48,888 bytes（14%）

尚未代替使用者按 Upload，因此不能把實體 ESP32 燒錄列為已完成。

既有 hardware/esp32_hx711/esp32_hx711.ino 也已實際嘗試 Verify，但本機目前缺少 ArduinoJson，編譯在 include 階段停止。Library Manager 須先安裝 ArduinoJson（Benoit Blanchon）與 HX711（bogde）；因 HX711 尚未到貨，本階段沒有改動或假裝通過真實韌體。安裝後仍需再 Verify 一次。

## 3. VS Code 啟動隔離 FastAPI

在 VS Code PowerShell Terminal 輸入：

~~~powershell
cd "C:\Users\sinyu\OneDrive\桌面\meow_house_integrated_v3_20261023"
powershell -ExecutionPolicy Bypass -File ".\啟動ESP32隔離測試.ps1"
~~~

畫面會以遮蔽方式詢問測試裝置金鑰。輸入與本機 secrets.h 的 MEOW_DEVICE_KEY 完全相同的值。請保持 Terminal 開啟。

應看到：

~~~text
CatSense ESP32 isolated test server
Database: isolated SQLite (...\tests\.tmp\esp32_hardware_test.db)
Device UID: ESP32-SIM-A01
Production Supabase: not selected
Uvicorn running on http://0.0.0.0:8765
~~~

若 Windows 防火牆詢問，只允許私人網路。ESP32 與筆電必須連到同一個 iPhone 熱點。

## 4. 燒錄後應看到的結果

韌體會依序上傳：120 g → 119 g → 117 g → 115 g → 110 g。

每一筆都包含 UTC 時間、NVS 保存的唯一序號、quality=GOOD 與 simulated=true。Serial Monitor 預期類似：

~~~text
CatSense isolated simulated-weight test
Wi-Fi connected, IP: ...
NTP clock ready
sequence=... grams=120.0 attempt=1 http=201
response={"accepted":true,"duplicate":false,...,"simulated":true}
...
sequence=... grams=110.0 attempt=1 http=201
TEST COMPLETE: 5 simulated weights sent.
~~~

若 HTTP 傳輸失敗，程式最多立即重試三次；仍失敗時會保留相同 payload 與序號供下一輪重送，避免把一次量測誤當成多筆。重新開機後 NVS 序號仍會遞增。

- 201：新增成功
- 200 且 duplicate=true：重送成功，未重複新增
- 401：本機金鑰與啟動服務時輸入的金鑰不同
- 404：device_uid 不存在
- 422：時間戳、範圍或 JSON 格式不符合規則
- http=-1：Wi-Fi、網址、HTTP client 或 HTTPS CA 設定問題

## 5. 查看隔離資料庫

ESP32 傳完後另開一個 VS Code Terminal：

~~~powershell
cd "C:\Users\sinyu\OneDrive\桌面\meow_house_integrated_v3_20261023"
.\.venv\Scripts\python.exe scripts\inspect_esp32_isolated_test.py
~~~

第一次完整成功預期：

~~~text
database=isolated_sqlite device_uid=ESP32-SIM-A01
sensor_readings=5 feeding_events=0
~~~

120→119→117→115→110 沒有「下降前兩筆穩定 + 下降後兩筆穩定」的平台，因此不應建立攝食候選事件。這是正確結果，不是辨識失敗。

系統只有在四筆 GOOD 讀值形成穩定前段、有效下降、穩定後段時才建立 status=CANDIDATE、source=WEIGHT_RULE。即使建立候選，也不代表確定進食；未來仍應用 YOLO FOOD 區活動或人工確認提高可信度。

## 6. 下一步換成 HX711

真實硬體到貨後沿用 hardware/esp32_hx711/esp32_hx711.ino：

1. 保留同一 API、device_uid、NVS 序號、Header 與重試邏輯。
2. 將固定陣列改為 HX711 去皮、校正及濾波讀值。
3. 真實資料設定 simulated=false，source 由伺服器記為 HX711。
4. Wi-Fi 長時間離線佇列尚未完成；目前只有 RAM 中單筆 pending payload，斷電時未送資料不會保留。
5. HTTPS 上線時必須填入可信根憑證；韌體會拒絕沒有 CA 的 HTTPS，不會停用 TLS 驗證。

## 7. 實體測試回報

完成 Upload 後，請提供 Serial Monitor 中不含 Wi-Fi 密碼、裝置金鑰的以下內容：

- Wi-Fi connected
- NTP clock ready
- 五筆 HTTP 狀態
- 最後的 TEST COMPLETE
- inspect_esp32_isolated_test.py 的筆數摘要

收到這些結果後，才能把「ESP32 實體傳輸」標示為通過。
