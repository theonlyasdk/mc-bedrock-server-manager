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
let mentionTeams = [];

const STORAGE_KEYS = {
  sidebarCollapsed: "mcbsm.sidebarCollapsed",
  updateIntervalSec: "mcbsm.updateIntervalSec",
  lastSection: "mcbsm.lastSection",
  commandHistory: "mcbsm.commandHistory",
};
const CHAT_STORAGE_KEY = "mcbsm.chatMessages";

const MINECRAFT_COMMANDS = [
  "ability", "alwaysday", "apple", "clear", "clone", "connect", "daylock", "deop", "diamond", "difficulty", "effect", "enchant",
  "event", "execute", "fill", "fog", "function", "gamemode", "gamerule", "gametest", "give", "help", "immutableworld",
  "iron_ingot", "kick", "kill", "list", "locate", "loot", "me", "mobevent", "msg", "music", "op", "ops", "particle", "playanimation",
  "playsound", "reload", "replaceitem", "ride", "say", "scriptevent", "setblock", "setmaxplayers", "setworldspawn",
  "spawnpoint", "spreadplayers", "steak", "stop", "stopsound", "structure", "summon", "tag", "teleport", "tell", "tellraw",
  "testfor", "testforblock", "testforblocks", "tickingarea", "time", "title", "titleraw", "tp", "w", "wb", "weather",
  "whitelist", "worldbuilder", "wsserver", "xp"
].sort();

const COMMON_SUBSTITUTIONS = [
  { label: "time", value: "@!time", description: "Current server time" },
  { label: "online_players", value: "@!online_players", description: "Count of online players" },
  { label: "max_players", value: "@!max_players", description: "Server player limit" },
  { label: "ip_local", value: "@!ip_local", description: "Local network IP" },
  { label: "uptime", value: "@!uptime", description: "Server uptime duration" },
];

let commandHistory = [];
try {
  const storedHistory = localStorage.getItem(STORAGE_KEYS.commandHistory);
  if (storedHistory) commandHistory = JSON.parse(storedHistory);
} catch (e) {
  commandHistory = [];
}
let historyIndex = -1;

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
const chatNotificationToastEl = document.getElementById("chatNotificationToast");
const chatNotificationToast = chatNotificationToastEl ? new bootstrap.Toast(chatNotificationToastEl) : null;
let chatPrefixModal = null;
let chatPrefix = "";
let backupProgressVisible = false;
const pageLoadingOverlay = document.getElementById("page-loading-overlay");

function showError(msg) {
  document.getElementById("errorToastBody").textContent = msg || "An internal error occurred.";
  errorToast.show();
}

function showToast(message, variant = "info") {
  const text = String(message || "").trim();
  if (!text) return;
  const container = document.querySelector(".toast-container");
  if (!container || typeof bootstrap === "undefined" || !bootstrap.Toast) return;

  const bgClassByVariant = {
    success: "text-bg-success",
    info: "text-bg-primary",
    warning: "text-bg-warning",
    danger: "text-bg-danger",
  };
  const bgClass = bgClassByVariant[String(variant || "").toLowerCase()] || "text-bg-primary";

  const toastEl = document.createElement("div");
  toastEl.className = `toast align-items-center ${bgClass} border-0`;
  toastEl.role = "alert";
  toastEl.ariaLive = "assertive";
  toastEl.ariaAtomic = "true";
  toastEl.innerHTML = `
    <div class="d-flex">
      <div class="toast-body"></div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
  `;
  toastEl.querySelector(".toast-body").textContent = text;
  container.appendChild(toastEl);

  const toast = new bootstrap.Toast(toastEl, { delay: 2500 });
  toastEl.addEventListener("hidden.bs.toast", () => toastEl.remove(), { once: true });
  toast.show();
}

function showConfirm(message, onConfirm, options = {}) {
  const text = String(message || "").trim();
  if (!text) return;
  const title = String(options.title || "Confirm").trim() || "Confirm";
  const confirmText = String(options.confirmText || "Confirm").trim() || "Confirm";
  const confirmClass = String(options.confirmClass || "btn-primary").trim() || "btn-primary";
  const inputOptions = options.input && typeof options.input === "object" ? options.input : null;

  const titleEl = document.getElementById("confirmTitle");
  const textEl = document.getElementById("confirmText");
  const btn = document.getElementById("confirmActionBtn");
  const inputWrapper = document.getElementById("confirmInputWrapper");
  const inputLabel = document.getElementById("confirmInputLabel");
  const inputEl = document.getElementById("confirmInput");
  const inputHelp = document.getElementById("confirmInputHelp");
  if (!titleEl || !textEl || !btn || !confirmModal) {
    if (window.confirm(`${title}\n\n${text}`)) onConfirm?.();
    return;
  }

  titleEl.textContent = title;
  textEl.textContent = text;
  btn.className = `btn ${confirmClass}`;
  btn.textContent = confirmText;

  if (inputWrapper && inputEl && inputLabel && inputHelp) {
    if (inputOptions) {
      inputWrapper.classList.remove("d-none");
      inputLabel.textContent = String(inputOptions.label || "Reason").trim() || "Reason";
      inputEl.value = String(inputOptions.value || "");
      inputEl.placeholder = String(inputOptions.placeholder || "");
      inputEl.maxLength = Number.isFinite(inputOptions.maxLength) ? inputOptions.maxLength : 0;
      if (inputEl.maxLength <= 0) inputEl.removeAttribute("maxlength");
      inputEl.required = Boolean(inputOptions.required);
      inputHelp.textContent = String(inputOptions.help || "");
      setTimeout(() => inputEl.focus(), 50);
    } else {
      inputWrapper.classList.add("d-none");
      inputLabel.textContent = "";
      inputEl.value = "";
      inputEl.placeholder = "";
      inputEl.required = false;
      inputHelp.textContent = "";
    }
  }

  btn.onclick = async () => {
    try {
      const inputValue = inputOptions && inputEl ? String(inputEl.value || "") : null;
      await onConfirm?.(inputValue);
    } finally {
      confirmModal.hide();
    }
  };
  confirmModal.show();
}

// Selectors
const sidebarToggle = document.getElementById("menu-toggle");
const wrapper = document.getElementById("wrapper");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
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
const quickMacroKeywordWrapper = document.getElementById("quickMacroKeywordWrapper");
const quickMacroKeywordInput = document.getElementById("quickMacroKeyword");
const quickMacroTimeWrapper = document.getElementById("quickMacroTimeWrapper");
const quickMacroTimeInput = document.getElementById("quickMacroTime");
const quickMacroIdInput = document.getElementById("quickMacroId");
const quickMacroDeleteBtn = document.getElementById("quickMacroDeleteBtn");
const quickMacroOutputBtn = document.getElementById("quickMacroOutputBtn");
const quickMacroTriggerBtn = document.getElementById("openQuickMacroModalBtn");
const presetMacroGrid = document.getElementById("presetMacroGrid");
const exportMacrosBtn = document.getElementById("exportMacrosBtn");
const importMacrosBtn = document.getElementById("importMacrosBtn");
const importMacrosFile = document.getElementById("importMacrosFile");
const openMacroVarsBtn = document.getElementById("openMacroVarsBtn");
const propertyModalTitle = document.getElementById("propertyModalTitle");
const propKeyInput = document.getElementById("propKey");
const propValueInput = document.getElementById("propValue");
const newPropertyBtn = document.getElementById("newPropertyBtn");
const consoleOnlineLayout = document.getElementById("consoleOnlineLayout");
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
const toolboxCopyLabel = document.getElementById("toolboxCopyLabel");
const toolboxCopyDropdownMenu = document.getElementById("toolboxCopyDropdownMenu");
const resourceUsageRow = document.getElementById("resourceUsageRow");
const openHistoricalPerfBtn = document.getElementById("openHistoricalPerfBtn");
const historicalPerfModalEl = document.getElementById("historicalPerfModal");
const historicalPerfModal = historicalPerfModalEl ? new bootstrap.Modal(historicalPerfModalEl) : null;
const cpuVBar = document.getElementById("cpuVBar");

const macroOutputModalEl = document.getElementById("macroOutputModal");
const macroOutputModal = macroOutputModalEl ? new bootstrap.Modal(macroOutputModalEl) : null;
const macroOutputModalTitle = document.getElementById("macroOutputModalTitle");
const macroOutputMeta = document.getElementById("macroOutputMeta");
const macroOutputPre = document.getElementById("macroOutputPre");
const macroOutputCopyBtn = document.getElementById("macroOutputCopyBtn");
const macroOutputDownloadBtn = document.getElementById("macroOutputDownloadBtn");
const memVBar = document.getElementById("memVBar");
const cpuUsageText = document.getElementById("cpuUsageText");
const memUsageText = document.getElementById("memUsageText");
const memRssText = document.getElementById("memRssText");
const cpuChart = document.getElementById("cpuChart");
const memChart = document.getElementById("memChart");
const cpuHistoryChart = document.getElementById("cpuHistoryChart");
const memHistoryChart = document.getElementById("memHistoryChart");
let hasHistoricalPerformance = false;

const teleportModalEl = document.getElementById("teleportModal");
const teleportModal = teleportModalEl ? new bootstrap.Modal(teleportModalEl) : null;
const tpSourcePlayer = document.getElementById("tpSourcePlayer");
const tpCustomSelector = document.getElementById("tpCustomSelector");
const tpPlayerList = document.getElementById("tpPlayerList");
const confirmTpBtn = document.getElementById("confirmTpBtn");

const giveModalEl = document.getElementById("giveModal");
const giveModal = giveModalEl ? new bootstrap.Modal(giveModalEl) : null;
const giveTargetPlayer = document.getElementById("giveTargetPlayer");
const giveItemName = document.getElementById("giveItemName");
const giveItemMentionPopup = document.getElementById("giveItemMentionPopup");
const giveItemMentionList = document.getElementById("giveItemMentionList");
const giveItemAmount = document.getElementById("giveItemAmount");
const confirmGiveBtn = document.getElementById("confirmGiveBtn");

