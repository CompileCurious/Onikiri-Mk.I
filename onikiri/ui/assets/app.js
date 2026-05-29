// =============================================================================
// Onikiri Mk.I — HMI application
// =============================================================================

const moduleDefaults = {
  "AUTO-RECON": { module: "network_scanner", module_action: "inventory", params: {} },
  "SYS TOOLS":  { module: "system_info",    module_action: "snapshot",  params: {} },
};

const panelOrder = [
  "WI-FI",      "AUTO-RECON",  "ROGUE AP",
  "MITM",       "USB GADGET",  "BLE/NFC",
  "EXPLOITS",   "SYS TOOLS",   "DASHBOARD",
];

// Per-tile metadata: icon glyph, descriptive label, required hardware key, backend module names
const PANEL_META = {
  "WI-FI":      { icon: "≈≈≈",  desc: "WI-FI OFFENSE",   hw: "alfa_wifi",  mods: ["wifi_recon"] },
  "AUTO-RECON": { icon: "◎",  desc: "NETWORK RECON",    hw: null,          mods: ["network_scanner"] },
  "ROGUE AP":   { icon: "⊗",  desc: "ROGUE AP ENGINE",  hw: "alfa_wifi",  mods: [] },
  "MITM":       { icon: "⇌",  desc: "MITM ENGINE",      hw: null,          mods: ["mitm"] },
  "USB GADGET": { icon: "⊞",  desc: "USB GADGET MODE",  hw: null,          mods: ["hid_gadget", "gadget_automation"] },
  "BLE/NFC":    { icon: "◈",  desc: "BLE / NFC RECON",  hw: "ble_nfc",    mods: ["bluetooth_recon"] },
  "EXPLOITS":   { icon: "⊘",  desc: "EXPLOIT SUITE",    hw: null,          mods: [] },
  "SYS TOOLS":  { icon: "⊟",  desc: "SYSTEM TOOLS",     hw: null,          mods: ["system_info"] },
  "DASHBOARD":  { icon: "▦",  desc: "HUD / DASHBOARD",  hw: null,          mods: [] },
};

function hasHardware(hwKey, hardware) {
  if (!hwKey) return true;
  if (hwKey === "ble_nfc") return !!(hardware.bluetooth || hardware.nfc);
  return !!hardware[hwKey];
}

const panelGrid = document.getElementById("panel-grid");
const panelTemplate = document.getElementById("panel-template");
const overlay = document.getElementById("overlay");
const overlayTitle = document.getElementById("overlay-title");
const overlayContent = document.getElementById("overlay-content");
const overlayClose = document.getElementById("overlay-close");
const wipeButton = document.getElementById("wipe-button");
const dashboardView = document.getElementById("dashboard-view");
const longPressMs = 450;

// =============================================================================
// Shared utilities
// =============================================================================

function setOverlay(title, payload) {
  overlayTitle.textContent = title;
  overlayContent.textContent = JSON.stringify(payload, null, 2);
  overlay.classList.remove("hidden");
}

function closeOverlay() {
  overlay.classList.add("hidden");
}

overlayClose.addEventListener("click", closeOverlay);
overlay.addEventListener("click", (event) => {
  if (event.target === overlay) closeOverlay();
});

async function api(path, options = {}) {
  const response = await fetch(path, options);
  return response.json();
}

async function apiPost(path, body = {}) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// =============================================================================
// Dashboard
// =============================================================================

function clearPanels() {
  panelGrid.replaceChildren();
}

function renderPanels(modules, jobs, hardware) {
  clearPanels();
  // Set of actively-running backend module names
  const runningMods = new Set(
    modules.filter((m) => m.status === "active" || m.running).map((m) => m.name)
  );
  let procCount = 0;

  panelOrder.forEach((label) => {
    const meta = PANEL_META[label] || { icon: "▣", desc: label, hw: null, mods: [] };
    const node = panelTemplate.content.firstElementChild.cloneNode(true);

    node.querySelector(".panel-icon").textContent = meta.icon;
    node.querySelector(".panel-label").textContent = label;

    const hwOk = hasHardware(meta.hw, hardware);
    const isRunning = meta.mods.some((m) => runningMods.has(m));
    const hasMod = modules.find((m) => meta.mods.includes(m.name));
    const statusText = node.querySelector(".status-text");
    const hwDot = node.querySelector(".hw-dot");

    if (!hwOk) {
      // Required hardware absent — grey tile, no glow
      node.classList.add("no-hardware");
      statusText.textContent = "NO HARDWARE";
      hwDot.classList.add("hw-dot-missing");
    } else {
      if (hasMod?.status === "error") {
        node.classList.add("error");
        statusText.textContent = "ERROR";
      } else if (isRunning) {
        node.classList.add("running");
        statusText.textContent = "RUNNING";
        procCount++;
      } else {
        statusText.textContent = "INACTIVE";
      }
      // Show bright hw indicator only for tiles that need specific hardware
      if (meta.hw) hwDot.classList.add("hw-dot-ok");
    }

    let longPressTimer = null;
    let didLongPress = false;
    const startLongPress = () => {
      didLongPress = false;
      longPressTimer = setTimeout(() => {
        didLongPress = true;
        if (isRunning && hwOk) {
          openStopDialog(label);
        } else {
          setOverlay(label, { module: meta.desc, hardware: hwOk ? "PRESENT" : "ABSENT", requires: meta.hw || "NONE" });
        }
      }, longPressMs);
    };
    const clearLongPress = () => {
      if (longPressTimer) clearTimeout(longPressTimer);
      longPressTimer = null;
    };

    node.addEventListener("pointerdown", startLongPress);
    node.addEventListener("pointerup", async () => {
      const wasLong = didLongPress;
      clearLongPress();
      if (wasLong) return;

      if (!hwOk) {
        setOverlay(label, { status: "HARDWARE UNAVAILABLE", requires: meta.hw });
        return;
      }

      // Tiles with dedicated views
      if (label === "MITM")       { openMitmView();   return; }
      if (label === "USB GADGET") { openGadgetView(); return; }

      // Quick-run tiles
      if (label in moduleDefaults) {
        node.classList.remove("flash");
        void node.offsetWidth;
        node.classList.add("flash");
        const panelConfig = moduleDefaults[label];
        const payload = await apiPost("/api/run", panelConfig);
        setOverlay(label, payload);
        refreshDashboard();
        return;
      }

      // Tiles pending full implementation
      setOverlay(label, { status: "PENDING", module: meta.desc, info: "dedicated view coming soon" });
    });
    node.addEventListener("pointerleave", clearLongPress);
    node.addEventListener("pointercancel", clearLongPress);
    panelGrid.appendChild(node);
  });

  // Update active process count badge in topbar
  const procBadge = document.getElementById("proc-badge");
  const procCountEl = document.getElementById("proc-count");
  if (procCount > 0) {
    procCountEl.textContent = procCount;
    procBadge.classList.remove("hidden");
  } else {
    procBadge.classList.add("hidden");
  }
}

async function refreshDashboard() {
  const state = await api("/api/state");
  renderPanels(state.modules || [], state.jobs || [], state.hardware || {});
}

wipeButton.addEventListener("click", async () => {
  const result = await apiPost("/api/wipe", {});
  setOverlay("WIPE", result);
  refreshDashboard();
});

refreshDashboard();
setInterval(refreshDashboard, 3000);

