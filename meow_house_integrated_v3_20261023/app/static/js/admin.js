async function api(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
  });
  if (response.status === 401) window.location.assign("/login");
  const body = response.headers.get("content-type")?.includes("json") ? await response.json() : null;
  if (!response.ok) throw new Error(body?.detail || `HTTP ${response.status}`);
  return body;
}

const escapeHtml = value => String(value ?? "").replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));
const timeText = value => value ? new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)) : "尚未回報";

let users = [];

async function loadOverview() {
  const [overview, monitor] = await Promise.all([api("/api/admin/overview"), api("/api/monitor/status")]);
  document.querySelector("#metric-users").textContent = overview.users;
  document.querySelector("#metric-pets").textContent = overview.pets;
  document.querySelector("#metric-houses").textContent = overview.houses;
  document.querySelector("#metric-occupied").textContent = `${overview.occupied_houses} 間使用中`;
  document.querySelector("#metric-activities").textContent = overview.activity_records;
  document.querySelector("#admin-active-alerts").textContent = overview.active_alerts;
  const state = document.querySelector("#admin-monitor-state");
  state.lastChild.textContent = monitor.running ? " ONLINE" : " OFFLINE";
  state.classList.toggle("is-online", monitor.running);
  document.querySelector("#admin-monitor-message").textContent = monitor.message || "尚未啟動";
  document.querySelector("#admin-current-zone").textContent = monitor.current_zone || "—";
  document.querySelector("#admin-frame-count").textContent = monitor.frame_count || 0;
  document.querySelector("#admin-detector").textContent = monitor.detector ? `${monitor.detector}${monitor.inference_ms != null ? ` · ${monitor.inference_ms} ms` : ""}` : "—";
  document.querySelector("#camera-device-list").innerHTML = overview.cameras.map(camera => `<div class="device-row"><span>▣</span><div><strong>${escapeHtml(camera.name)}</strong><small>${camera.last_seen_at ? `最後心跳 ${timeText(camera.last_seen_at)}` : "等待 AI Monitor 回報"}</small></div><b class="${camera.online ? "online-text" : "offline-text"}">${escapeHtml(camera.status)}</b></div>`).join("") || "<div class='empty-state'><p>尚無設備</p></div>";
}

async function loadUsers() {
  users = await api("/api/admin/users");
  document.querySelector("#user-table-body").innerHTML = users.map(user => `<tr><td><strong>${escapeHtml(user.name)}</strong><small>${escapeHtml(user.email)}</small></td><td><span class="role-chip">${escapeHtml(user.role)}</span></td><td><span class="status-chip ${user.status === "ACTIVE" ? "active" : "disabled"}">${escapeHtml(user.status)}</span></td><td><button class="table-action" data-user-id="${user.id}" data-next-status="${user.status === "ACTIVE" ? "DISABLED" : "ACTIVE"}">${user.status === "ACTIVE" ? "停用" : "啟用"}</button></td></tr>`).join("");
  const caregivers = users.filter(user => user.role === "CAREGIVER" && user.status === "ACTIVE");
  document.querySelector("#assignment-caregiver").innerHTML = caregivers.map(user => `<option value="${user.id}">${escapeHtml(user.name)}</option>`).join("");
}

async function loadAssignments() {
  const [assignments, pet] = await Promise.all([api("/api/admin/assignments"), api("/api/pets/current")]);
  document.querySelector("#assignment-pet").innerHTML = `<option value="${pet.id}">${escapeHtml(pet.name)}</option>`;
  document.querySelector("#assignment-list").innerHTML = assignments.map(item => `<div><span><strong>${escapeHtml(item.caregiver_name)}</strong><small>照護 ${escapeHtml(item.pet_name)}</small></span><b>${item.active ? "啟用" : "停用"}</b></div>`).join("") || "<p class='empty-copy'>尚無指派</p>";
}

async function loadRois() {
  const rois = await api("/api/admin/rois");
  document.querySelector("#roi-editor").innerHTML = Object.entries(rois).map(([zone, points]) => `<div><label><strong>${zone}</strong><textarea data-roi-zone="${zone}" rows="2">${escapeHtml(JSON.stringify(points))}</textarea></label><button data-save-roi="${zone}">儲存</button></div>`).join("");
}

async function loadSettings() {
  const settings = await api("/api/admin/settings");
  const values = Object.fromEntries(settings.map(item => [item.key, item.value]));
  document.querySelector("#setting-water").value = values.water_zone_hours || 8;
  document.querySelector("#setting-stay").value = values.long_stay_minutes || 60;
}

