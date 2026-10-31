const analysisZones = [
  ["FOOD", "進食區"], ["WATER", "飲水區"], ["LITTER", "貓砂區"]
];

async function loadAnalysis() {
  const chart = document.querySelector("#bar-chart");
  try {
    const response = await fetch("/api/activities/summary");
    if (response.status === 401) return window.location.assign("/login");
    if (!response.ok) throw new Error(`${response.status}`);
    const payload = await response.json();
  const values = analysisZones.map(([key, label]) => ({ key, label, seconds: payload.zones[key].duration_seconds }));
  const max = Math.max(...values.map(item => item.seconds), 1);
  document.querySelector("#bar-chart").innerHTML = values.map(item => {
    const height = Math.max(2, Math.round(item.seconds / max * 88));
    const minutes = Math.round(item.seconds / 60);
    return `<div class="bar-column"><span class="bar-value">${minutes} 分</span><i class="bar" style="height:${height}%"></i><span class="bar-label">${item.label}</span></div>`;
  }).join("");
  const sorted = [...values].sort((a, b) => b.seconds - a.seconds);
  if (sorted[0].seconds > 0) {
    document.querySelector("#top-zone-title").textContent = `Momo 今天最常待在${sorted[0].label}`;
    document.querySelector("#top-zone-copy").textContent = `目前完成的活動區段中，${sorted[0].label}累計約 ${Math.round(sorted[0].seconds / 60)} 分鐘。`;
  }
  document.querySelector("#analysis-legend").innerHTML = values.map((item, index) => `<div class="legend-item"><i style="filter:hue-rotate(${index * 35}deg)"></i><span>${item.label}</span><b>${Math.round(item.seconds / 60)} 分鐘</b></div>`).join("");
  } catch (error) {
    chart.innerHTML = '<div class="empty-state"><span>!</span><p>暫時無法讀取區域分析。</p></div>';
  }
}
loadAnalysis();