// =============================================================================
// Stop-process dialog
// =============================================================================

const stopDialog = document.getElementById("stop-dialog");
const stopDialogLabel = document.getElementById("stop-dialog-label");
const stopDialogConfirm = document.getElementById("stop-dialog-confirm");
const stopDialogCancel = document.getElementById("stop-dialog-cancel");
let stopDialogTarget = null;

function openStopDialog(label) {
  stopDialogTarget = label;
  stopDialogLabel.textContent = label;
  stopDialog.classList.remove("hidden");
}

stopDialogCancel.addEventListener("click", () => {
  stopDialog.classList.add("hidden");
  stopDialogTarget = null;
});

stopDialogConfirm.addEventListener("click", async () => {
  if (!stopDialogTarget) return;
  stopDialog.classList.add("hidden");
  const resp = await apiPost("/api/stop_module", { label: stopDialogTarget });
  setOverlay("STOP: " + stopDialogTarget, resp);
  stopDialogTarget = null;
  refreshDashboard();
});

// =============================================================================
// MITM view
// =============================================================================

const mitmView = document.getElementById("mitm-view");
const mitmBack = document.getElementById("mitm-back");
const mitmDot = document.getElementById("mitm-dot");
const mitmStatusLabel = document.getElementById("mitm-status-label");
const mitmStartBtn = document.getElementById("mitm-start-btn");
const mitmStopBtn = document.getElementById("mitm-stop-btn");
const mitmVectorSel = document.getElementById("mitm-vector");
const mitmIface = document.getElementById("mitm-iface");
const mitmGateway = document.getElementById("mitm-gateway");
const mitmTarget = document.getElementById("mitm-target");
const mitmPort = document.getElementById("mitm-port");
const mitmGenCa = document.getElementById("mitm-gen-ca");
const addRuleBtn = document.getElementById("add-rule-btn");
const ruleList = document.getElementById("rule-list");
const ruleCountEl = document.getElementById("rule-count");
const ruleEditor = document.getElementById("rule-editor");
const edCondType = document.getElementById("ed-cond-type");
const edCondOp = document.getElementById("ed-cond-op");
const edCondValue = document.getElementById("ed-cond-value");
const edActionType = document.getElementById("ed-action-type");
const edActionValue = document.getElementById("ed-action-value");
const edRuleName = document.getElementById("ed-rule-name");
const edSave = document.getElementById("ed-save");
const edCancel = document.getElementById("ed-cancel");
const edSecondaryRow = document.getElementById("ed-secondary-row");
const edSecondaryA = document.getElementById("ed-secondary-a");
const edSecondaryB = document.getElementById("ed-secondary-b");
const edError = document.getElementById("ed-error");

// Actions that need a header-name / find-replace secondary field
const DUAL_VALUE_ACTIONS = new Set(["substitute", "modify_header", "strip_header"]);

let mitmSchema = {};
let mitmRules = [];
let mitmRefreshTimer = null;

function openMitmView() {
  dashboardView.classList.add("hidden");
  mitmView.classList.remove("hidden");
  if (mitmRefreshTimer) clearInterval(mitmRefreshTimer);
  refreshMitmView();
  mitmRefreshTimer = setInterval(refreshMitmView, 3000);
}

function closeMitmView() {
  mitmView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
  if (mitmRefreshTimer) { clearInterval(mitmRefreshTimer); mitmRefreshTimer = null; }
}

mitmBack.addEventListener("click", closeMitmView);

async function refreshMitmView() {
  try {
    const state = await api("/api/mitm/state");
    applyMitmState(state);
  } catch (_) {}
}

function applyMitmState(state) {
  mitmSchema = state.schema || {};
  mitmRules = state.rules || [];

  // Status indicator
  const running = Boolean(state.running);
  mitmDot.classList.toggle("active", running);
  mitmStatusLabel.textContent = running ? "ACTIVE" : "INACTIVE";

  // Populate vector dropdown (once)
  if (mitmVectorSel.options.length === 0 && state.vectors) {
    state.vectors.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = v.label + (v.available ? "" : " [UNAVAIL]");
      mitmVectorSel.appendChild(opt);
    });
  }

  // Populate condition/action dropdowns in editor (once)
  if (edCondType.options.length === 0 && mitmSchema.condition_types) {
    mitmSchema.condition_types.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = mitmSchema.condition_labels?.[t] || t.toUpperCase();
      edCondType.appendChild(opt);
    });
  }
  if (edCondOp.options.length === 0 && mitmSchema.operators) {
    mitmSchema.operators.forEach((op) => {
      const opt = document.createElement("option");
      opt.value = op;
      opt.textContent = mitmSchema.operator_labels?.[op] || op.toUpperCase();
      edCondOp.appendChild(opt);
    });
  }
  if (edActionType.options.length === 0 && mitmSchema.action_types) {
    mitmSchema.action_types.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = mitmSchema.action_labels?.[t] || t.toUpperCase();
      edActionType.appendChild(opt);
    });
  }

  renderRuleList(mitmRules);
}

// ------------------------------------------------------------------
// Rule list rendering
// ------------------------------------------------------------------

function renderRuleList(rules) {
  ruleCountEl.textContent = rules.length;
  ruleList.replaceChildren();
  rules.forEach((rule, idx) => {
    const block = document.createElement("div");
    block.className = "rule-block" + (rule.enabled ? "" : " disabled");
    block.dataset.id = rule.id;

    const condLabel = mitmSchema.condition_labels?.[rule.condition?.type] || rule.condition?.type || "";
    const opLabel = mitmSchema.operator_labels?.[rule.condition?.operator] || rule.condition?.operator || "";
    const actLabel = mitmSchema.action_labels?.[rule.action?.type] || rule.action?.type || "";

    block.innerHTML = `
      <div class="rule-summary">
        <span class="rule-name-label">${escHtml(rule.name || "UNNAMED")}</span>
        <span class="rule-detail">
          <span class="rule-kw-inline">IF</span>${escHtml(condLabel)} ${escHtml(opLabel)} <em>${escHtml(rule.condition?.value || "")}</em>
        </span>
        <span class="rule-detail">
          <span class="rule-kw-inline">THEN</span>${escHtml(actLabel)} <em>${escHtml(ruleActionSummary(rule.action))}</em>
        </span>
      </div>
      <div class="rule-actions">
        <button class="rule-toggle-${rule.enabled ? "on" : "off"}" data-action="toggle" data-id="${rule.id}">${rule.enabled ? "ON" : "OFF"}</button>
        <button data-action="up" data-id="${rule.id}" ${idx === 0 ? "disabled" : ""}>▲</button>
        <button data-action="down" data-id="${rule.id}" ${idx === rules.length - 1 ? "disabled" : ""}>▼</button>
        <button class="danger" data-action="remove" data-id="${rule.id}">✕</button>
      </div>
    `;
    ruleList.appendChild(block);
  });

  // Delegated event handling on the list
  ruleList.onclick = (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const { action, id } = btn.dataset;
    handleRuleAction(action, id);
  };
}

