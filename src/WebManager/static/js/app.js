let isServerRunning = false;
let isRequestInFlight = false;
let isDisconnected = false;
let currentSection = "details";
let propertiesData = {};
let backupsData = [];
let lastLogs = "";
let serverStartTime = null;
let uptimeInterval = null;
let prevBackupsMap = new Map(); // name -> backup obj
let prevPropertiesMap = new Map(); // key -> value
let initialStatusLoadDone = false;
let refreshInFlight = false;
let refreshQueued = false;
let refreshOriginalHtml = null;
let backupsSortKey = "name";
let backupsSortDir = "asc"; // asc | desc
let autoRefreshTimer = null;

const STORAGE_KEYS = {
  sidebarCollapsed: "mcbsm.sidebarCollapsed",
  updateIntervalSec: "mcbsm.updateIntervalSec",
  lastSection: "mcbsm.lastSection",
};

// Bootstrap Instances
const editPropertyModal = new bootstrap.Modal(document.getElementById("editPropertyModal"));
const newBackupModal = new bootstrap.Modal(document.getElementById("newBackupModal"));
const backupProgressModal = new bootstrap.Modal(document.getElementById("backupProgressModal"));
const confirmModal = new bootstrap.Modal(document.getElementById("confirmModal"));
const disconnectedModal = new bootstrap.Modal(document.getElementById("disconnectedModal"));
const errorToast = new bootstrap.Toast(document.getElementById("errorToast"));
let backupProgressVisible = false;
const pageLoadingOverlay = document.getElementById("page-loading-overlay");

function showError(msg) {
  document.getElementById("errorToastBody").textContent = msg || "An internal error occurred.";
  errorToast.show();
}

// Selectors
const sidebarToggle = document.getElementById("menu-toggle");
const wrapper = document.getElementById("wrapper");
const toggleServerBtn = document.getElementById("toggleServerBtn");
const refreshBtn = document.getElementById("refreshBtn");
const reconnectBtn = document.getElementById("reconnectBtn");
const confirmNewBackupBtn = document.getElementById("confirmNewBackupBtn");
const sendCommandBtn = document.getElementById("sendCommandBtn");
const commandInput = document.getElementById("commandInput");
const serverLogs = document.getElementById("serverLogs");
const logsContainer = document.getElementById("logsContainer");
const connectionDetailsContainer = document.getElementById("connectionDetailsContainer");
const serverUptime = document.getElementById("serverUptime");
const uptimeCol = document.getElementById("uptimeCol");

function toggleSidebar() {
  wrapper.classList.toggle("toggled");
  try {
    localStorage.setItem(STORAGE_KEYS.sidebarCollapsed, wrapper.classList.contains("toggled") ? "1" : "0");
  } catch (_e) {}
}

function showSection(section) {
  currentSection = section;
  document.querySelectorAll("section").forEach((s) => s.classList.add("d-none"));
  document.getElementById(`section-${section}`).classList.remove("d-none");

  document.querySelectorAll(".nav-link").forEach((l) => {
    l.classList.remove("active");
    l.classList.add("text-white");
  });
  const activeLink = document.getElementById(`nav-${section}`);
  activeLink.classList.add("active");
  activeLink.classList.remove("text-white");

  if (window.innerWidth < 768) {
    wrapper.classList.remove("toggled");
  }

  try {
    localStorage.setItem(STORAGE_KEYS.lastSection, section);
  } catch (_e) {}
  if (location.hash !== `#${section}`) {
    history.replaceState(null, "", `#${section}`);
  }
}

function handleFetchError(err) {
  console.error("API Error:", err);
  if (!isDisconnected) {
    isDisconnected = true;
    disconnectedModal.show();
  }
}

async function sendCommand(action, data = null) {
  if (isRequestInFlight) return;
  isRequestInFlight = true;
  let shouldRefresh = false;

  if (action === "start_server") {
    updateToggleButton(true, "Starting server...");
  } else if (action === "stop_server") {
    updateToggleButton(true, "Stopping server...");
  }

  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, data }),
    });
    const result = await response.json();
    if (!response.ok) {
      showError(result.error);
      throw new Error(result.error || "Server response error");
    }
    if (result.success) {
      shouldRefresh = true;
    }
  } catch (err) {
    handleFetchError(err);
  } finally {
    isRequestInFlight = false;
    if (shouldRefresh) refreshStatus();
  }
}

