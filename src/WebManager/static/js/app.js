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
let lastChatLogLine = null;
let mentionPlayers = [];

const STORAGE_KEYS = {
  sidebarCollapsed: "mcbsm.sidebarCollapsed",
  updateIntervalSec: "mcbsm.updateIntervalSec",
  lastSection: "mcbsm.lastSection",
};
const CHAT_STORAGE_KEY = "mcbsm.chatMessages";

const MOTD_COLOR_MAP = {
  "0": "#000000",
  "1": "#0000AA",
  "2": "#00AA00",
  "3": "#00AAAA",
  "4": "#AA0000",
  "5": "#AA00AA",
  "6": "#FFAA00",
  "7": "#AAAAAA",
  "8": "#555555",
  "9": "#5555FF",
  "a": "#55FF55",
  "b": "#55FFFF",
  "c": "#FF5555",
  "d": "#FF55FF",
  "e": "#FFFF55",
  "f": "#FFFFFF",
};
const MOTD_OBFUSCATION_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const MOTD_ANIMATION_INTERVAL_MS = 100;

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
const serverBackendSelectSettings = document.getElementById("serverBackendSelectSettings");
const autostartServerCheckboxSettings = document.getElementById("autostartServerCheckboxSettings");
const confirmNewBackupBtn = document.getElementById("confirmNewBackupBtn");
const sendCommandBtn = document.getElementById("sendCommandBtn");
const commandInput = document.getElementById("commandInput");
const commandMentionPopup = document.getElementById("commandMentionPopup");
const commandMentionList = document.getElementById("commandMentionList");
const serverLogs = document.getElementById("serverLogs");
const logsContainer = document.getElementById("logsContainer");
const connectionDetailsContainer = document.getElementById("connectionDetailsContainer");
const serverUptime = document.getElementById("serverUptime");
const uptimeCol = document.getElementById("uptimeCol");
const motdInput = document.getElementById("motdInput");
const motdPreview = document.getElementById("motdPreview");
const motdColorButton = document.getElementById("motdColorButton");
const motdColorModalEl = document.getElementById("motdColorModal");
const motdColorModal = motdColorModalEl ? new bootstrap.Modal(motdColorModalEl) : null;
let motdPreviewHasObfuscated = false;
let motdAnimationTick = 0;
let motdAnimationTimer = null;
const macroGrid = document.getElementById("macroGrid");
const quickMacroModalEl = document.getElementById("quickMacroModal");
const quickMacroModal = quickMacroModalEl ? new bootstrap.Modal(quickMacroModalEl) : null;
const quickMacroModalTitle = document.getElementById("quickMacroModalTitle");
const quickMacroForm = document.getElementById("quickMacroForm");
const quickMacroIconInput = document.getElementById("quickMacroIcon");
const quickMacroCustomIconWrapper = document.getElementById("quickMacroCustomIconWrapper");
const quickMacroCustomIconInput = document.getElementById("quickMacroCustomIcon");
const quickMacroTitleInput = document.getElementById("quickMacroTitle");
const quickMacroCommandsInput = document.getElementById("quickMacroCommands");
const quickMacroTriggerSelect = document.getElementById("quickMacroTrigger");
const quickMacroIntervalInput = document.getElementById("quickMacroInterval");
const quickMacroIdInput = document.getElementById("quickMacroId");
const quickMacroDeleteBtn = document.getElementById("quickMacroDeleteBtn");
const quickMacroTriggerBtn = document.getElementById("openQuickMacroModalBtn");
const presetMacroGrid = document.getElementById("presetMacroGrid");
const exportMacrosBtn = document.getElementById("exportMacrosBtn");
const importMacrosBtn = document.getElementById("importMacrosBtn");
const importMacrosFile = document.getElementById("importMacrosFile");
const propertyModalTitle = document.getElementById("propertyModalTitle");
const propKeyInput = document.getElementById("propKey");
const propValueInput = document.getElementById("propValue");
const newPropertyBtn = document.getElementById("newPropertyBtn");
const consoleOfflineMessage = document.getElementById("consoleOfflineMessage");
const chatMessagesList = document.getElementById("chatMessagesList");
const chatRecipientLabel = document.getElementById("chatRecipientLabel");
const chatRecipientBtn = document.getElementById("chatRecipientBtn");
const chatRecipientDropdownMenu = document.getElementById("chatRecipientDropdownMenu");
const chatRecipientPlayersMenu = document.getElementById("chatRecipientPlayersMenu");
const chatRecipientPlayersHint = document.getElementById("chatRecipientPlayersHint");
const chatInput = document.getElementById("chatInput");
const chatSendBtn = document.getElementById("chatSendBtn");
const chatPanel = document.getElementById("chatPanel");
const toolboxSendEveryoneBtn = document.getElementById("toolboxSendEveryoneBtn");
const toolboxCopyBtn = document.getElementById("toolboxCopyBtn");
const toolboxCopyToggleBtn = document.getElementById("toolboxCopyToggleBtn");
const toolboxCopyLabel = document.getElementById("toolboxCopyLabel");
const toolboxCopyDropdownMenu = document.getElementById("toolboxCopyDropdownMenu");
const resourceUsageRow = document.getElementById("resourceUsageRow");
const cpuVBar = document.getElementById("cpuVBar");
const memVBar = document.getElementById("memVBar");
const cpuUsageText = document.getElementById("cpuUsageText");
const memUsageText = document.getElementById("memUsageText");
const memRssText = document.getElementById("memRssText");
const cpuChart = document.getElementById("cpuChart");
const memChart = document.getElementById("memChart");
let quickMacros = [];
let presetMacros = [];
const CHAT_MESSAGE_LIMIT = 120;
const CHAT_LOG_TAIL_FALLBACK = 20;
let chatRecipient = { id: "@a", label: "Everyone", icon: "bi-at" };
const chatMessages = [];
let lastAnimatedChatUid = null;
const CPU_HISTORY_LIMIT = 60;
const MEM_HISTORY_LIMIT = 60;
const cpuHistory = [];
const memHistory = [];
let previousServerRunning = null;
let toolboxCopyType = "say";

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
  if (section === "macros") {
    fetchQuickMacros();
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

async function sendServerCommand(command) {
  const trimmed = String(command || "").trim();
  if (!trimmed) return;
  return sendCommand("send_command", { command: trimmed });
}

async function sendServerCommands(commands) {
  for (const cmd of (commands || []).map((c) => String(c || "").trim()).filter(Boolean)) {
    await sendServerCommand(cmd);
  }
}

function downloadJson(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 250);
}