function ruleActionSummary(act) {
  if (!act) return "";
  const t = act.type || "";
  if (t === "substitute") return `${act.find || ""} → ${act.replace || ""}`;
  if (t === "modify_header" || t === "strip_header") return act.header_name || "";
  return act.value || "";
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function handleRuleAction(action, ruleId) {
  let resp;
  if (action === "toggle") {
    resp = await apiPost("/api/mitm/rules/toggle", { rule_id: ruleId });
  } else if (action === "remove") {
    resp = await apiPost("/api/mitm/rules/remove", { rule_id: ruleId });
  } else if (action === "up") {
    resp = await apiPost("/api/mitm/rules/move_up", { rule_id: ruleId });
  } else if (action === "down") {
    resp = await apiPost("/api/mitm/rules/move_down", { rule_id: ruleId });
  }
  if (resp?.rules) {
    mitmRules = resp.rules;
    renderRuleList(mitmRules);
    ruleCountEl.textContent = mitmRules.length;
  }
}

// ------------------------------------------------------------------
// Rule editor
// ------------------------------------------------------------------

function openRuleEditor() {
  edRuleName.value = "";
  edCondValue.value = "";
  edActionValue.value = "";
  edSecondaryA.value = "";
  edSecondaryB.value = "";
  edError.classList.add("hidden");
  edError.textContent = "";
  toggleSecondaryRow();
  ruleEditor.classList.remove("hidden");
  edRuleName.focus();
}

function closeRuleEditor() {
  ruleEditor.classList.add("hidden");
}

function toggleSecondaryRow() {
  const needsSecondary = DUAL_VALUE_ACTIONS.has(edActionType.value);
  edSecondaryRow.classList.toggle("hidden", !needsSecondary);
  if (edActionType.value === "substitute") {
    edSecondaryA.placeholder = "FIND TEXT";
    edSecondaryB.placeholder = "REPLACE WITH";
    edSecondaryB.classList.remove("hidden");
  } else if (edActionType.value === "modify_header") {
    edSecondaryA.placeholder = "HEADER NAME";
    edSecondaryB.placeholder = "HEADER VALUE";
    edSecondaryB.classList.remove("hidden");
  } else if (edActionType.value === "strip_header") {
    edSecondaryA.placeholder = "HEADER NAME";
    edSecondaryB.classList.add("hidden");
  }
}

edActionType.addEventListener("change", toggleSecondaryRow);

addRuleBtn.addEventListener("click", openRuleEditor);
edCancel.addEventListener("click", closeRuleEditor);

edSave.addEventListener("click", async () => {
  edError.classList.add("hidden");

  const condType = edCondType.value;
  const condOp = edCondOp.value;
  const condValue = edCondValue.value.trim();
  const actionType = edActionType.value;
  const name = edRuleName.value.trim() || `RULE ${mitmRules.length + 1}`;

  if (!condValue) {
    showEditorError("CONDITION VALUE IS REQUIRED");
    return;
  }

  const condition = { type: condType, operator: condOp, value: condValue };
  const action = buildAction(actionType);
  if (!action) return;

  const rule = {
    name,
    enabled: true,
    priority: mitmRules.length,
    condition,
    action,
  };

  const resp = await apiPost("/api/mitm/rules/add", rule);
  if (resp.status === "error") {
    showEditorError(resp.error || "SAVE FAILED");
    return;
  }
  mitmRules = resp.rules || mitmRules;
  renderRuleList(mitmRules);
  closeRuleEditor();
});

function buildAction(type) {
  const val = edActionValue.value.trim();
  if (type === "substitute") {
    return { type, find: edSecondaryA.value.trim(), replace: edSecondaryB.value.trim() };
  }
  if (type === "modify_header") {
    const hname = edSecondaryA.value.trim();
    if (!hname) { showEditorError("HEADER NAME IS REQUIRED"); return null; }
    return { type, header_name: hname, value: edSecondaryB.value.trim() };
  }
  if (type === "strip_header") {
    const hname = edSecondaryA.value.trim();
    if (!hname) { showEditorError("HEADER NAME IS REQUIRED"); return null; }
    return { type, header_name: hname };
  }
  if (type === "block") {
    return { type };
  }
  if (!val) { showEditorError("ACTION VALUE IS REQUIRED"); return null; }
  return { type, value: val };
}

function showEditorError(msg) {
  edError.textContent = msg;
  edError.classList.remove("hidden");
}

// ------------------------------------------------------------------
// MITM start / stop
// ------------------------------------------------------------------

mitmStartBtn.addEventListener("click", async () => {
  const params = {
    vector: mitmVectorSel.value,
    interface: mitmIface.value.trim(),
    gateway_ip: mitmGateway.value.trim(),
    target_ip: mitmTarget.value.trim(),
    listen_port: parseInt(mitmPort.value.trim(), 10) || 8080,
    ssl_port: 8443,
  };
  const resp = await apiPost("/api/mitm/start", params);
  setOverlay("MITM START", resp);
  refreshMitmView();
});

mitmStopBtn.addEventListener("click", async () => {
  const resp = await apiPost("/api/mitm/stop", {});
  setOverlay("MITM STOP", resp);
  refreshMitmView();
});

mitmGenCa.addEventListener("click", async () => {
  const resp = await apiPost("/api/mitm/generate_ca", {
    ca_name: "Onikiri-CA",
  });
  setOverlay("GENERATE CA", resp);
});

// =============================================================================
// HID view
// =============================================================================

const hidView = document.getElementById("hid-view");
const hidBack = document.getElementById("hid-back");
const hidDot = document.getElementById("hid-dot");
const hidStatusLabel = document.getElementById("hid-status-label");
const hidStartBtn = document.getElementById("hid-start-btn");
const hidStopBtn = document.getElementById("hid-stop-btn");
const hidDeviceSel = document.getElementById("hid-device-profile");
const hidDeviceAddBtn = document.getElementById("hid-device-add-btn");
const hidDeviceDelBtn = document.getElementById("hid-device-del-btn");
const hidDeviceEditor = document.getElementById("hid-device-editor");
const deLabel = document.getElementById("de-label");
const deVid = document.getElementById("de-vid");
const dePid = document.getElementById("de-pid");
const deMfr = document.getElementById("de-mfr");
const deProduct = document.getElementById("de-product");
const deSerial = document.getElementById("de-serial");
const deSave = document.getElementById("de-save");
const deCancel = document.getElementById("de-cancel");
const deError = document.getElementById("de-error");
const hidSeqName = document.getElementById("hid-seq-name");
const hidSetupBtn = document.getElementById("hid-setup-btn");
const hidTeardownBtn = document.getElementById("hid-teardown-btn");
const hidSdFile = document.getElementById("hid-sd-file");
const hidSdPreviewBtn = document.getElementById("hid-sd-preview-btn");
const hidSdImportBtn = document.getElementById("hid-sd-import-btn");
const hidSdRunBtn = document.getElementById("hid-sd-run-btn");
const hidSdPreviewBox = document.getElementById("hid-sd-preview-box");
const addBlockBtn = document.getElementById("add-block-btn");
const blockList = document.getElementById("block-list");
const blockCountEl = document.getElementById("block-count");
const blockEditor = document.getElementById("block-editor");
const beCategory = document.getElementById("be-category");
const beType = document.getElementById("be-type");
const beParams = document.getElementById("be-params");
const beSave = document.getElementById("be-save");
const beCancel = document.getElementById("be-cancel");
const beError = document.getElementById("be-error");

let hidSchema = {};
let hidBlocks = [];
let hidDevices = {};
let hidRefreshTimer = null;

function openHidView() {
  dashboardView.classList.add("hidden");
  hidView.classList.remove("hidden");
  if (hidRefreshTimer) clearInterval(hidRefreshTimer);
  refreshHidView();
  hidRefreshTimer = setInterval(refreshHidView, 3000);
}

function closeHidView() {
  hidView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
  if (hidRefreshTimer) { clearInterval(hidRefreshTimer); hidRefreshTimer = null; }
}

hidBack.addEventListener("click", closeHidView);

async function refreshHidView() {
  try {
    const state = await api("/api/hid/state");
    applyHidState(state);
  } catch (_) {}
}

function applyHidState(state) {
  hidSchema = state.schema || {};
  hidBlocks = state.blocks || [];
  hidDevices = state.devices || {};

  const running = Boolean(state.running);
  hidDot.classList.toggle("active", running);
  hidStatusLabel.textContent = running ? "ACTIVE" : "INACTIVE";

  // Rebuild device dropdown — always refresh to reflect newly added custom profiles
  hidDevices = state.devices || {};
  rebuildDeviceSelect(hidDevices, state.device_profile);
  if (state.sequence_name) hidSeqName.value = state.sequence_name;

  renderBlockList(hidBlocks);
  refreshSdList();
}

// ------------------------------------------------------------------
// Block list rendering
// ------------------------------------------------------------------

function blockTypeSummary(block) {
  const t = block.type || "";
  const p = block.params || {};
  if (t === "type_text") return `TYPE: "${(p.text || "").substring(0, 32)}"` ;
  if (t === "press_key") return `KEY: ${p.key || ""}`;
  if (t === "key_combo") return `COMBO: ${(p.modifiers || []).join("+")}+${p.key || ""}`;
  if (t === "delay") return `DELAY ${p.ms || 0}ms`;
  if (t === "mouse_move") return `MOUSE MOVE (${p.x || 0}, ${p.y || 0})`;
  if (t === "mouse_click") return `MOUSE CLICK ${p.button || "left"}`;
  if (t === "mouse_scroll") return `SCROLL ${p.amount || 0}`;
  if (t === "loop_start") return `LOOP ×${p.count || 1}`;
  if (t === "loop_end") return "END LOOP";
  return (hidSchema.block_types?.[t]?.label || t).toUpperCase();
}

function renderBlockList(blocks) {
  blockCountEl.textContent = blocks.length;
  blockList.replaceChildren();
  blocks.forEach((block, idx) => {
    const row = document.createElement("div");
    row.className = "rule-block" + (block.enabled ? "" : " disabled");
    row.dataset.id = block.id;
    row.innerHTML = `
      <div class="rule-summary">
        <span class="rule-name-label">${escHtml(blockTypeSummary(block))}</span>
      </div>
      <div class="rule-actions">
        <button class="rule-toggle-${block.enabled ? "on" : "off"}" data-action="toggle" data-id="${block.id}">${block.enabled ? "ON" : "OFF"}</button>
        <button data-action="up" data-id="${block.id}" ${idx === 0 ? "disabled" : ""}>▲</button>
        <button data-action="down" data-id="${block.id}" ${idx === blocks.length - 1 ? "disabled" : ""}>▼</button>
        <button class="danger" data-action="remove" data-id="${block.id}">✕</button>
      </div>
    `;
    blockList.appendChild(row);
  });

  blockList.onclick = (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const { action, id } = btn.dataset;
    handleBlockAction(action, id);
  };
}

async function handleBlockAction(action, blockId) {
  let resp;
  if (action === "toggle") {
    resp = await apiPost("/api/hid/blocks/toggle", { block_id: blockId });
  } else if (action === "remove") {
    resp = await apiPost("/api/hid/blocks/remove", { block_id: blockId });
  } else if (action === "up") {
    resp = await apiPost("/api/hid/blocks/move_up", { block_id: blockId });
  } else if (action === "down") {
    resp = await apiPost("/api/hid/blocks/move_down", { block_id: blockId });
  }
  if (resp?.blocks) {
    hidBlocks = resp.blocks;
    renderBlockList(hidBlocks);
  }
}

// ------------------------------------------------------------------
// Block editor
// ------------------------------------------------------------------

const BLOCK_PARAM_DEFS = {
  type_text:    [{ key: "text", label: "TEXT", type: "textarea" }, { key: "delay_ms", label: "DELAY (ms)", type: "number", default: 20 }],
  press_key:    [{ key: "key", label: "KEY NAME", type: "text" }],
  hold_key:     [{ key: "key", label: "KEY NAME", type: "text" }],
  release_key:  [{ key: "key", label: "KEY NAME", type: "text" }],
  key_combo:    [{ key: "modifiers", label: "MODIFIERS (comma-sep)", type: "text" }, { key: "key", label: "KEY", type: "text" }],
  mouse_move:   [{ key: "x", label: "X", type: "number", default: 0 }, { key: "y", label: "Y", type: "number", default: 0 }, { key: "relative", label: "RELATIVE", type: "checkbox" }],
  mouse_click:  [{ key: "button", label: "BUTTON (left/right/middle)", type: "text", default: "left" }, { key: "count", label: "CLICKS", type: "number", default: 1 }],
  mouse_scroll: [{ key: "amount", label: "AMOUNT", type: "number", default: 3 }],
  delay:        [{ key: "ms", label: "DURATION (ms)", type: "number", default: 500 }],
  wait_window:  [{ key: "title", label: "WINDOW TITLE", type: "text" }, { key: "timeout_ms", label: "TIMEOUT (ms)", type: "number", default: 5000 }],
  loop_start:   [{ key: "count", label: "REPEAT COUNT", type: "number", default: 2 }],
  loop_end:     [],
  if_condition: [{ key: "variable", label: "VARIABLE", type: "text" }, { key: "value", label: "VALUE", type: "text" }],
  else_block:   [],
  endif:        [],
  open_run:     [{ key: "command", label: "COMMAND", type: "text" }],
  open_terminal:[],
  paste_clipboard: [{ key: "text", label: "TEXT", type: "textarea" }],
};

const BLOCK_CATEGORIES = {
  keyboard: ["type_text", "press_key", "hold_key", "release_key", "key_combo"],
  mouse: ["mouse_move", "mouse_click", "mouse_scroll"],
  timing: ["delay", "wait_window"],
  flow: ["loop_start", "loop_end", "if_condition", "else_block", "endif"],
  system: ["open_run", "open_terminal", "paste_clipboard"],
};

function populateCategorySelect() {
  if (beCategory.options.length > 0) return;
  Object.keys(BLOCK_CATEGORIES).forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = cat;
    opt.textContent = cat.toUpperCase();
    beCategory.appendChild(opt);
  });
  updateTypeSelect();
}

