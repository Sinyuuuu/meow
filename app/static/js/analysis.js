const analysisZones = { FOOD: { label:"進食區", icon:"▰", color:"#f7ad78" }, WATER:{ label:"飲水區", icon:"●", color:"#72b9e5" }, LITTER:{ label:"貓砂區", icon:"◇", color:"#b994ce" } };
let selectedDays = 7;

async function getAnalytics(url) {
  const response = await fetch(url, { headers:{ Accept:"application/json" }, cache:"no-store" });
  if (response.status === 401) return window.location.assign("/login");
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
function shortDate(value) { return new Intl.DateTimeFormat("zh-TW", { month:"numeric", day:"numeric", timeZone:"Asia/Taipei" }).format(new Date(`${value}T12:00:00+08:00`)); }
function metric(row, basis) { return basis === "duration" ? `${Math.round(row.duration_seconds / 60)} 分` : `${row.event_count} 次`; }

function renderSummary(data) {
  const target=document.querySelector("#analysis-summary");
  const cards=Object.entries(analysisZones).map(([zone, meta])=>({ icon:meta.icon,label:meta.label,value:`${data.zones[zone].ratio}%`,note:metric(data.zones[zone],data.basis) }));
  cards.push({icon:"◷",label:data.basis==="duration"?"有效觀測總時長":"有效事件總數",value:data.basis==="duration"?`${Math.round(data.total_duration_seconds/60)} 分`:`${data.total_event_count} 次`,note:`${data.completed_interval_count} 個完成區段`});
  target.innerHTML=cards.map(card=>`<article class="cs-analysis-summary-card"><span>${card.icon}</span><small>${card.label}</small><strong>${card.value}</strong><p>${card.note}</p></article>`).join("");
}

function renderTrend(data) {
  const target=document.querySelector("#activity-trend");
  const rows=data.daily;
  const values=rows.flatMap(row=>Object.keys(analysisZones).map(zone=>data.basis==="duration"?row.zones[zone].duration_seconds:row.zones[zone].event_count));
  const max=Math.max(...values,1);
  target.innerHTML=rows.map(row=>{ const segments=Object.keys(analysisZones).map(zone=>{const value=data.basis==="duration"?row.zones[zone].duration_seconds:row.zones[zone].event_count;const height=Math.max(value?3:0,Math.round(value/max*210));return `<i class="${zone}" style="height:${height}px" title="${analysisZones[zone].label}：${data.basis==="duration"?`${Math.round(value/60)} 分鐘`:`${value} 次`}"></i>`}).join("");return `<div class="cs-day-column"><div class="cs-stack">${segments}</div><span>${shortDate(row.date)}</span></div>`}).join("");
  document.querySelector("#trend-unit").textContent=data.basis==="duration"?"每日完成區段停留時間":"尚無完整停留時間，改以每日事件數呈現";
}

function renderHeatmap(data) {
  const target=document.querySelector("#activity-heatmap");
  const max=Math.max(...data.heatmap.flatMap(row=>row.hours),1);
  const header=`<div class="cs-heat-header"><span></span>${Array.from({length:24},(_,h)=>`<span>${h%3===0?h:""}</span>`).join("")}</div>`;
  target.innerHTML=header+data.heatmap.map(row=>`<div class="cs-heat-row"><span>${shortDate(row.date)}</span>${row.hours.map((count,hour)=>{const level=count?Math.min(4,Math.ceil(count/max*4)):0;return `<button class="cs-heat-cell" data-level="${level}" title="${shortDate(row.date)} ${hour}:00 · ${count} 筆區域事件" aria-label="${shortDate(row.date)} ${hour}點 ${count}筆事件"></button>`}).join("")}</div>`).join("");
}

function renderRatio(data) {
  const target=document.querySelector("#zone-ratio");
  if (!data.total_duration_seconds && !data.total_event_count) { target.innerHTML='<div class="cs-empty"><span>◔</span><p>選定範圍內尚無活動資料。</p></div>'; return; }
  let angle=0;const segments=[];for(const [zone,meta] of Object.entries(analysisZones)){const next=angle+data.zones[zone].ratio*3.6;segments.push(`${meta.color} ${angle}deg ${next}deg`);angle=next;}
  target.innerHTML=`<div class="cs-donut" style="background:conic-gradient(${segments.join(",")})"><div class="cs-donut-center">${data.basis==="duration"?Math.round(data.total_duration_seconds/60):data.total_event_count}<small>${data.basis==="duration"?"分鐘":"事件"}</small></div></div><div class="cs-legend">${Object.entries(analysisZones).map(([zone,meta])=>`<div class="cs-legend-row"><i style="background:${meta.color}"></i><span>${meta.label}</span><b>${data.zones[zone].ratio}%</b></div>`).join("")}</div>`;
  document.querySelector("#ratio-title").textContent=data.basis==="duration"?"區域使用比例":"區域事件佔比";
}

function renderPaths(data) {
  const target=document.querySelector("#movement-paths");
  target.innerHTML=data.transitions.length?data.transitions.map((row,index)=>`<div class="cs-path-row"><span>${index+1}</span><strong>${analysisZones[row.from]?.label||row.from} → ${analysisZones[row.to]?.label||row.to}</strong><b>${row.count} 次</b></div>`).join(""):'<div class="cs-empty"><span>🐾</span><p>資料不足，尚無可統計的連續移動路徑。</p></div>';
}

function renderObservations(data) {
  const target=document.querySelector("#behavior-observations");
  if (!data.total_event_count) { target.innerHTML='<div class="cs-empty"><span>☀</span><p>等待累積更多活動資料後再提供趨勢觀察。</p></div>'; return; }
  const top=Object.entries(data.zones).sort((a,b)=>(data.basis==="duration"?b[1].duration_seconds-a[1].duration_seconds:b[1].event_count-a[1].event_count))[0];
  const activeHours=Array.from({length:24},(_,h)=>({h,count:data.heatmap.reduce((sum,row)=>sum+row.hours[h],0)})).sort((a,b)=>b.count-a.count).slice(0,3).filter(row=>row.count);
  const rows=[{icon:"↗",title:`${analysisZones[top[0]].label}比例最高`,body:`選定期間約 ${top[1].ratio}%（${metric(top[1],data.basis)}）。這是區域位置統計，不代表行為結果。`},{icon:"◷",title:"常見偵測時段",body:activeHours.length?`區域事件較集中在 ${activeHours.map(row=>`${row.h}:00`).join("、")}。資料覆蓋不足時可能偏差。`:"尚無足夠事件判斷時段。"},{icon:"♡",title:"判讀限制",body:"未偵測資料不會被視為休息；進食區與飲水區事件也不等同已確認進食或飲水。"}];
  target.innerHTML=rows.map(row=>`<div class="cs-observation"><span>${row.icon}</span><div><strong>${row.title}</strong><p>${row.body}</p></div></div>`).join("");
}

async function loadRange(url, updateQuery=true) {
  const status=document.querySelector("#analysis-status");status.textContent="正在讀取活動資料…";
  try { const data=await getAnalytics(url); renderSummary(data);renderTrend(data);renderHeatmap(data);renderRatio(data);renderPaths(data);renderObservations(data);status.textContent=`${data.range.start} ～ ${data.range.end} · ${data.total_event_count} 筆事件 · ${data.completed_interval_count} 個完成區段`;if(updateQuery){const params=new URLSearchParams(url.split("?")[1]||"");history.replaceState(null,"",`${location.pathname}?${params}`);}}
  catch(error){status.textContent="暫時無法讀取活動分析，請稍後重試。";document.querySelector("#analysis-summary").innerHTML='<div class="cs-empty compact">資料讀取失敗</div>';}
}

document.querySelectorAll("[data-days]").forEach(button=>button.addEventListener("click",()=>{document.querySelectorAll("[data-days]").forEach(item=>item.classList.toggle("active",item===button));const custom=button.dataset.days==="custom";document.querySelector("#custom-range").hidden=!custom;if(!custom){selectedDays=Number(button.dataset.days);loadRange(`/api/activities/analytics/range?days=${selectedDays}`);}}));
document.querySelector("#apply-range").addEventListener("click",()=>{const start=document.querySelector("#analysis-start").value;const end=document.querySelector("#analysis-end").value;if(!start||!end)return window.csToast("請選擇開始與結束日期","error");loadRange(`/api/activities/analytics/range?start=${start}&end=${end}`);});
const params=new URLSearchParams(location.search);if(params.has("start")&&params.has("end")){document.querySelector('[data-days="custom"]').click();document.querySelector("#analysis-start").value=params.get("start");document.querySelector("#analysis-end").value=params.get("end");loadRange(`/api/activities/analytics/range?start=${params.get("start")}&end=${params.get("end")}`,false);}else{const days=[7,30].includes(Number(params.get("days")))?Number(params.get("days")):7;document.querySelector(`[data-days="${days}"]`).click();}