async function loadTasks() {
  const tasks = await api("/api/admin/tasks");
  document.querySelector("#system-task-list").innerHTML = tasks.map(task => `<div><span><strong>${escapeHtml(task.title)}</strong><small>${task.status === "DONE" ? `完成於 ${timeText(task.done_at)}` : "待處理"}</small></span><button class="table-action" data-task-id="${task.id}" data-next-task="${task.status === "DONE" ? "TODO" : "DONE"}">${task.status === "DONE" ? "重開" : "完成"}</button></div>`).join("");
}

async function loadAudit() {
  const logs = await api("/api/admin/audit?limit=30");
  document.querySelector("#audit-table-body").innerHTML = logs.map(item => `<tr><td>${timeText(item.created_at)}</td><td>${escapeHtml(item.actor_name)}</td><td><code>${escapeHtml(item.action)}</code></td><td>${escapeHtml(item.detail || "—")}</td></tr>`).join("");
}

async function refreshAll() {
  await Promise.all([loadOverview(), loadUsers(), loadAssignments(), loadRois(), loadSettings(), loadTasks(), loadAudit()]);
}

document.querySelector("#user-create-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const feedback = document.querySelector("#user-feedback");
  try {
    await api("/api/admin/users", { method: "POST", body: JSON.stringify(Object.fromEntries(form)) });
    event.currentTarget.reset(); feedback.textContent = "帳號已建立。";
    await Promise.all([loadUsers(), loadOverview(), loadAudit()]);
  } catch (error) { feedback.textContent = error.message; }
});

document.querySelector("#user-table-body").addEventListener("click", async event => {
  const button = event.target.closest("[data-user-id]"); if (!button) return;
  try { await api(`/api/admin/users/${button.dataset.userId}/status`, { method: "PATCH", body: JSON.stringify({ status: button.dataset.nextStatus }) }); await Promise.all([loadUsers(), loadAudit()]); }
  catch (error) { document.querySelector("#user-feedback").textContent = error.message; }
});

document.querySelector("#assignment-form").addEventListener("submit", async event => {
  event.preventDefault();
  await api("/api/admin/assignments", { method: "POST", body: JSON.stringify({ caregiver_id: Number(document.querySelector("#assignment-caregiver").value), pet_id: Number(document.querySelector("#assignment-pet").value), active: document.querySelector("#assignment-active").checked }) });
  await Promise.all([loadAssignments(), loadAudit()]);
});

document.querySelector("#roi-editor").addEventListener("click", async event => {
  const button = event.target.closest("[data-save-roi]"); if (!button) return;
  const textarea = document.querySelector(`[data-roi-zone="${button.dataset.saveRoi}"]`);
  try { const points = JSON.parse(textarea.value); await api(`/api/admin/rois/${button.dataset.saveRoi}`, { method: "PUT", body: JSON.stringify({ points }) }); button.textContent = "已儲存"; await loadAudit(); }
  catch (error) { button.textContent = `錯誤：${error.message}`; }
});

document.querySelector("#settings-form").addEventListener("submit", async event => {
  event.preventDefault(); const feedback = document.querySelector("#settings-feedback");
  try { await Promise.all([api("/api/admin/settings/water_zone_hours", { method: "PATCH", body: JSON.stringify({ value: Number(document.querySelector("#setting-water").value) }) }), api("/api/admin/settings/long_stay_minutes", { method: "PATCH", body: JSON.stringify({ value: Number(document.querySelector("#setting-stay").value) }) })]); feedback.textContent = "提醒門檻已更新。"; await loadAudit(); }
  catch (error) { feedback.textContent = error.message; }
});

document.querySelector("#system-task-form").addEventListener("submit", async event => {
  event.preventDefault(); const form = new FormData(event.currentTarget);
  await api("/api/admin/tasks", { method: "POST", body: JSON.stringify({ title: form.get("title") }) }); event.currentTarget.reset(); await Promise.all([loadTasks(), loadAudit()]);
});

document.querySelector("#system-task-list").addEventListener("click", async event => {
  const button = event.target.closest("[data-task-id]"); if (!button) return;
  await api(`/api/admin/tasks/${button.dataset.taskId}`, { method: "PATCH", body: JSON.stringify({ status: button.dataset.nextTask }) }); await Promise.all([loadTasks(), loadAudit()]);
});

refreshAll().catch(error => { document.querySelector("#admin-monitor-message").textContent = `系統資料讀取失敗：${error.message}`; });
setInterval(() => loadOverview().catch(() => {}), 10000);