function updateTypeSelect() {
  beType.replaceChildren();
  const types = BLOCK_CATEGORIES[beCategory.value] || [];
  types.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = (hidSchema.block_types?.[t]?.label || t).toUpperCase();
    beType.appendChild(opt);
  });
  updateParamFields();
}

function updateParamFields() {
  beParams.replaceChildren();
  const defs = BLOCK_PARAM_DEFS[beType.value] || [];
  defs.forEach((def) => {
    const row = document.createElement("div");
    row.className = "editor-row";
    const lbl = document.createElement("span");
    lbl.className = "rule-kw";
    lbl.textContent = def.label;
    row.appendChild(lbl);
    if (def.type === "textarea") {
      const ta = document.createElement("textarea");
      ta.dataset.key = def.key;
      ta.className = "ed-input";
      ta.rows = 3;
      ta.style.resize = "vertical";
      row.appendChild(ta);
    } else if (def.type === "checkbox") {
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.key = def.key;
      cb.dataset.dtype = "bool";
      row.appendChild(cb);
    } else {
      const inp = document.createElement("input");
      inp.type = def.type === "number" ? "number" : "text";
      inp.dataset.key = def.key;
      inp.className = "ed-input";
      if (def.default !== undefined) inp.value = def.default;
      row.appendChild(inp);
    }
    beParams.appendChild(row);
  });
}

