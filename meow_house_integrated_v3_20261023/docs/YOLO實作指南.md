# Meow一下：YOLO 實作與實機測試指南

本文件對應目前專案的 `OpenCV → YOLO → ROI → 防抖 → SQLite → Dashboard` 管線。

## 1. YOLO 在本專題負責什麼

YOLO 只負責回答兩件事：

1. 畫面中有沒有 `cat`。
2. 貓咪的 Bounding Box 在哪裡、信心值是多少。

它不直接判斷「有沒有吃飯、喝水或生病」。系統再使用 Bounding Box 的位置點判斷五個 ROI，並以時間規則建立活動紀錄。

目前使用 `yolo11n.pt`，原因是模型小、CPU 可執行，而且已經完成整條系統整合。後續可用同一批影片比較 `yolo26n.pt`，確認準確率與速度確實更好後再切換。

## 2. 第一次安裝

在 PowerShell 進入專案：

```powershell
cd "C:\Users\sinyu\Documents\Codex\2026-09-15\prototype-meow-ai-ai-ai-demo"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

專案已附 `yolo11n.pt`。若更換成其他官方模型，第一次執行可能需要下載權重。

## 3. 先用單張圖片確認 YOLO

```powershell
$env:YOLO_CONFIG_DIR=(Resolve-Path .\work\ultralytics).Path
python -c "from ultralytics import YOLO; m=YOLO('yolo11n.pt'); r=m.predict('work/cat-frame.png', classes=[15], conf=0.35, save=True); print(r[0].boxes)"
```

`classes=[15]` 表示只保留 COCO 的 `cat` 類別。輸出應包含 `xyxy`、`conf` 與 `cls`。

## 4. 使用真實 MP4

先把影片放到 `data/`，例如 `data/my-cat.mp4`：

```powershell
python scripts\run_monitor.py --source data\my-cat.mp4 --detector yolo --display
```

畫面應顯示：

- 貓咪 Bounding Box
- `cat` confidence
- ROI 邊界
- 判定位置點
- Current Zone

按 `Q` 關閉預覽。

## 5. 使用 USB Webcam

```powershell
python scripts\run_monitor.py --source 0 --detector yolo --display
```

如果開不到鏡頭，依序嘗試 `1`、`2`。同一時間不要讓相機 App、Teams 或瀏覽器占用 Webcam。

## 6. 從網站操作

終端機一：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

開啟 <http://127.0.0.1:8000>，使用照護員帳號：

- 帳號：`caregiver@meow.local`
- 密碼：`Meow123!`

在「AI Monitor 控制」填入：

- `0`：USB Webcam
- `data/my-cat.mp4`：真實貓咪影片
- Detector 選擇 `YOLO 真實貓咪`

測試內建示範影片時，來源使用 `data/demo.mp4`，Detector 必須選 `Demo 測試影片`。這個模式只驗證資料管線，不是假裝 YOLO 偵測。

## 7. 校正貓屋 ROI

ROI 存在 `data/rois.json`，座標使用 0～1 比例，因此不依賴固定解析度：

```json
"REST": [[0.00, 0.00], [0.50, 0.00], [0.50, 0.55], [0.00, 0.55]]
```

校正流程：

1. 固定攝影機位置。
2. 截取一張完整貓屋畫面。
3. 記錄每個區域角點的 pixel 座標。
4. 用 `x / 影像寬度`、`y / 影像高度` 轉為 0～1。
5. 更新五個 polygon。
6. 讓貓分別進入五區，錄影驗證。

ROI 不可重疊；沒有被其他四區涵蓋的空間可規劃為 `ACTIVITY`。

## 8. 中心點或底部中心點

`.env`：

```dotenv
ZONE_POINT_MODE=center
```

- `center`：容易理解，適合目前示範影片及初始 Demo。
- `bottom_center`：更接近貓咪接觸地板的位置，較適合實際貓屋地面區域。

改為 `bottom_center` 後必須重新驗證 ROI，因為區域邊界會影響結果。

## 9. 建議初始參數

```dotenv
YOLO_MODEL=yolo11n.pt
YOLO_CONFIDENCE=0.35
ZONE_POINT_MODE=center
ZONE_SWITCH_SECONDS=2.0
MISSING_CAT_ALERT_SECONDS=30
LONG_STAY_ALERT_SECONDS=3600
MONITOR_SAMPLE_FPS=8
```

調整原則：

- 漏掉很多貓：confidence 可降至 `0.25～0.30`。
- 把其他物件誤認成貓：提高至 `0.40～0.50`。
- 區域一直跳動：切換時間提高至 `2.5～3 秒`。
- 移動後太慢更新：切換時間降低，但不要低於 `1 秒`。

## 10. 必須蒐集的測試影片

每種至少 2～3 段：

- 白天正常光線
- 夜間或低光源
- 貓趴下、縮成一團
- 貓靠近鏡頭
- 貓被睡窩或貓砂盆部分遮擋
- 五個區域之間來回移動
- 空貓屋
- 照護人員的手進入畫面

記錄每段影片的「應有區域」與「系統結果」，至少計算：

- Cat detection recall：應看到貓的影格中，有多少成功偵測。
- Zone accuracy：成功偵測時，區域判定正確比例。
- False transition：實際沒換區，系統卻產生切換的次數。
- Event delay：真正換區到系統確認的秒數。

## 11. 何時需要自行訓練

只有在真實貓屋影片出現以下情況才考慮自訂訓練：

- 預訓練 YOLO 經常漏掉趴睡或遮擋中的貓。
- 夜視畫面偵測率明顯不足。
- 貓在遠端畫面中太小。

先收集並標註約 500～1,000 張真實貓屋影像，只標一類 `cat`，再由 `yolo11n.pt` fine-tune。不要一開始就從零訓練。

## 12. 專題展示用語

可以說：

- 「偵測到 Momo 進入飲水區。」
- 「今日有 3 次飲水區活動。」
- 「較長時間未記錄到飲水區活動，建議確認。」

不要說：

- 「Momo 今天喝了三次水。」
- 「系統診斷 Momo 生病。」

影像位置只能證明出現在區域，不能證明實際攝取量或疾病。

## 13. 下一階段

完成穩定 MVP 後再依序考慮：

1. ByteTrack：取得較平滑的軌跡與移動距離。
2. YOLO Segmentation：用貓咪輪廓與 ROI 重疊比例改善邊界判定。
3. 自訂行為分類：趴臥、走動、舔毛等，但需另外蒐集和標註資料。
4. OpenVINO / ONNX：CPU 效能不足時再進行模型匯出與 benchmark。

官方參考：

- https://docs.ultralytics.com/models/yolo11/
- https://docs.ultralytics.com/modes/track/
- https://docs.ultralytics.com/tasks/segment/
- https://docs.ultralytics.com/modes/benchmark/