async function exportMacros() {
  try {
    const response = await fetch("/api/macros");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Failed to export macros");
    const macros = data.macros || [];
    downloadJson("mcbsm-macros.json", macros);
  } catch (err) {
    showError(err.message || "Failed to export macros.");
  }
}

async function importMacrosFromFile(file) {
  if (!file) return;
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    const macros = Array.isArray(parsed) ? parsed : parsed && Array.isArray(parsed.macros) ? parsed.macros : null;
    if (!macros) throw new Error("Invalid file. Expected a JSON array of macros.");
    await sendCommand("import_macros", { macros });
    fetchQuickMacros();
  } catch (err) {
    showError(err.message || "Failed to import macros.");
  } finally {
    if (importMacrosFile) importMacrosFile.value = "";
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
  const originalHtml = refreshOriginalHtml != null ? refreshOriginalHtml : refreshBtn.innerHTML;
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
    refreshBtn.innerHTML = refreshOriginalHtml != null ? refreshOriginalHtml : originalHtml;
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
  mentionPlayers = Array.isArray(players) ? players.map((p) => String(p || "").trim()).filter(Boolean) : [];
  const operators = new Set(data.operators || []);
  const logs = data.logs || [];
  const network = data.network || {};
  propertiesData = data.properties || {};
  backupsData = data.backups || [];
  serverStartTime = data.server_start_time;

  // Server Details
  if (previousServerRunning !== null && previousServerRunning !== bedrock.running) {
    resetChatHistory();
    lastChatLogLine = null;
  }
  isServerRunning = bedrock.running;
  const stateText = isServerRunning ? "Running" : "Stopped";
  document.getElementById("serverState").textContent = stateText;
  document.getElementById("statusDot").className = `rounded-circle ${isServerRunning ? "bg-success" : "bg-secondary"}`;
  const backendText = bedrock.backend ? String(bedrock.backend) : "-";
  const backendLabel = backendText === "-" ? "Backend: -" : `Backend: ${backendText}`;
  const backendEl = document.getElementById("serverBackend");
  if (backendEl) {
    backendEl.textContent = backendLabel;
    if (isServerRunning) backendEl.classList.add("is-visible");
    else backendEl.classList.remove("is-visible");
  }
  const backendPref = (bedrock.backend_preference || "auto").toString().toLowerCase();
  if (serverBackendSelectSettings) {
    serverBackendSelectSettings.value = backendPref === "endstone" ? "endstone" : backendPref === "bedrock" ? "bedrock" : "auto";
    serverBackendSelectSettings.disabled = isServerRunning || isRequestInFlight;
  }
  if (autostartServerCheckboxSettings) {
    autostartServerCheckboxSettings.checked = Boolean(bedrock.autostart_server);
    autostartServerCheckboxSettings.disabled = isRequestInFlight;
  }

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

  // Resource usage (server process)
  if (resourceUsageRow) {
    if (isServerRunning) {
      resourceUsageRow.classList.remove("d-none", "animate-out");
      resourceUsageRow.classList.add("animate-in");
    } else if (!resourceUsageRow.classList.contains("d-none") && !resourceUsageRow.classList.contains("animate-out")) {
      resourceUsageRow.classList.remove("animate-in");
      resourceUsageRow.classList.add("animate-out");
      setTimeout(() => {
        if (isServerRunning) return;
        resourceUsageRow.classList.remove("animate-out");
        resourceUsageRow.classList.add("d-none");
      }, 300);
    }

    const cpu = Number(bedrock.cpu_percent);
    const mem = Number(bedrock.mem_percent);
    const rssBytes = Number(bedrock.mem_rss_bytes);
    if (isServerRunning && Number.isFinite(cpu) && Number.isFinite(mem)) {
      pushMetric(cpuHistory, cpu, CPU_HISTORY_LIMIT);
      pushMetric(memHistory, mem, MEM_HISTORY_LIMIT);
      renderResourceCharts();
      if (cpuUsageText) cpuUsageText.textContent = Math.max(0, Math.round(cpu)).toString();
      if (memUsageText) memUsageText.textContent = Math.max(0, Math.round(mem)).toString();
      if (cpuVBar) cpuVBar.style.height = `${Math.min(100, Math.max(0, cpu))}%`;
      if (memVBar) memVBar.style.height = `${Math.min(100, Math.max(0, mem))}%`;
      if (memRssText) memRssText.textContent = Number.isFinite(rssBytes) && rssBytes > 0 ? `${formatBytes(rssBytes)} RSS` : "-";
    } else if (!isServerRunning) {
      cpuHistory.length = 0;
      memHistory.length = 0;
      renderResourceCharts(true);
      if (cpuUsageText) cpuUsageText.textContent = "-";
      if (memUsageText) memUsageText.textContent = "-";
      if (cpuVBar) cpuVBar.style.height = "0%";
      if (memVBar) memVBar.style.height = "0%";
      if (memRssText) memRssText.textContent = "-";
    }
  }

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
      el.classList.remove("col-md-3", "col-md-4", "col-md-6");
      el.classList.add(md);
    };
    const showPlayersCard = () => {
      if (!playersCol) return;
      playersCol.classList.remove("d-none", "animate-out");
      playersCol.classList.add("animate-in");
      setCol(playersCol, "col-md-3");
    };
    const hidePlayersCard = () => {
      if (!playersCol) return;
      if (playersCol.classList.contains("d-none") || playersCol.classList.contains("animate-out")) return;
      playersCol.classList.remove("animate-in");
      playersCol.classList.add("animate-out");
      setTimeout(() => {
        if (isServerRunning) return;
        playersCol.classList.remove("animate-out");
        playersCol.classList.add("d-none");
      }, 300);
    };

    if (isServerRunning) {
      // Layout first, then animate uptime in (no width animation).
      setCol(statusCol, "col-md-3");
      setCol(gamemodeCol, "col-md-3");
      showPlayersCard();
      setCol(uptimeCol, "col-md-3");
      uptimeCol.classList.remove("d-none", "animate-out");
      uptimeCol.classList.add("animate-in");
    } else {
      hidePlayersCard();
      setCol(statusCol, "col-md-6");
      setCol(gamemodeCol, "col-md-6");
      // Animate uptime out while keeping 4-up layout, then switch to 2-up.
      if (!uptimeCol.classList.contains("d-none") && !uptimeCol.classList.contains("animate-out")) {
        uptimeCol.classList.remove("animate-in");
        uptimeCol.classList.add("animate-out");
        setTimeout(() => {
          if (isServerRunning) return;
          uptimeCol.classList.add("d-none");
        }, 300);
      } else if (uptimeCol.classList.contains("d-none")) {
        setCol(statusCol, "col-md-6");
        setCol(gamemodeCol, "col-md-6");
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
    ingestChatFromLogs(logs);
    const logsText = logs.join("");
    if (logsText !== lastLogs) {
      serverLogs.innerText = logsText;
      requestAnimationFrame(() => {
        serverLogs.scrollTop = serverLogs.scrollHeight;
      });
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
    lastChatLogLine = null;
  }

  if (chatPanel) {
    if (isServerRunning) {
      chatPanel.classList.remove("d-none");
      chatPanel.classList.remove("animate-out");
      chatPanel.classList.add("animate-in");
    } else {
      chatPanel.classList.add("d-none");
      chatPanel.classList.remove("animate-in");
    }
  }

  if (consoleOfflineMessage) {
    consoleOfflineMessage.classList.toggle("d-none", isServerRunning);
  }
  if (chatInput) chatInput.disabled = !isServerRunning;
  if (chatSendBtn) chatSendBtn.disabled = !isServerRunning;
  if (chatRecipientBtn) chatRecipientBtn.disabled = !isServerRunning;

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
  updateChatPlayersList(players);

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
  updateToolboxSendButtonState();
  previousServerRunning = isServerRunning;
}

function initCommandMentions() {
  if (!commandInput || !commandMentionPopup || !commandMentionList) return;
  let activeIndex = 0;
  let lastAtIndex = null;
  let lastQueryEnd = null;

  function hidePopup() {
    commandMentionPopup.classList.add("d-none");
    commandMentionList.innerHTML = "";
    activeIndex = 0;
    lastAtIndex = null;
    lastQueryEnd = null;
  }

  function showPopup() {
    commandMentionPopup.classList.remove("d-none");
  }

  function renderList(items) {
    commandMentionList.innerHTML = "";
    items.forEach((item, idx) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = `list-group-item list-group-item-action ${idx === activeIndex ? "active" : ""}`;
      el.textContent = item.label;
      el.dataset.value = item.value;
      el.onclick = () => applySelection(item.value);
      commandMentionList.appendChild(el);
    });
  }

  function applySelection(value) {
    const text = commandInput.value || "";
    const cursor = typeof commandInput.selectionStart === "number" ? commandInput.selectionStart : text.length;
    const atIndex = lastAtIndex;
    const endIndex = lastQueryEnd ?? cursor;
    if (typeof atIndex !== "number" || atIndex < 0) return;
    const before = text.slice(0, atIndex);
    const after = text.slice(endIndex);
    const next = `${before}${value}${after}`;
    commandInput.value = next;
    const newCursor = before.length + value.length;
    commandInput.setSelectionRange(newCursor, newCursor);
    hidePopup();
    commandInput.focus();
  }

  function buildItems(query) {
    const q = String(query || "").toLowerCase();
    const filtered = mentionPlayers.filter((name) => name.toLowerCase().includes(q));
    const items = filtered.map((name) => {
      const selector = `@p[name=${JSON.stringify(name)}]`;
      return { label: name, value: selector };
    });
    items.push({ label: "Everyone", value: "@a" });
    return items;
  }

  function updatePopupFromInput() {
    const text = commandInput.value || "";
    const cursor = typeof commandInput.selectionStart === "number" ? commandInput.selectionStart : text.length;
    const atIndex = text.lastIndexOf("@", cursor - 1);
    if (atIndex < 0) return hidePopup();
    const query = text.slice(atIndex + 1, cursor);
    if (/\s|\[|\]/.test(query)) return hidePopup();
    lastAtIndex = atIndex;
    lastQueryEnd = cursor;
    const items = buildItems(query);
    if (items.length === 0) return hidePopup();
    activeIndex = Math.max(0, Math.min(activeIndex, items.length - 1));
    renderList(items);
    showPopup();
  }

  commandInput.addEventListener("input", () => {
    activeIndex = 0;
    updatePopupFromInput();
  });

  commandInput.addEventListener("keydown", (e) => {
    if (commandMentionPopup.classList.contains("d-none")) return;
    const items = Array.from(commandMentionList.querySelectorAll("[data-value]"));
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopImmediatePropagation();
      hidePopup();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      e.stopImmediatePropagation();
      activeIndex = Math.min(items.length - 1, activeIndex + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      e.stopImmediatePropagation();
      activeIndex = Math.max(0, activeIndex - 1);
    } else if (e.key === "Enter") {
      const el = items[activeIndex];
      if (!el) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      applySelection(el.dataset.value);
      return;
    } else {
      return;
    }
    items.forEach((el, idx) => el.classList.toggle("active", idx === activeIndex));
    items[activeIndex]?.scrollIntoView({ block: "nearest" });
  });

  commandInput.addEventListener("blur", () => {
    setTimeout(() => hidePopup(), 120);
  });
}

