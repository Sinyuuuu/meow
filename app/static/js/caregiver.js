const zoneLabels = { FOOD: "進食區", WATER: "飲水區", LITTER: "貓砂區", GENERAL: "一般活動範圍" };

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { Accept: "application/json", "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 401) window.location.assign("/login");
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function localTime(value) {
  return new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

async function loadTasks() {
  const tasks = await api("/api/care/tasks");
  const completed = tasks.filter(task => task.completed).length;
  document.querySelector("#task-progress").textContent = `${completed} / ${tasks.length}`;
  document.querySelector("#care-task-list").innerHTML = tasks.map(task => `
    <label class="care-task ${task.completed ? "done" : ""}">
      <input type="checkbox" data-task-id="${task.id}" ${task.completed ? "checked" : ""}>
      <span class="task-check">✓</span><time>${escapeHtml(task.scheduled_time)}</time>
      <strong>${escapeHtml(task.task_type)}</strong><small>${task.completed ? "已完成" : "待完成"}</small>
    </label>`).join("");
  document.querySelectorAll("[data-task-id]").forEach(input => input.addEventListener("change", async event => {
    const checkbox = event.currentTarget;
    checkbox.disabled = true;
    try {
      await api(`/api/care/tasks/${checkbox.dataset.taskId}`, { method: "PATCH", body: JSON.stringify({ completed: checkbox.checked }) });
      await loadTasks();
    } catch (error) {
      checkbox.checked = !checkbox.checked;
      checkbox.disabled = false;
    }
  }));
}

async function loadLogs() {
  const logs = await api("/api/care/logs?limit=6");
  const target = document.querySelector("#care-log-list");
  if (!logs.length) return;
  target.innerHTML = logs.map(log => `<div class="care-log-item"><span>✎</span><div><strong>${escapeHtml(log.type)}</strong><p>${escapeHtml(log.note)}</p><small>${localTime(log.created_at)}</small></div></div>`).join("");
}

async function loadAlerts() {
  const alerts = await api("/api/alerts");
  document.querySelector("#active-alert-count").textContent = alerts.filter(alert => !alert.resolved).length;
}

function updateMonitor(status) {
  const badge = document.querySelector("#monitor-running-badge");
  badge.textContent = status.running ? "MONITORING" : "OFFLINE";
  badge.classList.toggle("is-online", status.running);
  document.querySelector("#monitor-message").textContent = status.message || "監測尚未啟動";
  document.querySelector("#monitor-dot").parentElement.classList.toggle("offline", !status.running);
  document.querySelector("#care-zone").textContent = status.current_zone ? zoneLabels[status.current_zone] : "等待偵測";
  document.querySelector("#care-confidence").textContent = status.detected ? `confidence ${Number(status.confidence).toFixed(2)}` : "未偵測到 cat";
  if (status.frame_count > 0) {
    const image = document.querySelector("#care-live-frame");
    image.src = `/api/monitor/frame?t=${Date.now()}`;
    image.classList.remove("is-missing");
  }
}

async function loadMonitor() {
  updateMonitor(await api("/api/monitor/status"));
}

document.querySelector("#start-monitor").addEventListener("click", async () => {
  const feedback = document.querySelector("#monitor-feedback");
  feedback.textContent = "正在載入模型…";
  try {
    const raw = document.querySelector("#monitor-source").value.trim();
    const source = /^\d+$/.test(raw) ? Number(raw) : raw;
    const status = await api("/api/monitor/start", { method: "POST", body: JSON.stringify({ source, detector: document.querySelector("#monitor-detector").value, save_annotated_video: document.querySelector("#save-video").checked }) });
    updateMonitor(status); feedback.textContent = "啟動要求已送出。";
  } catch (error) { feedback.textContent = `啟動失敗：${error.message}`; }
});

document.querySelector("#stop-monitor").addEventListener("click", async () => {
  const feedback = document.querySelector("#monitor-feedback");
  try { updateMonitor(await api("/api/monitor/stop", { method: "POST", body: "{}" })); feedback.textContent = "正在安全停止監測。"; }
  catch (error) { feedback.textContent = `停止失敗：${error.message}`; }
});

document.querySelector("#care-log-form").addEventListener("submit", async event => {
  event.preventDefault();
  const feedback = document.querySelector("#care-log-feedback");
  const note = document.querySelector("#care-log-note");
  try {
    await api("/api/care/logs", { method: "POST", body: JSON.stringify({ type: document.querySelector("#care-log-type").value, note: note.value }) });
    note.value = ""; feedback.textContent = "照護紀錄已儲存。"; await loadLogs();
  } catch (error) { feedback.textContent = `儲存失敗：${error.message}`; }
});

Promise.all([loadTasks(), loadLogs(), loadAlerts(), loadMonitor()]).catch(() => {});
setInterval(() => loadMonitor().catch(() => {}), 2500);