function updateToggleButton(disabled, text) {
  toggleServerBtn.disabled = disabled;
  toggleServerBtn.querySelector(".btn-text").textContent = text;
  if (disabled) {
    toggleServerBtn.querySelector(".spinner-border").classList.remove("d-none");
  } else {
    toggleServerBtn.querySelector(".spinner-border").classList.add("d-none");
  }
}

async function refreshStatus() {
  if (refreshInFlight) {
    refreshQueued = true;
    return;
  }
  refreshInFlight = true;
  const originalHtml = refreshOriginalHtml ?? refreshBtn.innerHTML;
  refreshOriginalHtml = originalHtml;
  refreshBtn.disabled = true;
  refreshBtn.innerHTML =
    '<span class="ios-spinner me-md-1" aria-hidden="true">' +
    '<span class="bar"></span><span class="bar"></span><span class="bar"></span><span class="bar"></span><span class="bar"></span><span class="bar"></span>' +
    '<span class="bar"></span><span class="bar"></span><span class="bar"></span><span class="bar"></span><span class="bar"></span><span class="bar"></span>' +
    '</span><span class="d-none d-md-inline">Refreshing...</span>';

  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    if (!response.ok) {
      showError(data.error);
      throw new Error(data.error || "Status check failed");
    }

    if (isDisconnected) {
      isDisconnected = false;
      disconnectedModal.hide();
    }

    updateUI(data);
  } catch (err) {
    handleFetchError(err);
  } finally {
    if (!initialStatusLoadDone) {
      initialStatusLoadDone = true;
      if (pageLoadingOverlay) {
        pageLoadingOverlay.classList.add("hidden");
        setTimeout(() => pageLoadingOverlay.remove(), 250);
      }
    }
    refreshInFlight = false;
    setTimeout(() => {
      refreshBtn.disabled = false;
      refreshBtn.innerHTML = refreshOriginalHtml ?? originalHtml;
    }, 250);
    if (refreshQueued) {
      refreshQueued = false;
      setTimeout(refreshStatus, 0);
    }
  }
}