function pushMetric(list, value, limit) {
  list.push(value);
  while (list.length > limit) list.shift();
}

function sparklineSvg(values, color) {
  const width = 100;
  const height = 30;
  if (!Array.isArray(values) || values.length < 2) {
    return `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none"></svg>`;
  }
  const clamped = values.map((v) => Math.min(100, Math.max(0, Number(v))));
  const step = width / Math.max(1, clamped.length - 1);
  const points = clamped
    .map((v, idx) => {
      const x = (idx * step).toFixed(2);
      const y = (height - (v / 100) * height).toFixed(2);
      return `${x},${y}`;
    })
    .join(" ");
  return `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
      <polyline
        fill="none"
        stroke="${color}"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        points="${points}"
      />
    </svg>
  `;
}

function renderResourceCharts(clear = false) {
  if (cpuChart) cpuChart.innerHTML = clear ? "" : sparklineSvg(cpuHistory, "rgba(77, 171, 255, 0.95)");
  if (memChart) memChart.innerHTML = clear ? "" : sparklineSvg(memHistory, "rgba(255, 193, 7, 0.95)");
}

function formatBytes(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let idx = 0;
  let val = n;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx += 1;
  }
  const digits = idx === 0 ? 0 : idx === 1 ? 0 : 1;
  return `${val.toFixed(digits)} ${units[idx]}`;
}

