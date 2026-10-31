const petZones = { FOOD: { label: "進食區", icon: "▰" }, WATER: { label: "飲水區", icon: "●" }, LITTER: { label: "貓砂區", icon: "◇" } };
let currentPet = null;

async function requestJson(url, options = {}) {
  const response = await fetch(url, { headers: { Accept: "application/json", ...(options.headers || {}) }, ...options });
  if (response.status === 401) return window.location.assign("/login");
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) { const error = new Error(data?.detail?.message || data?.detail || `HTTP ${response.status}`); error.status = response.status; throw error; }
  return data;
}
function escapeHtml(value) { return String(value ?? "").replace(/[&<>'"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c])); }
function selectedDay() { return document.querySelector("#pet-day").value; }
function timeText(value) { return new Intl.DateTimeFormat("zh-TW", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)); }
function todayTaipei() { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date()); }

function showPet(pet) {
  currentPet = pet;
  document.querySelector("#pet-name").textContent = pet.name;
  document.querySelector("#pet-gender").textContent = pet.gender || "";
  document.querySelector("#pet-summary").textContent = `${pet.age != null ? `${pet.age} 歲` : "年齡未填"} · ${pet.breed || "品種未填"}`;
  document.querySelector("#pet-age").textContent = pet.age != null ? `${pet.age} 歲` : "尚未填寫";
  document.querySelector("#pet-weight").textContent = pet.weight != null ? `${pet.weight} kg` : "尚未填寫";
  document.querySelector("#pet-breed").textContent = pet.breed || "尚未填寫";
  document.querySelector("#pet-personality").textContent = pet.personality || "尚未填寫";
  const image = document.querySelector("#pet-photo");
  if (pet.photo) { image.src = pet.photo; image.hidden = false; document.querySelector("#pet-photo-fallback").hidden = true; }
  else { image.hidden = true; document.querySelector("#pet-photo-fallback").hidden = false; }
}

function zoneSummary(records) {
  const stats = Object.fromEntries(Object.keys(petZones).map(zone => [zone, { seconds: 0, count: 0 }]));
  records.forEach(row => { if (stats[row.zone]) { stats[row.zone].count += 1; stats[row.zone].seconds += Number(row.duration_seconds || 0); } });
  const totalSeconds = Object.values(stats).reduce((sum, row) => sum + row.seconds, 0);
  const target = document.querySelector("#pet-zone-summary");
  const hasAny = Object.values(stats).some(row => row.count);
  if (!hasAny) { target.innerHTML = '<div class="cs-empty compact">這天尚無可用的 AI 區域紀錄。</div>'; return stats; }
  target.innerHTML = Object.entries(petZones).map(([zone, meta]) => {
    const value = stats[zone]; const ratio = totalSeconds ? Math.round(value.seconds / totalSeconds * 100) : 0;
    return `<div class="cs-zone-tile ${zone.toLowerCase()}"><span>${meta.icon}</span><strong>${totalSeconds ? `${ratio}%` : `${value.count} 次`}</strong><b>${meta.label}</b><small>${value.seconds ? `${Math.round(value.seconds / 60)} 分鐘` : `${value.count} 筆事件`}</small></div>`;
  }).join("");
  document.querySelector("#zone-basis").textContent = totalSeconds ? `有效觀測 ${Math.round(totalSeconds / 60)} 分鐘` : "目前只有事件次數，尚無完成停留時間";
  return stats;
}

function renderTimeline(records) {
  const target = document.querySelector("#pet-daily-records");
  if (!records.length) { target.innerHTML = '<div class="cs-empty"><span>🐾</span><p>這天沒有 AI 區域紀錄。</p></div>'; return; }
  target.innerHTML = records.map(row => `<details class="cs-timeline-item"><time>${timeText(row.entered_at)}</time><span>${petZones[row.zone]?.icon || "🐾"}</span><div><strong>${escapeHtml(row.zone_label)}</strong><p>${row.left_at ? `離開 ${timeText(row.left_at)} · 停留 ${Math.round((row.duration_seconds || 0) / 60)} 分鐘` : "目前區段尚未結束"}</p><small>這是區域事件，不代表已完成進食或飲水。</small></div></details>`).join("");
}

function renderDailyAnalysis(stats) {
  const colors = { FOOD: "#f7ad78", WATER: "#72b9e5", LITTER: "#b994ce" };
  const total = Object.values(stats).reduce((sum, row) => sum + row.seconds, 0);
  const donut = document.querySelector("#daily-donut");
  const observations = document.querySelector("#daily-observations");
  if (!total) { donut.innerHTML = '<div class="cs-empty"><span>◔</span><p>沒有完整停留區段，無法計算比例。</p></div>'; observations.innerHTML = '<div class="cs-empty compact">資料不足，等待更多有效區域紀錄。</div>'; return; }
  let angle = 0; const segments = [];
  for (const [zone, row] of Object.entries(stats)) { const next = angle + row.seconds / total * 360; segments.push(`${colors[zone]} ${angle}deg ${next}deg`); angle = next; }
  donut.innerHTML = `<div class="cs-donut" style="background:conic-gradient(${segments.join(",")})"><div class="cs-donut-center">${Math.round(total / 60)}<small>分鐘</small></div></div><div class="cs-legend">${Object.entries(stats).map(([zone,row]) => `<div class="cs-legend-row"><i style="background:${colors[zone]}"></i><span>${petZones[zone].label}</span><b>${Math.round(row.seconds / total * 100)}%</b></div>`).join("")}</div>`;
  const top = Object.entries(stats).sort((a,b) => b[1].seconds - a[1].seconds)[0];
  observations.innerHTML = `<div class="cs-observation"><span>☀</span><div><strong>有效觀測最多：${petZones[top[0]].label}</strong><p>當日已完成區段中約 ${Math.round(top[1].seconds / 60)} 分鐘；這只是位置統計。</p></div></div><div class="cs-observation"><span>♡</span><div><strong>判讀界線</strong><p>無偵測資料不會被推定為休息，進食區事件也不等同確認進食。</p></div></div>`;
}

function renderWeightChart(rows) {
  const target = document.querySelector("#weight-chart");
  const good = [...rows].reverse().filter(row => Number.isFinite(Number(row.filtered_weight_grams)));
  if (!good.length) { target.innerHTML = '<div class="cs-empty"><span>▥</span><p>尚無量測資料。</p></div>'; return; }
  const values = good.map(row => Number(row.filtered_weight_grams)); const min = Math.min(...values); const max = Math.max(...values); const range = Math.max(max - min, 1);
  const points = values.map((value, index) => `${10 + index * (280 / Math.max(values.length - 1, 1))},${170 - (value - min) / range * 130}`);
  target.innerHTML = `<svg viewBox="0 0 300 190" role="img" aria-label="食碗重量折線圖"><line class="axis" x1="10" y1="170" x2="290" y2="170"/><polyline class="plot" points="${points.join(" ")}"/>${points.map((point,index) => { const [x,y]=point.split(","); return `<circle cx="${x}" cy="${y}" r="4"><title>${values[index].toFixed(1)} g · ${timeText(good[index].measured_at)}</title></circle>`; }).join("")}<text x="10" y="187">${timeText(good[0].measured_at)}</text><text x="252" y="187">${timeText(good.at(-1).measured_at)}</text></svg>`;
}

function renderCareSummary(records, logs, feedings) {
  const entries = [
    ...records.slice(0,3).map(row => ({ icon: petZones[row.zone]?.icon || "🐾", title: `進入${row.zone_label}`, detail: timeText(row.entered_at), at: row.entered_at })),
    ...logs.slice(0,2).map(row => ({ icon: "✎", title: row.type, detail: row.note, at: row.created_at })),
    ...feedings.filter(row => row.status === "CANDIDATE").slice(0,2).map(row => ({ icon: "▰", title: "食碗重量下降候選", detail: `${Number(row.estimated_consumed_grams).toFixed(1)} g · 待確認`, at: row.started_at })),
  ].sort((a,b) => new Date(b.at)-new Date(a.at)).slice(0,5);
  document.querySelector("#daily-care-summary").innerHTML = entries.length ? entries.map(row => `<div class="cs-summary-row"><span>${row.icon}</span><div><strong>${escapeHtml(row.title)}</strong><small>${escapeHtml(row.detail)}</small></div><time>${timeText(row.at)}</time></div>`).join("") : '<div class="cs-empty compact">這天尚無照護摘要。</div>';
  document.querySelector("#owner-care-logs").innerHTML = logs.length ? logs.slice(0,4).map(row => `<div class="cs-mini-row"><span>✎</span><div><strong>${escapeHtml(row.type)}</strong><small>${escapeHtml(row.note)}</small></div><time>${timeText(row.created_at)}</time></div>`).join("") : '<div class="cs-empty compact">目前尚無照護留言。</div>';
}

async function renderReminderPreview() {
  const target = document.querySelector("#pet-reminder-preview");
  try {
    const rows = await requestJson("/api/healthcare/reminders");
    const pending = rows.filter(row => !row.completed).slice(0,3);
    target.innerHTML = pending.length ? pending.map(row => `<div class="cs-mini-row"><span>♡</span><div><strong>${escapeHtml(row.title)}</strong><small>${new Date(row.scheduled_at).toLocaleDateString("zh-TW", { timeZone:"Asia/Taipei" })}</small></div></div>`).join("") : '<div class="cs-empty compact">目前沒有待處理提醒。</div>';
  } catch (error) { target.innerHTML = error.status === 503 ? '<div class="cs-empty compact">照護提醒功能等待資料庫 migration 啟用。</div>' : '<div class="cs-empty compact">暫時無法讀取提醒。</div>'; }
}

async function loadDay() {
  const day = selectedDay();
  const [records, logs, measurements, feedings, devices] = await Promise.all([
    requestJson(`/api/activities?day=${day}`), requestJson("/api/care/logs?limit=8"), requestJson(`/api/iot/pet-measurements?day=${day}&limit=300`), requestJson("/api/feeding/events?limit=30"), requestJson("/api/iot/pet-status"),
  ]);
  const stats = zoneSummary(records); renderTimeline(records); renderDailyAnalysis(stats); renderWeightChart(measurements); renderCareSummary(records, logs, feedings.filter(row => row.started_at.startsWith(day)));
  const latest = measurements[0];
  document.querySelector("#current-bowl-weight").textContent = latest ? `${Number(latest.filtered_weight_grams).toFixed(1)} g` : "—";
  document.querySelector("#current-bowl-time").textContent = latest ? `${timeText(latest.measured_at)} · ${latest.simulated ? "模擬資料" : "實體量測"}` : "尚無量測資料";
  const device = devices[0]; document.querySelector("#weight-device-status").textContent = device ? `${device.status === "ONLINE" ? "在線" : "離線"}${device.simulated ? " · 模擬裝置" : ""}` : "尚未綁定感測器";
}

document.querySelector("#pet-day").value = todayTaipei();
document.querySelector("#pet-day").addEventListener("change", () => loadDay().catch(() => window.csToast("無法載入指定日期", "error")));
document.querySelectorAll(".cs-tabs [data-tab]").forEach(button => button.addEventListener("click", () => {
  document.querySelectorAll(".cs-tabs [data-tab]").forEach(item => { item.classList.toggle("active", item === button); item.setAttribute("aria-selected", String(item === button)); });
  document.querySelectorAll("[data-panel]").forEach(panel => { panel.hidden = panel.dataset.panel !== button.dataset.tab; });
}));
document.querySelector("#pet-photo-button").addEventListener("click", () => document.querySelector("#pet-photo-input").click());
document.querySelector("#pet-photo-input").addEventListener("change", async event => {
  const file = event.target.files[0]; if (!file) return;
  if (!/^image\/(jpeg|png|webp)$/.test(file.type) || file.size > 5*1024*1024) return window.csToast("請選擇 5MB 以下的 JPEG、PNG 或 WebP", "error");
  const body = new FormData(); body.append("photo", file);
  try { const result = await requestJson("/api/pets/current/photo", { method:"POST", body }); currentPet.photo = result.photo; showPet(currentPet); window.csToast("貓咪照片已更新"); } catch (error) { window.csToast(error.message, "error"); }
});
const dialog = document.querySelector("#pet-edit-dialog");
document.querySelector("#edit-pet").addEventListener("click", () => { const form=document.querySelector("#pet-edit-form"); for (const key of ["name","gender","age","breed","weight","personality","food_notes","care_notes","medical_notes"]) form.elements[key].value=currentPet[key]??""; dialog.showModal(); });
document.querySelector("#pet-edit-form").addEventListener("submit", async event => { event.preventDefault(); const form=event.currentTarget; const payload=Object.fromEntries(new FormData(form)); ["age","weight"].forEach(key=>{ if(payload[key]!=="") payload[key]=Number(payload[key]); else delete payload[key]; }); try{currentPet=await requestJson("/api/pets/current",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});showPet(currentPet);dialog.close();window.csToast("基本資料已儲存");}catch(error){window.csToast(error.message,"error");} });

Promise.all([requestJson("/api/pets/current"), renderReminderPreview()]).then(async ([pet]) => { showPet(pet); await loadDay(); }).catch(() => window.csToast("部分資料暫時無法讀取", "error"));
