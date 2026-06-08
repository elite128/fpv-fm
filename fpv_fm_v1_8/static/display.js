let state = null;
const $ = (id) => document.getElementById(id);

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>'"]/g, s => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[s]));
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  
  ws.onopen = () => {
    $("connection").textContent = "online";
    $("connection").className = "pill online";
  };
  
  ws.onclose = () => {
    $("connection").textContent = "offline";
    $("connection").className = "pill offline";
    setTimeout(connectWs, 2000);
  };
  
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "state") {
      state = msg.state;
      render();
    }
  };
}

function render() {
  if (!state) return;
  $("version").textContent = `v${state.version}`;
  $("eventName").textContent = state.event_name;
  $("stats").innerHTML = `
    <span>${state.stats.pilots} pilots</span>
    <span>${state.stats.used_channels} claimed channels</span>
    <span>${state.stats.conflicts} conflicts</span>
  `;
  
  const list = $("pilotList");
  if (!state.pilots.length) {
    list.innerHTML = `<div class="display-empty">No pilots registered on the frequency board yet.</div>`;
    return;
  }
  
  list.innerHTML = state.pilots.map(p => {
    const ch = p.channel || "-";
    const freq = p.frequency ? `${p.frequency} MHz` : "No channel";
    
    let conflicts = "✓ Frequency safe";
    if (p.conflicts && p.conflicts.length > 0) {
      conflicts = p.conflicts.map(c => `⚠ ${escapeHtml(c.pilot)} (${c.diff} MHz)`).join(" · ");
    }
    
    return `<div class="display-row ${p.severity}">
      <div class="display-row-top">
        <div class="display-channel-box">${escapeHtml(ch)}</div>
        <div class="display-name-text">${escapeHtml(p.name)}</div>
      </div>
      <div class="display-row-bottom">
        <span class="display-frequency">${freq}</span>
        <span class="display-conflicts">${conflicts}</span>
      </div>
    </div>`;
  }).join("");
}

connectWs();