function initServerBackendSettingsSelect() {
  if (!serverBackendSelectSettings) return;
  serverBackendSelectSettings.addEventListener("change", () => {
    const backend = (serverBackendSelectSettings.value || "").trim().toLowerCase();
    if (!backend) return;
    if (isServerRunning) return;
    sendCommand("set_server_backend", { backend });
  });
}

function initAutostartServerSettingsToggle() {
  if (!autostartServerCheckboxSettings) return;
  autostartServerCheckboxSettings.addEventListener("change", () => {
    const enabled = Boolean(autostartServerCheckboxSettings.checked);
    sendCommand("set_autostart_server", { enabled });
  });
}

function initDropdownCloseAnimations() {
  if (typeof bootstrap === "undefined" || !bootstrap.Dropdown) return;
  document.addEventListener("hide.bs.dropdown", (e) => {
    const toggle = e.target;
    if (!toggle) return;
    const dropdownRoot = toggle.closest?.(".dropdown") || toggle.parentElement;
    const menu = dropdownRoot?.querySelector?.(".dropdown-menu.show");
    if (!menu) return;
    if (menu.dataset.allowHide === "1") {
      delete menu.dataset.allowHide;
      menu.classList.remove("dropdown-closing");
      return;
    }

    e.preventDefault();
    menu.classList.add("dropdown-closing");
    const instance = bootstrap.Dropdown.getInstance(toggle) || new bootstrap.Dropdown(toggle);
    window.setTimeout(() => {
      menu.dataset.allowHide = "1";
      instance.hide();
    }, 220);
  });
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
    const at = Number(a.timestamp != null ? a.timestamp : 0);
    const bt = Number(b.timestamp != null ? b.timestamp : 0);
    if (at !== bt) return (at - bt) * dir;
  } else if (backupsSortKey === "size") {
    const as = parseSizeToBytes(a.size);
    const bs = parseSizeToBytes(b.size);
    if (as !== bs) return (as - bs) * dir;
  } else {
    const an = String(a.name != null ? a.name : "").toLowerCase();
    const bn = String(b.name != null ? b.name : "").toLowerCase();
    if (an !== bn) return an < bn ? -1 * dir : 1 * dir;
  }
  const an2 = String(a.name != null ? a.name : "").toLowerCase();
  const bn2 = String(b.name != null ? b.name : "").toLowerCase();
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
  if (!propKeyInput || !propValueInput) return;
  propKeyInput.value = key || "";
  propKeyInput.disabled = true;
  propKeyInput.readOnly = true;
  propValueInput.value = value || "";
  if (propertyModalTitle) propertyModalTitle.textContent = "Edit Property";
  editPropertyModal.show();
}

function openNewPropertyModal() {
  if (!propKeyInput || !propValueInput) return;
  propKeyInput.value = "";
  propKeyInput.disabled = false;
  propKeyInput.readOnly = false;
  propValueInput.value = "";
  if (propertyModalTitle) propertyModalTitle.textContent = "New Property";
  editPropertyModal.show();
}

document.getElementById("savePropertyBtn").onclick = () => {
  if (!propKeyInput || !propValueInput) return;
  const key = propKeyInput.value.trim();
  const value = propValueInput.value.trim();
  if (!key) return;
  sendCommand("update_property", { key, value });
  editPropertyModal.hide();
};

newPropertyBtn?.addEventListener("click", openNewPropertyModal);

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
    if (commandMentionPopup && !commandMentionPopup.classList.contains("d-none")) return;
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

  const newBackupBtn = document.getElementById("newBackupBtn");
  if (newBackupBtn) {
    newBackupBtn.onclick = openNewBackupModal;
  }

toggleServerBtn.onclick = () => {
  sendCommand(isServerRunning ? "stop_server" : "start_server");
};

reconnectBtn.onclick = refreshStatus;
refreshBtn.onclick = refreshStatus;
sidebarToggle.onclick = toggleSidebar;

// Init
  initSettingsUI();
  initServerBackendSettingsSelect();
  initAutostartServerSettingsToggle();
  initDropdownCloseAnimations();
  initCommandMentions();
  initFromHash();
  initBackupSorting();
  initQuickMacros();
  initChatUI();
  initMotdToolbox();
  startAutoRefresh();
  refreshStatus();

exportMacrosBtn?.addEventListener("click", exportMacros);
importMacrosBtn?.addEventListener("click", () => importMacrosFile?.click());
importMacrosFile?.addEventListener("change", () => importMacrosFromFile(importMacrosFile.files?.[0]));

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

function initMotdToolbox() {
  if (!motdInput || !motdPreview) return;

  motdInput.addEventListener("input", updateMotdPreview);
  motdInput.addEventListener("input", updateToolboxSendButtonState);
  motdInput.addEventListener("input", updateToolboxCopyButtonState);
  document.querySelectorAll(".toolbox-toolbar [data-motd-code]").forEach((button) => {
    button.addEventListener("click", () => {
      const code = button.dataset.motdCode;
      if (code) insertMotdCode(code);
    });
  });

  if (motdColorModalEl) {
    motdColorModalEl.querySelectorAll(".motd-color-swatch").forEach((swatch) => {
      swatch.addEventListener("click", () => {
        insertMotdCode(swatch.dataset.motdColorCode);
        motdColorModal?.hide();
      });
    });
  }

  toolboxSendEveryoneBtn?.addEventListener("click", sendToolboxMessageToEveryone);
  toolboxCopyBtn?.addEventListener("click", () => copyToolboxCommand(toolboxCopyType));
  toolboxCopyDropdownMenu?.addEventListener("click", (event) => {
    const button = event.target?.closest?.("[data-copy-type]");
    if (!button || !button.dataset.copyType) return;
    setToolboxCopyType(button.dataset.copyType);
  });
  setToolboxCopyType(toolboxCopyType);
  updateMotdPreview();
  startMotdAnimationLoop();
  updateToolboxSendButtonState();
  updateToolboxCopyButtonState();
}

function updateToolboxSendButtonState() {
  if (!toolboxSendEveryoneBtn || !motdInput) return;
  const hasInput = Boolean((motdInput.value || "").trim());
  toolboxSendEveryoneBtn.disabled = !hasInput || !isServerRunning;
  updateToolboxCopyButtonState();
}

function sendToolboxMessageToEveryone() {
  if (!motdInput) return;
  const formatted = (motdInput.value || "").trim();
  if (!formatted || !isServerRunning) return;
  const payload = JSON.stringify({ rawtext: [{ text: formatted }] });
  sendServerCommand(`tellraw @a ${payload}`);
}

