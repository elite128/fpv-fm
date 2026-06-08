let state = null;
let currentUser = localStorage.getItem("fpv_name") || "";
let pendingChannel = null;

const $ = (id) => document.getElementById(id);

// Toast Notifications
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2800);
}

// REST API Helper
async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Fehler");
  return data;
}

// WebSocket Live Synchronization
function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  
  ws.onopen = () => {
    $("connection").textContent = "online";
    $("connection").className = "pill online";
    ws.send(JSON.stringify({ type: "hello", name: currentUser }));
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

// HTML Escaper
function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>'"]/g, s => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[s]));
}

// Channel Dropdown Options Helper
function channelOptions(selected = "") {
  if (!state) return "";
  let html = `<option value="">kein Kanal</option>`;
  for (const group of state.all_channel_groups) {
    html += `<optgroup label="${escapeHtml(group.name)}">`;
    for (const c of group.channels) {
      const isSelected = c.name === selected ? "selected" : "";
      const owner = c.owner ? ` · ${c.owner}` : "";
      const locked = c.locked ? " · gesperrt" : "";
      html += `<option value="${escapeHtml(c.name)}" ${isSelected}>${escapeHtml(c.name)} · ${c.frequency} MHz${escapeHtml(owner)}${escapeHtml(locked)}</option>`;
    }
    html += `</optgroup>`;
  }
  return html;
}

// User Actions
async function join() {
  const name = $("nameInput").value.trim();
  if (!name) return toast("Bitte Namen eingeben");
  try {
    const data = await api("/api/join", { name });
    currentUser = data.name;
    localStorage.setItem("fpv_name", currentUser);
    toast(`Profil als ${currentUser} gespeichert`);
    render();
  } catch (e) {
    toast(e.message);
  }
}

async function selectChannel(channel, force = false) {
  if (!currentUser) return toast("Bitte trage zuerst deinen Pilotennamen ein!");
  try {
    const data = await api("/api/select-channel", { name: currentUser, channel, force });
    if (data.needs_confirm) {
      pendingChannel = channel;
      showConfirm(data);
      return;
    }
    toast(channel ? `${channel} erfolgreich belegt` : "Frequenz freigegeben");
  } catch (e) {
    toast(e.message);
  }
}

// Confirm dialog on overlaps
function showConfirm(data) {
  $("confirmText").textContent = `${data.channel} (${data.frequency} MHz) liegt sehr nah an belegten Frequenzen:`;
  $("confirmConflicts").innerHTML = data.conflicts.map(c =>
    `<div class="conflicts" style="color: var(--red); font-weight: 700; margin: 0.2rem 0;">
      ⚠ ${escapeHtml(c.channel || "?")} (${escapeHtml(c.pilot)}) · ${c.frequency} MHz (Abstand: ${c.diff} MHz)
     </div>`
  ).join("");
  $("confirmDialog").showModal();
}

// Main Render Loop
function render() {
  if (!state) return;
  $("version").textContent = `v${state.version}`;
  $("eventName").textContent = state.event_name;
  $("nameInput").value = currentUser || $("nameInput").value;
  $("serverUrl").textContent = state.server_url;
  $("displayUrl").textContent = state.display_url;
  $("qrCode").src = state.qr;
  $("stats").innerHTML = `
    <span>${state.stats.pilots} Piloten</span>
    <span>${state.stats.used_channels} Belegt</span>
    <span>${state.stats.conflicts} Konflikte</span>
    <span>${state.stats.locked} Gesperrt</span>
  `;
  renderPilots();
  renderChannelGroups();
  renderRecommendations();
  renderAdmin();
}

