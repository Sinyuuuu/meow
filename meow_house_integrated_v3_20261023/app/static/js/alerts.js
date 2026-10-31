function timeText(value) {
  return new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}
function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}
async function loadAlerts() {
  const target = document.querySelector("#alert-list");
  try {
    const response = await fetch("/api/alerts");
    if (response.status === 401) return window.location.assign("/login");
    if (!response.ok) throw new Error(`${response.status}`);
    const alerts = await response.json();
  if (!alerts.length) {
    target.innerHTML = '<div class="empty-state"><span>♡</span><p>目前沒有需要確認的活動提醒。</p></div>';
    return;
  }
    const caregiver = document.body.dataset.role === "CAREGIVER";
    target.innerHTML = alerts.map(alert => `<div class="alert-row"><span>♢</span><div><p>${escapeHtml(alert.message)}</p><small>${timeText(alert.created_at)} · ${escapeHtml(alert.type)}${alert.handling_note ? ` · ${escapeHtml(alert.handling_note)}` : ""}</small></div>${caregiver && !alert.resolved ? `<button class="table-action" data-resolve-alert="${alert.id}">確認完成</button>` : `<b class="alert-state ${alert.resolved ? "resolved" : ""}">${alert.resolved ? "已確認" : "待確認"}</b>`}</div>`).join("");
  } catch (error) {
    target.innerHTML = '<div class="empty-state"><span>!</span><p>暫時無法讀取提醒紀錄。</p></div>';
  }
}
const refreshButton = document.querySelector("#refresh-rules");
if (document.body.dataset.role === "OWNER") refreshButton.hidden = true;
refreshButton.addEventListener("click", async event => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const response = await fetch("/api/alerts/evaluate", { method: "POST" });
    if (response.status === 401) return window.location.assign("/login");
    if (!response.ok) throw new Error(`${response.status}`);
    await loadAlerts();
  } finally {
    button.disabled = false;
  }
});
document.querySelector("#alert-list").addEventListener("click", async event => {
  const button = event.target.closest("[data-resolve-alert]");
  if (!button) return;
  button.disabled = true;
  try {
    const response = await fetch(`/api/alerts/${button.dataset.resolveAlert}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "RESOLVED", note: "照護人員已查看現場並完成確認" }),
    });
    if (!response.ok) throw new Error(`${response.status}`);
    await loadAlerts();
  } finally { button.disabled = false; }
});
loadAlerts();
