// =============================================================================
// Onikiri Mk.I — HMI application
// =============================================================================

const moduleDefaults = {
  RECON: { module: "network_scanner", module_action: "inventory", params: {} },
  WIRELESS: { module: "wifi_recon", module_action: "survey", params: {} },
  ENGAGEMENT: { module: "engagement", module_action: "active_profile", params: {} },
  SYSTEM: { module: "system_info", module_action: "snapshot", params: {} }
};

const panelOrder = ["RECON", "MITM", "HID", "WIRELESS", "ENGAGEMENT", "SYSTEM"];
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

function renderPanels(modules, jobs) {
  clearPanels();
  const activeModules = new Map(modules.map((item) => [item.label, item]));
  panelOrder.forEach((label) => {
    const node = panelTemplate.content.firstElementChild.cloneNode(true);
    const module = activeModules.get(label) || { label, status: "inactive", name: label.toLowerCase() };
    node.querySelector(".panel-label").textContent = label;
    const statusStrip = node.querySelector(".status-strip");
    statusStrip.textContent = (module.status || "inactive").toUpperCase();
    if (module.status === "active") node.classList.add("active");
    if (module.status === "error") node.classList.add("error");

    let longPressTimer = null;
    let didLongPress = false;
    const startLongPress = () => {
      didLongPress = false;
      longPressTimer = setTimeout(() => {
        didLongPress = true;
        setOverlay(label, module);
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

      // Feature panels open dedicated views
      if (label === "MITM") { openMitmView(); return; }
      if (label === "HID") { openHidView(); return; }

      node.classList.remove("flash");
      void node.offsetWidth;
      node.classList.add("flash");
      const panelConfig = moduleDefaults[label];
      if (!panelConfig) return;
      const payload = await apiPost("/api/run", panelConfig);
      setOverlay(label, payload);
      refreshDashboard();
    });
    node.addEventListener("pointerleave", clearLongPress);
    node.addEventListener("pointercancel", clearLongPress);
    panelGrid.appendChild(node);
  });
}

async function refreshDashboard() {
  const state = await api("/api/state");
  renderPanels(state.modules || [], state.jobs || []);
}

wipeButton.addEventListener("click", async () => {
  const result = await apiPost("/api/wipe", {});
  setOverlay("WIPE", result);
  refreshDashboard();
});

refreshDashboard();
setInterval(refreshDashboard, 3000);

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

  // Populate device profile dropdown (once)
  if (hidDeviceSel.options.length === 0 && Object.keys(hidDevices).length) {
    Object.entries(hidDevices).forEach(([id, dev]) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = dev.product || id;
      hidDeviceSel.appendChild(opt);
    });
  }
  if (state.device_profile) hidDeviceSel.value = state.device_profile;
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
  await apiPost("/api/hid/device/set", { profile_id: hidDeviceSel.value });
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