function buildToolboxCommand(type, formatted) {
  if (!formatted) return "";
  const cleaned = formatted;
  switch ((type || "say").toLowerCase()) {
    case "tellraw": {
      const payload = JSON.stringify({ rawtext: [{ text: cleaned }] });
      return `tellraw @a ${payload}`;
    }
    case "tell":
      return `tell @a ${cleaned}`;
    case "say":
    default:
      return `say ${cleaned}`;
  }
}

function copyToolboxCommand(type) {
  if (!motdInput) return;
  const formatted = (motdInput.value || "").trim();
  if (!formatted) return;
  const command = buildToolboxCommand(type, formatted);
  if (!command) return;
  copyTextToClipboard(command);
}

function copyTextToClipboard(text) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(() => {
      fallbackCopyText(text);
    });
  } else {
    fallbackCopyText(text);
  }

  function fallbackCopyText(value) {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
  }
}

function setToolboxCopyType(type) {
  const normalized = (type || "say").toLowerCase();
  toolboxCopyType = normalized;
  if (toolboxCopyLabel) {
    toolboxCopyLabel.textContent = "Copy";
  }
  if (!toolboxCopyDropdownMenu) return;
  toolboxCopyDropdownMenu.querySelectorAll("[data-copy-type]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.copyType === normalized);
  });
}

function updateToolboxCopyButtonState() {
  if (!toolboxCopyBtn || !motdInput) return;
  const hasInput = Boolean((motdInput.value || "").trim());
  toolboxCopyBtn.disabled = !hasInput;
  if (toolboxCopyToggleBtn) toolboxCopyToggleBtn.disabled = !hasInput;
}

function insertMotdCode(code) {
  if (!motdInput || !code) return;
  const normalizedCode = code.startsWith("§") ? code : `§${code}`;
  const start =
    typeof motdInput.selectionStart === "number" ? motdInput.selectionStart : motdInput.value.length;
  const end =
    typeof motdInput.selectionEnd === "number" ? motdInput.selectionEnd : start;
  const hasSelection = end > start;
  if (hasSelection && normalizedCode.toLowerCase() !== "§r") {
    const selectedText = motdInput.value.slice(start, end);
    const wrapped = `${normalizedCode}${selectedText}§r`;
    motdInput.setRangeText(wrapped, start, end, "select");
  } else {
    motdInput.setRangeText(normalizedCode, start, end, "end");
    const cursorPos = start + normalizedCode.length;
    motdInput.setSelectionRange(cursorPos, cursorPos);
  }
  motdInput.focus();
  motdInput.dispatchEvent(new Event("input", { bubbles: true }));
}

function updateMotdPreview() {
  if (!motdPreview || !motdInput) return;
  const raw = (motdInput.value || "").trim();
  if (!raw) {
    motdPreview.textContent = "Paste or type text to preview formatting.";
    motdPreviewHasObfuscated = false;
    return;
  }

  motdPreview.textContent = "";
  const state = {
    color: null,
    bold: false,
    italic: false,
    underline: false,
    strikethrough: false,
    obfuscated: false,
  };
  let buffer = "";

  const flushBuffer = () => {
    if (!buffer) return;
    const span = document.createElement("span");
    if (state.color) {
      span.style.color = state.color;
    }
    if (state.bold) {
      span.style.fontWeight = "700";
    }
    if (state.italic) {
      span.style.fontStyle = "italic";
    }
    const decorations = [];
    if (state.underline) decorations.push("underline");
    if (state.strikethrough) decorations.push("line-through");
    if (decorations.length) {
      span.style.textDecoration = decorations.join(" ");
    }
    span.textContent = buffer;
    motdPreview.appendChild(span);
    buffer = "";
  };

  for (let i = 0; i < raw.length; i++) {
    const char = raw[i];
    if (char === "§" && i + 1 < raw.length) {
      flushBuffer();
      i += 1;
      applyMotdCode(raw[i], state);
      continue;
    }
    if (char === "\n") {
      flushBuffer();
      motdPreview.appendChild(document.createElement("br"));
      continue;
    }
    let nextChar = char;
    if (state.obfuscated && /\S/.test(char)) {
      nextChar = MOTD_OBFUSCATION_CHARS.charAt(Math.floor(Math.random() * MOTD_OBFUSCATION_CHARS.length));
    }
    buffer += nextChar;
  }
  flushBuffer();
  motdPreviewHasObfuscated = state.obfuscated;
}

function applyMotdCode(code, state) {
  if (!code) return;
  const key = code.toLowerCase();
  if (MOTD_COLOR_MAP[key]) {
    state.color = MOTD_COLOR_MAP[key];
    state.bold = false;
    state.italic = false;
    state.underline = false;
    state.strikethrough = false;
    state.obfuscated = false;
    return;
  }
  switch (key) {
    case "l":
      state.bold = true;
      break;
    case "o":
      state.italic = true;
      break;
    case "n":
      state.underline = true;
      break;
    case "m":
      state.strikethrough = true;
      break;
    case "k":
      state.obfuscated = true;
      break;
    case "r":
      state.color = null;
      state.bold = false;
      state.italic = false;
      state.underline = false;
      state.strikethrough = false;
      state.obfuscated = false;
      break;
    default:
      break;
  }
}

function startMotdAnimationLoop() {
  if (motdAnimationTimer) return;
  motdAnimationTimer = setInterval(() => {
    motdAnimationTick = (motdAnimationTick + 1) % 20;
    if (motdAnimationTick !== 0) return;
    if (currentSection !== "toolbox" || !motdPreviewHasObfuscated) return;
    updateMotdPreview();
  }, MOTD_ANIMATION_INTERVAL_MS);
}

function initChatUI() {
  chatSendBtn?.addEventListener("click", sendChatMessage);
  chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChatMessage();
    }
  });
  chatRecipientDropdownMenu?.addEventListener("click", (event) => {
    const btn = event.target?.closest?.("[data-recipient]");
    if (!btn) return;
    const recipient = (btn.getAttribute("data-recipient") || "").trim();
    if (!recipient) return;
    if (recipient === "@a") {
      setChatRecipient({ id: "@a", label: "Everyone", icon: "bi-at" });
      return;
    }
    setChatRecipient({ id: recipient, label: recipient, icon: "bi-person-fill" });
  });
  setChatRecipient(chatRecipient, { hideModal: false });
  loadChatHistoryFromStorage();
  renderChatMessages();
}

