# ESP32 + HX711 接線與校正教學

## 1. 建議接線

### ESP32 到 HX711

| ESP32 | HX711 | 說明 |
|---|---|---|
| 3V3 | VCC | 優先使用 3.3V，確保 ESP32 邏輯電位安全 |
| GND | GND | 必須共地 |
| GPIO 19 | DT／DOUT | 資料腳，可在 `.ino` 修改 |
| GPIO 18 | SCK／CLK | 時脈腳，可在 `.ino` 修改 |

不要把 HX711 的資料輸出接到 5V 邏輯。若模組標示供電規格不同，應先查該模組 datasheet。

### 四線式荷重元到 HX711

| HX711 | 功能 | 常見線色（僅參考） |
|---|---|---|
| E+ | Excitation + | 紅 |
| E- | Excitation - | 黑 |
| A+ | Signal + | 白或綠 |
| A- | Signal - | 綠或白 |

不同廠牌線色可能完全不同，必須以荷重元標籤、賣場規格或萬用表量測為準。若重量方向相反，可交換 A+／A-，或讓 calibration factor 使用相反正負號。

## 2. 機構安裝

- 單點式荷重元通常一端固定、另一端承載食碗平台。
- 固定端與受力端不能同時碰到外框，否則重量會被旁路。
- 線材要留鬆弛，不能拉住平台。
- 食碗平台不可碰牆、地面或貓屋隔板。
- 選擇額定負載時要包含碗、飼料及貓咪踩踏的可能負荷。
- 正式使用前增加過載保護，避免貓跳上去損壞荷重元。

## 3. Arduino 準備

1. Arduino IDE 安裝 ESP32 board package。
2. Library Manager 安裝 `HX711`。
3. Library Manager 安裝 `ArduinoJson`。
4. 開啟 `hardware/esp32_hx711/esp32_hx711.ino`。
5. 複製 `secrets.example.h` 為 `secrets.h`。
6. 填入 Wi-Fi、裝置 UID、裝置金鑰與 API URL。

`secrets.h` 已被 `.gitignore` 排除，不可截圖公開或提交 Git。

## 4. 去皮重

1. 平台與空碗安裝完成。
2. 確認碗內沒有飼料，平台沒有被碰觸。
3. 開機時程式執行 `scale.tare(20)`。
4. Serial Monitor 觀察空碗讀值是否接近 0 g。
5. 若每次開機後偏移很大，檢查機構干涉、供電、接線與溫漂。

目前範例將「空碗」一起 tare，所以 API 的重量代表碗內內容物約略重量。若要記錄碗本身重量，應改變 tare 流程並清楚定義。

## 5. 校正係數

使用已知重量，例如 100 g：

1. 暫時將 `HX711_CALIBRATION_FACTOR` 設為 `1.0`。
2. tare 空碗。
3. 放上 100 g 校正砝碼，取得穩定的 counts 差值。
4. 計算：

```text
calibration_factor = (loaded_counts - tare_counts) / known_weight_grams
```

5. 將結果填回 `.ino` 的 `HX711_CALIBRATION_FACTOR`。
6. 重新上傳後，分別測試 20 g、50 g、100 g、200 g。
7. 若顯示負值，將係數改成相反符號或交換 A+／A-。

至少重複放置三次，記錄平均誤差與最大誤差。不要只用單一重量點就宣稱整段量測精準。

## 6. 穩定讀值

範例程式每次取多筆 HX711 讀值：

- `raw_value`：HX711 raw average。
- `raw_weight_grams`：最後一組轉換重量。
- `filtered_weight_grams`：多組重量平均。
- 最大值與最小值差異小於 1 g 時標記 `GOOD`。
- 超過門檻標記 `UNSTABLE`；伺服器仍可保存，但不參與 feeding candidate。

實機應依貓屋震動與取樣頻率調整門檻，不要為了產生事件而過度放寬。

## 7. 本機 HTTP 測試

1. 電腦與 ESP32 連到同一 Wi-Fi。
2. 啟動 FastAPI，監聽可讓區網連入的介面時才可由 ESP32 存取。
3. `MEOW_API_BASE_URL` 使用電腦區網 IP，例如 `http://192.168.1.100:8000`，不能使用 ESP32 自己的 `127.0.0.1`。
4. Windows 防火牆只允許私人網路與必要 port。
5. 先在測試裝置／隔離資料庫驗證，再連正式 API。

HTTP 只適合同一個受控區網的初期測試，不能用於公網傳輸裝置金鑰。

## 8. HTTPS

- 公網或跨網路必須使用 HTTPS。
- 將伺服器憑證鏈的可信任 root CA 放入 `MEOW_ROOT_CA_PEM`。
- 範例使用 `WiFiClientSecure.setCACert()`。
- 程式刻意沒有 `setInsecure()`；未提供 CA 時會拒絕 HTTPS。
- 憑證更新時要規劃 ESP32 firmware 更新或安全的 CA rotation。

## 9. 重送與事件 ID

- `sequence_no` 儲存在 ESP32 NVS，重新開機後繼續遞增。
- 同一筆網路重試必須沿用同一個 sequence 與 measured_at。
- HTTP 201 表示新資料；HTTP 200 且 `duplicate=true` 表示伺服器已收過。
- 401／403／404／409／422 不應無限重試，需要人員檢查設定或 payload。
- 目前範例只有有限即時重試；長時間斷線的持久離線 queue 尚待下一階段。

## 10. 到貨後驗收清單

- [ ] 空碗 tare 後接近 0 g。
- [ ] 20–200 g 多點誤差已記錄。
- [ ] 拿起再放回食碗後讀值可重現。
- [ ] 輕碰貓屋時標記 `UNSTABLE`。
- [ ] Wi-Fi 斷線時不會產生新的 sequence 重複資料。
- [ ] 重新連線後相同 payload 可安全重送。
- [ ] 錯誤裝置金鑰回傳 401。
- [ ] Supabase 不會收到明文裝置金鑰。
- [ ] 重量下降只能建立 `CANDIDATE`，不能顯示為確定進食。