// Render Active Pilots
function renderPilots() {
  const list = $("pilotList");
  if (!state.pilots.length) {
    list.innerHTML = `<p class="muted" style="padding: 1rem 0;">Noch keine Piloten eingetragen.</p>`;
    return;
  }
  list.innerHTML = state.pilots.map(p => {
    const ch = p.channel || "Kein Kanal";
    const freq = p.frequency ? `${p.frequency} MHz` : "Nicht zugewiesen";
    const source = p.created_by === "admin" ? "Admin" : p.created_by === "import" ? "Import" : "Selbst";
    
    let conflictHtml = "";
    if (p.conflicts && p.conflicts.length > 0) {
      conflictHtml = p.conflicts.map(c => 
        `<span class="conflict-badge">⚠ ${escapeHtml(c.pilot)} (${c.diff} MHz)</span>`
      ).join("");
    } else if (p.frequency) {
      conflictHtml = `<span class="conflict-badge" style="color: var(--green);">✓ Sicher</span>`;
    }

    return `<div class="pilot-row ${p.severity}">
      <div class="pilot-row-left">
        <div>
          <span class="pilot-channel">${escapeHtml(ch)}</span>
          <span class="pilot-name">${escapeHtml(p.name)}</span>
        </div>
        <div class="pilot-freq">${freq} <span class="pilot-source">${source}</span></div>
      </div>
      <div class="pilot-row-right">
        <div class="conflicts-wrapper">
          ${conflictHtml}
        </div>
      </div>
    </div>`;
  }).join("");
}

// Render Grid Grid Channels
function renderChannelGroups() {
  const root = $("channelGroups");
  root.innerHTML = state.channel_groups.map(group => `
    <h3>${escapeHtml(group.name)}</h3>
    <div class="channel-grid">${group.channels.map(channelTile).join("")}</div>
  `).join("");
  document.querySelectorAll(".channel-tile[data-channel]").forEach(btn => {
    btn.addEventListener("click", () => selectChannel(btn.dataset.channel));
  });
}

function channelTile(c) {
  const mine = c.owner === currentUser;
  const used = Boolean(c.owner);
  let cls = "channel-tile";
  if (mine) cls += " mine";
  else if (used) cls += " used";
  if (c.locked) cls += " locked";
  if (!used && !c.locked && c.severity === "yellow") cls += " warn";
  if (!used && !c.locked && c.severity === "red") cls += " bad";
  const disabled = (used && !mine) || c.locked ? "disabled" : "";
  
  let status = "frei";
  if (c.locked) status = "gesperrt";
  else if (mine) status = "dein Kanal";
  else if (used) status = `belegt: ${c.owner}`;
  else if (c.severity === "yellow") status = "nah";
  else if (c.severity === "red") status = "kritisch nah";

  return `<button class="${cls}" data-channel="${escapeHtml(c.name)}" ${disabled} title="${escapeHtml(status)}">
    <span class="tile-name">${escapeHtml(c.name)}</span>
    <span class="tile-freq">${c.frequency} MHz</span>
    <span class="tile-owner">${used ? escapeHtml(c.owner) : ""}</span>
    <span class="tile-status">${status}</span>
  </button>`;
}

// Render Recommendations
function renderRecommendations() {
  const el = $("recommendations");
  if (!state.recommendations.length) {
    el.innerHTML = `<p class="muted" style="grid-column: 1/-1; padding: 0.5rem 0;">Keine konfliktfreien Kanäle frei.</p>`;
    return;
  }
  el.innerHTML = state.recommendations.map(c => `
    <button class="reco" data-reco="${escapeHtml(c.name)}">
      <strong>✓ ${escapeHtml(c.name)}</strong>
      <span>${c.frequency} MHz</span>
    </button>
  `).join("");
  document.querySelectorAll("[data-reco]").forEach(btn => {
    btn.addEventListener("click", () => selectChannel(btn.dataset.reco));
  });
}

// Render Admin Sections
function adminPassword() {
  return $("adminPassword").value;
}