beCategory.addEventListener("change", updateTypeSelect);
beType.addEventListener("change", updateParamFields);

function openBlockEditor() {
  populateCategorySelect();
  beError.classList.add("hidden");
  beError.textContent = "";
  blockEditor.classList.remove("hidden");
}

function closeBlockEditor() {
  blockEditor.classList.add("hidden");
}

addBlockBtn.addEventListener("click", openBlockEditor);
beCancel.addEventListener("click", closeBlockEditor);

beSave.addEventListener("click", async () => {
  beError.classList.add("hidden");
  const type = beType.value;
  const params = {};
  beParams.querySelectorAll("[data-key]").forEach((el) => {
    const k = el.dataset.key;
    if (el.dataset.dtype === "bool") {
      params[k] = el.checked;
    } else if (el.type === "number") {
      params[k] = parseFloat(el.value) || 0;
    } else if (el.tagName === "TEXTAREA" || el.type === "text") {
      if (k === "modifiers") {
        params[k] = el.value.split(",").map((s) => s.trim()).filter(Boolean);
      } else {
        params[k] = el.value;
      }
    }
  });
  const block = { type, enabled: true, params };
  const resp = await apiPost("/api/hid/blocks/add", { block });
  if (resp.status === "error") {
    beError.textContent = resp.error || "SAVE FAILED";
    beError.classList.remove("hidden");
    return;
  }
  hidBlocks = resp.blocks || hidBlocks;
  renderBlockList(hidBlocks);
  closeBlockEditor();
});

// ------------------------------------------------------------------
// HID start / stop / setup / teardown
// ------------------------------------------------------------------

hidStartBtn.addEventListener("click", async () => {
  const resp = await apiPost("/api/hid/start", {});
  setOverlay("HID START", resp);
  refreshHidView();
});

hidStopBtn.addEventListener("click", async () => {
  const resp = await apiPost("/api/hid/stop", {});
  setOverlay("HID STOP", resp);
  refreshHidView();
});

hidSetupBtn.addEventListener("click", async () => {
  const resp = await apiPost("/api/hid/setup_gadget", { mouse: true });
  setOverlay("SETUP GADGET", resp);
});

hidTeardownBtn.addEventListener("click", async () => {
  const resp = await apiPost("/api/hid/teardown_gadget", {});
  setOverlay("TEARDOWN GADGET", resp);
});

hidDeviceSel.addEventListener("change", async () => {
  updateDeviceDelBtn();
  await apiPost("/api/hid/device/set", { profile_id: hidDeviceSel.value });
});

// ------------------------------------------------------------------
// Device ID management (add / remove custom profiles)
// ------------------------------------------------------------------

function rebuildDeviceSelect(devices, currentProfile) {
  hidDeviceSel.replaceChildren();
  Object.entries(devices).forEach(([id, dev]) => {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = (dev.label || dev.product || id) + (dev._custom ? " ★" : "");
    hidDeviceSel.appendChild(opt);
  });
  if (currentProfile && devices[currentProfile]) hidDeviceSel.value = currentProfile;
  updateDeviceDelBtn();
}

function updateDeviceDelBtn() {
  const dev = hidDevices[hidDeviceSel.value];
  hidDeviceDelBtn.disabled = !dev?._custom;
}

hidDeviceAddBtn.addEventListener("click", () => {
  deLabel.value = ""; deVid.value = ""; dePid.value = "";
  deMfr.value = ""; deProduct.value = ""; deSerial.value = "";
  deError.classList.add("hidden");
  hidDeviceEditor.classList.remove("hidden");
  deLabel.focus();
});

deCancel.addEventListener("click", () => hidDeviceEditor.classList.add("hidden"));

deSave.addEventListener("click", async () => {
  deError.classList.add("hidden");
  const vid = deVid.value.trim();
  const pid = dePid.value.trim();
  if (!vid || !pid) {
    deError.textContent = "VID AND PID ARE REQUIRED";
    deError.classList.remove("hidden");
    return;
  }
  const label = deLabel.value.trim() || deProduct.value.trim() || `${vid}:${pid}`;
  const resp = await apiPost("/api/hid/device/add", {
    label,
    vid, pid,
    manufacturer: deMfr.value.trim() || "Custom",
    product: deProduct.value.trim() || label,
    serial: deSerial.value.trim() || "CUSTOM001",
  });
  if (resp.status !== "ok") {
    deError.textContent = resp.error || "FAILED TO ADD DEVICE";
    deError.classList.remove("hidden");
    return;
  }
  hidDevices = resp.devices || hidDevices;
  hidDeviceEditor.classList.add("hidden");
  rebuildDeviceSelect(hidDevices, resp.profile_id);
  await apiPost("/api/hid/device/set", { profile_id: resp.profile_id });
});

hidDeviceDelBtn.addEventListener("click", async () => {
  const profileId = hidDeviceSel.value;
  if (!hidDevices[profileId]?._custom) return;
  const resp = await apiPost("/api/hid/device/remove", { profile_id: profileId });
  if (resp.status === "ok") {
    hidDevices = resp.devices || hidDevices;
    rebuildDeviceSelect(hidDevices, "generic_keyboard");
    await apiPost("/api/hid/device/set", { profile_id: "generic_keyboard" });
  }
});

// ------------------------------------------------------------------
// SD card browser
// ------------------------------------------------------------------

async function refreshSdList() {
  try {
    const resp = await api("/api/hid/sd/list");
    const files = resp.files || [];
    hidSdFile.replaceChildren();
    if (!files.length) {
      const opt = document.createElement("option");
      opt.textContent = "(no files)";
      opt.disabled = true;
      hidSdFile.appendChild(opt);
      return;
    }
    files.forEach((f) => {
      const opt = document.createElement("option");
      opt.value = f.name;
      opt.textContent = `${f.name} (${f.size}B)`;
      hidSdFile.appendChild(opt);
    });
  } catch (_) {}
}

hidSdPreviewBtn.addEventListener("click", async () => {
  const filename = hidSdFile.value;
  if (!filename || filename === "(no files)") return;
  const resp = await apiPost("/api/hid/sd/preview", { filename });
  if (resp.status === "ok") {
    hidSdPreviewBox.textContent = resp.preview + (resp.truncated ? "\n[TRUNCATED]" : "");
    hidSdPreviewBox.classList.remove("hidden");
  } else {
    hidSdPreviewBox.textContent = resp.error || "PREVIEW FAILED";
    hidSdPreviewBox.classList.remove("hidden");
  }
});

hidSdImportBtn.addEventListener("click", async () => {
  const filename = hidSdFile.value;
  if (!filename) return;
  const resp = await apiPost("/api/hid/sd/import", { filename });
  setOverlay("IMPORT", resp);
  if (resp.blocks) { hidBlocks = resp.blocks; renderBlockList(hidBlocks); }
});