function formatDuration(seconds) {
  if (seconds < 0) return "00:00:00";
  const h = Math.floor(seconds / 3600).toString().padStart(2, "0");
  const m = Math.floor((seconds % 3600) / 60).toString().padStart(2, "0");
  const s = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function updateUptimeDisplay() {
  if (isServerRunning && serverStartTime) {
    const now = Date.now() / 1000;
    const delta = now - serverStartTime;
    serverUptime.textContent = formatDuration(delta);
  } else {
    serverUptime.textContent = "--:--:--";
  }
}

function updateUI(data) {
  const bedrock = data.bedrock || {};
  const web = data.web_manager || {};
  const players = data.players || [];
  const operators = new Set(data.operators || []);
  const logs = data.logs || [];
  const network = data.network || {};
  propertiesData = data.properties || {};
  backupsData = data.backups || [];
  serverStartTime = data.server_start_time;

  // Server Details
  isServerRunning = bedrock.running;
  const stateText = isServerRunning ? "Running" : "Stopped";
  document.getElementById("serverState").textContent = stateText;
  document.getElementById("statusDot").className = `rounded-circle ${isServerRunning ? "bg-success" : "bg-secondary"}`;

  if (!isRequestInFlight) {
    const btnText = isServerRunning ? "Stop Server" : "Start Server";
    updateToggleButton(false, btnText);
    toggleServerBtn.className = `btn shadow-sm ${isServerRunning ? "btn-outline-danger" : "btn-primary"}`;
  }

  document.getElementById("playerCount").textContent = bedrock.connected || 0;
  document.getElementById("playerLimit").textContent = `Max: ${bedrock.max_players || "-"}`;
  const serverPortEl = document.getElementById("serverPort");
  if (serverPortEl) serverPortEl.textContent = bedrock.port || "-";
  document.getElementById("serverGamemode").textContent = bedrock.gamemode || "-";

  if (isServerRunning) {
    if (!uptimeInterval) uptimeInterval = setInterval(updateUptimeDisplay, 1000);
    updateUptimeDisplay();
  } else {
    if (uptimeInterval) {
      clearInterval(uptimeInterval);
      uptimeInterval = null;
    }
    serverUptime.textContent = "--:--:--";
  }

  // Show uptime only while running. Animate with scale/opacity, but change layout widths only after animation.
  const topStats = document.querySelector("#section-details .top-stats-row");
  if (topStats && uptimeCol) {
    const statusCol = topStats.querySelector('[data-stat="status"]');
    const playersCol = topStats.querySelector('[data-stat="players"]');
    const gamemodeCol = topStats.querySelector('[data-stat="gamemode"]');
    const setCol = (el, md) => {
      if (!el) return;
      el.classList.remove("col-md-3", "col-md-4");
      el.classList.add(md);
    };

    if (isServerRunning) {
      // Layout first, then animate uptime in (no width animation).
      setCol(statusCol, "col-md-3");
      setCol(playersCol, "col-md-3");
      setCol(gamemodeCol, "col-md-3");
      setCol(uptimeCol, "col-md-3");
      uptimeCol.classList.remove("d-none", "animate-out");
      uptimeCol.classList.add("animate-in");
    } else {
      // Animate uptime out while keeping 4-up layout, then switch to 3-up.
      if (!uptimeCol.classList.contains("d-none") && !uptimeCol.classList.contains("animate-out")) {
        uptimeCol.classList.remove("animate-in");
        uptimeCol.classList.add("animate-out");
        setTimeout(() => {
          if (isServerRunning) return;
          uptimeCol.classList.add("d-none");
          setCol(statusCol, "col-md-4");
          setCol(playersCol, "col-md-4");
          setCol(gamemodeCol, "col-md-4");
        }, 300);
      } else if (uptimeCol.classList.contains("d-none")) {
        setCol(statusCol, "col-md-4");
        setCol(playersCol, "col-md-4");
        setCol(gamemodeCol, "col-md-4");
      }
    }
  }

  if (document.getElementById("localIp")) {
    document.getElementById("localIp").textContent = network.local_ip || "-";
    document.getElementById("gamePort").textContent = network.port || "-";
    document.getElementById("localUrl").textContent =
      network.local_ip && network.port ? `${network.local_ip}:${network.port}` : "-";
  }

  if (isServerRunning) {
    [logsContainer, connectionDetailsContainer].forEach((container) => {
      if (container && container.classList.contains("d-none")) {
        container.classList.remove("d-none");
        container.classList.remove("animate-out");
        container.classList.add("animate-in");
      }
    });
    const logsText = logs.join("");
    if (logsText !== lastLogs) {
      serverLogs.innerText = logsText;
      serverLogs.scrollTop = serverLogs.scrollHeight;
      lastLogs = logsText;
    }
  } else {
    [logsContainer, connectionDetailsContainer].forEach((container) => {
      if (container && !container.classList.contains("d-none") && !container.classList.contains("animate-out")) {
        container.classList.remove("animate-in");
        container.classList.add("animate-out");
        setTimeout(() => {
          if (!isServerRunning) {
            container.classList.add("d-none");
            if (container === logsContainer) serverLogs.innerText = "";
          }
        }, 400);
      }
    });
    lastLogs = "";
  }

  // Player List
  const playerList = document.getElementById("playerList");
  const noPlayersMsg = document.getElementById("noPlayersMsg");
  playerList.innerHTML = "";
  if (players.length > 0) {
    noPlayersMsg.classList.add("d-none");
    players.forEach((p) => {
      const isOp = operators.has(p);
      const li = document.createElement("li");
      li.className = "list-group-item bg-transparent border-secondary d-flex align-items-center";
      li.innerHTML = `
        <i class="bi bi-person-fill me-2 text-primary"></i>
        <span class="flex-grow-1">${p}</span>
        ${isOp ? '<span class="badge text-bg-warning text-dark ms-2">OP</span>' : ""}
      `;
      playerList.appendChild(li);
    });
  } else {
    noPlayersMsg.classList.remove("d-none");
  }

  // Web Interface Info
  document.getElementById("webHost").textContent = web.host || "-";
  document.getElementById("webPort").textContent = web.port || "-";

  const webLocalUrl = network.local_ip && web.port ? `http://${network.local_ip}:${web.port}` : "-";
  if (document.getElementById("webLocalUrl")) {
    document.getElementById("webLocalUrl").textContent = webLocalUrl;
    document.getElementById("webLocalUrl").href = webLocalUrl !== "-" ? webLocalUrl : "#";
  }

  document.getElementById("webUrl").textContent = web.url || "-";
  document.getElementById("webUrl").href = web.url || "#";

  renderPropertiesTable(true);
  renderBackupsTable(true);

  // Backup Progress
  const backupInProgress = !!data.backup_in_progress;
  if (backupInProgress && !backupProgressVisible) {
    backupProgressModal.show();
    backupProgressVisible = true;
  } else if (!backupInProgress && backupProgressVisible) {
    backupProgressModal.hide();
    backupProgressVisible = false;
  }
  if (data.backup_error) {
    showError(data.backup_error);
  }
}

function renderPropertiesTable(animateDiff) {
  const propsBody = document.getElementById("propertiesTableBody");
  if (!propsBody) return;
  propsBody.innerHTML = "";
  const propKeys = Object.keys(propertiesData).sort();
  const propsCount = document.getElementById("propsCount");
  if (propsCount) propsCount.textContent = `${propKeys.length} items`;
  const nextPropertiesMap = new Map();
  propKeys.forEach((key) => {
    nextPropertiesMap.set(key, propertiesData[key]);
    const isAdded = animateDiff && !prevPropertiesMap.has(key);
    const tr = document.createElement("tr");
    if (isAdded) tr.classList.add("row-flash-add");
    tr.innerHTML = `
      <td class="fw-medium text-info">${key}</td>
      <td><code>${propertiesData[key]}</code></td>
      <td class="d-none d-md-table-cell" style="width: 140px;">
        <button class="btn btn-sm btn-light w-100 edit-icon" title="Edit" onclick="openEditProperty('${key}', '${propertiesData[key].replace(/'/g, "\\\\'")}')">
          <i class="bi bi-pencil me-1"></i> Edit
        </button>
      </td>
    `;
    tr.onclick = (e) => {
      if (!e.target.closest("button")) openEditProperty(key, propertiesData[key]);
    };
    propsBody.appendChild(tr);
  });
  if (animateDiff) {
    for (const [key, value] of prevPropertiesMap.entries()) {
      if (nextPropertiesMap.has(key)) continue;
      const tr = document.createElement("tr");
      tr.classList.add("row-flash-remove");
      tr.innerHTML = `
        <td class="fw-medium text-info">${key}</td>
        <td><code>${value}</code></td>
        <td class="d-none d-md-table-cell" style="width: 140px;"></td>
      `;
      propsBody.appendChild(tr);
      setTimeout(() => tr.remove(), 1000);
    }
  }
  prevPropertiesMap = nextPropertiesMap;
}

function renderBackupsTable(animateDiff) {
  const backupsBody = document.getElementById("backupsTableBody");
  const noBackupsMsg = document.getElementById("noBackupsMsg");
  if (!backupsBody || !noBackupsMsg) return;
  backupsBody.innerHTML = "";
  const nextBackupsMap = new Map();
  const sortedBackups = [...backupsData].sort((a, b) => compareBackups(a, b));
  if (sortedBackups.length > 0) {
    noBackupsMsg.classList.add("d-none");
    sortedBackups.forEach((b) => {
      nextBackupsMap.set(b.name, b);
      const isAdded = animateDiff && !prevBackupsMap.has(b.name);
      const tr = document.createElement("tr");
      if (isAdded) tr.classList.add("row-flash-add");
      tr.innerHTML = `
        <td class="fw-medium">${b.name}</td>
        <td><span class="badge text-bg-dark border border-secondary">${b.size}</span></td>
        <td class="small text-muted">${b.modified}</td>
        <td>
          <div class="d-flex w-100 gap-2">
            <button class="btn btn-sm btn-outline-primary flex-fill" onclick="confirmRestore('${b.name}')" title="Restore">
              <i class="bi bi-arrow-counterclockwise"></i>
            </button>
            <button class="btn btn-sm btn-outline-danger flex-fill" onclick="confirmDelete('${b.name}')" title="Delete">
              <i class="bi bi-trash"></i>
            </button>
          </div>
        </td>
      `;
      backupsBody.appendChild(tr);
    });
  } else {
    noBackupsMsg.classList.remove("d-none");
  }
  if (animateDiff) {
    for (const [name, b] of prevBackupsMap.entries()) {
      if (nextBackupsMap.has(name)) continue;
      const tr = document.createElement("tr");
      tr.classList.add("row-flash-remove");
      tr.innerHTML = `
        <td class="fw-medium">${b.name}</td>
        <td><span class="badge text-bg-dark border border-secondary">${b.size || ""}</span></td>
        <td class="small text-muted">${b.modified || ""}</td>
        <td></td>
      `;
      backupsBody.appendChild(tr);
      setTimeout(() => tr.remove(), 1000);
    }
  }
  prevBackupsMap = nextBackupsMap;
}

function compareBackups(a, b) {
  const dir = backupsSortDir === "asc" ? 1 : -1;
  if (backupsSortKey === "modified") {
    const at = Number(a.timestamp ?? 0);
    const bt = Number(b.timestamp ?? 0);
    if (at !== bt) return (at - bt) * dir;
  } else if (backupsSortKey === "size") {
    const as = parseSizeToBytes(a.size);
    const bs = parseSizeToBytes(b.size);
    if (as !== bs) return (as - bs) * dir;
  } else {
    const an = String(a.name ?? "").toLowerCase();
    const bn = String(b.name ?? "").toLowerCase();
    if (an !== bn) return an < bn ? -1 * dir : 1 * dir;
  }
  const an2 = String(a.name ?? "").toLowerCase();
  const bn2 = String(b.name ?? "").toLowerCase();
  if (an2 === bn2) return 0;
  return an2 < bn2 ? -1 : 1;
}

function parseSizeToBytes(sizeText) {
  if (!sizeText) return 0;
  const m = String(sizeText).trim().match(/^([0-9]+(?:\\.[0-9]+)?)\\s*([KMGT]?B)$/i);
  if (!m) return 0;
  const value = Number(m[1]);
  const unit = m[2].toUpperCase();
  const multipliers = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, TB: 1024 ** 4 };
  return Math.round(value * (multipliers[unit] || 1));
}

