# 三角色網站 v2 整合檢查報告

## 判定

匯入的 `Meow一下_Codex_三角色整合網站與資料庫_v2.zip` 已作為功能與資料設計來源，並非直接覆蓋目前專案。壓縮檔內的說明文件只作參考，不視為使用者指令。

原因是兩份專案各有不同優勢：目前專案已有可執行的 OpenCV + YOLO11 + ROI + 防抖 + SQLite 完整影像管線；匯入版本的優勢則是三角色治理、帳號狀態、照護指派、裝置回報、ROI 管理、稽核與系統設定。匯入版本本身沒有實作真實攝影機與 YOLO 推論，因此不能取代現有 AI 核心。

## 已整合

- `OWNER / CAREGIVER / ADMIN` 最小權限邊界。
- 帳號啟用／停用與「至少保留一名管理員」保護。
- 照護員與貓咪的明確指派；未指派即拒絕存取。
- 管理員不可建立真人照護留言，避免資料責任混淆。
- 攝影機裝置心跳與在線狀態。
- 管理頁可維護五區 polygon ROI，採 0–1 正規化座標及原子寫入。
- 活動提醒門檻、提醒處理狀態、系統維運待辦。
- 管理與照護敏感操作稽核紀錄。
- 可選的 Service Key 裝置心跳／活動寫入 API。
- SQLite 預設執行；加入 `PyMySQL` 以便日後改用 MySQL URL。
- 一鍵啟動器會自動挑選 8000、8010、8080 或 8765，降低 Windows port 衝突。

## 保留現有實作

- Ultralytics YOLO11 COCO `cat` 偵測。
- Webcam／MP4 來源、例外處理、標註影片。
- Bounding Box、confidence、中心／底部中心點。
- 五區 polygon ROI 與解析度無關座標。
- 時間型防抖、區域切換與活動區段資料庫紀錄。
- Rule-based 活動提醒；不做疾病或醫療診斷。

## 刻意未合併

- 匯入版的假資料攝影機／假 AI 活動產生器：會混淆真實 YOLO Demo。
- 另一套平行的使用者、ROI 與活動資料表：會造成資料來源衝突。
- 將密碼、金鑰或帳號資訊回傳前端的任何做法。
- 多貓 Re-ID、醫療診斷、金流與大型語言模型影像分析：不屬於第一階段。

## 驗證結果

- Python compile 與 FastAPI OpenAPI schema：通過，39 條 path、44 個 operations。
- JavaScript 語法檢查：`admin.js`、`alerts.js`、`caregiver.js` 通過。
- ROI、防抖、Detector、Activity Service、Monitor lifecycle：9 項測試通過。
- ASGI 整合煙霧測試：OWNER、CAREGIVER、ADMIN 權限界線及 8 組管理 API 通過。
- Demo color pipeline：160 frames，完成 REST → FOOD → WATER → LITTER → ACTIVITY。
- YOLO11 真實畫面：成功偵測 cat 並輸出 Bounding Box、中心點、ROI 與 Current Zone。

## 正式展示前仍需現場校正

目前 ROI 是示意配置。攝影機固定在實際 120 × 90 × 60 cm 貓屋後，應從管理頁依真正視角重新輸入五區座標，並用 3–5 段不同光線、遮擋與夜間影片驗證。預訓練 YOLO 能回答「畫面中有沒有貓」，區域判斷則取決於鏡頭位置與 ROI 是否正確。