const spawnMobModalEl = document.getElementById("spawnMobModal");
const spawnMobModal = spawnMobModalEl ? new bootstrap.Modal(spawnMobModalEl) : null;
const spawnMobTargetPlayer = document.getElementById("spawnMobTargetPlayer");
const spawnMobName = document.getElementById("spawnMobName");
const spawnMobCount = document.getElementById("spawnMobCount");
const confirmSpawnMobBtn = document.getElementById("confirmSpawnMobBtn");
const spawnMobMentionPopup = document.getElementById("spawnMobMentionPopup");
const spawnMobMentionList = document.getElementById("spawnMobMentionList");

let quickMacros = [];
let presetMacros = [];
let macroVariables = [];
let macrosRefreshInFlight = false;
let lastMacrosRefreshAt = 0;

const STORAGE_SPLIT_KEYS = {
  consoleSplitDesktopPct: "mcbsm.consoleSplitDesktopPct",
  consoleSplitMobilePct: "mcbsm.consoleSplitMobilePct",
  consoleMobileTab: "mcbsm.consoleMobileTab",
};
const CHAT_MESSAGE_LIMIT = 120;
const CHAT_LOG_TAIL_FALLBACK = 20;
let chatRecipient = { id: "@a", label: "Everyone", icon: "bi-at" };
let chatMessages = [];

// Global variables for player actions
let _currentPlayerTarget = null;
let _allActivePlayers = [];

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

function initSidebarBackdrop() {
  if (!sidebarBackdrop || !wrapper) return;
  sidebarBackdrop.addEventListener("click", () => {
    if (window.innerWidth >= 768) return;
    if (wrapper.classList.contains("toggled")) wrapper.classList.remove("toggled");
  });
}

function showSection(section) {
  currentSection = section;
  document.querySelectorAll("section").forEach((s) => s.classList.add("d-none"));
  document.getElementById(`section-${section}`).classList.remove("d-none");

  // Hide chat notification if we navigate to the chat tab
  if (section === "dashboard" && chatNotificationToast) {
    chatNotificationToast.hide();
  }

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

async function sendCommand(action, data = null, options = {}) {
  // Only lock for major state-changing actions like start/stop, not for generic commands (chat)
  const needsLock = action === "start_server" || action === "stop_server";
  if (needsLock && isRequestInFlight) return;
  if (needsLock) isRequestInFlight = true;
  
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
    if (result.success && !options.skipRefresh) {
      shouldRefresh = true;
    }
    return result.result;
  } catch (err) {
    handleFetchError(err);
  } finally {
    if (needsLock) isRequestInFlight = false;
    if (shouldRefresh) refreshStatus();
  }
}

async function sendServerCommand(command, options = {}) {
  const trimmed = String(command || "").trim();
  if (!trimmed) return;
  return sendCommand("send_command", { command: trimmed }, options);
}

async function sendServerCommands(commands) {
  for (const cmd of (commands || []).map((c) => String(c || "").trim()).filter(Boolean)) {
    await sendServerCommand(cmd);
  }
}