function openEditProperty(key, value) {
  document.getElementById("propKey").value = key;
  document.getElementById("propValue").value = value;
  editPropertyModal.show();
}

document.getElementById("savePropertyBtn").onclick = () => {
  const key = document.getElementById("propKey").value;
  const value = document.getElementById("propValue").value;
  sendCommand("update_property", { key, value });
  editPropertyModal.hide();
};

function confirmDelete(name) {
  document.getElementById("confirmTitle").textContent = "Delete Backup";
  document.getElementById("confirmText").innerHTML = `Are you sure you want to delete backup <strong>${name}</strong>? This action cannot be undone.`;
  const btn = document.getElementById("confirmActionBtn");
  btn.className = "btn btn-danger";
  btn.textContent = "Delete";
  btn.onclick = () => {
    refreshStatus();
    sendCommand("delete_backup", { name });
    confirmModal.hide();
  };
  confirmModal.show();
}

function confirmRestore(name) {
  document.getElementById("confirmTitle").textContent = "Restore Backup";
  document.getElementById("confirmText").innerHTML = `Are you sure you want to restore <strong>${name}</strong>? Current world data will be moved to an 'Old_' folder.`;
  const btn = document.getElementById("confirmActionBtn");
  btn.className = "btn btn-primary";
  btn.textContent = "Restore";
  btn.onclick = () => {
    refreshStatus();
    sendCommand("restore_backup", { name });
    confirmModal.hide();
  };
  confirmModal.show();
}