hidSdRunBtn.addEventListener("click", async () => {
  const filename = hidSdFile.value;
  if (!filename) return;
  const resp = await apiPost("/api/hid/sd/run_raw", { filename });
  setOverlay("RUN RAW", resp);
  refreshHidView();
});

// =============================================================================
// Gadget Automation view
// =============================================================================

const gadgetView = document.getElementById("gadget-view");
const gadgetBack = document.getElementById("gadget-back");
const gadgetDot = document.getElementById("gadget-dot");
const gadgetStatusLabel = document.getElementById("gadget-status-label");
const gadgetRunBtn = document.getElementById("gadget-run-btn");
const gadgetStopBtn = document.getElementById("gadget-stop-btn");
const gadgetOsHint = document.getElementById("gadget-os-hint");
const gadgetWfSelect = document.getElementById("gadget-wf-select");
const gadgetProfileLabel = document.getElementById("gadget-profile-label");
const gadgetSwHid = document.getElementById("gadget-sw-hid");
const gadgetSwSerial = document.getElementById("gadget-sw-serial");
const gadgetSwEth = document.getElementById("gadget-sw-eth");
const gadgetSwComposite = document.getElementById("gadget-sw-composite");
const gadgetTeardownBtn = document.getElementById("gadget-teardown-btn");
const gadgetSdFile = document.getElementById("gadget-sd-file");
const gadgetSdPreviewBtn = document.getElementById("gadget-sd-preview-btn");
const gadgetSdImportBtn = document.getElementById("gadget-sd-import-btn");
const gadgetSdPreviewBox = document.getElementById("gadget-sd-preview-box");
const gadgetLogBox = document.getElementById("gadget-log-box");
const gadgetLogRefreshBtn = document.getElementById("gadget-log-refresh-btn");
const gadgetBlockCount = document.getElementById("gadget-block-count");
const gadgetBlockList = document.getElementById("gadget-block-list");
const gadgetNewWfBtn = document.getElementById("gadget-new-wf-btn");
const gadgetSaveWfBtn = document.getElementById("gadget-save-wf-btn");
const gadgetDelWfBtn = document.getElementById("gadget-del-wf-btn");
const gadgetExportBtn = document.getElementById("gadget-export-btn");
const gadgetAddBlockBtn = document.getElementById("gadget-add-block-btn");
const gadgetWfName = document.getElementById("gadget-wf-name");
const gadgetWfTrigger = document.getElementById("gadget-wf-trigger");
const gadgetBlockEditor = document.getElementById("gadget-block-editor");
const gbeCategory = document.getElementById("gbe-category");
const gbeType = document.getElementById("gbe-type");
const gbeParams = document.getElementById("gbe-params");
const gbeSave = document.getElementById("gbe-save");
const gbeCancel = document.getElementById("gbe-cancel");
const gbeError = document.getElementById("gbe-error");
const gadgetExportDialog = document.getElementById("gadget-export-dialog");
const gadgetExportFilename = document.getElementById("gadget-export-filename");
const gadgetExportConfirm = document.getElementById("gadget-export-confirm");
const gadgetExportCancel = document.getElementById("gadget-export-cancel");
const gadgetExportError = document.getElementById("gadget-export-error");

let gadgetSchema = {};
let gadgetWorkflows = [];
let gadgetBlocks = [];
let gadgetRefreshTimer = null;
let gadgetActiveWfId = null;

function openGadgetView() {
  dashboardView.classList.add("hidden");
  gadgetView.classList.remove("hidden");
  if (gadgetRefreshTimer) clearInterval(gadgetRefreshTimer);
  refreshGadgetView();
  gadgetRefreshTimer = setInterval(refreshGadgetView, 3000);
}

function closeGadgetView() {
  gadgetView.classList.add("hidden");
  dashboardView.classList.remove("hidden");
  if (gadgetRefreshTimer) { clearInterval(gadgetRefreshTimer); gadgetRefreshTimer = null; }
}

gadgetBack.addEventListener("click", closeGadgetView);

async function refreshGadgetView() {
  try {
    const state = await api("/api/gadget/state");
    applyGadgetState(state);
  } catch (_) {}
}

function applyGadgetState(state) {
  gadgetSchema = state.schema || {};
  gadgetWorkflows = state.workflows || [];
  const running = Boolean(state.running);
  gadgetDot.classList.toggle("active", running);
  gadgetStatusLabel.textContent = running ? "RUNNING" : "INACTIVE";
  gadgetProfileLabel.textContent = state.gadget_profile ? state.gadget_profile.toUpperCase() : "NONE";

  // Populate trigger dropdown once
  if (gadgetWfTrigger.options.length === 0 && gadgetSchema.trigger_types) {
    Object.entries(gadgetSchema.trigger_types).forEach(([id, label]) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = label.toUpperCase();
      gadgetWfTrigger.appendChild(opt);
    });
  }

  // Rebuild workflow selector
  const prevId = gadgetWfSelect.value;
  gadgetWfSelect.replaceChildren();
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "(new workflow)";
  gadgetWfSelect.appendChild(none);
  gadgetWorkflows.forEach((wf) => {
    const opt = document.createElement("option");
    opt.value = wf.id;
    opt.textContent = `${wf.name || wf.id} [${wf.block_count || 0}]`;
    gadgetWfSelect.appendChild(opt);
  });
  if (prevId) gadgetWfSelect.value = prevId;

  // Update active workflow ID from server
  if (state.active_workflow_id) {
    gadgetActiveWfId = state.active_workflow_id;
    gadgetWfSelect.value = gadgetActiveWfId;
  }

  // If a workflow is selected and we have blocks, update block count
  gadgetBlockCount.textContent = gadgetBlocks.length;
  refreshGadgetSdList();
  refreshGadgetLog();
}

// ------------------------------------------------------------------
// Workflow selector
// ------------------------------------------------------------------

gadgetWfSelect.addEventListener("change", async () => {
  const wid = gadgetWfSelect.value;
  if (!wid) {
    gadgetWfName.value = "";
    gadgetBlocks = [];
    renderGadgetBlockList([]);
    return;
  }
  const resp = await apiPost("/api/gadget/workflow/get", { workflow_id: wid });
  if (resp.workflow) {
    gadgetActiveWfId = wid;
    gadgetWfName.value = resp.workflow.name || "";
    if (resp.workflow.trigger?.type) gadgetWfTrigger.value = resp.workflow.trigger.type;
    gadgetBlocks = resp.workflow.blocks || [];
    renderGadgetBlockList(gadgetBlocks);
  }
});

// ------------------------------------------------------------------
// Block summary helper
// ------------------------------------------------------------------

