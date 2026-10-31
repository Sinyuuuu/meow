const zoneLabels = { FOOD: "進食區", WATER: "飲水區", LITTER: "貓砂區", GENERAL: "一般活動範圍" };
const zoneIcons = { FOOD: "▰", WATER: "●", LITTER: "◇" };

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Authentication required");
  }
  if (!response.ok) throw new Error(`${response.status}`);
  return response.json();
}

function formatTime(value) {
  return new Intl.DateTimeFormat("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function updateStatus(status) {
  const zone = status.current_zone;
  document.querySelector("#live-zone").textContent = zone ? `Momo 在${zoneLabels[zone]}` : status.current_zone_label;
  document.querySelector("#house-map").dataset.zone = ["FOOD", "WATER", "LITTER"].includes(zone) ? zone : "";
  document.querySelector("#confidence").textContent = status.detected ? `Cat confidence ${Number(status.confidence).toFixed(2)}` : "目前未偵測到 cat";
  document.querySelector("#frame-count").textContent = `Frame ${status.frame_count || 0}${status.inference_ms != null ? ` · ${status.inference_ms} ms` : ""}`;
  document.querySelector("#monitor-message").textContent = status.message || "監測尚未啟動";
  document.querySelector("#monitor-dot").parentElement.classList.toggle("offline", !status.running);
  if (status.frame_count > 0) {
    const image = document.querySelector("#live-frame");
    image.src = `/api/monitor/frame?t=${Date.now()}`;
    image.classList.remove("is-missing");
  }
}

function updateSummary(payload) {
  const zones = payload.zones;
  document.querySelector("#food-count").textContent = zones.FOOD.count;
  document.querySelector("#water-count").textContent = zones.WATER.count;
  document.querySelector("#litter-count").textContent = zones.LITTER.count;
  const total = Object.values(zones).reduce((sum, zone) => sum + zone.count, 0);
  document.querySelector("#activity-status").textContent = total > 0 ? "持續記錄中" : "等待資料";
}

function updateNotices(records) {
  const target = document.querySelector("#notice-list");
  if (!records.length) return;
  target.innerHTML = records.slice(0, 4).map(record => `
    <div class="notice">
      <span class="notice-icon">${zoneIcons[record.zone] || "🐾"}</span>
      <p><strong>Momo</strong> 進入${record.zone_label}</p>
      <time datetime="${record.entered_at}">${formatTime(record.entered_at)}</time>
    </div>`).join("");
}

async function refresh() {
  try {
    const [status, summary, recent] = await Promise.all([
      getJson("/api/monitor/status"), getJson("/api/activities/summary"), getJson("/api/activities/recent?limit=4")
    ]);
    updateStatus(status); updateSummary(summary); updateNotices(recent);
  } catch (error) {
    document.querySelector("#monitor-message").textContent = "暫時無法讀取 AI 狀態";
    document.querySelector("#monitor-dot").parentElement.classList.add("offline");
  }
}

refresh();
setInterval(refresh, 2500);