function openNewBackupModal() {
  const timestamp = new Date()
    .toISOString()
    .replace(/T/, "_")
    .replace(/\\..+/, "")
    .replace(/-/g, "")
    .replace(/:/g, "");
  document.getElementById("backupName").value = `web-backup-${timestamp}`;
  newBackupModal.show();
}

async function handleSendCommand() {
  const command = commandInput.value.trim();
  if (command && isServerRunning) {
    commandInput.disabled = true;
    sendCommandBtn.disabled = true;
    const originalBtnHtml = sendCommandBtn.innerHTML;
    sendCommandBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>';

    try {
      await sendCommand("send_command", { command });
      commandInput.value = "";
    } finally {
      commandInput.disabled = false;
      sendCommandBtn.disabled = false;
      sendCommandBtn.innerHTML = originalBtnHtml;
      commandInput.focus();
    }
  }
}

sendCommandBtn.onclick = handleSendCommand;
commandInput.onkeydown = (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    handleSendCommand();
  }
};

confirmNewBackupBtn.onclick = async () => {
  const name = document.getElementById("backupName").value;
  if (!name) return;
  if (isRequestInFlight) return;
  confirmNewBackupBtn.disabled = true;
  try {
    refreshStatus();
    backupProgressModal.show();
    backupProgressVisible = true;
    await sendCommand("new_backup", { name });
    newBackupModal.hide();
  } finally {
    confirmNewBackupBtn.disabled = false;
  }
};