function gadgetBlockSummary(block) {
  const t = block.type || "";
  const p = block.params || {};
  const schema = gadgetSchema.block_types?.[t];
  if (t === "hid_type_text") return `TYPE: "${(p.text || "").substring(0, 24)}"`;
  if (t === "hid_press_key") return `KEY: ${p.key || ""}`;
  if (t === "hid_key_combo") return `COMBO: ${p.modifiers || ""}+${p.key || ""}`;
  if (t === "delay") return `DELAY ${p.ms || 0}ms`;
  if (t === "if_os") return `IF OS = ${(p.os || "").toUpperCase()}`;
  if (t === "else_block") return "ELSE";
  if (t === "end_if") return "END IF";
  if (t === "loop_n") return `LOOP ×${p.count || 1}`;
  if (t === "end_loop") return "END LOOP";
  if (t === "stop_workflow") return "STOP";
  if (t === "gadget_switch_hid") return "→ HID PROFILE";
  if (t === "gadget_switch_serial") return "→ SERIAL PROFILE";
  if (t === "gadget_switch_ethernet") return `→ ETHERNET (${p.mode || "rndis"})`;
  if (t === "gadget_switch_composite") return `→ COMPOSITE (${p.functions || ""})`;
  if (t === "net_provide_dhcp") return `DHCP on ${p.interface || "usb0"}`;
  if (t === "serial_send_string") return `SERIAL: "${(p.text || "").substring(0, 24)}"`;
  return schema ? schema.label.toUpperCase() : t.toUpperCase();
}

function renderGadgetBlockList(blocks) {
  gadgetBlockCount.textContent = blocks.length;
  gadgetBlockList.replaceChildren();
  blocks.forEach((block, idx) => {
    const row = document.createElement("div");
    row.className = "rule-block" + (block.enabled !== false ? "" : " disabled");
    row.dataset.id = block.id || idx;
    row.innerHTML = `
      <div class="rule-summary">
        <span class="rule-name-label">${escHtml(gadgetBlockSummary(block))}</span>
      </div>
      <div class="rule-actions">
        <button class="rule-toggle-${block.enabled !== false ? "on" : "off"}" data-action="toggle" data-idx="${idx}">${block.enabled !== false ? "ON" : "OFF"}</button>
        <button data-action="up" data-idx="${idx}" ${idx === 0 ? "disabled" : ""}>▲</button>
        <button data-action="down" data-idx="${idx}" ${idx === blocks.length - 1 ? "disabled" : ""}>▼</button>
        <button class="danger" data-action="remove" data-idx="${idx}">✕</button>
      </div>
    `;
    gadgetBlockList.appendChild(row);
  });

  gadgetBlockList.onclick = (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const action = btn.dataset.action;
    const idx = parseInt(btn.dataset.idx, 10);
    handleGadgetBlockAction(action, idx);
  };
}

function handleGadgetBlockAction(action, idx) {
  if (idx < 0 || idx >= gadgetBlocks.length) return;
  if (action === "toggle") {
    gadgetBlocks[idx].enabled = !gadgetBlocks[idx].enabled;
  } else if (action === "remove") {
    gadgetBlocks.splice(idx, 1);
  } else if (action === "up" && idx > 0) {
    [gadgetBlocks[idx - 1], gadgetBlocks[idx]] = [gadgetBlocks[idx], gadgetBlocks[idx - 1]];
  } else if (action === "down" && idx < gadgetBlocks.length - 1) {
    [gadgetBlocks[idx], gadgetBlocks[idx + 1]] = [gadgetBlocks[idx + 1], gadgetBlocks[idx]];
  }
  renderGadgetBlockList(gadgetBlocks);
}

// ------------------------------------------------------------------
// Block editor for Gadget Automation
// ------------------------------------------------------------------

function gbePopulateCategories() {
  if (gbeCategory.options.length > 0) return;
  const cats = gadgetSchema.block_categories || {};
  Object.entries(cats).forEach(([id, cat]) => {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = (cat.label || id).toUpperCase();
    gbeCategory.appendChild(opt);
  });
  gbeUpdateTypes();
}

function gbeUpdateTypes() {
  gbeType.replaceChildren();
  const cats = gadgetSchema.block_categories || {};
  const types = cats[gbeCategory.value]?.types || [];
  types.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    const schema = gadgetSchema.block_types?.[t];
    opt.textContent = schema ? schema.label.toUpperCase() : t.toUpperCase();
    gbeType.appendChild(opt);
  });
  gbeUpdateParams();
}

function gbeUpdateParams() {
  gbeParams.replaceChildren();
  const schema = gadgetSchema.block_types?.[gbeType.value];
  if (!schema) return;
  (schema.params || []).forEach((pdef) => {
    const row = document.createElement("div");
    row.className = "editor-row";
    const lbl = document.createElement("span");
    lbl.className = "rule-kw";
    lbl.textContent = pdef.label;
    row.appendChild(lbl);

    if (pdef.type === "textarea") {
      const ta = document.createElement("textarea");
      ta.dataset.key = pdef.key;
      ta.className = "ed-input";
      ta.rows = 3;
      ta.style.resize = "vertical";
      if (pdef.default !== undefined) ta.value = pdef.default;
      row.appendChild(ta);
    } else if (pdef.type === "checkbox") {
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.key = pdef.key;
      cb.dataset.dtype = "bool";
      if (pdef.default) cb.checked = true;
      row.appendChild(cb);
    } else if (pdef.type === "select") {
      const sel = document.createElement("select");
      sel.dataset.key = pdef.key;
      sel.className = "ed-select";
      (pdef.options || []).forEach((optVal) => {
        const opt = document.createElement("option");
        opt.value = optVal;
        opt.textContent = optVal.toUpperCase();
        sel.appendChild(opt);
      });
      if (pdef.default !== undefined) sel.value = pdef.default;
      row.appendChild(sel);
    } else {
      const inp = document.createElement("input");
      inp.type = pdef.type === "number" ? "number" : "text";
      inp.dataset.key = pdef.key;
      inp.className = "ed-input";
      if (pdef.default !== undefined) inp.value = pdef.default;
      row.appendChild(inp);
    }
    gbeParams.appendChild(row);
  });
}

gbeCategory.addEventListener("change", gbeUpdateTypes);
gbeType.addEventListener("change", gbeUpdateParams);

function openGadgetBlockEditor() {
  gbePopulateCategories();
  gbeError.classList.add("hidden");
  gadgetBlockEditor.classList.remove("hidden");
}

function closeGadgetBlockEditor() {
  gadgetBlockEditor.classList.add("hidden");
}

gadgetAddBlockBtn.addEventListener("click", openGadgetBlockEditor);
gbeCancel.addEventListener("click", closeGadgetBlockEditor);

gbeSave.addEventListener("click", () => {
  gbeError.classList.add("hidden");
  const type = gbeType.value;
  if (!type) { gbeError.textContent = "SELECT A BLOCK TYPE"; gbeError.classList.remove("hidden"); return; }
  const params = {};
  const schema = gadgetSchema.block_types?.[type];
  gbeParams.querySelectorAll("[data-key]").forEach((el) => {
    const k = el.dataset.key;
    if (el.dataset.dtype === "bool") {
      params[k] = el.checked;
    } else if (el.type === "number") {
      params[k] = parseFloat(el.value) || 0;
    } else {
      params[k] = el.value;
    }
  });
  // Check required fields
  if (schema) {
    for (const pdef of schema.params || []) {
      if (pdef.required && !params[pdef.key]) {
        gbeError.textContent = `${pdef.label} IS REQUIRED`;
        gbeError.classList.remove("hidden");
        return;
      }
    }
  }
  gadgetBlocks.push({ type, enabled: true, params });
  renderGadgetBlockList(gadgetBlocks);
  closeGadgetBlockEditor();
});

// ------------------------------------------------------------------
// Workflow save / new / delete
// ------------------------------------------------------------------

gadgetNewWfBtn.addEventListener("click", () => {
  gadgetActiveWfId = null;
  gadgetWfSelect.value = "";
  gadgetWfName.value = "";
  gadgetBlocks = [];
  renderGadgetBlockList([]);
});

