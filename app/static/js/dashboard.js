const zoneLabels = { FOOD: "進食區", WATER: "飲水區", LITTER: "貓砂區", GENERAL: "一般活動範圍" };
const zoneIcons = { FOOD: "▰", WATER: "●", LITTER: "◇" };

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store" });
  if (response.status === 401) return window.location.assign("/login");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function localTime(value, fallback = "尚無") {
  if (!value) return fallback;
  return new Intl.DateTimeFormat("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));
}

function updateMonitor(status) {
  const online = Boolean(status.running && status.frame_count > 0);
  const zone = status.current_zone;
  const zoneText = zoneLabels[zone] || status.current_zone_label || "等待辨識";
  const welcome = document.querySelector("#welcome-monitor-state");
  welcome.classList.toggle("online", online);
  welcome.querySelector("span").textContent = online ? "AI 監測中" : (status.running ? "AI 連線中" : "AI 未啟動");
  document.querySelector("#live-badge").textContent = online ? "LIVE" : "OFFLINE";
  document.querySelector("#live-badge").classList.toggle("online", online);
  document.querySelector("#camera-ai-state").textContent = status.running ? "監測中" : "未啟動";
  document.querySelector("#overview-ai").textContent = status.running ? (online ? "監測中" : "等待畫面") : "離線";
  document.querySelector("#overview-zone").textContent = zoneText;
  document.querySelector("#live-zone").textContent = zone ? `目前區域：${zoneText}` : "等待有效區域";
  document.querySelector("#confidence").textContent = status.detected ? `Cat confidence ${Number(status.confidence || 0).toFixed(2)}` : "目前未偵測到 cat";
  document.querySelector("#frame-count").textContent = `Frame ${status.frame_count || 0}`;
  document.querySelector("#monitor-detail").textContent = status.message || "尚無監控訊息";
  document.querySelector("#frame-updated").textContent = online ? `更新 ${new Date().toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}` : "尚未更新";
  document.querySelector("#overview-last").textContent = status.detected ? "剛剛" : "尚無偵測";
  const map = document.querySelector("#house-map");
  map.dataset.zone = ["FOOD", "WATER", "LITTER"].includes(zone) ? zone : "";
  document.querySelector("#momo-marker").hidden = !map.dataset.zone;
  document.querySelector("#map-status").textContent = map.dataset.zone ? zoneText : "等待辨識";
  if (online && !document.hidden) {
    const image = document.querySelector("#live-frame");
    image.src = `/api/monitor/frame?t=${Date.now()}`;
    image.classList.remove("is-missing");
  }
}

function updateZoneEvents(records) {
  for (const zone of ["FOOD", "WATER", "LITTER"]) {
    const record = records.find(item => item.zone === zone);
    document.querySelector(`#${zone.toLowerCase()}-last`).textContent = record ? `最近 ${localTime(record.entered_at)}` : "尚無事件";
  }
}

function renderDevices(devices) {
  const target = document.querySelector("#owner-device-list");
  const cameraOnline = document.querySelector("#live-badge").classList.contains("online");
  const rows = [{ name: "A01 攝影機", device_type: "CAMERA", status: cameraOnline ? "ONLINE" : "OFFLINE", last_seen_at: null }, ...devices];
  target.innerHTML = rows.map(device => `<div class="cs-device-row"><span>${device.device_type === "CAMERA" ? "▣" : "⌁"}</span><div><strong>${escapeHtml(device.name)}</strong><small>${device.last_seen_at ? `最後回報 ${localTime(device.last_seen_at)}` : (device.status === "ONLINE" ? "串流中" : "尚無近期回報")}${device.simulated ? " · 模擬裝置" : ""}</small></div><b class="${device.status === "ONLINE" ? "online" : ""}">${device.status === "ONLINE" ? "在線" : "離線"}</b></div>`).join("");
}

function renderEvents(records, alerts) {
  const events = [
    ...records.map(row => ({ icon: zoneIcons[row.zone] || "🐾", title: `Momo 進入${row.zone_label}`, note: "AI 區域事件", at: row.entered_at })),
    ...alerts.slice(0, 4).map(row => ({ icon: "♢", title: row.message, note: row.resolved ? "已處理提醒" : "待確認提醒", at: row.created_at })),
  ].sort((a, b) => new Date(b.at) - new Date(a.at)).slice(0, 6);
  const target = document.querySelector("#notice-list");
  if (!events.length) {
    target.innerHTML = '<div class="cs-empty"><span>🐾</span><p>貓屋目前很安靜，尚無事件。</p></div>';
    return;
  }
  target.innerHTML = events.map(event => `<div class="cs-event-row"><span>${event.icon}</span><div><strong>${escapeHtml(event.title)}</strong><small>${escapeHtml(event.note)}</small></div><time datetime="${escapeHtml(event.at)}">${localTime(event.at)}</time></div>`).join("");
}

async function refresh() {
  try {
    const [pet, status, recent, alerts, devices] = await Promise.all([
      getJson("/api/pets/current"), getJson("/api/monitor/status"), getJson("/api/activities/recent?limit=12"),
      getJson("/api/alerts"), getJson("/api/iot/pet-status"),
    ]);
    document.querySelector("#welcome-pet-name").textContent = pet.name;
    updateMonitor(status);
    updateZoneEvents(recent);
    renderDevices(devices);
    renderEvents(recent, alerts);
    document.querySelector("#overview-alerts").textContent = `${alerts.filter(row => !row.resolved).length} 則`;
  } catch (error) {
    const state = document.querySelector("#welcome-monitor-state");
    state.classList.remove("online");
    state.querySelector("span").textContent = "暫時無法讀取系統狀態";
  }
}

document.querySelector("#camera-fullscreen").addEventListener("click", () => {
  const stage = document.querySelector("#camera-stage");
  if (document.fullscreenElement) document.exitFullscreen();
  else stage.requestFullscreen?.();
});
document.querySelectorAll(".cs-map-zone").forEach(button => button.addEventListener("click", () => {
  const text = button.querySelector("small").textContent;
  window.csToast(`${button.querySelector("strong").textContent}：${text}`, "success");
}));

refresh();
setInterval(() => { if (!document.hidden) refresh(); }, 4000);
