const moduleDefaults = {
  RECON: { module: "network_scanner", module_action: "inventory", params: {} },
  MITM: { module: "mitm", module_action: "plan", params: { targets: [] } },
  PAYLOADS: { module: "payload_builder", module_action: "template", params: {} },
  WIRELESS: { module: "wifi_recon", module_action: "survey", params: {} },
  ENGAGEMENT: { module: "engagement", module_action: "active_profile", params: {} },
  SYSTEM: { module: "system_info", module_action: "snapshot", params: {} }
};

const panelOrder = ["RECON", "MITM", "PAYLOADS", "WIRELESS", "ENGAGEMENT", "SYSTEM"];
const panelGrid = document.getElementById("panel-grid");
const panelTemplate = document.getElementById("panel-template");
const overlay = document.getElementById("overlay");
const overlayTitle = document.getElementById("overlay-title");
const overlayContent = document.getElementById("overlay-content");
const overlayClose = document.getElementById("overlay-close");
const wipeButton = document.getElementById("wipe-button");
const longPressMs = 450;

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
  if (event.target === overlay) {
    closeOverlay();
  }
});

async function api(path, options = {}) {
  const response = await fetch(path, options);
  return response.json();
}

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
    if (module.status === "active") {
      node.classList.add("active");
    }
    if (module.status === "error") {
      node.classList.add("error");
    }
    const panelConfig = moduleDefaults[label];
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
      if (longPressTimer) {
        clearTimeout(longPressTimer);
      }
      longPressTimer = null;
    };
    node.addEventListener("pointerdown", startLongPress);
    node.addEventListener("pointerup", async () => {
      const wasLong = didLongPress;
      clearLongPress();
      if (wasLong) {
        return;
      }
      node.classList.remove("flash");
      void node.offsetWidth;
      node.classList.add("flash");
      const payload = await api("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(panelConfig)
      });
      setOverlay(label, payload);
      refresh();
    });
    node.addEventListener("pointerleave", clearLongPress);
    node.addEventListener("pointercancel", clearLongPress);
    panelGrid.appendChild(node);
  });
}

async function refresh() {
  const state = await api("/api/state");
  renderPanels(state.modules || [], state.jobs || []);
}

wipeButton.addEventListener("click", async () => {
  const result = await api("/api/wipe", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  setOverlay("WIPE", result);
  refresh();
});

refresh();
setInterval(refresh, 3000);