function quoteMinecraftArg(value) {
  const v = String(value ?? "");
  return `"${v.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

function formatTeleportTarget(targetSelectorRaw) {
  const targetSelector = String(targetSelectorRaw || "").trim();
  if (!targetSelector) return "";
  if (targetSelector.startsWith("@")) return targetSelector;

  // Coordinates like: 0 64 0, ~ ~1 ~, ^ ^ ^1.5
  const coordToken = "[~^]?-?\\d*(?:\\.\\d+)?";
  const coordsRe = new RegExp(`^${coordToken}\\s+${coordToken}\\s+${coordToken}$`);
  if (coordsRe.test(targetSelector)) return targetSelector;

  return quoteMinecraftArg(targetSelector);
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

    if (currentSection === "macros") {
      const now = Date.now();
      if (!macrosRefreshInFlight && now - lastMacrosRefreshAt >= 5000) {
        macrosRefreshInFlight = true;
        lastMacrosRefreshAt = now;
        fetchQuickMacros().finally(() => {
          macrosRefreshInFlight = false;
        });
      }
    }
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
  _allActivePlayers = mentionPlayers;
  const teams = data.teams || data.scoreboard_teams || [];
  mentionTeams = Array.isArray(teams) ? teams.map((t) => String(t || "").trim()).filter(Boolean) : [];
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
  }

  const cpu = Number(bedrock.cpu_percent);
  const mem = Number(bedrock.mem_percent);
  const rssBytes = Number(bedrock.mem_rss_bytes);
  if (isServerRunning && Number.isFinite(cpu) && Number.isFinite(mem)) {
    pushMetric(cpuHistory, cpu, CPU_HISTORY_LIMIT);
    pushMetric(memHistory, mem, MEM_HISTORY_LIMIT);
    renderResourceCharts();
    renderHistoricalCharts(data.resource_history);
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
      const isAtBottom = serverLogs.scrollHeight - serverLogs.scrollTop <= serverLogs.clientHeight + 100;
      serverLogs.innerText = logsText;
      if (isAtBottom) {
        requestAnimationFrame(() => {
          serverLogs.scrollTop = serverLogs.scrollHeight;
        });
      }
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
  if (consoleOnlineLayout) {
    consoleOnlineLayout.classList.toggle("d-none", !isServerRunning);
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
      li.className = "list-group-item bg-transparent border-secondary d-flex align-items-center py-2 gap-2";

      const icon = document.createElement("i");
      icon.className = "bi bi-person-fill text-primary";
      li.appendChild(icon);

      const info = document.createElement("div");
      info.className = "flex-grow-1 min-w-0";

      const nameWrap = document.createElement("div");
      nameWrap.className = "d-flex align-items-center gap-2";
      const nameEl = document.createElement("span");
      nameEl.className = "fw-semibold text-truncate";
      nameEl.title = p;
      nameEl.textContent = p;
      nameWrap.appendChild(nameEl);
      if (isOp) {
        const badge = document.createElement("span");
        badge.className = "badge text-bg-warning text-dark";
        badge.style.fontSize = "0.65rem";
        badge.textContent = "OP";
        nameWrap.appendChild(badge);
      }
      info.appendChild(nameWrap);
      li.appendChild(info);

      const actions = document.createElement("div");
      actions.className = "d-flex align-items-center gap-1 flex-wrap justify-content-end";

      const actionDefs = [
        { action: "kick", title: "Kick", icon: "bi-door-open", btnClass: "btn-outline-warning" },
        { action: "ban", title: "Ban", icon: "bi-hammer", btnClass: "btn-outline-danger" },
        { action: "tp", title: "Teleport", icon: "bi-geo-alt", btnClass: "btn-outline-info" },
        { action: "give", title: "Give", icon: "bi-gift", btnClass: "btn-outline-info" },
      ];

      actionDefs.forEach((def) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `btn btn-sm ${def.btnClass}`;
        btn.title = def.title;
        btn.dataset.player = p;
        btn.dataset.playerAction = def.action;
        btn.disabled = Boolean(def.disabled);
        btn.innerHTML = `<i class="bi ${def.icon}"></i><span class="d-none d-lg-inline ms-1">${def.title}</span>`;
        actions.appendChild(btn);
      });

      const menuWrap = document.createElement("div");
      menuWrap.className = "dropdown";
      const menuBtn = document.createElement("button");
      menuBtn.type = "button";
      menuBtn.className = "btn btn-sm btn-outline-light";
      menuBtn.title = "More actions";
      menuBtn.setAttribute("data-bs-toggle", "dropdown");
      menuBtn.setAttribute("aria-expanded", "false");
      menuBtn.innerHTML = '<i class="bi bi-three-dots-vertical"></i>';
      menuWrap.appendChild(menuBtn);

      const menu = document.createElement("ul");
      menu.className = "dropdown-menu dropdown-menu-end shadow-lg border-secondary";
      menu.innerHTML = `
        <li><h6 class="dropdown-header small text-uppercase">Actions</h6></li>
        <li>
          <button type="button" class="dropdown-item py-1" data-player="${p}" data-player-action="op" ${isOp ? "disabled" : ""}>
            <i class="bi bi-shield-check me-2 text-success"></i>Promote to OP
          </button>
        </li>
        <li>
          <button type="button" class="dropdown-item py-1" data-player="${p}" data-player-action="spawn_at">
            <i class="bi bi-geo-alt me-2 text-info"></i>Set world spawn here
          </button>
        </li>
        <li>
          <button type="button" class="dropdown-item py-1" data-player="${p}" data-player-action="spawn_mob_at">
            <i class="bi bi-bug me-2 text-warning"></i>Spawn mob(s) at player…
          </button>
        </li>
      `;
      menuWrap.appendChild(menu);
      actions.appendChild(menuWrap);

      li.appendChild(actions);
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
  let replaceStart = null;
  let replaceEnd = null;

  const SELECTOR_BASE_ITEMS = [
    { label: "@a", value: "@a", description: "all players" },
    { label: "@p", value: "@p", description: "nearest player" },
    { label: "@r", value: "@r", description: "random player" },
    { label: "@s", value: "@s", description: "self" },
    { label: "@e", value: "@e", description: "all entities" },
  ];

  const SELECTOR_KEYS_COMMON = [
    "name", "r", "rm", "x", "y", "z", "dx", "dy", "dz", "c", "l", "lm", "m", "tag", "team", "gamemode",
  ];
  const SELECTOR_KEYS_ENTITY = ["type", "family"].concat(SELECTOR_KEYS_COMMON);
  const GAMEMODE_VALUES = ["survival", "creative", "adventure", "spectator", "0", "1", "2", "3"];

  function hidePopup() {
    commandMentionPopup.classList.add("d-none");
    commandMentionList.innerHTML = "";
    activeIndex = 0;
    replaceStart = null;
    replaceEnd = null;
  }

  function showPopup() {
    commandMentionPopup.classList.remove("d-none");
  }

  function renderList(items) {
    commandMentionList.innerHTML = "";
    items.forEach((item, idx) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = `list-group-item list-group-item-action d-flex align-items-center justify-content-between ${idx === activeIndex ? "active" : ""}`;
      
      const content = document.createElement("div");
      content.innerHTML = item.html || item.label;
      el.appendChild(content);

      if (item.description) {
        const desc = document.createElement("span");
        desc.className = "ms-2 small opacity-50 text-white-50";
        desc.textContent = item.description;
        el.appendChild(desc);
      }

      el.dataset.value = item.value;
      el.onclick = () => applySelection(item.value);
      commandMentionList.appendChild(el);
    });
  }

  function getSubstitutionValue(tag) {
    if (tag === "@!time") return new Date().toLocaleTimeString([], { hour12: false });
    if (tag === "@!online_players") return String(mentionPlayers.length || 0);
    if (tag === "@!max_players") return document.getElementById("playerLimit")?.textContent?.replace("Max: ", "") || "20";
    if (tag === "@!ip_local") return document.getElementById("localIp")?.textContent || "127.0.0.1";
    if (tag === "@!uptime") return document.getElementById("serverUptime")?.textContent || "00:00:00";
    return tag;
  }

  function applySelection(value) {
    const text = commandInput.value || "";
    const startIndex = typeof replaceStart === "number" ? replaceStart : null;
    const endIndex = typeof replaceEnd === "number" ? replaceEnd : null;
    if (startIndex === null || endIndex === null || startIndex < 0 || endIndex < startIndex) return;
    
    // Resolve substitution if needed
    const resolvedValue = value.startsWith("@!") ? getSubstitutionValue(value) : value;

    const before = text.slice(0, startIndex);
    const after = text.slice(endIndex);
    const next = `${before}${resolvedValue}${after}`;
    commandInput.value = next;
    const newCursor = before.length + resolvedValue.length;
    commandInput.setSelectionRange(newCursor, newCursor);
    hidePopup();
    commandInput.focus();
  }

  function getTokenAtCursor(text, cursor) {
    const safeCursor = Math.max(0, Math.min(text.length, cursor));
    const left = text.slice(0, safeCursor);
    const lastWs = Math.max(left.lastIndexOf(" "), left.lastIndexOf("\n"), left.lastIndexOf("\t"));
    const start = lastWs < 0 ? 0 : lastWs + 1;
    return { start, end: safeCursor, token: text.slice(start, safeCursor) };
  }

  function buildItemsForCommandQuery(query) {
    const q = String(query || "").toLowerCase();
    return MINECRAFT_COMMANDS
      .filter((cmd) => cmd.startsWith(q))
      .map((cmd) => ({
        label: cmd,
        html: `<i class="bi bi-terminal me-2"></i><strong>${cmd.slice(0, q.length)}</strong>${cmd.slice(q.length)}`,
        value: cmd
      }));
  }

  function buildItemsForSubstitutionQuery(query) {
    const q = String(query || "").toLowerCase();
    return COMMON_SUBSTITUTIONS
      .filter((s) => s.label.toLowerCase().startsWith(q))
      .map((s) => ({
        label: s.label,
        description: s.description,
        html: `<i class="bi bi-magic me-2"></i><strong>${s.label.slice(0, q.length)}</strong>${s.label.slice(q.length)}`,
        value: s.value
      }));
  }

  function buildItemsForSelectorBaseQuery(query) {
    const q = String(query || "").toLowerCase();
    const items = [];
    items.push(...SELECTOR_BASE_ITEMS.filter((it) => it.value.toLowerCase().startsWith(`@${q}`)).map(it => ({...it})));
    const filteredPlayers = mentionPlayers.filter((name) => name.toLowerCase().includes(q));
    filteredPlayers.slice(0, 15).forEach((name) => {
      const formattedName = name.includes(" ") ? JSON.stringify(name) : name;
      const selector = `@p[name=${formattedName}]`;
      items.push({ label: name, description: "Player", value: selector });
    });
    return items;
  }

  function buildItemsForSelectorArgKey(base, keyPrefix) {
    const keys = base === "@e" ? SELECTOR_KEYS_ENTITY : SELECTOR_KEYS_COMMON;
    const q = String(keyPrefix || "").toLowerCase();
    return keys
      .filter((k) => k.toLowerCase().startsWith(q))
      .map((k) => ({ label: `${k}=`, value: `${k}=` }));
  }

  function buildItemsForSelectorArgValue(base, key, valuePrefix) {
    const k = String(key || "").trim().toLowerCase();
    const q = String(valuePrefix || "").toLowerCase();
    if (k === "name") {
      return mentionPlayers
        .filter((n) => n.toLowerCase().includes(q))
        .slice(0, 15)
        .map((n) => ({ label: n, value: n.includes(" ") ? JSON.stringify(n) : n }));
    }
    if (k === "team") {
      return (mentionTeams || [])
        .filter((t) => t.toLowerCase().includes(q))
        .slice(0, 15)
        .map((t) => ({ label: t, value: JSON.stringify(t) }));
    }
    if (k === "gamemode") {
      return GAMEMODE_VALUES.filter((gm) => gm.toLowerCase().startsWith(q)).map((gm) => ({ label: gm, value: gm }));
    }
    if (k === "type" && base === "@e") {
      const defaults = ["player"];
      return defaults.filter((t) => t.toLowerCase().startsWith(q)).map((t) => ({ label: t, value: t }));
    }
    return [];
  }

  function normalizeSelectorBase(base) {
    const b = String(base || "").trim();
    if (!b.startsWith("@")) return null;
    if (/^@[apres]$/.test(b)) return b;
    return null;
  }

  function updatePopupFromInput() {
    const text = commandInput.value || "";
    const cursor = typeof commandInput.selectionStart === "number" ? commandInput.selectionStart : text.length;
    const { start, token } = getTokenAtCursor(text, cursor);

    // Command suggestions (first token)
    if (start === 0 && !token.startsWith("@") && token.length > 0) {
      replaceStart = 0;
      replaceEnd = cursor;
      const items = buildItemsForCommandQuery(token);
      if (items.length === 0) return hidePopup();
      renderList(items);
      showPopup();
      return;
    }

    // Common Substitutions (@!)
    if (token.startsWith("@!")) {
      const query = token.slice(2);
      replaceStart = start;
      replaceEnd = cursor;
      const items = buildItemsForSubstitutionQuery(query);
      if (items.length === 0) return hidePopup();
      renderList(items);
      showPopup();
      return;
    }

    const atIndex = token.lastIndexOf("@");
    if (atIndex < 0) return hidePopup();
    const absAtIndex = start + atIndex;
    const fragment = text.slice(absAtIndex, cursor);

    if (!fragment.includes("[") && !fragment.includes("]")) {
      const query = fragment.slice(1);
      if (/\s/.test(query)) return hidePopup();
      replaceStart = absAtIndex;
      replaceEnd = cursor;
      const items = buildItemsForSelectorBaseQuery(query);
      if (items.length === 0) return hidePopup();
      renderList(items);
      showPopup();
      return;
    }

    const openIdx = fragment.indexOf("[");
    const closeIdx = fragment.indexOf("]");
    if (openIdx < 0 || (closeIdx >= 0 && closeIdx < fragment.length - 1)) return hidePopup();
    const baseRaw = fragment.slice(0, openIdx);
    const base = normalizeSelectorBase(baseRaw);
    if (!base) return hidePopup();

    const inside = fragment.slice(openIdx + 1);
    const lastComma = inside.lastIndexOf(",");
    const partStart = lastComma >= 0 ? lastComma + 1 : 0;
    const part = inside.slice(partStart);
    const eqIdx = part.indexOf("=");

    if (eqIdx < 0) {
      const keyPrefix = part.trim();
      replaceStart = absAtIndex + openIdx + 1 + partStart;
      replaceEnd = cursor;
      const items = buildItemsForSelectorArgKey(base, keyPrefix);
      if (items.length === 0) return hidePopup();
      renderList(items);
      showPopup();
      return;
    }

    const key = part.slice(0, eqIdx).trim();
    const valuePrefix = part.slice(eqIdx + 1).trim();
    replaceStart = absAtIndex + openIdx + 1 + partStart + eqIdx + 1;
    replaceEnd = cursor;
    const items = buildItemsForSelectorArgValue(base, key, valuePrefix);
    if (items.length === 0) return hidePopup();
    renderList(items);
    showPopup();
  }

  commandInput.addEventListener("input", () => {
    activeIndex = 0;
    updatePopupFromInput();
  });

  commandInput.addEventListener("keydown", (e) => {
    const isPopupVisible = !commandMentionPopup.classList.contains("d-none");
    if (e.key === "Escape" && isPopupVisible) {
      e.preventDefault();
      e.stopImmediatePropagation();
      hidePopup();
      return;
    }
    if (e.key === "Tab" && isPopupVisible) {
      e.preventDefault();
      e.stopImmediatePropagation();
      const items = Array.from(commandMentionList.querySelectorAll("[data-value]"));
      const el = items[activeIndex];
      if (el) applySelection(el.dataset.value);
      return;
    }
    if (e.key === "ArrowDown") {
      if (isPopupVisible) {
        e.preventDefault();
        e.stopImmediatePropagation();
        const items = Array.from(commandMentionList.querySelectorAll("[data-value]"));
        activeIndex = Math.min(items.length - 1, activeIndex + 1);
        items.forEach((el, idx) => el.classList.toggle("active", idx === activeIndex));
        items[activeIndex]?.scrollIntoView({ block: "nearest" });
      } else {
        // History Down
        if (historyIndex > -1) {
          e.preventDefault();
          historyIndex -= 1;
          commandInput.value = historyIndex === -1 ? "" : commandHistory[historyIndex];
          setTimeout(() => commandInput.setSelectionRange(commandInput.value.length, commandInput.value.length), 0);
        }
      }
    } else if (e.key === "ArrowUp") {
      if (isPopupVisible) {
        e.preventDefault();
        e.stopImmediatePropagation();
        const items = Array.from(commandMentionList.querySelectorAll("[data-value]"));
        activeIndex = Math.max(0, activeIndex - 1);
        items.forEach((el, idx) => el.classList.toggle("active", idx === activeIndex));
        items[activeIndex]?.scrollIntoView({ block: "nearest" });
      } else {
        // History Up
        if (historyIndex < commandHistory.length - 1) {
          e.preventDefault();
          historyIndex += 1;
          commandInput.value = commandHistory[historyIndex];
          setTimeout(() => commandInput.setSelectionRange(commandInput.value.length, commandInput.value.length), 0);
        }
      }
    } else if (e.key === "Enter") {
      if (isPopupVisible) {
        const items = Array.from(commandMentionList.querySelectorAll("[data-value]"));
        const el = items[activeIndex];
        if (el) {
          e.preventDefault();
          e.stopImmediatePropagation();
          applySelection(el.dataset.value);
        }
      }
    }
  });

  commandInput.addEventListener("blur", () => {
    setTimeout(() => hidePopup(), 120);
  });
}

function initSpawnMobMentions() {
  if (!spawnMobName || !spawnMobMentionPopup || !spawnMobMentionList) return;

  let activeIndex = 0;

  const MOB_SUGGESTIONS = Array.isArray(window.MinecraftSuggestions?.mobs) ? window.MinecraftSuggestions.mobs : [];

  function hidePopup() {
    spawnMobMentionPopup.classList.add("d-none");
    spawnMobMentionList.innerHTML = "";
    activeIndex = 0;
  }

  function showPopup() {
    spawnMobMentionPopup.classList.remove("d-none");
  }

  function applySelection(value) {
    spawnMobName.value = value;
    spawnMobName.setSelectionRange(value.length, value.length);
    hidePopup();
    spawnMobName.focus();
  }

  function renderList(items, query) {
    const q = String(query || "");
    spawnMobMentionList.innerHTML = "";
    items.forEach((mobId, idx) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = `list-group-item list-group-item-action d-flex align-items-center justify-content-between ${idx === activeIndex ? "active" : ""}`;
      const safe = String(mobId);
      const prefixLen = q && safe.toLowerCase().startsWith(q.toLowerCase()) ? q.length : 0;
      el.innerHTML = `<div><i class="bi bi-bug me-2"></i>${prefixLen ? `<strong>${safe.slice(0, prefixLen)}</strong>${safe.slice(prefixLen)}` : safe}</div>`;
      el.dataset.value = safe;
      el.onclick = () => applySelection(safe);
      spawnMobMentionList.appendChild(el);
    });
  }

  function updatePopupFromInput() {
    const raw = String(spawnMobName.value || "").trim();
    const q = raw.toLowerCase();

    const items = (q ? MOB_SUGGESTIONS.filter((m) => m.toLowerCase().includes(q)) : MOB_SUGGESTIONS.slice(0))
      .slice(0, 15);

    if (items.length === 0) return hidePopup();
    renderList(items, raw);
    showPopup();
  }

  spawnMobName.addEventListener("input", () => {
    activeIndex = 0;
    updatePopupFromInput();
  });

  spawnMobName.addEventListener("focus", () => {
    activeIndex = 0;
    updatePopupFromInput();
  });

  spawnMobName.addEventListener("keydown", (e) => {
    const isPopupVisible = !spawnMobMentionPopup.classList.contains("d-none");
    if (e.key === "Escape" && isPopupVisible) {
      e.preventDefault();
      e.stopImmediatePropagation();
      hidePopup();
      return;
    }
    if ((e.key === "Tab" || e.key === "Enter") && isPopupVisible) {
      const items = Array.from(spawnMobMentionList.querySelectorAll("[data-value]"));
      const el = items[activeIndex];
      if (el) {
        e.preventDefault();
        e.stopImmediatePropagation();
        applySelection(el.dataset.value);
      }
      return;
    }
    if (e.key === "ArrowDown" && isPopupVisible) {
      e.preventDefault();
      e.stopImmediatePropagation();
      const items = Array.from(spawnMobMentionList.querySelectorAll("[data-value]"));
      activeIndex = Math.min(items.length - 1, activeIndex + 1);
      items.forEach((el, idx) => el.classList.toggle("active", idx === activeIndex));
      items[activeIndex]?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (e.key === "ArrowUp" && isPopupVisible) {
      e.preventDefault();
      e.stopImmediatePropagation();
      const items = Array.from(spawnMobMentionList.querySelectorAll("[data-value]"));
      activeIndex = Math.max(0, activeIndex - 1);
      items.forEach((el, idx) => el.classList.toggle("active", idx === activeIndex));
      items[activeIndex]?.scrollIntoView({ block: "nearest" });
    }
  });

  spawnMobName.addEventListener("blur", () => {
    setTimeout(() => hidePopup(), 120);
  });

  spawnMobMentionPopup.addEventListener("mousedown", (e) => {
    // Prevent input blur before click selection.
    e.preventDefault();
  });
}

function initGiveItemMentions() {
  if (!giveItemName || !giveItemMentionPopup || !giveItemMentionList) return;

  let activeIndex = 0;

  const ITEM_SUGGESTIONS = Array.isArray(window.MinecraftSuggestions?.items) ? window.MinecraftSuggestions.items : [];

  function hidePopup() {
    giveItemMentionPopup.classList.add("d-none");
    giveItemMentionList.innerHTML = "";
    activeIndex = 0;
  }

  function showPopup() {
    giveItemMentionPopup.classList.remove("d-none");
  }

  function applySelection(value) {
    giveItemName.value = value;
    giveItemName.setSelectionRange(value.length, value.length);
    hidePopup();
    giveItemName.focus();
  }

  function renderList(items, query) {
    const q = String(query || "");
    giveItemMentionList.innerHTML = "";
    items.forEach((itemId, idx) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = `list-group-item list-group-item-action d-flex align-items-center justify-content-between ${idx === activeIndex ? "active" : ""}`;
      const safe = String(itemId);
      const prefixLen = q && safe.toLowerCase().startsWith(q.toLowerCase()) ? q.length : 0;
      el.innerHTML = `<div><i class="bi bi-box-seam me-2"></i>${prefixLen ? `<strong>${safe.slice(0, prefixLen)}</strong>${safe.slice(prefixLen)}` : safe}</div>`;
      el.dataset.value = safe;
      el.onclick = () => applySelection(safe);
      giveItemMentionList.appendChild(el);
    });
  }

  function updatePopupFromInput() {
    const raw = String(giveItemName.value || "").trim();
    const q = raw.toLowerCase();
    const items = (q ? ITEM_SUGGESTIONS.filter((m) => m.toLowerCase().includes(q)) : ITEM_SUGGESTIONS.slice(0))
      .slice(0, 15);
    if (items.length === 0) return hidePopup();
    renderList(items, raw);
    showPopup();
  }

  giveItemName.addEventListener("input", () => {
    activeIndex = 0;
    updatePopupFromInput();
  });

  giveItemName.addEventListener("focus", () => {
    activeIndex = 0;
    updatePopupFromInput();
  });

  giveItemName.addEventListener("keydown", (e) => {
    const isPopupVisible = !giveItemMentionPopup.classList.contains("d-none");
    if (e.key === "Escape" && isPopupVisible) {
      e.preventDefault();
      e.stopImmediatePropagation();
      hidePopup();
      return;
    }
    if ((e.key === "Tab" || e.key === "Enter") && isPopupVisible) {
      const items = Array.from(giveItemMentionList.querySelectorAll("[data-value]"));
      const el = items[activeIndex];
      if (el) {
        e.preventDefault();
        e.stopImmediatePropagation();
        applySelection(el.dataset.value);
      }
      return;
    }
    if (e.key === "ArrowDown" && isPopupVisible) {
      e.preventDefault();
      e.stopImmediatePropagation();
      const items = Array.from(giveItemMentionList.querySelectorAll("[data-value]"));
      activeIndex = Math.min(items.length - 1, activeIndex + 1);
      items.forEach((el, idx) => el.classList.toggle("active", idx === activeIndex));
      items[activeIndex]?.scrollIntoView({ block: "nearest" });
      return;
    }
    if (e.key === "ArrowUp" && isPopupVisible) {
      e.preventDefault();
      e.stopImmediatePropagation();
      const items = Array.from(giveItemMentionList.querySelectorAll("[data-value]"));
      activeIndex = Math.max(0, activeIndex - 1);
      items.forEach((el, idx) => el.classList.toggle("active", idx === activeIndex));
      items[activeIndex]?.scrollIntoView({ block: "nearest" });
    }
  });

  giveItemName.addEventListener("blur", () => {
    setTimeout(() => hidePopup(), 120);
  });

  giveItemMentionPopup.addEventListener("mousedown", (e) => {
    e.preventDefault();
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
  const gridLines = [0.25, 0.5, 0.75]
    .map((p) => {
      const y = (height - p * height).toFixed(2);
      return `<line x1="0" y1="${y}" x2="${width}" y2="${y}" stroke="rgba(255,255,255,0.06)" stroke-width="0.5" />`;
    })
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" style="display: block; width: 100%; height: 100%;">
      ${gridLines}
      <polyline
        fill="none"
        stroke="${color}"
        stroke-width="1.5"
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
  if (clear) {
    if (cpuHistoryChart) cpuHistoryChart.innerHTML = "";
    if (memHistoryChart) memHistoryChart.innerHTML = "";
  }
}

function renderHistoricalCharts(history) {
  hasHistoricalPerformance = Boolean(history && Array.isArray(history) && history.length >= 2);
  if (openHistoricalPerfBtn) openHistoricalPerfBtn.disabled = !hasHistoricalPerformance;
  if (!hasHistoricalPerformance) return;
  
  const cpuValues = history.map(h => h.cpu);
  const memValues = history.map(h => h.mem);

  if (cpuHistoryChart) cpuHistoryChart.innerHTML = sparklineSvg(cpuValues, "rgba(77, 171, 255, 0.8)", 400, 60);
  if (memHistoryChart) memHistoryChart.innerHTML = sparklineSvg(memValues, "rgba(255, 193, 7, 0.8)", 400, 60);
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
  const noPropsWarning = document.getElementById("noServerPropertiesWarning");
  if (noPropsWarning) {
    noPropsWarning.classList.toggle("d-none", propKeys.length !== 0);
  }
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
      
      // Update History
      if (commandHistory[0] !== command) {
        commandHistory.unshift(command);
        if (commandHistory.length > 50) commandHistory.pop();
        try {
          localStorage.setItem(STORAGE_KEYS.commandHistory, JSON.stringify(commandHistory));
        } catch (_e) {}
      }
      historyIndex = -1;
      
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
  initSpawnMobMentions();
  initGiveItemMentions();
  initSidebarBackdrop();
  initFromHash();
  initBackupSorting();
  initQuickMacros();
  initChatUI();
  initConsoleSplitView();
  initConsoleMobileTabs();
  initHistoricalPerformanceModal();
  initMotdToolbox();
  initPlayerActions();
  initActivePlayerActionButtons();
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

function initConsoleSplitView() {
  const splitView = document.querySelector("#section-console .split-view");
  const primary = document.querySelector("#section-console .split-pane-primary");
  const secondary = document.getElementById("chatPanel");
  const divider = document.getElementById("consoleSplitDivider");
  if (!splitView || !primary || !secondary || !divider) return;

  function isMobileLayout() {
    return window.matchMedia("(max-width: 991.98px)").matches;
  }

  function setPrimaryPct(pct) {
    const clamped = Math.max(15, Math.min(85, Number(pct)));
    primary.style.flex = `0 0 ${clamped}%`;
    primary.style.flexBasis = `${clamped}%`;
    secondary.style.flex = "1 1 auto";
  }

  function loadPct() {
    const key = isMobileLayout() ? STORAGE_SPLIT_KEYS.consoleSplitMobilePct : STORAGE_SPLIT_KEYS.consoleSplitDesktopPct;
    try {
      const stored = Number(localStorage.getItem(key));
      if (Number.isFinite(stored) && stored >= 15 && stored <= 85) return stored;
    } catch (_e) {}
    return isMobileLayout() ? 60 : 70;
  }

  function savePct(pct) {
    const key = isMobileLayout() ? STORAGE_SPLIT_KEYS.consoleSplitMobilePct : STORAGE_SPLIT_KEYS.consoleSplitDesktopPct;
    try {
      localStorage.setItem(key, String(pct));
    } catch (_e) {}
  }

  function applyInitial() {
    setPrimaryPct(loadPct());
  }

  function updateDividerVisibility() {
    const hide = secondary.classList.contains("d-none");
    divider.classList.toggle("d-none", hide);
    splitView.classList.toggle("split-secondary-hidden", hide);
  }

  applyInitial();
  updateDividerVisibility();

  const observer = new MutationObserver(() => updateDividerVisibility());
  observer.observe(secondary, { attributes: true, attributeFilter: ["class"] });

  let dragging = false;
  let startPos = 0;
  let startPct = 0;

  function getPos(evt) {
    return isMobileLayout() ? evt.clientY : evt.clientX;
  }

  function pointerMove(evt) {
    if (!dragging) return;
    const rect = splitView.getBoundingClientRect();
    const size = isMobileLayout() ? rect.height : rect.width;
    const delta = getPos(evt) - startPos;
    const pctDelta = (delta / Math.max(1, size)) * 100;
    const next = Math.max(15, Math.min(85, startPct + pctDelta));
    setPrimaryPct(next);
    savePct(next);
  }

  function pointerUp() {
    if (!dragging) return;
    dragging = false;
    divider.classList.remove("dragging");
    window.removeEventListener("pointermove", pointerMove);
    window.removeEventListener("pointerup", pointerUp);
  }

  divider.addEventListener("pointerdown", (evt) => {
    if (secondary.classList.contains("d-none")) return;
    dragging = true;
    divider.classList.add("dragging");
    divider.setPointerCapture?.(evt.pointerId);
    startPos = getPos(evt);
    const current = primary.getBoundingClientRect();
    const total = splitView.getBoundingClientRect();
    startPct = isMobileLayout() ? (current.height / Math.max(1, total.height)) * 100 : (current.width / Math.max(1, total.width)) * 100;
    window.addEventListener("pointermove", pointerMove);
    window.addEventListener("pointerup", pointerUp, { once: true });
  });

  window.addEventListener("resize", () => applyInitial());
}

function initConsoleMobileTabs() {
  const splitView = document.querySelector("#section-console .split-view");
  const secondary = document.getElementById("chatPanel");
  const divider = document.getElementById("consoleSplitDivider");
  const btnLogs = document.getElementById("consoleTabLogs");
  const btnChat = document.getElementById("consoleTabChat");
  if (!splitView || !secondary || !divider || !btnLogs || !btnChat) return;

  function isMobileLayout() {
    return window.matchMedia("(max-width: 991.98px)").matches;
  }

  function getStoredTab() {
    try {
      const stored = String(localStorage.getItem(STORAGE_SPLIT_KEYS.consoleMobileTab) || "").toLowerCase();
      if (stored === "chat" || stored === "logs") return stored;
    } catch (_e) {}
    return "logs";
  }

  function storeTab(tab) {
    try {
      localStorage.setItem(STORAGE_SPLIT_KEYS.consoleMobileTab, tab);
    } catch (_e) {}
  }

  function setActiveTab(tab) {
    const next = tab === "chat" ? "chat" : "logs";
    splitView.classList.toggle("mobile-tab-logs", next === "logs");
    splitView.classList.toggle("mobile-tab-chat", next === "chat");
    btnLogs.classList.toggle("active", next === "logs");
    btnChat.classList.toggle("active", next === "chat");
    storeTab(next);
  }

  function syncAvailability() {
    const chatAvailable = !secondary.classList.contains("d-none");
    btnChat.disabled = !chatAvailable;
    if (isMobileLayout()) {
      divider.classList.add("d-none");
    }
    if (!isMobileLayout()) {
      splitView.classList.remove("mobile-tab-logs", "mobile-tab-chat");
      divider.classList.toggle("d-none", !chatAvailable);
      return;
    }
    if (!chatAvailable && splitView.classList.contains("mobile-tab-chat")) {
      setActiveTab("logs");
    }
  }

  btnLogs.addEventListener("click", () => setActiveTab("logs"));
  btnChat.addEventListener("click", () => {
    if (btnChat.disabled) return;
    setActiveTab("chat");
  });

  const observer = new MutationObserver(() => syncAvailability());
  observer.observe(secondary, { attributes: true, attributeFilter: ["class"] });

  setActiveTab(getStoredTab());
  syncAvailability();
  window.addEventListener("resize", () => syncAvailability());
}

function initHistoricalPerformanceModal() {
  if (!openHistoricalPerfBtn) return;
  openHistoricalPerfBtn.disabled = true;
  openHistoricalPerfBtn.addEventListener("click", () => {
    if (!hasHistoricalPerformance) {
      showError("Historical performance data is not available yet.");
      return;
    }
    historicalPerfModal?.show();
  });
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
  toolboxCopyDropdownMenu?.addEventListener("click", async (event) => {
    const button = event.target?.closest?.("[data-copy-type]");
    if (!button || !button.dataset.copyType) return;
    setToolboxCopyType(button.dataset.copyType);
    const command = buildToolboxCommand(button.dataset.copyType, (motdInput.value || "").trim());
    if (!command) return;
    const ok = await copyTextToClipboard(command, toolboxCopyBtn);
    if (!ok) showError("Copy failed.");
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
  return copyTextToClipboard(command);
}

async function copyTextToClipboard(text, btn = null) {
  if (!text) return false;
  let ok = false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      ok = true;
    } else {
      ok = fallbackCopyText(text);
    }
  } catch (_e) {
    ok = fallbackCopyText(text);
  }

  if (ok && btn) {
    const originalHtml = btn.innerHTML;
    const originalWidth = btn.offsetWidth;
    const originalOpacity = btn.style.opacity || "1";
    btn.style.width = `${originalWidth}px`;
    btn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Copied!';
    btn.style.opacity = "0.85";
    setTimeout(() => {
      btn.innerHTML = originalHtml;
      btn.style.width = "";
      btn.style.opacity = originalOpacity;
    }, 2000);
  }
  return ok;

  function fallbackCopyText(value) {
    try {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "absolute";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      const success = document.execCommand("copy");
      document.body.removeChild(textarea);
      return Boolean(success);
    } catch (_e) {
      return false;
    }
  }
}

function setToolboxCopyType(type) {
  const normalized = (type || "say").toLowerCase();
  toolboxCopyType = normalized;
  if (!toolboxCopyDropdownMenu) return;
  toolboxCopyDropdownMenu.querySelectorAll("[data-copy-type]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.copyType === normalized);
  });
}

function updateToolboxCopyButtonState() {
  if (!toolboxCopyBtn || !motdInput) return;
  const hasInput = Boolean((motdInput.value || "").trim());
  toolboxCopyBtn.disabled = !hasInput;
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

  if (chatNotificationToastEl) {
    chatNotificationToastEl.style.cursor = "pointer";
    chatNotificationToastEl.addEventListener("click", () => {
      showSection("console");
      chatNotificationToast?.hide();
    });
  }

  const chatPrefixModalEl = document.getElementById("chatPrefixModal");
  if (chatPrefixModalEl) {
    chatPrefixModal = new bootstrap.Modal(chatPrefixModalEl);
  }

  const chatPrefixBtn = document.getElementById("chatPrefixBtn");
  const chatPrefixInput = document.getElementById("chatPrefixInput");
  const saveChatPrefixBtn = document.getElementById("saveChatPrefixBtn");

  chatPrefixBtn?.addEventListener("click", () => {
    if (chatPrefixInput) {
      chatPrefixInput.value = chatPrefix.trim();
      chatPrefixModal?.show();
    }
  });

  saveChatPrefixBtn?.addEventListener("click", () => {
    if (chatPrefixInput) {
      let val = chatPrefixInput.value.trim();
      if (val) {
        chatPrefix = val + " ";
      } else {
        chatPrefix = "";
      }

      if (chatPrefixBtn) {
        if (chatPrefix) {
          chatPrefixBtn.classList.add("text-primary");
          chatPrefixBtn.classList.remove("text-white");
        } else {
          chatPrefixBtn.classList.add("text-white");
          chatPrefixBtn.classList.remove("text-primary");
        }
      }
    }
    chatPrefixModal?.hide();
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
  const now = Date.now();
  const uid = `${now}-${Math.random().toString(16).slice(2)}`;
  
  // Deduplication: If inbound message matches a recent outbound one, ignore it
  if (entry.direction === "inbound") {
    const isDuplicate = chatMessages.some(msg => {
      if (msg.direction !== "outbound") return false;
      // Check if text matches
      if (msg.text !== entry.text) return false;
      // Check if sender matches prefix (if set)
      if (msg.prefix && entry.sender && entry.sender.indexOf(msg.prefix.trim()) === -1) return false;
      // Check timestamp proximity (last 3 seconds)
      const msgTime = parseInt(msg.uid.split("-")[0]);
      return (now - msgTime) < 3000;
    });
    if (isDuplicate) return;
  }

  chatMessages.push({ ...entry, uid });
  if (chatMessages.length > CHAT_MESSAGE_LIMIT) {
    chatMessages.shift();
  }
  renderChatMessages();
  persistChatHistory();

  // Show notification if it's an inbound message and chat tab is not active
  if (entry.direction === "inbound" && currentSection !== "console" && chatNotificationToast) {
    const chatNotificationBody = document.getElementById("chatNotificationBody");
    if (chatNotificationBody) {
      chatNotificationBody.textContent = `${entry.sender || "Player"}: ${entry.text}`;
      chatNotificationToast.show();
    }
  }
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

    // Check if this inbound message already exists in chatMessages (prevent reload duplicates)
    const alreadyPresent = chatMessages.some(m => 
      m.direction === "inbound" && 
      m.sender === parsed.sender && 
      m.text === parsed.text
    );
    if (alreadyPresent) continue;

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
    const label = isInbound ? (msg.sender || "Player") : (msg.prefix?.trim() || "You");
    const row = document.createElement("div");
    row.className = `chat-row ${isInbound ? "chat-row-inbound" : "chat-row-outbound"}`;
    row.innerHTML = `
      <div class="chat-bubble ${isInbound ? "chat-bubble-inbound" : "chat-bubble-outbound"} ${msg.uid === shouldAnimateUid ? "chat-pop" : ""}" data-chat-uid="${msg.uid || ""}">
        <div class="chat-meta small opacity-75">
          <div class="chat-label">
            <i class="bi ${isInbound ? "bi-person-fill" : "bi-send-fill"} me-1"></i>
            <span>${escapeHtml(label)}</span>
          </div>
          <span class="chat-timestamp ms-2">${msg.timestamp || ""}</span>
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
    if (chatPrefix) {
      const fullText = `${chatPrefix}${text}`;
      const tellrawJson = JSON.stringify({ rawtext: [{ text: fullText }] });
      await sendServerCommand(`tellraw ${target} ${tellrawJson}`, { skipRefresh: true });
    } else {
      await sendServerCommand(`tell ${target} ${text}`, { skipRefresh: true });
    }
    pushChatMessage({
      direction: "outbound",
      text,
      prefix: chatPrefix,
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
    // Immediate refresh to pull latest logs/chat from server
    refreshStatus();
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
        
        // Try to set lastChatLogLine to the last inbound message's original format if we have it
        // Or at least avoid re-ingesting what we already have.
        // Actually, just knowing we HAVE messages helps ingestChatFromLogs decide.
      }
    });

    // We don't have the "raw" log line stored, but we can prevent the very first 
    // ingestChatFromLogs from adding the "fallback" tail if we already have history.
    if (chatMessages.length > 0) {
      // setting it to a non-null but not-matching value will force the fallback 
      // check, but we want to avoid duplicates.
      // Better: update ingestChatFromLogs to check if message already exists.
    }
  } catch (_e) {}
}

