async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (response.status === 401) window.location.assign("/login");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "—").replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function localTime(value) {
  return new Intl.DateTimeFormat("zh-TW", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

async function loadPetPage() {
  const [pet, logs] = await Promise.all([getJson("/api/pets/current"), getJson("/api/care/logs?limit=8")]);
  document.querySelector("#pet-basic").textContent = `${pet.gender || "性別未填"} · ${pet.age ?? "—"} 歲 · ${pet.breed || "品種未填"} · ${pet.weight ?? "—"} kg`;
  document.querySelector("#pet-personality").textContent = pet.personality || "—";
  document.querySelector("#pet-food").textContent = pet.food_notes || "—";
  document.querySelector("#pet-care").textContent = pet.care_notes || "—";
  document.querySelector("#pet-medical").textContent = pet.medical_notes || "—";
  if (logs.length) document.querySelector("#owner-care-logs").innerHTML = logs.map(log => `<div class="care-log-item"><span>✎</span><div><strong>${escapeHtml(log.type)}</strong><p>${escapeHtml(log.note)}</p><small>${localTime(log.created_at)}</small></div></div>`).join("");
}

loadPetPage().catch(() => { document.querySelector("#pet-basic").textContent = "暫時無法讀取資料"; });