function renderAdmin() {
  const addSel = $("adminAddChannel");
  const prevAdd = addSel.value;
  addSel.innerHTML = channelOptions(prevAdd);

  $("adminPilots").innerHTML = state.pilots.length ? state.pilots.map(p => `
    <div class="admin-row admin-pilot-row">
      <input value="${escapeHtml(p.name)}" data-edit-name="${escapeHtml(p.name)}" />
      <select data-edit-channel="${escapeHtml(p.name)}">${channelOptions(p.channel || "")}</select>
      <button data-save="${escapeHtml(p.name)}">Speichern</button>
      <button data-remove="${escapeHtml(p.name)}" class="danger">Entfernen</button>
    </div>`).join("") : `<p class="muted">Keine Piloten eingetragen.</p>`;

  $("adminChannels").innerHTML = state.all_channel_groups.map(group => `
    <div class="admin-group"><h4>${escapeHtml(group.name)}</h4><div class="admin-channel-grid">
      ${group.channels.map(c => `<button class="channel-tile ${c.locked ? "locked" : ""}" data-lock="${escapeHtml(c.name)}">
        <span class="tile-name">${escapeHtml(c.name)} ${c.locked ? "🔒" : ""}</span>
        <span class="tile-freq">${c.frequency} MHz</span>
        <span class="tile-status">${c.locked ? "freigeben" : "sperren"}</span>
      </button>`).join("")}
    </div></div>`).join("");

  document.querySelectorAll("[data-remove]").forEach(btn => {
    btn.addEventListener("click", async () => {
      try {
        await api("/api/admin/remove-pilot", { password: adminPassword(), name: btn.dataset.remove });
        toast("Pilot entfernt");
      } catch (e) { toast(e.message); }
    });
  });

  document.querySelectorAll("[data-save]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const oldName = btn.dataset.save;
      const name = document.querySelector(`[data-edit-name="${CSS.escape(oldName)}"]`).value;
      const channel = document.querySelector(`[data-edit-channel="${CSS.escape(oldName)}"]`).value || null;
      try {
        await api("/api/admin/update-pilot", { password: adminPassword(), old_name: oldName, name, channel, force: true });
        toast("Pilot aktualisiert");
      } catch (e) { toast(e.message); }
    });
  });

  document.querySelectorAll("[data-lock]").forEach(btn => {
    btn.addEventListener("click", async () => {
      try {
        await api("/api/admin/toggle-lock", { password: adminPassword(), channel: btn.dataset.lock });
        toast("Kanalstatus geändert");
      } catch (e) { toast(e.message); }
    });
  });

}

// PWA Install Prompt Mechanics
let deferredPrompt = null;
const installBtn = $("installBtn");

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  installBtn.style.display = "inline-flex";
});

installBtn.addEventListener("click", async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  console.log(`PWA Install Choice: ${outcome}`);
  deferredPrompt = null;
  installBtn.style.display = "none";
});

window.addEventListener("appinstalled", () => {
  installBtn.style.display = "none";
  deferredPrompt = null;
  toast("App erfolgreich installiert!");
});

// Theme Toggle (Light/Dark Daylight vs Goggles)
const themeToggleBtn = $("themeToggleBtn");
const sunIcon = $("themeIconSun");
const moonIcon = $("themeIconMoon");

function applyTheme(theme) {
  if (theme === "light") {
    document.body.classList.add("light-theme");
    sunIcon.style.display = "none";
    moonIcon.style.display = "block";
    const themeColor = document.querySelector("meta[name='theme-color']");
    if (themeColor) themeColor.setAttribute("content", "#f3f4f6");
  } else {
    document.body.classList.remove("light-theme");
    sunIcon.style.display = "block";
    moonIcon.style.display = "none";
    const themeColor = document.querySelector("meta[name='theme-color']");
    if (themeColor) themeColor.setAttribute("content", "#2563eb");
  }
}

let activeTheme = localStorage.getItem("fpv_theme") || "light";
applyTheme(activeTheme);

themeToggleBtn.addEventListener("click", () => {
  activeTheme = activeTheme === "dark" ? "light" : "dark";
  localStorage.setItem("fpv_theme", activeTheme);
  applyTheme(activeTheme);
});