function initQuickMacros() {
  quickMacroForm?.addEventListener("submit", handleMacroSubmit);
  quickMacroModalEl?.addEventListener("hidden.bs.modal", resetMacroForm);
  quickMacroDeleteBtn?.addEventListener("click", handleMacroDelete);
  quickMacroOutputBtn?.addEventListener("click", () => {
    const macroId = quickMacroIdInput?.value;
    const macro = quickMacros.find(m => m.id === macroId);
    if (macro) openMacroOutput(macro);
  });
  quickMacroIconInput?.addEventListener("change", updateQuickMacroCustomIconVisibility);
  quickMacroTriggerSelect?.addEventListener("change", () => {
    updateQuickMacroIntervalVisibility();
    updateQuickMacroKeywordVisibility();
    updateQuickMacroTimeVisibility();
  });
  updateQuickMacroCustomIconVisibility();
  quickMacroTriggerBtn?.addEventListener("click", () => resetMacroForm());
  initMacroVariablesUI();
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
    const varsPayload = payload.variables;
    quickMacros = Array.isArray(macrosPayload) ? macrosPayload : [];
    presetMacros = Array.isArray(presetsPayload) ? presetsPayload : [];
    macroVariables = Array.isArray(varsPayload) ? varsPayload : [];
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
        : trigger === "player_connected"
        ? "On player connect"
        : trigger === "player_leave"
        ? "On player leave"
        : trigger === "player_death"
        ? "On player death"
        : trigger === "server_started"
        ? "On server start"
        : trigger === "server_stopped"
        ? "On server stop"
        : trigger === "interval" && macro.interval_seconds && Number(macro.interval_seconds) > 0
        ? `Auto every ${macro.interval_seconds}s`
        : trigger === "time" && macro.time_of_day
        ? `Daily at ${macro.time_of_day}`
        : trigger === "chat_keyword" && macro.chat_keyword
        ? `On chat keyword: ${macro.chat_keyword}`
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
  player_connected: "player_connected",
  player_leave: "player_leave",
  player_death: "player_death",
  server_started: "server_started",
  server_stopped: "server_stopped",
  chat_keyword: "chat_keyword",
  time: "time",
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
  if (quickMacroIntervalInput) {
    quickMacroIntervalInput.value =
      preset.interval_seconds && Number(preset.interval_seconds) > 0 ? String(Math.floor(Number(preset.interval_seconds))) : "";
  }
  if (quickMacroKeywordInput) {
    quickMacroKeywordInput.value = (preset.chat_keyword || "").trim();
  }
  if (quickMacroTimeInput) {
    quickMacroTimeInput.value = (preset.time_of_day || "").trim();
  }
  updateQuickMacroKeywordVisibility();
  updateQuickMacroTimeVisibility();
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

function updateQuickMacroTimeVisibility() {
  if (!quickMacroTriggerSelect || !quickMacroTimeWrapper) return;
  const trigger = (quickMacroTriggerSelect.value || "manual").toLowerCase();
  quickMacroTimeWrapper.classList.toggle("d-none", trigger !== "time");
}

async function activateMacro(macro) {
  if (!macro) return;
  const playerName = (chatRecipient && chatRecipient.id && !chatRecipient.id.startsWith("@")) ? chatRecipient.id : "";
  await sendCommand("run_macro", { 
    macro_id: macro.id, 
    macro_title: macro.title, 
    commands: macro.commands,
    player_name: playerName
  });
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
  const timeValue = quickMacroTimeInput ? quickMacroTimeInput.value.trim() : "";
  const trigger = (quickMacroTriggerSelect?.value || (intervalValue ? "interval" : "manual")).toString().toLowerCase();
  const payload = {
    title,
    icon,
    commands,
    trigger,
  };
  if (trigger === "chat_keyword") {
    const keyword = (quickMacroKeywordInput?.value || "").trim();
    if (!keyword) {
      showError("Chat keyword is required for chat keyword macros.");
      return;
    }
    payload.chat_keyword = keyword;
  }
  if (trigger === "time") {
    if (!timeValue) {
      showError("Time of day is required for time-based macros.");
      return;
    }
    payload.time_of_day = timeValue;
  }
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
  if (quickMacroKeywordInput) {
    quickMacroKeywordInput.value = macro.chat_keyword || "";
  }
  if (quickMacroTimeInput) {
    quickMacroTimeInput.value = macro.time_of_day || "";
  }
  if (quickMacroTriggerSelect) {
    const triggerValue = normalizeMacroTrigger(
      macro.trigger || (macro.interval_seconds ? "interval" : "manual")
    );
    quickMacroTriggerSelect.value = triggerValue;
  }
  updateQuickMacroCustomIconVisibility();
  updateQuickMacroIntervalVisibility();
  updateQuickMacroKeywordVisibility();
  updateQuickMacroTimeVisibility();
  if (quickMacroModalTitle) {
    quickMacroModalTitle.textContent = "Editing macro";
  }
  quickMacroDeleteBtn?.classList.remove("d-none");
  quickMacroDeleteBtn && (quickMacroDeleteBtn.disabled = false);
  quickMacroOutputBtn?.classList.remove("d-none");
  quickMacroModal?.show();
}

function resetMacroForm() {
  quickMacroForm?.reset();
  quickMacroCustomIconInput && (quickMacroCustomIconInput.value = "");
  if (quickMacroIntervalInput) {
    quickMacroIntervalInput.value = "";
  }
  if (quickMacroKeywordInput) {
    quickMacroKeywordInput.value = "";
  }
  if (quickMacroTimeInput) {
    quickMacroTimeInput.value = "";
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
  updateQuickMacroKeywordVisibility();
  updateQuickMacroTimeVisibility();
  quickMacroDeleteBtn?.classList.add("d-none");
  quickMacroDeleteBtn && (quickMacroDeleteBtn.disabled = false);
  quickMacroOutputBtn?.classList.add("d-none");
}

function initMacroVariablesUI() {
  const macroVarsModalEl = document.getElementById("macroVarsModal");
  const macroVarsModal = macroVarsModalEl ? new bootstrap.Modal(macroVarsModalEl) : null;
  const macroVarsList = document.getElementById("macroVarsList");
  const macroVarsEmpty = document.getElementById("macroVarsEmpty");
  const addMacroVarBtn = document.getElementById("addMacroVarBtn");
  const addRandomMacroVarBtn = document.getElementById("addRandomMacroVarBtn");
  const saveMacroVarsBtn = document.getElementById("saveMacroVarsBtn");
  if (!macroVarsModal || !macroVarsList || !saveMacroVarsBtn) return;

  function normalizeVarName(name) {
    const raw = String(name || "").trim();
    if (!raw) return "";
    if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(raw)) return "";
    return raw;
  }

  function buildRow(variable = {}) {
    const name = String(variable.name || "").trim();
    const type = String(variable.type || "static").trim().toLowerCase();
    const value = String(variable.value || "");
    const items = Array.isArray(variable.items) ? variable.items : [];

    const card = document.createElement("div");
    card.className = "card bg-black border-secondary";
    card.innerHTML = `
      <div class="card-body p-3">
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <div class="flex-grow-1" style="min-width: 180px;">
            <label class="form-label small text-muted mb-1">Name</label>
            <input type="text" class="form-control bg-dark border-secondary text-white macro-var-name" placeholder="e.g. kit_name" value="${escapeHtml(name)}">
            <div class="form-text text-muted">Use as <code>{${escapeHtml(name || "var")}}</code></div>
          </div>
          <div style="min-width: 170px;">
            <label class="form-label small text-muted mb-1">Type</label>
            <select class="form-select bg-dark border-secondary text-white macro-var-type">
              <option value="static" ${type !== "random" ? "selected" : ""}>Static value</option>
              <option value="random" ${type === "random" ? "selected" : ""}>Random from list</option>
            </select>
          </div>
          <div class="ms-auto">
            <button type="button" class="btn btn-sm btn-outline-danger macro-var-delete">
              <i class="bi bi-trash"></i>
            </button>
          </div>
        </div>

        <div class="mt-3 macro-var-static ${type === "random" ? "d-none" : ""}">
          <label class="form-label small text-muted mb-1">Value</label>
          <input type="text" class="form-control bg-dark border-secondary text-white macro-var-value" placeholder="e.g. diamond_sword" value="${escapeHtml(value)}">
        </div>

        <div class="mt-3 macro-var-random ${type === "random" ? "" : "d-none"}">
          <label class="form-label small text-muted mb-1">Items (one per line)</label>
          <textarea class="form-control bg-dark border-secondary text-white macro-var-items" rows="3" placeholder="e.g.\napple\ngolden_apple\nbread">${escapeHtml(items.join("\n"))}</textarea>
          <div class="form-text text-muted">One item will be chosen at random each time a macro runs.</div>
        </div>
      </div>
    `;

    const typeSel = card.querySelector(".macro-var-type");
    const staticWrap = card.querySelector(".macro-var-static");
    const randomWrap = card.querySelector(".macro-var-random");
    const delBtn = card.querySelector(".macro-var-delete");
    delBtn.onclick = () => {
      card.remove();
      updateEmptyState();
    };
    typeSel.onchange = () => {
      const t = String(typeSel.value || "static").toLowerCase();
      staticWrap.classList.toggle("d-none", t === "random");
      randomWrap.classList.toggle("d-none", t !== "random");
    };
    return card;
  }

  function updateEmptyState() {
    const hasAny = macroVarsList.children.length > 0;
    macroVarsEmpty?.classList.toggle("d-none", hasAny);
  }

  function openModal() {
    macroVarsList.innerHTML = "";
    (macroVariables || []).forEach((v) => macroVarsList.appendChild(buildRow(v)));
    updateEmptyState();
    macroVarsModal.show();
  }

  function collectVariables() {
    const rows = Array.from(macroVarsList.querySelectorAll(".card"));
    const out = [];
    const seen = new Set();
    for (const row of rows) {
      const nameRaw = row.querySelector(".macro-var-name")?.value;
      const name = normalizeVarName(nameRaw);
      if (!name) throw new Error("Variable names must match: A-Z, 0-9, _, - (and can’t start with a number).");
      if (seen.has(name)) throw new Error(`Duplicate variable name: ${name}`);
      seen.add(name);
      const type = String(row.querySelector(".macro-var-type")?.value || "static").toLowerCase();
      if (type === "random") {
        const itemsText = String(row.querySelector(".macro-var-items")?.value || "");
        const items = itemsText
          .split(/\r?\n/)
          .map((s) => s.trim())
          .filter(Boolean);
        if (!items.length) throw new Error(`Random variable "${name}" needs at least 1 item.`);
        out.push({ name, type: "random", items });
      } else {
        const value = String(row.querySelector(".macro-var-value")?.value || "");
        out.push({ name, type: "static", value });
      }
    }
    return out;
  }

  async function saveVariables() {
    const vars = collectVariables();
    saveMacroVarsBtn.disabled = true;
    try {
      const response = await fetch("/api/macros", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ set_variables: true, variables: vars }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Failed to save variables.");
      if (Array.isArray(body.variables)) macroVariables = body.variables;
      showToast("Variables saved.", "success");
      macroVarsModal.hide();
    } finally {
      saveMacroVarsBtn.disabled = false;
    }
  }

  openMacroVarsBtn?.addEventListener("click", openModal);
  addMacroVarBtn?.addEventListener("click", () => {
    macroVarsList.appendChild(buildRow({ type: "static" }));
    updateEmptyState();
  });
  addRandomMacroVarBtn?.addEventListener("click", () => {
    macroVarsList.appendChild(buildRow({ type: "random", items: [""] }));
    updateEmptyState();
  });
  saveMacroVarsBtn?.addEventListener("click", async () => {
    try {
      await saveVariables();
    } catch (err) {
      showError(err?.message || "Unable to save variables.");
    }
  });
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

function updateQuickMacroKeywordVisibility() {
  if (!quickMacroTriggerSelect || !quickMacroKeywordWrapper) return;
  const trigger = (quickMacroTriggerSelect.value || "manual").toLowerCase();
  quickMacroKeywordWrapper.classList.toggle("d-none", trigger !== "chat_keyword");
}

function formatMacroRunLog(run) {
  if (!run) return "";
  const lines = [];
  const title = run.macro_title ? `${run.macro_title}` : "Macro";
  lines.push(`${title} (run ${run.id})`);
  if (run.started_at) lines.push(`Started: ${new Date(run.started_at * 1000).toLocaleString()}`);
  if (run.finished_at) lines.push(`Finished: ${new Date(run.finished_at * 1000).toLocaleString()}`);
  if (typeof run.success === "boolean") lines.push(`Success: ${run.success ? "Yes" : "No"}`);
  lines.push("");
  const steps = Array.isArray(run.steps) ? run.steps : [];
  steps.forEach((step, i) => {
    lines.push(`Step ${i + 1}: ${step.success ? "OK" : "FAIL"}  ${step.command}`);
    const out = Array.isArray(step.output) ? step.output : [];
    if (step.truncated) lines.push("(output truncated)");
    out.forEach((l) => lines.push(String(l).replace(/\n$/, "")));
    lines.push("");
  });
  return lines.join("\n").trim() + "\n";
}

async function openMacroOutput(macro) {
  if (!macroOutputModal || !macro || !macro.id) return;
  try {
    const response = await fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "get_latest_macro_run", data: { macro_id: macro.id } }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Failed to load macro output.");
    const run = payload.result?.run;
    if (!run) throw new Error("No run data available.");
    const text = formatMacroRunLog(run);
    if (macroOutputModalTitle) macroOutputModalTitle.textContent = `Macro Output: ${macro.title || ""}`.trim();
    if (macroOutputMeta) {
      const parts = [];
      if (run.started_at) parts.push(`Started ${new Date(run.started_at * 1000).toLocaleString()}`);
      if (typeof run.success === "boolean") parts.push(run.success ? "Success" : "Failed");
      macroOutputMeta.textContent = parts.join(" • ");
    }
    if (macroOutputPre) macroOutputPre.textContent = text;
    if (macroOutputCopyBtn) {
      macroOutputCopyBtn.onclick = async () => {
        const ok = await copyTextToClipboard(text, macroOutputCopyBtn);
        if (!ok) showError("Copy failed.");
      };
    }
    if (macroOutputDownloadBtn) {
      macroOutputDownloadBtn.onclick = () => {
        const filename = `macro-run-${run.id}.log`;
        const blob = new Blob([text], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 250);
      };
    }
    macroOutputModal.show();
  } catch (err) {
    console.error(err);
    showError(err.message || "Unable to load macro output.");
  }
}

// --- Player Action Handlers ---
async function handlePlayerAction(player, action) {
  _currentPlayerTarget = player;
  let command = "";
  let confirmMessage = "";
  let successMessage = "";

  if (!player || !action) return;

  if (action === "kick") {
    confirmMessage = `Kick ${player}?`;
    successMessage = `${player} has been kicked.`;
  } else if (action === "ban") {
    command = `ban ${quoteMinecraftArg(player)}`;
    confirmMessage = `Are you sure you want to ban ${player}? This will prevent them from rejoining.`;
    successMessage = `${player} has been banned.`;
  } else if (action === "op") {
    command = `op ${quoteMinecraftArg(player)}`;
    confirmMessage = `Are you sure you want to promote ${player} to operator?`;
    successMessage = `${player} is now an operator.`;
  } else if (action === "spawn_at") {
    command = `execute at ${quoteMinecraftArg(player)} run setworldspawn ~ ~ ~`;
    confirmMessage = `Set world spawn to ${player}'s current location?`;
    successMessage = `World spawn set to ${player}'s location.`;
  }

  if (confirmMessage) {
    const confirmOptions = {
      title: "Confirm",
      confirmText: "Confirm",
      confirmClass: "btn-primary",
    };
    if (action === "kick") {
      confirmOptions.title = "Kick player";
      confirmOptions.confirmText = "Kick";
      confirmOptions.confirmClass = "btn-warning";
      confirmOptions.input = {
        label: "Reason (optional)",
        placeholder: "e.g. Please rejoin in 5 minutes",
        help: "The player will be kicked immediately",
        maxLength: 120,
        required: false,
      };
    } else if (action === "ban") {
      confirmOptions.title = "Ban player";
      confirmOptions.confirmText = "Ban";
      confirmOptions.confirmClass = "btn-danger";
      confirmOptions.input = {
        label: "Reason (optional)",
        placeholder: "e.g. Griefing",
        help: "Adds an optional reason to the ban command (server must support it).",
        maxLength: 120,
        required: false,
      };
    } else if (action === "op") {
      confirmOptions.title = "Grant operator";
      confirmOptions.confirmText = "Make OP";
      confirmOptions.confirmClass = "btn-warning";
    }

    showConfirm(confirmMessage, async (inputValue) => {
      if (action === "kick") {
        const rawReason = String(inputValue || "").replace(/[\r\n]+/g, " ").trim();
        command = `kick ${quoteMinecraftArg(player)}${rawReason ? ` ${rawReason}` : ""}`;
      } else if (action === "ban") {
        const rawReason = String(inputValue || "").replace(/[\r\n]+/g, " ").trim();
        command = `ban ${quoteMinecraftArg(player)}${rawReason ? ` ${rawReason}` : ""}`;
      }
      if (!command) return;
      try {
        const response = await sendCommand("send_command", { command: command });
        if (response.success) {
          showToast(successMessage, "success");
          refreshStatus(); // Refresh status to update player list, OP status, etc.
        } else {
          showError(response.error || `Failed to ${action} ${player}.`);
        }
      } catch (err) {
        showError(`Error sending command: ${err.message}`);
      }
    }, confirmOptions);
  }
}

function openSpawnMobDialog(player) {
  _currentPlayerTarget = player;
  if (spawnMobTargetPlayer) spawnMobTargetPlayer.textContent = player;
  if (spawnMobName) spawnMobName.value = (spawnMobName.value || "").trim() || "zombie";
  if (spawnMobCount) spawnMobCount.value = spawnMobCount.value || "1";
  spawnMobModal?.show();
  setTimeout(() => spawnMobName?.focus(), 50);
}

function normalizeMobId(input) {
  const raw = (input || "").trim();
  if (!raw) return "";
  return raw.toLowerCase();
}

function isSafeMobId(mobId) {
  if (!mobId) return false;
  // Allow common Bedrock identifiers like "zombie" or "minecraft:zombie".
  // Block whitespace and shell-like injection characters.
  return /^[a-z0-9_.:-]+$/.test(mobId);
}

function openTeleportDialog(player) {
  _currentPlayerTarget = player;
  if (tpSourcePlayer) tpSourcePlayer.textContent = player;
  if (tpCustomSelector) tpCustomSelector.value = ""; // Clear custom selector
  if (tpPlayerList) {
    tpPlayerList.innerHTML = ""; // Clear existing players
    const candidates = _allActivePlayers.filter((p) => p !== player); // Don't allow teleporting to self
    if (candidates.length === 0) {
      const empty = document.createElement("div");
      empty.className = "list-group-item bg-body-secondary border-secondary-subtle text-body-secondary small";
      empty.textContent = "No other players online.";
      tpPlayerList.appendChild(empty);
    }
    candidates.forEach((p, idx) => {
        const id = `tpTarget-${idx}`;
        const div = document.createElement("div");
        div.className = "list-group-item list-group-item-action bg-body-secondary border-secondary-subtle d-flex align-items-center gap-2 py-2";
        div.innerHTML = `
          <input class="form-check-input m-0" type="radio" name="tpTargetPlayer" id="${id}">
          <label class="mb-0 flex-grow-1 text-truncate" for="${id}"></label>
        `;
        const input = div.querySelector("input");
        const label = div.querySelector("label");
        if (input) input.value = p;
        if (label) label.textContent = p;
        tpPlayerList.appendChild(div);
      });
  }
  teleportModal?.show();
}

function openGiveDialog(player) {
  _currentPlayerTarget = player;
  if (giveTargetPlayer) giveTargetPlayer.textContent = player;
  if (giveItemName) giveItemName.value = "";
  if (giveItemAmount) giveItemAmount.value = "1";
  giveModal?.show();
}

// --- Init Player Actions ---
function initPlayerActions() {
  function updateTpSelectedStyles() {
    if (!tpPlayerList) return;
    const rows = Array.from(tpPlayerList.querySelectorAll('input[type="radio"][name="tpTargetPlayer"]'));
    rows.forEach((radio) => {
      const item = radio.closest(".list-group-item");
      if (!item) return;
      item.classList.toggle("active", radio.checked);
      item.classList.toggle("border-primary", radio.checked);
      item.classList.toggle("bg-body-secondary", !radio.checked);
    });
  }

  if (confirmTpBtn) {
    confirmTpBtn.onclick = async () => {
      let targetSelector = (tpCustomSelector.value || "").trim();
      if (!targetSelector) {
        // If custom selector is empty, check radio buttons
        const selectedRadio = tpPlayerList.querySelector('input[name="tpTargetPlayer"]:checked');
        if (selectedRadio) {
          targetSelector = selectedRadio.value;
        }
      }

      if (!_currentPlayerTarget || !targetSelector) {
        showError("Please specify a target for teleportation.");
        return;
      }

      const command = `tp ${quoteMinecraftArg(_currentPlayerTarget)} ${formatTeleportTarget(targetSelector)}`;
      try {
        const response = await sendCommand("send_command", { command: command });
        if (response.success) {
          showToast(`Teleported ${_currentPlayerTarget} to ${targetSelector}.`, "success");
          teleportModal?.hide();
        } else {
          showError(response.error || `Failed to teleport ${_currentPlayerTarget}.`);
        }
      } catch (err) {
        showError(`Error sending command: ${err.message}`);
      }
    };
  }

  if (confirmGiveBtn) {
    confirmGiveBtn.onclick = async () => {
      const itemName = (giveItemName.value || "").trim();
      const itemAmount = parseInt(giveItemAmount.value || "1", 10);

      if (!_currentPlayerTarget || !itemName) {
        showError("Please specify an item name to give.");
        return;
      }
      if (isNaN(itemAmount) || itemAmount < 1) {
        showError("Item amount must be a positive number.");
        return;
      }

      const command = `give ${quoteMinecraftArg(_currentPlayerTarget)} ${itemName} ${itemAmount}`;
      try {
        const response = await sendCommand("send_command", { command: command });
        if (response.success) {
          showToast(`Gave ${itemAmount} ${itemName} to ${_currentPlayerTarget}.`, "success");
          giveModal?.hide();
        } else {
          showError(response.error || `Failed to give item to ${_currentPlayerTarget}.`);
        }
      } catch (err) {
        showError(`Error sending command: ${err.message}`);
      }
    };
  }

  if (confirmSpawnMobBtn) {
    confirmSpawnMobBtn.onclick = async () => {
      const mobId = normalizeMobId(spawnMobName?.value);
      const count = parseInt(spawnMobCount?.value || "1", 10);

      if (!_currentPlayerTarget) {
        showError("No player selected.");
        return;
      }
      if (!mobId) {
        showError("Please choose a mob to spawn.");
        return;
      }
      if (!isSafeMobId(mobId)) {
        showError("Mob id contains invalid characters. Use something like zombie or minecraft:zombie.");
        return;
      }
      if (isNaN(count) || count < 1) {
        showError("Mob count must be a positive number.");
        return;
      }
      if (count > 50) {
        showError("Mob count is capped at 50 to prevent flooding.");
        return;
      }

      const player = _currentPlayerTarget;
      // Close the spawn dialog so the confirmation modal is visible on mobile.
      spawnMobModal?.hide();
      showConfirm(`Spawn ${count} ${mobId} at ${player}?`, async () => {
        confirmSpawnMobBtn.disabled = true;
        try {
          for (let i = 0; i < count; i++) {
            const command = `execute at ${quoteMinecraftArg(player)} run summon ${mobId} ~ ~ ~`;
            // eslint-disable-next-line no-await-in-loop
            const response = await sendCommand("send_command", { command });
            if (!response?.success) {
              throw new Error(response?.error || "Failed to summon.");
            }
          }
          showToast(`Spawned ${count} ${mobId} at ${player}.`, "success");
          spawnMobModal?.hide();
        } catch (err) {
          showError(err?.message || "Failed to spawn mob(s).");
        } finally {
          confirmSpawnMobBtn.disabled = false;
        }
      });
    };
  }

  // Clear custom selector when a radio button is selected
  tpCustomSelector?.addEventListener("focus", () => {
    if (tpPlayerList) {
      const selectedRadio = tpPlayerList.querySelector('input[name="tpTargetPlayer"]:checked');
      if (selectedRadio) {
        selectedRadio.checked = false;
        updateTpSelectedStyles();
      }
    }
  });

  // Clear radio button selection when custom selector is typed into
  tpCustomSelector?.addEventListener("input", () => {
    if (!tpPlayerList) return;
    const selectedRadio = tpPlayerList.querySelector('input[name="tpTargetPlayer"]:checked');
    if (selectedRadio) selectedRadio.checked = false;
    updateTpSelectedStyles();
  });

  // Clear custom selector and update selected row styling when a radio is selected
  tpPlayerList?.addEventListener("change", (event) => {
    if (event.target?.type === "radio" && tpCustomSelector) {
      tpCustomSelector.value = "";
      updateTpSelectedStyles();
    }
  });
}

function initActivePlayerActionButtons() {
  const playerList = document.getElementById("playerList");
  if (!playerList) return;
  playerList.addEventListener("click", (e) => {
    const btn = e.target.closest?.("button[data-player-action][data-player]");
    if (!btn) return;
    const player = btn.dataset.player;
    const action = btn.dataset.playerAction;
    if (!player || !action) return;
    if (action === "tp") return openTeleportDialog(player);
    if (action === "give") return openGiveDialog(player);
    if (action === "spawn_mob_at") return openSpawnMobDialog(player);
    return handlePlayerAction(player, action);
  });
}