function setChatRecipient(recipient, options = {}) {
  chatRecipient = { ...recipient };
  if (chatRecipientLabel) {
    chatRecipientLabel.innerHTML = `<i class="bi ${chatRecipient.icon} me-1"></i>${chatRecipient.label}`;
  }
}

function updateChatPlayersList(players) {
  if (!chatRecipientPlayersMenu) return;
  chatRecipientPlayersMenu.innerHTML = "";
  if (chatRecipientPlayersHint) {
    chatRecipientPlayersHint.classList.toggle("d-none", players.length > 0);
  }
  players.forEach((player) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <button type="button" class="dropdown-item" data-recipient="${player}">
        <i class="bi bi-person-fill me-2"></i>${player}
      </button>
    `;
    chatRecipientPlayersMenu.appendChild(li);
  });
  if (chatRecipient.id !== "@a" && !players.includes(chatRecipient.id)) {
    setChatRecipient({ id: "@a", label: "Everyone", icon: "bi-at" }, { hideModal: false });
  }
}

function pushChatMessage(entry) {
  const uid = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  chatMessages.push({ ...entry, uid });
  if (chatMessages.length > CHAT_MESSAGE_LIMIT) {
    chatMessages.shift();
  }
  renderChatMessages();
  persistChatHistory();
}

function ingestChatFromLogs(logs) {
  if (!Array.isArray(logs) || logs.length === 0) {
    lastChatLogLine = null;
    return;
  }
  let startIndex = 0;
  if (lastChatLogLine) {
    let found = false;
    for (let i = logs.length - 1; i >= 0; i -= 1) {
      if (logs[i] === lastChatLogLine) {
        startIndex = i + 1;
        found = true;
        break;
      }
    }
    if (!found) {
      startIndex = Math.max(0, logs.length - CHAT_LOG_TAIL_FALLBACK);
    }
  }
  for (let i = startIndex; i < logs.length; i += 1) {
    const parsed = parseChatLogLine(logs[i]);
    if (!parsed) continue;
    pushChatMessage({
      direction: "inbound",
      sender: parsed.sender,
      text: parsed.text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    });
  }
  lastChatLogLine = logs[logs.length - 1] || lastChatLogLine;
}

function parseChatLogLine(line) {
  if (!line) return null;
  const text = String(line);
  const markerIndex = text.indexOf("[CHAT]");
  if (markerIndex === -1) return null;
  const payload = text.slice(markerIndex + 6).trim();
  if (!payload) return null;
  const sep = payload.indexOf(":");
  if (sep === -1) return null;
  const sender = payload.slice(0, sep).trim();
  const message = payload.slice(sep + 1).trim();
  if (!sender || !message) return null;
  return { sender, text: message };
}

function renderChatMessages() {
  if (!chatMessagesList) return;
  if (!chatMessages.length) {
    chatMessagesList.innerHTML = `
      <div class="chat-empty text-muted small">
        <i class="bi bi-chat-dots opacity-50"></i>
        <div>Nothing here... Send something!</div>
      </div>
    `;
    return;
  }
  const fragment = document.createDocumentFragment();
  const lastMsg = chatMessages[chatMessages.length - 1];
  const shouldAnimateUid = lastMsg?.uid && lastMsg.uid !== lastAnimatedChatUid ? lastMsg.uid : null;
  chatMessages.forEach((msg) => {
    const isInbound = msg.direction === "inbound";
    const label = isInbound ? `${msg.sender || "Player"}` : `You`;
    const row = document.createElement("div");
    row.className = `chat-row ${isInbound ? "chat-row-inbound" : "chat-row-outbound"}`;
    row.innerHTML = `
      <div class="chat-bubble ${isInbound ? "chat-bubble-inbound" : "chat-bubble-outbound"} ${msg.uid === shouldAnimateUid ? "chat-pop" : ""}" data-chat-uid="${msg.uid || ""}">
        <div class="chat-meta small opacity-75">
          <span><i class="bi ${isInbound ? "bi-person-fill" : "bi-send-fill"} me-1"></i>${label}</span>
          <span class="ms-2">${msg.timestamp || ""}</span>
        </div>
        <div class="chat-text">${escapeHtml(msg.text || "")}</div>
      </div>
    `;
    fragment.appendChild(row);
  });
  chatMessagesList.innerHTML = "";
  chatMessagesList.appendChild(fragment);
  requestAnimationFrame(() => {
    chatMessagesList.scrollTop = chatMessagesList.scrollHeight;
  });
  if (shouldAnimateUid) lastAnimatedChatUid = shouldAnimateUid;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function sendChatMessage() {
  if (!chatInput || !chatSendBtn || !isServerRunning) return;
  const text = chatInput.value.trim();
  if (!text) return;
  chatSendBtn.disabled = true;
  if (chatRecipientBtn) chatRecipientBtn.disabled = true;
  const target = chatRecipient.id === "@a" ? "@a" : chatRecipient.id;
  try {
    await sendServerCommand(`tell ${target} ${text}`);
    pushChatMessage({
      direction: "outbound",
      text,
      targetLabel: chatRecipient.label,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    });
    chatInput.value = "";
  } catch (err) {
    console.error("Chat send failed:", err);
  } finally {
    chatSendBtn.disabled = !isServerRunning;
    if (chatRecipientBtn) chatRecipientBtn.disabled = !isServerRunning;
    chatInput.focus();
  }
}

function resetChatHistory() {
  chatMessages.length = 0;
  lastAnimatedChatUid = null;
  renderChatMessages();
  persistChatHistory();
  lastChatLogLine = null;
}

function persistChatHistory() {
  if (!CHAT_STORAGE_KEY) return;
  try {
    if (!chatMessages.length) {
      localStorage.removeItem(CHAT_STORAGE_KEY);
      return;
    }
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(chatMessages));
  } catch (_e) {}
}

function loadChatHistoryFromStorage() {
  if (!CHAT_STORAGE_KEY) return;
  try {
    const stored = localStorage.getItem(CHAT_STORAGE_KEY);
    if (!stored) return;
    const parsed = JSON.parse(stored);
    if (!Array.isArray(parsed)) return;
    const sliceStart = Math.max(0, parsed.length - CHAT_MESSAGE_LIMIT);
    chatMessages.length = 0;
    parsed.slice(sliceStart).forEach((entry) => {
      if (entry && typeof entry.text === "string") {
        const uid = entry.uid || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        chatMessages.push({ ...entry, uid });
      }
    });
  } catch (_e) {}
}

function initQuickMacros() {
  quickMacroForm?.addEventListener("submit", handleMacroSubmit);
  quickMacroModalEl?.addEventListener("hidden.bs.modal", resetMacroForm);
  quickMacroDeleteBtn?.addEventListener("click", handleMacroDelete);
  quickMacroIconInput?.addEventListener("change", updateQuickMacroCustomIconVisibility);
  quickMacroTriggerSelect?.addEventListener("change", updateQuickMacroIntervalVisibility);
  updateQuickMacroCustomIconVisibility();
  quickMacroTriggerBtn?.addEventListener("click", () => resetMacroForm());
  fetchQuickMacros();
  resetMacroForm();
}

async function fetchQuickMacros() {
  if (!macroGrid) return;
  try {
    const response = await fetch("/api/macros");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Failed to fetch macros.");
    }
    const macrosPayload = payload.macros;
    const presetsPayload = payload.presets;
    quickMacros = Array.isArray(macrosPayload) ? macrosPayload : [];
    presetMacros = Array.isArray(presetsPayload) ? presetsPayload : [];
    renderQuickMacros();
    renderPresetMacros();
  } catch (err) {
    console.error("Macros fetch failed:", err);
    showError(err.message || "Unable to load quick macros.");
  }
}

function renderQuickMacros() {
  if (!macroGrid) return;
  macroGrid.innerHTML = "";
  if (!quickMacros.length) {
    const empty = document.createElement("div");
    empty.className = "col-12 macro-empty";
    empty.innerHTML = `
      <i class="bi bi-lightning-charge"></i>
      <div>No macros yet. Create one to pin a command.</div>
    `;
    macroGrid.appendChild(empty);
    return;
  }
  quickMacros.forEach((macro) => {
    const col = document.createElement("div");
    col.className = "col";
    const card = document.createElement("div");
    card.className = "macro-card bg-dark text-white";
    const iconClass = macro.icon || "bi-gear-fill";
    const trigger = normalizeMacroTrigger(macro.trigger || (macro.interval_seconds ? "interval" : "manual"));
    const meta =
      trigger === "player_join"
        ? "On player login"
        : trigger === "player_leave"
        ? "On player leave"
        : trigger === "player_death"
        ? "On player death"
        : trigger === "interval" && macro.interval_seconds && Number(macro.interval_seconds) > 0
        ? `Auto every ${macro.interval_seconds}s`
        : "Manual";
    const header = document.createElement("div");
    header.className = "d-flex align-items-center gap-3";
    header.innerHTML = `
      <i class="bi ${iconClass}"></i>
      <div>
        <span class="fw-semibold">${macro.title}</span>
        <div class="small text-muted">${meta}</div>
        <div class="small text-muted">Ran ${macro.times_ran || 0} times</div>
      </div>
    `;
    const actions = document.createElement("div");
    actions.className = "macro-actions";
    const executeBtn = document.createElement("button");
    executeBtn.type = "button";
    executeBtn.className = "btn btn-primary execute-btn";
    executeBtn.textContent = macro.interval_seconds && Number(macro.interval_seconds) > 0 ? "Execute now" : "Execute";
    executeBtn.addEventListener("click", () => activateMacro(macro));
    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn btn-outline-secondary edit-btn";
    editBtn.textContent = "Edit";
    editBtn.addEventListener("click", () => openMacroEditor(macro));
    actions.appendChild(executeBtn);
    actions.appendChild(editBtn);
    card.appendChild(header);
    card.appendChild(actions);
    col.appendChild(card);
    macroGrid.appendChild(col);
  });
}

function renderPresetMacros() {
  if (!presetMacroGrid) return;
  presetMacroGrid.innerHTML = "";
  if (!presetMacros.length) {
    const empty = document.createElement("div");
    empty.className = "text-muted small";
    empty.textContent = "No presets defined.";
    presetMacroGrid.appendChild(empty);
    return;
  }
  presetMacros.forEach((preset) => {
    const col = document.createElement("div");
    col.className = "preset-macro-wrap";
    const card = document.createElement("div");
    card.className = "macro-preset-card";
    const iconClass = preset.icon || "bi-gear-fill";
    const header = document.createElement("div");
    header.className = "d-flex align-items-center gap-2 mb-2";
    header.innerHTML = `
      <i class="bi ${iconClass}"></i>
      <span class="fw-semibold small mb-0">${preset.title || "Preset"}</span>
    `;
    const description = document.createElement("p");
    description.className = "small text-muted mb-3";
    description.textContent = preset.description || "Ready-to-use macro preset.";
    const actions = document.createElement("div");
    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.className = "btn btn-sm btn-outline-primary w-100";
    applyBtn.textContent = "Use preset";
    applyBtn.addEventListener("click", () => applyPresetToModal(preset));
    actions.appendChild(applyBtn);
    card.appendChild(header);
    card.appendChild(description);
    card.appendChild(actions);
    col.appendChild(card);
    presetMacroGrid.appendChild(col);
  });
}

const TRIGGER_CANONICAL = {
  player_login: "player_join",
  player_join: "player_join",
  player_leave: "player_leave",
  player_death: "player_death",
};

function normalizeMacroTrigger(trigger) {
  const normalized = String(trigger || "").trim().toLowerCase().replace(/\s+/g, "_");
  if (!normalized) {
    return "manual";
  }
  return TRIGGER_CANONICAL[normalized] || normalized;
}

function applyPresetToModal(preset) {
  resetMacroForm();
  if (quickMacroTitleInput) quickMacroTitleInput.value = preset.title || "";
  if (quickMacroIconInput) {
    const matchOption = Array.from(quickMacroIconInput.options).find((opt) => opt.value === preset.icon);
    if (matchOption) {
      quickMacroIconInput.value = preset.icon;
    } else {
      quickMacroIconInput.value = "custom";
      quickMacroCustomIconInput && (quickMacroCustomIconInput.value = preset.icon || "");
    }
  }
  updateQuickMacroCustomIconVisibility();
  if (quickMacroCommandsInput) quickMacroCommandsInput.value = (preset.commands || []).join("\n");
  if (quickMacroTriggerSelect) quickMacroTriggerSelect.value = normalizeMacroTrigger(preset.trigger || "manual");
  updateQuickMacroIntervalVisibility();
  if (quickMacroModalTitle) quickMacroModalTitle.textContent = "New Quick Macro";
  quickMacroModal?.show();
}

function updateQuickMacroIntervalVisibility() {
  if (!quickMacroTriggerSelect || !quickMacroIntervalInput) return;
  const wrapper = quickMacroIntervalInput.closest(".mb-3");
  if (!wrapper) return;
  const trigger = (quickMacroTriggerSelect.value || "manual").toLowerCase();
  wrapper.classList.toggle("d-none", trigger !== "interval");
}

async function activateMacro(macro) {
  if (!macro) return;
  await sendCommand("run_macro", { macro_id: macro.id, commands: macro.commands });
  fetchQuickMacros();
}

async function handleMacroSubmit(event) {
  event.preventDefault();
  if (!quickMacroTitleInput || !quickMacroCommandsInput) return;
  const title = quickMacroTitleInput.value.trim();
  const commands = quickMacroCommandsInput.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!title || !commands.length) return;
  let icon = quickMacroIconInput?.value || "";
  if (icon === "custom") {
    icon = quickMacroCustomIconInput?.value.trim() || "";
  }
  if (!icon) {
    icon = "bi-gear-fill";
  }
  const intervalValue = quickMacroIntervalInput ? quickMacroIntervalInput.value.trim() : "";
  const trigger = (quickMacroTriggerSelect?.value || (intervalValue ? "interval" : "manual")).toString().toLowerCase();
  const payload = {
    title,
    icon,
    commands,
    trigger,
  };
  if (trigger === "interval" && intervalValue) {
    const parsed = Number(intervalValue);
    if (!Number.isNaN(parsed) && parsed > 0) {
      payload.interval_seconds = Math.floor(parsed);
    }
  }
  if (quickMacroIdInput?.value) {
    payload.id = quickMacroIdInput.value;
  }
  try {
    const response = await fetch("/api/macros", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || "Failed to save macro.");
    }
    if (Array.isArray(body.macros)) {
      quickMacros = body.macros;
    }
    if (Array.isArray(body.presets)) {
      presetMacros = body.presets;
      renderPresetMacros();
    }
    renderQuickMacros();
    quickMacroModal?.hide();
  } catch (err) {
    console.error("Macro save failed:", err);
    showError(err.message || "Unable to save macro.");
  }
}

async function handleMacroDelete() {
  const macroId = quickMacroIdInput?.value?.trim();
  if (!macroId) return;
  quickMacroDeleteBtn && (quickMacroDeleteBtn.disabled = true);
  try {
    const response = await fetch("/api/macros", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: macroId, delete: true }),
    });
    const body = await response.json();
    if (!response.ok) {
      throw new Error(body.error || "Failed to delete macro.");
    }
    if (Array.isArray(body.macros)) {
      quickMacros = body.macros;
    }
    if (Array.isArray(body.presets)) {
      presetMacros = body.presets;
      renderPresetMacros();
    }
    renderQuickMacros();
    quickMacroModal?.hide();
  } catch (err) {
    console.error("Macro delete failed:", err);
    showError(err.message || "Unable to delete macro.");
  } finally {
    quickMacroDeleteBtn && (quickMacroDeleteBtn.disabled = false);
  }
}

function openMacroEditor(macro) {
  if (!macro) return;
  quickMacroIdInput && (quickMacroIdInput.value = macro.id || "");
  const defaultIcon = quickMacroIconInput?.options?.[0]?.value || "bi-gear-fill";
  const storedIcon = macro.icon || defaultIcon;
  if (quickMacroIconInput) {
    const validIcon = Array.from(quickMacroIconInput.options).some((option) => option.value === storedIcon);
    if (validIcon) {
      quickMacroIconInput.value = storedIcon;
      quickMacroCustomIconInput && (quickMacroCustomIconInput.value = "");
    } else {
      quickMacroIconInput.value = "custom";
      quickMacroCustomIconInput && (quickMacroCustomIconInput.value = storedIcon);
    }
  }
  quickMacroTitleInput.value = macro.title || "";
  quickMacroCommandsInput.value = (macro.commands || []).join("\n");
  if (quickMacroIntervalInput) {
    quickMacroIntervalInput.value = macro.interval_seconds ? String(macro.interval_seconds) : "";
  }
  if (quickMacroTriggerSelect) {
    const triggerValue = normalizeMacroTrigger(
      macro.trigger || (macro.interval_seconds ? "interval" : "manual")
    );
    quickMacroTriggerSelect.value = triggerValue;
  }
  updateQuickMacroCustomIconVisibility();
  updateQuickMacroIntervalVisibility();
  if (quickMacroModalTitle) {
    quickMacroModalTitle.textContent = "Editing macro";
  }
  quickMacroDeleteBtn?.classList.remove("d-none");
  quickMacroDeleteBtn && (quickMacroDeleteBtn.disabled = false);
  quickMacroModal?.show();
}

function resetMacroForm() {
  quickMacroForm?.reset();
  quickMacroCustomIconInput && (quickMacroCustomIconInput.value = "");
  if (quickMacroIntervalInput) {
    quickMacroIntervalInput.value = "";
  }
  if (quickMacroTriggerSelect) {
    quickMacroTriggerSelect.value = "manual";
  }
  if (quickMacroIdInput) {
    quickMacroIdInput.value = "";
  }
  if (quickMacroModalTitle) {
    quickMacroModalTitle.textContent = "New Quick Macro";
  }
  updateQuickMacroCustomIconVisibility();
  updateQuickMacroIntervalVisibility();
  quickMacroDeleteBtn?.classList.add("d-none");
  quickMacroDeleteBtn && (quickMacroDeleteBtn.disabled = false);
}

function updateQuickMacroCustomIconVisibility() {
  if (!quickMacroIconInput || !quickMacroCustomIconWrapper) return;
  const isCustom = quickMacroIconInput.value === "custom";
  quickMacroCustomIconWrapper.classList.toggle("d-none", !isCustom);
  if (!isCustom && quickMacroCustomIconInput) {
    quickMacroCustomIconInput.value = "";
  }
}

function updateQuickMacroIntervalVisibility() {
  if (!quickMacroTriggerSelect || !quickMacroIntervalInput) return;
  const wrapper = quickMacroIntervalInput.closest(".mb-3");
  if (!wrapper) return;
  const trigger = (quickMacroTriggerSelect.value || "manual").toLowerCase();
  wrapper.classList.toggle("d-none", trigger !== "interval");
}