// Network status listener
window.addEventListener("online", () => toast("Verbindung zum Netzwerk hergestellt"));
window.addEventListener("offline", () => toast("Sie sind offline. Zeige lokale Offline-Kopie."));

// Basic Event Listeners
$("joinBtn").addEventListener("click", join);
$("nameInput").addEventListener("keydown", e => { if (e.key === "Enter") join(); });
$("cancelSelect").addEventListener("click", () => $("confirmDialog").close());

$("forceSelect").addEventListener("click", async () => {
  $("confirmDialog").close();
  if (pendingChannel) await selectChannel(pendingChannel, true);
  pendingChannel = null;
});

$("copyLinkBtn").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(state.server_url); toast("Event-Link in Zwischenablage!"); }
  catch { toast(state.server_url); }
});

$("copyDisplayLinkBtn").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(state.display_url); toast("Display-Link in Zwischenablage!"); }
  catch { toast(state.display_url); }
});

$("adminAddBtn").addEventListener("click", async () => {
  try {
    await api("/api/admin/add-pilot", {
      password: adminPassword(),
      name: $("adminAddName").value,
      channel: $("adminAddChannel").value || null,
      force: true,
    });
    $("adminAddName").value = "";
    toast("Pilot hinzugefügt");
  } catch (e) { toast(e.message); }
});

$("bulkImportBtn").addEventListener("click", async () => {
  try {
    const data = await api("/api/admin/bulk-import", { password: adminPassword(), text: $("bulkImportText").value, force: true });
    toast(data.errors?.length ? `Importfehler: ${data.errors.join(" | ")}` : `${data.added.length} Piloten erfolgreich importiert`);
  } catch (e) { toast(e.message); }
});

$("resetBtn").addEventListener("click", async () => {
  if (!confirm("Rennleitungs-Warnung: Wirklich alle Piloten, Frequenzen und Sperren löschen?")) return;
  try { await api("/api/admin/reset", { password: adminPassword() }); toast("Event vollständig zurückgesetzt"); }
  catch (e) { toast(e.message); }
});

$("saveConfigBtn").addEventListener("click", async () => {
  try {
    await api("/api/admin/save-config", {
      password: adminPassword(),
      yaml_text: $("configYamlText").value
    });
    toast("Event-Konfiguration gespeichert!");
    configLoaded = true;
  } catch (e) { toast(e.message); }
});

let configLoaded = false;

async function tryLoadConfig() {
  const configArea = $("configYamlText");
  if (!configArea) return;

  const pwd = adminPassword();
  if (!pwd) {
    if (document.activeElement !== configArea) {
      configArea.value = "";
    }
    configArea.placeholder = "Bitte Passwort eingeben, um Konfiguration zu laden.";
    configArea.disabled = true;
    $("saveConfigBtn").disabled = true;
    configLoaded = false;
    return;
  }

  try {
    const data = await api("/api/admin/get-config", { password: pwd });
    if (document.activeElement !== configArea) {
      configArea.value = data.yaml_text;
    }
    configArea.disabled = false;
    $("saveConfigBtn").disabled = false;
    configLoaded = true;
  } catch (e) {
    if (document.activeElement !== configArea) {
      configArea.value = "";
    }
    configArea.placeholder = "Bitte korrektes Passwort eingeben, um Konfiguration zu laden.";
    configArea.disabled = true;
    $("saveConfigBtn").disabled = true;
    configLoaded = false;
  }
}

$("adminPassword").addEventListener("input", tryLoadConfig);

const adminDetails = document.querySelector(".admin-card details");
if (adminDetails) {
  adminDetails.addEventListener("toggle", (e) => {
    if (e.target.open) {
      tryLoadConfig();
    }
  });
}

// Register PWA Service Worker
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then((reg) => {
      console.log("ServiceWorker registered, scope: ", reg.scope);
    }).catch((err) => {
      console.error("ServiceWorker registration failed: ", err);
    });
  });
}

// Connect WebSocket
connectWs();