document.getElementById("newBackupBtn").onclick = openNewBackupModal;

toggleServerBtn.onclick = () => {
  sendCommand(isServerRunning ? "stop_server" : "start_server");
};

reconnectBtn.onclick = refreshStatus;
refreshBtn.onclick = refreshStatus;
sidebarToggle.onclick = toggleSidebar;

// Init
initSettingsUI();
initFromHash();
initBackupSorting();
startAutoRefresh();
refreshStatus();

function initBackupSorting() {
  const nameTh = document.getElementById("backupsSortName");
  const sizeTh = document.getElementById("backupsSortSize");
  const modTh = document.getElementById("backupsSortModified");
  if (!nameTh || !sizeTh || !modTh) return;
  nameTh.onclick = () => toggleBackupsSort("name");
  sizeTh.onclick = () => toggleBackupsSort("size");
  modTh.onclick = () => toggleBackupsSort("modified");
  updateBackupsSortIndicators();
}

function toggleBackupsSort(key) {
  if (backupsSortKey === key) {
    backupsSortDir = backupsSortDir === "asc" ? "desc" : "asc";
  } else {
    backupsSortKey = key;
    backupsSortDir = "asc";
  }
  // Re-render without flashing add/remove since this is just a re-order.
  prevBackupsMap = new Map(backupsData.map((b) => [b.name, b]));
  renderBackupsTable(false);
  updateBackupsSortIndicators();
}

function updateBackupsSortIndicators() {
  const headers = [
    { el: document.getElementById("backupsSortName"), key: "name" },
    { el: document.getElementById("backupsSortSize"), key: "size" },
    { el: document.getElementById("backupsSortModified"), key: "modified" },
  ];
  headers.forEach(({ el, key }) => {
    if (!el) return;
    el.classList.remove("sort-active", "sort-asc", "sort-desc");
    if (key === backupsSortKey) {
      el.classList.add("sort-active", backupsSortDir === "asc" ? "sort-asc" : "sort-desc");
    }
  });
}

function initSettingsUI() {
  try {
    const collapsed = localStorage.getItem(STORAGE_KEYS.sidebarCollapsed);
    if (collapsed === "1") wrapper.classList.add("toggled");
  } catch (_e) {}

  const slider = document.getElementById("updateIntervalSlider");
  const label = document.getElementById("updateIntervalLabel");
  if (!slider || !label) return;

  let sec = 5;
  try {
    const stored = Number(localStorage.getItem(STORAGE_KEYS.updateIntervalSec));
    if (Number.isFinite(stored) && stored >= 2 && stored <= 30) sec = stored;
  } catch (_e) {}
  slider.value = String(sec);
  label.textContent = String(sec);

  slider.oninput = () => {
    const v = Number(slider.value);
    label.textContent = String(v);
  };
  slider.onchange = () => {
    const v = Math.max(2, Math.min(30, Number(slider.value)));
    label.textContent = String(v);
    try {
      localStorage.setItem(STORAGE_KEYS.updateIntervalSec, String(v));
    } catch (_e) {}
    startAutoRefresh();
  };
}

function startAutoRefresh() {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer);
  let sec = 5;
  try {
    const stored = Number(localStorage.getItem(STORAGE_KEYS.updateIntervalSec));
    if (Number.isFinite(stored) && stored >= 2 && stored <= 30) sec = stored;
  } catch (_e) {}
  autoRefreshTimer = setInterval(refreshStatus, sec * 1000);
}

function initFromHash() {
  function normalize(hash) {
    const h = (hash || "").replace(/^#/, "").trim();
    return h || null;
  }
  const fromHash = normalize(location.hash);
  let section = fromHash;
  if (!section) {
    try {
      section = localStorage.getItem(STORAGE_KEYS.lastSection) || "details";
    } catch (_e) {
      section = "details";
    }
  }
  showSection(section);
  window.addEventListener("hashchange", () => {
    const next = normalize(location.hash);
    if (next) showSection(next);
  });
}
