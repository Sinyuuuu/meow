# Meow一下：專題系統架構

## 核心定位

「人負責照顧，AI 負責記錄，飼主遠端掌握。」

系統部署在專業寄養環境。AI 記錄單一智慧貓屋中的區域活動，照護員負責實際照顧與文字回報，飼主查看兩種資訊。

## 系統分層

```text
OWNER / CAREGIVER / ADMIN Browser
                │
                ▼
       Jinja2 + CSS + JavaScript
                │ session / JSON API
                ▼
              FastAPI
       ┌────────┼─────────┐
       ▼        ▼         ▼
 SQLAlchemy   Services   MonitorManager
       │        │         │
       ▼        │         ▼
    SQLite      │   OpenCV + YOLO
                │         │
                └────┬────┘
                     ▼
             Activity / Alert Records
```

## 三種角色

### OWNER

- 查看即時影像與目前區域
- 查看活動 Timeline、區域分析與提醒
- 查看貓咪資料與照護人員留言
- 不可啟停 Monitor 或修改照護任務

### CAREGIVER

- 查看今日入住貓咪與提醒
- 完成或重新開啟照護任務
- 填寫真人照護紀錄
- 啟動及停止 AI Monitor

### ADMIN

- 查看會員、貓咪、貓屋、寄養與資料量摘要
- 查看攝影機設備及 AI 管線狀態
- 進入照護工作台及 FastAPI 文件

## AI 資料流程

```text
Camera frame
  → cat detection
  → Bounding Box / confidence
  → configured anchor point
  → polygon ROI mapping
  → time-based debounce
  → close previous interval
  → open new interval
  → SQLite transaction
  → Dashboard polling
```

## 資料責任邊界

- `activity_records`：由 AI 產生的客觀區域區段。
- `care_tasks`：人工照護待辦與完成狀態。
- `care_logs`：照護人員撰寫的回報。
- `alerts`：規則式活動提醒，不是醫療診斷。
- `boarding_orders`：貓咪入住期間與貓屋分配。

AI 資料與人工照護紀錄不得混成同一種證據。

## 展示流程

1. 使用 OWNER 帳號展示飼主遠端查看。
2. 切換 CAREGIVER，完成任務、填寫留言並啟動 Monitor。
3. 播放 `data/demo.mp4` 驗證五區活動紀錄。
4. 切回 OWNER，確認 Timeline、分析與照護留言更新。
5. 使用 ADMIN 展示系統管線、設備狀態與角色權限。

## 近期開發界線

第一階段維持：單貓、固定鏡頭、固定 ROI、SQLite、本機服務。

暫不納入：多貓 Re-ID、疾病診斷、情緒辨識、攝取量估計、金流、手機 App。

