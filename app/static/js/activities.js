const dateInput = document.querySelector("#activity-date");
dateInput.value = new Date().toLocaleDateString("en-CA");

function durationText(seconds) {
  if (seconds == null) return "監測進行中";
  if (seconds < 60) return `停留 ${seconds} 秒`;
  const minutes = Math.round(seconds / 60);
  return `停留 ${minutes} 分鐘`;
}

function timeText(value) {
  return new Intl.DateTimeFormat("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

async function loadActivities() {
  const timeline = document.querySelector("#activity-timeline");
  try {
    const response = await fetch(`/api/activities?day=${encodeURIComponent(dateInput.value)}`);
    if (response.status === 401) return window.location.assign("/login");
    if (!response.ok) throw new Error(`${response.status}`);
    const records = await response.json();
  document.querySelector("#record-count").textContent = `${records.length} 筆`;
  if (!records.length) {
    timeline.innerHTML = '<div class="empty-state"><span>🐾</span><p>這天還沒有 AI 活動紀錄。</p></div>';
    return;
  }
    timeline.innerHTML = records.map(record => `
    <div class="timeline-item">
      <time class="timeline-time" datetime="${record.entered_at}">${timeText(record.entered_at)}</time>
      <div class="timeline-track"><i class="timeline-dot"></i><i class="timeline-line"></i></div>
      <div class="timeline-copy"><strong>${escapeHtml(record.zone_label)}</strong><span>${durationText(record.duration_seconds)}</span><small>${record.left_at ? `${timeText(record.entered_at)} — ${timeText(record.left_at)}` : "目前仍在此區"}</small></div>
    </div>`).join("");
  } catch (error) {
    timeline.innerHTML = '<div class="empty-state"><span>!</span><p>暫時無法讀取活動紀錄，請稍後再試。</p></div>';
  }
}

dateInput.addEventListener("change", loadActivities);
loadActivities();
