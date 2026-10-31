# NodeMCU-32S 模擬重量傳輸

Arduino IDE 請直接開啟 `esp32_simulated_weight.ino`。

1. 複製 `secrets.example.h` 為同資料夾的 `secrets.h`。
2. 在 `secrets.h` 本機填入 Wi-Fi、裝置測試金鑰及 API URL。
3. Board 選擇 `NodeMCU-32S`。
4. Serial Monitor 選擇 `115200 baud`。

程式只傳送一次 `120 → 119 → 117 → 115 → 110 g`，所有 payload 都是 `simulated=true`。序號儲存在 ESP32 NVS，網路重試會沿用同一份 payload；五筆成功後停止新增資料。

`secrets.h` 已被專案 `.gitignore` 排除。不要把 Wi-Fi 密碼或裝置金鑰貼到對話、文件、截圖或 Git。