gadgetSaveWfBtn.addEventListener("click", async () => {
  const name = gadgetWfName.value.trim() || "Unnamed Workflow";
  const trigger = { type: gadgetWfTrigger.value || "manual", params: {} };
  const workflow = {
    id: gadgetActiveWfId || undefined,
    name,
    trigger,
    blocks: gadgetBlocks,
  };
  const resp = await apiPost("/api/gadget/workflow/save", { workflow });
  if (resp.status === "ok") {
    gadgetActiveWfId = resp.workflow?.id || gadgetActiveWfId;
    setOverlay("SAVED", resp.workflow);
    refreshGadgetView();
  } else {
    setOverlay("ERROR", resp);
  }
});

gadgetDelWfBtn.addEventListener("click", async () => {
  if (!gadgetActiveWfId) return;
  const resp = await apiPost("/api/gadget/workflow/delete", { workflow_id: gadgetActiveWfId });
  if (resp.status === "ok") {
    gadgetActiveWfId = null;
    gadgetBlocks = [];
    renderGadgetBlockList([]);
    refreshGadgetView();
  }
});

// ------------------------------------------------------------------
// Run / Stop workflow
// ------------------------------------------------------------------

gadgetRunBtn.addEventListener("click", async () => {
  if (!gadgetActiveWfId && gadgetBlocks.length === 0) return;
  const params = {
    detected_os: gadgetOsHint.value || "",
  };
  if (gadgetActiveWfId) {
    params.workflow_id = gadgetActiveWfId;
  } else {
    // Run inline from current block list
    params.workflow = {
      name: gadgetWfName.value.trim() || "Inline",
      trigger: { type: gadgetWfTrigger.value || "manual", params: {} },
      blocks: gadgetBlocks,
    };
  }
  const resp = await apiPost("/api/gadget/workflow/run", params);
  setOverlay("RUN WORKFLOW", resp);
  refreshGadgetView();
});

gadgetStopBtn.addEventListener("click", async () => {
  const resp = await apiPost("/api/gadget/workflow/stop", {});
  setOverlay("STOP", resp);
  refreshGadgetView();
});

// ------------------------------------------------------------------
// Gadget profile quick-switch
// ------------------------------------------------------------------

gadgetSwHid.addEventListener("click", async () => {
  await apiPost("/api/gadget/workflow/run", {
    workflow: {
      name: "quick-hid",
      trigger: { type: "manual", params: {} },
      blocks: [{ type: "gadget_switch_hid", enabled: true, params: { mouse: true } }],
    },
  });
  refreshGadgetView();
});

gadgetSwSerial.addEventListener("click", async () => {
  await apiPost("/api/gadget/workflow/run", {
    workflow: {
      name: "quick-serial",
      trigger: { type: "manual", params: {} },
      blocks: [{ type: "gadget_switch_serial", enabled: true, params: {} }],
    },
  });
  refreshGadgetView();
});

gadgetSwEth.addEventListener("click", async () => {
  await apiPost("/api/gadget/workflow/run", {
    workflow: {
      name: "quick-ethernet",
      trigger: { type: "manual", params: {} },
      blocks: [{ type: "gadget_switch_ethernet", enabled: true, params: { mode: "rndis" } }],
    },
  });
  refreshGadgetView();
});

gadgetSwComposite.addEventListener("click", async () => {
  await apiPost("/api/gadget/workflow/run", {
    workflow: {
      name: "quick-composite",
      trigger: { type: "manual", params: {} },
      blocks: [{ type: "gadget_switch_composite", enabled: true, params: { functions: "hid,serial" } }],
    },
  });
  refreshGadgetView();
});

gadgetTeardownBtn.addEventListener("click", async () => {
  const resp = await apiPost("/api/gadget/teardown", {});
  setOverlay("TEARDOWN", resp);
  refreshGadgetView();
});

// ------------------------------------------------------------------
// SD card workflow browser
// ------------------------------------------------------------------

async function refreshGadgetSdList() {
  try {
    const resp = await api("/api/gadget/sd/list");
    const files = resp.files || [];
    gadgetSdFile.replaceChildren();
    if (!files.length) {
      const opt = document.createElement("option");
      opt.textContent = "(no workflow files)";
      opt.disabled = true;
      gadgetSdFile.appendChild(opt);
      return;
    }
    files.forEach((f) => {
      const opt = document.createElement("option");
      opt.value = f.name;
      opt.textContent = `${f.name} (${f.size}B)`;
      gadgetSdFile.appendChild(opt);
    });
  } catch (_) {}
}

gadgetSdPreviewBtn.addEventListener("click", async () => {
  const filename = gadgetSdFile.value;
  if (!filename) return;
  const resp = await apiPost("/api/gadget/sd/preview", { filename });
  if (resp.status === "ok") {
    gadgetSdPreviewBox.textContent =
      `[${resp.block_count || 0} blocks]\n` +
      resp.preview +
      (resp.truncated ? "\n[TRUNCATED]" : "");
    gadgetSdPreviewBox.classList.remove("hidden");
  } else {
    gadgetSdPreviewBox.textContent = resp.error || "PREVIEW FAILED";
    gadgetSdPreviewBox.classList.remove("hidden");
  }
});

gadgetSdImportBtn.addEventListener("click", async () => {
  const filename = gadgetSdFile.value;
  if (!filename) return;
  const resp = await apiPost("/api/gadget/sd/import", { filename });
  if (resp.status === "ok") {
    const wf = resp.workflow;
    gadgetActiveWfId = wf.id;
    gadgetWfName.value = wf.name || "";
    gadgetBlocks = wf.blocks || [];
    renderGadgetBlockList(gadgetBlocks);
    refreshGadgetView();
  } else {
    setOverlay("IMPORT ERROR", resp);
  }
});

// ------------------------------------------------------------------
// Export workflow to SD
// ------------------------------------------------------------------

gadgetExportBtn.addEventListener("click", () => {
  gadgetExportFilename.value = (gadgetWfName.value.trim() || "workflow").replace(/\s+/g, "_") + ".workflow";
  gadgetExportError.classList.add("hidden");
  gadgetExportDialog.classList.remove("hidden");
});

gadgetExportCancel.addEventListener("click", () => gadgetExportDialog.classList.add("hidden"));

gadgetExportConfirm.addEventListener("click", async () => {
  const filename = gadgetExportFilename.value.trim();
  if (!filename) {
    gadgetExportError.textContent = "FILENAME REQUIRED";
    gadgetExportError.classList.remove("hidden");
    return;
  }
  if (!gadgetActiveWfId) {
    gadgetExportError.textContent = "SAVE WORKFLOW FIRST";
    gadgetExportError.classList.remove("hidden");
    return;
  }
  const resp = await apiPost("/api/gadget/sd/export", {
    workflow_id: gadgetActiveWfId,
    filename,
  });
  gadgetExportDialog.classList.add("hidden");
  setOverlay("EXPORT", resp);
});

// ------------------------------------------------------------------
// Execution log
// ------------------------------------------------------------------

async function refreshGadgetLog() {
  try {
    const resp = await api("/api/gadget/logs");
    const lines = resp.log || [];
    gadgetLogBox.textContent = lines.length ? lines.join("\n") : "(no log)";
  } catch (_) {}
}

gadgetLogRefreshBtn.addEventListener("click", refreshGadgetLog);

