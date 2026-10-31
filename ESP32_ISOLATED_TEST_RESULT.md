# CatSense AI — ESP32 隔離測試結果

測試日期：2026-10-29  
正式資料庫：未寫入、未切換  
隔離資料庫：tests/.tmp/*.db

## 實際檢查結果

| 項目 | 結果 |
|---|---|
| Python 新增腳本語法 | 通過 |
| PowerShell 啟動器語法 | 通過 |
| Arduino IDE / NodeMCU-32S Verify | 通過 |
| 既有 HX711 韌體 Verify | 未通過；本機缺少 ArduinoJson，HX711 函式庫亦尚未確認 |
| FastAPI 隔離 SQLite 啟動 | 通過 |
| /docs 啟動後 HTTP | 200 |
| 120、119、117、115、110 g 新增 | 五筆皆 HTTP 201 |
| 模擬網路中斷後相同序號重送 | 通過 |
| 已存在序號重播 | HTTP 200、duplicate=true |
| 無效裝置金鑰 | HTTP 401；未新增資料 |
| 隔離服務重啟後保存 | 仍為五筆 |
| 五筆資料 simulated | 全部 true |
| 120→119→117→115→110 候選事件 | 0 筆，符合保守規則 |
| 120→120→110→110 規則探針 | 建立一筆 10 g CANDIDATE，simulated=true |
| 原有測試套件 | 22 passed、1 個既有 deprecation warning |

## 120→119→117→115→110 寫入摘要

- sensor_readings=5
- feeding_events=0
- 序號為裝置範圍內唯一
- 時間為含 UTC offset 的有效時間
- quality=GOOD
- source=SIMULATOR
- 正式 Supabase 未被選用

此序列的每一段仍在持續下降，沒有兩筆穩定的 before plateau 與兩筆穩定的 after plateau，因此不應直接產生攝食事件。

## 候選事件規則驗證

另一個獨立 SQLite 探針使用 120→120→110→110，得到：

- sensor_readings=4
- feeding_events=1
- status=CANDIDATE
- estimated_consumed_grams=10.0
- simulated=true

這只證明規則型候選流程可運作，不是貓咪確定進食的判定，也沒有寫入正式 Supabase。

## 正式設定保護

完成測試後再次安全檢查：

- 正式 DATABASE_URL backend 仍為 postgresql
- 正式 AUTO_CREATE_SCHEMA=false
- .env 未修改
- 所有端對端寫入均由隔離啟動器在程序內強制改用 SQLite
- 未執行 migration、DROP、TRUNCATE 或 Supabase 搬移

## 尚未實測

- 尚未由使用者將新 .ino Upload 到實體 Ai-Thinker NodeMCU-32 V1.3。
- 尚未從實體 ESP32 經 iPhone 熱點送出五筆 POST。
- HX711、荷重元、去皮與校正尚待硬體到貨。
- 既有 HX711 韌體需先由 Arduino Library Manager 安裝 ArduinoJson 與 HX711，再重新 Verify。
- 長時間離線與斷電後的多筆佇列尚未完成；目前僅保留運行中的單筆 pending payload。

因此目前可標示為「韌體編譯與隔離端到端軟體測試通過」，不可標示為「實體 ESP32 重量傳輸已通過」。
