# ESP32 + HX711 範例

1. 將 `secrets.example.h` 複製為 `secrets.h`。
2. 在 `secrets.h` 填入 Wi-Fi、裝置 UID、裝置金鑰及 API URL。
3. Arduino Library Manager 安裝 `HX711` 與 `ArduinoJson`。
4. 依 `ESP32_HX711_WIRING_AND_CALIBRATION.md` 接線與校正。
5. 修改 `HX711_CALIBRATION_FACTOR` 後上傳 `esp32_hx711.ino`。

`secrets.h` 已由專案 `.gitignore` 排除。HTTPS 模式必須提供可信任根憑證；程式沒有 `setInsecure()`。

API 使用 `(device_uid, sequence_no)` 作為唯一事件識別。ESP32 將 sequence 儲存在 NVS，重送時沿用完全相同的 JSON，伺服器會回傳 `duplicate=true` 而不重複新增資料。

