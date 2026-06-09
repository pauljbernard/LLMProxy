const persistedTableState = (() => {
  try {
    return JSON.parse(localStorage.getItem("llmproxy.admin.tableState") || "{}");
  } catch (_error) {
    return {};
  }
})();

const state = {
  activeDataCollection: "candidates",
  activeGovernanceCollection: "keys",
  activeIntegrationsCollection: "mcp",
  activeModelCatalogCollection: "proxy",
  activeModelRegisterCollection: "vendor",
  activeModelRoutingCollection: "entries",
  activeModelsSubview: "catalog",
  activeOperationsSubview: "monitor",
  activeOverviewSubview: "config",
  activeProxySubview: "playground",
  activeTrainingSubview: "workbench",
  routingPolicyQuery: "",
  routingPolicyScopedOnly: false,
  token: localStorage.getItem("llmproxy.admin.token") || "",
  activePanel: "overview",
  activeOpsCollection: "events",
  opsPollTimer: null,
  activeRuntimeCollection: "jobs",
  activeTrainingCollection: "runs",
  trainingPollTimer: null,
  tablePages: persistedTableState.tablePages || {},
  tablePageSizes: persistedTableState.tablePageSizes || {},
  tableContexts: persistedTableState.tableContexts || {},
  foundationModelVisibilityScope: persistedTableState.foundationModelVisibilityScope || "active",
  opsEventColumnPreset: persistedTableState.opsEventColumnPreset || "adaptive",
  savedOpsPresets: persistedTableState.savedOpsPresets || {},
  loadedPanels: new Set(),
  lastRoutePreview: null,
  dataCandidates: [],
  dataExports: [],
  dataImports: [],
  dataVersions: [],
  governanceKeys: [],
  guardrailsSettings: null,
  mcpServers: [],
  a2aPeers: [],
  restEndpoints: [],
  pricingRows: [],
  promptTemplates: [],
  promptTemplateInventory: [],
  providerGuides: [],
  modelCatalogRows: [],
  localRuntimeRows: [],
  localModelRows: [],
  proxyModelOptions: [],
  localDeploymentRows: [],
  localDeploymentRowsLoaded: false,
  deploymentInventoryQuery: "",
  deploymentInventoryStage: "all",
  streamingSupportQuery: "",
  streamingSupportConfiguredOnly: true,
  streamingSupportStreamableOnly: true,
  expandedFoundationProviderKeys: new Set(),
  trainingEvaluations: [],
  trainingRuns: [],
  trainingLifecycleData: null,
  trainingRuntimeStatus: null,
  trainingStudioStatus: null,
  runtimeJobs: [],
  runtimeEvents: [],
  healthPayload: null,
  llmTimeseriesPayload: null,
  modelMonitorPayload: null,
  configPayload: null,
  operationsTopologyData: null,
  selectedJobId: null,
  selectedEventId: null,
  selectedOpsRecordKey: null,
  selectedOpsRecord: null,
  selectedOperationsTopologyKey: null,
  selectedOperationsTopologyEdgeKey: null,
  selectedGovernanceKeyId: null,
  selectedGovernanceGraphKey: null,
  selectedGovernanceGraphEdgeKey: null,
  selectedPricingKey: null,
  selectedExportId: null,
  selectedDatasetRecordId: null,
  selectedTrainingLifecycleStage: null,
  selectedTrainingRunId: null,
  selectedEvaluationId: null,
  selectedProviderGuideKey: null,
  selectedStreamingSupportKey: null,
  selectedMcpServerName: null,
  selectedA2APeerName: null,
  selectedRestEndpointName: null,
  selectedIntegrationsGraphKey: null,
  selectedIntegrationsGraphEdgeKey: null,
  selectedPromptTemplateKey: null,
  selectedPromptTemplateRecord: null,
  selectedPromptComparison: null,
  foundationProviderGroups: [],
  selectedFoundationProviderKey: null,
  selectedFoundationModelKey: null,
  selectedLocalModelAlias: null,
  policyRows: [],
  routingTopologyInventory: null,
  selectedInboundListenerId: null,
  selectedModelMonitorId: null,
  selectedPolicyRowKey: null,
  selectedRoutingNodeKey: null,
  selectedRoutingPoolKey: null,
  selectedRoutingGraphKey: null,
  selectedRoutingGraphEdgeKey: null,
  selectedDeploymentGraphKey: null,
  selectedDeploymentGraphEdgeKey: null,
  selectedLocalRuntime: null,
  selectedLocalDeploymentAlias: null,
  activeModelPickerTarget: "chat",
  modelPickerQuery: "",
  selectedModelPickerOption: null,
  graphViewBoxes: {},
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const knownPanels = new Set(["overview", "proxy", "governance", "models", "integrations", "prompts", "data", "training", "operations", "runtime"]);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function humanizeLabel(text) {
  return String(text || "")
    .replace(/^llmproxy_/i, "")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function logConsole(label, payload) {
  const output = $("#console-output");
  const rendered = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
  const stamp = new Date().toISOString();
  output.textContent = `[${stamp}] ${label}\n${rendered}\n\n${output.textContent}`;
}

const TOAST_GLYPHS = { ok: "✓", err: "✕", warn: "!", info: "i" };

function showToast(message, tone = "info") {
  const region = $("#toast-region");
  if (!region) return;
  const toast = document.createElement("div");
  toast.className = `toast ${tone}`;
  toast.setAttribute("role", tone === "err" ? "alert" : "status");
  toast.innerHTML = `
    <span class="toast-icon" aria-hidden="true">${TOAST_GLYPHS[tone] || TOAST_GLYPHS.info}</span>
    <span class="toast-message"></span>
    <span class="toast-dismiss-hint" aria-hidden="true">dismiss</span>
  `;
  toast.querySelector(".toast-message").textContent = message;
  region.appendChild(toast);

  let dismissed = false;
  const dismiss = () => {
    if (dismissed) return;
    dismissed = true;
    window.clearTimeout(timer);
    toast.classList.add("leaving");
    toast.addEventListener("animationend", () => toast.remove(), { once: true });
    // Fallback in case the animation event doesn't fire (e.g. reduced-motion).
    window.setTimeout(() => toast.remove(), 400);
  };
  toast.addEventListener("click", dismiss);
  const timer = window.setTimeout(dismiss, 4200);
}

function setStatus(text, tone = "info") {
  const pill = $("#status-pill");
  pill.textContent = text;
  pill.className = `status-pill ${tone}`;
}

async function withLoading(button, fn, loadingText = "Loading…") {
  if (!button) {
    return fn();
  }
  const original = button.textContent;
  button.disabled = true;
  button.textContent = loadingText;
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (state.token) {
    headers.set("Authorization", `Bearer ${state.token}`);
  }

  const response = await fetch(url, { ...options, headers });
  const raw = await response.text();
  const payload = raw ? (() => {
    try {
      return JSON.parse(raw);
    } catch {
      return raw;
    }
  })() : null;
  if (!response.ok) {
    throw new Error(typeof payload === "string" ? payload : JSON.stringify(payload, null, 2));
  }
  return payload;
}

async function apiStream(url, body) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (state.token) {
    headers.set("Authorization", `Bearer ${state.token}`);
  }
  const response = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  if (!response.body) {
    throw new Error("Streaming response body unavailable.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const events = [];
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const segments = buffer.split("\n\n");
    buffer = segments.pop() || "";
    for (const segment of segments) {
      const dataLine = segment.split("\n").find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      const raw = dataLine.slice(6).trim();
      if (raw === "[DONE]") {
        events.push({ done: true });
        continue;
      }
      try {
        events.push(JSON.parse(raw));
      } catch {
        events.push({ raw });
      }
    }
  }
  const streamError = events.find((event) => event && typeof event === "object" && event.error);
  if (streamError && typeof streamError.error === "object") {
    throw new Error(String(streamError.error.message || "Streaming request failed."));
  }
  return events;
}

function renderOutput(selector, payload) {
  const node = $(selector);
  if (!node) return;
  node.textContent = payload == null ? "" : JSON.stringify(payload, null, 2);
}

function setText(selector, text) {
  const node = $(selector);
  if (node) {
    node.textContent = text;
  }
}

function setActiveRuntimeRow(tableSelector, recordId) {
  $$(`${tableSelector} tbody tr`).forEach((row) => {
    row.classList.toggle("active-row", row.dataset.recordId === recordId);
  });
}

function buildOpsRecordKey(row) {
  if (row?.event_source && row?.source_record_id) {
    return `${row.event_source}:${row.source_record_id}`;
  }
  return [row?.timestamp, row?.event_class, row?.level, row?.component, row?.message].map((value) => String(value ?? "")).join("|");
}

function buildPricingKey(row) {
  return `${row?.provider || ""}|${row?.model || ""}`;
}

function buildPromptTemplateKey(row) {
  return `${row?.name || ""}|${row?.version || ""}`;
}

function buildFoundationProviderKey(row) {
  return String(row?.provider_key || row?.provider_name || "");
}

function buildFoundationModelKey(providerKey, modelId) {
  return `${providerKey || ""}|${modelId || ""}`;
}

function foundationProviderExpanded(providerKey) {
  return state.expandedFoundationProviderKeys?.has(providerKey);
}

function toggleFoundationProviderExpanded(providerKey, expanded = !foundationProviderExpanded(providerKey)) {
  if (!providerKey) return;
  if (expanded) {
    state.expandedFoundationProviderKeys.add(providerKey);
  } else {
    state.expandedFoundationProviderKeys.delete(providerKey);
  }
}

function buildStreamingSupportKey(row) {
  return `${row?.provider_key || row?.provider_name || ""}|${row?.model_id || ""}`;
}

function buildPolicyRowKey(row) {
  return `${row?.policy_version || ""}|${row?.entry_id || ""}|${row?.provider || ""}|${row?.model || ""}|${row?.mode || ""}`;
}

function buildRoutingNodeKey(row) {
  return String(row?.node_id || "");
}

function buildRoutingPoolKey(row) {
  return String(row?.pool_id || "");
}

function currentSelectedFoundationProvider() {
  return (state.foundationProviderGroups || []).find((group) => buildFoundationProviderKey(group) === state.selectedFoundationProviderKey) || null;
}

function currentSelectedFoundationModel() {
  const provider = currentSelectedFoundationProvider();
  if (!provider) return null;
  return (provider.models || []).find((model) => buildFoundationModelKey(provider.provider_key, model.model_id) === state.selectedFoundationModelKey) || null;
}

function currentFoundationModelVisibilityScope() {
  return ["active", "all", "historical"].includes(state.foundationModelVisibilityScope)
    ? state.foundationModelVisibilityScope
    : "active";
}

function setFoundationModelVisibilityScope(scope) {
  state.foundationModelVisibilityScope = ["active", "all", "historical"].includes(scope) ? scope : "active";
  const field = $("#foundation-visibility-scope");
  if (field) {
    field.value = state.foundationModelVisibilityScope;
  }
  persistTableState();
}

const modelPickerTargetConfigs = {
  chat: {
    title: "Choose Chat Model",
    description: "Select a proxy model, a vendor LLM, or a custom LLM to populate the chat model field.",
    inputSelector: "#chat-model",
    emptySelectionMessage: "Choose a model from the picker to populate the chat model field.",
    successMessage: "Selected model",
    includeProxy: () => true,
    includeVendor: () => true,
    includeCustom: () => true,
  },
  embeddings: {
    title: "Choose Embedding Model",
    description: "Select an embedding-capable proxy model or vendor model to populate the embeddings model field.",
    inputSelector: "#emb-model",
    emptySelectionMessage: "Choose an embedding-capable model to populate the embeddings model field.",
    successMessage: "Selected embedding model",
    includeProxy: (option) => Boolean(option.supports_embeddings),
    includeVendor: (option) => Boolean(option.supports_embeddings),
    includeCustom: (option) => Boolean(option.supports_embeddings),
  },
};

function currentModelPickerTargetConfig(target = state.activeModelPickerTarget) {
  return modelPickerTargetConfigs[target] || modelPickerTargetConfigs.chat;
}

function currentModelValue(target = state.activeModelPickerTarget) {
  const config = currentModelPickerTargetConfig(target);
  return String($(config.inputSelector)?.value || "").trim();
}

function modelPickerQuery() {
  return String(state.modelPickerQuery || "").trim().toLowerCase();
}

function pickerOptionMatchesQuery(option, query) {
  if (!query) return true;
  const haystack = [
    option.id,
    option.description,
    option.family,
    option.provider_name,
    option.provider_family,
    option.status,
    option.kind,
  ].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(query);
}

function buildChatModelPickerData(target = state.activeModelPickerTarget, { applyQuery = true } = {}) {
  const config = currentModelPickerTargetConfig(target);
  const query = applyQuery ? modelPickerQuery() : "";
  const proxyModels = (state.proxyModelOptions || [])
    .filter((option) => config.includeProxy(option))
    .filter((option) => pickerOptionMatchesQuery(option, query));
  const vendorSource = target === "embeddings" && (state.modelCatalogRows || []).length
    ? Array.from((state.modelCatalogRows || []).reduce((map, row) => {
      if (String(row.provider_family || "").toLowerCase() === "local runtime") return map;
      const providerKey = String(row.provider_name || row.provider_family || "");
      if (!providerKey) return map;
      if (!map.has(providerKey)) {
        map.set(providerKey, {
          provider_key: providerKey,
          provider_name: row.provider_name || providerKey,
          provider_family: row.provider_family || providerKey,
          status: "catalog",
          models: [],
        });
      }
      map.get(providerKey).models.push({
        model_id: row.model_id,
        status: "catalog",
        streaming_supported: Boolean(row.supports_streaming),
        supports_embeddings: Boolean(row.supports_embeddings),
        routed: false,
        exposed: true,
      });
      return map;
    }, new Map()).values())
    : (state.foundationProviderGroups || []);
  const vendorProviders = vendorSource.map((provider) => {
    const eligibleModels = (provider.models || [])
      .map((model) => ({
        id: model.model_id,
        status: model.status,
        streaming_supported: Boolean(model.streaming_supported),
        supports_embeddings: Boolean(model.supports_embeddings),
        routed: Boolean(model.routed),
        exposed: Boolean(model.exposed),
        kind: "vendor",
        provider_key: provider.provider_key,
        provider_name: provider.provider_name,
        provider_family: provider.provider_family,
      }))
      .filter((model) => config.includeVendor(model));
    const providerMatches = pickerOptionMatchesQuery({
      id: provider.provider_key,
      provider_name: provider.provider_name,
      provider_family: provider.provider_family,
      status: provider.status,
      kind: "vendor-provider",
    }, query);
    const filteredModels = providerMatches || !query
      ? eligibleModels
      : eligibleModels.filter((model) => pickerOptionMatchesQuery(model, query));
    return {
      provider_key: provider.provider_key,
      provider_name: provider.provider_name,
      provider_family: provider.provider_family,
      status: provider.status,
      models: filteredModels,
    };
  }).filter((provider) => (provider.models || []).length);
  const customModels = (state.localModelRows || [])
    .map((row) => ({
      id: row.model_alias,
      family: row.base_model || "Custom model",
      description: (row.domains || []).join(", ") || "Onboarded internal package.",
      status: row.promotion_status || "registered",
      supports_embeddings: Boolean(row.supports_embeddings),
      kind: "custom",
    }))
    .filter((option) => config.includeCustom(option))
    .filter((option) => pickerOptionMatchesQuery(option, query));
  return { proxyModels, vendorProviders, customModels };
}

function resolveModelPickerSelection(target = state.activeModelPickerTarget, modelId = currentModelValue(target)) {
  const normalized = String(modelId || "").trim();
  if (!normalized) return null;
  const { proxyModels, vendorProviders, customModels } = buildChatModelPickerData(target, { applyQuery: false });
  const proxyMatch = proxyModels.find((item) => item.id === normalized);
  if (proxyMatch) return proxyMatch;
  for (const provider of vendorProviders) {
    const vendorMatch = (provider.models || []).find((item) => item.id === normalized);
    if (vendorMatch) return vendorMatch;
  }
  const customMatch = customModels.find((item) => item.id === normalized);
  if (customMatch) return customMatch;
  return { id: normalized, family: "Manual entry", description: "Current model value is not present in the picker inventory.", kind: "manual" };
}

function clearHost(selector) {
  const host = $(selector);
  if (host) {
    host.innerHTML = "";
  }
}

function buildEmptyState(config = {}) {
  const { icon = "□", title = "No data yet.", body = "", action = null } =
    typeof config === "string" ? { body: config } : config;
  const wrap = document.createElement("div");
  wrap.className = "empty-state";
  wrap.innerHTML = `
    <div class="empty-icon" aria-hidden="true">${escapeHtml(icon)}</div>
    <strong>${escapeHtml(title)}</strong>
    ${body ? `<p>${escapeHtml(body)}</p>` : ""}
  `;
  if (action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button tonal";
    button.textContent = action.label;
    button.addEventListener("click", action.onClick);
    wrap.appendChild(button);
  }
  return wrap;
}

function renderMetricGrid(selector, items) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  const entries = items.filter((item) => item && item.label);
  if (!entries.length) {
    host.appendChild(buildEmptyState({
      icon: "Σ",
      title: "No metrics available.",
      body: "Metrics will appear here once there is activity to summarize.",
    }));
    return;
  }
  entries.forEach((item) => {
    const card = document.createElement("div");
    card.className = "metric-card";
    card.innerHTML = `
      <div class="metric-label">${escapeHtml(item.label)}</div>
      <div class="metric-value">${item.badge ? item.badge : escapeHtml(item.value ?? "-")}</div>
      ${item.subvalue ? `<div class="metric-subvalue">${escapeHtml(item.subvalue)}</div>` : ""}
    `;
    host.appendChild(card);
  });
}

function renderSummaryChips(selector, items) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  const entries = items.filter((item) => item && item.label);
  if (!entries.length) {
    host.appendChild(buildEmptyState({
      icon: "Σ",
      title: "No summary available.",
      body: "Runtime totals will appear here once jobs or events are loaded.",
    }));
    return;
  }
  entries.forEach((item) => {
    const chip = document.createElement("div");
    chip.className = "summary-chip";
    chip.innerHTML = `<span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value ?? "-")}</strong>`;
    host.appendChild(chip);
  });
}

function closeChatModelPicker() {
  const modal = $("#chat-model-picker-modal");
  if (!modal) return;
  modal.classList.remove("active");
  modal.setAttribute("aria-hidden", "true");
  state.modelPickerQuery = "";
  if ($("#model-picker-search")) {
    $("#model-picker-search").value = "";
  }
}

function renderChatModelPickerSummary() {
  const host = $("#chat-model-picker-summary");
  if (!host) return;
  const selected = state.selectedModelPickerOption;
  const config = currentModelPickerTargetConfig();
  if (!selected) {
    host.innerHTML = `
      <strong>No model selected yet.</strong>
      <p class="card-subtitle">${escapeHtml(config.emptySelectionMessage)}</p>
    `;
    return;
  }
  host.innerHTML = `
    <strong>${escapeHtml(selected.id)}</strong>
    <p class="card-subtitle">${escapeHtml(selected.provider_name || selected.family || selected.description || "Selected model")}</p>
  `;
}

function createChatModelOption(option, { subtitle = "", badges = [] } = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `picker-model-option${state.selectedModelPickerOption?.id === option.id ? " active" : ""}`;
  button.innerHTML = `
    <span class="picker-model-option-label">
      <strong>${escapeHtml(option.id)}</strong>
      <span>${escapeHtml(subtitle || option.description || option.family || "")}</span>
    </span>
    <span class="picker-model-option-meta">${badges.join("")}</span>
  `;
  button.addEventListener("click", () => {
    state.selectedModelPickerOption = option;
    renderChatModelPickerSummary();
    renderChatModelPicker();
  });
  return button;
}

function renderChatModelPicker() {
  const host = $("#chat-model-picker-content");
  if (!host) return;
  host.innerHTML = "";
  const config = currentModelPickerTargetConfig();
  setText("#chat-model-picker-title", config.title);
  setText("#chat-model-picker-description", config.description);
  const { proxyModels, vendorProviders, customModels } = buildChatModelPickerData();
  const grid = document.createElement("div");
  grid.className = "picker-grid";

  const proxySection = document.createElement("section");
  proxySection.className = "picker-section";
  proxySection.innerHTML = `<h3>Proxy Models</h3>`;
  if (!proxyModels.length) {
    proxySection.appendChild(buildEmptyState({
      icon: "□",
      title: "No proxy models match.",
      body: state.modelPickerQuery
        ? "Adjust the search filter or use a manual model value."
        : "No proxy models are available for this picker.",
    }));
  } else {
    const proxyList = document.createElement("div");
    proxyList.className = "picker-chip-list";
    proxyModels.forEach((option) => {
      const badges = [statusBadge(option.family)];
      if (state.activeModelPickerTarget === "embeddings") {
        badges.push(boolBadge(Boolean(option.supports_embeddings)));
      }
      proxyList.appendChild(createChatModelOption(option, {
        subtitle: option.description,
        badges,
      }));
    });
    proxySection.appendChild(proxyList);
  }
  grid.appendChild(proxySection);

  const vendorSection = document.createElement("section");
  vendorSection.className = "picker-section";
  vendorSection.innerHTML = `<h3>Vendor Providers</h3>`;
  if (!vendorProviders.length) {
    vendorSection.appendChild(buildEmptyState({
      icon: "□",
      title: state.activeModelPickerTarget === "embeddings" ? "No embedding-capable vendor models found." : "No vendor inventory loaded.",
      body: state.activeModelPickerTarget === "embeddings"
        ? (state.modelPickerQuery ? "No vendor models match the current filter." : "The current catalog does not expose any embedding-capable vendor models.")
        : "Load the vendor model directory first, then reopen the picker.",
    }));
  } else {
    vendorProviders.forEach((provider) => {
      const details = document.createElement("details");
      details.className = "picker-provider";
      details.open = provider.models.some((model) => model.id === state.selectedModelPickerOption?.id) || Boolean(state.modelPickerQuery);
      details.innerHTML = `
        <summary>
          <span>${escapeHtml(provider.provider_name || provider.provider_key)}</span>
          <span class="picker-provider-meta">
            ${statusBadge(provider.status || "-")}
            <span>${escapeHtml(String((provider.models || []).length))} models</span>
          </span>
        </summary>
      `;
      const list = document.createElement("div");
      list.className = "picker-model-list";
      (provider.models || []).forEach((model) => {
        const badges = [statusBadge(model.status || "-")];
        if (state.activeModelPickerTarget === "chat") {
          badges.push(boolBadge(Boolean(model.streaming_supported)), boolBadge(Boolean(model.routed)));
        } else {
          badges.push(boolBadge(Boolean(model.supports_embeddings)), boolBadge(Boolean(model.routed)));
        }
        list.appendChild(createChatModelOption(model, {
          subtitle: provider.provider_family || provider.provider_name,
          badges,
        }));
      });
      details.appendChild(list);
      vendorSection.appendChild(details);
    });
  }
  grid.appendChild(vendorSection);

  const customSection = document.createElement("section");
  customSection.className = "picker-section";
  customSection.innerHTML = `<h3>Custom LLMs</h3>`;
  if (!customModels.length) {
    customSection.appendChild(buildEmptyState({
      icon: "□",
      title: state.activeModelPickerTarget === "embeddings" ? "No custom embedding models loaded." : "No custom LLMs loaded.",
      body: state.modelPickerQuery
        ? "No custom models match the current filter."
        : "Onboarded internal packages will appear here once available.",
    }));
  } else {
    const customList = document.createElement("div");
    customList.className = "picker-chip-list";
    customModels.forEach((option) => {
      customList.appendChild(createChatModelOption(option, {
        subtitle: option.description,
        badges: [statusBadge(option.status || "-")],
      }));
    });
    customSection.appendChild(customList);
  }
  grid.appendChild(customSection);

  host.appendChild(grid);
}

async function openModelPicker(target = "chat") {
  await ensurePanelLoaded("models");
  if (!state.foundationProviderGroups.length || !state.modelCatalogRows.length || !state.proxyModelOptions.length) {
    await refreshModels();
  }
  if (!state.localModelRows.length) {
    await refreshLocalModels();
  }
  state.activeModelPickerTarget = target;
  state.modelPickerQuery = "";
  if ($("#model-picker-search")) {
    $("#model-picker-search").value = "";
  }
  state.selectedModelPickerOption = resolveModelPickerSelection(target);
  renderChatModelPickerSummary();
  renderChatModelPicker();
  const modal = $("#chat-model-picker-modal");
  if (modal) {
    modal.classList.add("active");
    modal.setAttribute("aria-hidden", "false");
  }
}

async function openChatModelPicker() {
  await openModelPicker("chat");
}

async function openEmbModelPicker() {
  await openModelPicker("embeddings");
}

function applyChatModelPickerSelection() {
  const selected = state.selectedModelPickerOption;
  if (!selected?.id) {
    showToast("Select a model first.", "warn");
    return;
  }
  const config = currentModelPickerTargetConfig();
  const input = $(config.inputSelector);
  if (input) {
    input.value = selected.id;
  }
  closeChatModelPicker();
  showToast(`${config.successMessage} ${selected.id}.`, "ok");
}

function setTableLoading(selector, { title = "Loading rows…", body = "Retrieving the latest data from the API." } = {}) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  const shell = buildLoadingState({ title, body });
  host.appendChild(shell);
}

function buildLoadingState({ title = "Loading rows…", body = "Retrieving the latest data from the API." } = {}) {
  const shell = document.createElement("div");
  shell.className = "table-loading";
  shell.innerHTML = `
    <div class="table-spinner" aria-hidden="true"></div>
    <div class="table-loading-copy">
      <strong>${escapeHtml(title)}</strong>
      <p>${escapeHtml(body)}</p>
    </div>
  `;
  return shell;
}

function parseViewBox(svg, fallbackWidth, fallbackHeight) {
  const raw = String(svg.getAttribute("viewBox") || "").trim();
  const parts = raw.split(/\s+/).map((value) => Number(value));
  if (parts.length === 4 && parts.every((value) => Number.isFinite(value))) {
    return { x: parts[0], y: parts[1], width: parts[2], height: parts[3] };
  }
  return { x: 0, y: 0, width: fallbackWidth, height: fallbackHeight };
}

function setSvgViewBox(svg, box) {
  svg.setAttribute("viewBox", `${box.x} ${box.y} ${box.width} ${box.height}`);
}

function clampGraphViewBox(box, baseWidth, baseHeight) {
  const minWidth = baseWidth * 0.4;
  const minHeight = baseHeight * 0.4;
  const maxWidth = baseWidth * 1.4;
  const maxHeight = baseHeight * 1.4;
  const nextWidth = Math.min(Math.max(box.width, minWidth), maxWidth);
  const nextHeight = Math.min(Math.max(box.height, minHeight), maxHeight);
  const maxX = Math.max(0, baseWidth - nextWidth);
  const maxY = Math.max(0, baseHeight - nextHeight);
  return {
    x: Math.min(Math.max(box.x, 0), maxX),
    y: Math.min(Math.max(box.y, 0), maxY),
    width: nextWidth,
    height: nextHeight,
  };
}

function mountInteractiveSvgGraph(host, svg, { graphKey, baseWidth, baseHeight }) {
  const shell = document.createElement("div");
  shell.className = "graph-interaction-shell";
  const controls = document.createElement("div");
  controls.className = "graph-interaction-controls";
  controls.innerHTML = `
    <span class="graph-interaction-hint">Scroll to zoom. Drag the background to pan.</span>
    <div class="graph-interaction-buttons">
      <button class="button micro" type="button" data-graph-zoom="out">−</button>
      <button class="button micro" type="button" data-graph-zoom="in">+</button>
      <button class="button micro" type="button" data-graph-zoom="reset">Reset</button>
    </div>
  `;
  shell.appendChild(controls);
  shell.appendChild(svg);
  host.appendChild(shell);

  const persisted = state.graphViewBoxes[graphKey];
  const initialViewBox = persisted
    ? clampGraphViewBox({ ...persisted }, baseWidth, baseHeight)
    : parseViewBox(svg, baseWidth, baseHeight);
  setSvgViewBox(svg, initialViewBox);
  state.graphViewBoxes[graphKey] = initialViewBox;

  const updateViewBox = (nextBox) => {
    const clamped = clampGraphViewBox(nextBox, baseWidth, baseHeight);
    state.graphViewBoxes[graphKey] = clamped;
    setSvgViewBox(svg, clamped);
  };

  const zoomBy = (factor, originClient = null) => {
    const current = state.graphViewBoxes[graphKey] || parseViewBox(svg, baseWidth, baseHeight);
    const rect = svg.getBoundingClientRect();
    const originX = originClient ? (originClient.x - rect.left) / Math.max(rect.width, 1) : 0.5;
    const originY = originClient ? (originClient.y - rect.top) / Math.max(rect.height, 1) : 0.5;
    const nextWidth = current.width * factor;
    const nextHeight = current.height * factor;
    const worldX = current.x + current.width * originX;
    const worldY = current.y + current.height * originY;
    updateViewBox({
      x: worldX - nextWidth * originX,
      y: worldY - nextHeight * originY,
      width: nextWidth,
      height: nextHeight,
    });
  };

  controls.querySelector('[data-graph-zoom="in"]')?.addEventListener("click", () => zoomBy(0.85));
  controls.querySelector('[data-graph-zoom="out"]')?.addEventListener("click", () => zoomBy(1.18));
  controls.querySelector('[data-graph-zoom="reset"]')?.addEventListener("click", () => {
    updateViewBox({ x: 0, y: 0, width: baseWidth, height: baseHeight });
  });

  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? 0.9 : 1.1, { x: event.clientX, y: event.clientY });
  }, { passive: false });

  let panState = null;
  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || event.target !== svg) return;
    const current = state.graphViewBoxes[graphKey] || parseViewBox(svg, baseWidth, baseHeight);
    panState = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      viewBox: { ...current },
    };
    svg.setPointerCapture(event.pointerId);
    svg.classList.add("is-panning");
  });
  svg.addEventListener("pointermove", (event) => {
    if (!panState || event.pointerId !== panState.pointerId) return;
    const rect = svg.getBoundingClientRect();
    const deltaX = ((event.clientX - panState.startX) / Math.max(rect.width, 1)) * panState.viewBox.width;
    const deltaY = ((event.clientY - panState.startY) / Math.max(rect.height, 1)) * panState.viewBox.height;
    updateViewBox({
      x: panState.viewBox.x - deltaX,
      y: panState.viewBox.y - deltaY,
      width: panState.viewBox.width,
      height: panState.viewBox.height,
    });
  });
  const endPan = (event) => {
    if (!panState || event.pointerId !== panState.pointerId) return;
    panState = null;
    svg.classList.remove("is-panning");
    try {
      svg.releasePointerCapture(event.pointerId);
    } catch (_error) {
      // Ignore stale pointer capture release attempts.
    }
  };
  svg.addEventListener("pointerup", endPan);
  svg.addEventListener("pointercancel", endPan);
}

function renderSparklineTimeseriesHost(host, series, config) {
  if (!host) return;
  host.innerHTML = "";
  const rows = Array.isArray(series) ? series : [];
  const definitions = Array.isArray(config?.seriesDefinitions) ? config.seriesDefinitions : [];
  const stacked = Boolean(config?.stacked);
  const populatedRows = rows.filter((row) => {
    if (stacked) {
      return definitions.some((definition) => Number.isFinite(Number(row?.[definition.key])) && Number(row?.[definition.key]) > 0);
    }
    return definitions.some((definition) => Number.isFinite(Number(row?.[definition.key])));
  });
  if (!populatedRows.length) {
    host.appendChild(buildEmptyState({
      icon: "≈",
      title: "No time-series samples yet.",
      body: config?.emptyBody || "Run more requests for this vendor or model to populate the chart.",
    }));
    return;
  }

  const NS = "http://www.w3.org/2000/svg";
  const width = 560;
  const height = 220;
  const padding = { top: 18, right: 20, bottom: 34, left: 48 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const allValues = stacked
    ? populatedRows.map((row) => (
      definitions.reduce((sum, definition) => {
        const value = Number(row?.[definition.key]);
        return sum + (Number.isFinite(value) ? Math.max(0, value) : 0);
      }, 0)
    ))
    : definitions.flatMap((definition) => (
      populatedRows
        .map((row) => Number(row?.[definition.key]))
        .filter((value) => Number.isFinite(value))
    ));
  const minValue = stacked ? 0 : Math.min(...allValues);
  const maxValue = Math.max(...allValues);
  const range = maxValue === minValue ? Math.max(1, Math.abs(maxValue || 1)) : (maxValue - minValue);
  const xForIndex = (index) => padding.left + (populatedRows.length <= 1 ? plotWidth / 2 : (index / (populatedRows.length - 1)) * plotWidth);
  const yForValue = (value) => padding.top + plotHeight - ((value - minValue) / range) * plotHeight;

  const shell = document.createElement("div");
  shell.className = "llm-timeseries-shell";
  const legend = document.createElement("div");
  legend.className = "llm-timeseries-legend";
  legend.innerHTML = definitions.map((definition) => `
    <span class="llm-timeseries-legend-item">
      <span class="llm-timeseries-swatch" style="--swatch:${escapeHtml(definition.color)}"></span>
      <span>${escapeHtml(definition.label)}</span>
    </span>
  `).join("");
  shell.appendChild(legend);

  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "llm-timeseries-svg");
  const bucketSelectable = typeof config?.onBucketSelect === "function";
  if (bucketSelectable) {
    svg.style.cursor = "pointer";
  }

  const axis = document.createElementNS(NS, "line");
  axis.setAttribute("x1", String(padding.left));
  axis.setAttribute("y1", String(height - padding.bottom));
  axis.setAttribute("x2", String(width - padding.right));
  axis.setAttribute("y2", String(height - padding.bottom));
  axis.setAttribute("class", "llm-timeseries-axis");
  svg.appendChild(axis);

  const yAxis = document.createElementNS(NS, "line");
  yAxis.setAttribute("x1", String(padding.left));
  yAxis.setAttribute("y1", String(padding.top));
  yAxis.setAttribute("x2", String(padding.left));
  yAxis.setAttribute("y2", String(height - padding.bottom));
  yAxis.setAttribute("class", "llm-timeseries-axis");
  svg.appendChild(yAxis);

  const formatTickValue = (value) => {
    if (typeof config?.formatValue === "function") {
      return String(config.formatValue(value));
    }
    return `${formattedValue(value)}${config?.unitSuffix || ""}`;
  };
  const tickValues = [maxValue, minValue + range / 2, minValue];
  tickValues.forEach((tickValue) => {
    const y = yForValue(tickValue);
    const grid = document.createElementNS(NS, "line");
    grid.setAttribute("x1", String(padding.left));
    grid.setAttribute("y1", String(y));
    grid.setAttribute("x2", String(width - padding.right));
    grid.setAttribute("y2", String(y));
    grid.setAttribute("class", "llm-timeseries-gridline");
    svg.appendChild(grid);

    const label = document.createElementNS(NS, "text");
    label.setAttribute("x", String(padding.left - 8));
    label.setAttribute("y", String(y + 4));
    label.setAttribute("text-anchor", "end");
    label.setAttribute("class", "llm-timeseries-label");
    label.textContent = formatTickValue(tickValue);
    svg.appendChild(label);
  });

  if (stacked) {
    const barWidth = Math.max(8, Math.min(36, plotWidth / Math.max(populatedRows.length, 1) * 0.66));
    populatedRows.forEach((row, index) => {
      let currentTotal = 0;
      const x = xForIndex(index) - (barWidth / 2);
      definitions.forEach((definition) => {
        const value = Number(row?.[definition.key]);
        if (!Number.isFinite(value) || value <= 0) return;
        const lowerBound = currentTotal;
        currentTotal += value;
        const rect = document.createElementNS(NS, "rect");
        rect.setAttribute("x", String(x));
        rect.setAttribute("width", String(barWidth));
        rect.setAttribute("y", String(yForValue(currentTotal)));
        rect.setAttribute("height", String(Math.max(1, yForValue(lowerBound) - yForValue(currentTotal))));
        rect.setAttribute("fill", definition.color);
        rect.setAttribute("rx", "3");
        rect.setAttribute("opacity", "0.92");
        svg.appendChild(rect);
      });
    });
  } else {
    definitions.forEach((definition) => {
      const points = populatedRows
        .map((row, index) => {
          const value = Number(row?.[definition.key]);
          if (!Number.isFinite(value)) return null;
          return `${xForIndex(index)},${yForValue(value)}`;
        })
        .filter(Boolean);
      if (!points.length) return;
      const polyline = document.createElementNS(NS, "polyline");
      polyline.setAttribute("fill", "none");
      polyline.setAttribute("stroke", definition.color);
      polyline.setAttribute("stroke-width", "3");
      polyline.setAttribute("stroke-linecap", "round");
      polyline.setAttribute("stroke-linejoin", "round");
      polyline.setAttribute("points", points.join(" "));
      svg.appendChild(polyline);

      const lastIndex = populatedRows.length - 1;
      const lastValue = Number(populatedRows[lastIndex]?.[definition.key]);
      if (Number.isFinite(lastValue)) {
        const circle = document.createElementNS(NS, "circle");
        circle.setAttribute("cx", String(xForIndex(lastIndex)));
        circle.setAttribute("cy", String(yForValue(lastValue)));
        circle.setAttribute("r", "4.5");
        circle.setAttribute("fill", definition.color);
        svg.appendChild(circle);
      }
    });
  }

  if (bucketSelectable) {
    populatedRows.forEach((row, index) => {
      const previousX = index === 0 ? padding.left : xForIndex(index - 1);
      const nextX = index === populatedRows.length - 1 ? width - padding.right : xForIndex(index + 1);
      const left = index === 0 ? padding.left : (previousX + xForIndex(index)) / 2;
      const right = index === populatedRows.length - 1 ? width - padding.right : (xForIndex(index) + nextX) / 2;
      const hotspot = document.createElementNS(NS, "rect");
      hotspot.setAttribute("x", String(left));
      hotspot.setAttribute("y", String(padding.top));
      hotspot.setAttribute("width", String(Math.max(8, right - left)));
      hotspot.setAttribute("height", String(plotHeight));
      hotspot.setAttribute("fill", "transparent");
      hotspot.addEventListener("click", () => config.onBucketSelect(row, index));
      const title = document.createElementNS(NS, "title");
      title.textContent = `Open traffic for ${new Date(row.bucket_start).toLocaleString()}`;
      hotspot.appendChild(title);
      svg.appendChild(hotspot);
    });
  }

  const tickIndexes = [...new Set([0, Math.floor((populatedRows.length - 1) / 2), populatedRows.length - 1])].filter((index) => index >= 0);
  tickIndexes.forEach((index) => {
    const row = populatedRows[index];
    const label = document.createElementNS(NS, "text");
    label.setAttribute("x", String(xForIndex(index)));
    label.setAttribute("y", String(height - 10));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "llm-timeseries-label");
    label.textContent = new Date(row.bucket_start).toLocaleDateString([], populatedRows.length > 24 ? { month: "short", day: "numeric" } : { month: "short", day: "numeric", hour: "numeric" });
    svg.appendChild(label);
  });

  shell.appendChild(svg);
  host.appendChild(shell);
}

function renderSparklineTimeseries(selector, series, config) {
  renderSparklineTimeseriesHost($(selector), series, config);
}

function setTableLoadingMany(selectors, options) {
  (selectors || []).forEach((selector) => setTableLoading(selector, options));
}

function persistTableState() {
  localStorage.setItem("llmproxy.admin.tableState", JSON.stringify({
    tablePages: state.tablePages,
    tablePageSizes: state.tablePageSizes,
    tableContexts: state.tableContexts,
    foundationModelVisibilityScope: state.foundationModelVisibilityScope,
    opsEventColumnPreset: state.opsEventColumnPreset,
    savedOpsPresets: state.savedOpsPresets,
  }));
}

function pageSizeFor(pageKey, fallback = 15) {
  if (!pageKey) return fallback;
  const configured = Number(state.tablePageSizes[pageKey] || fallback);
  return configured > 0 ? configured : fallback;
}

function rememberTableContext(pageKey, context = {}) {
  if (!pageKey) return context;
  state.tableContexts[pageKey] = { ...context };
  persistTableState();
  return state.tableContexts[pageKey];
}

function currentTableContext(pageKey, formSelector = null) {
  const remembered = state.tableContexts[pageKey];
  if (remembered && Object.keys(remembered).length) {
    return { ...remembered };
  }
  return formSelector ? collectFormFilters(formSelector) : {};
}

function tableOptionsForHost(host, selector, options = {}) {
  if (!host?.classList?.contains("runtime-table")) {
    return options;
  }
  const defaultPageSize = options.pageSize ?? 15;
  return {
    pageKey: selector,
    pageSize: pageSizeFor(selector, defaultPageSize),
    itemLabel: "rows",
    ...options,
  };
}

function getPaginatedRows(rows, { pageKey = null, pageSize = null } = {}) {
  const items = Array.isArray(rows) ? rows : [];
  const resolvedPageSize = pageKey ? pageSizeFor(pageKey, pageSize || 15) : pageSize;
  if (!pageKey || !resolvedPageSize || items.length <= resolvedPageSize) {
    return {
      currentPage: 1,
      endIndex: items.length,
      pageRows: items,
      pageSize: resolvedPageSize || items.length || 0,
      startIndex: items.length ? 1 : 0,
      totalPages: 1,
      totalRows: items.length,
    };
  }
  const totalPages = Math.max(1, Math.ceil(items.length / resolvedPageSize));
  const requestedPage = Number(state.tablePages[pageKey] || 1);
  const currentPage = Math.min(Math.max(requestedPage, 1), totalPages);
  state.tablePages[pageKey] = currentPage;
  persistTableState();
  const startOffset = (currentPage - 1) * resolvedPageSize;
  return {
    currentPage,
    endIndex: Math.min(items.length, startOffset + resolvedPageSize),
    pageRows: items.slice(startOffset, startOffset + resolvedPageSize),
    pageSize: resolvedPageSize,
    startIndex: startOffset + 1,
    totalPages,
    totalRows: items.length,
  };
}

function buildTablePaginationControls(pageState, { pageKey, itemLabel = "rows", onChange, defaultPageSize = 15 } = {}) {
  const controls = document.createElement("div");
  controls.className = "table-pagination";
  const status = document.createElement("div");
  status.className = "table-pagination-status";
  status.textContent = `Showing ${pageState.startIndex}-${pageState.endIndex} of ${pageState.totalRows} ${itemLabel}`;
  controls.appendChild(status);

  const actions = document.createElement("div");
  actions.className = "table-pagination-actions";

  const pageChip = document.createElement("span");
  pageChip.className = "table-page-chip";
  pageChip.textContent = `Page ${pageState.currentPage} / ${pageState.totalPages}`;

  const pageSizeSelect = document.createElement("select");
  pageSizeSelect.className = "table-page-size";
  [10, 15, 25, 50, 100].forEach((size) => {
    const option = document.createElement("option");
    option.value = String(size);
    option.textContent = `${size} / page`;
    if (size === pageSizeFor(pageKey, defaultPageSize)) {
      option.selected = true;
    }
    pageSizeSelect.appendChild(option);
  });
  pageSizeSelect.addEventListener("change", () => {
    state.tablePageSizes[pageKey] = Number(pageSizeSelect.value || defaultPageSize);
    state.tablePages[pageKey] = 1;
    persistTableState();
    onChange?.();
  });

  const previous = document.createElement("button");
  previous.type = "button";
  previous.className = "button micro";
  previous.textContent = "Previous";
  previous.disabled = pageState.currentPage <= 1;
  previous.addEventListener("click", () => {
    state.tablePages[pageKey] = Math.max(1, pageState.currentPage - 1);
    persistTableState();
    onChange?.();
  });

  const next = document.createElement("button");
  next.type = "button";
  next.className = "button micro";
  next.textContent = "Next";
  next.disabled = pageState.currentPage >= pageState.totalPages;
  next.addEventListener("click", () => {
    state.tablePages[pageKey] = Math.min(pageState.totalPages, pageState.currentPage + 1);
    persistTableState();
    onChange?.();
  });

  actions.appendChild(pageSizeSelect);
  actions.appendChild(previous);
  actions.appendChild(pageChip);
  actions.appendChild(next);
  controls.appendChild(actions);
  return controls;
}

function requestedPage(pageKey) {
  return Math.max(1, Number(state.tablePages[pageKey] || 1));
}

function paginationParams(pageKey, pageSize = 15) {
  const currentPage = requestedPage(pageKey);
  const resolvedPageSize = pageSizeFor(pageKey, pageSize);
  return {
    currentPage,
    limit: resolvedPageSize,
    offset: (currentPage - 1) * resolvedPageSize,
    pageSize: resolvedPageSize,
  };
}

function resetTablePage(pageKey) {
  state.tablePages[pageKey] = 1;
  persistTableState();
}

function serverPaginationForPayload(pageKey, payload, pageSize, onChange) {
  const totalRows = Math.max(0, Number(payload?.total || 0));
  const offset = Math.max(0, Number(payload?.offset || 0));
  const limit = Math.max(1, Number(payload?.limit || pageSize || 15));
  const itemCount = Array.isArray(payload?.items) ? payload.items.length : 0;
  return {
    currentPage: Math.max(1, Math.floor(offset / limit) + 1),
    totalPages: Math.max(1, Math.ceil(totalRows / limit)),
    totalRows,
    startIndex: totalRows ? offset + 1 : 0,
    endIndex: totalRows ? offset + itemCount : 0,
    pageSize: limit,
    onChange,
  };
}

function renderKeyValueTable(selector, rows, { emptyMessage = "No values available.", allowEdit = false, ...tableOptions } = {}) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  const resolvedTableOptions = tableOptionsForHost(host, selector, { itemLabel: "settings", ...tableOptions });
  host.appendChild(
    makeTable(allowEdit ? ["Key", "Value", "Edit", "Actions"] : ["Key", "Value"], rows, (row) => {
      const tr = document.createElement("tr");
      if (!allowEdit) {
        tr.innerHTML = `<td><strong>${escapeHtml(row.key)}</strong></td><td>${escapeHtml(row.value)}</td>`;
        return tr;
      }
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.key)}</strong></td>
        <td>${escapeHtml(row.value)}</td>
        <td></td>
        <td></td>
      `;
      const input = document.createElement("input");
      input.value = row.value;
      tr.children[2].appendChild(input);
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Save", async () => {
          const result = await apiFetch("/admin/api/config/set", {
            method: "POST",
            body: JSON.stringify({
              key: row.key,
              value: input.value,
              env_file: $("#config-set-form [name='env_file']").value || ".env.local",
            }),
          });
          logConsole("config inline save", result);
          showToast(`Updated ${row.key}.`, "ok");
          setFieldValue("#config-set-form", "key", row.key);
          setFieldValue("#config-set-form", "value", input.value);
          await refreshConfig();
        }, { accent: true }),
      );
      tr.children[3].appendChild(actions);
      return tr;
    }, emptyMessage, resolvedTableOptions),
  );
}

function renderSimpleTable(selector, title, columns, rows, rowRenderer, emptyMessage, tableOptions = {}) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  const resolvedTableOptions = tableOptionsForHost(host, selector, tableOptions);
  if (title) {
    const heading = document.createElement("h4");
    heading.textContent = title;
    host.appendChild(heading);
  }
  host.appendChild(makeTable(columns, rows, rowRenderer, emptyMessage, resolvedTableOptions));
}

function renderConnectivitySnapshotTable(selector, groups) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  const entries = Array.isArray(groups) ? groups : [];
  if (!entries.length) {
    host.appendChild(buildEmptyState({
      icon: "↳",
      title: "No provider readiness data.",
      body: "Refresh readiness to load the current provider and model status tree.",
    }));
    return;
  }

  host.appendChild(
    makeTable(
      ["Vendor", "Configured", "Connectivity", "Healthy Models", "Notes", "Actions"],
      entries,
      (group) => {
        const tr = document.createElement("tr");
        tr.dataset.recordId = buildFoundationProviderKey(group);
        tr.addEventListener("click", (event) => {
          if (event.target.closest("button")) return;
          openConnectivityVendorContext(group).catch((error) => {
            showToast(`Vendor drill-through failed: ${String(error)}`, "err");
            logConsole("connectivity vendor drill-through failed", String(error));
          });
        });
        tr.innerHTML = `
          <td>
            <strong>${escapeHtml(humanizeLabel(group.provider_name || group.provider_key || "Provider"))}</strong>
            <div class="table-subtext">${escapeHtml(String(group.provider_family || ""))}</div>
          </td>
          <td>${boolBadge(Boolean(group.configured))}</td>
          <td>${statusBadge(group.status || "-")}</td>
          <td><span class="num">${escapeHtml(`${formattedValue(group.healthy_model_count)}/${formattedValue(group.model_count)}`)}</span></td>
          <td>${escapeHtml(group.note || "See Models > LLMs for per-model drill-down.")}</td>
          <td></td>
        `;
        const actions = document.createElement("div");
        actions.className = "table-actions";
        actions.appendChild(createActionButton("Open Vendor", () => openConnectivityVendorContext(group), { accent: true }));
        tr.lastElementChild.appendChild(actions);
        return tr;
      },
      "Vendor connectivity will appear here once readiness data is loaded.",
    ),
  );
}

function currentModelMonitor() {
  const rows = Array.isArray(state.modelMonitorPayload?.monitors) ? state.modelMonitorPayload.monitors : [];
  return rows.find((row) => String(row.monitor_id || "") === String(state.selectedModelMonitorId || "")) || null;
}

function readinessProviderModelOptions() {
  const groups = Array.isArray(state.healthPayload?.provider_readiness) ? state.healthPayload.provider_readiness : [];
  return groups
    .map((group) => ({
      provider_key: group.models?.[0]?.provider_key || group.provider_key,
      provider_name: group.provider_name || group.provider_key,
      models: Array.isArray(group.models) ? group.models.map((model) => ({
        provider_key: model.provider_key || group.provider_key,
        model_id: model.model_id,
        status: model.status,
      })) : [],
    }))
    .filter((group) => group.provider_key && group.models.length);
}

function renderModelMonitorProviderOptions() {
  const providerSelect = $("#model-monitor-provider-key");
  const modelSelect = $("#model-monitor-model-id");
  if (!providerSelect || !modelSelect) return;
  const groups = readinessProviderModelOptions();
  const currentProvider = String(providerSelect.value || groups[0]?.provider_key || "");
  providerSelect.innerHTML = groups.map((group) => (
    `<option value="${escapeHtml(group.provider_key)}"${group.provider_key === currentProvider ? " selected" : ""}>${escapeHtml(group.provider_name)}</option>`
  )).join("");
  const selectedGroup = groups.find((group) => group.provider_key === String(providerSelect.value || currentProvider)) || groups[0];
  const currentModel = String(modelSelect.value || selectedGroup?.models?.[0]?.model_id || "");
  modelSelect.innerHTML = (selectedGroup?.models || []).map((model) => (
    `<option value="${escapeHtml(model.model_id)}"${model.model_id === currentModel ? " selected" : ""}>${escapeHtml(model.model_id)}</option>`
  )).join("");
}

function promptTemplateInventoryRows() {
  return Array.isArray(state.promptTemplateInventory) && state.promptTemplateInventory.length
    ? state.promptTemplateInventory
    : (Array.isArray(state.promptTemplates) ? state.promptTemplates : []);
}

function promptTemplateFamilies() {
  const families = new Map();
  promptTemplateInventoryRows().forEach((row) => {
    const name = String(row?.name || "").trim();
    if (!name) return;
    if (!families.has(name)) {
      families.set(name, []);
    }
    families.get(name).push(row);
  });
  return [...families.entries()]
    .map(([name, versions]) => ({
      name,
      versions: [...versions].sort((left, right) => Number(right?.version || 0) - Number(left?.version || 0)),
    }))
    .sort((left, right) => left.name.localeCompare(right.name));
}

function promptTemplateVersionOptionLabel(row) {
  const parts = [`v${formattedValue(row?.version || "-")}`];
  if (row?.status) {
    parts.push(humanizeLabel(row.status));
  }
  if (row?.rollout?.mode === "canary") {
    parts.push(`Canary ${formattedValue(row.rollout.traffic_percentage)}%`);
  }
  return parts.join(" · ");
}

function renderPromptTemplatePicker(nameSelector, versionSelector, options = {}) {
  const {
    blankNameLabel = "Any prompt template",
    blankVersionLabel = "Any version",
    unresolvedVersionLabel = "Live resolved version",
  } = options;
  const nameSelect = $(nameSelector);
  const versionSelect = $(versionSelector);
  if (!nameSelect || !versionSelect) return;
  const families = promptTemplateFamilies();
  const currentName = String(nameSelect.value || "").trim();
  nameSelect.innerHTML = [
    `<option value="">${escapeHtml(blankNameLabel)}</option>`,
    ...families.map((family) => `<option value="${escapeHtml(family.name)}"${family.name === currentName ? " selected" : ""}>${escapeHtml(family.name)}</option>`),
  ].join("");
  const selectedName = String(nameSelect.value || currentName || "").trim();
  const versions = families.find((family) => family.name === selectedName)?.versions || [];
  const currentVersion = String(versionSelect.value || "").trim();
  versionSelect.innerHTML = [
    `<option value="">${escapeHtml(selectedName ? blankVersionLabel : unresolvedVersionLabel)}</option>`,
    ...versions.map((row) => `<option value="${escapeHtml(String(row.version))}"${String(row.version) === currentVersion ? " selected" : ""}>${escapeHtml(promptTemplateVersionOptionLabel(row))}</option>`),
  ].join("");
  versionSelect.disabled = !selectedName && !versions.length;
  versionSelect.value = currentVersion && versions.some((row) => String(row.version) === currentVersion) ? currentVersion : "";
}

function renderAllPromptTemplatePickers() {
  renderPromptTemplatePicker("#chat-prompt-template-name", "#chat-prompt-template-version", {
    blankNameLabel: "No prompt template",
    unresolvedVersionLabel: "Live resolved version",
    blankVersionLabel: "Live resolved version",
  });
  renderPromptTemplatePicker("#candidates-prompt-template-name", "#candidates-prompt-template-version", {
    blankNameLabel: "Any prompt template",
    unresolvedVersionLabel: "Choose template first",
    blankVersionLabel: "All versions for template",
  });
  renderPromptTemplatePicker("#export-prompt-template-name", "#export-prompt-template-version", {
    blankNameLabel: "Any prompt template",
    unresolvedVersionLabel: "Choose template first",
    blankVersionLabel: "All versions for template",
  });
  renderPromptTemplatePicker("#exports-prompt-template-name", "#exports-prompt-template-version", {
    blankNameLabel: "Any prompt template",
    unresolvedVersionLabel: "Choose template first",
    blankVersionLabel: "All versions for template",
  });
  renderPromptTemplatePicker("#ops-events-prompt-template-name", "#ops-events-prompt-template-version", {
    blankNameLabel: "Any prompt template",
    unresolvedVersionLabel: "Choose template first",
    blankVersionLabel: "All versions for template",
  });
}

async function refreshPromptTemplateInventory(force = false) {
  if (!state.token) return [];
  if (!force && Array.isArray(state.promptTemplateInventory) && state.promptTemplateInventory.length) {
    renderAllPromptTemplatePickers();
    return state.promptTemplateInventory;
  }
  const payload = await apiFetch("/admin/api/prompts?paginated=true&limit=200&offset=0");
  state.promptTemplateInventory = payload.items || [];
  renderPromptSummary();
  renderAllPromptTemplatePickers();
  return state.promptTemplateInventory;
}

function opsEventTrafficFiltersActive(filters = collectFormFilters("#ops-events-filter-form")) {
  const normalizedClass = String(filters.event_class || "").trim().toLowerCase();
  const normalizedSource = String(filters.event_source || "").trim().toLowerCase();
  if (normalizedClass === "request" || normalizedSource === "request") {
    return true;
  }
  return [
    "selected_provider",
    "selected_model",
    "selected_pool_id",
    "selected_node_id",
    "prompt_template_name",
    "prompt_template_version",
    "prompt_template_selection_mode",
    "traffic_origin",
    "automation_scope",
  ].some((key) => String(filters[key] || "").trim() !== "");
}

function renderOpsEventTrafficScopeVisibility() {
  const group = $("#ops-traffic-scope-group");
  if (!group) return;
  group.classList.toggle("hidden", !opsEventTrafficFiltersActive());
}

function opsEventPoolOptions() {
  const pools = Array.isArray(state.routingTopologyInventory?.pools) ? state.routingTopologyInventory.pools : [];
  const fromTopology = pools
    .map((pool) => ({
      value: String(pool.pool_id || "").trim(),
      label: String(pool.label || pool.pool_id || "").trim(),
    }))
    .filter((entry) => entry.value);
  const fromPolicy = (state.policyRows || [])
    .map((row) => ({
      value: String(row.pool_id || row.detail?.entry?.pool_id || "").trim(),
      label: String(row.pool_id || row.detail?.entry?.pool_id || "").trim(),
    }))
    .filter((entry) => entry.value);
  return [...fromTopology, ...fromPolicy];
}

function opsEventNodeOptions() {
  const nodes = Array.isArray(state.routingTopologyInventory?.nodes) ? state.routingTopologyInventory?.nodes : [];
  const fromTopology = nodes
    .map((node) => ({
      value: String(node.node_id || node.id || "").trim(),
      label: String(node.label || node.title || node.node_id || node.id || "").trim(),
    }))
    .filter((entry) => entry.value);
  const fromPolicy = (state.policyRows || [])
    .map((row) => ({
      value: String(row.node_id || row.detail?.entry?.node_id || "").trim(),
      label: String(row.node_id || row.detail?.entry?.node_id || "").trim(),
    }))
    .filter((entry) => entry.value);
  return [...fromTopology, ...fromPolicy];
}

function uniqueSelectEntries(entries = []) {
  const deduped = [];
  const seen = new Set();
  entries.forEach((entry) => {
    const value = String(entry?.value || "").trim();
    const label = String(entry?.label || value).trim();
    if (!value) return;
    if (seen.has(value)) return;
    seen.add(value);
    deduped.push({ value, label });
  });
  return deduped;
}

function renderOpsEventTrafficFilterOptions() {
  const providerSelect = $("#ops-events-selected-provider");
  const modelSelect = $("#ops-events-selected-model");
  const poolSelect = $("#ops-events-selected-pool");
  const nodeSelect = $("#ops-events-selected-node");
  const originSelect = $("#ops-events-traffic-origin");
  const scopeSelect = $("#ops-events-automation-scope");
  if (!providerSelect || !modelSelect || !poolSelect || !nodeSelect || !originSelect || !scopeSelect) return;
  const groups = readinessProviderModelOptions();
  const persisted = currentTableContext("#ops-events-table", "#ops-events-filter-form");
  const currentProvider = String(providerSelect.value || persisted.selected_provider || "").trim();
  providerSelect.innerHTML = [
    '<option value="">All discovered providers</option>',
    ...groups.map((group) => (
      `<option value="${escapeHtml(group.provider_key)}"${group.provider_key === currentProvider ? " selected" : ""}>${escapeHtml(group.provider_name)}</option>`
    )),
  ].join("");
  const selectedProvider = String(providerSelect.value || currentProvider || "").trim();
  const modelEntries = selectedProvider
    ? (groups.find((group) => group.provider_key === selectedProvider)?.models || []).map((model) => ({
        value: String(model.model_id || ""),
        label: String(model.model_id || ""),
      }))
    : groups.flatMap((group) => (group.models || []).map((model) => ({
        value: String(model.model_id || ""),
        label: `${group.provider_name} / ${String(model.model_id || "")}`,
      })));
  const deduped = [];
  const seen = new Set();
  modelEntries.forEach((entry) => {
    if (!entry.value || seen.has(`${entry.value}|${entry.label}`)) return;
    seen.add(`${entry.value}|${entry.label}`);
    deduped.push(entry);
  });
  const currentModel = String(modelSelect.value || persisted.selected_model || "").trim();
  modelSelect.innerHTML = [
    `<option value="">${escapeHtml(selectedProvider ? "All discovered models for provider" : "All discovered models")}</option>`,
    ...deduped.map((entry) => `<option value="${escapeHtml(entry.value)}"${entry.value === currentModel ? " selected" : ""}>${escapeHtml(entry.label)}</option>`),
  ].join("");
  modelSelect.value = currentModel && deduped.some((entry) => entry.value === currentModel) ? currentModel : "";
  const currentPool = String(poolSelect.value || persisted.selected_pool_id || "").trim();
  const pools = uniqueSelectEntries(opsEventPoolOptions());
  poolSelect.innerHTML = [
    '<option value="">All discovered pools</option>',
    ...pools.map((entry) => `<option value="${escapeHtml(entry.value)}"${entry.value === currentPool ? " selected" : ""}>${escapeHtml(entry.label)}</option>`),
  ].join("");
  poolSelect.value = currentPool && pools.some((entry) => entry.value === currentPool) ? currentPool : "";
  const currentNode = String(nodeSelect.value || persisted.selected_node_id || "").trim();
  const nodes = uniqueSelectEntries(opsEventNodeOptions());
  nodeSelect.innerHTML = [
    '<option value="">All discovered nodes</option>',
    ...nodes.map((entry) => `<option value="${escapeHtml(entry.value)}"${entry.value === currentNode ? " selected" : ""}>${escapeHtml(entry.label)}</option>`),
  ].join("");
  nodeSelect.value = currentNode && nodes.some((entry) => entry.value === currentNode) ? currentNode : "";
  const currentOrigin = String(originSelect.value || persisted.traffic_origin || "").trim();
  const originEntries = uniqueSelectEntries([
    { value: "interactive", label: "Interactive" },
    { value: "learning_pipeline", label: "Learning Pipeline" },
    { value: "automation", label: "Automation" },
    { value: "api_client", label: "API Client" },
  ]);
  originSelect.innerHTML = [
    '<option value="">All traffic origins</option>',
    ...originEntries.map((entry) => `<option value="${escapeHtml(entry.value)}"${entry.value === currentOrigin ? " selected" : ""}>${escapeHtml(entry.label)}</option>`),
  ].join("");
  originSelect.value = currentOrigin && originEntries.some((entry) => entry.value === currentOrigin) ? currentOrigin : "";
  const currentScope = String(scopeSelect.value || persisted.automation_scope || "").trim();
  const scopeEntries = [
    { value: "training", label: "Training" },
    { value: "evaluation", label: "Evaluation" },
  ];
  scopeSelect.innerHTML = [
    '<option value="">All pipeline scopes</option>',
    ...scopeEntries.map((entry) => `<option value="${escapeHtml(entry.value)}"${entry.value === currentScope ? " selected" : ""}>${escapeHtml(entry.label)}</option>`),
  ].join("");
  scopeSelect.value = currentScope && scopeEntries.some((entry) => entry.value === currentScope) ? currentScope : "";
  renderPromptTemplatePicker("#ops-events-prompt-template-name", "#ops-events-prompt-template-version", {
    blankNameLabel: "Any prompt template",
    unresolvedVersionLabel: "Choose template first",
    blankVersionLabel: "All versions for template",
  });
  renderOpsEventTrafficScopeVisibility();
}

const llmTimeseriesMetricDefinitions = {
  request_count: { key: "request_count", label: "Requests", category: "Traffic", scaleType: "count", color: "#2563eb" },
  rate_limit_event_count: { key: "rate_limit_event_count", label: "Rate Limit Events", category: "Traffic", scaleType: "count", color: "#ef4444" },
  provider_429_count: { key: "provider_429_count", label: "Provider 429s", category: "Traffic", scaleType: "count", color: "#f97316" },
  provider_429_request_count: { key: "provider_429_request_count", label: "Provider 429s (Request)", category: "Traffic", scaleType: "count", color: "#ea580c" },
  provider_429_stream_count: { key: "provider_429_stream_count", label: "Provider 429s (Stream)", category: "Traffic", scaleType: "count", color: "#c2410c" },
  success_rate_pct: { key: "success_rate_pct", label: "Success Rate", category: "Traffic", scaleType: "percent", color: "#16a34a" },
  error_rate_pct: { key: "error_rate_pct", label: "Error Rate", category: "Traffic", scaleType: "percent", color: "#dc2626" },
  provider_429_rate_pct: { key: "provider_429_rate_pct", label: "Provider 429 Rate", category: "Traffic", scaleType: "percent", color: "#fb923c" },
  fallback_rate_pct: { key: "fallback_rate_pct", label: "Fallback Rate", category: "Routing", scaleType: "percent", color: "#ca8a04" },
  redirect_rate_pct: { key: "redirect_rate_pct", label: "Redirect Rate", category: "Routing", scaleType: "percent", color: "#7c3aed" },
  stream_start_count: { key: "stream_start_count", label: "Streams Started", category: "Streaming", scaleType: "count", color: "#2563eb" },
  stream_complete_count: { key: "stream_complete_count", label: "Streams Completed", category: "Streaming", scaleType: "count", color: "#16a34a" },
  stream_failure_count: { key: "stream_failure_count", label: "Streams Failed", category: "Streaming", scaleType: "count", color: "#dc2626" },
  stream_partial_abort_count: { key: "stream_partial_abort_count", label: "Partial Aborts", category: "Streaming", scaleType: "count", color: "#f59e0b" },
  stream_prelude_failure_count: { key: "stream_prelude_failure_count", label: "Prelude Failures", category: "Streaming", scaleType: "count", color: "#b91c1c" },
  stream_complete_rate_pct: { key: "stream_complete_rate_pct", label: "Stream Completion Rate", category: "Streaming", scaleType: "percent", color: "#0f766e" },
  stream_partial_abort_rate_pct: { key: "stream_partial_abort_rate_pct", label: "Partial Abort Rate", category: "Streaming", scaleType: "percent", color: "#d97706" },
  stream_prelude_failure_rate_pct: { key: "stream_prelude_failure_rate_pct", label: "Prelude Failure Rate", category: "Streaming", scaleType: "percent", color: "#991b1b" },
  cache_hit_count: { key: "cache_hit_count", label: "Cache Hits", category: "Cache", scaleType: "count", color: "#16a34a" },
  cache_miss_count: { key: "cache_miss_count", label: "Cache Misses", category: "Cache", scaleType: "count", color: "#dc2626" },
  cache_bypass_count: { key: "cache_bypass_count", label: "Cache Bypasses", category: "Cache", scaleType: "count", color: "#6b7280" },
  exact_cache_hit_count: { key: "exact_cache_hit_count", label: "Exact Cache Hits", category: "Cache", scaleType: "count", color: "#2563eb" },
  semantic_cache_hit_count: { key: "semantic_cache_hit_count", label: "Semantic Cache Hits", category: "Cache", scaleType: "count", color: "#7c3aed" },
  cache_hit_rate_pct: { key: "cache_hit_rate_pct", label: "Cache Hit Rate", category: "Cache", scaleType: "percent", color: "#15803d" },
  cache_miss_rate_pct: { key: "cache_miss_rate_pct", label: "Cache Miss Rate", category: "Cache", scaleType: "percent", color: "#b91c1c" },
  exact_cache_hit_rate_pct: { key: "exact_cache_hit_rate_pct", label: "Exact Cache Hit Rate", category: "Cache", scaleType: "percent", color: "#1d4ed8" },
  semantic_cache_hit_rate_pct: { key: "semantic_cache_hit_rate_pct", label: "Semantic Cache Hit Rate", category: "Cache", scaleType: "percent", color: "#6d28d9" },
  p50_first_response_latency_ms: { key: "p50_first_response_latency_ms", label: "P50 First Response", category: "Latency", scaleType: "latency_ms", color: "#1e40af" },
  avg_first_response_latency_ms: { key: "avg_first_response_latency_ms", label: "Avg First Response", category: "Latency", scaleType: "latency_ms", color: "#1d4ed8" },
  p95_first_response_latency_ms: { key: "p95_first_response_latency_ms", label: "P95 First Response", category: "Latency", scaleType: "latency_ms", color: "#60a5fa" },
  p99_first_response_latency_ms: { key: "p99_first_response_latency_ms", label: "P99 First Response", category: "Latency", scaleType: "latency_ms", color: "#93c5fd" },
  p50_total_latency_ms: { key: "p50_total_latency_ms", label: "P50 Total Response", category: "Latency", scaleType: "latency_ms", color: "#115e59" },
  avg_total_latency_ms: { key: "avg_total_latency_ms", label: "Avg Total Response", category: "Latency", scaleType: "latency_ms", color: "#0f766e" },
  p95_total_latency_ms: { key: "p95_total_latency_ms", label: "P95 Total Response", category: "Latency", scaleType: "latency_ms", color: "#6ee7b7" },
  p99_total_latency_ms: { key: "p99_total_latency_ms", label: "P99 Total Response", category: "Latency", scaleType: "latency_ms", color: "#a7f3d0" },
  avg_input_tokens: { key: "avg_input_tokens", label: "Avg Input Tokens", category: "Tokens", scaleType: "tokens", color: "#7c3aed" },
  avg_output_tokens: { key: "avg_output_tokens", label: "Avg Output Tokens", category: "Tokens", scaleType: "tokens", color: "#ea580c" },
  avg_total_tokens: { key: "avg_total_tokens", label: "Avg Total Tokens", category: "Tokens", scaleType: "tokens", color: "#9333ea" },
  avg_output_tokens_per_second: { key: "avg_output_tokens_per_second", label: "Avg Output Tok/Sec", category: "Throughput", scaleType: "tokens_per_second", color: "#0891b2" },
  avg_cost_per_request: { key: "avg_cost_per_request", label: "Avg Cost / Request", category: "Cost", scaleType: "usd_per_request", color: "#16a34a" },
  input_cost_usd_total: { key: "input_cost_usd_total", label: "Input Cost Total", category: "Cost", scaleType: "usd_total", color: "#3b82f6", stackGroup: "cost_breakdown" },
  output_cost_usd_total: { key: "output_cost_usd_total", label: "Output Cost Total", category: "Cost", scaleType: "usd_total", color: "#22c55e", stackGroup: "cost_breakdown" },
  total_cost_usd: { key: "total_cost_usd", label: "Total Cost", category: "Cost", scaleType: "usd_total", color: "#15803d" },
  cost_per_1k_requests: { key: "cost_per_1k_requests", label: "Cost / 1K Requests", category: "Cost", scaleType: "usd_per_1k_requests", color: "#065f46" },
  first_response_sla_breach_rate_pct: { key: "first_response_sla_breach_rate_pct", label: "First Response SLA Breach", category: "SLA", scaleType: "percent", color: "#f59e0b" },
  total_response_sla_breach_rate_pct: { key: "total_response_sla_breach_rate_pct", label: "Total Response SLA Breach", category: "SLA", scaleType: "percent", color: "#ea580c" },
  cost_sla_breach_rate_pct: { key: "cost_sla_breach_rate_pct", label: "Cost SLA Breach", category: "SLA", scaleType: "percent", color: "#be123c" },
};

const llmTimeseriesMetricPresets = {
  latency: {
    label: "Latency",
    metrics: [
      "request_count",
      "p50_first_response_latency_ms",
      "avg_first_response_latency_ms",
      "p95_first_response_latency_ms",
      "p50_total_latency_ms",
      "p95_total_latency_ms",
      "p99_total_latency_ms",
    ],
  },
  reliability: {
    label: "Reliability",
    metrics: [
      "request_count",
      "error_rate_pct",
      "fallback_rate_pct",
      "provider_429_rate_pct",
      "stream_complete_rate_pct",
      "stream_partial_abort_rate_pct",
      "stream_prelude_failure_rate_pct",
    ],
  },
  cache: {
    label: "Cache",
    metrics: [
      "cache_hit_count",
      "cache_miss_count",
      "cache_bypass_count",
      "exact_cache_hit_count",
      "semantic_cache_hit_count",
      "cache_hit_rate_pct",
      "exact_cache_hit_rate_pct",
      "semantic_cache_hit_rate_pct",
    ],
  },
  finops: {
    label: "FinOps",
    metrics: [
      "request_count",
      "avg_input_tokens",
      "avg_output_tokens",
      "avg_cost_per_request",
      "input_cost_usd_total",
      "output_cost_usd_total",
      "total_cost_usd",
      "cost_per_1k_requests",
    ],
  },
  sla: {
    label: "SLA",
    metrics: [
      "p95_first_response_latency_ms",
      "p99_first_response_latency_ms",
      "p95_total_latency_ms",
      "p99_total_latency_ms",
      "first_response_sla_breach_rate_pct",
      "total_response_sla_breach_rate_pct",
      "cost_sla_breach_rate_pct",
    ],
  },
};

const llmTimeseriesScaleDefinitions = {
  count: {
    title: "Traffic Volume",
    emptyBody: "No request activity has been recorded for this vendor/model in the selected window.",
  },
  percent: {
    title: "Rates",
    emptyBody: "No routing or outcome rates have been recorded for this vendor/model in the selected window.",
    formatValue: (value) => `${Number(value).toFixed(1)}%`,
  },
  latency_ms: {
    title: "Latency",
    emptyBody: "No latency samples have been recorded for this vendor/model in the selected window.",
    unitSuffix: " ms",
  },
  tokens: {
    title: "Tokens Per Request",
    emptyBody: "No token usage has been recorded for this vendor/model in the selected window.",
  },
  tokens_per_second: {
    title: "Throughput",
    emptyBody: "No throughput samples have been recorded for this vendor/model in the selected window.",
    unitSuffix: " tok/s",
  },
  usd_per_request: {
    title: "Unit Cost",
    emptyBody: "No per-request cost has been recorded for this vendor/model in the selected window.",
    formatValue: (value) => `$${Number(value).toFixed(4)}`,
  },
  usd_total: {
    title: "Cost Volume",
    emptyBody: "No cost volume has been recorded for this vendor/model in the selected window.",
    formatValue: (value) => `$${Number(value).toFixed(4)}`,
  },
  usd_per_1k_requests: {
    title: "Normalized Cost",
    emptyBody: "No normalized cost data has been recorded for this vendor/model in the selected window.",
    formatValue: (value) => `$${Number(value).toFixed(2)}`,
  },
};

function defaultLlmTimeseriesMetrics() {
  return [
    "request_count",
    "error_rate_pct",
    "rate_limit_event_count",
    "fallback_rate_pct",
    "avg_first_response_latency_ms",
    "p95_total_latency_ms",
    "cache_hit_rate_pct",
    "stream_complete_rate_pct",
    "input_cost_usd_total",
    "output_cost_usd_total",
  ];
}

function activeLlmTimeseriesPresetName() {
  const field = $("#llm-timeseries-metric-preset");
  const candidate = String(field?.value || currentTableContext("#llm-timeseries-charts", "#llm-timeseries-filter-form").metric_preset || "").trim().toLowerCase();
  if (candidate && llmTimeseriesMetricPresets[candidate]) {
    return candidate;
  }
  return "";
}

function normalizeLlmTimeseriesMetricSelection(rawValue) {
  const rawItems = Array.isArray(rawValue)
    ? rawValue
    : String(rawValue || "").split(",");
  const seen = new Set();
  const valid = [];
  rawItems.forEach((item) => {
    const key = String(item || "").trim();
    if (!key || seen.has(key) || !llmTimeseriesMetricDefinitions[key]) return;
    seen.add(key);
    valid.push(key);
  });
  return valid.length ? valid : defaultLlmTimeseriesMetrics();
}

function selectedLlmTimeseriesMetrics() {
  const field = $("#llm-timeseries-metrics");
  return normalizeLlmTimeseriesMetricSelection(field?.value || currentTableContext("#llm-timeseries-charts", "#llm-timeseries-filter-form").metrics);
}

function persistLlmTimeseriesMetricSelection(metricKeys) {
  const normalized = normalizeLlmTimeseriesMetricSelection(metricKeys);
  const value = normalized.join(",");
  const field = $("#llm-timeseries-metrics");
  if (field) field.value = value;
  const context = collectFormFilters("#llm-timeseries-filter-form");
  context.metrics = value;
  rememberTableContext("#llm-timeseries-charts", context);
  return normalized;
}

function persistLlmTimeseriesPreset(presetName) {
  const normalized = String(presetName || "").trim().toLowerCase();
  const value = llmTimeseriesMetricPresets[normalized] ? normalized : "";
  const field = $("#llm-timeseries-metric-preset");
  if (field) field.value = value;
  const context = collectFormFilters("#llm-timeseries-filter-form");
  context.metric_preset = value;
  rememberTableContext("#llm-timeseries-charts", context);
  return value;
}

function renderLlmTimeseriesPresetPicker() {
  const host = $("#llm-timeseries-preset-picker");
  if (!host) return;
  const activePreset = activeLlmTimeseriesPresetName();
  host.innerHTML = `
    <section class="llm-timeseries-metric-group">
      <div class="llm-timeseries-metric-chip-list">
        ${Object.entries(llmTimeseriesMetricPresets).map(([key, preset]) => `
          <button
            class="llm-timeseries-metric-chip${activePreset === key ? " active" : ""}"
            type="button"
            data-timeseries-preset="${escapeHtml(key)}"
          >${escapeHtml(preset.label)}</button>
        `).join("")}
      </div>
    </section>
  `;
}

function renderLlmTimeseriesMetricPicker() {
  const host = $("#llm-timeseries-metric-picker");
  if (!host) return;
  const selected = new Set(selectedLlmTimeseriesMetrics());
  const groups = ["Traffic", "Routing", "Streaming", "Cache", "Latency", "Tokens", "Throughput", "Cost", "SLA"].map((category) => ({
    category,
    metrics: Object.values(llmTimeseriesMetricDefinitions).filter((definition) => definition.category === category),
  })).filter((group) => group.metrics.length);
  host.innerHTML = groups.map((group) => `
    <section class="llm-timeseries-metric-group">
      <h4>${escapeHtml(group.category)}</h4>
      <div class="llm-timeseries-metric-chip-list">
        ${group.metrics.map((definition) => `
          <button
            class="llm-timeseries-metric-chip${selected.has(definition.key) ? " active" : ""}"
            type="button"
            data-metric-key="${escapeHtml(definition.key)}"
          >${escapeHtml(definition.label)}</button>
        `).join("")}
      </div>
    </section>
  `).join("");
}

function renderLlmTimeseriesProviderOptions() {
  const providerSelect = $("#llm-timeseries-provider-key");
  const modelSelect = $("#llm-timeseries-model-id");
  if (!providerSelect || !modelSelect) return;
  const groups = readinessProviderModelOptions();
  const persisted = currentTableContext("#llm-timeseries-charts", "#llm-timeseries-filter-form");
  const preferredProvider = String(providerSelect.value || persisted.provider_key || groups[0]?.provider_key || "");
  providerSelect.innerHTML = groups.map((group) => (
    `<option value="${escapeHtml(group.provider_key)}"${group.provider_key === preferredProvider ? " selected" : ""}>${escapeHtml(group.provider_name)}</option>`
  )).join("");
  const selectedGroup = groups.find((group) => group.provider_key === String(providerSelect.value || preferredProvider)) || groups[0];
  const preferredModel = String(modelSelect.value || persisted.model_id || "");
  const availableModels = (selectedGroup?.models || []).map((model) => String(model.model_id || "")).filter(Boolean);
  modelSelect.innerHTML = [
    '<option value="">All discovered vendor models</option>',
    ...availableModels.map((modelId) => `<option value="${escapeHtml(modelId)}">${escapeHtml(modelId)}</option>`),
  ].join("");
  modelSelect.value = preferredModel && availableModels.includes(preferredModel) ? preferredModel : "";
  persistLlmTimeseriesPreset(persisted.metric_preset || $("#llm-timeseries-metric-preset")?.value || "");
  persistLlmTimeseriesMetricSelection(persisted.metrics || $("#llm-timeseries-metrics")?.value || "");
  renderLlmTimeseriesPresetPicker();
  renderLlmTimeseriesMetricPicker();
}

function renderLlmTimeseriesCharts(payload) {
  state.llmTimeseriesPayload = payload || null;
  const summary = payload?.summary || {};
  renderSummaryChips("#llm-timeseries-summary-strip", [
    { label: "Requests", value: String(payload?.request_count || 0) },
    { label: "Success Rate", value: summary.success_rate_pct != null ? `${formattedValue(summary.success_rate_pct)}%` : "—" },
    { label: "Error Rate", value: summary.error_rate_pct != null ? `${formattedValue(summary.error_rate_pct)}%` : "—" },
    { label: "Rate Limit Events", value: summary.rate_limit_event_count != null ? formattedValue(summary.rate_limit_event_count) : "—" },
    { label: "Provider 429s", value: summary.provider_429_count != null ? formattedValue(summary.provider_429_count) : "—" },
    { label: "Fallback Rate", value: summary.fallback_rate_pct != null ? `${formattedValue(summary.fallback_rate_pct)}%` : "—" },
    { label: "Redirect Rate", value: summary.redirect_rate_pct != null ? `${formattedValue(summary.redirect_rate_pct)}%` : "—" },
    { label: "Stream Completion", value: summary.stream_complete_rate_pct != null ? `${formattedValue(summary.stream_complete_rate_pct)}%` : "—" },
    { label: "Partial Aborts", value: summary.stream_partial_abort_count != null ? formattedValue(summary.stream_partial_abort_count) : "—" },
    { label: "Cache Hit Rate", value: summary.cache_hit_rate_pct != null ? `${formattedValue(summary.cache_hit_rate_pct)}%` : "—" },
    { label: "Exact Cache Hits", value: summary.exact_cache_hit_rate_pct != null ? `${formattedValue(summary.exact_cache_hit_rate_pct)}%` : "—" },
    { label: "Avg First Response", value: summary.avg_first_response_latency_ms != null ? `${formattedValue(summary.avg_first_response_latency_ms)} ms` : "—" },
    { label: "P95 First Response", value: summary.p95_first_response_latency_ms != null ? `${formattedValue(summary.p95_first_response_latency_ms)} ms` : "—" },
    { label: "Avg Total Response", value: summary.avg_total_latency_ms != null ? `${formattedValue(summary.avg_total_latency_ms)} ms` : "—" },
    { label: "P95 Total Response", value: summary.p95_total_latency_ms != null ? `${formattedValue(summary.p95_total_latency_ms)} ms` : "—" },
    { label: "P99 Total Response", value: summary.p99_total_latency_ms != null ? `${formattedValue(summary.p99_total_latency_ms)} ms` : "—" },
    { label: "First SLA Breach", value: summary.first_response_sla_breach_rate_pct != null ? `${formattedValue(summary.first_response_sla_breach_rate_pct)}%` : "—" },
    { label: "Total Cost", value: summary.total_cost_usd != null ? `$${Number(summary.total_cost_usd).toFixed(4)}` : "—" },
    { label: "Avg Cost", value: summary.avg_cost_per_request != null ? `$${Number(summary.avg_cost_per_request).toFixed(4)}` : "—" },
  ]);
  renderLlmTimeseriesChartGroups(payload);
  renderLlmTimeseriesLeaderboards(payload);
}

async function openLlmTimeseriesBucketContext(bucketRow) {
  if (!bucketRow?.bucket_start) return;
  const filters = collectFormFilters("#llm-timeseries-filter-form");
  const bucketMinutes = Number(filters.bucket_minutes || state.llmTimeseriesPayload?.bucket_minutes || 60) || 60;
  const bucketStart = new Date(bucketRow.bucket_start);
  const bucketEnd = new Date(bucketStart.getTime() + bucketMinutes * 60 * 1000);
  await openRequestHistoryContext({
    listener_id: "",
    session_id: "",
    traffic_origin: "",
    automation_scope: "",
    selected_pool_id: "",
    selected_node_id: "",
    domain: "",
    task_type: "",
    selected_provider: filters.provider_key || state.llmTimeseriesPayload?.provider_key || "",
    selected_model: filters.model_id || state.llmTimeseriesPayload?.model_id || "",
    created_after: bucketStart.toISOString(),
    created_before: bucketEnd.toISOString(),
  });
  showToast(`Opened traffic for ${bucketStart.toLocaleString()} bucket.`, "info");
}

function renderLlmTimeseriesChartGroups(payload) {
  const host = $("#llm-timeseries-chart-grid");
  if (!host) return;
  host.innerHTML = "";
  const rows = Array.isArray(payload?.series) ? payload.series : [];
  const selectedMetrics = selectedLlmTimeseriesMetrics();
  if (!selectedMetrics.length) {
    host.appendChild(buildEmptyState({
      icon: "≈",
      title: "No time series selected.",
      body: "Choose at least one metric to plot for the selected vendor and model window.",
    }));
    return;
  }
  const groupedMetrics = new Map();
  selectedMetrics.forEach((key) => {
    const definition = llmTimeseriesMetricDefinitions[key];
    if (!definition) return;
    if (!groupedMetrics.has(definition.scaleType)) {
      groupedMetrics.set(definition.scaleType, []);
    }
    groupedMetrics.get(definition.scaleType).push(definition);
  });
  const appendChartCard = (definitions, scaleType, options = {}) => {
    if (!definitions.length) return;
    const scaleConfig = llmTimeseriesScaleDefinitions[scaleType] || {};
    const card = document.createElement("section");
    card.className = "llm-timeseries-card";
    card.innerHTML = `
      <h4>${escapeHtml(options.title || scaleConfig.title || "Time Series")}</h4>
      <p class="card-subtitle compact-bottom">${escapeHtml(options.subtitle || definitions.map((definition) => definition.label).join(" • "))}</p>
    `;
    const chartHost = document.createElement("div");
    chartHost.className = "llm-timeseries-chart";
    card.appendChild(chartHost);
    host.appendChild(card);
    renderSparklineTimeseriesHost(chartHost, rows, {
      unitSuffix: scaleConfig.unitSuffix,
      formatValue: scaleConfig.formatValue,
      emptyBody: scaleConfig.emptyBody,
      stacked: Boolean(options.stacked),
      onBucketSelect: (row) => {
        void openLlmTimeseriesBucketContext(row);
      },
      seriesDefinitions: definitions.map((definition) => ({
        key: definition.key,
        label: definition.label,
        color: definition.color,
      })),
    });
  };
  groupedMetrics.forEach((definitions, scaleType) => {
    const stackedDefinitions = definitions.filter((definition) => definition.stackGroup === "cost_breakdown");
    const lineDefinitions = definitions.filter((definition) => definition.stackGroup !== "cost_breakdown");
    if (stackedDefinitions.length) {
      appendChartCard(stackedDefinitions, scaleType, {
        stacked: true,
        title: "Cost Breakdown",
        subtitle: stackedDefinitions.map((definition) => definition.label).join(" • "),
      });
    }
    appendChartCard(lineDefinitions, scaleType);
  });
}

function loadLlmTimeseriesModel(modelId) {
  setFieldValue("#llm-timeseries-filter-form", "model_id", modelId || "");
  rememberTableContext("#llm-timeseries-charts", collectFormFilters("#llm-timeseries-filter-form"));
  return refreshLlmTimeseries();
}

function renderLlmTimeseriesLeaderboard(selector, rows, emptyMessage, title) {
  renderSimpleTable(
    selector,
    title,
    ["Model", "Requests", "First Response", "Total Response", "Cost", "Actions"],
    rows,
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${renderIdChip(row.model_id, { truncate: false })}</td>
        <td><strong>${escapeHtml(formattedValue(row.request_count))}</strong></td>
        <td>${row.avg_first_response_latency_ms != null ? `<strong>${escapeHtml(formattedValue(row.avg_first_response_latency_ms))} ms</strong>${row.p95_first_response_latency_ms != null ? `<br/><span>P95 ${escapeHtml(formattedValue(row.p95_first_response_latency_ms))} ms</span>` : ""}` : '<span class="empty-value">-</span>'}</td>
        <td>${row.avg_total_latency_ms != null ? `<strong>${escapeHtml(formattedValue(row.avg_total_latency_ms))} ms</strong>${row.p95_total_latency_ms != null ? `<br/><span>P95 ${escapeHtml(formattedValue(row.p95_total_latency_ms))} ms</span>` : ""}` : '<span class="empty-value">-</span>'}</td>
        <td>${row.avg_cost_per_request != null ? `$${escapeHtml(Number(row.avg_cost_per_request).toFixed(4))}` : '<span class="empty-value">-</span>'}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Load Trends", async () => {
        await loadLlmTimeseriesModel(row.model_id);
      }, { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    },
    emptyMessage,
    { itemLabel: "models" },
  );
}

function renderLlmTimeseriesLeaderboards(payload) {
  const models = Array.isArray(payload?.model_rollups) ? payload.model_rollups : [];
  const busiest = [...models]
    .sort((a, b) => (Number(b.request_count || 0) - Number(a.request_count || 0)) || String(a.model_id || "").localeCompare(String(b.model_id || "")))
    .slice(0, 8);
  const slowest = [...models]
    .filter((row) => row.p95_total_latency_ms != null || row.avg_total_latency_ms != null)
    .sort((a, b) => {
      const left = Number(b.p95_total_latency_ms ?? b.avg_total_latency_ms ?? 0);
      const right = Number(a.p95_total_latency_ms ?? a.avg_total_latency_ms ?? 0);
      return left - right || String(a.model_id || "").localeCompare(String(b.model_id || ""));
    })
    .slice(0, 8);
  renderLlmTimeseriesLeaderboard(
    "#llm-timeseries-busiest-models",
    busiest,
    "No model request activity recorded for this vendor in the selected window.",
    null,
  );
  renderLlmTimeseriesLeaderboard(
    "#llm-timeseries-slowest-models",
    slowest,
    "No model latency samples recorded for this vendor in the selected window.",
    null,
  );
}

function resetModelMonitorEditor() {
  state.selectedModelMonitorId = null;
  setFieldValue("#model-monitor-form", "monitor_id", "");
  setFieldValue("#model-monitor-form", "label", "");
  setFieldValue("#model-monitor-form", "frequency_minutes", "60");
  setFieldValue("#model-monitor-form", "prompt", "Respond with OK.");
  setFieldValue("#model-monitor-form", "monitor_mode", "frontdoor_stream");
  const enabled = $("#model-monitor-enabled");
  if (enabled) enabled.checked = true;
  renderStreamingValidationListenerOptions("#model-monitor-listener-id");
  renderModelMonitorProviderOptions();
}

async function refreshLlmTimeseries() {
  const hostSelectors = [
    "#llm-timeseries-chart-grid",
    "#llm-timeseries-busiest-models",
    "#llm-timeseries-slowest-models",
  ];
  hostSelectors.forEach((selector) => {
    const host = $(selector);
    if (!host) return;
    host.innerHTML = "";
    host.appendChild(buildLoadingState({
      title: "Loading time series…",
      body: "Aggregating stored selected-response telemetry for the selected vendor and model.",
    }));
  });
  const filters = rememberTableContext("#llm-timeseries-charts", currentTableContext("#llm-timeseries-charts", "#llm-timeseries-filter-form"));
  if (!filters.provider_key) {
    renderSummaryChips("#llm-timeseries-summary-strip", []);
    hostSelectors.forEach((selector) => {
      const host = $(selector);
      if (!host) return;
      host.innerHTML = "";
      host.appendChild(buildEmptyState({
        icon: "≈",
        title: "No vendor selected.",
        body: "Choose a vendor from readiness to load request, routing, latency, token, throughput, and cost trends.",
      }));
    });
    return null;
  }
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value == null || value === "") return;
    params.set(key, value);
  });
  const payload = await apiFetch(`/admin/api/ops/llm-timeseries?${params.toString()}`);
  renderLlmTimeseriesCharts(payload);
  return payload;
}

function inspectModelMonitor(row) {
  state.selectedModelMonitorId = row?.monitor_id || null;
  setFieldValue("#model-monitor-form", "monitor_id", row?.monitor_id || "");
  setFieldValue("#model-monitor-form", "label", row?.label || "");
  setFieldValue("#model-monitor-form", "provider_key", row?.provider_key || "");
  renderModelMonitorProviderOptions();
  setFieldValue("#model-monitor-form", "model_id", row?.model_id || "");
  setFieldValue("#model-monitor-form", "frequency_minutes", String(row?.frequency_minutes || 60));
  setFieldValue("#model-monitor-form", "monitor_mode", row?.monitor_mode || "frontdoor_stream");
  renderStreamingValidationListenerOptions("#model-monitor-listener-id");
  setFieldValue("#model-monitor-form", "listener_id", row?.listener_id || "");
  setFieldValue("#model-monitor-form", "prompt", row?.prompt || "Respond with OK.");
  const enabled = $("#model-monitor-enabled");
  if (enabled) enabled.checked = Boolean(row?.enabled);
  setActiveRuntimeRow("#model-monitors-table", row?.monitor_id || "");
}

function renderModelMonitorsTable(rows) {
  const host = $("#model-monitors-table");
  if (!host) return;
  host.innerHTML = "";
  host.appendChild(
    makeTable(
      ["Model", "Mode", "Frequency", "Status", "Last Checked", "Next Due", "Actions"],
      rows,
      (row) => {
        const tr = document.createElement("tr");
        tr.dataset.recordId = row.monitor_id;
        if (String(row.monitor_id) === String(state.selectedModelMonitorId || "")) {
          tr.classList.add("active-row");
        }
        tr.addEventListener("click", (event) => {
          if (event.target.closest("button")) return;
          inspectModelMonitor(row);
        });
        tr.innerHTML = `
          <td><strong>${escapeHtml(row.label || row.model_id)}</strong><div class="table-subtext">${escapeHtml(`${row.provider_key}:${row.model_id}`)}</div></td>
          <td>${escapeHtml(humanizeLabel(String(row.monitor_mode || "").replaceAll("_", " ")))}</td>
          <td>${escapeHtml(`${formattedValue(row.frequency_minutes)} min`)}</td>
          <td>${row.last_status === "never_checked" ? '<span class="badge badge-muted">Never Checked</span>' : statusBadge(row.last_success ? "healthy" : "unavailable")}</td>
          <td>${escapeHtml(row.last_checked_at ? formattedValue(row.last_checked_at) : "-")}</td>
          <td>${escapeHtml(row.due_at ? formattedValue(row.due_at) : "Now")}</td>
          <td></td>
        `;
        const actions = document.createElement("div");
        actions.className = "table-actions";
        actions.appendChild(createActionButton("Run Now", async () => {
          const result = await apiFetch(`/admin/api/ops/model-monitors/${encodeURIComponent(row.monitor_id)}/run`, {
            method: "POST",
          });
          showToast(`Ran monitor for ${row.label || row.model_id}.`, result?.result?.success ? "ok" : "warn");
          await refreshModelMonitors();
          inspectModelMonitor(
            (state.modelMonitorPayload?.monitors || []).find((item) => item.monitor_id === row.monitor_id) || row,
          );
        }, { accent: true }));
        tr.lastElementChild.appendChild(actions);
        return tr;
      },
      "No periodic model monitors are configured yet.",
      { pageKey: "#model-monitors-table", pageSize: 10, itemLabel: "monitors" },
    ),
  );
}

async function refreshModelMonitors() {
  setTableLoading("#model-monitors-table", {
    title: "Loading model monitors…",
    body: "Fetching selected periodic LLM monitor definitions and their last results.",
  });
  const payload = await apiFetch("/admin/api/ops/model-monitors");
  state.modelMonitorPayload = payload;
  renderModelMonitorsTable(payload.monitors || []);
  const selected = currentModelMonitor();
  if (selected) {
    inspectModelMonitor(selected);
  } else if (!(payload.monitors || []).length) {
    resetModelMonitorEditor();
  }
  return payload;
}

function replaceModelMonitorPayload(rows) {
  state.modelMonitorPayload = {
    ...(state.modelMonitorPayload || {}),
    monitor_count: Array.isArray(rows) ? rows.length : 0,
    enabled_count: Array.isArray(rows) ? rows.filter((row) => row.enabled).length : 0,
    due_count: Array.isArray(rows) ? rows.filter((row) => row.due_now).length : 0,
    monitors: Array.isArray(rows) ? rows : [],
  };
  renderModelMonitorsTable(state.modelMonitorPayload.monitors);
}

function modelMonitorFormPayload() {
  const form = $("#model-monitor-form");
  const data = new FormData(form);
  return {
    monitor_id: String(data.get("monitor_id") || "").trim() || null,
    label: String(data.get("label") || "").trim() || null,
    provider_key: String(data.get("provider_key") || "").trim(),
    model_id: String(data.get("model_id") || "").trim(),
    enabled: Boolean($("#model-monitor-enabled")?.checked),
    frequency_minutes: Number(data.get("frequency_minutes") || 60),
    monitor_mode: String(data.get("monitor_mode") || "frontdoor_stream"),
    listener_id: String(data.get("listener_id") || "").trim() || null,
    prompt: String(data.get("prompt") || "").trim() || null,
  };
}

function renderFoundationProviderTree(selector, groups) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  const entries = Array.isArray(groups) ? groups : [];
  if (!entries.length) {
    host.appendChild(buildEmptyState({
      icon: "↳",
      title: "No vendor providers available.",
      body: "Refresh the provider directory once readiness, streaming support, and routing state are loaded.",
    }));
    return;
  }

  const pageState = getPaginatedRows(entries, { pageKey: selector, pageSize: 12 });
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr>
      <th>Vendor</th>
      <th>Configured</th>
      <th>Status</th>
      <th>Models</th>
      <th>Streaming</th>
      <th>Explicit Route</th>
    </tr>
  `;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  pageState.pageRows.forEach((group) => {
    const providerKey = buildFoundationProviderKey(group);
    const providerRow = document.createElement("tr");
    providerRow.dataset.recordId = providerKey;
    providerRow.className = "foundation-provider-row";
    if (state.selectedFoundationProviderKey === providerKey) {
      providerRow.classList.add("active-row");
    }
    providerRow.addEventListener("click", () => {
      inspectFoundationProvider(group);
      toggleFoundationProviderExpanded(providerKey, true);
      renderFoundationProviderTree(selector, state.foundationProviderGroups);
    });

    const expanded = foundationProviderExpanded(providerKey);
    providerRow.innerHTML = `
      <td>
        <div class="foundation-tree-cell">
          <button class="tree-toggle" type="button" aria-expanded="${expanded ? "true" : "false"}" aria-label="${expanded ? "Collapse" : "Expand"} ${escapeHtml(humanizeLabel(group.provider_name || group.provider_key || "vendor"))}">
            <span class="tree-toggle-icon">${expanded ? "▾" : "▸"}</span>
          </button>
          <div>
            <span class="cell-primary">${escapeHtml(humanizeLabel(group.provider_name || group.provider_key || "-"))}</span>
            <span class="cell-secondary">${escapeHtml(String(group.provider_family || group.provider_key || ""))}</span>
          </div>
        </div>
      </td>
      <td>${boolBadge(Boolean(group.configured))}</td>
      <td>${statusBadge(group.status || "-")}</td>
      <td><span class="num">${escapeHtml(`${formattedValue(group.healthy_model_count)}/${formattedValue(group.model_count)}`)}</span></td>
      <td><span class="num">${escapeHtml(`${formattedValue(group.streaming_model_count)}/${formattedValue(group.model_count)}`)}</span></td>
      <td><span class="num">${escapeHtml(`${formattedValue(group.routed_model_count)}/${formattedValue(group.model_count)}`)}</span></td>
    `;
    providerRow.querySelector(".tree-toggle")?.addEventListener("click", (event) => {
      event.stopPropagation();
      toggleFoundationProviderExpanded(providerKey);
      renderFoundationProviderTree(selector, state.foundationProviderGroups);
    });
    tbody.appendChild(providerRow);

    if (expanded) {
      const modelRow = document.createElement("tr");
      modelRow.className = "foundation-model-row-wrap";
      const modelCell = document.createElement("td");
      modelCell.colSpan = 6;
      const inner = document.createElement("div");
      inner.className = "foundation-model-list";
      const models = Array.isArray(group.models) ? group.models : [];
      inner.appendChild(
        makeTable(
          ["Model", "Ready", "Streaming", "Exposed", "Explicit Route", "Policy Modes"],
          models,
          (row) => {
            const tr = document.createElement("tr");
            const modelKey = buildFoundationModelKey(providerKey, row.model_id);
            tr.dataset.recordId = modelKey;
            if (state.selectedFoundationModelKey === modelKey) {
              tr.classList.add("active-row");
            }
            tr.addEventListener("click", (event) => {
              event.stopPropagation();
              inspectFoundationModel(group, row);
              renderFoundationProviderTree(selector, state.foundationProviderGroups);
            });
            tr.innerHTML = `
              <td><strong>${escapeHtml(row.model_id || "-")}</strong></td>
              <td>${statusBadge(row.status || "-")}</td>
              <td>${boolBadge(Boolean(row.streaming_supported))}</td>
              <td>${boolBadge(Boolean(row.exposed))}</td>
              <td>${boolBadge(Boolean(row.routed))}</td>
              <td>${escapeHtml((row.routing_modes || []).join(", ") || "-")}</td>
            `;
            return tr;
          },
          "No models discovered for this vendor.",
        ),
      );
      modelCell.appendChild(inner);
      modelRow.appendChild(modelCell);
      tbody.appendChild(modelRow);
    }
  });
  table.appendChild(tbody);
  host.appendChild(table);
  if (pageState.totalPages > 1) {
    host.appendChild(buildTablePaginationControls(pageState, {
      pageKey: selector,
      itemLabel: "vendors",
      onChange: () => renderFoundationProviderTree(selector, groups),
    }));
  }
}

function formattedValue(value) {
  if (value == null || value === "") return "-";
  if (Array.isArray(value)) return value.join(", ") || "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderAmount(value, { currency = "$", precision = 2, zeroMuted = true } = {}) {
  if (value == null || value === "") return '<span class="amount empty-value">-</span>';
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return escapeHtml(String(value));
  const formatted = numeric.toLocaleString(undefined, { minimumFractionDigits: precision, maximumFractionDigits: precision });
  const zeroClass = zeroMuted && numeric === 0 ? " zero" : "";
  return `<span class="amount${zeroClass}"><span class="currency-symbol">${escapeHtml(currency)}</span>${escapeHtml(formatted)}</span>`;
}

function renderIdChip(value, { truncate = true } = {}) {
  if (!value) return '<span class="amount empty-value">-</span>';
  return `<span class="id-chip${truncate ? " truncate" : ""}" title="${escapeHtml(String(value))}">${escapeHtml(String(value))}</span>`;
}

function renderList(values, { emptyLabel = "None configured", limit = 8 } = {}) {
  const items = (Array.isArray(values) ? values : [values]).filter((item) => item != null && item !== "");
  if (!items.length) return `<span class="empty-value">${escapeHtml(emptyLabel)}</span>`;
  const shown = items.slice(0, limit).map((item) => `<span class="badge badge-muted">${escapeHtml(String(item))}</span>`);
  if (items.length > limit) shown.push(`<span class="badge badge-muted">+${items.length - limit} more</span>`);
  return shown.join("");
}

/**
 * Renders a record as a labeled definition-list ("commercial" detail view) instead
 * of a raw JSON dump. `fields` is an array of either field-key strings or
 * `{ key, label, render(value, record), hideEmpty }` descriptors; `render` receives
 * the raw value and may return trusted HTML (badges, amounts, id chips, etc).
 * The original payload remains available behind a collapsed "View raw JSON" disclosure
 * so operators who need the wire format never lose it — they just stop needing it by default.
 */
function renderRecordView(selector, record, fields, options = {}) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  const hasRecord = record && (Array.isArray(record) ? record.length : Object.keys(record).length);
  if (!hasRecord) {
    host.appendChild(buildEmptyState(options.emptyState || {
      title: "Nothing to show yet.",
      body: "Details will appear here once a record is selected.",
    }));
    return;
  }
  const dl = document.createElement("dl");
  dl.className = "record-view";
  fields.forEach((field) => {
    const descriptor = typeof field === "string" ? { key: field } : field;
    const key = descriptor.key;
    const value = descriptor.value ? descriptor.value(record) : record?.[key];
    if (descriptor.hideEmpty && (value == null || value === "" || (Array.isArray(value) && !value.length))) return;
    const dt = document.createElement("dt");
    dt.textContent = descriptor.label || humanizeLabel(key);
    const dd = document.createElement("dd");
    if (descriptor.render) {
      dd.innerHTML = descriptor.render(value, record);
    } else if (value == null || value === "") {
      dd.innerHTML = '<span class="empty-value">Not set</span>';
    } else {
      dd.textContent = formattedValue(value);
    }
    dl.appendChild(dt);
    dl.appendChild(dd);
  });
  host.appendChild(dl);
  if (options.raw !== false) {
    host.appendChild(renderRawDisclosure(record, options.rawLabel));
  }
}

function renderRawDisclosure(payload, label = "View raw JSON") {
  const details = document.createElement("details");
  details.className = "raw-disclosure";
  const summary = document.createElement("summary");
  summary.textContent = label;
  const pre = document.createElement("pre");
  pre.className = "output compact";
  pre.textContent = JSON.stringify(payload, null, 2);
  details.appendChild(summary);
  details.appendChild(pre);
  return details;
}

const REQUEST_RECORD_FIELDS = [
  { key: "id", label: "Request ID", render: (value) => renderIdChip(value) },
  { key: "traffic_origin", label: "Traffic Origin", render: (value) => `<span class="badge badge-info">${escapeHtml(humanizeLabel(value || "interactive"))}</span>` },
  { key: "automation_scope", label: "Pipeline Scope", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
  { key: "automation_owner_id", label: "Pipeline Owner", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "domain", label: "Domain", render: (value) => `<span class="badge badge-info">${escapeHtml(value || "-")}</span>` },
  { key: "task_type", label: "Task Type", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(value)}</span>` },
  { key: "requested_model", label: "Requested Model", render: (value) => renderIdChip(value, { truncate: false }) },
  {
    key: "prompt_template_name",
    label: "Prompt Template",
    hideEmpty: true,
    render: (_value, row) => renderPromptTemplateUsage(row),
  },
  {
    key: "prompt_template_selection_mode",
    label: "Prompt Rollout",
    hideEmpty: true,
    render: (_value, row) => renderPromptSelectionModeBadge(row.prompt_template_selection_mode, row.prompt_template_rollout_percentage),
  },
  { key: "listener_id", label: "Inbound Listener", hideEmpty: true, render: (value, row) => `${renderIdChip(value, { truncate: false })}${row.listener_port ? `<br/><span>${escapeHtml(formattedValue(row.listener_host || "-"))}:${escapeHtml(formattedValue(row.listener_port))}</span>` : ""}` },
  { key: "successful", label: "Outcome", render: (value) => (value ? '<span class="badge badge-ok">Successful</span>' : '<span class="badge badge-err">Failed</span>') },
  { key: "session_id", label: "Session", hideEmpty: true, render: (value) => renderIdChip(value) },
  { key: "route_type", label: "Route Type", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "quality_score", label: "Quality Score", render: (value) => (value == null ? '<span class="empty-value">Not scored</span>' : `<span class="num">${escapeHtml(formattedValue(value))}</span>`) },
  { key: "cost_estimate", label: "Cost Estimate", render: (value) => (value == null ? '<span class="empty-value">-</span>' : renderAmount(value, { precision: 4 })) },
  { key: "created_at", label: "Created", render: (value) => timeLabel(value) },
];

function renderPromptSelectionModeBadge(selectionMode, rolloutPercentage = null) {
  const normalized = String(selectionMode || "").trim().toLowerCase();
  if (!normalized) {
    return '<span class="empty-value">No rollout metadata</span>';
  }
  if (normalized === "challenger_canary") {
    return `<span class="badge badge-info">Challenger Canary${rolloutPercentage != null ? ` ${escapeHtml(formattedValue(rolloutPercentage))}%` : ""}</span>`;
  }
  if (normalized === "active") {
    return '<span class="badge badge-ok">Active</span>';
  }
  if (normalized === "explicit") {
    return '<span class="badge badge-muted">Explicit Version</span>';
  }
  return `<span class="badge badge-muted">${escapeHtml(humanizeLabel(normalized))}</span>`;
}

function renderPromptTemplateUsage(row) {
  if (!row?.prompt_template_name) {
    return '<span class="empty-value">No prompt template</span>';
  }
  return `<strong>${escapeHtml(row.prompt_template_name)}</strong>${row.prompt_template_version ? ` · v${escapeHtml(formattedValue(row.prompt_template_version))}` : ""}${row.prompt_template_render_hash ? `<br/><span>${escapeHtml(row.prompt_template_render_hash)}</span>` : ""}`;
}


function normalizeFallbackChain(chain = []) {
  return Array.isArray(chain) ? chain : [];
}


function renderFallbackChainTable(host, title, rows, { includeDecision = false, emptyLabel } = {}) {
  const normalizedRows = Array.isArray(rows) ? rows : [];
  renderSimpleTable(
    host,
    title,
    includeDecision
      ? ["Route", "Step", "Provider", "Model", "Pool", "Node", "Strategy"]
      : ["Step", "Provider", "Model", "Pool", "Node", "Strategy"],
    normalizedRows,
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        ${includeDecision ? `<td>${row.route_label ? escapeHtml(row.route_label) : '<span class="empty-value">Route</span>'}</td>` : ""}
        <td><span class="badge badge-muted">${escapeHtml(formattedValue(row.order))}</span></td>
        <td><strong>${escapeHtml(row.provider || "-")}</strong>${row.provider_family ? `<br/><span>${escapeHtml(humanizeLabel(row.provider_family))}</span>` : ""}</td>
        <td>${escapeHtml(row.model || "-")}</td>
        <td>${row.pool_id ? renderIdChip(row.pool_id, { truncate: false }) : '<span class="empty-value">Direct</span>'}</td>
        <td>${row.node_id ? `${renderIdChip(row.node_id, { truncate: false })}${row.node_role ? `<br/><span>${escapeHtml(humanizeLabel(row.node_role))}</span>` : ""}` : '<span class="empty-value">Direct</span>'}</td>
        <td>${row.balancing_strategy ? `<span class="badge badge-info">${escapeHtml(humanizeLabel(row.balancing_strategy))}</span>${row.affinity_key ? `<br/><span>${escapeHtml(humanizeLabel(row.affinity_key))}</span>` : ""}` : '<span class="empty-value">Provider fallback</span>'}</td>
      `;
      return tr;
    },
    emptyLabel,
  );
}

function renderInteractionTraceTable(host, rows, emptyLabel = "No interaction traces recorded for this request.") {
  renderSimpleTable(
    host,
    "Interaction Traces",
    ["Protocol", "Operation", "Target", "Outcome", "Parent"],
    rows || [],
    (row) => {
      const tr = document.createElement("tr");
      let target = `${row.provider || "-"} / ${row.model || "-"}`;
      if (row.protocol === "mcp") {
        target = `${row.server || "-"} / ${row.tool_name || "-"}`;
      } else if (row.protocol === "a2a") {
        target = `${row.peer || "-"} / ${row.capability || row.operation || "-"}`;
      } else if (row.protocol === "rest") {
        target = `${row.method || "HTTP"} ${row.endpoint || "-"}`;
      }
      tr.innerHTML = `
        <td><span class="badge badge-info">${escapeHtml(String(row.protocol || "unknown").toUpperCase())}</span></td>
        <td>${escapeHtml(row.operation || "-")}</td>
        <td>${escapeHtml(target)}</td>
        <td>${boolBadge(Boolean(row.success))}</td>
        <td>${row.parent_trace_id ? renderIdChip(row.parent_trace_id) : '<span class="empty-value">Root</span>'}</td>
      `;
      return tr;
    },
    emptyLabel,
  );
}

function renderRequestDetail(payload) {
  const request = payload?.request || {};
  const interactionProtocols = payload?.interaction_protocols || {};
  renderMetricGrid("#request-detail-summary-grid", [
    { label: "Request", value: request.id || "-" },
    { label: "Domain", value: request.domain || "-", subvalue: request.task_type || "No task type" },
    { label: "Model", value: request.requested_model || "-" },
    { label: "Listener", value: request.listener_id || "-", subvalue: request.listener_port ? `${request.listener_host || "-"}:${request.listener_port}` : "Default listener" },
    { label: "Origin", value: humanizeLabel(request.traffic_origin || "interactive"), subvalue: request.automation_scope ? humanizeLabel(request.automation_scope) : "Direct traffic" },
    { label: "Virtual Key", value: request.virtual_key_id || "-", subvalue: request.virtual_key_role ? humanizeLabel(request.virtual_key_role) : "No scoped key" },
    { label: "Candidates", value: String((payload?.training_candidates || []).length) },
    { label: "Responses", value: String((payload?.model_responses || []).length) },
    { label: "Trace Protocols", value: String(Object.keys(interactionProtocols).length), subvalue: Object.keys(interactionProtocols).join(", ") || "LLM only" },
  ]);
  renderRecordView("#request-detail-summary-table", request, REQUEST_RECORD_FIELDS, {
    rawLabel: "View raw request record",
    emptyState: { title: "No request selected.", body: "Choose a request from the history table to see its full detail here." },
  });
  renderSimpleTable(
    "#request-routing-table",
    "Routing Decisions",
    ["Provider", "Model", "Mode", "Pool", "Node", "Strategy", "Why"],
    payload?.routing_decisions || [],
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.selected_provider || "-")}</strong></td>
        <td>${escapeHtml(row.selected_model || "-")}</td>
        <td>${escapeHtml(row.selected_mode || "-")}</td>
        <td>${row.selected_pool_id ? renderIdChip(row.selected_pool_id, { truncate: false }) : '<span class="empty-value">Direct</span>'}</td>
        <td>${row.selected_node_id ? `${renderIdChip(row.selected_node_id, { truncate: false })}${row.selected_node_role ? `<br/><span>${escapeHtml(humanizeLabel(row.selected_node_role))}</span>` : ""}` : '<span class="empty-value">Direct</span>'}</td>
        <td>${row.selected_balancing_strategy ? `<span class="badge badge-muted">${escapeHtml(humanizeLabel(row.selected_balancing_strategy))}</span>${row.selected_affinity_key ? `<br/><span>${escapeHtml(humanizeLabel(row.selected_affinity_key))}</span>` : ""}` : `<span class="empty-value">${escapeHtml(formattedValue(row.predicted_latency_class))}</span>`}</td>
        <td>${escapeHtml(row.decision_rationale || "-")}</td>
      `;
      return tr;
    },
    "No routing decisions recorded for this request.",
  );
  const fallbackRows = (payload?.routing_decisions || []).flatMap((row, index) =>
    normalizeFallbackChain(row.fallback_chain || row.fallback_chain_json).map((item) => ({
      route_label: (payload?.routing_decisions || []).length > 1 ? `Route ${index + 1}` : "Primary route",
      order: item.order,
      provider: item.provider,
      provider_family: item.provider_family,
      model: item.model,
      pool_id: item.pool_id,
      node_id: item.node_id,
      node_role: item.node_role,
      balancing_strategy: item.balancing_strategy,
      affinity_key: item.affinity_key,
    })),
  );
  renderFallbackChainTable("#request-fallback-table", "Fallback Order", fallbackRows, {
    includeDecision: (payload?.routing_decisions || []).length > 1,
    emptyLabel: "No fallback chain recorded for this request.",
  });
  renderSimpleTable(
    "#request-responses-table",
    "Model Responses",
    ["Model", "Success", "Latency", "Cost", "Created"],
    payload?.model_responses || [],
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.model || "-")}</strong></td>
        <td>${boolBadge(!row.finish_reason || row.finish_reason !== "error")}</td>
        <td>${escapeHtml(formattedValue(row.latency_ms))}</td>
        <td>${escapeHtml(formattedValue(row.cost_estimate))}</td>
        <td>${escapeHtml(formattedValue(row.created_at))}</td>
      `;
      return tr;
    },
    "No model responses recorded for this request.",
  );
  renderSimpleTable(
    "#request-candidates-table",
    "Training Candidates",
    ["Candidate", "Domain", "Task", "Quality", "Eligible"],
    payload?.training_candidates || [],
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.id || "-")}</strong></td>
        <td>${escapeHtml(row.domain || "-")}</td>
        <td>${escapeHtml(row.task_type || "-")}</td>
        <td>${escapeHtml(formattedValue(row.quality_score))}</td>
        <td>${boolBadge(Boolean(row.export_eligible))}</td>
      `;
      return tr;
    },
    "No training candidates were created from this request.",
  );
  renderSimpleTable(
    "#request-performance-table",
    "Performance Samples",
    ["Model", "Domain", "Score", "Cost", "Created"],
    payload?.performance_samples || [],
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.model_alias || "-")}</strong></td>
        <td>${escapeHtml(row.domain || "-")}</td>
        <td>${escapeHtml(formattedValue(row.quality_score))}</td>
        <td>${escapeHtml(formattedValue(row.cost_estimate))}</td>
        <td>${escapeHtml(formattedValue(row.created_at))}</td>
      `;
      return tr;
    },
    "No performance samples were recorded for this request.",
  );
  renderSimpleTable(
    "#request-judge-table",
    "Judge Critiques",
    ["Judge", "Selected Model", "Selected Provider", "Created"],
    payload?.judge_critiques || [],
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.judge_model || "-")}</strong></td>
        <td>${escapeHtml(row.selected_model || "-")}</td>
        <td>${escapeHtml(row.selected_provider || "-")}</td>
        <td>${escapeHtml(formattedValue(row.created_at))}</td>
      `;
      return tr;
    },
    "No judge critiques were recorded for this request.",
  );
  renderInteractionTraceTable(
    "#request-interaction-trace-table",
    payload?.interaction_traces || [],
    "No normalized interaction traces recorded for this request.",
  );
}

function renderPipelineTrafficTables(prefix, payload) {
  const summary = payload?.pipeline_traffic || null;
  renderRecordView(`${prefix}-summary-table`, summary, [
    { key: "scope", label: "Scope", render: (value) => `<span class="badge badge-info">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
    { key: "traffic_origin", label: "Traffic Origin", render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
    { key: "request_count", label: "Proxy Requests", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
    { key: "response_count", label: "Model Responses", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
    { key: "virtual_key_count", label: "Scoped Keys", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
    { key: "total_virtual_key_spend_usd", label: "Tracked Spend", render: (value) => renderAmount(value, { precision: 4 }) },
    { key: "total_response_cost_usd", label: "Response Cost", render: (value) => renderAmount(value, { precision: 4 }) },
    { key: "response_cost_gap_usd", label: "Non-Response Cost Gap", render: (value) => renderAmount(value, { precision: 4 }) },
    { key: "total_input_tokens", label: "Input Tokens", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
    { key: "total_output_tokens", label: "Output Tokens", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
    { key: "last_request_at", label: "Last Request", render: (value) => timeLabel(value) },
  ], {
    rawLabel: "View raw pipeline traffic summary",
    emptyState: {
      title: "No pipeline traffic recorded.",
      body: "This run has not yet created any proxy-attributed learning traffic.",
    },
  });
  renderSimpleTable(
    `${prefix}-keys-table`,
    "Scoped Virtual Keys",
    ["Key", "Role", "Status", "Spend", "Last Used"],
    summary?.virtual_keys || [],
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.key_prefix || "-")}</strong><br/><span>${escapeHtml(row.id || "-")}</span></td>
        <td>${escapeHtml(humanizeLabel(row.role || "-"))}</td>
        <td>${statusBadge(row.status || "-")}</td>
        <td>${renderAmount(row.spend_usd, { precision: 4 })}</td>
        <td>${timeLabel(row.last_used_at || row.created_at)}</td>
      `;
      return tr;
    },
    "No scoped virtual keys have been issued for this run.",
  );
  renderSimpleTable(
    `${prefix}-requests-table`,
    "Recent Proxy Requests",
    ["Request", "Origin", "Route", "Topology", "Created"],
    summary?.recent_requests || [],
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.id || "-")}</strong><br/><span>${escapeHtml(row.virtual_key_id || row.session_id || "-")}</span>${row.prompt_template_name ? `<br/><span>Prompt ${escapeHtml(row.prompt_template_name)}${row.prompt_template_version ? ` · v${escapeHtml(formattedValue(row.prompt_template_version))}` : ""}</span><br/>${renderPromptSelectionModeBadge(row.prompt_template_selection_mode, row.prompt_template_rollout_percentage)}` : ""}</td>
        <td>${escapeHtml(humanizeLabel(row.automation_scope || row.traffic_origin || "-"))}</td>
        <td><strong>${escapeHtml(row.selected_provider || row.requested_model || "-")}</strong><br/><span>${escapeHtml(row.selected_model || row.requested_model || "-")}</span></td>
        <td>${row.selected_pool_id ? `${renderIdChip(row.selected_pool_id, { truncate: false })}<br/>` : ""}${row.selected_node_id ? `${renderIdChip(row.selected_node_id, { truncate: false })}` : '<span class="empty-value">Direct</span>'}${row.selected_balancing_strategy ? `<br/><span>${escapeHtml(humanizeLabel(row.selected_balancing_strategy))}</span>` : ""}</td>
        <td>${timeLabel(row.created_at)}</td>
      `;
      return tr;
    },
    "No proxy requests have been attributed to this run yet.",
  );
}

function renderTrainingDetail(payload) {
  const progress = payload?.metrics_json?.progress || null;
  renderRecordView("#training-detail-summary-table", payload, [
    { key: "id", label: "Run", render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "status", label: "Status", render: (value) => statusBadge(value || "-") },
    { key: "training_mode", label: "Mode", render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
    { key: "trainer_backend", label: "Backend", render: (value) => `<span class="badge badge-info">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
    { key: "base_model", label: "Base Model", render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "dataset_version_id", label: "Dataset Version", render: (value) => renderIdChip(value) },
    { key: "progress_stage", label: "Progress", render: () => progress ? `<span class="badge badge-info">${escapeHtml(humanizeLabel(progress.stage || "reported"))}</span>` : '<span class="empty-value">No progress reported</span>' },
    { key: "artifact_path", label: "Artifact Path", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "started_at", label: "Started", render: (value) => timeLabel(value) },
    { key: "completed_at", label: "Completed", render: (value) => timeLabel(value) },
  ], {
    rawLabel: "View raw training run record",
    emptyState: {
      title: "No training run selected.",
      body: "Pick a run from the worklist to inspect its status, config, and metrics here.",
    },
  });
  renderKeyValueTable(
    "#training-progress-table",
    progress ? Object.entries(progress).map(([key, value]) => ({ key: humanizeLabel(key), value: formattedValue(value) })) : [],
    { emptyMessage: "No live progress events recorded yet." },
  );
  renderKeyValueTable(
    "#training-config-table",
    Object.entries(payload?.training_config_json || {}).map(([key, value]) => ({ key: humanizeLabel(key), value: formattedValue(value) })),
    { emptyMessage: "No training configuration recorded." },
  );
  renderKeyValueTable(
    "#training-metrics-table",
    Object.entries(payload?.metrics_json || {}).map(([key, value]) => ({ key: humanizeLabel(key), value: formattedValue(value) })),
    { emptyMessage: "No training metrics recorded yet." },
  );
  renderPipelineTrafficTables("#training-traffic", payload);
}

function renderTrainingPreflight(payload) {
  const host = $("#training-preflight-output");
  if (!host) return;
  host.innerHTML = "";
  if (!payload || !Object.keys(payload).length) {
    host.appendChild(buildEmptyState({
      title: "No preflight run yet.",
      body: "Run training preflight to validate dataset splits and backend configuration before queueing a training job.",
    }));
    return;
  }
  const summary = document.createElement("div");
  host.appendChild(summary);
  summary.id = "training-preflight-summary";
  renderRecordView("#training-preflight-summary", payload, [
    { key: "dataset_version_id", label: "Dataset Version", render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "base_model", label: "Base Model", render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "training_mode", label: "Mode", render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
    { key: "trainer_backend", label: "Backend", render: (value) => `<span class="badge badge-info">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
    { key: "ready", label: "Ready", render: (value) => statusBadge(value ? "ready" : "blocked") },
    { key: "errors", label: "Errors", render: (value) => renderList(value || [], { emptyLabel: "None" }) },
    { key: "warnings", label: "Warnings", render: (value) => renderList(value || [], { emptyLabel: "None" }) },
  ], { rawLabel: "View raw preflight result" });
  host.appendChild(makeTable(["Split", "Records"], [
    { split: "Train", records: formattedValue(payload?.record_counts?.train) },
    { split: "Validation", records: formattedValue(payload?.record_counts?.validation) },
    { split: "Test", records: formattedValue(payload?.record_counts?.test) },
  ], (row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><strong>${escapeHtml(row.split)}</strong></td><td>${escapeHtml(row.records)}</td>`;
    return tr;
  }, "No preflight counts recorded."));
  host.appendChild(
    makeTable(["Check", "Status", "Detail"], payload.checks || [], (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(humanizeLabel(row.name || "-"))}</strong></td>
        <td>${statusBadge(row.status || "-")}</td>
        <td>${escapeHtml(row.detail || "-")}</td>
      `;
      return tr;
    }, "No preflight checks recorded."),
  );
  if (payload.worker_runtime_status) {
    const runtimeHeading = document.createElement("h4");
    runtimeHeading.textContent = "Worker Runtime Snapshot";
    host.appendChild(runtimeHeading);
    host.appendChild(
      makeTable(
        ["Field", "Value"],
        [
          { field: "Reported", value: payload.worker_runtime_status.reported_at ? relativeTime(payload.worker_runtime_status.reported_at) : "Not reported" },
          { field: "Ready", value: payload.worker_runtime_status.ready ? "Ready" : "Blocked" },
          { field: "Backend Imports", value: payload.worker_runtime_status.backend_import_ready ? "Ready" : "Blocked" },
          { field: "CUDA", value: payload.worker_runtime_status.cuda_available ? "Available" : "Unavailable" },
          { field: "Device Count", value: formattedValue(payload.worker_runtime_status.device_count) },
          { field: "Torch", value: payload.worker_runtime_status.torch_version || "-" },
          { field: "Unsloth", value: payload.worker_runtime_status.unsloth_version || "-" },
          { field: "Proxy Base URL", value: payload.worker_runtime_status.internal_api_base_url || "-" },
        ],
        (row) => {
          const tr = document.createElement("tr");
          tr.innerHTML = `<td><strong>${escapeHtml(row.field)}</strong></td><td>${escapeHtml(row.value)}</td>`;
          return tr;
        },
        "No worker runtime detail reported.",
      ),
    );
    if ((payload.worker_runtime_status.dependencies || []).length) {
      host.appendChild(
        makeTable(["Dependency", "Available", "Detail"], payload.worker_runtime_status.dependencies || [], (row) => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td><strong>${escapeHtml(row.name || "-")}</strong></td>
            <td>${boolBadge(Boolean(row.available))}</td>
            <td>${escapeHtml(row.detail || "-")}</td>
          `;
          return tr;
        }, "No runtime dependency status reported."),
      );
    }
  }
}

function renderEvaluationDetail(payload) {
  renderRecordView("#evaluation-detail-summary-table", payload, [
    { key: "id", label: "Evaluation", render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "status", label: "Status", render: (value) => statusBadge(value || "-") },
    { key: "promotion_status", label: "Promotion", render: (value) => statusBadge(value || "-") },
    { key: "domain", label: "Domain", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
    { key: "training_run_id", label: "Training Run", render: (value) => renderIdChip(value) },
    { key: "frontier_baseline_name", label: "Frontier Baseline", hideEmpty: true },
    { key: "overall_score", label: "Overall Score", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
    { key: "value_per_dollar_gain_vs_frontier", label: "Value Gain", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
    { key: "quality_delta_vs_frontier", label: "Quality Delta", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
    { key: "created_at", label: "Created", render: (value) => timeLabel(value) },
  ], {
    rawLabel: "View raw evaluation record",
    emptyState: {
      title: "No evaluation selected.",
      body: "Pick an evaluation from the worklist to inspect its promotion outcome and result payload here.",
    },
  });
  renderKeyValueTable(
    "#evaluation-result-table",
    Object.entries(payload?.result_json || {}).map(([key, value]) => ({ key: humanizeLabel(key), value: formattedValue(value) })),
    { emptyMessage: "No evaluation result payload recorded." },
  );
  renderPipelineTrafficTables("#evaluation-traffic", payload);
}

function renderJobDetail(payload) {
  if (!payload || !Object.keys(payload).length) {
    renderRecordView("#job-detail-summary-table", null, [], {
      raw: false,
      emptyState: {
        title: "No job selected.",
        body: "Pick a row from the jobs worklist to inspect attempts, timing, and payload.",
      },
    });
    renderRecordView("#job-payload-table", null, [], {
      raw: false,
      emptyState: {
        title: "No payload yet.",
        body: "The selected job's payload fields will appear here.",
      },
    });
    return;
  }
  renderRecordView("#job-detail-summary-table", payload, [
    { key: "id", label: "Job", render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "status", label: "Status", render: (value) => statusBadge(value || "-") },
    { key: "job_type", label: "Type" },
    { key: "attempts", label: "Attempts", value: (record) => `${record?.attempts ?? 0}/${record?.max_attempts ?? 0}` },
    { key: "available_at", label: "Available" },
    { key: "claimed_at", label: "Claimed" },
    { key: "completed_at", label: "Completed" },
    { key: "created_at", label: "Created" },
    { key: "last_error", label: "Last Error" },
  ], {
    rawLabel: "View raw job record",
  });
  renderRecordView("#job-payload-table", payload?.payload || null, Object.keys(payload?.payload || {}).map((key) => ({
    key,
    label: humanizeLabel(key),
  })), {
    raw: false,
    emptyState: {
      title: "No payload recorded.",
      body: "This job did not store a structured payload.",
    },
  });
}

function renderEventDetail(payload) {
  if (!payload || !Object.keys(payload).length) {
    renderRecordView("#event-detail-summary-table", null, [], {
      raw: false,
      emptyState: {
        title: "No event selected.",
        body: "Pick a row from the events worklist to inspect source, processing state, and payload.",
      },
    });
    renderRecordView("#event-payload-table", null, [], {
      raw: false,
      emptyState: {
        title: "No payload yet.",
        body: "The selected event's payload fields will appear here.",
      },
    });
    renderInteractionTraceTable(
      "#event-interaction-trace-table",
      [],
      "No normalized interaction traces were recorded for this event.",
    );
    return;
  }
  renderRecordView("#event-detail-summary-table", payload, [
    { key: "id", label: "Event", render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "event_type", label: "Type" },
    { key: "source", label: "Source" },
    { key: "processed_at", label: "Processed", render: (value) => value ? statusBadge("processed") : statusBadge("pending") },
    { key: "occurred_at", label: "Occurred" },
    { key: "processed_at", label: "Processed At" },
    { key: "event_id", label: "Event Id" },
  ], {
    rawLabel: "View raw event record",
  });
  renderRecordView("#event-payload-table", payload?.payload_json || null, Object.keys(payload?.payload_json || {}).map((key) => ({
    key,
    label: humanizeLabel(key),
  })), {
    raw: false,
    emptyState: {
      title: "No payload recorded.",
      body: "This event did not store a structured payload.",
    },
  });
  renderInteractionTraceTable(
    "#event-interaction-trace-table",
    payload?.payload_json?.interaction_traces || [],
    "No normalized interaction traces were recorded for this event.",
  );
}

function setOperationsInspectorMode(mode = "event") {
  const opsCard = $("#ops-detail-card");
  const requestCard = $("#request-detail-card");
  if (mode === "request") {
    opsCard?.classList.add("hidden");
    requestCard?.classList.remove("hidden");
    return;
  }
  requestCard?.classList.add("hidden");
  opsCard?.classList.remove("hidden");
}

function renderOpsRecordDetail(payload) {
  state.selectedOpsRecord = payload && Object.keys(payload).length ? payload : null;
  setOperationsInspectorMode("event");
  if (!payload || !Object.keys(payload).length) {
    renderRecordView("#ops-detail-summary-table", null, [], {
      raw: false,
      emptyState: {
        title: "No signal selected.",
        body: "Inspect an operational event, job signal, or runtime event from the unified directory to see it here.",
      },
    });
    return;
  }
  renderRecordView("#ops-detail-summary-table", payload, [
    { key: "event_class", label: "Event Class", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
    { key: "timestamp", label: "Timestamp" },
    { key: "level", label: "Level", render: (value) => statusBadge(value || "info") },
    { key: "component", label: "Component" },
    { key: "category", label: "Category" },
    {
      key: "listener",
      label: "Inbound Listener",
      value: (record) => record?.data?.listener_id || record?.data?.metadata?.listener_id,
      hideEmpty: true,
      render: (value) => renderIdChip(value, { truncate: false }),
    },
    { key: "training_opportunity", label: "Training Opportunity", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
    { key: "message", label: "Message" },
    {
      key: "data",
      label: "Payload",
      render: (value) => value == null
        ? '<span class="empty-value">No structured payload</span>'
        : `<pre class="value-pre">${escapeHtml(JSON.stringify(value, null, 2))}</pre>`,
    },
  ], {
    rawLabel: "View raw signal record",
  });
}

const ROUTE_COMPARISON_RECORD_FIELDS = [
  { key: "provider", label: "Provider: Preview → Actual", value: (c) => `${formattedValue(c.preview?.selected_provider)} -> ${formattedValue(c.actualDecision?.selected_provider)}` },
  { key: "model", label: "Model: Preview → Actual", value: (c) => `${formattedValue(c.preview?.decision?.selected_model)} -> ${formattedValue(c.actualDecision?.selected_model)}` },
  { key: "mode", label: "Mode: Preview → Actual", value: (c) => `${formattedValue(c.preview?.decision?.selected_mode)} -> ${formattedValue(c.actualDecision?.selected_mode)}` },
  { key: "pool", label: "Pool: Preview → Actual", value: (c) => `${formattedValue(c.preview?.decision?.selected_pool_id)} -> ${formattedValue(c.actualDecision?.selected_pool_id)}` },
  { key: "node", label: "Node: Preview → Actual", value: (c) => `${formattedValue(c.preview?.decision?.selected_node_id)} -> ${formattedValue(c.actualDecision?.selected_node_id)}` },
  { key: "strategy", label: "Strategy: Preview → Actual", value: (c) => `${formattedValue(c.preview?.decision?.selected_balancing_strategy)} -> ${formattedValue(c.actualDecision?.selected_balancing_strategy)}` },
  { key: "preview_domain", label: "Preview Domain", value: (c) => c.preview?.classification?.domain, hideEmpty: true },
  { key: "actual_request_id", label: "Actual Request", value: (c) => c.actualDetail?.request?.id, render: (value) => renderIdChip(value) },
];

function renderRouteComparison(actualDetail) {
  const preview = state.lastRoutePreview;
  const actualDecision = actualDetail?.routing_decisions?.[0] || {};
  const comparable = preview && actualDetail ? { preview, actualDecision, actualDetail } : null;
  renderRecordView("#route-comparison-table", comparable, ROUTE_COMPARISON_RECORD_FIELDS, {
    raw: false,
    emptyState: {
      title: "No route comparison available yet.",
      body: "Generate a route preview, then send a chat request with the same session — the predicted route and what actually happened will line up here.",
    },
  });
}

const MODEL_INFO_FIELDS = [
  { key: "id", label: "Model ID", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "object", label: "Object Type", render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value || "model"))}</span>` },
];

function renderModelInfoDetail(model, selector = "#model-detail-summary-table") {
  renderRecordView(selector, model, MODEL_INFO_FIELDS, {
    rawLabel: "View raw model record",
    emptyState: {
      title: "No model selected.",
      body: "Choose a vendor model from the directory above to inspect it. For routing configuration, look up the matching entry in the Routing Policies table.",
    },
  });
}

const FOUNDATION_PROVIDER_FIELDS = [
  { key: "provider_name", label: "Provider", render: (value) => `<span class="cell-primary">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
  { key: "provider_key", label: "Provider Key", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "configured", label: "Configured", render: (value) => boolBadge(Boolean(value)) },
  { key: "status", label: "Overall Status", render: (value) => statusBadge(value || "-") },
  { key: "model_count", label: "Models", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "healthy_model_count", label: "Healthy Models", render: (value, row) => `<span class="num">${escapeHtml(`${formattedValue(value)}/${formattedValue(row.model_count)}`)}</span>` },
  { key: "streaming_model_count", label: "Streaming Models", render: (value, row) => `<span class="num">${escapeHtml(`${formattedValue(value)}/${formattedValue(row.model_count)}`)}</span>` },
  { key: "routed_model_count", label: "Routed Models", render: (value, row) => `<span class="num">${escapeHtml(`${formattedValue(value)}/${formattedValue(row.model_count)}`)}</span>` },
  { key: "note", label: "Notes", hideEmpty: true },
];

const FOUNDATION_MODEL_FIELDS = [
  { key: "model_id", label: "Model", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "status", label: "Readiness", render: (value) => statusBadge(value || "-") },
  { key: "latency_ms", label: "Latency", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))} ms</span>` },
  { key: "streaming_supported", label: "Streaming", render: (value) => boolBadge(Boolean(value)) },
  { key: "exposed", label: "Exposed", render: (value) => boolBadge(Boolean(value)) },
  { key: "routed", label: "In Routing", render: (value) => boolBadge(Boolean(value)) },
  { key: "routing_modes", label: "Routing Modes", render: (value) => renderList(value, { emptyLabel: "Not in routing policy" }) },
  { key: "source", label: "Readiness Source", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value || "-"))}</span>` },
  { key: "domains", label: "Domains", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "All domains" }) },
  { key: "regions", label: "Regions", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "All regions" }) },
  { key: "note", label: "Notes", hideEmpty: true },
];

function renderFoundationModelDetail(model) {
  renderRecordView("#provider-model-detail", model, FOUNDATION_MODEL_FIELDS, {
    rawLabel: "View raw selected model record",
    emptyState: {
      title: "No model selected.",
      body: "Choose a vendor model row under the selected provider to inspect its readiness, streaming support, and routing participation.",
    },
  });
}

function populateFrontierPolicyForm(entry = {}) {
  setFieldValue("#frontier-policy-form", "entry_id", entry.entry_id || "");
  setFieldValue("#frontier-policy-form", "provider_key", entry.provider_key || "");
  setFieldValue("#frontier-policy-form", "model_id", entry.model_id || "");
  setFieldValue("#frontier-policy-form", "requested_models", (entry.requested_models || []).join(","));
  setFieldValue("#frontier-policy-form", "domains", (entry.domains || []).join(","));
  setFieldValue("#frontier-policy-form", "task_types", (entry.task_types || []).join(","));
  setFieldValue("#frontier-policy-form", "tags", (entry.tags || []).join(","));
  setFieldValue("#frontier-policy-form", "labels", (entry.labels || []).join(","));
  setFieldValue("#frontier-policy-form", "regions", (entry.regions || []).join(","));
  setFieldValue("#frontier-policy-form", "listener_ids", (entry.listener_ids || []).join(","));
  setFieldValue("#frontier-policy-form", "deployment_mode", entry.deployment_mode || "production");
  setFieldValue("#frontier-policy-form", "canary_percent", String(entry.canary_percent ?? 0));
  setFieldValue("#frontier-policy-form", "endpoint_url", entry.endpoint_url || "");
  setFieldValue("#frontier-policy-form", "node_id", entry.node_id || "");
  setFieldValue("#frontier-policy-form", "node_role", entry.node_role || "");
  setFieldValue("#frontier-policy-form", "capacity_class", entry.capacity_class || "");
  setFieldValue("#frontier-policy-form", "node_labels", (entry.node_labels || []).join(","));
  setFieldValue("#frontier-policy-form", "pool_id", entry.pool_id || "");
  setFieldValue("#frontier-policy-form", "pool_weight", String(entry.pool_weight ?? 1));
  setFieldValue("#frontier-policy-form", "balancing_strategy", entry.balancing_strategy || "");
  setFieldValue("#frontier-policy-form", "affinity_key", entry.affinity_key || "");
  setFieldValue("#frontier-policy-form", "supports_local_models", Boolean(entry.supports_local_models));
  setFieldValue("#frontier-policy-form", "supports_training", Boolean(entry.supports_training));
  setFieldValue("#frontier-policy-form", "forward_request_metadata", Boolean(entry.forward_request_metadata));
  setFieldValue("#frontier-policy-form", "fallback_chain", (entry.fallback_chain || []).map((item) => `${item.provider}:${item.model}`).join(","));
  setFieldValue("#frontier-policy-form", "decision_rationale", entry.decision_rationale || "");
}

async function openFoundationProviderGuide() {
  const provider = currentSelectedFoundationProvider();
  if (!provider) {
    showToast("Select a vendor provider first.", "warn");
    return;
  }
  switchPanel("integrations");
  switchCollection("integrations", "providers");
  await ensurePanelLoaded("integrations", true);
  const match = (state.providerGuides || []).find((row) => row.provider_key === provider.provider_key);
  if (match) {
    inspectProviderGuide(match);
    showToast(`Opened provider guide for ${humanizeLabel(provider.provider_name || provider.provider_key)}.`, "ok");
    return;
  }
  showToast(`No provider guide exists for ${provider.provider_key}.`, "warn");
}

async function openProviderGuideVendorContext() {
  const providerKey = state.selectedProviderGuideKey;
  if (!providerKey) {
    showToast("Select a provider guide first.", "warn");
    return;
  }
  switchPanel("models");
  switchSubview("models", "catalog");
  switchCollection("modelCatalog", "proxy");
  await ensurePanelLoaded("models", true);
  const match = (state.foundationProviderGroups || []).find((row) => row.provider_key === providerKey);
  if (match) {
    inspectFoundationProvider(match);
    showToast(`Opened vendor workspace for ${humanizeLabel(match.provider_name || match.provider_key)}.`, "ok");
    return;
  }
  showToast(`Vendor ${providerKey} is not present in the canonical directory yet.`, "warn");
}

async function openConnectivityVendorContext(group) {
  if (!group?.provider_key) {
    showToast("No vendor selected from connectivity snapshot.", "warn");
    return;
  }
  switchPanel("models");
  switchSubview("models", "catalog");
  switchCollection("modelCatalog", "proxy");
  await ensurePanelLoaded("models", true);
  const match = (state.foundationProviderGroups || []).find((row) => row.provider_key === group.provider_key);
  if (match) {
    inspectFoundationProvider(match);
    showToast(`Opened vendor workspace for ${humanizeLabel(match.provider_name || match.provider_key)}.`, "ok");
    return;
  }
  showToast(`Vendor ${group.provider_key} is not present in the canonical directory yet.`, "warn");
}

async function openFoundationRoutingContext() {
  const provider = currentSelectedFoundationProvider();
  const model = currentSelectedFoundationModel();
  if (!provider) {
    showToast("Select a vendor provider first.", "warn");
    return;
  }
  switchPanel("models");
  switchSubview("models", "routing");
  state.routingPolicyScopedOnly = true;
  const scopedToggle = $("#routing-policy-scoped-only");
  if (scopedToggle) scopedToggle.checked = true;
  await ensurePanelLoaded("models", true);
  const matchingRows = (state.policyRows || []).filter((row) => {
    if (row.provider !== provider.provider_key) return false;
    if (model) {
      return row.model === model.model_id;
    }
    return true;
  });
  if (matchingRows.length) {
    const target = matchingRows[0];
    inspectPolicyRow(target);
    showToast(
      model
        ? `Opened routing context for ${model.model_id}.`
        : `Opened routing context for ${humanizeLabel(provider.provider_name || provider.provider_key)}.`,
      "ok",
    );
    return;
  }
  populateFrontierPolicyForm({
    provider_key: provider.provider_key,
    model_id: model?.model_id || "",
    deployment_mode: "production",
  });
  state.selectedPolicyRowKey = null;
  setActiveRuntimeRow("#policies-table", "");
  renderOutput("#frontier-policy-output", {
    note: "No existing routing entry matched the selected vendor model. The frontier policy form has been prefilled to create one.",
    provider_key: provider.provider_key,
    model_id: model?.model_id || null,
  });
  showToast("No matching routing entry found. Prefilled a new frontier entry instead.", "info");
}

async function openFoundationStreamingValidation() {
  const provider = currentSelectedFoundationProvider();
  const model = currentSelectedFoundationModel();
  if (!provider) {
    showToast("Select a vendor provider first.", "warn");
    return;
  }
  switchPanel("proxy");
  switchSubview("proxy", "streaming");
  await ensurePanelLoaded("proxy", true);
  const rows = state.streamingSupportPayload?.providers || [];
  const match = rows.find((row) => row.provider_key === provider.provider_key && (!model || row.model_id === model.model_id))
    || rows.find((row) => row.provider_key === provider.provider_key)
    || null;
  if (match) {
    if (!match.configured) {
      state.streamingSupportConfiguredOnly = false;
      const configuredToggle = $("#streaming-target-configured-only");
      if (configuredToggle) configuredToggle.checked = false;
    }
    if (!match.supports_streaming) {
      state.streamingSupportStreamableOnly = false;
      const streamableToggle = $("#streaming-target-streamable-only");
      if (streamableToggle) streamableToggle.checked = false;
    }
    await refreshStreamingSupport();
    inspectStreamingSupportRow(match);
  } else {
    setFieldValue("#streaming-validate-form", "provider_key", provider.provider_key || "");
  }
  showToast(
    model
      ? `Prepared stream validation for ${model.model_id}.`
      : `Prepared stream validation for ${humanizeLabel(provider.provider_name || provider.provider_key)}.`,
    "ok",
  );
}

function graphArtifactLabel(kind) {
  return ({
    listener: "Listener Scope",
    policy: "Routing Policy",
    pool: "Pool",
    node: "Node",
    target: "Target",
    service: "Service",
    package: "Package",
    deployment: "Deployment",
    runtime: "Runtime",
    route: "Live Route",
    protocol: "Protocol Surface",
    endpoint: "Endpoint",
    key: "Virtual Key",
    scope: "Model Scope",
    pricing: "Pricing",
    guardrail: "Guardrail Policy",
  }[kind] || humanizeLabel(kind || "artifact"));
}

const GRAPH_EDGE_RECORD_FIELDS = [
  { key: "path", label: "Path" },
  { key: "from_label", label: "From Type" },
  { key: "from_title", label: "From" },
  { key: "to_label", label: "To Type" },
  { key: "to_title", label: "To" },
  { key: "detail", label: "Meaning", hideEmpty: true },
];

const GRAPH_ARTIFACT_RECORD_FIELDS = [
  { key: "type", label: "Type" },
  { key: "title", label: "Artifact" },
  { key: "subtitle", label: "Summary" },
  { key: "collection", label: "Collection", hideEmpty: true },
  { key: "detail", label: "Meaning", hideEmpty: true },
];

async function openRuntimeHostingContext(runtimeName) {
  if (!runtimeName) {
    showToast("No runtime selected.", "warn");
    return;
  }
  switchPanel("models");
  switchSubview("models", "register");
  switchCollection("modelRegister", "runtime");
  await ensurePanelLoaded("models", true);
  const match = (state.localRuntimeRows || []).find((row) => String(row.runtime || "") === String(runtimeName));
  if (match) {
    await selectLocalRuntime(runtimeName);
    showToast(`Opened runtime hosting context for ${runtimeName}.`, "ok");
    return;
  }
  showToast(`Runtime ${runtimeName} is not present in local runtime inventory.`, "warn");
}

async function openLocalDeploymentRoutingContext(modelAlias) {
  if (!modelAlias) {
    showToast("No deployment selected.", "warn");
    return;
  }
  switchPanel("models");
  switchSubview("models", "routing");
  await ensurePanelLoaded("models", true);
  const match = (state.policyRows || []).find((row) => row.entry_type === "local" && row.model === modelAlias);
  if (match) {
    inspectPolicyRow(match);
    showToast(`Opened routing entry for ${modelAlias}.`, "ok");
    return;
  }
  showToast(`No active local routing entry exists for ${modelAlias}.`, "warn");
}

function inspectFoundationProvider(group) {
  const providerKey = buildFoundationProviderKey(group);
  state.selectedFoundationProviderKey = providerKey;
  state.selectedFoundationModelKey = null;
  toggleFoundationProviderExpanded(providerKey, true);
  setActiveRuntimeRow("#models-table", providerKey);
  renderFoundationProviderTree("#models-table", state.foundationProviderGroups);
  renderRecordView("#model-detail-summary-table", group, FOUNDATION_PROVIDER_FIELDS, {
    rawLabel: "View raw provider record",
    emptyState: {
      title: "No provider selected.",
      body: "Choose a provider from the directory to inspect its models and operational facets.",
    },
  });
  const modelRows = Array.isArray(group?.models) ? group.models : [];
  const host = $("#provider-model-table");
  if (host) {
    host.innerHTML = "";
    host.appendChild(
      makeTable(["Model", "Ready", "Streaming", "Exposed", "Explicit Route", "Policy Modes"], modelRows, (row) => {
        const tr = document.createElement("tr");
        const modelKey = buildFoundationModelKey(providerKey, row.model_id);
        tr.dataset.recordId = modelKey;
        tr.addEventListener("click", () => inspectFoundationModel(group, row));
        if (state.selectedFoundationModelKey === modelKey) {
          tr.classList.add("active-row");
        }
        tr.innerHTML = `
          <td><strong>${escapeHtml(row.model_id || "-")}</strong></td>
          <td>${statusBadge(row.status || "-")}</td>
          <td>${boolBadge(Boolean(row.streaming_supported))}</td>
          <td>${boolBadge(Boolean(row.exposed))}</td>
          <td>${boolBadge(Boolean(row.routed))}</td>
          <td>${escapeHtml((row.routing_modes || []).join(", ") || "-")}</td>
        `;
        return tr;
      }, "No models are associated with this provider yet."),
    );
  }
  renderFoundationModelDetail({});
}

function inspectFoundationModel(group, model) {
  const providerKey = buildFoundationProviderKey(group);
  state.selectedFoundationProviderKey = providerKey;
  state.selectedFoundationModelKey = buildFoundationModelKey(providerKey, model?.model_id);
  toggleFoundationProviderExpanded(providerKey, true);
  renderFoundationProviderTree("#models-table", state.foundationProviderGroups);
  setActiveRuntimeRow("#provider-model-table", state.selectedFoundationModelKey);
  renderRecordView("#model-detail-summary-table", group, FOUNDATION_PROVIDER_FIELDS, {
    rawLabel: "View raw provider record",
    emptyState: {
      title: "No provider selected.",
      body: "Choose a provider from the directory to inspect its models and operational facets.",
    },
  });
  const selectedProvider = currentSelectedFoundationProvider();
  if (selectedProvider) {
    const host = $("#provider-model-table");
    if (host) {
      host.innerHTML = "";
      host.appendChild(
        makeTable(["Model", "Ready", "Streaming", "Exposed", "Explicit Route", "Policy Modes"], selectedProvider.models || [], (row) => {
          const tr = document.createElement("tr");
          const modelKey = buildFoundationModelKey(providerKey, row.model_id);
          tr.dataset.recordId = modelKey;
          tr.addEventListener("click", () => inspectFoundationModel(selectedProvider, row));
          if (state.selectedFoundationModelKey === modelKey) {
            tr.classList.add("active-row");
          }
          tr.innerHTML = `
            <td><strong>${escapeHtml(row.model_id || "-")}</strong></td>
            <td>${statusBadge(row.status || "-")}</td>
            <td>${boolBadge(Boolean(row.streaming_supported))}</td>
            <td>${boolBadge(Boolean(row.exposed))}</td>
            <td>${boolBadge(Boolean(row.routed))}</td>
            <td>${escapeHtml((row.routing_modes || []).join(", ") || "-")}</td>
          `;
          return tr;
        }, "No models are associated with this provider yet."),
      );
    }
  }
  renderFoundationModelDetail(model);
}

function inspectPolicyRow(row) {
  state.selectedPolicyRowKey = buildPolicyRowKey(row);
  setActiveRuntimeRow("#policies-table", state.selectedPolicyRowKey);
  setText("#model-routing-detail-heading", "Selected Routing Record");
  showDetailCard("#model-detail-card", null, row.detail);
  renderRoutingRelatedEntries([row], "No routing entry selected.");
  if (row.detail?.entry?.entry_type === "frontier") {
    populateFrontierPolicyForm(row.detail.entry);
    renderOutput("#frontier-policy-output", row.detail);
  }
}

function filteredPolicyRows(rows) {
  const query = String(state.routingPolicyQuery || "").trim().toLowerCase();
  const selectedProvider = currentSelectedFoundationProvider();
  const selectedModel = currentSelectedFoundationModel();
  return (rows || []).filter((row) => {
    if (state.routingPolicyScopedOnly && selectedProvider) {
      if (row.provider !== selectedProvider.provider_key) {
        return false;
      }
      if (selectedModel && row.model !== selectedModel.model_id) {
        return false;
      }
    }
    if (!query) {
      return true;
    }
    const haystack = [
      row.policy_version,
      row.entry_type,
      row.domains,
      row.tags,
      row.regions,
      row.mode,
      row.provider,
      row.model,
    ].map((value) => String(value || "").toLowerCase()).join(" ");
    return haystack.includes(query);
  });
}

function renderRoutingScopeBanner() {
  const host = $("#routing-scope-banner");
  if (!host) return;
  host.classList.toggle("hidden", state.activeModelRoutingCollection !== "entries");
  if (state.activeModelRoutingCollection !== "entries") return;
  const selectedProvider = currentSelectedFoundationProvider();
  const selectedModel = currentSelectedFoundationModel();
  if (state.routingPolicyScopedOnly && selectedProvider) {
    host.innerHTML = selectedModel
      ? `Scoped to <strong>${escapeHtml(humanizeLabel(selectedProvider.provider_name || selectedProvider.provider_key))}</strong> / <code>${escapeHtml(selectedModel.model_id)}</code>. Clear the filter to return to the full routing directory.`
      : `Scoped to <strong>${escapeHtml(humanizeLabel(selectedProvider.provider_name || selectedProvider.provider_key))}</strong>. Clear the filter to return to the full routing directory.`;
    return;
  }
  host.textContent = "Showing the full routing directory across all vendor providers.";
}

function buildRoutingNodeInventory(rows) {
  const grouped = new Map();
  (rows || []).forEach((row) => {
    const entry = row?.detail?.entry;
    if (!entry?.node_id) return;
    const key = buildRoutingNodeKey(entry);
    if (!grouped.has(key)) {
      grouped.set(key, {
        node_id: entry.node_id,
        node_role: entry.node_role || null,
        capacity_class: entry.capacity_class || null,
        node_labels: new Set(entry.node_labels || []),
        providers: new Set(),
        models: new Set(),
        pool_ids: new Set(),
        balancing_strategies: new Set(),
        supports_local_models: false,
        supports_training: false,
        entry_rows: [],
      });
    }
    const record = grouped.get(key);
    record.node_role ||= entry.node_role || null;
    record.capacity_class ||= entry.capacity_class || null;
    (entry.node_labels || []).forEach((label) => record.node_labels.add(label));
    if (row.provider && row.provider !== "-") record.providers.add(row.provider);
    if (row.model && row.model !== "-") record.models.add(row.model);
    if (entry.pool_id) record.pool_ids.add(entry.pool_id);
    if (entry.balancing_strategy) record.balancing_strategies.add(entry.balancing_strategy);
    record.supports_local_models ||= Boolean(entry.supports_local_models);
    record.supports_training ||= Boolean(entry.supports_training);
    record.entry_rows.push(row);
  });
  return Array.from(grouped.values()).map((record) => ({
    node_id: record.node_id,
    node_role: record.node_role,
    capacity_class: record.capacity_class,
    node_labels: Array.from(record.node_labels).sort(),
    providers: Array.from(record.providers).sort(),
    models: Array.from(record.models).sort(),
    pool_ids: Array.from(record.pool_ids).sort(),
    pool_count: record.pool_ids.size,
    provider_count: record.providers.size,
    model_count: record.models.size,
    entry_count: record.entry_rows.length,
    balancing_strategies: Array.from(record.balancing_strategies).sort(),
    supports_local_models: record.supports_local_models,
    supports_training: record.supports_training,
    entry_rows: record.entry_rows,
  })).sort((a, b) => a.node_id.localeCompare(b.node_id));
}

function buildRoutingPoolInventory(rows) {
  const grouped = new Map();
  (rows || []).forEach((row) => {
    const entry = row?.detail?.entry;
    if (!entry?.pool_id) return;
    const key = buildRoutingPoolKey(entry);
    if (!grouped.has(key)) {
      grouped.set(key, {
        pool_id: entry.pool_id,
        balancing_strategy: entry.balancing_strategy || null,
        affinity_key: entry.affinity_key || null,
        node_ids: new Set(),
        node_roles: new Set(),
        capacity_classes: new Set(),
        providers: new Set(),
        models: new Set(),
        total_weight: 0,
        entry_rows: [],
      });
    }
    const record = grouped.get(key);
    record.balancing_strategy ||= entry.balancing_strategy || null;
    record.affinity_key ||= entry.affinity_key || null;
    if (entry.node_id) record.node_ids.add(entry.node_id);
    if (entry.node_role) record.node_roles.add(entry.node_role);
    if (entry.capacity_class) record.capacity_classes.add(entry.capacity_class);
    if (row.provider && row.provider !== "-") record.providers.add(row.provider);
    if (row.model && row.model !== "-") record.models.add(row.model);
    record.total_weight += Number(entry.pool_weight || 0);
    record.entry_rows.push(row);
  });
  return Array.from(grouped.values()).map((record) => ({
    pool_id: record.pool_id,
    balancing_strategy: record.balancing_strategy,
    affinity_key: record.affinity_key,
    node_ids: Array.from(record.node_ids).sort(),
    node_roles: Array.from(record.node_roles).sort(),
    capacity_classes: Array.from(record.capacity_classes).sort(),
    providers: Array.from(record.providers).sort(),
    models: Array.from(record.models).sort(),
    node_count: record.node_ids.size,
    provider_count: record.providers.size,
    model_count: record.models.size,
    entry_count: record.entry_rows.length,
    total_weight: Math.round(record.total_weight * 100) / 100,
    entry_rows: record.entry_rows,
  })).sort((a, b) => a.pool_id.localeCompare(b.pool_id));
}

function attachRoutingEntriesToTopology(rows, topology = {}) {
  const nodeEntries = new Map();
  const poolEntries = new Map();
  (rows || []).forEach((row) => {
    const entry = row?.detail?.entry || {};
    if (entry.node_id) {
      const key = String(entry.node_id);
      if (!nodeEntries.has(key)) nodeEntries.set(key, []);
      nodeEntries.get(key).push(row);
    }
    if (entry.pool_id) {
      const key = String(entry.pool_id);
      if (!poolEntries.has(key)) poolEntries.set(key, []);
      poolEntries.get(key).push(row);
    }
  });
  return {
    ...topology,
    nodes: (topology.nodes || []).map((row) => ({
      ...row,
      entry_rows: nodeEntries.get(String(row.node_id || "")) || [],
    })),
    pools: (topology.pools || []).map((row) => ({
      ...row,
      entry_rows: poolEntries.get(String(row.pool_id || "")) || [],
    })),
  };
}

function renderRoutingTopologySummary(topology) {
  const summary = topology?.summary || {};
  renderSummaryChips("#routing-topology-summary", [
    { label: "Nodes", value: formattedValue(summary.node_count ?? 0) },
    { label: "Pools", value: formattedValue(summary.pool_count ?? 0) },
    { label: "Active Nodes", value: formattedValue(summary.active_node_count ?? 0) },
    { label: "Active Pools", value: formattedValue(summary.active_pool_count ?? 0) },
    { label: "Cooling Nodes", value: formattedValue(summary.cooled_node_count ?? 0) },
    { label: "Cooling Pools", value: formattedValue(summary.cooled_pool_count ?? 0) },
  ]);
}

function routingGraphArtifactKey(artifact) {
  return `${artifact?.kind || "artifact"}:${artifact?.id || ""}`;
}

function buildRoutingGraphData({ rows = [], topology = {}, config = null } = {}) {
  const listeners = (Array.isArray(config?.llmproxy_inbound_listeners) ? config.llmproxy_inbound_listeners : [])
    .filter((listener) => Boolean(listener?.exposes_proxy));
  const listenerLookup = new Map(listeners.map((listener) => [String(listener.listener_id || ""), listener]));
  const nodeLookup = new Map((Array.isArray(topology?.nodes) ? topology.nodes : []).map((node) => [String(node.node_id || ""), node]));
  const poolLookup = new Map((Array.isArray(topology?.pools) ? topology.pools : []).map((pool) => [String(pool.pool_id || ""), pool]));
  const listenerNodes = [];
  const policyNodes = [];
  const poolNodes = [];
  const nodeNodes = [];
  const targetNodes = [];
  const edges = [];
  const listenerNodeMap = new Map();
  const policyNodeMap = new Map();
  const poolNodeMap = new Map();
  const nodeNodeMap = new Map();
  const targetNodeMap = new Map();
  const addNode = (collection, map, artifact) => {
    if (!artifact?.id) return null;
    const key = routingGraphArtifactKey(artifact);
    if (!map.has(key)) {
      map.set(key, artifact);
      collection.push(artifact);
    }
    return map.get(key);
  };
  const addEdge = (from, to) => {
    if (!from || !to) return;
    const key = `${from}->${to}`;
    if (edges.some((edge) => `${edge.from}->${edge.to}` === key)) return;
    edges.push({ from, to });
  };
  const ensureListenerArtifact = (listenerId) => {
    const known = listenerLookup.get(String(listenerId || ""));
    return addNode(listenerNodes, listenerNodeMap, {
      kind: "listener",
      id: String(listenerId || "unknown"),
      title: String(known?.name || listenerId || "Listener"),
      subtitle: known ? `${known.published_host || "127.0.0.1"}:${formattedValue(known.published_port || known.port)}` : "Listener declared by routing policy",
      detail: {
        type: "Listener Scope",
        listener_id: known?.listener_id || listenerId,
        name: known?.name || listenerId,
        published: known ? `${known.published_host || "127.0.0.1"}:${formattedValue(known.published_port || known.port)}` : null,
        bind: known ? `${known.host || "0.0.0.0"}:${formattedValue(known.port)}` : null,
        exposes_admin: Boolean(known?.exposes_admin),
        exposes_platform_api: Boolean(known?.exposes_platform_api),
        exposes_proxy: known ? Boolean(known?.exposes_proxy) : true,
      },
      entry_rows: [],
    });
  };
  const allListenersArtifact = listeners.length
    ? addNode(listenerNodes, listenerNodeMap, {
      kind: "listener",
      id: "__all_proxy__",
      title: "All Proxy Listeners",
      subtitle: `${formattedValue(listeners.length)} published inbound surfaces`,
      detail: {
        type: "Listener Scope",
        listener_id: "all",
        name: "All Proxy Listeners",
        listener_ids: listeners.map((listener) => String(listener.listener_id || "")),
        published: "Inherited from proxy-capable listeners",
        exposes_proxy: true,
      },
      entry_rows: [],
    })
    : addNode(listenerNodes, listenerNodeMap, {
      kind: "listener",
      id: "__all_proxy__",
      title: "All Proxy Listeners",
      subtitle: "Listener scope inferred from routing policy",
      detail: {
        type: "Listener Scope",
        listener_id: "all",
        name: "All Proxy Listeners",
        listener_ids: [],
        published: "No proxy listeners published yet",
        exposes_proxy: true,
      },
      entry_rows: [],
    });
  (rows || []).filter(isRenderableTopologyPolicyRow).forEach((row, index) => {
    const entry = row?.detail?.entry || {};
    const rowKey = buildPolicyRowKey(row) || `${row.provider}:${row.model}:${index}`;
    const policyArtifact = addNode(policyNodes, policyNodeMap, {
      kind: "policy",
      id: rowKey,
      title: String(row.model || row.provider || "Routing Entry"),
      subtitle: `${String(row.provider || "-")} • ${humanizeLabel(row.mode || "route")}`,
      detail: {
        type: "Routing Policy Entry",
        policy_version: row.policy_version,
        entry_id: row.entry_id,
        provider: row.provider,
        model: row.model,
        mode: row.mode,
        entry_type: row.entry_type,
        domains: row.domains,
        regions: row.regions,
        tags: row.tags,
        listener_ids: Array.isArray(entry.listener_ids) ? entry.listener_ids : [],
        pool_id: entry.pool_id || null,
        node_id: entry.node_id || null,
      },
      row,
      entry_rows: [row],
    });
    const scopedListeners = Array.isArray(entry.listener_ids) && entry.listener_ids.length
      ? entry.listener_ids.map((listenerId) => ensureListenerArtifact(listenerId))
      : [allListenersArtifact];
    scopedListeners.forEach((listenerArtifact) => {
      if (listenerArtifact) {
        listenerArtifact.entry_rows.push(row);
        addEdge(routingGraphArtifactKey(listenerArtifact), routingGraphArtifactKey(policyArtifact));
      }
    });
    const targetId = `${String(row.provider || "")}:${String(row.model || "")}:${String(row.mode || "")}`;
    const targetArtifact = addNode(targetNodes, targetNodeMap, {
      kind: "target",
      id: targetId,
      title: String(row.model || "Target"),
      subtitle: `${String(row.provider || "-")} • ${humanizeLabel(row.mode || "route")}`,
      target_type: row.entry_type === "local" || String(row.provider || "").startsWith("local:") || String(row.provider || "") === "ollama" ? "local" : "frontier",
      provider: String(row.provider || ""),
      model: String(row.model || ""),
      detail: {
        type: row.entry_type === "local" || String(row.provider || "").startsWith("local:") || String(row.provider || "") === "ollama" ? "Local Target" : "Frontier Target",
        provider: row.provider,
        model: row.model,
        mode: row.mode,
        entry_count: 0,
        pool_ids: [],
        node_ids: [],
        domains: row.domains,
        regions: row.regions,
        tags: row.tags,
      },
      entry_rows: [],
    });
    targetArtifact.entry_rows.push(row);
    targetArtifact.detail.entry_count = targetArtifact.entry_rows.length;
    const poolId = String(entry.pool_id || "").trim();
    const nodeId = String(entry.node_id || "").trim();
    let lastArtifact = policyArtifact;
    if (poolId) {
      const poolRecord = poolLookup.get(poolId) || null;
      const poolArtifact = addNode(poolNodes, poolNodeMap, {
        kind: "pool",
        id: poolId,
        title: poolId,
        subtitle: poolRecord?.balancing_strategy ? `${humanizeLabel(poolRecord.balancing_strategy)} pool` : "Shared target pool",
        detail: poolRecord || {
          type: "Routing Pool",
          pool_id: poolId,
          balancing_strategy: entry.balancing_strategy || null,
          affinity_key: entry.affinity_key || null,
          node_ids: nodeId ? [nodeId] : [],
          entry_count: 0,
        },
        entry_rows: [],
      });
      if (!poolArtifact.entry_rows.some((item) => buildPolicyRowKey(item) === buildPolicyRowKey(row))) {
        poolArtifact.entry_rows.push(row);
      }
      addEdge(routingGraphArtifactKey(policyArtifact), routingGraphArtifactKey(poolArtifact));
      if (Array.isArray(targetArtifact.detail.pool_ids) && !targetArtifact.detail.pool_ids.includes(poolId)) {
        targetArtifact.detail.pool_ids.push(poolId);
      }
      lastArtifact = poolArtifact;
    }
    if (nodeId) {
      const nodeRecord = nodeLookup.get(nodeId) || null;
      const nodeArtifact = addNode(nodeNodes, nodeNodeMap, {
        kind: "node",
        id: nodeId,
        title: nodeId,
        subtitle: nodeRecord?.node_role ? `${humanizeLabel(nodeRecord.node_role)} node` : "Execution node",
        detail: nodeRecord || {
          type: "Routing Node",
          node_id: nodeId,
          node_role: entry.node_role || null,
          capacity_class: entry.capacity_class || null,
          entry_count: 0,
        },
        entry_rows: [],
      });
      if (!nodeArtifact.entry_rows.some((item) => buildPolicyRowKey(item) === buildPolicyRowKey(row))) {
        nodeArtifact.entry_rows.push(row);
      }
      addEdge(routingGraphArtifactKey(lastArtifact), routingGraphArtifactKey(nodeArtifact));
      if (Array.isArray(targetArtifact.detail.node_ids) && !targetArtifact.detail.node_ids.includes(nodeId)) {
        targetArtifact.detail.node_ids.push(nodeId);
      }
      lastArtifact = nodeArtifact;
    }
    addEdge(routingGraphArtifactKey(lastArtifact), routingGraphArtifactKey(targetArtifact));
  });
  return {
    listeners: listenerNodes,
    policies: policyNodes,
    pools: poolNodes,
    nodes: nodeNodes,
    targets: targetNodes,
    edges,
  };
}

const ROUTING_LISTENER_SCOPE_FIELDS = [
  { key: "listener_id", label: "Listener ID", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "name", label: "Name", hideEmpty: true },
  { key: "listener_ids", label: "Scoped Listener IDs", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "All listeners" }) },
  { key: "published", label: "Published Address", hideEmpty: true },
  { key: "bind", label: "Bind Address", hideEmpty: true },
  { key: "exposes_admin", label: "Admin Surface", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "exposes_platform_api", label: "Platform API", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "exposes_proxy", label: "Proxy Traffic", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
];

const ROUTING_TARGET_RECORD_FIELDS = [
  { key: "provider", label: "Provider", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "model", label: "Model", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "mode", label: "Deployment Mode", hideEmpty: true, render: (value) => statusBadge(value) },
  { key: "entry_count", label: "Routing Entries", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "pool_ids", label: "Pools", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "Direct routing" }) },
  { key: "node_ids", label: "Nodes", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "Direct routing" }) },
  { key: "domains", label: "Domains", hideEmpty: true, render: (value) => renderList(String(value || "").split(",").map((item) => item.trim()).filter((item) => item && item !== "-"), { emptyLabel: "All domains" }) },
  { key: "regions", label: "Regions", hideEmpty: true, render: (value) => renderList(String(value || "").split(",").map((item) => item.trim()).filter((item) => item && item !== "-"), { emptyLabel: "No region restriction" }) },
  { key: "tags", label: "Tags", hideEmpty: true, render: (value) => renderList(String(value || "").split(",").map((item) => item.trim()).filter((item) => item && item !== "-"), { emptyLabel: "No tags" }) },
];

function routingGraphEdgeKey(edge) {
  return `${edge?.from || ""}->${edge?.to || ""}`;
}

function buildRoutingGraphEdgeArtifact(edge, artifactLookup) {
  if (!edge) return null;
  const fromArtifact = artifactLookup.get(edge.from);
  const toArtifact = artifactLookup.get(edge.to);
  if (!fromArtifact || !toArtifact) return null;
  return {
    kind: "edge",
    id: routingGraphEdgeKey(edge),
    title: `${fromArtifact.title} -> ${toArtifact.title}`,
    subtitle: `${graphArtifactLabel(fromArtifact.kind)} to ${graphArtifactLabel(toArtifact.kind)}`,
    detail: {
      path: `${fromArtifact.title} -> ${toArtifact.title}`,
      from_label: graphArtifactLabel(fromArtifact.kind),
      from_title: fromArtifact.title,
      to_label: graphArtifactLabel(toArtifact.kind),
      to_title: toArtifact.title,
      detail: "Policy path segment between two routing artifacts.",
    },
    entry_rows: toArtifact.entry_rows || fromArtifact.entry_rows || [],
    openArtifact: toArtifact,
  };
}

function renderRoutingGraphDetail(artifact = null) {
  if (!artifact) {
  renderRecordView("#model-routing-detail-summary-table", null, [], {
      raw: false,
      emptyState: {
        title: "No graph artifact selected.",
        body: "Hover or click a listener scope, policy entry, pool, node, or target in the routing graph to inspect it here.",
      },
    });
    renderRoutingRelatedEntries([], "No routing artifact selected.");
    return;
  }
  const headingMap = {
    listener: "Selected Listener Scope",
    policy: "Selected Routing Policy",
    pool: "Selected Pool",
    node: "Selected Node",
    target: "Selected Target",
    edge: "Selected Graph Edge",
  };
  setText("#model-routing-detail-heading", headingMap[artifact.kind] || "Selected Routing Record");
  if (artifact.kind === "edge") {
    renderRecordView("#model-routing-detail-summary-table", artifact.detail || {}, GRAPH_EDGE_RECORD_FIELDS, {
      rawLabel: "View raw graph edge record",
    });
  } else if (artifact.kind === "listener") {
    renderRecordView("#model-routing-detail-summary-table", artifact.detail || {}, ROUTING_LISTENER_SCOPE_FIELDS, {
      rawLabel: "View raw listener scope record",
    });
  } else if (artifact.kind === "policy") {
    renderPolicyEntryDetail({ policy_version: artifact.row?.policy_version, entry_index: artifact.row?.detail?.entry_index, entry: artifact.row?.detail?.entry || {} }, "#model-routing-detail-summary-table");
  } else if (artifact.kind === "pool") {
    renderRoutingPoolDetail(artifact.detail || {});
  } else if (artifact.kind === "node") {
    renderRoutingNodeDetail(artifact.detail || {});
  } else {
    renderRecordView("#model-routing-detail-summary-table", artifact.detail || {}, ROUTING_TARGET_RECORD_FIELDS, {
      rawLabel: "View raw target record",
    });
  }
  renderRoutingRelatedEntries(artifact.entry_rows || [], "No routing entries map to this artifact.");
}

async function openRoutingGraphContext(artifact) {
  if (!artifact) return;
  if (artifact.kind === "edge" && artifact.openArtifact) {
    artifact = artifact.openArtifact;
  }
  if (artifact.kind === "listener") {
    const listenerIds = Array.isArray(artifact.detail?.listener_ids) && artifact.detail.listener_ids.length
      ? artifact.detail.listener_ids
      : artifact.detail?.listener_id && artifact.detail.listener_id !== "all"
        ? [artifact.detail.listener_id]
        : [];
    if (listenerIds.length === 1) {
      await openRequestHistoryContext({ listener_id: listenerIds[0] });
      return;
    }
    if (!listenerIds.length) {
      switchPanel("operations");
      switchSubview("operations", "traffic");
      showToast("Opened traffic directory for all listeners in this routing scope.", "info");
      return;
    }
    showToast("This listener scope spans multiple listeners. Use Traffic to filter the exact listener you want.", "info");
    return;
  }
  if (artifact.kind === "policy" && artifact.row) {
    switchPanel("models");
    switchSubview("models", "routing");
    switchCollection("modelRouting", "entries");
    inspectPolicyRow(artifact.row);
    return;
  }
  if (artifact.kind === "pool") {
    switchPanel("models");
    switchSubview("models", "routing");
    switchCollection("modelRouting", "pools");
    inspectRoutingPool(artifact.detail || artifact);
    return;
  }
  if (artifact.kind === "node") {
    switchPanel("models");
    switchSubview("models", "routing");
    switchCollection("modelRouting", "nodes");
    inspectRoutingNode(artifact.detail || artifact);
    return;
  }
  if (artifact.kind === "target") {
    await openOperationsTopologyContext({
      kind: "target",
      id: artifact.id,
      provider: artifact.provider,
      model: artifact.model,
      target_type: artifact.target_type,
    });
  }
}

function renderRoutingGraph(data = null) {
  const host = $("#routing-graph");
  if (!host) return;
  host.innerHTML = "";
  const listeners = data?.listeners || [];
  const policies = data?.policies || [];
  const pools = data?.pools || [];
  const nodes = data?.nodes || [];
  const targets = data?.targets || [];
  renderSummaryChips("#routing-graph-summary-strip", [
    { label: "Listener Scopes", value: String(listeners.length) },
    { label: "Policies", value: String(policies.length) },
    { label: "Pools", value: String(pools.length) },
    { label: "Nodes", value: String(nodes.length) },
    { label: "Targets", value: String(targets.length) },
  ]);
  if (!policies.length || !targets.length) {
    host.appendChild(buildEmptyState({
      icon: "⇄",
      title: "No routing path available.",
      body: "Publish routing entries to render the listener-to-policy-to-target path graph.",
    }));
    renderRoutingGraphDetail(null);
    return;
  }
  const columns = [
    { title: "Listener Scope", items: listeners, x: 40 },
    { title: "Policy Entries", items: policies, x: 290 },
    { title: "Pools", items: pools, x: 540 },
    { title: "Nodes", items: nodes, x: 790 },
    { title: "Targets", items: targets, x: 1040 },
  ];
  const NS = "http://www.w3.org/2000/svg";
  const nodeWidth = 210;
  const nodeHeight = 58;
  const gapY = 18;
  const topY = 42;
  const maxRows = Math.max(...columns.map((column) => Math.max(column.items.length, 1)));
  const height = topY + maxRows * (nodeHeight + gapY) + 30;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 1300 ${height}`);
  svg.setAttribute("class", "topology-graph");
  const positions = new Map();
  const artifactLookup = new Map();
  columns.forEach((column) => {
    const startY = topY + Math.max(0, (maxRows - column.items.length) * (nodeHeight + gapY) * 0.5);
    column.items.forEach((artifact, index) => {
      artifactLookup.set(routingGraphArtifactKey(artifact), artifact);
      positions.set(routingGraphArtifactKey(artifact), {
        x: column.x,
        y: startY + index * (nodeHeight + gapY),
      });
    });
    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(column.x));
    title.setAttribute("y", "22");
    title.setAttribute("class", "topology-title");
    title.textContent = column.title;
    svg.appendChild(title);
  });
  (data?.edges || []).forEach((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) return;
    const edgeArtifact = buildRoutingGraphEdgeArtifact(edge, artifactLookup);
    const path = document.createElementNS(NS, "path");
    const startX = from.x + nodeWidth;
    const startY = from.y + nodeHeight / 2;
    const endX = to.x;
    const endY = to.y + nodeHeight / 2;
    const controlX = (startX + endX) / 2;
    path.setAttribute("d", `M ${startX} ${startY} C ${controlX} ${startY}, ${controlX} ${endY}, ${endX} ${endY}`);
    path.setAttribute("class", "topology-edge");
    if (edgeArtifact && edgeArtifact.id === state.selectedRoutingGraphEdgeKey) {
      path.classList.add("active");
    }
    path.setAttribute("tabindex", "0");
    const activateEdge = () => {
      if (!edgeArtifact) return;
      state.selectedRoutingGraphEdgeKey = edgeArtifact.id;
      state.selectedRoutingGraphKey = null;
      renderRoutingGraphDetail(edgeArtifact);
    };
    path.addEventListener("mouseenter", activateEdge);
    path.addEventListener("focus", activateEdge);
    path.addEventListener("click", activateEdge);
    path.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activateEdge();
      await openRoutingGraphContext(edgeArtifact);
    });
    svg.appendChild(path);
  });
  columns.flatMap((column) => column.items).forEach((artifact) => {
    const pos = positions.get(routingGraphArtifactKey(artifact));
    if (!pos) return;
    const group = document.createElementNS(NS, "g");
    const extraTargetClass = artifact.kind === "target" && artifact.target_type ? ` topology-node-${artifact.target_type}` : "";
    group.setAttribute("class", `topology-node topology-node-${artifact.kind}${extraTargetClass}`);
    if (routingGraphArtifactKey(artifact) === state.selectedRoutingGraphKey) {
      group.classList.add("active");
    }
    group.setAttribute("tabindex", "0");
    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("x", String(pos.x));
    rect.setAttribute("y", String(pos.y));
    rect.setAttribute("rx", "12");
    rect.setAttribute("ry", "12");
    rect.setAttribute("width", String(nodeWidth));
    rect.setAttribute("height", String(nodeHeight));
    group.appendChild(rect);
    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(pos.x + 14));
    title.setAttribute("y", String(pos.y + 24));
    title.setAttribute("class", "topology-node-title");
    title.textContent = artifact.title;
    group.appendChild(title);
    const subtitle = document.createElementNS(NS, "text");
    subtitle.setAttribute("x", String(pos.x + 14));
    subtitle.setAttribute("y", String(pos.y + 43));
    subtitle.setAttribute("class", "topology-node-subtitle");
    subtitle.textContent = artifact.subtitle;
    group.appendChild(subtitle);
    const activate = () => {
      state.selectedRoutingGraphEdgeKey = null;
      state.selectedRoutingGraphKey = routingGraphArtifactKey(artifact);
      renderRoutingGraphDetail(artifact);
    };
    group.addEventListener("mouseenter", activate);
    group.addEventListener("focus", activate);
    group.addEventListener("click", activate);
    group.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activate();
      await openRoutingGraphContext(artifact);
    });
    svg.appendChild(group);
  });
  mountInteractiveSvgGraph(host, svg, { graphKey: "#routing-graph", baseWidth: 1300, baseHeight: height });
  const selectedArtifact = columns.flatMap((column) => column.items)
    .find((artifact) => routingGraphArtifactKey(artifact) === state.selectedRoutingGraphKey)
    || policies[0]
    || targets[0]
    || listeners[0]
    || null;
  const selectedEdge = state.selectedRoutingGraphEdgeKey
    ? buildRoutingGraphEdgeArtifact((data?.edges || []).find((edge) => routingGraphEdgeKey(edge) === state.selectedRoutingGraphEdgeKey), artifactLookup)
    : null;
  renderRoutingGraphDetail(selectedEdge || selectedArtifact);
}

function currentSelectedRoutingGraphArtifact() {
  const data = buildRoutingGraphData({
    rows: filteredPolicyRows(state.policyRows || []),
    topology: state.routingTopologyInventory || {},
    config: state.configPayload,
  });
  const artifactLookup = new Map();
  [...(data.listeners || []), ...(data.policies || []), ...(data.pools || []), ...(data.nodes || []), ...(data.targets || [])]
    .forEach((artifact) => artifactLookup.set(routingGraphArtifactKey(artifact), artifact));
  if (state.selectedRoutingGraphEdgeKey) {
    const edge = (data.edges || []).find((item) => routingGraphEdgeKey(item) === state.selectedRoutingGraphEdgeKey);
    const edgeArtifact = edge ? buildRoutingGraphEdgeArtifact(edge, artifactLookup) : null;
    if (edgeArtifact) return edgeArtifact;
  }
  const items = [...(data.listeners || []), ...(data.policies || []), ...(data.pools || []), ...(data.nodes || []), ...(data.targets || [])];
  return items.find((artifact) => routingGraphArtifactKey(artifact) === state.selectedRoutingGraphKey) || null;
}

function inspectRoutingNode(record) {
  state.selectedRoutingNodeKey = buildRoutingNodeKey(record);
  setActiveRuntimeRow("#routing-nodes-table", state.selectedRoutingNodeKey);
  setText("#model-routing-detail-heading", "Selected Node");
  renderRoutingNodeDetail(record || {});
  renderRoutingRelatedEntries(record?.entry_rows || [], "No routing entries map to this node.");
}

function inspectRoutingPool(record) {
  state.selectedRoutingPoolKey = buildRoutingPoolKey(record);
  setActiveRuntimeRow("#routing-pools-table", state.selectedRoutingPoolKey);
  setText("#model-routing-detail-heading", "Selected Pool");
  renderRoutingPoolDetail(record || {});
  renderRoutingRelatedEntries(record?.entry_rows || [], "No routing entries map to this pool.");
}

const LOCAL_PACKAGE_FIELDS = [
  { key: "model_alias", label: "Model Alias", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "model_registry_id", label: "Registry ID", render: (value) => renderIdChip(value) },
  { key: "base_model", label: "Base Model", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "adapter_type", label: "Adapter Type", render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "promotion_status", label: "Promotion Status", render: (value) => statusBadge(value) },
  { key: "runtime_target", label: "Runtime Target", hideEmpty: true, render: (value) => `<span class="badge badge-info">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "deployment_status", label: "Deployment Status", hideEmpty: true, render: (value) => statusBadge(value) },
  { key: "routing_state", label: "Routing State", hideEmpty: true, render: (value) => statusBadge(value) },
  { key: "active_route_mode", label: "Live Route Mode", hideEmpty: true, render: (value) => statusBadge(value) },
  { key: "endpoint_url", label: "Endpoint URL", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "domains", label: "Domains", render: (value) => renderList(value, { emptyLabel: "No domains configured" }) },
  { key: "artifact_paths", label: "Artifact Paths", render: (value) => (Array.isArray(value) && value.length ? `<pre class="value-pre">${escapeHtml(value.join("\n"))}</pre>` : '<span class="empty-value">No artifacts recorded</span>') },
];

function renderLocalPackageDetail(pkg, selector = "#model-detail-summary-table") {
  renderRecordView(selector, pkg, LOCAL_PACKAGE_FIELDS, {
    rawLabel: "View raw model package record",
    emptyState: {
      title: "No package selected.",
      body: "Choose a registered local package from the table above to inspect its manifest, training domains, and promotion status.",
    },
  });
}

function inspectLocalModel(row) {
  state.selectedLocalModelAlias = row?.model_alias || null;
  setActiveRuntimeRow("#local-models-table", state.selectedLocalModelAlias || "");
  setText("#model-detail-heading", "Selected Custom LLM");
  $("#foundation-open-provider-guide")?.classList.add("hidden");
  $("#foundation-open-routing")?.classList.add("hidden");
  $("#foundation-open-streaming")?.classList.add("hidden");
  $("#provider-model-table")?.classList.add("hidden");
  $("#provider-model-detail")?.classList.add("hidden");
  showDetailCard("#model-detail-card", null, row);
}

const POLICY_ENTRY_RECORD_FIELDS = [
  { key: "policy_version", label: "Policy Version", render: (value) => renderIdChip(value) },
  { key: "entry_index", label: "Position in Policy", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "entry_id", label: "Entry ID", render: (value) => renderIdChip(value) },
  { key: "entry_type", label: "Entry Type", render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "model", label: "Model", value: (record) => record.model_alias || record.model_id, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "provider_key", label: "Provider", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "provider_family", label: "Provider Family", value: (record) => (record.entry_type === "frontier" ? record.provider_family : null), hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(String(value))}</span>` },
  { key: "runtime", label: "Runtime", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(String(value))}</span>` },
  {
    key: "deployment_mode",
    label: "Deployment Mode",
    render: (value) => {
      const tone = value === "production" ? "ok" : value === "canary" ? "info" : "muted";
      return `<span class="badge badge-${tone}">${escapeHtml(humanizeLabel(value))}</span>`;
    },
  },
  { key: "canary_percent", label: "Canary Traffic", render: (value) => `<span class="num">${escapeHtml(formattedValue(Math.round((value ?? 0) * 10000) / 100))}%</span>` },
  { key: "endpoint_url", label: "Endpoint", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "node_id", label: "Node ID", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "node_role", label: "Node Role", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(String(value)))}</span>` },
  { key: "capacity_class", label: "Capacity Class", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "node_labels", label: "Node Labels", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No node labels" }) },
  { key: "pool_id", label: "Pool ID", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "pool_weight", label: "Pool Weight", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "balancing_strategy", label: "Balancing", hideEmpty: true, render: (value) => `<span class="badge badge-info">${escapeHtml(String(value))}</span>` },
  { key: "affinity_key", label: "Affinity Key", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(String(value))}</span>` },
  { key: "supports_local_models", label: "Local Models", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "supports_training", label: "Training", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "forward_request_metadata", label: "Forward Metadata", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "domains", label: "Domains", render: (value) => renderList(value, { emptyLabel: "All domains" }) },
  { key: "requested_models", label: "Requested Models", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "Direct 1:1 access" }) },
  { key: "task_types", label: "Task Types", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "All task types" }) },
  { key: "tags", label: "Tags", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No tags configured" }) },
  { key: "labels", label: "Labels", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No labels configured" }) },
  { key: "regions", label: "Regions", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No region restriction" }) },
  { key: "listener_ids", label: "Listener IDs", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "All listeners" }) },
  { key: "fallback_chain", label: "Fallback Chain", hideEmpty: true, render: (value) => renderList((value || []).map((item) => `${item.order}: ${item.provider}/${item.model}`), { emptyLabel: "No fallback chain configured" }) },
  { key: "decision_rationale", label: "Decision Rationale", hideEmpty: true },
  { key: "artifact_path", label: "Artifact Path", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "quality_summary", label: "Quality Summary", value: (record) => (record.quality_summary && Object.keys(record.quality_summary).length ? record.quality_summary : null), hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(JSON.stringify(value, null, 2))}</pre>` },
];

function renderPolicyEntryDetail(wrapper, selector = "#model-detail-summary-table") {
  const entry = wrapper?.entry || {};
  const flattened = { policy_version: wrapper?.policy_version, entry_index: wrapper?.entry_index, ...entry };
  renderRecordView(selector, flattened, POLICY_ENTRY_RECORD_FIELDS, {
    rawLabel: "View raw policy entry record",
    emptyState: {
      title: "No policy entry selected.",
      body: "Choose an entry from the Routing Policies table above to inspect its target model, direct-access scope, redirect rules, and rollout configuration.",
    },
  });
}

const ROUTING_NODE_RECORD_FIELDS = [
  { key: "node_id", label: "Node ID", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "node_role", label: "Node Role", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(String(value)))}</span>` },
  { key: "capacity_class", label: "Capacity Class", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "policy_version", label: "Active Policy", hideEmpty: true, render: (value) => renderIdChip(value) },
  { key: "recent_request_count", label: "Recent Requests", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "successful_request_count", label: "Successful Requests", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "failed_request_count", label: "Failed Requests", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "avg_latency_ms", label: "Avg Latency", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))} ms</span>` },
  { key: "p95_latency_ms", label: "P95 Latency", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))} ms</span>` },
  { key: "cooled_down", label: "Cooldown", render: (value, record) => value ? `<span class="badge badge-warn">Cooling Down</span>${record?.cooled_provider_count ? `<br/><span>${escapeHtml(formattedValue(record.cooled_provider_count))} provider(s)</span>` : ""}` : '<span class="badge badge-ok">Ready</span>' },
  { key: "last_seen_at", label: "Last Seen", hideEmpty: true, render: (value) => timeLabel(value) },
  { key: "pool_count", label: "Pools", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "entry_count", label: "Routing Entries", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "provider_count", label: "Providers", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "model_count", label: "Models", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "balancing_strategies", label: "Balancing", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No pool strategy" }) },
  { key: "node_labels", label: "Node Labels", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No node labels" }) },
  { key: "providers", label: "Providers", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No providers" }) },
  { key: "models", label: "Models", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No models" }) },
  { key: "supports_local_models", label: "Local Models", render: (value) => boolBadge(Boolean(value)) },
  { key: "supports_training", label: "Training", render: (value) => boolBadge(Boolean(value)) },
];

const ROUTING_POOL_RECORD_FIELDS = [
  { key: "pool_id", label: "Pool ID", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "balancing_strategy", label: "Balancing", hideEmpty: true, render: (value) => `<span class="badge badge-info">${escapeHtml(humanizeLabel(String(value)))}</span>` },
  { key: "affinity_key", label: "Affinity Key", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(String(value))}</span>` },
  { key: "policy_version", label: "Active Policy", hideEmpty: true, render: (value) => renderIdChip(value) },
  { key: "recent_request_count", label: "Recent Requests", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "successful_request_count", label: "Successful Requests", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "failed_request_count", label: "Failed Requests", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "avg_latency_ms", label: "Avg Latency", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))} ms</span>` },
  { key: "p95_latency_ms", label: "P95 Latency", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))} ms</span>` },
  { key: "cooled_down", label: "Cooldown", render: (value, record) => value ? `<span class="badge badge-warn">Cooling Down</span>${record?.cooled_provider_count ? `<br/><span>${escapeHtml(formattedValue(record.cooled_provider_count))} provider(s)</span>` : ""}` : '<span class="badge badge-ok">Ready</span>' },
  { key: "last_seen_at", label: "Last Seen", hideEmpty: true, render: (value) => timeLabel(value) },
  { key: "entry_count", label: "Routing Entries", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "node_count", label: "Nodes", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "provider_count", label: "Providers", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "model_count", label: "Models", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "total_weight", label: "Total Weight", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "node_roles", label: "Node Roles", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No node roles" }) },
  { key: "capacity_classes", label: "Capacity Classes", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No capacity classes" }) },
  { key: "node_ids", label: "Node IDs", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No nodes" }) },
  { key: "providers", label: "Providers", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No providers" }) },
  { key: "models", label: "Models", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No models" }) },
];

function renderRoutingRelatedEntries(rows, emptyMessage = "No related routing entries.") {
  const host = $("#model-routing-related-table");
  if (!host) return;
  host.innerHTML = "";
  const items = Array.isArray(rows) ? rows : [];
  host.appendChild(
    makeTable(["Provider", "Model", "Mode", "Pool", "Node"], items, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = buildPolicyRowKey(row);
      if (buildPolicyRowKey(row) === state.selectedPolicyRowKey) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td>${escapeHtml(row.provider || "-")}</td>
        <td>${escapeHtml(row.model || "-")}</td>
        <td>${escapeHtml(row.mode || "-")}</td>
        <td>${row.detail?.entry?.pool_id ? renderIdChip(row.detail.entry.pool_id, { truncate: false }) : '<span class="empty-value">Direct</span>'}</td>
        <td>${row.detail?.entry?.node_id ? renderIdChip(row.detail.entry.node_id, { truncate: false }) : '<span class="empty-value">Direct</span>'}</td>
      `;
      tr.addEventListener("click", () => {
        state.activeModelRoutingCollection = "entries";
        switchCollection("modelRouting", "entries");
        inspectPolicyRow(row);
      });
      return tr;
    }, emptyMessage),
  );
}

function renderRoutingNodeDetail(record) {
  renderRecordView("#model-routing-detail-summary-table", record, ROUTING_NODE_RECORD_FIELDS, {
    rawLabel: "View raw node inventory record",
    emptyState: {
      title: "No node selected.",
      body: "Choose a node row from the inventory table to inspect its role, capacity, capabilities, and linked routing entries.",
    },
  });
}

function renderRoutingPoolDetail(record) {
  renderRecordView("#model-routing-detail-summary-table", record, ROUTING_POOL_RECORD_FIELDS, {
    rawLabel: "View raw pool inventory record",
    emptyState: {
      title: "No pool selected.",
      body: "Choose a pool row from the inventory table to inspect its balancing strategy, coverage, and linked routing entries.",
    },
  });
}

const POLICY_VERSION_RECORD_FIELDS = [
  { key: "policy_version", label: "Policy Version", render: (value) => renderIdChip(value) },
  {
    key: "entry_count",
    label: "Routing Entries",
    value: (record) => (Array.isArray(record.policy?.entries) ? record.policy.entries.length : 0),
    render: (value) => (value === 0 ? '<span class="empty-value">No routing entries in this policy version</span>' : `<span class="num">${escapeHtml(formattedValue(value))}</span>`),
  },
];

function renderPolicyVersionDetail(policyVersion, selector = "#model-detail-summary-table") {
  renderRecordView(selector, policyVersion, POLICY_VERSION_RECORD_FIELDS, {
    rawLabel: "View raw policy version record",
    emptyState: {
      title: "No policy version selected.",
      body: "Choose a routing policy version from the table above to inspect it.",
    },
  });
}

/**
 * `#model-detail-card` is shared by three different "Inspect" actions across the
 * Models panel — proxy-exposed models, local packages, and routing-policy
 * entries/versions — each handing it a structurally distinct payload. Detect
 * which one arrived (by the field that uniquely identifies its shape) and render
 * it with the matching specialised view rather than forcing one schema onto all four.
 */
function renderModelDetail(payload, selector = "#model-detail-summary-table") {
  if (payload && typeof payload === "object" && payload.entry && typeof payload.entry === "object") {
    renderPolicyEntryDetail(payload, selector);
  } else if (payload && Array.isArray(payload.artifact_paths)) {
    renderLocalPackageDetail(payload, selector);
  } else if (payload && payload.policy && typeof payload.policy === "object") {
    renderPolicyVersionDetail(payload, selector);
  } else {
    renderModelInfoDetail(payload, selector);
  }
}

function showDetailCard(cardSelector, outputSelector, payload) {
  let resolvedCardSelector = cardSelector;
  let resolvedOutputSelector = outputSelector;
  let modelSummarySelector = "#model-detail-summary-table";
  if (cardSelector === "#model-detail-card" && state.activePanel === "models" && state.activeModelsSubview === "routing") {
    resolvedCardSelector = "#model-routing-detail-card";
    modelSummarySelector = "#model-routing-detail-summary-table";
  }
  const card = $(resolvedCardSelector);
  if (card) {
    card.classList.remove("hidden");
    if (!["#request-detail-card", "#model-detail-card", "#model-routing-detail-card", "#job-detail-card", "#event-detail-card"].includes(resolvedCardSelector)) {
      card.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  if (resolvedCardSelector === "#request-detail-card") {
    renderRequestDetail(payload);
  } else if (cardSelector === "#model-detail-card") {
    renderModelDetail(payload, modelSummarySelector);
  } else if (resolvedCardSelector === "#training-detail-card") {
    renderTrainingDetail(payload);
  } else if (resolvedCardSelector === "#evaluation-detail-card") {
    renderEvaluationDetail(payload);
  } else if (resolvedCardSelector === "#job-detail-card") {
    renderJobDetail(payload);
  } else if (resolvedCardSelector === "#event-detail-card") {
    renderEventDetail(payload);
  }
  // `#model-detail-card` is the one card whose renderer (renderModelDetail, for
  // every one of its four payload shapes — model info, local package, policy
  // version, and policy entry) already builds its summary table with
  // renderRecordView()'s default `rawLabel` raw-JSON disclosure. Re-dumping the
  // same payload into a second, permanently-visible `<pre class="output tall">`
  // below it would show the identical JSON twice on screen for no benefit, so
  // that element has been removed from the markup and this call is skipped here.
  // Every other card's renderer (request, training, evaluation, job, event)
  // either omits an embedded raw view entirely (training/evaluation/job/event —
  // this is their only raw view) or embeds only a sub-object of the full payload
  // (request — its disclosure shows just `request`, not the routing decisions,
  // model responses, candidates, etc. that this dump uniquely surfaces), so the
  // generic dump still earns its place for those.
  if (cardSelector !== "#model-detail-card") {
    renderOutput(resolvedOutputSelector, payload);
  }
}

function switchSubview(group, subview) {
  $$(`[data-subview-group="${group}"]`).forEach((button) => {
    const isActive = button.dataset.subview === subview;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  $$(`[data-subview-pane-group="${group}"]`).forEach((pane) => {
    const isActive = pane.dataset.subviewPane === subview;
    pane.classList.toggle("hidden", !isActive);
    pane.classList.toggle("active", isActive);
  });
  if (group === "overview") {
    state.activeOverviewSubview = subview;
  } else if (group === "operations") {
    state.activeOperationsSubview = subview;
  } else if (group === "proxy") {
    state.activeProxySubview = subview;
  } else if (group === "models") {
    state.activeModelsSubview = subview;
  } else if (group === "training") {
    state.activeTrainingSubview = subview;
  }
}

function syncSidebarNavGroups() {
  $$("[data-nav-group]").forEach((group) => {
    const isActive = group.dataset.navGroup === state.activePanel;
    group.classList.toggle("active", isActive);
    group.querySelector(".nav-group-body")?.classList.toggle("hidden", !isActive);
  });
}

function switchCollection(group, collection) {
  $$(`[data-collection-group="${group}"]`).forEach((button) => {
    const isActive = button.dataset.collection === collection;
    button.classList.toggle("active", isActive);
    button.classList.toggle("accent", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  if (group === "runtime") {
    state.activeRuntimeCollection = collection;
    $("#runtime-collection-pane-jobs")?.classList.toggle("hidden", collection !== "jobs");
    $("#runtime-collection-pane-events")?.classList.toggle("hidden", collection !== "events");
    $("#runtime-jobs-toolbar")?.classList.toggle("hidden", collection !== "jobs");
    $("#runtime-events-toolbar")?.classList.toggle("hidden", collection !== "events");
    $("#job-detail-card")?.classList.toggle("hidden", collection !== "jobs");
    $("#event-detail-card")?.classList.toggle("hidden", collection !== "events");
    setText("#runtime-detail-heading", collection === "events" ? "Selected Event" : "Selected Job");
  } else if (group === "ops") {
    state.activeOpsCollection = collection;
    $("#ops-collection-pane-events")?.classList.remove("hidden");
    $("#ops-toolbar-events")?.classList.remove("hidden");
    setText("#ops-detail-heading", "Selected Operational Event");
  } else if (group === "data") {
    state.activeDataCollection = collection;
    $("#data-collection-pane-candidates")?.classList.toggle("hidden", collection !== "candidates");
    $("#data-collection-pane-exports")?.classList.toggle("hidden", collection !== "exports");
    $("#data-collection-pane-datasets")?.classList.toggle("hidden", collection !== "datasets");
    $("#data-toolbar-candidates")?.classList.toggle("hidden", collection !== "candidates");
    $("#data-toolbar-exports")?.classList.toggle("hidden", collection !== "exports");
    $("#data-toolbar-datasets")?.classList.toggle("hidden", collection !== "datasets");
    $("#data-detail-pane-candidates")?.classList.toggle("hidden", collection !== "candidates");
    $("#data-detail-pane-exports")?.classList.toggle("hidden", collection !== "exports");
    $("#data-detail-pane-datasets")?.classList.toggle("hidden", collection !== "datasets");
    $("#data-action-pane-export")?.classList.toggle("hidden", collection === "datasets");
    $("#data-action-pane-import")?.classList.toggle("hidden", collection !== "datasets");
    setText(
      "#data-detail-heading",
      collection === "exports" ? "Selected Export" : collection === "datasets" ? "Selected Import / Version" : "Candidate Guidance",
    );
    setText("#data-action-heading", collection === "datasets" ? "Import Dataset" : "Create Export");
  } else if (group === "training") {
    state.activeTrainingCollection = collection;
    $("#training-collection-pane-runs")?.classList.toggle("hidden", collection !== "runs");
    $("#training-collection-pane-evaluations")?.classList.toggle("hidden", collection !== "evaluations");
    $("#training-toolbar-runs")?.classList.toggle("hidden", collection !== "runs");
    $("#training-toolbar-evaluations")?.classList.toggle("hidden", collection !== "evaluations");
    $("#training-detail-card")?.classList.toggle("hidden", collection !== "runs");
    $("#evaluation-detail-card")?.classList.toggle("hidden", collection !== "evaluations");
    $("#training-action-pane-runs")?.classList.toggle("hidden", collection !== "runs");
    $("#training-action-pane-evaluations")?.classList.toggle("hidden", collection !== "evaluations");
    setText("#training-action-heading", collection === "evaluations" ? "Run Evaluation" : "Run Training");
    setText("#training-detail-heading", collection === "evaluations" ? "Selected Evaluation" : "Selected Training Run");
    syncTrainingPolling();
  } else if (group === "governance") {
    state.activeGovernanceCollection = collection;
    $("#governance-collection-pane-keys")?.classList.toggle("hidden", collection !== "keys");
    $("#governance-collection-pane-pricing")?.classList.toggle("hidden", collection !== "pricing");
    $("#governance-collection-pane-guardrails")?.classList.toggle("hidden", collection !== "guardrails");
    $("#governance-toolbar-keys")?.classList.toggle("hidden", collection !== "keys");
    $("#governance-toolbar-pricing")?.classList.toggle("hidden", collection !== "pricing");
    $("#governance-toolbar-guardrails")?.classList.toggle("hidden", collection !== "guardrails");
    $("#governance-detail-pane-keys")?.classList.toggle("hidden", collection !== "keys");
    $("#governance-detail-pane-pricing")?.classList.toggle("hidden", collection !== "pricing");
    $("#governance-detail-pane-guardrails")?.classList.toggle("hidden", collection !== "guardrails");
    $("#governance-action-pane-keys")?.classList.toggle("hidden", collection !== "keys");
    $("#governance-action-pane-pricing")?.classList.toggle("hidden", collection !== "pricing");
    $("#governance-action-pane-guardrails")?.classList.toggle("hidden", collection !== "guardrails");
    setText(
      "#governance-detail-heading",
      collection === "pricing" ? "Pricing Reference" : collection === "guardrails" ? "Guardrail Detail" : "Selected Virtual Key",
    );
    setText(
      "#governance-action-heading",
      collection === "pricing" ? "Pricing Notes" : collection === "guardrails" ? "Guardrail Notes" : "Issue Virtual Key",
    );
  } else if (group === "integrations") {
    state.activeIntegrationsCollection = collection;
    $("#integrations-collection-pane-providers")?.classList.toggle("hidden", collection !== "providers");
    $("#integrations-collection-pane-mcp")?.classList.toggle("hidden", collection !== "mcp");
    $("#integrations-collection-pane-a2a")?.classList.toggle("hidden", collection !== "a2a");
    $("#integrations-collection-pane-rest")?.classList.toggle("hidden", collection !== "rest");
    $("#integrations-toolbar-providers")?.classList.toggle("hidden", collection !== "providers");
    $("#integrations-toolbar-mcp")?.classList.toggle("hidden", collection !== "mcp");
    $("#integrations-toolbar-a2a")?.classList.toggle("hidden", collection !== "a2a");
    $("#integrations-toolbar-rest")?.classList.toggle("hidden", collection !== "rest");
    $("#integrations-detail-pane-providers")?.classList.toggle("hidden", collection !== "providers");
    $("#integrations-detail-pane-mcp")?.classList.toggle("hidden", collection !== "mcp");
    $("#integrations-detail-pane-a2a")?.classList.toggle("hidden", collection !== "a2a");
    $("#integrations-detail-pane-rest")?.classList.toggle("hidden", collection !== "rest");
    setText(
      "#integrations-detail-heading",
      collection === "mcp"
        ? "Selected MCP Server"
        : collection === "a2a"
          ? "Selected A2A Peer"
          : collection === "rest"
            ? "Selected REST Endpoint"
            : "Selected Reference Guide",
    );
  } else if (group === "modelCatalog") {
    state.activeModelCatalogCollection = collection;
    $("#model-catalog-pane-proxy")?.classList.toggle("hidden", collection !== "proxy");
    $("#model-catalog-pane-local")?.classList.toggle("hidden", collection !== "local");
    $("#model-catalog-toolbar-proxy")?.classList.toggle("hidden", collection !== "proxy");
    $("#model-catalog-toolbar-local")?.classList.toggle("hidden", collection !== "local");
    $("#provider-model-table")?.classList.toggle("hidden", collection !== "proxy");
    $("#provider-model-detail")?.classList.toggle("hidden", collection !== "proxy");
    $("#foundation-open-provider-guide")?.classList.toggle("hidden", collection === "local");
    $("#foundation-open-routing")?.classList.toggle("hidden", collection === "local");
    $("#foundation-open-streaming")?.classList.toggle("hidden", collection === "local");
    setText("#model-detail-heading", collection === "local" ? "Selected Custom LLM" : "Selected Vendor Provider");
    if (collection === "local") {
      const selected = (state.localModelRows || []).find((row) => String(row.model_alias || "") === String(state.selectedLocalModelAlias || ""));
      if (selected) {
        renderLocalPackageDetail(selected);
      } else {
        renderLocalPackageDetail(null);
      }
    } else {
      state.selectedLocalModelAlias = null;
    }
  } else if (group === "modelRegister") {
    state.activeModelRegisterCollection = collection;
    $("#model-register-pane-vendor")?.classList.toggle("hidden", collection !== "vendor");
    $("#model-register-pane-custom")?.classList.toggle("hidden", collection !== "custom");
    $("#model-register-pane-runtime")?.classList.toggle("hidden", collection !== "runtime");
  } else if (group === "modelRouting") {
    state.activeModelRoutingCollection = collection;
    $("#model-routing-pane-entries")?.classList.toggle("hidden", collection !== "entries");
    $("#model-routing-pane-nodes")?.classList.toggle("hidden", collection !== "nodes");
    $("#model-routing-pane-pools")?.classList.toggle("hidden", collection !== "pools");
    $("#model-routing-toolbar-entries")?.classList.toggle("hidden", collection !== "entries");
    $("#model-routing-toolbar-nodes")?.classList.toggle("hidden", collection !== "nodes");
    $("#model-routing-toolbar-pools")?.classList.toggle("hidden", collection !== "pools");
    setText(
      "#model-routing-detail-heading",
      collection === "nodes" ? "Selected Node" : collection === "pools" ? "Selected Pool" : "Selected Routing Record",
    );
    renderRoutingScopeBanner();
  }
}

function renderRuntimeSummary() {
  const jobs = state.runtimeJobs || [];
  const events = state.runtimeEvents || [];
  renderSummaryChips("#runtime-summary-strip", [
    { label: "Jobs Visible", value: String(jobs.length) },
    { label: "Pending Jobs", value: String(jobs.filter((row) => ["pending", "queued", "running"].includes(String(row.status || "").toLowerCase())).length) },
    { label: "Events Visible", value: String(events.length) },
    { label: "Unprocessed Events", value: String(events.filter((row) => !row.processed_at).length) },
  ]);
}

function renderOpsSummaryChips(payload) {
  renderSummaryChips("#ops-summary-strip", [
    { label: "Requests", value: String(payload?.request_count ?? 0) },
    { label: "Recent Errors", value: String(payload?.recent_error_count ?? 0) },
    { label: "Recent Audit", value: String(payload?.recent_audit_count ?? 0) },
    { label: "Latest Request", value: payload?.latest_request_id || "-" },
    { label: "Latest Eval", value: payload?.latest_evaluation_run_id || "-" },
  ]);
}

function renderTrainingSummary() {
  const runs = state.trainingRuns || [];
  const evaluations = state.trainingEvaluations || [];
  renderSummaryChips("#training-summary-grid", [
    { label: "Runs Visible", value: String(runs.length) },
    { label: "Active Runs", value: String(runs.filter((row) => ["pending", "queued", "running"].includes(String(row.status || "").toLowerCase())).length) },
    { label: "Unsloth Runs", value: String(runs.filter((row) => String(row.trainer_backend || "").toLowerCase() === "unsloth").length) },
    { label: "Evaluations Visible", value: String(evaluations.length) },
    { label: "Approved", value: String(evaluations.filter((row) => String(row.promotion_status || "").toLowerCase() === "approved").length) },
  ]);
  refreshTrainingLifecycleView();
}

function buildTrainingLifecycleData() {
  const candidates = state.dataCandidates || [];
  const exportsRows = state.dataExports || [];
  const imports = state.dataImports || [];
  const versions = state.dataVersions || [];
  const runs = state.trainingRuns || [];
  const evaluations = state.trainingEvaluations || [];
  const approvedPromotions = evaluations.filter((row) => String(row.promotion_status || "").toLowerCase() === "approved");
  const tracedInteractions = candidates.reduce((sum, row) => sum + Number(row.interaction_trace_count || 0), 0);
  return {
    stages: [
      {
        key: "interactions",
        title: "Interaction Traces",
        count: tracedInteractions,
        subtitle: `${candidates.length} visible candidate source${candidates.length === 1 ? "" : "s"}`,
        tone: "info",
        actionLabel: "Open Candidates",
        detail: "Cross-protocol traces captured from visible candidate rows. These are the raw learning signals feeding the rest of the pipeline.",
      },
      {
        key: "candidates",
        title: "Candidates",
        count: candidates.length,
        subtitle: `${candidates.filter((row) => String(row.approval_status || "").toLowerCase() === "approved").length} approved`,
        tone: "accent",
        actionLabel: "Open Candidates",
        detail: "Curated records awaiting approval, rejection, or export into reusable datasets.",
      },
      {
        key: "exports",
        title: "Exports",
        count: exportsRows.length,
        subtitle: `${exportsRows.reduce((sum, row) => sum + Number(row.record_count || 0), 0)} visible records`,
        tone: "info",
        actionLabel: "Open Exports",
        detail: "Bundles of approved candidates prepared for downstream import and dataset normalization.",
      },
      {
        key: "datasets",
        title: "Dataset Versions",
        count: versions.length,
        subtitle: `${imports.length} visible import${imports.length === 1 ? "" : "s"}`,
        tone: "warn",
        actionLabel: "Open Datasets",
        detail: "Normalized train/validation/test dataset versions created from imported exports.",
      },
      {
        key: "runs",
        title: "Training Runs",
        count: runs.length,
        subtitle: `${runs.filter((row) => ["pending", "queued", "running"].includes(String(row.status || "").toLowerCase())).length} active`,
        tone: "accent",
        actionLabel: "Open Training Runs",
        detail: "Adapter training work issued against dataset versions and monitored as asynchronous runs.",
      },
      {
        key: "evaluations",
        title: "Evaluations",
        count: evaluations.length,
        subtitle: `${approvedPromotions.length} approved`,
        tone: "ok",
        actionLabel: "Open Evaluations",
        detail: "Quality and promotion decisions scored against completed training runs.",
      },
      {
        key: "promotions",
        title: "Approved Promotions",
        count: approvedPromotions.length,
        subtitle: "Ready for package and deploy flow",
        tone: "ok",
        actionLabel: "Open Custom LLMs",
        detail: "Approved evaluation outcomes ready to become deployed local package capacity and live routing targets.",
      },
    ],
  };
}

function trainingLifecycleGraphFilters() {
  const filters = currentTableContext("#training-lifecycle-graph", "#training-lifecycle-filter-form");
  return {
    stageMode: String(filters.stage_mode || "all"),
    hideEmpty: String(filters.hide_empty || "").toLowerCase() === "on",
  };
}

function renderTrainingLifecycleDetail(stage) {
  const fields = [
    { key: "title", label: "Stage", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
    { key: "count", label: "Visible Count", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
    { key: "subtitle", label: "Summary" },
    { key: "detail", label: "Meaning" },
  ];
  renderRecordView("#training-lifecycle-detail-table", stage || null, fields, {
    emptyState: {
      title: "No graph artifact selected.",
      body: "Click a lifecycle stage in the graph to inspect it here and open its canonical worklist.",
    },
  });
  setText("#training-lifecycle-detail-heading", stage ? stage.title : "Selected Lifecycle Stage");
  setText("#open-training-lifecycle-stage", "Open Selected Artifact");
}

function renderTrainingLifecycleGraph(data) {
  const host = $("#training-lifecycle-graph");
  if (!host) return;
  host.innerHTML = "";
  const filters = trainingLifecycleGraphFilters();
  const modeKeys = {
    all: null,
    data_prep: new Set(["interactions", "candidates", "exports", "datasets"]),
    execution: new Set(["runs", "evaluations"]),
    promotion: new Set(["promotions"]),
  };
  const allowedKeys = modeKeys[filters.stageMode] || null;
  const stages = (data?.stages || [])
    .filter((stage) => !allowedKeys || allowedKeys.has(stage.key))
    .filter((stage) => !filters.hideEmpty || Number(stage.count || 0) > 0);
  if (!stages.length) {
    host.appendChild(buildEmptyState({
      icon: "→",
      title: "No lifecycle stages match the current graph filter.",
      body: "Adjust the lifecycle filter or load more training records to render this flow.",
    }));
    renderSummaryChips("#training-lifecycle-summary-strip", []);
    renderTrainingLifecycleDetail(null);
    return;
  }
  renderSummaryChips("#training-lifecycle-summary-strip", [
    { label: "Visible Traces", value: String(stages.find((stage) => stage.key === "interactions")?.count || 0) },
    { label: "Visible Candidates", value: String(stages.find((stage) => stage.key === "candidates")?.count || 0) },
    { label: "Visible Versions", value: String(stages.find((stage) => stage.key === "datasets")?.count || 0) },
    { label: "Visible Runs", value: String(stages.find((stage) => stage.key === "runs")?.count || 0) },
    { label: "Approved Promotions", value: String(stages.find((stage) => stage.key === "promotions")?.count || 0) },
  ]);
  const graph = document.createElement("div");
  graph.className = "lifecycle-graph";
  stages.forEach((stage, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `lifecycle-node lifecycle-node-${stage.tone || "info"}`;
    if (state.selectedTrainingLifecycleStage === stage.key || (!state.selectedTrainingLifecycleStage && index === 0)) {
      button.classList.add("active");
    }
    button.innerHTML = `
      <span class="lifecycle-node-count">${escapeHtml(formattedValue(stage.count))}</span>
      <span class="lifecycle-node-title">${escapeHtml(stage.title)}</span>
      <span class="lifecycle-node-subtitle">${escapeHtml(stage.subtitle)}</span>
    `;
    button.addEventListener("click", () => {
      state.selectedTrainingLifecycleStage = stage.key;
      renderTrainingLifecycleGraph(data);
    });
    graph.appendChild(button);
    if (index < stages.length - 1) {
      const arrow = document.createElement("div");
      arrow.className = "lifecycle-arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.textContent = "→";
      graph.appendChild(arrow);
    }
  });
  host.appendChild(graph);
  const selected = stages.find((stage) => stage.key === state.selectedTrainingLifecycleStage) || stages[0];
  renderTrainingLifecycleDetail(selected);
}

function refreshTrainingLifecycleView() {
  state.trainingLifecycleData = buildTrainingLifecycleData();
  renderTrainingLifecycleGraph(state.trainingLifecycleData);
}

async function openTrainingLifecycleStageContext(stage = null) {
  const current = stage
    || (state.trainingLifecycleData?.stages || []).find((item) => item.key === state.selectedTrainingLifecycleStage)
    || null;
  if (!current) return;
  if (current.key === "interactions" || current.key === "candidates") {
    switchPanel("data");
    switchCollection("data", "candidates");
    showToast(`Opened candidate curation for ${current.title.toLowerCase()}.`, "ok");
  } else if (current.key === "exports") {
    switchPanel("data");
    switchCollection("data", "exports");
    showToast("Opened dataset exports.", "ok");
  } else if (current.key === "datasets") {
    switchPanel("data");
    switchCollection("data", "datasets");
    showToast("Opened dataset versions.", "ok");
  } else if (current.key === "runs") {
    switchPanel("training");
    switchSubview("training", "workbench");
    switchCollection("training", "runs");
    showToast("Opened training runs.", "ok");
  } else if (current.key === "evaluations") {
    switchPanel("training");
    switchSubview("training", "workbench");
    switchCollection("training", "evaluations");
    showToast("Opened evaluations.", "ok");
  } else if (current.key === "promotions") {
    switchPanel("models");
    switchSubview("models", "catalog");
    switchCollection("modelCatalog", "local");
    showToast("Opened custom LLMs for approved promotion outcomes.", "ok");
  }
}

function renderTrainingRuntimeStatus(payload) {
  state.trainingRuntimeStatus = payload?.available ? payload : null;
  const summaryHost = $("#training-runtime-summary-grid");
  const tableHost = $("#training-runtime-table");
  const dependenciesHost = $("#training-runtime-dependencies");
  if (!summaryHost || !tableHost || !dependenciesHost) return;

  if (!payload || !payload.available) {
    renderMetricGrid("#training-runtime-summary-grid", [
      { label: "Worker Report", badge: statusBadge("blocked"), subvalue: payload?.detail || "No training-worker runtime report has been received yet." },
    ]);
    renderKeyValueTable(
      "#training-runtime-table",
      [{ key: "Status", value: payload?.detail || "No training-worker runtime report has been received yet." }],
      { emptyMessage: "Worker runtime details will appear here once the training-worker reports its Unsloth environment." },
    );
    renderSimpleTable(
      "#training-runtime-dependencies",
      "Dependencies",
      ["Dependency", "Available", "Detail"],
      [],
      () => document.createElement("tr"),
      "Dependency readiness will appear here once the training-worker reports runtime capabilities.",
    );
    return;
  }

  renderMetricGrid("#training-runtime-summary-grid", [
    {
      label: "Worker",
      value: payload.role || "training-worker",
      subvalue: payload.reported_at ? `Reported ${relativeTime(payload.reported_at)}` : "No report timestamp",
    },
    {
      label: "Runtime Ready",
      badge: statusBadge(payload.ready ? "ready" : "blocked"),
      subvalue: payload.backend_import_ready ? "Imports available" : "Imports blocked",
    },
    {
      label: "GPU",
      badge: payload.cuda_available ? '<span class="badge badge-ok">CUDA Ready</span>' : '<span class="badge badge-err">Unavailable</span>',
      subvalue: `${formattedValue(payload.device_count ?? 0)} device(s)`,
    },
    {
      label: "Libraries",
      value: payload.unsloth_version || "Unsloth missing",
      subvalue: payload.torch_version ? `Torch ${payload.torch_version}` : "Torch not reported",
    },
  ]);
  renderKeyValueTable(
    "#training-runtime-table",
    [
      { key: "Reported At", value: payload.reported_at || "-" },
      { key: "Backend Ready", value: payload.backend_import_ready ? "Yes" : "No" },
      { key: "CUDA Available", value: payload.cuda_available ? "Yes" : "No" },
      { key: "Device Count", value: formattedValue(payload.device_count) },
      { key: "Internal Proxy Base URL", value: payload.internal_api_base_url || "-" },
      { key: "Unsloth Command Configured", value: payload.unsloth_command_configured ? "Yes" : "No" },
      { key: "Unsloth Command", value: payload.unsloth_command || "-" },
      { key: "Torch Version", value: payload.torch_version || "-" },
      { key: "Unsloth Version", value: payload.unsloth_version || "-" },
      { key: "Errors", value: (payload.errors || []).join(" | ") || "None" },
      { key: "Warnings", value: (payload.warnings || []).join(" | ") || "None" },
    ],
    { emptyMessage: "Worker runtime details are unavailable." },
  );
  renderSimpleTable(
    "#training-runtime-dependencies",
    "Dependencies",
    ["Dependency", "Available", "Detail"],
    payload.dependencies || [],
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.name || "-")}</strong></td>
        <td>${boolBadge(Boolean(row.available))}</td>
        <td>${escapeHtml(row.detail || "-")}</td>
      `;
      return tr;
    },
    "No dependency readiness reported.",
  );
}

function renderTrainingStudioStatus(payload) {
  state.trainingStudioStatus = payload;
  renderMetricGrid("#training-studio-summary-grid", [
    {
      label: "Studio",
      badge: statusBadge(payload?.enabled ? (payload?.reachable ? "ready" : "pending") : "blocked"),
      subvalue: payload?.enabled ? (payload?.reachable ? "Reachable" : (payload?.detail || "Configured but not reachable")) : "Disabled",
    },
    {
      label: "Password",
      value: payload?.password_configured ? "Configured" : "Missing",
      subvalue: "Jupyter access credential",
    },
    {
      label: "Proxy Routing",
      value: payload?.configured ? "Configured" : "Pending",
      subvalue: "Environment prepared to target LLMProxy",
    },
  ]);
  renderKeyValueTable(
    "#training-studio-table",
    [
      { key: "Enabled", value: payload?.enabled ? "Yes" : "No" },
      { key: "Configured", value: payload?.configured ? "Yes" : "No" },
      { key: "Reachable", value: payload?.reachable ? "Yes" : "No" },
      { key: "External URL", value: payload?.external_url || "-" },
      { key: "Internal URL", value: payload?.internal_url || "-" },
      { key: "HTTP Status", value: formattedValue(payload?.status_code) },
      { key: "Detail", value: payload?.detail || "-" },
      { key: "Notes", value: (payload?.notes || []).join(" | ") || "-" },
    ],
    { emptyMessage: "Studio status will appear here once loaded." },
  );
  const openLink = $("#open-training-studio");
  if (openLink) {
    openLink.href = payload?.external_url || "http://127.0.0.1:8888";
    openLink.classList.toggle("disabled", !payload?.external_url);
    openLink.setAttribute("aria-disabled", payload?.external_url ? "false" : "true");
  }
}

function renderGovernanceSummary() {
  const keys = state.governanceKeys || [];
  const pricingRows = state.pricingRows || [];
  const guardrails = state.guardrailsSettings || {};
  renderSummaryChips("#governance-summary-strip", [
    { label: "Visible Keys", value: String(keys.length) },
    { label: "Active Keys", value: String(keys.filter((row) => row.status === "active").length) },
    { label: "Budgeted", value: String(keys.filter((row) => row.max_budget_usd != null).length) },
    { label: "Priced Models", value: String(pricingRows.length) },
    { label: "Guardrail Hooks", value: String((guardrails.pre_hooks || []).length + (guardrails.post_hooks || []).length) },
  ]);
}

function governanceGraphArtifactKey(artifact) {
  return `${artifact?.kind || "artifact"}:${artifact?.id || ""}`;
}

function governanceGraphEdgeKey(edge) {
  return `${edge?.from || ""}->${edge?.to || ""}`;
}

function buildGovernanceGraphEdgeArtifact(edge, artifactLookup) {
  if (!edge) return null;
  const fromArtifact = artifactLookup.get(edge.from);
  const toArtifact = artifactLookup.get(edge.to);
  if (!fromArtifact || !toArtifact) return null;
  return {
    kind: "edge",
    id: governanceGraphEdgeKey(edge),
    detail: {
      path: `${fromArtifact.title} -> ${toArtifact.title}`,
      from_label: graphArtifactLabel(fromArtifact.kind),
      from_title: fromArtifact.title,
      to_label: graphArtifactLabel(toArtifact.kind),
      to_title: toArtifact.title,
      detail: "Governance relationship path between two governance artifacts.",
    },
    openArtifact: toArtifact,
  };
}

function renderGovernanceGraphDetail(artifact = null) {
  renderRecordView("#governance-graph-detail-table", artifact
    ? (artifact.kind === "edge"
      ? artifact.detail
      : {
        type: graphArtifactLabel(artifact.kind),
        title: artifact.title,
        subtitle: artifact.subtitle,
        collection: artifact.kind === "pricing" ? "Pricing"
          : artifact.kind === "guardrail" ? "Guardrails"
            : "Virtual Keys",
        detail: artifact.kind === "service"
          ? "Global governance plane across keys, cost exposure, and guardrails."
          : artifact.kind === "scope"
            ? "Model scope visible through one or more issued virtual keys."
            : undefined,
      })
    : null,
  artifact?.kind === "edge" ? GRAPH_EDGE_RECORD_FIELDS : GRAPH_ARTIFACT_RECORD_FIELDS, {
    emptyState: {
      title: "No graph artifact selected.",
      body: "Hover or click a governance node or edge in the graph to inspect it here.",
    },
    raw: false,
  });
}

function governanceGraphFilters() {
  const filters = currentTableContext("#governance-graph", "#governance-graph-filter-form");
  return {
    query: String(filters.query || "").trim().toLowerCase(),
    role: String(filters.role || "").trim().toLowerCase(),
    status: String(filters.status || "").trim().toLowerCase(),
    budgetedOnly: String(filters.budgeted_only || "").toLowerCase() === "on",
  };
}

function buildGovernanceGraphData() {
  const filters = governanceGraphFilters();
  const keys = (state.governanceKeys || []).filter((row) => {
    if (filters.role && String(row.role || "").trim().toLowerCase() !== filters.role) return false;
    if (filters.status && String(row.status || "").trim().toLowerCase() !== filters.status) return false;
    if (filters.budgetedOnly && row.max_budget_usd == null) return false;
    if (!filters.query) return true;
    const haystack = [
      row.display_name,
      row.key_prefix,
      row.owner_id,
      row.role,
      row.status,
      ...(Array.isArray(row.models_allowed) ? row.models_allowed : []),
    ].map((value) => String(value || "").toLowerCase()).join(" ");
    return haystack.includes(filters.query);
  });
  const pricingRows = state.pricingRows || [];
  const guardrails = state.guardrailsSettings || {};
  const service = [{
    kind: "service",
    id: "governance-plane",
    title: "Governance Plane",
    subtitle: "Keys, cost controls, and guardrails",
  }];
  const keyArtifacts = keys.map((row) => ({
    kind: "key",
    id: String(row.id || row.key_prefix || ""),
    title: row.display_name || row.key_prefix || "Virtual Key",
    subtitle: `${humanizeLabel(row.role || "api")} • ${humanizeLabel(row.status || "active")}`,
    record: row,
  }));
  const pricedModelMap = new Map(pricingRows.map((row) => [String(row.model || ""), row]));
  const scopeArtifacts = [];
  const pricingArtifacts = [];
  const guardrailArtifacts = [{
    kind: "guardrail",
    id: "guardrail-policy",
    title: "Guardrail Policy",
    subtitle: `${formattedValue((guardrails.pre_hooks || []).length + (guardrails.post_hooks || []).length)} hook(s) • ${guardrails.prompt_injection_blocking_enabled ? "PI blocking" : "PI open"}`,
    record: guardrails,
  }];
  const edges = [];
  const scopeMap = new Map();
  const pricingMap = new Map();
  const addEdge = (from, to) => {
    if (!from || !to) return;
    const key = `${from}->${to}`;
    if (edges.some((edge) => `${edge.from}->${edge.to}` === key)) return;
    edges.push({ from, to });
  };
  keyArtifacts.forEach((artifact) => {
    addEdge("service:governance-plane", governanceGraphArtifactKey(artifact));
    const allowedModels = Array.isArray(artifact.record?.models_allowed) ? artifact.record.models_allowed.filter(Boolean) : [];
    if (!allowedModels.length) {
      const scopeArtifact = scopeMap.get("scope:all-models") || {
        kind: "scope",
        id: "all-models",
        title: "All Models",
        subtitle: "Unrestricted model scope",
      };
      if (!scopeMap.has("scope:all-models")) {
        scopeMap.set("scope:all-models", scopeArtifact);
        scopeArtifacts.push(scopeArtifact);
      }
      addEdge(governanceGraphArtifactKey(artifact), governanceGraphArtifactKey(scopeArtifact));
      return;
    }
    allowedModels.forEach((modelId) => {
      const scopeKey = `scope:${modelId}`;
      const pricingRow = pricedModelMap.get(String(modelId));
      const scopeArtifact = scopeMap.get(scopeKey) || {
        kind: "scope",
        id: String(modelId),
        title: String(modelId),
        subtitle: pricingRow ? `${pricingRow.provider} priced scope` : "Scoped model access",
      };
      if (!scopeMap.has(scopeKey)) {
        scopeMap.set(scopeKey, scopeArtifact);
        scopeArtifacts.push(scopeArtifact);
      }
      addEdge(governanceGraphArtifactKey(artifact), governanceGraphArtifactKey(scopeArtifact));
      if (pricingRow) {
        const pricingKey = buildPricingKey(pricingRow);
        const pricingArtifact = pricingMap.get(pricingKey) || {
          kind: "pricing",
          id: pricingKey,
          title: pricingRow.model,
          subtitle: `${pricingRow.provider} • ${renderAmount(Number(pricingRow.input_cost_per_token || 0) * 1_000_000, { precision: 2 })}/1M in`,
          record: pricingRow,
        };
        if (!pricingMap.has(pricingKey)) {
          pricingMap.set(pricingKey, pricingArtifact);
          pricingArtifacts.push(pricingArtifact);
        }
        addEdge(governanceGraphArtifactKey(scopeArtifact), governanceGraphArtifactKey(pricingArtifact));
      }
    });
  });
  addEdge("service:governance-plane", "guardrail:guardrail-policy");
  return {
    service,
    keys: keyArtifacts,
    scopes: scopeArtifacts,
    pricing: pricingArtifacts,
    guardrails: guardrailArtifacts,
    edges,
  };
}

function refreshGovernanceGraphView() {
  const host = $("#governance-graph");
  if (!host) return;
  const data = buildGovernanceGraphData();
  renderSummaryChips("#governance-graph-summary-strip", [
    { label: "Virtual Keys", value: String(data.keys.length) },
    { label: "Model Scopes", value: String(data.scopes.length) },
    { label: "Priced Models", value: String(data.pricing.length) },
    { label: "Guardrail Policies", value: String(data.guardrails.length) },
  ]);
  host.innerHTML = "";
  if (!data.keys.length && !data.guardrails.length) {
    host.appendChild(buildEmptyState({
      icon: "⇄",
      title: "No graph artifacts available.",
      body: "Issue virtual keys or configure guardrails to render the governance graph.",
    }));
    renderGovernanceGraphDetail(null);
    return;
  }
  const columns = [
    { title: "Governance Plane", items: data.service, x: 40 },
    { title: "Virtual Keys", items: data.keys, x: 290 },
    { title: "Model Scope", items: data.scopes, x: 540 },
    { title: "Pricing & Policy", items: [...data.pricing, ...data.guardrails], x: 790 },
  ];
  const NS = "http://www.w3.org/2000/svg";
  const nodeWidth = 220;
  const nodeHeight = 58;
  const gapY = 18;
  const topY = 42;
  const maxRows = Math.max(...columns.map((column) => Math.max(column.items.length, 1)));
  const height = topY + maxRows * (nodeHeight + gapY) + 30;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 1080 ${height}`);
  svg.setAttribute("class", "topology-graph");
  const positions = new Map();
  const artifactLookup = new Map();
  columns.forEach((column) => {
    const startY = topY + Math.max(0, (maxRows - column.items.length) * (nodeHeight + gapY) * 0.5);
    column.items.forEach((artifact, index) => {
      artifactLookup.set(governanceGraphArtifactKey(artifact), artifact);
      positions.set(governanceGraphArtifactKey(artifact), {
        x: column.x,
        y: startY + index * (nodeHeight + gapY),
      });
    });
    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(column.x));
    title.setAttribute("y", "22");
    title.setAttribute("class", "topology-title");
    title.textContent = column.title;
    svg.appendChild(title);
  });
  data.edges.forEach((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) return;
    const edgeArtifact = buildGovernanceGraphEdgeArtifact(edge, artifactLookup);
    const path = document.createElementNS(NS, "path");
    const startX = from.x + nodeWidth;
    const startY = from.y + nodeHeight / 2;
    const endX = to.x;
    const endY = to.y + nodeHeight / 2;
    const controlX = (startX + endX) / 2;
    path.setAttribute("d", `M ${startX} ${startY} C ${controlX} ${startY}, ${controlX} ${endY}, ${endX} ${endY}`);
    path.setAttribute("class", "topology-edge");
    if (edgeArtifact && edgeArtifact.id === state.selectedGovernanceGraphEdgeKey) {
      path.classList.add("active");
    }
    path.setAttribute("tabindex", "0");
    const activateEdge = () => {
      if (!edgeArtifact) return;
      state.selectedGovernanceGraphEdgeKey = edgeArtifact.id;
      state.selectedGovernanceGraphKey = null;
      renderGovernanceGraphDetail(edgeArtifact);
    };
    path.addEventListener("mouseenter", activateEdge);
    path.addEventListener("focus", activateEdge);
    path.addEventListener("click", activateEdge);
    path.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activateEdge();
      await openGovernanceGraphContext(edgeArtifact);
    });
    svg.appendChild(path);
  });
  columns.flatMap((column) => column.items).forEach((artifact) => {
    const pos = positions.get(governanceGraphArtifactKey(artifact));
    if (!pos) return;
    const className = artifact.kind === "service" ? "topology-node-service"
      : artifact.kind === "key" ? "topology-node-key"
        : artifact.kind === "scope" ? "topology-node-scope"
          : artifact.kind === "pricing" ? "topology-node-pricing"
            : "topology-node-guardrail";
    const group = document.createElementNS(NS, "g");
    group.setAttribute("class", `topology-node ${className}`);
    if (governanceGraphArtifactKey(artifact) === state.selectedGovernanceGraphKey) {
      group.classList.add("active");
    }
    group.setAttribute("tabindex", "0");
    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("x", String(pos.x));
    rect.setAttribute("y", String(pos.y));
    rect.setAttribute("rx", "12");
    rect.setAttribute("ry", "12");
    rect.setAttribute("width", String(nodeWidth));
    rect.setAttribute("height", String(nodeHeight));
    group.appendChild(rect);
    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(pos.x + 14));
    title.setAttribute("y", String(pos.y + 24));
    title.setAttribute("class", "topology-node-title");
    title.textContent = artifact.title;
    group.appendChild(title);
    const subtitle = document.createElementNS(NS, "text");
    subtitle.setAttribute("x", String(pos.x + 14));
    subtitle.setAttribute("y", String(pos.y + 43));
    subtitle.setAttribute("class", "topology-node-subtitle");
    subtitle.textContent = artifact.subtitle;
    group.appendChild(subtitle);
    const activate = () => {
      state.selectedGovernanceGraphEdgeKey = null;
      state.selectedGovernanceGraphKey = governanceGraphArtifactKey(artifact);
      renderGovernanceGraphDetail(artifact);
      refreshGovernanceGraphView();
    };
    group.addEventListener("mouseenter", activate);
    group.addEventListener("focus", activate);
    group.addEventListener("click", activate);
    group.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activate();
      await openGovernanceGraphContext(artifact);
    });
    svg.appendChild(group);
  });
  mountInteractiveSvgGraph(host, svg, { graphKey: "#governance-graph", baseWidth: 1080, baseHeight: height });
  const selectedEdge = state.selectedGovernanceGraphEdgeKey
    ? buildGovernanceGraphEdgeArtifact((data.edges || []).find((edge) => governanceGraphEdgeKey(edge) === state.selectedGovernanceGraphEdgeKey), artifactLookup)
    : null;
  const selectedArtifact = columns.flatMap((column) => column.items)
    .find((artifact) => governanceGraphArtifactKey(artifact) === state.selectedGovernanceGraphKey)
    || data.keys[0]
    || data.pricing[0]
    || data.guardrails[0]
    || data.service[0]
    || null;
  renderGovernanceGraphDetail(selectedEdge || selectedArtifact);
}

function currentSelectedGovernanceGraphArtifact() {
  const data = buildGovernanceGraphData();
  const artifactLookup = new Map();
  [...(data.service || []), ...(data.keys || []), ...(data.scopes || []), ...(data.pricing || []), ...(data.guardrails || [])]
    .forEach((artifact) => artifactLookup.set(governanceGraphArtifactKey(artifact), artifact));
  if (state.selectedGovernanceGraphEdgeKey) {
    const edge = (data.edges || []).find((item) => governanceGraphEdgeKey(item) === state.selectedGovernanceGraphEdgeKey);
    const edgeArtifact = buildGovernanceGraphEdgeArtifact(edge, artifactLookup);
    if (edgeArtifact) return edgeArtifact;
  }
  const items = [...(data.service || []), ...(data.keys || []), ...(data.scopes || []), ...(data.pricing || []), ...(data.guardrails || [])];
  return items.find((artifact) => governanceGraphArtifactKey(artifact) === state.selectedGovernanceGraphKey) || null;
}

async function openGovernanceGraphContext(artifact) {
  if (!artifact) return;
  if (artifact.kind === "edge" && artifact.openArtifact) {
    artifact = artifact.openArtifact;
  }
  if (artifact.kind === "service") {
    showToast("The governance plane applies scoped access, pricing exposure, and global guardrail policy to llmProxy traffic.", "info");
    return;
  }
  if (artifact.kind === "key") {
    switchCollection("governance", "keys");
    if (artifact.record) {
      inspectVirtualKey(artifact.record);
    }
    return;
  }
  if (artifact.kind === "pricing") {
    switchCollection("governance", "pricing");
    if (artifact.record) {
      inspectPricingRow(artifact.record);
    }
    return;
  }
  if (artifact.kind === "guardrail") {
    switchCollection("governance", "guardrails");
    renderRecordView("#guardrails-output", artifact.record || {}, GUARDRAILS_RECORD_FIELDS, {
      rawLabel: "View raw guardrail payload",
      emptyState: { title: "No guardrail detail available.", body: "Refresh guardrails to inspect the current policy here." },
    });
    return;
  }
  switchCollection("governance", "keys");
  showToast(`Opened key directory for scope ${artifact.title}.`, "info");
}

function renderIntegrationsSummary() {
  const providerGuides = state.providerGuides || [];
  const mcpServers = state.mcpServers || [];
  const a2aPeers = state.a2aPeers || [];
  const restEndpoints = state.restEndpoints || [];
  renderSummaryChips("#integrations-summary-strip", [
    { label: "Reference Guides", value: String(providerGuides.length) },
    { label: "Configured Guides", value: String(providerGuides.filter((row) => row.configured).length) },
    { label: "MCP Servers", value: String(mcpServers.length) },
    { label: "MCP Tools", value: String(mcpServers.reduce((sum, row) => sum + Number(row.tool_count || 0), 0)) },
    { label: "A2A Peers", value: String(a2aPeers.length) },
    { label: "A2A Capabilities", value: String(a2aPeers.reduce((sum, row) => sum + Number(row.capability_count || 0), 0)) },
    { label: "REST Endpoints", value: String(restEndpoints.length) },
    { label: "REST Configured", value: String(restEndpoints.filter((row) => row.configured).length) },
  ]);
}

function integrationGraphArtifactKey(artifact) {
  return `${artifact?.kind || "artifact"}:${artifact?.id || ""}`;
}

function integrationGraphEdgeKey(edge) {
  return `${edge?.from || ""}->${edge?.to || ""}`;
}

function buildIntegrationGraphEdgeArtifact(edge, artifactLookup) {
  if (!edge) return null;
  const fromArtifact = artifactLookup.get(edge.from);
  const toArtifact = artifactLookup.get(edge.to);
  if (!fromArtifact || !toArtifact) return null;
  return {
    kind: "edge",
    id: integrationGraphEdgeKey(edge),
    detail: {
      path: `${fromArtifact.title} -> ${toArtifact.title}`,
      from_label: graphArtifactLabel(fromArtifact.kind),
      from_title: fromArtifact.title,
      to_label: graphArtifactLabel(toArtifact.kind),
      to_title: toArtifact.title,
      detail: "Execution path between protocol surface and integration endpoint.",
    },
    openArtifact: toArtifact,
  };
}

function renderIntegrationsGraphDetail(artifact = null) {
  renderRecordView("#integrations-graph-detail-table", artifact
    ? (artifact.kind === "edge"
      ? artifact.detail
      : {
        type: graphArtifactLabel(artifact.kind),
        title: artifact.title,
        subtitle: artifact.subtitle,
        collection: artifact.collection ? humanizeLabel(artifact.collection) : undefined,
        detail: artifact.kind === "service"
          ? "Central integration proxy across MCP, A2A, and REST endpoint surfaces."
          : artifact.kind === "protocol"
            ? "Protocol surface grouping one or more executable endpoints."
            : "Executable integration endpoint available through this protocol surface.",
      })
    : null,
  artifact?.kind === "edge" ? GRAPH_EDGE_RECORD_FIELDS : GRAPH_ARTIFACT_RECORD_FIELDS, {
    emptyState: {
      title: "No graph artifact selected.",
      body: "Hover or click an integration node or edge in the graph to inspect it here.",
    },
    raw: false,
  });
}

function integrationsGraphFilters() {
  const filters = currentTableContext("#integrations-graph", "#integrations-graph-filter-form");
  return {
    query: String(filters.query || "").trim().toLowerCase(),
    protocol: String(filters.protocol || "").trim().toLowerCase(),
  };
}

function buildIntegrationGraphData() {
  const filters = integrationsGraphFilters();
  const service = [{
    kind: "service",
    id: "llmproxy-integrations",
    title: "llmProxy",
    subtitle: "Unified integration proxy",
  }];
  const protocols = [
    {
      kind: "protocol",
      id: "mcp",
      title: "MCP",
      subtitle: `${formattedValue((state.mcpServers || []).length)} server(s)`,
      collection: "mcp",
    },
    {
      kind: "protocol",
      id: "a2a",
      title: "A2A",
      subtitle: `${formattedValue((state.a2aPeers || []).length)} peer(s)`,
      collection: "a2a",
    },
    {
      kind: "protocol",
      id: "rest",
      title: "REST",
      subtitle: `${formattedValue((state.restEndpoints || []).length)} endpoint(s)`,
      collection: "rest",
    },
  ];
  const endpoints = [];
  const edges = [];
  const endpointVisible = (row, collection, values = []) => {
    if (filters.protocol && filters.protocol !== collection) return false;
    if (!filters.query) return true;
    const haystack = values.map((value) => String(value || "").toLowerCase()).join(" ");
    return haystack.includes(filters.query) || collection.includes(filters.query);
  };
  const addEdge = (from, to) => {
    if (!from || !to) return;
    const key = `${from}->${to}`;
    if (edges.some((edge) => `${edge.from}->${edge.to}` === key)) return;
    edges.push({ from, to });
  };
  const visibleCollections = new Set();
  (state.mcpServers || []).forEach((row) => {
    if (!endpointVisible(row, "mcp", [row.server, row.tool_count])) return;
    const artifact = {
      kind: "endpoint",
      id: `mcp:${row.server}`,
      title: row.server || "MCP Server",
      subtitle: `${formattedValue(row.tool_count || 0)} tool(s)`,
      collection: "mcp",
      recordKey: row.server,
    };
    endpoints.push(artifact);
    visibleCollections.add("mcp");
    addEdge("protocol:mcp", integrationGraphArtifactKey(artifact));
  });
  (state.a2aPeers || []).forEach((row) => {
    if (!endpointVisible(row, "a2a", [row.peer, row.label, row.capability_count])) return;
    const artifact = {
      kind: "endpoint",
      id: `a2a:${row.peer}`,
      title: row.label || row.peer || "A2A Peer",
      subtitle: `${formattedValue(row.capability_count || 0)} capability(ies)`,
      collection: "a2a",
      recordKey: row.peer,
    };
    endpoints.push(artifact);
    visibleCollections.add("a2a");
    addEdge("protocol:a2a", integrationGraphArtifactKey(artifact));
  });
  (state.restEndpoints || []).forEach((row) => {
    if (!endpointVisible(row, "rest", [row.endpoint_name, row.label, row.default_method, row.auth_mode])) return;
    const artifact = {
      kind: "endpoint",
      id: `rest:${row.endpoint_name}`,
      title: row.label || row.endpoint_name || "REST Endpoint",
      subtitle: `${String(row.default_method || "POST").toUpperCase()} • ${humanizeLabel(row.auth_mode || "none")}`,
      collection: "rest",
      recordKey: row.endpoint_name,
    };
    endpoints.push(artifact);
    visibleCollections.add("rest");
    addEdge("protocol:rest", integrationGraphArtifactKey(artifact));
  });
  const visibleProtocols = protocols.filter((protocol) => {
    if (filters.protocol) {
      return protocol.collection === filters.protocol;
    }
    if (!filters.query) {
      return true;
    }
    return visibleCollections.has(protocol.collection) || String(protocol.title || "").toLowerCase().includes(filters.query);
  });
  visibleProtocols.forEach((protocol) => {
    addEdge("service:llmproxy-integrations", integrationGraphArtifactKey(protocol));
  });
  return { service, protocols: visibleProtocols, endpoints, edges };
}

function refreshIntegrationGraphView() {
  const host = $("#integrations-graph");
  if (!host) return;
  const data = buildIntegrationGraphData();
  renderSummaryChips("#integrations-graph-summary-strip", [
    { label: "Protocol Surfaces", value: String(data.protocols.length) },
    { label: "Executable Endpoints", value: String(data.endpoints.length) },
    { label: "Edges", value: String(data.edges.length) },
    { label: "Reference Guides", value: String((state.providerGuides || []).length) },
  ]);
  host.innerHTML = "";
  if (!data.endpoints.length) {
    host.appendChild(buildEmptyState({
      icon: "⇄",
      title: "No graph artifacts available.",
      body: "Configure MCP servers, A2A peers, or REST endpoints to render the integrations graph.",
    }));
    renderIntegrationsGraphDetail(null);
    return;
  }
  const columns = [
    { title: "Integration Proxy", items: data.service, x: 40 },
    { title: "Protocol Surface", items: data.protocols, x: 340 },
    { title: "Endpoints", items: data.endpoints, x: 640 },
  ];
  const NS = "http://www.w3.org/2000/svg";
  const nodeWidth = 230;
  const nodeHeight = 58;
  const gapY = 18;
  const topY = 42;
  const maxRows = Math.max(...columns.map((column) => Math.max(column.items.length, 1)));
  const height = topY + maxRows * (nodeHeight + gapY) + 30;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 930 ${height}`);
  svg.setAttribute("class", "topology-graph");
  const positions = new Map();
  const artifactLookup = new Map();
  columns.forEach((column) => {
    const startY = topY + Math.max(0, (maxRows - column.items.length) * (nodeHeight + gapY) * 0.5);
    column.items.forEach((artifact, index) => {
      artifactLookup.set(integrationGraphArtifactKey(artifact), artifact);
      positions.set(integrationGraphArtifactKey(artifact), {
        x: column.x,
        y: startY + index * (nodeHeight + gapY),
      });
    });
    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(column.x));
    title.setAttribute("y", "22");
    title.setAttribute("class", "topology-title");
    title.textContent = column.title;
    svg.appendChild(title);
  });
  data.edges.forEach((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) return;
    const edgeArtifact = buildIntegrationGraphEdgeArtifact(edge, artifactLookup);
    const path = document.createElementNS(NS, "path");
    const startX = from.x + nodeWidth;
    const startY = from.y + nodeHeight / 2;
    const endX = to.x;
    const endY = to.y + nodeHeight / 2;
    const controlX = (startX + endX) / 2;
    path.setAttribute("d", `M ${startX} ${startY} C ${controlX} ${startY}, ${controlX} ${endY}, ${endX} ${endY}`);
    path.setAttribute("class", "topology-edge");
    if (edgeArtifact && edgeArtifact.id === state.selectedIntegrationsGraphEdgeKey) {
      path.classList.add("active");
    }
    path.setAttribute("tabindex", "0");
    const activateEdge = () => {
      if (!edgeArtifact) return;
      state.selectedIntegrationsGraphEdgeKey = edgeArtifact.id;
      state.selectedIntegrationsGraphKey = null;
      renderIntegrationsGraphDetail(edgeArtifact);
    };
    path.addEventListener("mouseenter", activateEdge);
    path.addEventListener("focus", activateEdge);
    path.addEventListener("click", activateEdge);
    path.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activateEdge();
      await openIntegrationGraphContext(edgeArtifact);
    });
    svg.appendChild(path);
  });
  columns.flatMap((column) => column.items).forEach((artifact) => {
    const pos = positions.get(integrationGraphArtifactKey(artifact));
    if (!pos) return;
    const group = document.createElementNS(NS, "g");
    const nodeClass = artifact.kind === "service" ? "topology-node-service"
      : artifact.kind === "protocol" ? "topology-node-protocol"
        : "topology-node-endpoint";
    group.setAttribute("class", `topology-node ${nodeClass}`);
    if (integrationGraphArtifactKey(artifact) === state.selectedIntegrationsGraphKey) {
      group.classList.add("active");
    }
    group.setAttribute("tabindex", "0");
    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("x", String(pos.x));
    rect.setAttribute("y", String(pos.y));
    rect.setAttribute("rx", "12");
    rect.setAttribute("ry", "12");
    rect.setAttribute("width", String(nodeWidth));
    rect.setAttribute("height", String(nodeHeight));
    group.appendChild(rect);
    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(pos.x + 14));
    title.setAttribute("y", String(pos.y + 24));
    title.setAttribute("class", "topology-node-title");
    title.textContent = artifact.title;
    group.appendChild(title);
    const subtitle = document.createElementNS(NS, "text");
    subtitle.setAttribute("x", String(pos.x + 14));
    subtitle.setAttribute("y", String(pos.y + 43));
    subtitle.setAttribute("class", "topology-node-subtitle");
    subtitle.textContent = artifact.subtitle;
    group.appendChild(subtitle);
    const activate = () => {
      state.selectedIntegrationsGraphEdgeKey = null;
      state.selectedIntegrationsGraphKey = integrationGraphArtifactKey(artifact);
      renderIntegrationsGraphDetail(artifact);
      refreshIntegrationGraphView();
    };
    group.addEventListener("mouseenter", activate);
    group.addEventListener("focus", activate);
    group.addEventListener("click", activate);
    group.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activate();
      await openIntegrationGraphContext(artifact);
    });
    svg.appendChild(group);
  });
  mountInteractiveSvgGraph(host, svg, { graphKey: "#integrations-graph", baseWidth: 930, baseHeight: height });
  const selectedEdge = state.selectedIntegrationsGraphEdgeKey
    ? buildIntegrationGraphEdgeArtifact((data.edges || []).find((edge) => integrationGraphEdgeKey(edge) === state.selectedIntegrationsGraphEdgeKey), artifactLookup)
    : null;
  const selectedArtifact = columns.flatMap((column) => column.items)
    .find((artifact) => integrationGraphArtifactKey(artifact) === state.selectedIntegrationsGraphKey)
    || data.endpoints[0]
    || data.protocols[0]
    || data.service[0]
    || null;
  renderIntegrationsGraphDetail(selectedEdge || selectedArtifact);
}

function currentSelectedIntegrationsGraphArtifact() {
  const data = buildIntegrationGraphData();
  const artifactLookup = new Map();
  [...(data.service || []), ...(data.protocols || []), ...(data.endpoints || [])]
    .forEach((artifact) => artifactLookup.set(integrationGraphArtifactKey(artifact), artifact));
  if (state.selectedIntegrationsGraphEdgeKey) {
    const edge = (data.edges || []).find((item) => integrationGraphEdgeKey(item) === state.selectedIntegrationsGraphEdgeKey);
    const edgeArtifact = buildIntegrationGraphEdgeArtifact(edge, artifactLookup);
    if (edgeArtifact) return edgeArtifact;
  }
  const items = [...(data.service || []), ...(data.protocols || []), ...(data.endpoints || [])];
  return items.find((artifact) => integrationGraphArtifactKey(artifact) === state.selectedIntegrationsGraphKey) || null;
}

async function openIntegrationGraphContext(artifact) {
  if (!artifact) return;
  if (artifact.kind === "edge" && artifact.openArtifact) {
    artifact = artifact.openArtifact;
  }
  if (artifact.kind === "service") {
    showToast("llmProxy is the central integration proxy between protocol surfaces and executable endpoints.", "info");
    return;
  }
  if (artifact.kind === "protocol") {
    switchCollection("integrations", artifact.collection);
    showToast(`Opened ${artifact.title} endpoint directory.`, "ok");
    return;
  }
  switchCollection("integrations", artifact.collection);
  if (artifact.collection === "mcp") {
    const row = (state.mcpServers || []).find((item) => String(item.server || "") === String(artifact.recordKey || ""));
    if (row) inspectMcpServer(row);
  } else if (artifact.collection === "a2a") {
    const row = (state.a2aPeers || []).find((item) => String(item.peer || "") === String(artifact.recordKey || ""));
    if (row) inspectA2APeer(row);
  } else if (artifact.collection === "rest") {
    const row = (state.restEndpoints || []).find((item) => String(item.endpoint_name || "") === String(artifact.recordKey || ""));
    if (row) inspectRestEndpoint(row);
  }
}

function renderPromptSummary() {
  const prompts = promptTemplateInventoryRows();
  const uniqueNames = new Set(prompts.map((row) => row.name).filter(Boolean));
  const totalRequests = prompts.reduce((sum, row) => sum + Number(row.metrics?.request_count || 0), 0);
  const totalCandidates = prompts.reduce((sum, row) => sum + Number(row.metrics?.candidate_count || 0), 0);
  const activeVersions = prompts.filter((row) => String(row.status || "").toLowerCase() === "active").length;
  const challengerRollouts = prompts.filter((row) => row.rollout?.mode === "canary").length;
  renderSummaryChips("#prompts-summary-strip", [
    { label: "Visible Versions", value: String(prompts.length) },
    { label: "Template Names", value: String(uniqueNames.size) },
    { label: "Active Versions", value: String(activeVersions) },
    { label: "Challenger Rollouts", value: String(challengerRollouts) },
    { label: "Requests", value: String(totalRequests) },
    { label: "Candidates", value: String(totalCandidates) },
    { label: "With Variables", value: String(prompts.filter((row) => (row.variables || []).length).length) },
    { label: "Model Overrides", value: String(prompts.filter((row) => row.model_override).length) },
  ]);
}

function renderOverviewSummary() {
  const health = state.healthPayload || {};
  const config = state.configPayload || {};
  const providerConfigured = health.provider_families_configured || {};
  const providerCount = Object.keys(providerConfigured).length;
  const configuredCount = Object.values(providerConfigured).filter(Boolean).length;
  const providerReadiness = Array.isArray(health.provider_readiness) ? health.provider_readiness : [];
  const healthyVendors = providerReadiness.filter((item) => item.status === "healthy").length;
  const connectedVendors = providerReadiness.filter((item) => item.status === "healthy" || item.status === "partial").length;
  renderSummaryChips("#overview-summary-strip", [
    { label: "Environment", value: health.environment || "-" },
    { label: "Database", value: health.database_backend || "-" },
    { label: "Redis", value: health.redis_configured ? "Configured" : "Missing" },
    { label: "Providers", value: providerCount ? `${configuredCount}/${providerCount}` : "0" },
    { label: "Healthy Vendors", value: String(healthyVendors) },
    { label: "Connected Vendors", value: String(connectedVendors) },
    { label: "Routing Strategy", value: config.llmproxy_routing_strategy || "-" },
  ]);
}

function statusBadge(value) {
  const map = {
    connected: ["ok", "Connected"],
    configured: ["ok", "Configured"],
    completed: ["ok", "Completed"],
    approved: ["ok", "Approved"],
    ready: ["ok", "Ready"],
    healthy: ["ok", "Healthy"],
    success: ["ok", "Success"],
    running: ["info", "Running"],
    active: ["info", "Active"],
    processing: ["info", "Processing"],
    draft: ["warn", "Draft"],
    pending: ["warn", "Pending"],
    queued: ["warn", "Queued"],
    partial: ["warn", "Partial"],
    unavailable: ["warn", "Unavailable"],
    mixed: ["warn", "Mixed"],
    needs_review: ["warn", "Needs Review"],
    deprecated: ["muted", "Deprecated"],
    archived: ["muted", "Archived"],
    missing_config: ["err", "Missing Config"],
    blocked: ["err", "Blocked"],
    unprocessed: ["warn", "Unprocessed"],
    failure: ["err", "Failure"],
    failed: ["err", "Failed"],
    rejected: ["err", "Rejected"],
    canceled: ["err", "Canceled"],
    unknown: ["muted", "Unknown"],
  };
  const normalized = String(value ?? "").toLowerCase();
  const [tone, label] = map[normalized] || ["muted", value ?? "-"];
  return `<span class="badge badge-${tone}">${escapeHtml(label)}</span>`;
}

function boolBadge(value) {
  return value
    ? '<span class="badge badge-ok">Yes</span>'
    : '<span class="badge badge-muted">No</span>';
}

function relativeTime(isoString) {
  if (!isoString) return "-";
  const timestamp = new Date(isoString).getTime();
  if (Number.isNaN(timestamp)) return String(isoString);
  const diff = Date.now() - timestamp;
  const future = diff < 0;
  const minutes = Math.floor(Math.abs(diff) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return future ? `in ${minutes}m` : `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return future ? `in ${hours}h` : `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return future ? `in ${days}d` : `${days}d ago`;
}

function timeLabel(isoString) {
  if (!isoString) return "-";
  return `<span title="${escapeHtml(isoString)}">${escapeHtml(relativeTime(isoString))}</span>`;
}

function setFieldValue(formSelector, name, value) {
  const field = document.querySelector(`${formSelector} [name="${name}"]`);
  if (field) {
    if (field.type === "checkbox") {
      field.checked = Boolean(value);
      return;
    }
    field.value = value ?? "";
  }
}

function collectFormFilters(formSelector) {
  const form = $(formSelector);
  if (!form) return {};
  const data = new FormData(form);
  const filters = {};
  for (const [key, value] of data.entries()) {
    const normalized = String(value || "").trim();
    if (normalized) {
      filters[key] = normalized;
    }
  }
  return filters;
}

function setFormFilters(formSelector, filters = {}) {
  const fields = Array.from(document.querySelectorAll(`${formSelector} [name]`));
  fields.forEach((field) => {
    const name = field.getAttribute("name");
    setFieldValue(formSelector, name, filters[name] || "");
  });
}

function setOperationalEventFilters(filters = {}) {
  const next = {
    history_scope: "active",
    event_class: "",
    event_source: "",
    level: "",
    component: "",
    category: "",
    listener_id: "",
    selected_provider: "",
    selected_model: "",
    selected_pool_id: "",
    selected_node_id: "",
    prompt_template_name: "",
    prompt_template_version: "",
    prompt_template_selection_mode: "",
    traffic_origin: "",
    automation_scope: "",
    domain: "",
    task_type: "",
    created_after: "",
    created_before: "",
    promotable_only: "",
    sort_by: "timestamp",
    sort_dir: "desc",
    ...filters,
  };
  setFormFilters("#ops-events-filter-form", next);
  renderOpsEventTrafficFilterOptions();
  setFieldValue("#ops-events-filter-form", "selected_provider", next.selected_provider || "");
  renderOpsEventTrafficFilterOptions();
  setFieldValue("#ops-events-filter-form", "selected_model", next.selected_model || "");
  setFieldValue("#ops-events-filter-form", "selected_pool_id", next.selected_pool_id || "");
  setFieldValue("#ops-events-filter-form", "selected_node_id", next.selected_node_id || "");
  renderAllPromptTemplatePickers();
  setFieldValue("#ops-events-filter-form", "prompt_template_name", next.prompt_template_name || "");
  setFieldValue("#ops-events-filter-form", "prompt_template_version", next.prompt_template_version || "");
  setFieldValue("#ops-events-filter-form", "prompt_template_selection_mode", next.prompt_template_selection_mode || "");
  setFieldValue("#ops-events-filter-form", "traffic_origin", next.traffic_origin || "");
  setFieldValue("#ops-events-filter-form", "automation_scope", next.automation_scope || "");
  renderOpsEventTrafficScopeVisibility();
  rememberTableContext("#ops-events-table", collectFormFilters("#ops-events-filter-form"));
}

const opsSavedPresetDefinitions = {
  traffic: { label: "Traffic", fallback: { event_class: "request", event_source: "request", sort_by: "timestamp", sort_dir: "desc" } },
  errors: { label: "Errors", fallback: { event_class: "error", sort_by: "timestamp", sort_dir: "desc" } },
  audit: { label: "Audit", fallback: { event_class: "audit", sort_by: "timestamp", sort_dir: "desc" } },
  training: { label: "Training-Relevant", fallback: { promotable_only: "true", sort_by: "timestamp", sort_dir: "desc" } },
};

const opsEventSortLabels = {
  timestamp: "Time",
  event_class: "Event class",
  event_source: "Event source",
  level: "Level",
  component: "Component",
  category: "Category",
  listener_id: "Listener",
  selected_provider: "Provider",
  selected_model: "Selected model",
  requested_model: "Requested model",
  latency_ms: "Total latency",
  first_response_latency_ms: "First response latency",
  cost_estimate: "Cost per request",
  input_tokens: "Input tokens",
  output_tokens: "Output tokens",
  total_tokens: "Total tokens",
  traffic_origin: "Traffic origin",
  domain: "Domain",
  task_type: "Task type",
  message: "Message",
};

const opsEventHistoryScopeLabels = {
  active: "Active Only",
  all: "Active + Historical",
  historical: "Historical Only",
};

function currentOpsEventColumnPreset() {
  return ["adaptive", "events", "traffic"].includes(state.opsEventColumnPreset) ? state.opsEventColumnPreset : "adaptive";
}

function setOpsEventColumnPreset(mode) {
  state.opsEventColumnPreset = ["adaptive", "events", "traffic"].includes(mode) ? mode : "adaptive";
  persistTableState();
}

function currentSavedOpsPreset(slot) {
  const saved = state.savedOpsPresets?.[slot];
  if (saved && typeof saved === "object" && Object.keys(saved).length) {
    return { ...saved };
  }
  return { ...(opsSavedPresetDefinitions[slot]?.fallback || {}) };
}

function saveCurrentOpsPreset(slot) {
  if (!opsSavedPresetDefinitions[slot]) return;
  state.savedOpsPresets[slot] = collectFormFilters("#ops-events-filter-form");
  persistTableState();
}

function renderOpsColumnPresetControls() {
  const active = currentOpsEventColumnPreset();
  [
    ["#ops-columns-adaptive", "adaptive"],
    ["#ops-columns-events", "events"],
    ["#ops-columns-traffic", "traffic"],
  ].forEach(([selector, mode]) => {
    const button = $(selector);
    if (!button) return;
    button.classList.toggle("active", active === mode);
    button.setAttribute("aria-pressed", active === mode ? "true" : "false");
  });
}

function renderSavedOpsPresetControls() {
  Object.entries(opsSavedPresetDefinitions).forEach(([slot, definition]) => {
    const button = $(`#ops-load-saved-${slot}`);
    if (!button) return;
    const hasSaved = Boolean(state.savedOpsPresets?.[slot] && Object.keys(state.savedOpsPresets[slot]).length);
    button.textContent = hasSaved ? `${definition.label}*` : definition.label;
  });
}

function resolveOpsViewLabel(filters = {}) {
  if (String(filters.event_source || "").toLowerCase() === "request" || String(filters.event_class || "").toLowerCase() === "request") {
    return "Traffic";
  }
  if (String(filters.event_class || "").toLowerCase() === "error") {
    return "Errors";
  }
  if (String(filters.event_class || "").toLowerCase() === "audit") {
    return "Audit";
  }
  if (String(filters.promotable_only || "").toLowerCase() === "true") {
    return "Training-Relevant";
  }
  return "Custom";
}

function renderOpsActiveViewStrip() {
  const filters = collectFormFilters("#ops-events-filter-form");
  const chips = [
    { label: "View", value: resolveOpsViewLabel(filters) },
    { label: "Visibility", value: opsEventHistoryScopeLabels[filters.history_scope || "active"] || "Active Only" },
    { label: "Columns", value: humanizeLabel(currentOpsEventColumnPreset()) },
    {
      label: "Sort",
      value: `${opsEventSortLabels[filters.sort_by || "timestamp"] || humanizeLabel(filters.sort_by || "timestamp")} · ${String(filters.sort_dir || "desc").toLowerCase() === "asc" ? "Ascending" : "Descending"}`,
    },
  ];
  if (filters.listener_id) chips.push({ label: "Listener", value: filters.listener_id });
  if (filters.selected_provider) chips.push({ label: "Provider", value: filters.selected_provider });
  if (filters.selected_model) chips.push({ label: "Model", value: filters.selected_model });
  if (filters.prompt_template_name) chips.push({ label: "Prompt", value: filters.prompt_template_name });
  if (filters.prompt_template_version) chips.push({ label: "Prompt Version", value: filters.prompt_template_version });
  if (filters.prompt_template_selection_mode) chips.push({ label: "Prompt Rollout", value: humanizeLabel(filters.prompt_template_selection_mode) });
  if (filters.domain) chips.push({ label: "Domain", value: filters.domain });
  if (filters.task_type) chips.push({ label: "Task", value: filters.task_type });
  if (filters.created_after || filters.created_before) {
    chips.push({
      label: "Time window",
      value: [filters.created_after || "start", filters.created_before || "now"].join(" → "),
    });
  }
  renderSummaryChips("#ops-active-view-strip", chips);
}

function opsEventColumnModeForRows(rows = []) {
  const active = currentOpsEventColumnPreset();
  if (active !== "adaptive") return active;
  return rows.length > 0 && rows.every((row) => row?.event_source === "request") ? "traffic" : "events";
}

function restorePersistentTableContexts() {
  const bindings = [
    ["#llm-timeseries-charts", "#llm-timeseries-filter-form"],
    ["#candidates-table", "#candidates-filter-form"],
    ["#training-table", "#training-filter-form"],
    ["#evaluation-table", "#evaluation-filter-form"],
    ["#jobs-table", "#jobs-filter-form"],
    ["#events-table", "#events-filter-form"],
    ["#ops-events-table", "#ops-events-filter-form"],
    ["#exports-table", "#exports-filter-form"],
    ["#dataset-imports-table", "#dataset-imports-filter-form"],
    ["#dataset-versions-table", "#dataset-versions-filter-form"],
    ["#governance-graph", "#governance-graph-filter-form"],
    ["#integrations-graph", "#integrations-graph-filter-form"],
    ["#training-lifecycle-graph", "#training-lifecycle-filter-form"],
  ];
  bindings.forEach(([pageKey, formSelector]) => {
    const context = state.tableContexts[pageKey];
    if (context && Object.keys(context).length) {
      setFormFilters(formSelector, context);
    }
  });
}

async function openRequestHistoryContext(filters = {}) {
  switchPanel("operations");
  switchSubview("operations", "monitor");
  setOpsEventColumnPreset("traffic");
  setOperationalEventFilters({
    event_source: "request",
    event_class: "request",
    listener_id: filters.listener_id || "",
    selected_provider: filters.selected_provider || "",
    selected_model: filters.selected_model || "",
    prompt_template_name: filters.prompt_template_name || "",
    prompt_template_version: filters.prompt_template_version || "",
    prompt_template_selection_mode: filters.prompt_template_selection_mode || "",
    selected_pool_id: filters.selected_pool_id || "",
    selected_node_id: filters.selected_node_id || "",
    traffic_origin: filters.traffic_origin || "",
    automation_scope: filters.automation_scope || "",
    domain: filters.domain || "",
    task_type: filters.task_type || "",
    created_after: filters.created_after || "",
    created_before: filters.created_before || "",
  });
  resetTablePage("#ops-events-table");
  await refreshOperationalEvents();
  showToast("Opened request traffic inside the unified event directory.", "info");
}

function operationTopologyNodeKey(node) {
  return `${node.kind}:${node.id}`;
}

function isRenderableTopologyPolicyRow(row) {
  if (!row || typeof row !== "object") return false;
  const entry = row.detail?.entry;
  if (!entry || typeof entry !== "object") return false;
  const provider = String(row.provider || "").trim();
  const model = String(row.model || "").trim();
  if (!provider || provider === "-") return false;
  if (!model || model === "-") return false;
  return true;
}

function buildOperationsTopologyData({ listeners = [], policyRows = [], config = null } = {}) {
  const inboundListeners = (Array.isArray(listeners) ? listeners : [])
    .filter((listener) => Boolean(listener.exposes_proxy))
    .map((listener) => ({
      kind: "listener",
      id: String(listener.listener_id || ""),
      title: String(listener.name || listener.listener_id || "Listener"),
      subtitle: `${listener.published_host || "127.0.0.1"}:${formattedValue(listener.published_port || listener.port)}`,
      detail: {
        type: "Inbound Listener",
        listener_id: listener.listener_id,
        name: listener.name || listener.listener_id,
        bind: `${listener.host || "0.0.0.0"}:${formattedValue(listener.port)}`,
        published: `${listener.published_host || "127.0.0.1"}:${formattedValue(listener.published_port || listener.port)}`,
        exposes_admin: Boolean(listener.exposes_admin),
        exposes_platform_api: Boolean(listener.exposes_platform_api),
        exposes_proxy: Boolean(listener.exposes_proxy),
      },
    }));
  const knownListenerIds = inboundListeners.map((listener) => listener.id);
  const routeTargets = [];
  const edges = [];
  const targetIds = new Set();
  const addTarget = (target, scopedListeners) => {
    if (!target || !target.id || targetIds.has(target.id)) {
      return;
    }
    targetIds.add(target.id);
    routeTargets.push(target);
    (scopedListeners.length ? scopedListeners : knownListenerIds).forEach((listenerId) => {
      edges.push({
        from: `listener:${listenerId}`,
        to: "service:llmproxy-node",
      });
      edges.push({
        from: "service:llmproxy-node",
        to: `target:${target.id}`,
      });
    });
  };
  (Array.isArray(policyRows) ? policyRows : []).filter(isRenderableTopologyPolicyRow).forEach((row, index) => {
    const entry = row.detail?.entry || {};
    const routeId = String(row.entry_id || `${row.provider}:${row.model}:${index}`);
    const scopedListeners = Array.isArray(entry.listener_ids) && entry.listener_ids.length
      ? entry.listener_ids.map((item) => String(item))
      : knownListenerIds;
    const target = {
      kind: "target",
      id: routeId,
      title: String(row.model || "-"),
      subtitle: `${String(row.provider || "-")} • ${humanizeLabel(row.mode || "-")}`,
      target_type: row.entry_type === "local" || String(row.provider || "").startsWith("local:") ? "local" : "frontier",
      provider: String(row.provider || ""),
      model: String(row.model || ""),
      detail: {
        type: row.entry_type === "local" ? "Local Target" : "Frontier Target",
        entry_id: row.entry_id,
        policy_version: row.policy_version,
        provider: row.provider,
        model: row.model,
        mode: row.mode,
        domains: row.domains,
        regions: row.regions,
        tags: row.tags,
        listener_ids: scopedListeners,
      },
    };
    addTarget(target, scopedListeners);
  });
  const ollamaModel = String(config?.llmproxy_ollama_model || "").trim();
  const ollamaConfigured = Boolean(config?.provider_configuration?.ollama);
  if (ollamaConfigured && ollamaModel) {
    addTarget({
      kind: "target",
      id: `implicit:ollama:${ollamaModel}`,
      title: ollamaModel,
      subtitle: "ollama • Configured local default",
      target_type: "local",
      provider: "ollama",
      model: ollamaModel,
      detail: {
        type: "Local Target",
        entry_id: null,
        policy_version: null,
        provider: "ollama",
        model: ollamaModel,
        mode: "configured default",
        domains: "all",
        regions: "-",
        tags: "implicit fallback",
        listener_ids: knownListenerIds,
      },
    }, knownListenerIds);
  }
  const serviceNodes = inboundListeners.length || routeTargets.length
    ? [{
      kind: "service",
      id: "llmproxy-node",
      title: "llmProxy Node",
      subtitle: "Central routing and proxy service",
      detail: {
        type: "llmProxy Node",
        name: "llmProxy",
        proxy_capable_listeners: inboundListeners.length,
        outbound_target_count: routeTargets.length,
        mapped_edge_count: edges.length,
      },
    }]
    : [];
  return {
    listeners: inboundListeners,
    services: serviceNodes,
    targets: routeTargets,
    edges,
  };
}

function flattenRoutingPolicyRows(policies = []) {
  return (policies || []).flatMap((policyVersion) => {
    const entries = Array.isArray(policyVersion.policy?.entries) ? policyVersion.policy.entries : [];
    if (!entries.length) {
      return [{
        policy_version: policyVersion.policy_version,
        entry_type: "-",
        domains: "-",
        tags: "-",
        regions: "-",
        mode: "-",
        provider: "-",
        model: "-",
        canary_percent: 0,
        detail: policyVersion,
      }];
    }
    return entries.map((entry, index) => ({
      entry_id: entry.entry_id || null,
      policy_version: policyVersion.policy_version,
      entry_type: entry.entry_type || (String(entry.provider_key || "").startsWith("local:") ? "local" : "frontier"),
      domains: (entry.domains || []).join(", ") || "-",
      tags: (entry.tags || entry.labels || []).join(", ") || "-",
      regions: (entry.regions || []).join(", ") || "-",
      mode: entry.deployment_mode || "-",
      provider: entry.provider_key || "-",
      model: entry.model_alias || entry.model_id || "-",
      canary_percent: entry.canary_percent ?? 0,
      detail: { policy_version: policyVersion.policy_version, entry, entry_index: index },
    }));
  });
}

function renderOperationsTopologyDetail(node = null) {
  if (!node) {
    renderRecordView("#operations-topology-detail-table", null, [], {
      raw: false,
      emptyState: {
        title: "No graph artifact selected.",
        body: "Hover or click a listener, proxy node, or routed target in the graph to inspect it here.",
      },
    });
    return;
  }
  if (node.kind === "edge") {
    renderRecordView("#operations-topology-detail-table", node.detail || {}, GRAPH_EDGE_RECORD_FIELDS, {
      rawLabel: "View raw graph edge record",
    });
    return;
  }
  renderRecordView("#operations-topology-detail-table", node.detail || {}, [
    { key: "type", label: "Type" },
    { key: "listener_id", label: "Listener ID", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "entry_id", label: "Route Entry", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "provider", label: "Provider", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
    { key: "model", label: "Model", hideEmpty: true },
    { key: "name", label: "Name", hideEmpty: true },
    { key: "mode", label: "Deployment Mode", hideEmpty: true },
    { key: "proxy_capable_listeners", label: "Inbound Listeners", hideEmpty: true },
    { key: "outbound_target_count", label: "Outbound Targets", hideEmpty: true },
    { key: "mapped_edge_count", label: "Mapped Edges", hideEmpty: true },
    { key: "policy_version", label: "Policy Version", hideEmpty: true },
    { key: "domains", label: "Domains", hideEmpty: true },
    { key: "regions", label: "Regions", hideEmpty: true },
    { key: "tags", label: "Tags", hideEmpty: true },
    { key: "published", label: "Published Address", hideEmpty: true },
    { key: "bind", label: "Bind Address", hideEmpty: true },
    { key: "listener_ids", label: "Listener Scope", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "All listeners" }) },
    { key: "exposes_admin", label: "Admin Surface", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
    { key: "exposes_platform_api", label: "Platform API", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
    { key: "exposes_proxy", label: "Proxy Traffic", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  ], {
    rawLabel: "View raw mapping artifact",
  });
}

async function openOperationsTopologyContext(node) {
  if (!node) return;
  if (node.kind === "edge" && node.openArtifact) {
    node = node.openArtifact;
  }
  if (node.kind === "listener") {
    await openRequestHistoryContext({ listener_id: node.id });
    return;
  }
  if (node.kind === "service") {
    showToast("The central llmProxy node is the service layer between inbound listeners and outbound targets.", "info");
    return;
  }
  const provider = String(node.provider || "");
  if (provider.startsWith("local:") || node.target_type === "local") {
    await ensurePanelLoaded("models", true);
    const customMatch = (state.localModelRows || []).find((row) => String(row.model_alias || "") === String(node.model || ""));
    if (customMatch) {
      switchPanel("models");
      switchSubview("models", "catalog");
      switchCollection("modelCatalog", "local");
      inspectLocalModel(customMatch);
      showToast(`Opened custom LLM context for ${node.model}.`, "ok");
      return;
    }
    const runtimeProvider = provider === "ollama" ? "ollama" : provider.replace(/^local:/, "");
    if (runtimeProvider) {
      switchPanel("models");
      switchSubview("models", "register");
      switchCollection("modelRegister", "runtime");
      await ensurePanelLoaded("models", true);
      await openRuntimeHostingContext(runtimeProvider);
      showToast(`Opened ${runtimeProvider} runtime context for served model ${node.model}.`, "ok");
      return;
    }
    showToast(`Local target ${node.model} is not mapped to a custom package or known runtime context.`, "warn");
    return;
  }
  switchPanel("models");
  switchSubview("models", "catalog");
  switchCollection("modelCatalog", "proxy");
  await ensurePanelLoaded("models", true);
  const group = (state.foundationProviderGroups || []).find((item) => buildFoundationProviderKey(item) === provider);
  if (!group) {
    showToast(`Vendor provider ${provider} is not present in the vendor catalog.`, "warn");
    return;
  }
  inspectFoundationProvider(group);
  const model = (group.models || []).find((item) => String(item.model_id || "") === String(node.model || ""));
  if (model) {
    inspectFoundationModel(group, model);
  }
  showToast(`Opened vendor model context for ${provider} / ${node.model}.`, "ok");
}

function currentSelectedOperationsTopologyArtifact() {
  const data = state.operationsTopologyData || {};
  const artifactLookup = new Map();
  [...(data.listeners || []), ...(data.services || []), ...(data.targets || [])]
    .forEach((node) => artifactLookup.set(operationTopologyNodeKey(node), node));
  if (state.selectedOperationsTopologyEdgeKey) {
    const edge = (data.edges || []).find((item) => `${item.from}->${item.to}` === state.selectedOperationsTopologyEdgeKey);
    if (edge) {
      const fromNode = artifactLookup.get(edge.from);
      const toNode = artifactLookup.get(edge.to);
      if (fromNode && toNode) {
        return {
          kind: "edge",
          id: `${edge.from}->${edge.to}`,
          detail: {
            path: `${fromNode.title} -> ${toNode.title}`,
            from_label: graphArtifactLabel(fromNode.kind),
            from_title: fromNode.title,
            to_label: graphArtifactLabel(toNode.kind),
            to_title: toNode.title,
            detail: "Inbound mapping path segment inside the topology graph.",
          },
          openArtifact: toNode,
        };
      }
    }
  }
  const items = [...(data.listeners || []), ...(data.services || []), ...(data.targets || [])];
  return items.find((node) => operationTopologyNodeKey(node) === state.selectedOperationsTopologyKey) || null;
}

function renderOperationsTopologyGraph(data) {
  const host = $("#operations-topology-graph");
  if (!host) return;
  host.innerHTML = "";
  const listeners = data?.listeners || [];
  const services = data?.services || [];
  const targets = data?.targets || [];
  if (!listeners.length || !targets.length || !services.length) {
    host.appendChild(buildEmptyState({
      icon: "⇄",
      title: "No graph artifacts available.",
      body: "Publish inbound listeners and routing entries to render the topology graph.",
    }));
    renderOperationsTopologyDetail(null);
    return;
  }
  renderSummaryChips("#operations-topology-summary-strip", [
    { label: "Inbound Listeners", value: String(listeners.length) },
    { label: "llmProxy Nodes", value: String(services.length) },
    { label: "Mapped Targets", value: String(targets.length) },
    { label: "Edges", value: String((data.edges || []).length) },
    { label: "Providers", value: String(new Set(targets.map((item) => item.provider).filter(Boolean)).size) },
  ]);
  const NS = "http://www.w3.org/2000/svg";
  const nodeWidth = 240;
  const nodeHeight = 58;
  const gapY = 22;
  const marginX = 40;
  const leftX = marginX;
  const middleX = 300;
  const rightX = 560;
  const topY = 40;
  const height = topY + Math.max(listeners.length, targets.length, services.length) * (nodeHeight + gapY) + 40;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 900 ${height}`);
  svg.setAttribute("class", "topology-graph");
  const positions = new Map();
  const artifactLookup = new Map();
  listeners.forEach((node, index) => {
    artifactLookup.set(operationTopologyNodeKey(node), node);
    positions.set(operationTopologyNodeKey(node), { x: leftX, y: topY + index * (nodeHeight + gapY) });
  });
  services.forEach((node, index) => {
    artifactLookup.set(operationTopologyNodeKey(node), node);
    const centeredY = topY + ((Math.max(listeners.length, targets.length) - 1) * (nodeHeight + gapY)) / 2;
    positions.set(operationTopologyNodeKey(node), { x: middleX, y: services.length > 1 ? topY + index * (nodeHeight + gapY) : Math.max(topY, centeredY) });
  });
  targets.forEach((node, index) => {
    artifactLookup.set(operationTopologyNodeKey(node), node);
    positions.set(operationTopologyNodeKey(node), { x: rightX, y: topY + index * (nodeHeight + gapY) });
  });
  const titleLeft = document.createElementNS(NS, "text");
  titleLeft.setAttribute("x", String(leftX));
  titleLeft.setAttribute("y", "22");
  titleLeft.setAttribute("class", "topology-title");
  titleLeft.textContent = "Inbound Listeners";
  svg.appendChild(titleLeft);
  const titleRight = document.createElementNS(NS, "text");
  titleRight.setAttribute("x", String(rightX));
  titleRight.setAttribute("y", "22");
  titleRight.setAttribute("class", "topology-title");
  titleRight.textContent = "Outbound Targets";
  svg.appendChild(titleRight);
  const titleMiddle = document.createElementNS(NS, "text");
  titleMiddle.setAttribute("x", String(middleX));
  titleMiddle.setAttribute("y", "22");
  titleMiddle.setAttribute("class", "topology-title");
  titleMiddle.textContent = "Proxy Service";
  svg.appendChild(titleMiddle);
  (data.edges || []).forEach((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) return;
    const fromNode = artifactLookup.get(edge.from);
    const toNode = artifactLookup.get(edge.to);
    const edgeArtifact = fromNode && toNode ? {
      kind: "edge",
      id: `${edge.from}->${edge.to}`,
      detail: {
        path: `${fromNode.title} -> ${toNode.title}`,
        from_label: graphArtifactLabel(fromNode.kind),
        from_title: fromNode.title,
        to_label: graphArtifactLabel(toNode.kind),
        to_title: toNode.title,
        detail: "Inbound mapping path segment inside the topology graph.",
      },
      openArtifact: toNode,
    } : null;
    const path = document.createElementNS(NS, "path");
    const startX = from.x + nodeWidth;
    const startY = from.y + nodeHeight / 2;
    const endX = to.x;
    const endY = to.y + nodeHeight / 2;
    const controlX = (startX + endX) / 2;
    path.setAttribute("d", `M ${startX} ${startY} C ${controlX} ${startY}, ${controlX} ${endY}, ${endX} ${endY}`);
    path.setAttribute("class", "topology-edge");
    if (edgeArtifact && edgeArtifact.id === state.selectedOperationsTopologyEdgeKey) {
      path.classList.add("active");
    }
    path.setAttribute("tabindex", "0");
    const activateEdge = () => {
      if (!edgeArtifact) return;
      state.selectedOperationsTopologyEdgeKey = edgeArtifact.id;
      state.selectedOperationsTopologyKey = null;
      renderOperationsTopologyDetail(edgeArtifact);
    };
    path.addEventListener("mouseenter", activateEdge);
    path.addEventListener("focus", activateEdge);
    path.addEventListener("click", activateEdge);
    path.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activateEdge();
      await openOperationsTopologyContext(edgeArtifact);
    });
    svg.appendChild(path);
  });
  [...listeners, ...services, ...targets].forEach((node) => {
    const pos = positions.get(operationTopologyNodeKey(node));
    if (!pos) return;
    const group = document.createElementNS(NS, "g");
    group.setAttribute("class", `topology-node topology-node-${node.kind}${node.target_type ? ` topology-node-${node.target_type}` : ""}`);
    if (operationTopologyNodeKey(node) === state.selectedOperationsTopologyKey) {
      group.classList.add("active");
    }
    group.setAttribute("tabindex", "0");
    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("x", String(pos.x));
    rect.setAttribute("y", String(pos.y));
    rect.setAttribute("rx", "12");
    rect.setAttribute("ry", "12");
    rect.setAttribute("width", String(nodeWidth));
    rect.setAttribute("height", String(nodeHeight));
    group.appendChild(rect);
    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(pos.x + 14));
    title.setAttribute("y", String(pos.y + 24));
    title.setAttribute("class", "topology-node-title");
    title.textContent = node.title;
    group.appendChild(title);
    const subtitle = document.createElementNS(NS, "text");
    subtitle.setAttribute("x", String(pos.x + 14));
    subtitle.setAttribute("y", String(pos.y + 43));
    subtitle.setAttribute("class", "topology-node-subtitle");
    subtitle.textContent = node.subtitle;
    group.appendChild(subtitle);
    const activate = () => {
      state.selectedOperationsTopologyEdgeKey = null;
      state.selectedOperationsTopologyKey = operationTopologyNodeKey(node);
      renderOperationsTopologyDetail(node);
    };
    group.addEventListener("mouseenter", activate);
    group.addEventListener("focus", activate);
    group.addEventListener("click", activate);
    group.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activate();
      await openOperationsTopologyContext(node);
    });
    svg.appendChild(group);
  });
  mountInteractiveSvgGraph(host, svg, { graphKey: "#operations-topology-graph", baseWidth: 900, baseHeight: height });
  const selectedNode = [...listeners, ...services, ...targets].find((node) => operationTopologyNodeKey(node) === state.selectedOperationsTopologyKey) || services[0] || listeners[0];
  const selectedEdge = currentSelectedOperationsTopologyArtifact();
  renderOperationsTopologyDetail(selectedEdge || selectedNode || null);
}

async function refreshOperationsTopology() {
  const host = $("#operations-topology-graph");
  if (!host) return null;
  const cachedListeners = Array.isArray(state.configPayload?.llmproxy_inbound_listeners)
    ? state.configPayload.llmproxy_inbound_listeners
    : [];
  const cachedPolicyRows = Array.isArray(state.policyRows) ? state.policyRows : [];
  if (cachedListeners.length || cachedPolicyRows.length) {
    state.operationsTopologyData = buildOperationsTopologyData({
      listeners: cachedListeners,
      policyRows: cachedPolicyRows,
      config: state.configPayload,
    });
    renderOperationsTopologyGraph(state.operationsTopologyData);
  } else {
    host.innerHTML = "";
    host.appendChild(buildLoadingState({
      title: "Loading topology graph…",
      body: "Fetching listeners and routing policies.",
    }));
  }
  const [config, policies] = await Promise.all([
    apiFetch("/admin/api/config"),
    apiFetch("/deployment/routing-policies"),
  ]);
  state.configPayload = config;
  const flattenedPolicyRows = flattenRoutingPolicyRows(policies);
  state.policyRows = flattenedPolicyRows;
  state.operationsTopologyData = buildOperationsTopologyData({
    listeners: config.llmproxy_inbound_listeners || [],
    policyRows: flattenedPolicyRows,
    config,
  });
  renderOperationsTopologyGraph(state.operationsTopologyData);
  return state.operationsTopologyData;
}

function applyClientFilters(rows, filters = {}) {
  return rows.filter((row) => Object.entries(filters).every(([key, value]) => {
    if (!value) return true;
    const candidate = row[key];
    return String(candidate ?? "").toLowerCase().includes(String(value).toLowerCase());
  }));
}

function deriveAliasFromManifest(path) {
  if (!path) return "";
  const parts = String(path).split("/").filter(Boolean);
  if (parts.length < 2) return "";
  return parts[parts.length - 2];
}

function renderPipelineSummary({ candidates = [], exports = [], imports = [], versions = [], training = [] }) {
  renderSummaryChips("#pipeline-summary", [
    { label: "Visible Candidates", value: String(candidates.length) },
    { label: "Visible Exports", value: String(exports.length) },
    { label: "Visible Imports", value: String(imports.length) },
    { label: "Visible Versions", value: String(versions.length) },
    { label: "Visible Training", value: String(training.length) },
  ]);
}

function csv(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseFallbackChain(value) {
  return csv(value).map((item, index) => {
    const [provider, model] = item.split(":");
    if (!provider || !model) {
      throw new Error("Fallback chain entries must use provider:model format.");
    }
    return { order: index + 1, provider: provider.trim(), model: model.trim() };
  });
}

function parseMessages(text) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const idx = line.indexOf(":");
      if (idx < 1) throw new Error("Messages must use role:content format.");
      return { role: line.slice(0, idx).trim(), content: line.slice(idx + 1).trim() };
    });
}

function validateRoutingDefaultEntries(entries) {
  if (!Array.isArray(entries)) {
    throw new Error("Routing default entries must be a JSON array.");
  }
  return entries.map((entry, index) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      throw new Error(`Entry ${index + 1} must be a JSON object.`);
    }
    const providerKey = String(entry.provider_key || "").trim();
    const modelId = String(entry.model_id || "").trim();
    const deploymentMode = String(entry.deployment_mode || "production").trim();
    if (!providerKey) {
      throw new Error(`Entry ${index + 1} is missing provider_key.`);
    }
    if (!modelId) {
      throw new Error(`Entry ${index + 1} is missing model_id.`);
    }
    if (!["production", "canary", "shadow"].includes(deploymentMode)) {
      throw new Error(`Entry ${index + 1} has invalid deployment_mode '${deploymentMode}'.`);
    }
    const poolWeight = entry.pool_weight == null ? 1 : Number(entry.pool_weight || 1);
    if (Number.isNaN(poolWeight) || poolWeight <= 0) {
      throw new Error(`Entry ${index + 1} has invalid pool_weight '${entry.pool_weight}'.`);
    }
    const normalizeStringArray = (value, fieldName) => {
      if (value == null) return [];
      if (!Array.isArray(value)) {
        throw new Error(`Entry ${index + 1} field '${fieldName}' must be an array of strings.`);
      }
      return value.map((item) => String(item).trim()).filter(Boolean);
    };
    return {
      ...entry,
      provider_key: providerKey,
      model_id: modelId,
      deployment_mode: deploymentMode,
      domains: normalizeStringArray(entry.domains, "domains"),
      task_types: normalizeStringArray(entry.task_types, "task_types"),
      tags: normalizeStringArray(entry.tags, "tags"),
      labels: normalizeStringArray(entry.labels, "labels"),
      regions: normalizeStringArray(entry.regions, "regions"),
      listener_ids: normalizeStringArray(entry.listener_ids, "listener_ids"),
      node_id: entry.node_id == null ? null : String(entry.node_id).trim() || null,
      node_role: entry.node_role == null ? null : String(entry.node_role).trim() || null,
      capacity_class: entry.capacity_class == null ? null : String(entry.capacity_class).trim() || null,
      node_labels: normalizeStringArray(entry.node_labels, "node_labels"),
      pool_id: entry.pool_id == null ? null : String(entry.pool_id).trim() || null,
      pool_weight: poolWeight,
      balancing_strategy: entry.balancing_strategy == null ? null : String(entry.balancing_strategy).trim() || null,
      affinity_key: entry.affinity_key == null ? null : String(entry.affinity_key).trim() || null,
      supports_local_models: Boolean(entry.supports_local_models),
      supports_training: Boolean(entry.supports_training),
      forward_request_metadata: Boolean(entry.forward_request_metadata),
      decision_rationale: entry.decision_rationale == null ? null : String(entry.decision_rationale),
    };
  });
}

function parseMcpTools(text) {
  return String(text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(":");
      if (parts.length < 3 || parts[0] !== "mcp") {
        throw new Error("MCP tools must use mcp:server:tool_name format.");
      }
      return { type: "mcp", server: parts[1].trim(), name: parts.slice(2).join(":").trim() };
    });
}

function parseJsonObject(value, fieldName) {
  const text = String(value || "").trim();
  if (!text) return {};
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error(`${fieldName} must be valid JSON.`);
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${fieldName} must be a JSON object.`);
  }
  return parsed;
}

function makeTable(columns, rows, rowRenderer, emptyState = "No records available yet.", options = {}) {
  const { itemLabel = "rows", pageKey = null, pageSize = null } = options;
  const serverPagination = options.serverPagination || null;
  const wrapper = document.createElement("div");
  wrapper.className = "table-render";
  const table = document.createElement("table");
  const pagerHost = document.createElement("div");

  function renderCurrentPage() {
    const pageState = serverPagination || getPaginatedRows(rows, { pageKey, pageSize });
    table.innerHTML = "";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    columns.forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = columns.length;
      const config = typeof emptyState === "string" ? { title: "No data yet.", body: emptyState } : emptyState;
      td.appendChild(buildEmptyState(config));
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      const visibleRows = serverPagination ? rows : pageState.pageRows;
      visibleRows.forEach((row) => tbody.appendChild(rowRenderer(row)));
    }
    table.appendChild(tbody);

    pagerHost.innerHTML = "";
    if (pageState.totalPages > 1) {
      pagerHost.appendChild(buildTablePaginationControls(pageState, {
        pageKey,
        itemLabel,
        defaultPageSize: pageSize,
        onChange: serverPagination?.onChange || renderCurrentPage,
      }));
    }
  }

  renderCurrentPage();
  wrapper.appendChild(table);
  wrapper.appendChild(pagerHost);
  return wrapper;
}

function createActionButton(label, handler, options = {}) {
  const { accent = false, destructive = false, confirmMessage = null } = options;
  const button = document.createElement("button");
  button.type = "button";
  button.className = `button micro${accent ? " accent" : ""}${destructive ? " destructive" : ""}`;
  button.textContent = label;
  button.addEventListener("click", async () => {
    if (confirmMessage && !window.confirm(confirmMessage)) {
      return;
    }
    await withLoading(button, handler, "Working…");
  });
  return button;
}

function toQueryString(formSelector) {
  const data = new FormData($(formSelector));
  const params = new URLSearchParams();
  Object.entries(Object.fromEntries(data.entries())).forEach(([key, value]) => value && params.set(key, value));
  return params.toString();
}

function normalizedPanel(panel) {
  return knownPanels.has(panel) ? panel : "overview";
}

function panelFromHash() {
  return normalizedPanel(window.location.hash.replace(/^#/, "").trim());
}

function switchPanel(panel, { updateHash = true } = {}) {
  const nextPanel = normalizedPanel(panel);
  state.activePanel = nextPanel;
  if (nextPanel !== "training") {
    clearTrainingPolling();
  }
  $$(".panel").forEach((node) => {
    const isActive = node.dataset.panel === nextPanel;
    node.classList.toggle("active", isActive);
    node.setAttribute("aria-hidden", isActive ? "false" : "true");
  });
  $$(".nav-link").forEach((node) => {
    const isActive = node.dataset.panel === nextPanel;
    node.classList.toggle("active", isActive);
    node.setAttribute("aria-selected", isActive ? "true" : "false");
    node.tabIndex = isActive ? 0 : -1;
  });
  syncSidebarNavGroups();
  if (updateHash && window.location.hash !== `#${nextPanel}`) {
    window.location.hash = nextPanel;
  }
  if (state.token) {
    ensurePanelLoaded(nextPanel).catch((error) => {
      showToast(`Failed to load ${nextPanel}: ${String(error)}`, "err");
      logConsole(`${nextPanel} load failed`, String(error));
    });
  }
}

function enhanceFormLabels() {
  $$("form input, form select, form textarea").forEach((field) => {
    if (field.closest(".checkbox-row")) return;
    if (field.type === "hidden" || field.type === "submit" || field.type === "button") return;
    if (field.closest(".field")) return;
    const wrapper = document.createElement("div");
    wrapper.className = "field";
    const label = document.createElement("label");
    label.className = "field-label";
    label.textContent = field.dataset.label || humanizeLabel(field.placeholder || field.name || "Field");
    field.parentNode.insertBefore(wrapper, field);
    wrapper.appendChild(label);
    wrapper.appendChild(field);
  });
}

const panelLoaders = {
  overview: async () => {
    await Promise.all([refreshHealth(), refreshConfig()]);
  },
  proxy: async () => {
    await Promise.all([refreshStreamingSupport(), refreshPromptTemplateInventory()]);
  },
  governance: async () => {
    await Promise.all([refreshVirtualKeys(), refreshPricingCatalog(), refreshGuardrails()]);
  },
  models: async () => {
    await Promise.all([refreshModels(), refreshLocalModels(), refreshPolicies(), refreshLocalRuntimeStatus(), refreshDeployments()]);
  },
  integrations: async () => {
    await Promise.all([refreshProviderGuides(), refreshMcpServers(), refreshA2APeers(), refreshRestEndpoints()]);
  },
  prompts: async () => {
    await refreshPrompts();
  },
  data: async () => {
    await Promise.all([refreshDatasetPipeline(), refreshPromptTemplateInventory()]);
  },
  training: async () => {
    await Promise.all([
      refreshTrainingRuns(),
      refreshEvaluations(),
      refreshKpis(),
      refreshTrainingRuntimeStatus(),
      refreshTrainingStudioStatus(),
      refreshCandidates(),
      refreshExports(),
      refreshDatasetViews(),
    ]);
  },
  operations: async () => {
    await Promise.all([refreshOperationsSummary(), refreshOperationsLive(), refreshObservability(), refreshOperationalEvents(), refreshOperationsTopology(), refreshPromptTemplateInventory()]);
  },
  runtime: async () => {
    await Promise.all([refreshJobs(), refreshEvents()]);
  },
};

async function ensurePanelLoaded(panel, force = false) {
  if (!state.token) return;
  if (!force && state.loadedPanels.has(panel)) return;
  const loader = panelLoaders[panel];
  if (!loader) return;
  await loader();
  state.loadedPanels.add(panel);
}

function renderInboundListenerTable(selector, listeners) {
  const rows = Array.isArray(listeners) ? listeners : [];
  renderSimpleTable(
    selector,
    "",
    ["Listener", "Published", "Bind", "Admin Surface", "Platform API", "Proxy Traffic", "Actions"],
    rows,
    (listener) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>
          <strong>${escapeHtml(listener.name || listener.listener_id || "Listener")}</strong>
          <div class="table-subtext">${renderIdChip(listener.listener_id || "-", { truncate: false })}</div>
        </td>
        <td><code>${escapeHtml(`${listener.published_host || "127.0.0.1"}:${formattedValue(listener.published_port)}`)}</code></td>
        <td><code>${escapeHtml(`${listener.host || "0.0.0.0"}:${formattedValue(listener.port)}`)}</code></td>
        <td>${boolBadge(Boolean(listener.exposes_admin))}</td>
        <td>${boolBadge(Boolean(listener.exposes_platform_api))}</td>
        <td>${boolBadge(Boolean(listener.exposes_proxy))}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Edit", () => {
          selectInboundListener(listener.listener_id || null);
        }, { accent: true }),
      );
      actions.appendChild(
        createActionButton("Open Traffic", async () => {
          await openRequestHistoryContext({ listener_id: listener.listener_id });
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    },
    "Inbound listeners will appear here once configuration is loaded.",
  );
}

function currentInboundListeners() {
  return Array.isArray(state.configPayload?.llmproxy_inbound_listeners) ? state.configPayload.llmproxy_inbound_listeners : [];
}

function currentSelectedInboundListener() {
  const selected = currentInboundListeners().find((listener) => String(listener.listener_id || "") === String(state.selectedInboundListenerId || ""));
  return selected || null;
}

function renderInboundListenerEditor(listener = null) {
  const form = $("#listener-editor-form");
  if (!form) return;
  const row = listener || {};
  setFieldValue("#listener-editor-form", "listener_id", row.listener_id || "");
  setFieldValue("#listener-editor-form", "name", row.name || "");
  setFieldValue("#listener-editor-form", "host", row.host || "0.0.0.0");
  setFieldValue("#listener-editor-form", "port", row.port || "");
  setFieldValue("#listener-editor-form", "published_host", row.published_host || "");
  setFieldValue("#listener-editor-form", "published_port", row.published_port || "");
  form.querySelector("[name='exposes_admin']").checked = Boolean(row.exposes_admin);
  form.querySelector("[name='exposes_platform_api']").checked = Boolean(row.exposes_platform_api);
  form.querySelector("[name='exposes_proxy']").checked = row.exposes_proxy == null ? true : Boolean(row.exposes_proxy);
}

function selectInboundListener(listenerId = null) {
  state.selectedInboundListenerId = listenerId || null;
  renderInboundListenerEditor(currentSelectedInboundListener());
}

function resetInboundListenerEditor() {
  state.selectedInboundListenerId = null;
  renderInboundListenerEditor(null);
}

function replaceInboundListenerTopology(listeners) {
  if (!state.configPayload) {
    state.configPayload = {};
  }
  state.configPayload.llmproxy_inbound_listeners = Array.isArray(listeners) ? listeners : [];
  renderInboundListenerTable("#listener-table", state.configPayload.llmproxy_inbound_listeners);
  if (state.selectedInboundListenerId && !currentSelectedInboundListener()) {
    state.selectedInboundListenerId = null;
  }
  if (!state.selectedInboundListenerId && state.configPayload.llmproxy_inbound_listeners.length) {
    state.selectedInboundListenerId = state.configPayload.llmproxy_inbound_listeners[0].listener_id;
  }
  renderInboundListenerEditor(currentSelectedInboundListener());
}

async function refreshHealth() {
  setTableLoading("#health-provider-table", {
    title: "Loading readiness…",
    body: "Fetching current platform and vendor connectivity status.",
  });
  const payload = await apiFetch("/health");
  state.healthPayload = payload;
  renderOverviewSummary();
  renderConnectivitySnapshotTable("#health-provider-table", payload.provider_readiness || []);
  renderModelMonitorProviderOptions();
  renderLlmTimeseriesProviderOptions();
  renderOpsEventTrafficFilterOptions();
  renderRecordView("#health-meta-table", payload, [
    { key: "status", label: "Status", render: (value) => statusBadge(value || "-") },
    { key: "environment", label: "Environment" },
    { key: "database_backend", label: "Database Backend" },
    { key: "redis_configured", label: "Redis Configured", render: (value) => boolBadge(Boolean(value)) },
    { key: "logs_path", label: "Logs Path", render: (value) => renderIdChip(value, { truncate: false }) },
  ], {
    rawLabel: "View raw health payload",
    emptyState: { title: "No health data.", body: "Refresh readiness to load the current process and provider status." },
  });
  await refreshLlmTimeseries();
  await refreshModelMonitors();
  return payload;
}

async function refreshConfig() {
  setTableLoading("#listener-table", {
    title: "Loading inbound listeners…",
    body: "Reading the published listener topology and capability flags.",
  });
  setTableLoading("#config-table", {
    title: "Loading configuration…",
    body: "Reading the current config directory and effective settings.",
  });
  const payload = await apiFetch("/admin/api/config");
  state.configPayload = payload;
  renderOverviewSummary();
  replaceInboundListenerTopology(payload.llmproxy_inbound_listeners || []);
  renderStreamingValidationListenerOptions();
  renderStreamingValidationListenerOptions("#model-monitor-listener-id");
  const rows = Object.entries(payload)
    .filter(([key]) => !["provider_configuration", "llmproxy_inbound_listeners"].includes(key))
    .map(([key, value]) => ({ key, value: typeof value === "object" ? JSON.stringify(value) : String(value ?? "") }));
  renderKeyValueTable("#config-table", rows, {
    emptyMessage: "Configuration values will appear here once loaded.",
    allowEdit: true,
  });
  const autoDeployCheckbox = document.querySelector('#automation-form [name="auto_deploy_approved_evaluations"]');
  if (autoDeployCheckbox) {
    autoDeployCheckbox.checked = Boolean(payload.llmproxy_auto_deploy_approved_evaluations);
  }
  setFieldValue("#automation-form", "auto_deploy_deployment_mode", payload.llmproxy_auto_deploy_deployment_mode || "production");
  setFieldValue("#routing-settings-form", "routing_strategy", payload.llmproxy_routing_strategy || "balanced");
  setFieldValue("#routing-settings-form", "frontier_default_entries", JSON.stringify(payload.llmproxy_frontier_default_entries || [], null, 2));
  return payload;
}

const PROVIDER_GUIDE_RECORD_FIELDS = [
  { key: "label", label: "Provider", render: (value, row) => `<span class="cell-primary">${escapeHtml(value || row.provider_key || "Untitled provider")}</span>` },
  { key: "provider_key", label: "Provider Key", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "provider_family", label: "Provider Family", hideEmpty: true },
  { key: "configured", label: "Configured", render: (value) => boolBadge(Boolean(value)) },
  { key: "validation_mode", label: "Validation Mode", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "recommended_base_url", label: "Recommended Base URL", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "config_keys", label: "Config Keys", render: (value) => renderList(value, { emptyLabel: "No configuration keys documented" }) },
  { key: "notes", label: "Setup Notes", hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml((value || []).map((note) => `• ${note}`).join("\n"))}</pre>` },
];

function inspectProviderGuide(row, { rawLabel = "View raw provider guide" } = {}) {
  state.selectedProviderGuideKey = row?.provider_key || null;
  setActiveRuntimeRow("#provider-guide-table", state.selectedProviderGuideKey || "");
  renderRecordView("#provider-guide-detail", row, PROVIDER_GUIDE_RECORD_FIELDS, { rawLabel });
}

async function refreshProviderGuides() {
  setTableLoading("#provider-guide-table", {
    title: "Loading reference guides…",
    body: "Fetching vendor configuration and setup guidance.",
  });
  const page = paginationParams("#provider-guide-table", 15);
  const params = new URLSearchParams({
    paginated: "true",
    limit: String(page.limit),
    offset: String(page.offset),
  });
  const payload = await apiFetch(`/admin/api/providers/guides?${params.toString()}`);
  const rows = payload.items || [];
  state.providerGuides = rows;
  renderIntegrationsSummary();
  refreshIntegrationGraphView();
  const host = $("#provider-guide-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Provider", "Configured", "Validation", "Config Keys", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.provider_key;
      if (row.provider_key === state.selectedProviderGuideKey) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.label)}</strong><br/><span>${escapeHtml(row.provider_key)}</span></td>
        <td>${boolBadge(Boolean(row.configured))}</td>
        <td>${escapeHtml(row.validation_mode || "-")}</td>
        <td>${escapeHtml((row.config_keys || []).join(", "))}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectProviderGuide(row);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => inspectProviderGuide(row), { accent: true }));
      actions.appendChild(createActionButton("Open Vendor", () => openConnectivityVendorContext(row)));
      if (row.provider_key !== "replicate") {
        actions.appendChild(createActionButton("Validate", async () => {
          const result = await apiFetch("/admin/api/providers/validate", {
            method: "POST",
            body: JSON.stringify({ provider_key: row.provider_key, prompt: "Say hello briefly." }),
          });
          renderOutput("#provider-guide-output", result);
          inspectProviderGuide(row, { rawLabel: "View raw validation response" });
          showToast(`Validated ${row.label}.`, "ok");
        }));
      }
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Reference guidance will appear here.", {
      pageKey: "#provider-guide-table",
      itemLabel: "providers",
      serverPagination: serverPaginationForPayload("#provider-guide-table", payload, page.limit, () => refreshProviderGuides()),
    }),
  );
  const guideCount = Number(payload.total || rows.length || 0);
  clearHost("#provider-guide-detail");
  $("#provider-guide-detail")?.appendChild(buildEmptyState({
    icon: "→",
    title: "Select a reference guide to inspect.",
    body: `${guideCount} reference guide${guideCount === 1 ? "" : "s"} available — choose “Inspect” on any row to see its configuration expectations, recommended endpoint, and setup notes here.`,
  }));
  renderOutput("#provider-guide-output", payload);
  return payload;
}

const ROUTE_PREVIEW_RECORD_FIELDS = [
  { key: "policy_version", label: "Policy Version", value: (p) => p?.decision?.policy_version, hideEmpty: true },
  { key: "selected_provider_family", label: "Provider Family", value: (p) => p?.decision?.selected_provider_family, hideEmpty: true },
  { key: "selected_pool_id", label: "Selected Pool", value: (p) => p?.decision?.selected_pool_id, hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "selected_node_id", label: "Selected Node", value: (p) => p?.decision?.selected_node_id, hideEmpty: true, render: (value, payload) => `${renderIdChip(value, { truncate: false })}${payload?.decision?.selected_node_role ? `<br/><span>${escapeHtml(humanizeLabel(payload.decision.selected_node_role))}</span>` : ""}` },
  { key: "selected_capacity_class", label: "Capacity Class", value: (p) => p?.decision?.selected_capacity_class, hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "selected_balancing_strategy", label: "Balancing Strategy", value: (p) => p?.decision?.selected_balancing_strategy, hideEmpty: true, render: (value, payload) => `<span class="badge badge-info">${escapeHtml(humanizeLabel(value || "-"))}</span>${payload?.decision?.selected_affinity_key ? `<br/><span>${escapeHtml(humanizeLabel(payload.decision.selected_affinity_key))}</span>` : ""}` },
  { key: "selected_node_labels", label: "Node Labels", value: (p) => p?.decision?.selected_node_labels || [], hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No node labels" }) },
  { key: "decision_rationale", label: "Decision Rationale", value: (p) => p?.decision?.decision_rationale, hideEmpty: true },
  { key: "shadow_provider_keys", label: "Shadows", value: (p) => p?.shadow_provider_keys || [], render: (value) => renderList(value, { emptyLabel: "No shadow routing configured" }) },
  { key: "fallback_chain", label: "Fallback Count", value: (p) => normalizeFallbackChain(p?.decision?.fallback_chain).length, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "route_tags", label: "Route Tags", value: (p) => p?.classification?.route_tags || [], render: (value) => renderList(value, { emptyLabel: "No route tags" }) },
  { key: "region", label: "Region", value: (p) => p?.classification?.region, hideEmpty: true },
];

function renderRoutePreview(payload) {
  state.lastRoutePreview = payload;
  const decision = payload?.decision || {};
  const classification = payload?.classification || {};
  renderMetricGrid("#route-preview-grid", [
    { label: "Provider", value: payload?.selected_provider || "-" },
    { label: "Model", value: decision.selected_model || "-" },
    { label: "Mode", value: decision.selected_mode || "-" },
    { label: "Pool", value: decision.selected_pool_id || "-", subvalue: decision.selected_balancing_strategy ? humanizeLabel(decision.selected_balancing_strategy) : "Direct route" },
    { label: "Node", value: decision.selected_node_id || "-", subvalue: decision.selected_node_role ? humanizeLabel(decision.selected_node_role) : "No downstream node" },
    { label: "Domain", value: classification.domain || "-", subvalue: classification.task_type || "No task type" },
    { label: "Latency Class", value: decision.predicted_latency_class || "-" },
    { label: "Cost Class", value: decision.predicted_cost_class || "-" },
  ]);
  renderRecordView("#route-preview-table", payload, ROUTE_PREVIEW_RECORD_FIELDS, {
    rawLabel: "View raw route preview",
    emptyState: { title: "No route preview yet.", body: "Submit the form above to preview how a request would be routed." },
  });
  renderFallbackChainTable(
    "#route-preview-fallback-table",
    "Fallback Order",
    normalizeFallbackChain(decision.fallback_chain).map((item) => ({
      order: item.order,
      provider: item.provider,
      provider_family: item.provider_family,
      model: item.model,
      pool_id: item.pool_id,
      node_id: item.node_id,
      node_role: item.node_role,
      balancing_strategy: item.balancing_strategy,
      affinity_key: item.affinity_key,
    })),
    {
      emptyLabel: "No fallback chain configured for this preview.",
    },
  );
  clearHost("#route-comparison-table");
  renderOutput("#route-preview-output", payload);
}

async function fetchLatestRequestDetailBySession(sessionId) {
  if (!sessionId) return null;
  const rows = await apiFetch(`/admin/api/proxy/requests?session_id=${encodeURIComponent(sessionId)}`);
  if (!Array.isArray(rows) || !rows.length) return null;
  return apiFetch(`/admin/api/proxy/requests/${encodeURIComponent(rows[0].id)}`);
}

const PROMPT_TEMPLATE_RECORD_FIELDS = [
  { key: "name", label: "Name", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "version", label: "Version", render: (value) => `<span class="badge badge-muted">v${escapeHtml(formattedValue(value))}</span>` },
  { key: "status", label: "Status", render: (value) => statusBadge(value || "draft") },
  {
    key: "rollout",
    label: "Rollout",
    render: (value, record) => {
      if (value?.mode === "canary") return `<span class="badge badge-info">Challenger ${escapeHtml(formattedValue(value.traffic_percentage))}%</span>`;
      if (record.family_rollout?.active_version === record.version) return '<span class="badge badge-ok">Active Baseline</span>';
      return '<span class="badge badge-muted">Inactive</span>';
    },
  },
  { key: "id", label: "Template ID", render: (value) => renderIdChip(value) },
  { key: "description", label: "Description", hideEmpty: true },
  { key: "model_override", label: "Model Override", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "request_count", label: "Requests", value: (record) => record.metrics?.request_count ?? 0 },
  { key: "candidate_count", label: "Candidates", value: (record) => record.metrics?.candidate_count ?? 0 },
  { key: "approved_candidate_count", label: "Approved Candidates", value: (record) => record.metrics?.approved_candidate_count ?? 0 },
  { key: "avg_latency_ms", label: "Avg Latency", value: (record) => record.metrics?.avg_latency_ms, render: (value) => value == null ? '<span class="empty-value">-</span>' : `${escapeHtml(formattedValue(value))} ms` },
  { key: "avg_cost_estimate", label: "Avg Cost", value: (record) => record.metrics?.avg_cost_estimate, render: (value) => value == null ? '<span class="empty-value">-</span>' : `$${escapeHtml(formattedValue(value))}` },
  { key: "error_rate_pct", label: "Error Rate", value: (record) => record.metrics?.error_rate_pct, render: (value) => `${escapeHtml(formattedValue(value ?? 0))}%` },
  { key: "candidate_yield_rate_pct", label: "Candidate Yield", value: (record) => record.metrics?.candidate_yield_rate_pct, render: (value) => `${escapeHtml(formattedValue(value ?? 0))}%` },
  { key: "variables", label: "Variables", render: (value) => renderList(value, { emptyLabel: "No variables — renders as static text" }) },
  { key: "template_text", label: "Template Text", render: (value) => `<pre class="value-pre">${escapeHtml(value || "")}</pre>` },
  { key: "metadata", label: "Metadata", value: (record) => (record.metadata && Object.keys(record.metadata).length ? record.metadata : null), hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(JSON.stringify(value, null, 2))}</pre>` },
  { key: "created_at", label: "Created", render: (value) => timeLabel(value) },
];

function renderPromptRolloutBadge(row) {
  if (row.rollout?.mode === "canary") {
    return `<span class="badge badge-info">Canary ${escapeHtml(formattedValue(row.rollout.traffic_percentage))}%</span>`;
  }
  if (row.family_rollout?.active_version === row.version) {
    return '<span class="badge badge-ok">Active Baseline</span>';
  }
  return '<span class="badge badge-muted">Off</span>';
}

function renderPromptRecommendation(recommendation) {
  if (!recommendation || typeof recommendation !== "object") {
    return '<span class="empty-value">No recommendation yet.</span>';
  }
  const action = String(recommendation.action || "").trim().toLowerCase();
  const tone = action === "promote_challenger" ? "ok" : action === "keep_active" ? "warn" : "info";
  const actionLabel = action ? humanizeLabel(action) : "Observe";
  const reasons = Array.isArray(recommendation.reasons) && recommendation.reasons.length
    ? `<br/><span>${escapeHtml(recommendation.reasons.join(" "))}</span>`
    : "";
  return `<span class="badge badge-${tone}">${escapeHtml(actionLabel)}</span><br/><strong>${escapeHtml(humanizeLabel(recommendation.confidence || "low"))} confidence</strong><br/><span>${escapeHtml(recommendation.summary || "No recommendation yet.")}</span>${reasons}`;
}

function applyPromptAutoPromotionPolicyToForm(policy) {
  const resolved = policy && typeof policy === "object" ? policy : {};
  setFieldValue("#prompt-auto-promotion-form", "enabled", resolved.enabled ? "true" : "false");
  setFieldValue("#prompt-auto-promotion-form", "minimum_challenger_requests", resolved.minimum_challenger_requests ?? 10);
  setFieldValue(
    "#prompt-auto-promotion-form",
    "min_candidate_yield_improvement_pct",
    resolved.min_candidate_yield_improvement_pct ?? 2.0,
  );
  setFieldValue(
    "#prompt-auto-promotion-form",
    "max_error_rate_regression_pct",
    resolved.max_error_rate_regression_pct ?? 1.0,
  );
  setFieldValue(
    "#prompt-auto-promotion-form",
    "max_latency_regression_ms",
    resolved.max_latency_regression_ms ?? 250.0,
  );
  setFieldValue(
    "#prompt-auto-promotion-form",
    "max_cost_regression_usd",
    resolved.max_cost_regression_usd ?? 0.001,
  );
}

function renderPromptTemplateDetail(detail) {
  renderRecordView("#prompt-detail-output", detail, PROMPT_TEMPLATE_RECORD_FIELDS, {
    rawLabel: "View raw prompt template record",
    emptyState: {
      title: "No prompt template selected.",
      body: "Choose a version from the table above and select “Inspect” to see its full text, variables, and metadata here.",
    },
  });
}

const PROMPT_COMPARISON_RECORD_FIELDS = [
  { key: "name", label: "Prompt", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "baseline", label: "Baseline", render: (value) => `<strong>v${escapeHtml(formattedValue(value?.version))}</strong> <span>${statusBadge(value?.status || "-")}</span>` },
  { key: "comparison", label: "Comparison", render: (value) => `<strong>v${escapeHtml(formattedValue(value?.version))}</strong> <span>${statusBadge(value?.status || "-")}</span> ${value?.rollout?.mode === "canary" ? `<span class="badge badge-info">Canary ${escapeHtml(formattedValue(value.rollout.traffic_percentage))}%</span>` : ""}` },
  { key: "recommendation", label: "Recommendation", render: (value) => renderPromptRecommendation(value) },
  { key: "request_count", label: "Requests: Baseline -> Comparison", value: (record) => `${formattedValue(record.baseline?.metrics?.request_count ?? 0)} -> ${formattedValue(record.comparison?.metrics?.request_count ?? 0)} (${formattedValue(record.deltas?.request_count ?? 0)})` },
  { key: "candidate_count", label: "Candidates: Baseline -> Comparison", value: (record) => `${formattedValue(record.baseline?.metrics?.candidate_count ?? 0)} -> ${formattedValue(record.comparison?.metrics?.candidate_count ?? 0)} (${formattedValue(record.deltas?.candidate_count ?? 0)})` },
  { key: "candidate_yield_rate_pct", label: "Candidate Yield %: Baseline -> Comparison", value: (record) => `${formattedValue(record.baseline?.metrics?.candidate_yield_rate_pct ?? 0)}% -> ${formattedValue(record.comparison?.metrics?.candidate_yield_rate_pct ?? 0)}% (${formattedValue(record.deltas?.candidate_yield_rate_pct ?? 0)})` },
  { key: "avg_latency_ms", label: "Avg Latency: Baseline -> Comparison", value: (record) => `${formattedValue(record.baseline?.metrics?.avg_latency_ms ?? "-")} ms -> ${formattedValue(record.comparison?.metrics?.avg_latency_ms ?? "-")} ms (${formattedValue(record.deltas?.avg_latency_ms ?? "-")})` },
  { key: "avg_cost_estimate", label: "Avg Cost: Baseline -> Comparison", value: (record) => `$${formattedValue(record.baseline?.metrics?.avg_cost_estimate ?? 0)} -> $${formattedValue(record.comparison?.metrics?.avg_cost_estimate ?? 0)} (${formattedValue(record.deltas?.avg_cost_estimate ?? 0)})` },
  { key: "error_rate_pct", label: "Error Rate %: Baseline -> Comparison", value: (record) => `${formattedValue(record.baseline?.metrics?.error_rate_pct ?? 0)}% -> ${formattedValue(record.comparison?.metrics?.error_rate_pct ?? 0)}% (${formattedValue(record.deltas?.error_rate_pct ?? 0)})` },
];

function renderPromptComparisonResult(detail) {
  renderRecordView("#prompt-detail-output", detail, PROMPT_COMPARISON_RECORD_FIELDS, {
    rawLabel: "View raw comparison response",
    emptyState: {
      title: "No prompt comparison yet.",
      body: "Select a prompt version, then compare it against the active baseline to review request volume, candidate yield, latency, cost, and error-rate deltas.",
    },
  });
}

function populatePromptRolloutForm(detail) {
  state.selectedPromptTemplateRecord = detail || null;
  setFieldValue("#prompt-rollout-form", "name", detail?.name || "");
  setFieldValue("#prompt-rollout-form", "version", detail?.version ? `v${detail.version}` : "");
  const startButton = $("#prompt-start-canary");
  const compareButton = $("#prompt-compare-active");
  const promoteButton = $("#prompt-promote-challenger");
  const stopButton = $("#prompt-stop-canary");
  const autoRunButton = $("#prompt-run-auto-promotion");
  const comparison = state.selectedPromptComparison;
  const recommendation = comparison?.recommendation || null;
  const isSelected = Boolean(detail?.name && detail?.version);
  const isActiveSelection = String(detail?.status || "").toLowerCase() === "active";
  if (startButton) startButton.disabled = !isSelected || isActiveSelection;
  if (compareButton) compareButton.disabled = !isSelected;
  if (promoteButton) {
    const recommendedVersion = Number(comparison?.comparison?.version || 0);
    const canPromote = !isActiveSelection
      && isSelected
      && recommendedVersion === Number(detail?.version || 0)
      && String(recommendation?.action || "").toLowerCase() === "promote_challenger";
    promoteButton.disabled = !canPromote;
  }
  if (stopButton) stopButton.disabled = !detail?.family_rollout?.challenger_version;
  if (autoRunButton) autoRunButton.disabled = !detail?.name;
  applyPromptAutoPromotionPolicyToForm(detail?.family_rollout?.auto_promotion_policy || comparison?.family_rollout?.auto_promotion_policy || null);
}

const PROMPT_RENDER_RECORD_FIELDS = [
  { key: "name", label: "Template", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "version", label: "Version", render: (value) => `<span class="badge badge-muted">v${escapeHtml(formattedValue(value))}</span>` },
  { key: "render_variables", label: "Variables Used", render: (value) => (value && Object.keys(value).length ? `<pre class="value-pre">${escapeHtml(JSON.stringify(value, null, 2))}</pre>` : '<span class="empty-value">No variables supplied — template has none to fill</span>') },
  { key: "template_text", label: "Template Text", render: (value) => `<pre class="value-pre">${escapeHtml(value || "")}</pre>` },
  { key: "rendered_text", label: "Rendered Output", render: (value) => `<pre class="value-pre">${escapeHtml(value ?? "")}</pre>` },
];

function renderPromptRenderResult(detail) {
  renderRecordView("#prompt-detail-output", detail, PROMPT_RENDER_RECORD_FIELDS, {
    rawLabel: "View raw render response",
    emptyState: {
      title: "No render preview yet.",
      body: "Choose a version from the table above and select “Render” to fill its placeholders with sample values and preview the result here.",
    },
  });
}

const PROMPT_DIFF_RECORD_FIELDS = [
  { key: "name", label: "Template", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "version", label: "Version: From → To", value: (record) => `v${formattedValue(record.from_version)} -> v${formattedValue(record.to_version)}` },
  { key: "variables", label: "Variables: From → To", value: (record) => `${formattedValue(record.from_variables)} -> ${formattedValue(record.to_variables)}` },
  { key: "model_override", label: "Model Override: From → To", value: (record) => `${formattedValue(record.from_model_override)} -> ${formattedValue(record.to_model_override)}` },
  { key: "unified_diff", label: "Unified Diff", render: (value) => (value ? `<pre class="value-pre">${escapeHtml(value)}</pre>` : '<span class="empty-value">Template text is identical between these versions — see Variables / Model Override above for what else changed.</span>') },
];

function renderPromptDiffResult(detail) {
  renderRecordView("#prompt-detail-output", detail, PROMPT_DIFF_RECORD_FIELDS, {
    rawLabel: "View raw diff response",
    emptyState: {
      title: "No version comparison yet.",
      body: "Choose a version numbered 2 or higher from the table above and select “Diff Prev” to compare its template text against the version immediately before it.",
    },
  });
}

function inspectPromptTemplate(detail) {
  state.selectedPromptTemplateKey = buildPromptTemplateKey(detail);
  state.selectedPromptTemplateRecord = detail;
  state.selectedPromptComparison = null;
  setActiveRuntimeRow("#prompts-table", state.selectedPromptTemplateKey || "");
  renderPromptTemplateDetail(detail);
  populatePromptRolloutForm(detail);
}

function showPromptRenderResult(detail) {
  state.selectedPromptTemplateKey = buildPromptTemplateKey(detail);
  state.selectedPromptTemplateRecord = detail;
  state.selectedPromptComparison = null;
  setActiveRuntimeRow("#prompts-table", state.selectedPromptTemplateKey || "");
  renderPromptRenderResult(detail);
  populatePromptRolloutForm(detail);
}

function showPromptDiffResult(detail, row) {
  state.selectedPromptTemplateKey = buildPromptTemplateKey(row || detail);
  state.selectedPromptTemplateRecord = row || detail;
  state.selectedPromptComparison = null;
  setActiveRuntimeRow("#prompts-table", state.selectedPromptTemplateKey || "");
  renderPromptDiffResult(detail);
  populatePromptRolloutForm(row || detail);
}

function showPromptComparisonResult(detail) {
  const comparisonRecord = detail?.comparison || detail;
  state.selectedPromptComparison = detail || null;
  state.selectedPromptTemplateKey = buildPromptTemplateKey(comparisonRecord);
  if (comparisonRecord?.name && comparisonRecord?.version) {
    state.selectedPromptTemplateRecord = comparisonRecord;
  }
  setActiveRuntimeRow("#prompts-table", state.selectedPromptTemplateKey || "");
  renderPromptComparisonResult(detail);
  populatePromptRolloutForm(comparisonRecord);
}

async function refreshPrompts() {
  setTableLoading("#prompts-table", {
    title: "Loading prompt versions…",
    body: "Fetching prompt templates and version history.",
  });
  await refreshPromptTemplateInventory(true);
  const page = paginationParams("#prompts-table", 15);
  const params = new URLSearchParams({
    paginated: "true",
    limit: String(page.limit),
    offset: String(page.offset),
  });
  const payload = await apiFetch(`/admin/api/prompts?${params.toString()}`);
  const rows = payload.items || [];
  state.promptTemplates = rows;
  renderPromptSummary();
  const host = $("#prompts-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Name", "Version", "Status", "Rollout", "Requests", "Candidates", "Avg Latency", "Error Rate", "Model", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      const promptKey = buildPromptTemplateKey(row);
      tr.dataset.recordId = promptKey;
      if (promptKey === state.selectedPromptTemplateKey) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.name)}</strong><br/><span>${escapeHtml(row.description || "")}</span></td>
        <td>${escapeHtml(String(row.version))}</td>
        <td>${statusBadge(row.status || "draft")}</td>
        <td>${renderPromptRolloutBadge(row)}</td>
        <td>${escapeHtml(String(row.metrics?.request_count ?? 0))}</td>
        <td>${escapeHtml(String(row.metrics?.candidate_count ?? 0))}</td>
        <td>${row.metrics?.avg_latency_ms == null ? "-" : `${escapeHtml(formattedValue(row.metrics.avg_latency_ms))} ms`}</td>
        <td>${escapeHtml(formattedValue(row.metrics?.error_rate_pct ?? 0))}%</td>
        <td>${escapeHtml(row.model_override || "-")}<br/><span>${escapeHtml((row.variables || []).join(", ") || "no variables")}</span></td>
        <td></td>
      `;
      tr.addEventListener("click", async (event) => {
        if (event.target.closest("button")) return;
        const detail = await apiFetch(`/admin/api/prompts/${encodeURIComponent(row.name)}?version=${encodeURIComponent(row.version)}`);
        inspectPromptTemplate(detail);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", async () => {
        const detail = await apiFetch(`/admin/api/prompts/${encodeURIComponent(row.name)}?version=${encodeURIComponent(row.version)}`);
        inspectPromptTemplate(detail);
      }, { accent: true }));
      actions.appendChild(createActionButton("Render", async () => {
        const variables = Object.fromEntries((row.variables || []).map((name) => [name, `sample_${name}`]));
        const detail = await apiFetch(`/admin/api/prompts/${encodeURIComponent(row.name)}/render`, {
          method: "POST",
          body: JSON.stringify({ version: row.version, variables }),
        });
        showPromptRenderResult(detail);
      }));
      actions.appendChild(createActionButton("Compare", async () => {
        const query = String(row.status || "").toLowerCase() === "active"
          ? ""
          : `?compare_version=${encodeURIComponent(row.version)}`;
        const detail = await apiFetch(`/admin/api/prompts/${encodeURIComponent(row.name)}/comparison${query}`);
        showPromptComparisonResult(detail);
      }));
      if ((row.status || "").toLowerCase() !== "active") {
        actions.appendChild(createActionButton("Activate", async () => {
          const detail = await apiFetch(
            `/admin/api/prompts/${encodeURIComponent(row.name)}/${encodeURIComponent(row.version)}/status`,
            {
              method: "POST",
              body: JSON.stringify({ status: "active" }),
            },
          );
          inspectPromptTemplate(detail);
          showToast(`Activated ${row.name} v${row.version}.`, "ok");
          await refreshPrompts();
        }));
      }
      if (Number(row.version || 0) > 1) {
        actions.appendChild(createActionButton("Diff Prev", async () => {
          const detail = await apiFetch(
            `/admin/api/prompts/${encodeURIComponent(row.name)}/diff?from_version=${encodeURIComponent(Number(row.version) - 1)}&to_version=${encodeURIComponent(row.version)}`,
          );
          showPromptDiffResult(detail, row);
        }));
      }
      tr.children[9].appendChild(actions);
      return tr;
    }, "No prompt templates registered yet.", {
      pageKey: "#prompts-table",
      itemLabel: "prompt versions",
      serverPagination: serverPaginationForPayload("#prompts-table", payload, page.limit, () => refreshPrompts()),
    }),
  );
  const promptCount = Number(payload.total || rows.length || 0);
  clearHost("#prompt-detail-output");
  if (!promptCount) {
    state.selectedPromptTemplateRecord = null;
    populatePromptRolloutForm(null);
  }
  if (!promptCount) {
    $("#prompt-detail-output")?.appendChild(buildEmptyState({
      icon: "✎",
      title: "No prompt templates registered yet.",
      body: "Create one using the form to the right — its versions will appear here for inspection, rendering, and diffing.",
    }));
  } else {
    $("#prompt-detail-output")?.appendChild(buildEmptyState({
      icon: "→",
      title: "Select a prompt version to inspect.",
      body: `${promptCount} version${promptCount === 1 ? "" : "s"} available — choose “Inspect” to view a template, “Render” to preview it filled with sample variables, or “Diff Prev” to compare it against the version before it.`,
    }));
  }
  return payload;
}

function formatVirtualKeyLimits(row) {
  const parts = [];
  if (row.rpm_limit != null) parts.push(`RPM ${row.rpm_limit}`);
  if (row.tpm_limit != null) parts.push(`TPM ${row.tpm_limit}`);
  if (row.max_budget_usd != null) parts.push(`$${Number(row.max_budget_usd).toFixed(2)}`);
  return parts.join(" / ") || "-";
}

// `<input type="datetime-local">` speaks in wall-clock-local "YYYY-MM-DDTHH:mm" with
// no timezone, while the API speaks in UTC ISO-8601. These two helpers do the
// conversion at the edges so the operator only ever sees and picks a local time —
// never has to hand-author a UTC timestamp string.
function toDatetimeLocalValue(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromDatetimeLocalValue(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return null;
  const date = new Date(trimmed);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

function populateVirtualKeyForm(row = {}) {
  setFieldValue("#virtual-key-form", "key_id", row.id || "");
  setFieldValue("#virtual-key-form", "display_name", row.display_name || "");
  setFieldValue("#virtual-key-form", "owner_id", row.owner_id || "");
  setFieldValue("#virtual-key-form", "role", row.role || "api");
  setFieldValue("#virtual-key-form", "models_allowed", (row.models_allowed || []).join(","));
  setFieldValue("#virtual-key-form", "rpm_limit", row.rpm_limit ?? "");
  setFieldValue("#virtual-key-form", "tpm_limit", row.tpm_limit ?? "");
  setFieldValue("#virtual-key-form", "max_budget_usd", row.max_budget_usd ?? "");
  setFieldValue("#virtual-key-form", "budget_reset_period", row.budget_reset_period || "monthly");
  setFieldValue("#virtual-key-form", "budget_reset_at", toDatetimeLocalValue(row.budget_reset_at));
  setFieldValue("#virtual-key-form", "status", row.status || "active");
  $("#virtual-key-form")?.classList.toggle("is-editing", Boolean(row.id));
  const heading = $("#virtual-key-form-heading");
  if (heading) heading.textContent = row.id ? `Editing ${row.display_name || row.key_prefix || "virtual key"}` : "Issue a new virtual key";
  const submitButton = $("#virtual-key-form button[type='submit']");
  if (submitButton) submitButton.textContent = row.id ? "Save Changes" : "Issue Virtual Key";
}

const VIRTUAL_KEY_RECORD_FIELDS = [
  { key: "display_name", label: "Name", render: (value, row) => `<span class="cell-primary">${escapeHtml(value || row.key_prefix || "Untitled key")}</span>` },
  { key: "key_prefix", label: "Key Prefix", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "id", label: "Key ID", render: (value) => renderIdChip(value) },
  { key: "token", label: "Bearer Token", hideEmpty: true, render: (value) => `${renderIdChip(value, { truncate: false })} <span class="badge badge-warn">Shown once — store it now</span>` },
  { key: "owner_id", label: "Owner", hideEmpty: true },
  { key: "role", label: "Role", render: (value) => `<span class="badge badge-info">${escapeHtml(value || "api")}</span>` },
  { key: "status", label: "Status", render: (value) => statusBadge(value || "pending") },
  { key: "models_allowed", label: "Models Allowed", render: (value) => renderList(value, { emptyLabel: "All registered models" }) },
  { key: "rpm_limit", label: "Requests / Minute", render: (value) => (value == null ? '<span class="empty-value">Unlimited</span>' : `<span class="num">${escapeHtml(String(value))}</span>`) },
  { key: "tpm_limit", label: "Tokens / Minute", render: (value) => (value == null ? '<span class="empty-value">Unlimited</span>' : `<span class="num">${escapeHtml(String(value))}</span>`) },
  { key: "max_budget_usd", label: "Budget Ceiling", render: (value) => (value == null ? '<span class="empty-value">No ceiling set</span>' : renderAmount(value)) },
  { key: "spend_usd", label: "Spend To Date", render: (value) => renderAmount(value || 0, { precision: 4 }) },
  { key: "budget_reset_period", label: "Budget Resets", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "budget_reset_at", label: "Next Reset", render: (value) => (value ? timeLabel(value) : '<span class="empty-value">Not scheduled</span>') },
  { key: "created_at", label: "Issued", hideEmpty: true, render: (value) => timeLabel(value) },
];

function showVirtualKeyRecord(record, { rawLabel } = {}) {
  renderRecordView("#virtual-keys-output", record, VIRTUAL_KEY_RECORD_FIELDS, { rawLabel });
}

function inspectVirtualKey(row, { rawLabel } = {}) {
  state.selectedGovernanceKeyId = row?.id || null;
  setActiveRuntimeRow("#virtual-keys-table", row?.id || "");
  showVirtualKeyRecord(row, { rawLabel });
}

async function refreshVirtualKeys() {
  setTableLoading("#virtual-keys-table", {
    title: "Loading virtual keys…",
    body: "Fetching scoped API keys, limits, and spend.",
  });
  const page = paginationParams("#virtual-keys-table", 15);
  const params = new URLSearchParams({
    paginated: "true",
    limit: String(page.limit),
    offset: String(page.offset),
  });
  const payload = await apiFetch(`/admin/api/auth/virtual-keys?${params.toString()}`);
  const rows = payload.items || [];
  state.governanceKeys = rows;
  renderGovernanceSummary();
  refreshGovernanceGraphView();
  const directoryCount = $("#virtual-key-directory-count");
  if (directoryCount) {
    const total = Number(payload.total || rows.length || 0);
    directoryCount.textContent = total ? `${total} key${total === 1 ? "" : "s"} on file` : "";
  }
  const host = $("#virtual-keys-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Key", "Role", "Limits", "Spend", "Status", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.id;
      if (row.id === state.selectedGovernanceKeyId) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><span class="cell-primary">${escapeHtml(row.display_name || row.key_prefix)}</span><span class="cell-secondary">${escapeHtml(row.key_prefix)}</span></td>
        <td><span class="badge badge-info">${escapeHtml(row.role || "-")}</span></td>
        <td>${escapeHtml(formatVirtualKeyLimits(row))}</td>
        <td>${renderAmount(row.spend_usd || 0, { precision: 4 })}</td>
        <td>${statusBadge(row.status || "pending")}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectVirtualKey(row);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => {
        inspectVirtualKey(row);
      }, { accent: true }));
      actions.appendChild(createActionButton("Edit", () => {
        inspectVirtualKey(row);
        populateVirtualKeyForm(row);
        showToast(`Loaded ${row.key_prefix} into the form below.`, "info");
      }));
      actions.appendChild(createActionButton("Rotate", async () => {
        const result = await apiFetch(`/admin/api/auth/virtual-keys/${encodeURIComponent(row.id)}/rotate`, { method: "POST" });
        inspectVirtualKey(result, { rawLabel: "View raw rotation response" });
        renderRecordView("#virtual-key-form-output", result, VIRTUAL_KEY_RECORD_FIELDS, { rawLabel: "View raw rotation response" });
        showToast(`Rotated ${row.key_prefix}. Store the new token now — it will not be shown again.`, "warn");
        await refreshVirtualKeys();
      }, { confirmMessage: `Rotate ${row.key_prefix}? The current token will stop working immediately and a new one will be issued.` }));
      actions.appendChild(createActionButton("Disable", async () => {
        const result = await apiFetch(`/admin/api/auth/virtual-keys/${encodeURIComponent(row.id)}/disable`, { method: "POST" });
        inspectVirtualKey(result, { rawLabel: "View raw response" });
        showToast(`Disabled ${row.key_prefix}.`, "warn");
        await refreshVirtualKeys();
      }, { destructive: true, confirmMessage: `Disable virtual key ${row.key_prefix}? Existing callers will stop working immediately.` }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, {
      icon: "⚷",
      title: "No virtual keys issued yet.",
      body: "Virtual keys grant scoped, budget- and rate-limited API access. Issue one with the form to the right to get started.",
      action: { label: "Issue your first key", onClick: () => $("#virtual-key-form input[name='display_name']")?.focus() },
    }, {
      pageKey: "#virtual-keys-table",
      itemLabel: "keys",
      serverPagination: serverPaginationForPayload("#virtual-keys-table", payload, page.limit, () => refreshVirtualKeys()),
    }),
  );
  if (!rows.length) {
    clearHost("#virtual-keys-output");
    $("#virtual-keys-output")?.appendChild(buildEmptyState({
      icon: "⚷",
      title: "Nothing to inspect yet.",
      body: "Issue a key, then choose “Inspect” on any row to see its full configuration here.",
    }));
  } else {
    clearHost("#virtual-keys-output");
    $("#virtual-keys-output")?.appendChild(buildEmptyState({
      icon: "→",
      title: "Select a key to inspect.",
      body: `${Number(payload.total || rows.length || 0)} key${Number(payload.total || rows.length || 0) === 1 ? "" : "s"} on file. Choose “Inspect” on any row in the directory to view its full configuration, limits, and spend here.`,
    }));
  }
  return rows;
}

function renderPerTokenCost(value) {
  if (value == null) return '<span class="empty-value">Not priced</span>';
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return escapeHtml(String(value));
  const per1k = renderAmount(numeric * 1000, { precision: 4 });
  const per1m = renderAmount(numeric * 1_000_000, { precision: 2 });
  return `${per1m} <span class="cell-secondary" style="display:inline; margin-left:6px;">/ 1M tokens · ${per1k} / 1K</span>`;
}

const PRICING_RECORD_FIELDS = [
  { key: "provider", label: "Provider", render: (value) => `<span class="badge badge-info">${escapeHtml(value)}</span>` },
  { key: "model", label: "Model", render: (value) => `<span class="cell-primary">${escapeHtml(value)}</span>` },
  { key: "input_cost_per_token", label: "Input Cost", render: (value) => renderPerTokenCost(value) },
  { key: "output_cost_per_token", label: "Output Cost", render: (value) => renderPerTokenCost(value) },
];

function inspectPricingRow(row) {
  state.selectedPricingKey = buildPricingKey(row);
  setActiveRuntimeRow("#pricing-table", state.selectedPricingKey);
  renderRecordView("#pricing-output", row, PRICING_RECORD_FIELDS, { rawLabel: "View raw catalog entry" });
}

async function refreshPricingCatalog() {
  setTableLoading("#pricing-table", {
    title: "Loading pricing catalog…",
    body: "Fetching vendor pricing rows for FinOps and routing analysis.",
  });
  const payload = await apiFetch("/admin/api/pricing/catalog");
  const rows = payload.items || [];
  state.pricingRows = rows;
  renderGovernanceSummary();
  refreshGovernanceGraphView();
  const host = $("#pricing-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Provider", "Model", "Input / 1M", "Output / 1M", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      const pricingKey = buildPricingKey(row);
      tr.dataset.recordId = pricingKey;
      if (pricingKey === state.selectedPricingKey) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><span class="badge badge-info">${escapeHtml(row.provider)}</span></td>
        <td><span class="cell-primary">${escapeHtml(row.model)}</span></td>
        <td>${row.input_cost_per_token == null ? '<span class="empty-value">-</span>' : renderAmount(Number(row.input_cost_per_token) * 1_000_000, { precision: 2 })}</td>
        <td>${row.output_cost_per_token == null ? '<span class="empty-value">-</span>' : renderAmount(Number(row.output_cost_per_token) * 1_000_000, { precision: 2 })}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectPricingRow(row);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => {
        inspectPricingRow(row);
      }, { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, {
      icon: "$",
      title: "Pricing catalog is empty.",
      body: "Per-token costs for connected providers and models will be listed here as they are registered.",
    }, { pageKey: "#pricing-table", pageSize: 15, itemLabel: "pricing rows" }),
  );
  clearHost("#pricing-output");
  $("#pricing-output")?.appendChild(buildEmptyState({
    icon: "→",
    title: "Select a model to inspect its pricing.",
    body: rows.length
      ? `${rows.length} priced model${rows.length === 1 ? "" : "s"} in the catalog. Choose “Inspect” on any row to see its full per-token, per-1K, and per-1M cost breakdown.`
      : "Pricing details will appear here once the catalog has entries.",
  }));
  return payload;
}

const GUARDRAILS_RECORD_FIELDS = [
  { key: "prompt_injection_blocking_enabled", label: "Prompt Injection Blocking", render: (value) => boolBadge(Boolean(value)) },
  { key: "pii_output_masking_enabled", label: "PII Output Masking", render: (value) => boolBadge(Boolean(value)) },
  { key: "pre_hooks", label: "Pre-Request Hooks", render: (value) => renderList(value, { emptyLabel: "No pre-request hooks configured" }) },
  { key: "post_hooks", label: "Post-Response Hooks", render: (value) => renderList(value, { emptyLabel: "No post-response hooks configured" }) },
  { key: "blocked_output_patterns", label: "Blocked Output Patterns", render: (value) => renderList(value, { emptyLabel: "No blocked patterns configured", limit: 6 }) },
];

async function refreshGuardrails() {
  const payload = await apiFetch("/admin/api/guardrails/settings");
  state.guardrailsSettings = payload;
  renderGovernanceSummary();
  refreshGovernanceGraphView();
  renderRecordView("#guardrails-table", payload, GUARDRAILS_RECORD_FIELDS, {
    raw: false,
    emptyState: { title: "No guardrail settings available.", body: "Guardrail configuration will appear here once it is available." },
  });
  renderRecordView("#guardrails-output", payload, GUARDRAILS_RECORD_FIELDS, {
    rawLabel: "View raw guardrail payload",
    emptyState: { title: "No guardrail detail available.", body: "Refresh guardrails to inspect the current policy here." },
  });
  return payload;
}

async function refreshObservability() {
  setTableLoadingMany(["#observability-table", "#ops-stream-live-table", "#ops-mcp-table"], {
    title: "Loading observability feeds…",
    body: "Fetching telemetry endpoints and support signal tables.",
  });
  const payload = await apiFetch("/admin/api/observability");
  renderMetricGrid("#observability-grid", [
    { label: "Prometheus", badge: boolBadge(Boolean(payload.prometheus?.enabled)), subvalue: payload.prometheus?.path || "-" },
    { label: "OTEL Export", badge: boolBadge(Boolean(payload.otel?.enabled)), subvalue: payload.otel?.service_name || "-" },
    { label: "Jaeger UI", value: payload.otel?.jaeger_ui_url || "-", subvalue: "Trace search endpoint" },
  ]);
  const host = $("#observability-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Surface", "Value"], [
      { key: "Prometheus Path", value: payload.prometheus?.path || "-" },
      { key: "OTLP Endpoint", value: payload.otel?.exporter_otlp_endpoint || "-" },
      { key: "Jaeger UI", value: payload.otel?.jaeger_ui_url || "-" },
      { key: "Scrape Job", value: payload.prometheus?.scrape_config?.job_name || "llmproxy" },
    ], (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><strong>${escapeHtml(row.key)}</strong></td><td>${escapeHtml(String(row.value ?? "-"))}</td>`;
      return tr;
    }, "No observability configuration available."),
  );
  renderOutput("#observability-output", payload);
  return payload;
}

const MCP_SERVER_RECORD_FIELDS = [
  { key: "server", label: "Server", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "transport", label: "Transport", render: (value) => `<span class="badge badge-muted">${escapeHtml(value || "stdio")}</span>` },
  { key: "configured", label: "Configured", render: (value) => boolBadge(Boolean(value)) },
  { key: "command", label: "Command", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "cwd", label: "Working Directory", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "timeout_seconds", label: "Timeout", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}s</span>` },
  { key: "tool_count", label: "Tools Exposed", render: (value) => `<span class="num">${escapeHtml(formattedValue(value ?? 0))}</span>` },
  { key: "tools", label: "Tools", hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml((value || []).map((tool) => `${tool.name}${tool.description ? ` — ${tool.description}` : ""}`).join("\n"))}</pre>` },
  { key: "error", label: "Error", hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(value)}</pre>` },
];

function inspectMcpServer(row, { rawLabel = "View raw server config" } = {}) {
  state.selectedMcpServerName = row?.server || null;
  setActiveRuntimeRow("#mcp-server-table", state.selectedMcpServerName || "");
  renderRecordView("#mcp-server-detail", row, MCP_SERVER_RECORD_FIELDS, { rawLabel });
}

const A2A_PEER_RECORD_FIELDS = [
  { key: "label", label: "Peer", render: (value, row) => `<span class="cell-primary">${escapeHtml(value || row.peer || "-")}</span>` },
  { key: "peer", label: "Peer Key", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "protocol", label: "Protocol", render: (value) => `<span class="badge badge-info">${escapeHtml(String(value || "a2a").toUpperCase())}</span>` },
  { key: "transport", label: "Transport", render: (value) => `<span class="badge badge-muted">${escapeHtml(value || "http")}</span>` },
  { key: "configured", label: "Configured", render: (value) => boolBadge(Boolean(value)) },
  { key: "auth_mode", label: "Auth", render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value || "none"))}</span>` },
  { key: "endpoint", label: "Endpoint", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "discovery_url", label: "Discovery URL", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "invoke_url", label: "Invoke URL", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "validation_mode", label: "Validation Mode", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "timeout_seconds", label: "Timeout", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}s</span>` },
  { key: "capabilities", label: "Configured Capabilities", render: (value) => renderList(value, { emptyLabel: "No configured capabilities" }) },
  { key: "labels", label: "Labels", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No labels" }) },
  { key: "notes", label: "Notes", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No notes", limit: 12 }) },
  { key: "validated", label: "Validated", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "status_code", label: "HTTP Status", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "latency_ms", label: "Latency", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))} ms</span>` },
  { key: "invoked_capability", label: "Invoked Capability", hideEmpty: true, render: (value) => `<span class="badge badge-info">${escapeHtml(value || "-")}</span>` },
  { key: "discovered_name", label: "Discovered Name", hideEmpty: true },
  { key: "discovered_description", label: "Discovered Description", hideEmpty: true },
  { key: "discovered_capabilities", label: "Discovered Capabilities", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No discovered capabilities" }) },
  { key: "parse_error", label: "Parse Error", hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(value)}</pre>` },
];

function currentSelectedA2APeer() {
  return (state.a2aPeers || []).find((row) => row.peer === state.selectedA2APeerName) || null;
}

function currentSelectedRestEndpoint() {
  return (state.restEndpoints || []).find((row) => row.endpoint_name === state.selectedRestEndpointName) || null;
}

function seedA2AInvokeForm(row) {
  const capabilityInput = $("#a2a-invoke-capability");
  const payloadInput = $("#a2a-invoke-input-json");
  if (!capabilityInput || !payloadInput) return;
  const firstCapability = (row?.discovered_capabilities || row?.capabilities || [])[0] || "";
  capabilityInput.value = String(firstCapability || "");
  payloadInput.value = JSON.stringify({ goal: `Use ${row?.label || row?.peer || "the selected peer"} to help with this request.` }, null, 2);
}

function inspectA2APeer(row, { rawLabel = "View raw A2A peer config" } = {}) {
  state.selectedA2APeerName = row?.peer || null;
  setActiveRuntimeRow("#a2a-peer-table", state.selectedA2APeerName || "");
  renderRecordView("#a2a-peer-detail", row, A2A_PEER_RECORD_FIELDS, { rawLabel });
  seedA2AInvokeForm(row);
  renderInteractionTraceTable(
    "#a2a-peer-interaction-trace-table",
    row?.interaction_traces || [],
    "No normalized interaction trace recorded for this A2A peer yet.",
  );
}

const REST_ENDPOINT_RECORD_FIELDS = [
  { key: "label", label: "Endpoint", render: (value, row) => `<span class="cell-primary">${escapeHtml(value || row.endpoint_name || "-")}</span>` },
  { key: "endpoint_name", label: "Endpoint Key", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "protocol", label: "Protocol", render: (value) => `<span class="badge badge-info">${escapeHtml(String(value || "rest").toUpperCase())}</span>` },
  { key: "transport", label: "Transport", render: (value) => `<span class="badge badge-muted">${escapeHtml(value || "http")}</span>` },
  { key: "configured", label: "Configured", render: (value) => boolBadge(Boolean(value)) },
  { key: "auth_mode", label: "Auth", render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value || "none"))}</span>` },
  { key: "endpoint", label: "Endpoint", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "validate_url", label: "Validate URL", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "invoke_url", label: "Invoke URL", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "validation_method", label: "Validation Method", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(value || "GET")}</span>` },
  { key: "default_method", label: "Default Method", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(value || "POST")}</span>` },
  { key: "timeout_seconds", label: "Timeout", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}s</span>` },
  { key: "header_count", label: "Headers", render: (value) => `<span class="num">${escapeHtml(formattedValue(value ?? 0))}</span>` },
  { key: "labels", label: "Labels", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No labels" }) },
  { key: "notes", label: "Notes", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No notes", limit: 12 }) },
  { key: "validated", label: "Validated", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "invoked", label: "Invoked", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "invoked_method", label: "Invoked Method", hideEmpty: true, render: (value) => `<span class="badge badge-info">${escapeHtml(value || "-")}</span>` },
  { key: "invoked_path", label: "Invoked Path", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "status_code", label: "HTTP Status", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "latency_ms", label: "Latency", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))} ms</span>` },
  { key: "parse_error", label: "Parse Error", hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(value)}</pre>` },
];

function seedRestInvokeForm(row) {
  const methodInput = $("#rest-invoke-method");
  const pathInput = $("#rest-invoke-path");
  const payloadInput = $("#rest-invoke-input-json");
  if (!methodInput || !pathInput || !payloadInput) return;
  methodInput.value = String(row?.default_method || "POST");
  pathInput.value = "";
  payloadInput.value = JSON.stringify({ id: "1234" }, null, 2);
}

function inspectRestEndpoint(row, { rawLabel = "View raw REST endpoint config" } = {}) {
  state.selectedRestEndpointName = row?.endpoint_name || null;
  setActiveRuntimeRow("#rest-endpoint-table", state.selectedRestEndpointName || "");
  renderRecordView("#rest-endpoint-detail", row, REST_ENDPOINT_RECORD_FIELDS, { rawLabel });
  seedRestInvokeForm(row);
  renderInteractionTraceTable(
    "#rest-endpoint-interaction-trace-table",
    row?.interaction_traces || [],
    "No normalized interaction trace recorded for this REST endpoint yet.",
  );
}

async function refreshMcpServers() {
  setTableLoading("#mcp-server-table", {
    title: "Loading MCP servers…",
    body: "Fetching configured MCP endpoints and validation state.",
  });
  const page = paginationParams("#mcp-server-table", 12);
  const params = new URLSearchParams({
    paginated: "true",
    limit: String(page.limit),
    offset: String(page.offset),
  });
  const payload = await apiFetch(`/admin/api/mcp/servers?${params.toString()}`);
  const rows = payload.items || [];
  state.mcpServers = rows;
  renderIntegrationsSummary();
  refreshIntegrationGraphView();
  const host = $("#mcp-server-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Server", "Transport", "Configured", "Tools", "Status", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.server;
      if (row.server === state.selectedMcpServerName) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.server)}</strong></td>
        <td>${escapeHtml(row.transport || "-")}</td>
        <td>${boolBadge(Boolean(row.configured))}</td>
        <td>${escapeHtml(String(row.tool_count ?? 0))}</td>
        <td>${row.error ? statusBadge("failed") : statusBadge(row.configured ? "connected" : "pending")}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectMcpServer(row);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => inspectMcpServer(row), { accent: true }));
      actions.appendChild(createActionButton("Validate", async () => {
        const result = await apiFetch(`/admin/api/mcp/servers/${encodeURIComponent(row.server)}/validate`, {
          method: "POST",
        });
        renderOutput("#mcp-server-output", result);
        inspectMcpServer(row, { rawLabel: "View raw validation response" });
        showToast(`Validated MCP server ${row.server}.`, "ok");
        await refreshMcpServers();
      }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Configured MCP servers will appear here.", {
      pageKey: "#mcp-server-table",
      itemLabel: "servers",
      serverPagination: serverPaginationForPayload("#mcp-server-table", payload, page.limit, () => refreshMcpServers()),
    }),
  );
  const serverCount = Number(payload.total || rows.length || 0);
  clearHost("#mcp-server-detail");
  if (!serverCount) {
    $("#mcp-server-detail")?.appendChild(buildEmptyState({
      icon: "🔌",
      title: "No MCP servers configured.",
      body: "Configure servers via LLMPROXY_MCP_SERVERS to expose their tools through the gateway.",
    }));
  } else {
    $("#mcp-server-detail")?.appendChild(buildEmptyState({
      icon: "→",
      title: "Select a server to inspect.",
      body: `${serverCount} server${serverCount === 1 ? "" : "s"} configured — choose “Inspect” on any row to see its transport, command, and exposed tools here.`,
    }));
  }
  renderOutput("#mcp-server-output", payload);
  return payload;
}

async function refreshA2APeers() {
  setTableLoading("#a2a-peer-table", {
    title: "Loading A2A peers…",
    body: "Fetching configured A2A endpoints and validation state.",
  });
  const page = paginationParams("#a2a-peer-table", 12);
  const params = new URLSearchParams({
    paginated: "true",
    limit: String(page.limit),
    offset: String(page.offset),
  });
  const payload = await apiFetch(`/admin/api/a2a/peers?${params.toString()}`);
  const rows = payload.items || [];
  state.a2aPeers = rows;
  renderIntegrationsSummary();
  refreshIntegrationGraphView();
  const host = $("#a2a-peer-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Peer", "Transport", "Configured", "Capabilities", "Status", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.peer;
      if (row.peer === state.selectedA2APeerName) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.label || row.peer || "-")}</strong><br/><span>${escapeHtml(row.peer || "-")}</span></td>
        <td>${escapeHtml(row.transport || "-")}</td>
        <td>${boolBadge(Boolean(row.configured))}</td>
        <td>${escapeHtml(String(row.capability_count ?? 0))}</td>
        <td>${statusBadge(row.configured ? "connected" : "pending")}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectA2APeer(row);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => inspectA2APeer(row), { accent: true }));
      actions.appendChild(createActionButton("Validate", async () => {
        const result = await apiFetch(`/admin/api/a2a/peers/${encodeURIComponent(row.peer)}/validate`, {
          method: "POST",
        });
        renderOutput("#a2a-peer-output", result);
        inspectA2APeer(result, { rawLabel: "View raw validation response" });
        showToast(`Validated A2A peer ${row.label || row.peer}.`, "ok");
        await refreshA2APeers();
      }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Configured A2A peers will appear here.", {
      pageKey: "#a2a-peer-table",
      itemLabel: "peers",
      serverPagination: serverPaginationForPayload("#a2a-peer-table", payload, page.limit, () => refreshA2APeers()),
    }),
  );
  const peerCount = Number(payload.total || rows.length || 0);
  clearHost("#a2a-peer-detail");
  if (!peerCount) {
    $("#a2a-peer-detail")?.appendChild(buildEmptyState({
      icon: "⇄",
      title: "No A2A peers configured.",
      body: "Configure peers via LLMPROXY_A2A_PEERS to proxy discovery, validation, and later delegated agent workflows through llmProxy.",
    }));
    $("#a2a-peer-invoke-form")?.reset();
    renderInteractionTraceTable(
      "#a2a-peer-interaction-trace-table",
      [],
      "No normalized interaction trace recorded for this A2A peer yet.",
    );
  } else {
    $("#a2a-peer-detail")?.appendChild(buildEmptyState({
      icon: "→",
      title: "Select an A2A peer to inspect.",
      body: `${peerCount} peer${peerCount === 1 ? "" : "s"} configured — choose “Inspect” on any row to see its discovery endpoint, auth mode, and capabilities here.`,
    }));
    $("#a2a-peer-invoke-form")?.reset();
    renderInteractionTraceTable(
      "#a2a-peer-interaction-trace-table",
      [],
      "No normalized interaction trace recorded for this A2A peer yet.",
    );
  }
  renderOutput("#a2a-peer-output", payload);
  return payload;
}

async function refreshRestEndpoints() {
  setTableLoading("#rest-endpoint-table", {
    title: "Loading REST endpoints…",
    body: "Fetching configured REST endpoints and validation state.",
  });
  const page = paginationParams("#rest-endpoint-table", 12);
  const params = new URLSearchParams({
    paginated: "true",
    limit: String(page.limit),
    offset: String(page.offset),
  });
  const payload = await apiFetch(`/admin/api/rest/endpoints?${params.toString()}`);
  const rows = payload.items || [];
  state.restEndpoints = rows;
  renderIntegrationsSummary();
  refreshIntegrationGraphView();
  const host = $("#rest-endpoint-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Endpoint", "Method", "Configured", "Auth", "Status", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.endpoint_name;
      if (row.endpoint_name === state.selectedRestEndpointName) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.label || row.endpoint_name || "-")}</strong><br/><span>${escapeHtml(row.endpoint_name || "-")}</span></td>
        <td>${escapeHtml(row.default_method || "-")}</td>
        <td>${boolBadge(Boolean(row.configured))}</td>
        <td><span class="badge badge-muted">${escapeHtml(humanizeLabel(row.auth_mode || "none"))}</span></td>
        <td>${statusBadge(row.configured ? "connected" : "pending")}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectRestEndpoint(row);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => inspectRestEndpoint(row), { accent: true }));
      actions.appendChild(createActionButton("Validate", async () => {
        const result = await apiFetch(`/admin/api/rest/endpoints/${encodeURIComponent(row.endpoint_name)}/validate`, {
          method: "POST",
        });
        renderOutput("#rest-endpoint-output", result);
        inspectRestEndpoint(result, { rawLabel: "View raw validation response" });
        showToast(`Validated REST endpoint ${row.label || row.endpoint_name}.`, "ok");
        await refreshRestEndpoints();
      }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Configured REST endpoints will appear here.", {
      pageKey: "#rest-endpoint-table",
      itemLabel: "endpoints",
      serverPagination: serverPaginationForPayload("#rest-endpoint-table", payload, page.limit, () => refreshRestEndpoints()),
    }),
  );
  const endpointCount = Number(payload.total || rows.length || 0);
  clearHost("#rest-endpoint-detail");
  if (!endpointCount) {
    $("#rest-endpoint-detail")?.appendChild(buildEmptyState({
      icon: "⇄",
      title: "No REST endpoints configured.",
      body: "Configure endpoints via LLMPROXY_REST_ENDPOINTS to proxy validation and generic HTTP JSON execution through llmProxy.",
    }));
    $("#rest-endpoint-invoke-form")?.reset();
    renderInteractionTraceTable(
      "#rest-endpoint-interaction-trace-table",
      [],
      "No normalized interaction trace recorded for this REST endpoint yet.",
    );
  } else {
    $("#rest-endpoint-detail")?.appendChild(buildEmptyState({
      icon: "→",
      title: "Select a REST endpoint to inspect.",
      body: `${endpointCount} endpoint${endpointCount === 1 ? "" : "s"} configured — choose “Inspect” on any row to see its URLs, methods, and recent validation or invocation details here.`,
    }));
    $("#rest-endpoint-invoke-form")?.reset();
    renderInteractionTraceTable(
      "#rest-endpoint-interaction-trace-table",
      [],
      "No normalized interaction trace recorded for this REST endpoint yet.",
    );
  }
  renderOutput("#rest-endpoint-output", payload);
  return payload;
}

async function validateConfig() {
  const payload = await apiFetch("/admin/api/config/validate");
  logConsole("config validate", payload);
  renderOutput("#provider-guide-output", payload.provider_guides || []);
}

const STREAMING_VALIDATION_RECORD_FIELDS = [
  { key: "success", label: "Result", render: (_value, row) => renderStreamingValidationOutcomeBadge(row) },
  { key: "validation_scope", label: "Scope", hideEmpty: true, render: (value) => `<span class="badge badge-info">${escapeHtml(humanizeLabel(String(value).replaceAll("_", " ")))}</span>` },
  { key: "target_filter", label: "Target Filter", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(String(value).replaceAll("_", " ")))}</span>` },
  { key: "listener_id", label: "Listener", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "listener_url", label: "Front Door", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "requested_model", label: "Requested Model", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "provider_key", label: "Provider", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "provider_family", label: "Provider Family", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "model", label: "Model", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "execution_mode", label: "Execution Mode", hideEmpty: true, render: (value) => `<span class="badge badge-info">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "traffic_origin", label: "Traffic Origin", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "automation_owner_id", label: "Pipeline Owner", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "request_id", label: "Verified Request", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "candidate_id", label: "Captured Candidate", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "candidate_captured", label: "Candidate Capture", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "learning_pipeline_verified", label: "Learning Pipeline", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "target_count", label: "Targets", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "validated_count", label: "Validated", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "failed_count", label: "Failed", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "max_concurrency", label: "Max Concurrency", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "discovered_model_count", label: "Discovered Models", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "streamable_model_count", label: "Streamable Models", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "chat_capable_subset_count", label: "Chat-Capable Subset", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "skipped_model_count", label: "Skipped", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "skipped_models", label: "Skipped Models", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No skipped models" }) },
  { key: "elapsed_ms", label: "Elapsed (ms)", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "cache_hit", label: "Cache Hit", hideEmpty: true, render: (value) => boolBadge(Boolean(value)) },
  { key: "cache_age_seconds", label: "Cache Age (s)", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "error", label: "Error Detail", hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(value)}</pre>` },
  { key: "preview_text", label: "Streamed Preview", hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(value)}</pre>` },
  { key: "finish_reason", label: "Finish Reason", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "chunk_count", label: "Chunk Count", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "input_tokens", label: "Input Tokens", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "output_tokens", label: "Output Tokens", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "validated_by", label: "Validated By", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
];

const STREAMING_SUPPORT_RECORD_FIELDS = [
  { key: "provider_name", label: "Provider", render: (value, row) => `<span class="cell-primary">${escapeHtml(value || row.provider_key || "Unknown provider")}</span>` },
  { key: "provider_key", label: "Provider Key", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "provider_family", label: "Provider Family", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "model_id", label: "Model", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "configured", label: "Configured", render: (value) => boolBadge(Boolean(value)) },
  { key: "supports_streaming", label: "Streaming", render: (value) => boolBadge(Boolean(value)) },
];

function currentStreamingSupportRow() {
  return (state.streamingSupportPayload?.providers || []).find((row) => buildStreamingSupportKey(row) === state.selectedStreamingSupportKey) || null;
}

function renderStreamingValidationListenerOptions(selector = "#streaming-listener-id") {
  const select = $(selector);
  if (!select) return;
  const listeners = (state.configPayload?.llmproxy_inbound_listeners || []).filter((listener) => Boolean(listener?.exposes_proxy));
  const currentValue = select.value;
  select.innerHTML = "";
  if (!listeners.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No proxy listeners available";
    select.appendChild(option);
    select.disabled = true;
    return;
  }
  listeners.forEach((listener) => {
    const option = document.createElement("option");
    option.value = String(listener.listener_id || "");
    option.textContent = `${listener.name || listener.listener_id} (${listener.published_host || "127.0.0.1"}:${listener.published_port || listener.port})`;
    select.appendChild(option);
  });
  select.disabled = false;
  const nextValue = listeners.some((listener) => String(listener.listener_id || "") === currentValue)
    ? currentValue
    : String(listeners[0].listener_id || "");
  select.value = nextValue;
}

function renderStreamingValidationTarget(row = null) {
  const node = $("#streaming-validation-target");
  const button = $("#run-streaming-validation");
  if (!node) return;
  if (!row) {
    node.textContent = "Select a target row first. The test calls the proxy through one chosen listener, executes routing, streams a response, and verifies the recorded artifacts.";
    if (button) button.disabled = true;
    return;
  }
  node.textContent = `Targeting ${row.provider_name || row.provider_key} / ${row.model_id}. This front-door test will execute routing, stream output, and confirm the resulting request and candidate records.`;
  if (button) button.disabled = false;
}

function renderStreamingValidationOutcomeBadge(row) {
  if (!row?.success) {
    return '<span class="badge badge-err">Hard Failure</span>';
  }
  if (String(row?.selected_mode || "").toLowerCase() === "fallback") {
    return '<span class="badge badge-warn">Fallback Success</span>';
  }
  return '<span class="badge badge-ok">Direct Success</span>';
}

function filteredStreamingSupportRows(rows) {
  const query = String(state.streamingSupportQuery || "").trim().toLowerCase();
  return (rows || []).filter((row) => {
    if (state.streamingSupportConfiguredOnly && !row.configured) return false;
    if (state.streamingSupportStreamableOnly && !row.supports_streaming) return false;
    if (!query) return true;
    const haystack = [
      row.provider_name,
      row.provider_key,
      row.model_id,
      row.provider_family,
    ].map((value) => String(value || "").toLowerCase()).join(" ");
    return haystack.includes(query);
  });
}

function inspectStreamingSupportRow(row, { preserveOutput = false } = {}) {
  state.selectedStreamingSupportKey = buildStreamingSupportKey(row);
  setActiveRuntimeRow("#streaming-support-table", state.selectedStreamingSupportKey);
  setFieldValue("#streaming-validate-form", "provider_key", row?.provider_key || "");
  setFieldValue("#streaming-validate-form", "requested_model", row?.model_id || "proxy-auto");
  renderStreamingValidationTarget(row);
  if (preserveOutput) {
    return;
  }
  renderRecordView("#streaming-target-summary-table", row, STREAMING_SUPPORT_RECORD_FIELDS, {
    emptyState: {
      icon: "▷",
      title: "No stream target selected.",
      body: "Choose a stream target row to inspect one provider/model readiness record and prepare a probe against it.",
    },
  });
  renderOutput("#streaming-target-output", row);
}

function showStreamingValidationResult(result) {
  renderRecordView("#streaming-validation-summary-table", result, STREAMING_VALIDATION_RECORD_FIELDS, {
    emptyState: {
      icon: "▷",
      title: "No validation run yet.",
      body: "Select a target and run a short probe to confirm streaming behavior and preview what comes back.",
    },
  });
  const resultsHost = $("#streaming-validation-results-table");
  if (resultsHost) {
    resultsHost.innerHTML = "";
    const rows = Array.isArray(result?.results) ? result.results : [];
    if (!rows.length) {
      resultsHost.classList.add("hidden");
    } else {
      resultsHost.classList.remove("hidden");
      resultsHost.appendChild(
        makeTable(
          ["Requested Model", "Resolved Route", "Outcome", "Chunks", "Finish", "Error"],
          rows,
          (row) => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
              <td>${renderIdChip(row.requested_model || "-", { truncate: false })}</td>
              <td><strong>${escapeHtml(row.provider_key || "-")}</strong><br/><span>${escapeHtml(row.model || row.requested_model || "-")}</span></td>
              <td>${renderStreamingValidationOutcomeBadge(row)}</td>
              <td><span class="num">${escapeHtml(formattedValue(row.chunk_count || 0))}</span></td>
              <td>${escapeHtml(row.finish_reason || "-")}</td>
              <td>${row.error ? `<pre class="value-pre">${escapeHtml(String(row.error))}</pre>` : '<span class="empty-value">-</span>'}</td>
            `;
            return tr;
          },
          "No per-model validation results are available.",
        ),
      );
    }
  }
  renderOutput("#streaming-validation-output", result);
}

async function refreshStreamingSupport() {
  setTableLoading("#streaming-support-table", {
    title: "Loading stream targets…",
    body: "Fetching configured provider and model streaming support.",
  });
  const payload = await apiFetch("/admin/api/proxy/streaming-support");
  state.streamingSupportPayload = payload;
  const filteredRows = filteredStreamingSupportRows(payload.providers || []);
  const host = $("#streaming-support-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Provider", "Model", "Configured", "Streaming", "Family"], filteredRows, (row) => {
      const tr = document.createElement("tr");
      const recordKey = buildStreamingSupportKey(row);
      tr.dataset.recordId = recordKey;
      if (recordKey === state.selectedStreamingSupportKey) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${row.provider_name}</strong></td>
        <td>${row.model_id}</td>
        <td>${boolBadge(row.configured)}</td>
        <td>${boolBadge(row.supports_streaming)}</td>
        <td>${row.provider_family}</td>
      `;
      tr.addEventListener("click", () => inspectStreamingSupportRow(row));
      return tr;
    }, "Streaming validation targets will render here once configuration is loaded.", { pageKey: "#streaming-support-table", pageSize: 15, itemLabel: "targets" }),
  );
  const selected = filteredRows.find((row) => buildStreamingSupportKey(row) === state.selectedStreamingSupportKey);
  if (selected) {
    inspectStreamingSupportRow(selected);
  } else {
    state.selectedStreamingSupportKey = null;
    renderStreamingValidationTarget(null);
    renderRecordView("#streaming-target-summary-table", null, STREAMING_SUPPORT_RECORD_FIELDS, {
      emptyState: {
        icon: "▷",
        title: "No stream target selected.",
        body: "Choose a stream target row to inspect one provider/model readiness record and prepare a probe against it.",
      },
    });
    renderOutput("#streaming-target-output", null);
    showStreamingValidationResult(null);
  }
  return payload;
}

function buildFoundationProviderGroups({ health = null, streaming = null, catalogRows = [], policies = [] } = {}) {
  const providerMap = new Map();
  const activePolicyEntries = Array.isArray(policies?.[0]?.policy?.entries) ? policies[0].policy.entries : [];
  const historicalPolicyEntries = Array.isArray(policies)
    ? policies.slice(1).flatMap((policyVersion) => Array.isArray(policyVersion?.policy?.entries) ? policyVersion.policy.entries : [])
    : [];
  const visibilityScope = currentFoundationModelVisibilityScope();
  const ensureProvider = (providerKey, fields = {}) => {
    const normalizedKey = String(providerKey || "");
    if (!providerMap.has(normalizedKey)) {
      providerMap.set(normalizedKey, {
        provider_key: normalizedKey,
        provider_name: normalizedKey,
        provider_family: fields.provider_family || normalizedKey,
        configured: false,
        status: "unavailable",
        healthy_model_count: 0,
        streaming_model_count: 0,
        routed_model_count: 0,
        model_count: 0,
        note: "",
        models: [],
      });
    }
    const provider = providerMap.get(normalizedKey);
    Object.assign(provider, fields);
    if (!Array.isArray(provider.models)) {
      provider.models = [];
    }
    return provider;
  };
  const ensureModel = (provider, modelId) => {
    let model = provider.models.find((item) => item.model_id === modelId);
    if (!model) {
      model = {
        model_id: modelId,
        status: "unavailable",
        streaming_supported: false,
        exposed: false,
        routed: false,
        active: false,
        historical: false,
        routing_modes: [],
        domains: [],
        regions: [],
        note: "",
      };
      provider.models.push(model);
    }
    return model;
  };

  (health?.provider_readiness || []).forEach((group) => {
    if (String(group.provider_key || "").startsWith("local:") || String(group.provider_family || "").toLowerCase() === "local runtime") {
      return;
    }
    const provider = ensureProvider(group.provider_key, {
      provider_name: group.provider_name || group.provider_key,
      provider_family: group.provider_family || group.provider_key,
      configured: Boolean(group.configured),
      status: group.status || "unavailable",
      healthy_model_count: Number(group.healthy_model_count || 0),
      model_count: Number(group.model_count || 0),
      note: group.note || "",
    });
    (group.models || []).forEach((row) => {
      Object.assign(ensureModel(provider, row.model_id), {
        status: row.status || (row.ok ? "healthy" : "unavailable"),
        latency_ms: row.latency_ms,
        source: row.source || "",
        note: row.error || row.detail || "",
        active: true,
      });
    });
  });

  (streaming?.providers || []).forEach((row) => {
    if (String(row.provider_family || "").toLowerCase() === "local runtime") {
      return;
    }
    const providerKey = String(row.provider_key || row.provider_name || "");
    const provider = ensureProvider(providerKey, {
      provider_name: row.provider_name || providerKey,
      provider_family: row.provider_family || providerKey,
      configured: Boolean(row.configured) || providerMap.get(providerKey)?.configured,
    });
    const model = ensureModel(provider, row.model_id);
    model.streaming_supported = Boolean(row.supports_streaming);
    if (row.supports_streaming) {
      provider.streaming_model_count = (provider.streaming_model_count || 0) + 1;
    }
  });

  (catalogRows || []).forEach((row) => {
    if (String(row.provider_family || "").toLowerCase() === "local runtime") {
      return;
    }
    const providerKey = String(row.provider_key || row.provider_name || row.provider_family || "");
    const provider = ensureProvider(providerKey, {
      provider_name: row.provider_name || providerKey,
      provider_family: row.provider_family || providerKey,
    });
    const model = ensureModel(provider, row.model_id);
    model.exposed = true;
    model.active = true;
    model.streaming_supported = model.streaming_supported || Boolean(row.supports_streaming);
    model.supports_embeddings = Boolean(row.supports_embeddings);
    model.supports_tools = Boolean(row.supports_tools);
  });

  activePolicyEntries.forEach((entry) => {
    const providerKey = String(entry.provider_key || "");
    if (!providerKey || providerKey.startsWith("local:")) return;
    const modelId = String(entry.model_id || entry.model_alias || "");
    const provider = ensureProvider(providerKey, {
      provider_name: providerKey,
      provider_family: entry.provider_family || providerKey,
    });
    const model = ensureModel(provider, modelId);
    model.routed = true;
    model.active = true;
    model.routing_modes = Array.from(new Set([...(model.routing_modes || []), String(entry.deployment_mode || "production")]));
    model.domains = Array.from(new Set([...(model.domains || []), ...((entry.domains || []).map(String))]));
    model.regions = Array.from(new Set([...(model.regions || []), ...((entry.regions || []).map(String))]));
  });

  historicalPolicyEntries.forEach((entry) => {
    const providerKey = String(entry.provider_key || "");
    if (!providerKey || providerKey.startsWith("local:")) return;
    const modelId = String(entry.model_id || entry.model_alias || "");
    const provider = ensureProvider(providerKey, {
      provider_name: providerKey,
      provider_family: entry.provider_family || providerKey,
    });
    const model = ensureModel(provider, modelId);
    model.historical = true;
    model.note = model.note || "Historical policy reference.";
  });

  return Array.from(providerMap.values())
    .map((provider) => {
      provider.models = (provider.models || [])
        .filter((model) => {
          const historicalOnly = Boolean(model.historical) && !Boolean(model.active);
          if (visibilityScope === "historical") {
            return historicalOnly;
          }
          if (visibilityScope === "all") {
            return Boolean(model.active) || Boolean(model.historical);
          }
          return Boolean(model.active);
        })
        .sort((a, b) => String(a.model_id).localeCompare(String(b.model_id)));
      provider.model_count = provider.models.length;
      provider.healthy_model_count = provider.models.filter((item) => item.status === "healthy").length;
      provider.streaming_model_count = provider.models.filter((item) => item.streaming_supported).length;
      provider.routed_model_count = provider.models.filter((item) => item.routed).length;
      return provider;
    })
    .filter((provider) => provider.model_count > 0)
    .sort((a, b) => String(a.provider_name).localeCompare(String(b.provider_name)));
}

function applyFoundationProviderGroups(groups) {
  state.foundationProviderGroups = Array.isArray(groups) ? groups : [];
  renderFoundationProviderTree("#models-table", state.foundationProviderGroups);
  if (!state.foundationProviderGroups.length) {
    renderRecordView("#model-detail-summary-table", {}, FOUNDATION_PROVIDER_FIELDS, {
      raw: false,
      emptyState: { title: "No providers available.", body: "Refresh the provider directory once configuration and health data are available." },
    });
    renderFoundationModelDetail({});
    const providerModelTable = $("#provider-model-table");
    if (providerModelTable) providerModelTable.innerHTML = "";
    return;
  }
  const selected = state.foundationProviderGroups.find((item) => buildFoundationProviderKey(item) === state.selectedFoundationProviderKey) || state.foundationProviderGroups[0];
  inspectFoundationProvider(selected);
}

async function refreshModels() {
  setTableLoading("#models-table", {
    title: "Loading vendor LLMs…",
    body: "Fetching vendor readiness, routing exposure, and streaming support.",
  });
  const [payload, policies] = await Promise.all([
    apiFetch("/models"),
    apiFetch("/deployment/routing-policies"),
  ]);
  state.modelCatalogRows = Array.isArray(payload) ? payload : [];
  state.proxyModelOptions = payload
    .map((row) => ({
      id: String(row.id || row.model_id || ""),
      family: "Proxy model",
      description: String(row.id || row.model_id || "") === "proxy-auto"
        ? "Router-managed automatic selection."
        : String(row.id || row.model_id || "") === "proxy-local"
          ? "Local-first route selection."
          : "Proxy model preset.",
      supports_embeddings: Boolean(row.supports_embeddings),
      supports_tools: Boolean(row.supports_tools),
      kind: "proxy",
    }))
    .filter((row) => row.id.startsWith("proxy-"))
    .sort((a, b) => a.id.localeCompare(b.id));
  applyFoundationProviderGroups(buildFoundationProviderGroups({
    catalogRows: state.modelCatalogRows,
    policies,
  }));

  try {
    const [health, streaming] = await Promise.all([
      apiFetch("/health"),
      apiFetch("/admin/api/proxy/streaming-support"),
    ]);
    state.healthPayload = health;
    state.streamingSupportPayload = streaming;
    renderOverviewSummary();
    applyFoundationProviderGroups(buildFoundationProviderGroups({
      health,
      streaming,
      catalogRows: state.modelCatalogRows,
      policies,
    }));
  } catch (error) {
    showToast(`Loaded vendor LLM directory before readiness enrichment: ${String(error)}`, "warn");
    logConsole("vendor llm enrichment failed", String(error));
  }
  return state.foundationProviderGroups;
}

async function refreshLocalModels() {
  setTableLoading("#local-models-table", {
    title: "Loading custom LLMs…",
    body: "Fetching registered internal model packages.",
  });
  const page = paginationParams("#local-models-table", 15);
  const params = new URLSearchParams({
    paginated: "true",
    limit: String(page.limit),
    offset: String(page.offset),
  });
  const [payload, deploymentPayload] = await Promise.all([
    apiFetch(`/models/local?${params.toString()}`),
    apiFetch("/deployment/models/local-inventory").catch(() => []),
  ]);
  const deploymentRows = Array.isArray(deploymentPayload) ? deploymentPayload : [];
  const deploymentByAlias = new Map(deploymentRows.map((row) => [String(row.model_alias || ""), row]));
  const rows = (payload.items || []).map((row) => ({
    ...row,
    ...(deploymentByAlias.get(String(row.model_alias || "")) || {}),
  }));
  state.localModelRows = rows;
  const host = $("#local-models-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Alias", "Base Model", "Runtime", "Lifecycle", "Domains", "Status", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = String(row.model_alias || "");
      if (String(row.model_alias || "") === state.selectedLocalModelAlias) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.model_alias)}</strong></td>
        <td>${escapeHtml(row.base_model)}</td>
        <td>${row.runtime_target ? statusBadge(row.runtime_target) : '<span class="empty-value">-</span>'}</td>
        <td>${statusBadge(row.lifecycle_stage || "registered")}</td>
        <td>${escapeHtml((row.domains || []).join(", ") || "-")}</td>
        <td>${statusBadge(row.promotion_status || "-")}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectLocalModel(row);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => inspectLocalModel(row), { accent: true }));
      if (row.runtime_target) {
        actions.appendChild(createActionButton("Open Runtime", async () => {
          await openRuntimeHostingContext(row.runtime_target);
        }));
      }
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Onboarded local packages will appear here.", {
      pageKey: "#local-models-table",
      itemLabel: "packages",
      serverPagination: serverPaginationForPayload("#local-models-table", payload, page.limit, () => refreshLocalModels()),
    }),
  );
  const selected = rows.find((row) => String(row.model_alias || "") === String(state.selectedLocalModelAlias || ""));
  if (selected) {
    inspectLocalModel(selected);
  } else if (state.activeModelCatalogCollection === "local") {
    renderLocalPackageDetail(null);
  }
  return rows;
}

const LOCAL_RUNTIME_DETAIL_FIELDS = [
  { key: "runtime", label: "Runtime", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "configured", label: "Configured", render: (value) => boolBadge(Boolean(value)) },
  { key: "reachable", label: "Reachable", render: (value) => boolBadge(Boolean(value)) },
  { key: "base_url", label: "Base URL", render: (value) => value ? renderIdChip(value, { truncate: false }) : '<span class="empty-value">-</span>' },
  { key: "package_alias_count", label: "Registered", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
  { key: "deployed_alias_count", label: "Deployed", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
  { key: "active_route_count", label: "Routed Live", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
  { key: "models_visible", label: "Visible Models", render: (value) => value != null ? `<span class="num">${escapeHtml(formattedValue(value))}</span>` : '<span class="empty-value">-</span>' },
  { key: "detail", label: "Runtime Detail", hideEmpty: true, render: (value) => `<span>${escapeHtml(value)}</span>` },
];

const OLLAMA_RECONCILE_FIELDS = [
  { key: "runtime", label: "Runtime", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "base_url", label: "Base URL", render: (value) => value ? renderIdChip(value, { truncate: false }) : '<span class="empty-value">-</span>' },
  { key: "installed_model_count", label: "Installed Models", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
  { key: "managed_package_count", label: "Managed Packages", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
  { key: "missing_base_model_count", label: "Missing Base Models", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
  { key: "missing_alias_count", label: "Missing Aliases", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
];

const LOCAL_DEPLOYMENT_DETAIL_FIELDS = [
  { key: "model_alias", label: "Model Alias", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "base_model", label: "Base Model", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "lifecycle_stage", label: "Lifecycle", render: (value) => statusBadge(value || "registered") },
  { key: "promotion_status", label: "Promotion", render: (value) => statusBadge(value || "-") },
  { key: "runtime_target", label: "Runtime Target", render: (value) => statusBadge(value || "-") },
  { key: "deployment_runtime", label: "Deployment Runtime", hideEmpty: true, render: (value) => statusBadge(value || "-") },
  { key: "deployment_status", label: "Deployment Status", render: (value) => statusBadge(value || "not_deployed") },
  { key: "routing_state", label: "Routing State", render: (value) => statusBadge(value || "not_routed") },
  { key: "active_route_mode", label: "Route Mode", hideEmpty: true, render: (value) => statusBadge(value || "-") },
  { key: "endpoint_url", label: "Endpoint", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
];

const DEPLOY_RUNTIME_GRAPH_FIELDS = [
  { key: "runtime", label: "Runtime", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "configured", label: "Configured", render: (value) => boolBadge(Boolean(value)) },
  { key: "reachable", label: "Reachable", render: (value) => boolBadge(Boolean(value)) },
  { key: "base_url", label: "Base URL", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "package_alias_count", label: "Registered Packages", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
  { key: "deployed_alias_count", label: "Deployed Packages", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
  { key: "active_route_count", label: "Live Routes", render: (value) => `<span class="num">${escapeHtml(formattedValue(value || 0))}</span>` },
  { key: "detail", label: "Runtime Detail", hideEmpty: true },
];

const DEPLOY_ROUTE_GRAPH_FIELDS = [
  { key: "model_alias", label: "Model Alias", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "routing_state", label: "Routing State", render: (value) => statusBadge(value || "not_routed") },
  { key: "active_route_mode", label: "Route Mode", hideEmpty: true, render: (value) => statusBadge(value || "-") },
  { key: "active_route_runtime", label: "Route Runtime", hideEmpty: true, render: (value) => statusBadge(value || "-") },
  { key: "active_route_endpoint_url", label: "Live Endpoint", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "active_route_domains", label: "Domains", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "All domains" }) },
  { key: "active_route_task_types", label: "Task Types", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "All task types" }) },
];

function deploymentRowsForRuntime(runtimeName) {
  return (state.localDeploymentRows || []).filter((row) => {
    const runtimeTarget = String(row.runtime_target || "");
    const deploymentRuntime = String(row.deployment_runtime || "");
    return runtimeTarget === String(runtimeName || "") || deploymentRuntime === String(runtimeName || "");
  });
}

function deploymentLifecycleStage(row) {
  if (row?.routed_live) return "routed_live";
  if (String(row?.deployment_status || "") === "deployed") return "deployed";
  return "registered";
}

function prepareDeployFormFromInventory(row) {
  setFieldValue("#deploy-form", "model_alias", row?.model_alias || "");
  setFieldValue("#deploy-form", "domains", (row?.domains || []).join(","));
  setFieldValue("#deploy-form", "task_types", (row?.task_types || []).join(","));
}

function deploymentGraphArtifactKey(artifact) {
  return `${artifact?.kind || "artifact"}:${artifact?.id || ""}`;
}

function deploymentGraphEdgeKey(edge) {
  return `${edge?.from || ""}->${edge?.to || ""}`;
}

function buildDeploymentGraphEdgeArtifact(edge, artifactLookup) {
  if (!edge) return null;
  const fromArtifact = artifactLookup.get(edge.from);
  const toArtifact = artifactLookup.get(edge.to);
  if (!fromArtifact || !toArtifact) return null;
  return {
    kind: "edge",
    id: deploymentGraphEdgeKey(edge),
    title: `${fromArtifact.title} -> ${toArtifact.title}`,
    subtitle: `${graphArtifactLabel(fromArtifact.kind)} to ${graphArtifactLabel(toArtifact.kind)}`,
    detail: {
      path: `${fromArtifact.title} -> ${toArtifact.title}`,
      from_label: graphArtifactLabel(fromArtifact.kind),
      from_title: fromArtifact.title,
      to_label: graphArtifactLabel(toArtifact.kind),
      to_title: toArtifact.title,
      detail: "Lifecycle path segment between two deployment artifacts.",
    },
    openArtifact: toArtifact,
  };
}

function buildDeploymentGraphData(rows = [], runtimeRows = []) {
  const packages = [];
  const deployments = [];
  const runtimes = [];
  const routes = [];
  const edges = [];
  const packageMap = new Map();
  const deploymentMap = new Map();
  const runtimeMap = new Map();
  const routeMap = new Map();
  const runtimeLookup = new Map((runtimeRows || []).map((row) => [String(row.runtime || ""), row]));
  const addArtifact = (collection, map, artifact) => {
    if (!artifact?.id) return null;
    const key = deploymentGraphArtifactKey(artifact);
    if (!map.has(key)) {
      map.set(key, artifact);
      collection.push(artifact);
    }
    return map.get(key);
  };
  const addEdge = (from, to) => {
    if (!from || !to) return;
    const key = `${from}->${to}`;
    if (edges.some((edge) => `${edge.from}->${edge.to}` === key)) return;
    edges.push({ from, to });
  };
  (rows || []).forEach((row) => {
    const alias = String(row.model_alias || "");
    if (!alias) return;
    const packageArtifact = addArtifact(packages, packageMap, {
      kind: "package",
      id: alias,
      title: alias,
      subtitle: row.base_model ? `Base ${row.base_model}` : "Onboarded package",
      detail: row,
    });
    const deploymentArtifact = addArtifact(deployments, deploymentMap, {
      kind: "deployment",
      id: alias,
      title: alias,
      subtitle: `${humanizeLabel(row.deployment_status || "not deployed")} • ${humanizeLabel(row.lifecycle_stage || "registered")}`,
      detail: row,
    });
    addEdge(deploymentGraphArtifactKey(packageArtifact), deploymentGraphArtifactKey(deploymentArtifact));
    const runtimeName = String(row.deployment_runtime || row.runtime_target || "").trim();
    if (runtimeName) {
      const runtimeRow = runtimeLookup.get(runtimeName) || null;
      const runtimeArtifact = addArtifact(runtimes, runtimeMap, {
        kind: "runtime",
        id: runtimeName,
        title: runtimeName,
        subtitle: runtimeRow?.reachable ? "Reachable runtime" : runtimeRow?.configured ? "Configured runtime" : "Runtime target",
        detail: runtimeRow || {
          runtime: runtimeName,
          configured: Boolean(runtimeRow?.configured),
          reachable: Boolean(runtimeRow?.reachable),
          base_url: row.endpoint_url || "",
          package_alias_count: deploymentRowsForRuntime(runtimeName).length,
          deployed_alias_count: deploymentRowsForRuntime(runtimeName).filter((item) => String(item.deployment_status || "") === "deployed").length,
          active_route_count: deploymentRowsForRuntime(runtimeName).filter((item) => Boolean(item.routed_live)).length,
          detail: "Derived from deployment inventory",
        },
      });
      addEdge(deploymentGraphArtifactKey(deploymentArtifact), deploymentGraphArtifactKey(runtimeArtifact));
      if (row.routed_live) {
        const routeArtifact = addArtifact(routes, routeMap, {
          kind: "route",
          id: alias,
          title: alias,
          subtitle: `${humanizeLabel(row.active_route_mode || "live")} route`,
          detail: row,
        });
        addEdge(deploymentGraphArtifactKey(runtimeArtifact), deploymentGraphArtifactKey(routeArtifact));
      }
    }
  });
  return { packages, deployments, runtimes, routes, edges };
}

function renderDeploymentGraphDetail(artifact = null) {
  const heading = $("#deploy-detail-heading");
  if (heading) {
    heading.textContent = artifact?.title
      ? ({
        edge: "Selected Graph Edge",
        package: `Package: ${artifact.title}`,
        deployment: `Deployment: ${artifact.title}`,
        runtime: `Runtime: ${artifact.title}`,
        route: `Live Route: ${artifact.title}`,
      }[artifact.kind] || "Selected Deployment")
      : "Selected Deployment";
  }
  if (!artifact) {
    renderRecordView("#deploy-detail-summary", null, [], {
      raw: false,
      emptyState: {
        title: "No graph artifact selected.",
        body: "Hover or click a package, deployment, runtime, or live-route node in the graph to inspect its lifecycle detail here.",
      },
    });
    return;
  }
  if (artifact.kind === "edge") {
    renderRecordView("#deploy-detail-summary", artifact.detail || {}, GRAPH_EDGE_RECORD_FIELDS, {
      rawLabel: "View raw graph edge record",
    });
    return;
  }
  if (artifact.kind === "runtime") {
    renderRecordView("#deploy-detail-summary", artifact.detail || {}, DEPLOY_RUNTIME_GRAPH_FIELDS, {
      rawLabel: "View raw runtime record",
    });
    return;
  }
  if (artifact.kind === "route") {
    renderRecordView("#deploy-detail-summary", artifact.detail || {}, DEPLOY_ROUTE_GRAPH_FIELDS, {
      rawLabel: "View raw live route record",
    });
    return;
  }
  renderLocalDeploymentDetail(artifact.detail || null);
}

async function openDeploymentGraphContext(artifact) {
  if (!artifact) return;
  if (artifact.kind === "edge" && artifact.openArtifact) {
    artifact = artifact.openArtifact;
  }
  if (artifact.kind === "runtime") {
    await openRuntimeHostingContext(String(artifact.id || ""));
    return;
  }
  if (artifact.kind === "route") {
    await openLocalDeploymentRoutingContext(String(artifact.id || ""));
    return;
  }
  await openLocalDeploymentWorkspaceContext(String(artifact.id || ""));
}

function renderDeploymentGraph(data = null) {
  const host = $("#deploy-graph");
  if (!host) return;
  host.innerHTML = "";
  const packages = data?.packages || [];
  const deployments = data?.deployments || [];
  const runtimes = data?.runtimes || [];
  const routes = data?.routes || [];
  renderSummaryChips("#deploy-graph-summary-strip", [
    { label: "Packages", value: String(packages.length) },
    { label: "Deployment Steps", value: String(deployments.length) },
    { label: "Runtimes", value: String(runtimes.length) },
    { label: "Live Routes", value: String(routes.length) },
  ]);
  if (!packages.length) {
    host.appendChild(buildEmptyState({
      icon: "⇄",
      title: "No graph artifacts available.",
      body: "Onboard local packages to render the deployment graph.",
    }));
    renderDeploymentGraphDetail(null);
    return;
  }
  const columns = [
    { title: "Packages", items: packages, x: 40 },
    { title: "Deployment State", items: deployments, x: 290 },
    { title: "Runtime", items: runtimes, x: 540 },
    { title: "Live Routes", items: routes, x: 790 },
  ];
  const NS = "http://www.w3.org/2000/svg";
  const nodeWidth = 210;
  const nodeHeight = 58;
  const gapY = 18;
  const topY = 42;
  const maxRows = Math.max(...columns.map((column) => Math.max(column.items.length, 1)));
  const height = topY + maxRows * (nodeHeight + gapY) + 30;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 1040 ${height}`);
  svg.setAttribute("class", "topology-graph");
  const positions = new Map();
  const artifactLookup = new Map();
  columns.forEach((column) => {
    const startY = topY + Math.max(0, (maxRows - column.items.length) * (nodeHeight + gapY) * 0.5);
    column.items.forEach((artifact, index) => {
      artifactLookup.set(deploymentGraphArtifactKey(artifact), artifact);
      positions.set(deploymentGraphArtifactKey(artifact), {
        x: column.x,
        y: startY + index * (nodeHeight + gapY),
      });
    });
    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(column.x));
    title.setAttribute("y", "22");
    title.setAttribute("class", "topology-title");
    title.textContent = column.title;
    svg.appendChild(title);
  });
  (data?.edges || []).forEach((edge) => {
    const from = positions.get(edge.from);
    const to = positions.get(edge.to);
    if (!from || !to) return;
    const edgeArtifact = buildDeploymentGraphEdgeArtifact(edge, artifactLookup);
    const path = document.createElementNS(NS, "path");
    const startX = from.x + nodeWidth;
    const startY = from.y + nodeHeight / 2;
    const endX = to.x;
    const endY = to.y + nodeHeight / 2;
    const controlX = (startX + endX) / 2;
    path.setAttribute("d", `M ${startX} ${startY} C ${controlX} ${startY}, ${controlX} ${endY}, ${endX} ${endY}`);
    path.setAttribute("class", "topology-edge");
    if (edgeArtifact && edgeArtifact.id === state.selectedDeploymentGraphEdgeKey) {
      path.classList.add("active");
    }
    path.setAttribute("tabindex", "0");
    const activateEdge = () => {
      if (!edgeArtifact) return;
      state.selectedDeploymentGraphEdgeKey = edgeArtifact.id;
      state.selectedDeploymentGraphKey = null;
      renderDeploymentGraphDetail(edgeArtifact);
    };
    path.addEventListener("mouseenter", activateEdge);
    path.addEventListener("focus", activateEdge);
    path.addEventListener("click", activateEdge);
    path.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activateEdge();
      await openDeploymentGraphContext(edgeArtifact);
    });
    svg.appendChild(path);
  });
  columns.flatMap((column) => column.items).forEach((artifact) => {
    const pos = positions.get(deploymentGraphArtifactKey(artifact));
    if (!pos) return;
    const group = document.createElementNS(NS, "g");
    group.setAttribute("class", `topology-node topology-node-${artifact.kind}`);
    if (deploymentGraphArtifactKey(artifact) === state.selectedDeploymentGraphKey) {
      group.classList.add("active");
    }
    group.setAttribute("tabindex", "0");
    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("x", String(pos.x));
    rect.setAttribute("y", String(pos.y));
    rect.setAttribute("rx", "12");
    rect.setAttribute("ry", "12");
    rect.setAttribute("width", String(nodeWidth));
    rect.setAttribute("height", String(nodeHeight));
    group.appendChild(rect);
    const title = document.createElementNS(NS, "text");
    title.setAttribute("x", String(pos.x + 14));
    title.setAttribute("y", String(pos.y + 24));
    title.setAttribute("class", "topology-node-title");
    title.textContent = artifact.title;
    group.appendChild(title);
    const subtitle = document.createElementNS(NS, "text");
    subtitle.setAttribute("x", String(pos.x + 14));
    subtitle.setAttribute("y", String(pos.y + 43));
    subtitle.setAttribute("class", "topology-node-subtitle");
    subtitle.textContent = artifact.subtitle;
    group.appendChild(subtitle);
    const activate = () => {
      state.selectedDeploymentGraphEdgeKey = null;
      state.selectedDeploymentGraphKey = deploymentGraphArtifactKey(artifact);
      renderDeploymentGraphDetail(artifact);
    };
    group.addEventListener("mouseenter", activate);
    group.addEventListener("focus", activate);
    group.addEventListener("click", activate);
    group.addEventListener("contextmenu", async (event) => {
      event.preventDefault();
      activate();
      await openDeploymentGraphContext(artifact);
    });
    svg.appendChild(group);
  });
  mountInteractiveSvgGraph(host, svg, { graphKey: "#deploy-graph", baseWidth: 1040, baseHeight: height });
  const selectedArtifact = columns.flatMap((column) => column.items)
    .find((artifact) => deploymentGraphArtifactKey(artifact) === state.selectedDeploymentGraphKey)
    || deployments[0]
    || packages[0]
    || runtimes[0]
    || routes[0]
    || null;
  const selectedEdge = state.selectedDeploymentGraphEdgeKey
    ? buildDeploymentGraphEdgeArtifact((data?.edges || []).find((edge) => deploymentGraphEdgeKey(edge) === state.selectedDeploymentGraphEdgeKey), artifactLookup)
    : null;
  renderDeploymentGraphDetail(selectedEdge || selectedArtifact);
}

function currentSelectedDeploymentGraphArtifact() {
  const data = buildDeploymentGraphData(filteredLocalDeploymentRows(state.localDeploymentRows || []), state.localRuntimeRows || []);
  const artifactLookup = new Map();
  [...(data.packages || []), ...(data.deployments || []), ...(data.runtimes || []), ...(data.routes || [])]
    .forEach((artifact) => artifactLookup.set(deploymentGraphArtifactKey(artifact), artifact));
  if (state.selectedDeploymentGraphEdgeKey) {
    const edge = (data.edges || []).find((item) => deploymentGraphEdgeKey(item) === state.selectedDeploymentGraphEdgeKey);
    const edgeArtifact = buildDeploymentGraphEdgeArtifact(edge, artifactLookup);
    if (edgeArtifact) return edgeArtifact;
  }
  const items = [...(data.packages || []), ...(data.deployments || []), ...(data.runtimes || []), ...(data.routes || [])];
  return items.find((artifact) => deploymentGraphArtifactKey(artifact) === state.selectedDeploymentGraphKey) || null;
}

function filteredLocalDeploymentRows(rows) {
  const query = String(state.deploymentInventoryQuery || "").trim().toLowerCase();
  const stage = String(state.deploymentInventoryStage || "all");
  return (rows || []).filter((row) => {
    const lifecycleStage = deploymentLifecycleStage(row);
    if (stage === "registered" && lifecycleStage !== "registered") return false;
    if (stage === "deployed" && lifecycleStage === "registered") return false;
    if (stage === "deployed_not_routed" && !(String(row?.deployment_status || "") === "deployed" && !row?.routed_live)) return false;
    if (stage === "routed_live" && lifecycleStage !== "routed_live") return false;
    if (!query) return true;
    const haystack = [
      row.model_alias,
      row.runtime_target,
      row.deployment_runtime,
      row.promotion_status,
      row.lifecycle_stage,
      row.endpoint_url,
      ...(row.domains || []),
      ...(row.task_types || []),
    ].map((value) => String(value || "").toLowerCase()).join(" ");
    return haystack.includes(query);
  });
}

async function ensureLocalDeploymentRowsLoaded() {
  if (state.localDeploymentRowsLoaded) {
    return state.localDeploymentRows;
  }
  const payload = await apiFetch("/deployment/models/local-inventory");
  state.localDeploymentRows = Array.isArray(payload) ? payload : [];
  state.localDeploymentRowsLoaded = true;
  return state.localDeploymentRows;
}

function renderLocalDeploymentDetail(row) {
  const heading = $("#deploy-detail-heading");
  if (heading) {
    heading.textContent = row?.model_alias ? `Deployment: ${row.model_alias}` : "Selected Deployment";
  }
  renderRecordView("#deploy-detail-summary", row, LOCAL_DEPLOYMENT_DETAIL_FIELDS, {
    rawLabel: "View raw deployment record",
    emptyState: {
      title: "No deployment selected.",
      body: "Choose a package from deployment inventory to inspect its registration, runtime, and live-routing state.",
    },
  });
}

function inspectLocalDeploymentRow(row, { prefillForm = true } = {}) {
  state.selectedLocalDeploymentAlias = row?.model_alias ? String(row.model_alias) : null;
  state.selectedDeploymentGraphKey = row?.model_alias ? `deployment:${String(row.model_alias)}` : null;
  setActiveRuntimeRow("#deployments-table", state.selectedLocalDeploymentAlias);
  renderLocalDeploymentDetail(row || null);
  if (row && prefillForm) {
    prepareDeployFormFromInventory(row);
  }
}

async function openLocalDeploymentWorkspaceContext(modelAlias) {
  if (!modelAlias) {
    showToast("No deployment selected.", "warn");
    return;
  }
  switchPanel("models");
  switchSubview("models", "deploy");
  await ensurePanelLoaded("models", true);
  const match = (state.localDeploymentRows || []).find((row) => String(row.model_alias || "") === String(modelAlias || ""));
  if (match) {
    inspectLocalDeploymentRow(match);
    showToast(`Opened deployment context for ${modelAlias}.`, "ok");
    return;
  }
  showToast(`Deployment ${modelAlias} is not present in local deployment inventory.`, "warn");
}

function renderOllamaReconcile(selector, payload) {
  if (!payload) {
    renderRecordView(selector, null, OLLAMA_RECONCILE_FIELDS, {
      raw: false,
      emptyState: {
        title: "No runtime reconciliation yet.",
        body: "Run reconcile on the selected Ollama runtime to compare installed models with registered and deployed packages.",
      },
    });
    return;
  }
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  renderRecordView(selector, payload, OLLAMA_RECONCILE_FIELDS, {
    rawLabel: "View raw reconcile payload",
  });
  host.appendChild(
    makeTable(["Package", "Base Model", "Lifecycle", "Base Present", "Alias Present", "Recommended"], payload.packages || [], (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.model_alias)}</strong></td>
        <td>${row.base_model ? renderIdChip(row.base_model, { truncate: false }) : '<span class="empty-value">-</span>'}</td>
        <td>${statusBadge(row.lifecycle_stage || "registered")}</td>
        <td>${boolBadge(Boolean(row.base_model_present))}</td>
        <td>${boolBadge(Boolean(row.alias_present))}</td>
        <td>${statusBadge(row.recommended_action || "ready")}</td>
      `;
      return tr;
    }, "No Ollama-managed packages were found to reconcile."),
  );
}

async function pullOllamaBaseModel(modelName, outputSelector = "#deploy-output") {
  const result = await apiFetch("/deployment/runtimes/ollama/pull", {
    method: "POST",
    body: JSON.stringify({ model: modelName }),
  });
  renderOutput(outputSelector, result);
  showToast(`Ollama pull requested for ${modelName}.`, "ok");
  return result;
}

async function runSelectedRuntimeReconcile() {
  if (state.selectedLocalRuntime !== "ollama") {
    showToast("Runtime reconcile is currently available only for Ollama.", "warn");
    return null;
  }
  const result = await apiFetch("/deployment/runtimes/ollama/reconcile");
  renderOllamaReconcile("#local-runtime-ops-output", result);
  showToast("Ollama runtime reconciled.", "ok");
  return result;
}

function renderLocalRuntimeLifecycle(row) {
  const heading = $("#local-runtime-detail-heading");
  if (heading) {
    heading.textContent = row?.runtime ? `${humanizeLabel(row.runtime)} Runtime` : "Selected Runtime";
  }
  renderRecordView("#local-runtime-detail-summary", row, LOCAL_RUNTIME_DETAIL_FIELDS, {
    rawLabel: "View raw runtime record",
    emptyState: {
      title: "No runtime selected.",
      body: "Choose a runtime row to inspect its package lifecycle and current routing footprint.",
    },
  });
  const host = $("#local-runtime-lifecycle-table");
  if (!host) return;
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Package", "Promotion", "Lifecycle", "Deployment", "Routing", "Actions"], row ? deploymentRowsForRuntime(row.runtime) : [], (item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(item.model_alias)}</strong></td>
        <td>${statusBadge(item.promotion_status || "-")}</td>
        <td>${statusBadge(item.lifecycle_stage || "registered")}</td>
        <td>${statusBadge(item.deployment_status || "not_deployed")}${item.deployment_manifest_path ? `<br/><span>${escapeHtml(item.deployment_runtime || item.runtime_target || "-")}</span>` : '<br/><span class="empty-value">No deployment manifest</span>'}</td>
        <td>${item.routed_live ? `${statusBadge(item.active_route_mode || "production")}<br/><span>${escapeHtml(item.active_route_runtime || item.runtime_target || "-")}</span>` : '<span class="empty-value">Not routed live</span>'}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Open Deploy", () => {
        void openLocalDeploymentWorkspaceContext(item.model_alias);
      }, { accent: true }));
      if (row?.runtime === "ollama" && item.base_model) {
        actions.appendChild(createActionButton("Pull Base Model", async () => {
          await pullOllamaBaseModel(item.base_model, "#local-runtime-ops-output");
          await Promise.all([refreshLocalRuntimeStatus(), refreshDeployments()]);
        }));
      }
      if (item.routed_live) {
        actions.appendChild(createActionButton("Open Routing", async () => {
          await openLocalDeploymentRoutingContext(item.model_alias);
        }));
      }
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, row
      ? `No packages are currently associated with the ${humanizeLabel(row.runtime)} runtime.`
      : "Choose a runtime to inspect the packages assigned to it."),
  );
  if (!row || row.runtime !== "ollama") {
    renderOllamaReconcile("#local-runtime-ops-output", null);
  }
}

async function selectLocalRuntime(runtimeName) {
  if (!runtimeName) {
    state.selectedLocalRuntime = null;
    renderLocalRuntimeLifecycle(null);
    return null;
  }
  await ensureLocalDeploymentRowsLoaded();
  const row = (state.localRuntimeRows || []).find((item) => String(item.runtime || "") === String(runtimeName || ""));
  state.selectedLocalRuntime = row ? String(row.runtime || "") : null;
  setActiveRuntimeRow("#local-runtime-table", state.selectedLocalRuntime);
  renderLocalRuntimeLifecycle(row || null);
  return row || null;
}

async function refreshLocalRuntimeStatus() {
  setTableLoading("#local-runtime-table", {
    title: "Loading runtime inventory…",
    body: "Checking configured local runtimes and package counts.",
  });
  const payload = await apiFetch("/admin/api/models/local-runtimes");
  state.localRuntimeRows = Array.isArray(payload) ? payload : [];
  const host = $("#local-runtime-table");
  if (host) {
    host.innerHTML = "";
    host.appendChild(
      makeTable(["Runtime", "Health", "Base URL", "Registered", "Deployed", "Routed Live", "Visible Models", "Actions"], state.localRuntimeRows, (row) => {
        const tr = document.createElement("tr");
        tr.dataset.recordId = String(row.runtime || "");
        if (String(row.runtime || "") === state.selectedLocalRuntime) {
          tr.classList.add("active-row");
        }
        tr.innerHTML = `
          <td><strong>${escapeHtml(row.runtime)}</strong></td>
          <td>${row.reachable ? '<span class="badge badge-ok">reachable</span>' : row.configured ? '<span class="badge badge-warn">unreachable</span>' : '<span class="badge badge-muted">not configured</span>'}</td>
          <td>${renderIdChip(row.base_url || "-", { truncate: false })}</td>
          <td><strong>${escapeHtml(formattedValue(row.package_alias_count || 0))}</strong>${(row.package_aliases || []).length ? `<br/><span>${escapeHtml((row.package_aliases || []).slice(0, 2).join(", "))}${row.package_alias_count > 2 ? "..." : ""}</span>` : '<br/><span class="empty-value">No registered packages</span>'}</td>
          <td><strong>${escapeHtml(formattedValue(row.deployed_alias_count || 0))}</strong>${(row.deployed_aliases || []).length ? `<br/><span>${escapeHtml((row.deployed_aliases || []).slice(0, 2).join(", "))}${row.deployed_alias_count > 2 ? "..." : ""}</span>` : '<br/><span class="empty-value">No deployed packages</span>'}</td>
          <td><strong>${escapeHtml(formattedValue(row.active_route_count || 0))}</strong>${(row.active_route_aliases || []).length ? `<br/><span>${escapeHtml((row.active_route_aliases || []).slice(0, 2).join(", "))}${row.active_route_count > 2 ? "..." : ""}</span>` : '<br/><span class="empty-value">No live routes</span>'}</td>
          <td>${escapeHtml(formattedValue(row.models_visible ?? "-"))}<br/><span>${escapeHtml(row.detail || "")}</span></td>
          <td></td>
        `;
        tr.addEventListener("click", (event) => {
          if (event.target.closest("button")) return;
          void selectLocalRuntime(row.runtime);
        });
        const actions = document.createElement("div");
        actions.className = "table-actions";
        actions.appendChild(createActionButton("Inspect", () => {
          void selectLocalRuntime(row.runtime);
        }, { accent: true }));
        actions.appendChild(createActionButton("Open Deployments", async () => {
          const firstAlias = String((row.package_aliases || [])[0] || "");
          if (firstAlias) {
            await openLocalDeploymentWorkspaceContext(firstAlias);
            return;
          }
          switchPanel("models");
          switchSubview("models", "deploy");
          await ensurePanelLoaded("models", true);
          showToast(`Opened deployment workspace for ${row.runtime}.`, "ok");
        }));
        if ((row.active_route_count || 0) > 0 && (row.active_route_aliases || []).length) {
          actions.appendChild(createActionButton("Open Routing", async () => {
            await openLocalDeploymentRoutingContext(String(row.active_route_aliases[0] || ""));
          }));
        }
        actions.appendChild(createActionButton("Open Deploy", () => {
          switchPanel("models");
          switchSubview("models", "deploy");
        }));
        tr.lastElementChild.appendChild(actions);
        return tr;
      }, "Local runtime status will appear here once runtime configuration is available.", { pageKey: "#local-runtime-table", pageSize: 12, itemLabel: "runtimes" }),
    );
  }
  const byRuntime = Object.fromEntries(state.localRuntimeRows.map((row) => [String(row.runtime), row]));
  setFieldValue("#local-runtime-config-form", "ollama_base_url", byRuntime.ollama?.base_url || "");
  setFieldValue("#local-runtime-config-form", "vllm_base_url", byRuntime.vllm?.base_url || "");
  setFieldValue("#local-runtime-config-form", "llama_cpp_base_url", byRuntime.llama_cpp?.base_url || "");
  setFieldValue("#local-runtime-config-form", "mlx_base_url", byRuntime.mlx?.base_url || "");
  const selectedRuntime = state.selectedLocalRuntime && byRuntime[state.selectedLocalRuntime]
    ? state.selectedLocalRuntime
    : String(state.localRuntimeRows[0]?.runtime || "");
  if (selectedRuntime) {
    await selectLocalRuntime(selectedRuntime);
  } else {
    state.selectedLocalRuntime = null;
    renderLocalRuntimeLifecycle(null);
  }
  if (state.localDeploymentRowsLoaded) {
    renderDeploymentGraph(buildDeploymentGraphData(filteredLocalDeploymentRows(state.localDeploymentRows), state.localRuntimeRows));
  }
  return state.localRuntimeRows;
}

async function refreshDeployments() {
  setTableLoading("#deployments-table", {
    title: "Loading deployment inventory…",
    body: "Fetching package, runtime, and live routing lifecycle state.",
  });
  const graphHost = $("#deploy-graph");
  if (graphHost) {
    graphHost.innerHTML = "";
    graphHost.appendChild(buildLoadingState({
      title: "Loading deployment graph…",
      body: "Fetching package, runtime, and live routing lifecycle state.",
    }));
  }
  const payload = await apiFetch("/deployment/models/local-inventory");
  state.localDeploymentRows = Array.isArray(payload) ? payload : [];
  state.localDeploymentRowsLoaded = true;
  const filteredRows = filteredLocalDeploymentRows(state.localDeploymentRows);
  renderDeploymentGraph(buildDeploymentGraphData(filteredRows, state.localRuntimeRows || []));
  const host = $("#deployments-table");
  if (host) {
    host.innerHTML = "";
    host.appendChild(
      makeTable(["Model Alias", "Package", "Deployment", "Routing", "Runtime", "Endpoint", "Actions"], filteredRows, (row) => {
        const tr = document.createElement("tr");
        tr.dataset.recordId = String(row.model_alias || "");
        if (String(row.model_alias || "") === state.selectedLocalDeploymentAlias) {
          tr.classList.add("active-row");
        }
        tr.innerHTML = `
          <td><strong>${escapeHtml(row.model_alias)}</strong><br/>${statusBadge(row.lifecycle_stage || "registered")}</td>
          <td>${statusBadge(row.package_state || "registered")}<br/><span>${escapeHtml(humanizeLabel(row.promotion_status || "-"))}</span></td>
          <td>${statusBadge(row.deployment_status || "not_deployed")}${row.deployment_manifest_path ? `<br/><span>${escapeHtml(row.deployment_runtime || row.runtime_target || "-")}</span>` : '<br/><span class="empty-value">No deployment manifest</span>'}</td>
          <td>${row.routed_live ? `${statusBadge(row.routing_state || "routed_live")}<br/><span>${escapeHtml(humanizeLabel(row.active_route_mode || "active"))}</span>` : '<span class="empty-value">Not routed live</span>'}</td>
          <td>${statusBadge(row.deployment_runtime || row.runtime_target || "-")}</td>
          <td>${row.endpoint_url ? renderIdChip(row.endpoint_url, { truncate: false }) : '<span class="empty-value">-</span>'}</td>
          <td></td>
        `;
        tr.addEventListener("click", (event) => {
          if (event.target.closest("button")) return;
          inspectLocalDeploymentRow(row, { prefillForm: false });
        });
        const actions = document.createElement("div");
        actions.className = "table-actions";
        actions.appendChild(createActionButton("Prepare Deploy", () => {
          inspectLocalDeploymentRow(row);
          logConsole("deployment form prepared from inventory", { model_alias: row.model_alias });
        }, { accent: true }));
        if (row.routed_live) {
          actions.appendChild(createActionButton("Prepare Rollback", () => {
            inspectLocalDeploymentRow(row);
            logConsole("rollback prepared from inventory", { model_alias: row.model_alias });
          }));
        }
        if ((row.deployment_runtime || row.runtime_target) === "ollama" && row.base_model) {
          actions.appendChild(createActionButton("Pull Base Model", async () => {
            await pullOllamaBaseModel(row.base_model);
            await Promise.all([refreshLocalRuntimeStatus(), refreshDeployments()]);
          }));
        }
        actions.appendChild(createActionButton("Open Runtime", async () => {
          await openRuntimeHostingContext(row.deployment_runtime || row.runtime_target || "");
        }));
        if (row.routed_live) {
          actions.appendChild(createActionButton("Open Routing", async () => {
            await openLocalDeploymentRoutingContext(row.model_alias);
          }));
        }
        actions.appendChild(createActionButton("Inspect", () => inspectLocalDeploymentRow(row, { prefillForm: false })));
        tr.lastElementChild.appendChild(actions);
        return tr;
      }, "No deployments match the current lifecycle filter.", { pageKey: "#deployments-table", pageSize: 15, itemLabel: "deployments" }),
    );
  }
  const selectedDeployment = (state.localDeploymentRows || []).find((row) => String(row.model_alias || "") === state.selectedLocalDeploymentAlias);
  if (selectedDeployment) {
    inspectLocalDeploymentRow(selectedDeployment, { prefillForm: false });
  } else if (filteredRows?.[0]) {
    inspectLocalDeploymentRow(filteredRows[0], { prefillForm: false });
  } else {
    state.selectedLocalDeploymentAlias = null;
    renderLocalDeploymentDetail(null);
  }
  if (state.selectedLocalRuntime) {
    renderLocalRuntimeLifecycle((state.localRuntimeRows || []).find((row) => String(row.runtime || "") === state.selectedLocalRuntime) || null);
  }
  return state.localDeploymentRows;
}

async function refreshPolicies() {
  setTableLoadingMany(["#policies-table", "#routing-nodes-table", "#routing-pools-table"], {
    title: "Loading routing topology…",
    body: "Fetching routing entries plus derived node and pool inventory.",
  });
  const graphHost = $("#routing-graph");
  if (graphHost) {
    graphHost.innerHTML = "";
    graphHost.appendChild(buildLoadingState({
      title: "Loading routing path graph…",
      body: "Fetching listener scope, routing entries, and pooled capacity.",
    }));
  }
  const [payload, topology, config] = await Promise.all([
    apiFetch("/deployment/routing-policies"),
    apiFetch("/admin/api/topology/routing-inventory"),
    apiFetch("/admin/api/config"),
  ]);
  state.configPayload = config;
  const rows = flattenRoutingPolicyRows(payload);
  state.policyRows = rows;
  state.routingTopologyInventory = attachRoutingEntriesToTopology(rows, topology || { nodes: [], pools: [], summary: {} });
  const filteredRows = filteredPolicyRows(rows);
  const nodeInventory = Array.isArray(state.routingTopologyInventory?.nodes) ? state.routingTopologyInventory.nodes : buildRoutingNodeInventory(rows);
  const poolInventory = Array.isArray(state.routingTopologyInventory?.pools) ? state.routingTopologyInventory.pools : buildRoutingPoolInventory(rows);
  renderRoutingScopeBanner();
  renderRoutingTopologySummary(state.routingTopologyInventory);
  renderRoutingGraph(buildRoutingGraphData({
    rows: filteredRows,
    topology: state.routingTopologyInventory,
    config,
  }));
  const host = $("#policies-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Version", "Type", "Domains", "Tags", "Regions", "Mode", "Provider", "Model", "Actions"], filteredRows, (row) => {
      const tr = document.createElement("tr");
      const recordKey = buildPolicyRowKey(row);
      tr.dataset.recordId = recordKey;
      if (recordKey === state.selectedPolicyRowKey) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.policy_version)}</strong></td>
        <td>${statusBadge(row.entry_type)}</td>
        <td>${escapeHtml(row.domains)}</td>
        <td>${escapeHtml(row.tags)}</td>
        <td>${escapeHtml(row.regions)}</td>
        <td>${escapeHtml(row.mode)}</td>
        <td>${escapeHtml(row.provider)}</td>
        <td>${escapeHtml(row.model)}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectPolicyRow(row);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => inspectPolicyRow(row), { accent: true }));
      if (row.detail?.entry?.entry_type === "frontier") {
        actions.appendChild(createActionButton("Edit", () => inspectPolicyRow(row)));
        if (row.entry_id) {
          actions.appendChild(createActionButton("Delete", async () => {
            const result = await apiFetch(`/deployment/routing-policies/entries/${row.entry_id}`, { method: "DELETE" });
            renderOutput("#frontier-policy-output", result);
            showToast("Frontier policy entry deleted.", "warn");
            await refreshPolicies();
          }, { destructive: true, confirmMessage: `Delete frontier policy entry ${row.entry_id}?` }));
        }
      }
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, state.routingPolicyScopedOnly && currentSelectedFoundationProvider()
      ? "No routing rows match the currently selected vendor/model scope."
      : "Routing policies will appear here as versions are published.", { pageKey: "#policies-table", pageSize: 15, itemLabel: "routing entries" }),
  );
  const nodesHost = $("#routing-nodes-table");
  if (nodesHost) {
    nodesHost.innerHTML = "";
    nodesHost.appendChild(
      makeTable(["Node", "Role", "Health", "Latency", "Activity", "Pools", "Entries", "Actions"], nodeInventory, (row) => {
        const tr = document.createElement("tr");
        const recordKey = buildRoutingNodeKey(row);
        tr.dataset.recordId = recordKey;
        if (recordKey === state.selectedRoutingNodeKey) {
          tr.classList.add("active-row");
        }
        tr.innerHTML = `
          <td><strong>${escapeHtml(row.node_id)}</strong></td>
          <td>${row.node_role ? statusBadge(row.node_role) : '<span class="empty-value">-</span>'}</td>
          <td>${row.cooled_down ? '<span class="badge badge-warn">Cooling</span>' : '<span class="badge badge-ok">Ready</span>'}${row.capacity_class ? `<br/><span>${escapeHtml(row.capacity_class)}</span>` : ""}</td>
          <td>${row.avg_latency_ms != null ? `<strong>${escapeHtml(formattedValue(row.avg_latency_ms))} ms</strong>${row.p95_latency_ms != null ? `<br/><span>P95 ${escapeHtml(formattedValue(row.p95_latency_ms))} ms</span>` : ""}` : '<span class="empty-value">No runtime data</span>'}</td>
          <td><strong>${escapeHtml(formattedValue(row.recent_request_count || 0))}</strong>${row.last_seen_at ? `<br/>${timeLabel(row.last_seen_at)}` : ""}</td>
          <td>${escapeHtml(formattedValue(row.pool_count))}</td>
          <td>${escapeHtml(formattedValue(row.entry_count))}</td>
          <td></td>
        `;
        tr.addEventListener("click", (event) => {
          if (event.target.closest("button")) return;
          inspectRoutingNode(row);
        });
        const actions = document.createElement("div");
        actions.className = "table-actions";
        actions.appendChild(createActionButton("Inspect", () => inspectRoutingNode(row), { accent: true }));
        actions.appendChild(createActionButton("Open Traffic", async () => {
          await openRequestHistoryContext({ selected_node_id: row.node_id });
        }));
        tr.lastElementChild.appendChild(actions);
        return tr;
      }, "Node inventory will appear here once routing entries declare node metadata.", { pageKey: "#routing-nodes-table", pageSize: 12, itemLabel: "nodes" }),
    );
  }
  const poolsHost = $("#routing-pools-table");
  if (poolsHost) {
    poolsHost.innerHTML = "";
    poolsHost.appendChild(
      makeTable(["Pool", "Balancing", "Health", "Latency", "Activity", "Nodes", "Weight", "Actions"], poolInventory, (row) => {
        const tr = document.createElement("tr");
        const recordKey = buildRoutingPoolKey(row);
        tr.dataset.recordId = recordKey;
        if (recordKey === state.selectedRoutingPoolKey) {
          tr.classList.add("active-row");
        }
        tr.innerHTML = `
          <td><strong>${escapeHtml(row.pool_id)}</strong></td>
          <td>${row.balancing_strategy ? statusBadge(row.balancing_strategy) : '<span class="empty-value">-</span>'}</td>
          <td>${row.cooled_down ? '<span class="badge badge-warn">Cooling</span>' : '<span class="badge badge-ok">Ready</span>'}${row.affinity_key ? `<br/><span>${escapeHtml(row.affinity_key)}</span>` : ""}</td>
          <td>${row.avg_latency_ms != null ? `<strong>${escapeHtml(formattedValue(row.avg_latency_ms))} ms</strong>${row.p95_latency_ms != null ? `<br/><span>P95 ${escapeHtml(formattedValue(row.p95_latency_ms))} ms</span>` : ""}` : '<span class="empty-value">No runtime data</span>'}</td>
          <td><strong>${escapeHtml(formattedValue(row.recent_request_count || 0))}</strong>${row.last_seen_at ? `<br/>${timeLabel(row.last_seen_at)}` : ""}</td>
          <td>${escapeHtml(formattedValue(row.node_count))}</td>
          <td>${escapeHtml(formattedValue(row.total_weight))}</td>
          <td></td>
        `;
        tr.addEventListener("click", (event) => {
          if (event.target.closest("button")) return;
          inspectRoutingPool(row);
        });
        const actions = document.createElement("div");
        actions.className = "table-actions";
        actions.appendChild(createActionButton("Inspect", () => inspectRoutingPool(row), { accent: true }));
        actions.appendChild(createActionButton("Open Traffic", async () => {
          await openRequestHistoryContext({ selected_pool_id: row.pool_id });
        }));
        tr.lastElementChild.appendChild(actions);
        return tr;
      }, "Pool inventory will appear here once multiple equivalent endpoints are grouped under pool IDs.", { pageKey: "#routing-pools-table", pageSize: 12, itemLabel: "pools" }),
    );
  }
  const selected = filteredRows.find((row) => buildPolicyRowKey(row) === state.selectedPolicyRowKey);
  const selectedNode = nodeInventory.find((row) => buildRoutingNodeKey(row) === state.selectedRoutingNodeKey);
  const selectedPool = poolInventory.find((row) => buildRoutingPoolKey(row) === state.selectedRoutingPoolKey);
  if (state.activeModelRoutingCollection === "nodes") {
    if (selectedNode) {
      inspectRoutingNode(selectedNode);
    } else if (nodeInventory.length) {
      inspectRoutingNode(nodeInventory[0]);
    } else {
      state.selectedRoutingNodeKey = null;
      setActiveRuntimeRow("#routing-nodes-table", "");
      renderRoutingNodeDetail({});
      renderRoutingRelatedEntries([], "No node inventory selected.");
    }
  } else if (state.activeModelRoutingCollection === "pools") {
    if (selectedPool) {
      inspectRoutingPool(selectedPool);
    } else if (poolInventory.length) {
      inspectRoutingPool(poolInventory[0]);
    } else {
      state.selectedRoutingPoolKey = null;
      setActiveRuntimeRow("#routing-pools-table", "");
      renderRoutingPoolDetail({});
      renderRoutingRelatedEntries([], "No pool inventory selected.");
    }
  } else if (selected) {
    inspectPolicyRow(selected);
  } else if (!filteredRows.length) {
    state.selectedPolicyRowKey = null;
    setActiveRuntimeRow("#policies-table", "");
    renderModelDetail({}, "#model-routing-detail-summary-table");
    renderRoutingRelatedEntries([], "No routing entry selected.");
  } else {
    inspectPolicyRow(filteredRows[0]);
  }
  return payload;
}

async function refreshCandidates() {
  setTableLoading("#candidates-table", {
    title: "Loading training candidates…",
    body: "Fetching proxy-generated learning candidates and their interaction traces.",
  });
  const filters = rememberTableContext("#candidates-table", currentTableContext("#candidates-table", "#candidates-filter-form"));
  const page = paginationParams("#candidates-table", 15);
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  params.set("paginated", "true");
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  const payload = await apiFetch(`/proxy/training-candidates?${params.toString()}`);
  const rows = payload.items || [];
  state.dataCandidates = rows;
  const host = $("#candidates-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Candidate", "Domain", "Protocols", "Outcome", "Score", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.id}</strong><br/><span>${row.task_type}</span>${row.prompt_template_name ? `<br/><span>Prompt ${escapeHtml(row.prompt_template_name)}${row.prompt_template_version ? ` · v${escapeHtml(formattedValue(row.prompt_template_version))}` : ""}</span><br/>${renderPromptSelectionModeBadge(row.prompt_template_selection_mode, row.prompt_template_rollout_percentage)}` : ""}</td>
        <td>${row.domain}</td>
        <td>${escapeHtml((row.interaction_protocols || []).join(", ") || "-")}<br/><span>${escapeHtml((row.interaction_operations || []).join(", ") || "No traced operations")}</span></td>
        <td>${statusBadge(row.interaction_outcome || row.approval_status)}</td>
        <td>${escapeHtml(formattedValue(row.quality_score))}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Approve", async () => {
          const result = await apiFetch(`/proxy/training-candidates/${row.id}/approve`, { method: "POST" });
          logConsole("candidate approve", result);
          showToast(`Candidate ${row.id} approved.`, "ok");
          await refreshCandidates();
        }, { accent: true }),
      );
      actions.appendChild(
        createActionButton("Reject", async () => {
          const result = await apiFetch(`/proxy/training-candidates/${row.id}/reject`, { method: "POST" });
          logConsole("candidate reject", result);
          showToast(`Candidate ${row.id} rejected.`, "warn");
          await refreshCandidates();
        }, { destructive: true, confirmMessage: `Reject training candidate ${row.id}?` }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Traffic will begin generating candidates automatically.", {
      pageKey: "#candidates-table",
      itemLabel: "candidates",
      serverPagination: serverPaginationForPayload("#candidates-table", payload, page.limit, () => refreshCandidates()),
    }),
  );
  refreshTrainingLifecycleView();
  return rows;
}

const EXPORT_RECORD_FIELDS = [
  { key: "dataset_export_id", label: "Export ID", render: (value) => renderIdChip(value) },
  { key: "name", label: "Export Name", hideEmpty: true, render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "domain", label: "Domain", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "record_count", label: "Records", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "schema_version", label: "Schema Version" },
  { key: "interaction_filters", label: "Trace Filters", render: (value) => renderKeyValueChipList(value, { emptyLabel: "No trace filters" }) },
  { key: "prompt_rollout_modes", label: "Prompt Rollout Modes", render: (value, record) => {
    const counts = record?.prompt_rollout_mode_counts || {};
    const entries = Object.entries(counts);
    if (!entries.length) return '<span class="empty-value">No rollout summary available</span>';
    return entries.map(([mode, count]) => `${renderPromptSelectionModeBadge(mode)} <span class="num">${escapeHtml(formattedValue(count))}</span>`).join("<br/>");
  } },
  { key: "manifest_path", label: "Manifest Path", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "data_path", label: "Data Path", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "interaction_protocols", label: "Protocols", render: (value) => renderList(value, { emptyLabel: "No protocol summary available" }) },
  { key: "id", label: "Record ID", render: (value) => renderIdChip(value) },
  { key: "created_at", label: "Created", render: (value) => timeLabel(value) },
];

function renderExportDetail(detail) {
  renderRecordView("#export-detail", detail, EXPORT_RECORD_FIELDS, {
    rawLabel: "View raw export record",
    emptyState: {
      title: "No export selected.",
      body: "Choose an export from the table above and select “Inspect” to see its manifest path, data path, and record count here.",
    },
  });
  renderSimpleTable(
    "#export-interaction-protocols-table",
    "Interaction Protocol Summary",
    ["Protocol", "Trace Count"],
    Object.entries(detail?.interaction_protocol_counts || {}).map(([protocol, count]) => ({ protocol, count })),
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="badge badge-info">${escapeHtml(String(row.protocol || "unknown").toUpperCase())}</span></td>
        <td><span class="num">${escapeHtml(formattedValue(row.count))}</span></td>
      `;
      return tr;
    },
    "This export does not yet include any summarized interaction protocols.",
  );
}

function inspectExport(row) {
  state.selectedExportId = row?.dataset_export_id || null;
  setActiveRuntimeRow("#exports-table", state.selectedExportId || "");
  renderExportDetail(row);
}

async function refreshExports() {
  setTableLoading("#exports-table", {
    title: "Loading exports…",
    body: "Fetching dataset export inventory.",
  });
  const filters = rememberTableContext("#exports-table", currentTableContext("#exports-table", "#exports-filter-form"));
  const page = paginationParams("#exports-table", 15);
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  params.set("paginated", "true");
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  const payload = await apiFetch(`/admin/api/exports?${params.toString()}`);
  const rows = payload.items || [];
  state.dataExports = rows;
  const host = $("#exports-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Export", "Domain", "Records", "Created", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.dataset_export_id;
      if (row.dataset_export_id === state.selectedExportId) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${row.dataset_export_id}</strong><br/><span>${row.id}</span>${(row.interaction_filters || {}).prompt_template_name ? `<br/><span>Prompt ${escapeHtml(row.interaction_filters.prompt_template_name)}${(row.interaction_filters || {}).prompt_template_version ? ` · v${escapeHtml(formattedValue(row.interaction_filters.prompt_template_version))}` : ""}</span>${(row.interaction_filters || {}).prompt_template_selection_mode ? `<br/>${renderPromptSelectionModeBadge(row.interaction_filters.prompt_template_selection_mode)}` : ""}` : ""}</td>
        <td>${row.domain || "-"}</td>
        <td>${row.record_count}${Object.keys(row.prompt_rollout_mode_counts || {}).length ? `<br/><span>${escapeHtml(Object.entries(row.prompt_rollout_mode_counts || {}).map(([mode, count]) => `${humanizeLabel(mode)} ${formattedValue(count)}`).join(", "))}</span>` : ""}</td>
        <td>${timeLabel(row.created_at)}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectExport(row);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => inspectExport(row), { accent: true }));
      actions.appendChild(
        createActionButton("Use for Import", () => {
          inspectExport(row);
          setFieldValue("#dataset-import-form", "dataset_export_id", row.dataset_export_id);
          setFieldValue("#dataset-import-form", "manifest_path", row.manifest_path);
          setFieldValue("#dataset-import-form", "data_path", row.data_path);
          logConsole("dataset import form filled", row);
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Create a dataset export to move approved candidates into the learner pipeline.", {
      pageKey: "#exports-table",
      itemLabel: "exports",
      serverPagination: serverPaginationForPayload("#exports-table", payload, page.limit, () => refreshExports()),
    }),
  );
  const exportCount = Number(payload.total || rows.length || 0);
  clearHost("#export-detail");
  if (!exportCount) {
    $("#export-detail")?.appendChild(buildEmptyState({
      icon: "✎",
      title: "No exports created yet.",
      body: "Bundle approved, export-eligible candidates into a dataset using the form below — each export will appear here for inspection and reuse as an import source.",
    }));
    clearHost("#export-interaction-protocols-table");
  } else {
    $("#export-detail")?.appendChild(buildEmptyState({
      icon: "→",
      title: "Select an export to inspect.",
      body: `${exportCount} export${exportCount === 1 ? "" : "s"} available — choose “Inspect” to see its manifest and data paths, or “Use for Import” to copy its IDs into the import form below.`,
    }));
    renderSimpleTable(
      "#export-interaction-protocols-table",
      "Interaction Protocol Summary",
      [],
      () => document.createElement("tr"),
      "Select an export to inspect its trace protocol mix.",
    );
  }
  renderOutput("#exports-output", payload);
  refreshTrainingLifecycleView();
  return rows;
}

const DATASET_IMPORT_RECORD_FIELDS = [
  { key: "id", label: "Import ID", render: (value) => renderIdChip(value) },
  { key: "dataset_export_id", label: "Source Export", render: (value) => renderIdChip(value) },
  { key: "status", label: "Status", render: (value) => statusBadge(value) },
  { key: "record_count", label: "Records Imported", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  {
    key: "quarantined_count",
    label: "Quarantined",
    render: (value) => (value ? `<span class="badge badge-warn">${escapeHtml(formattedValue(value))} duplicate${Number(value) === 1 ? "" : "s"} dropped</span>` : '<span class="empty-value">None — every record was unique</span>'),
  },
  { key: "manifest_path", label: "Manifest Path", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "data_path", label: "Data Path", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "created_at", label: "Imported", render: (value) => timeLabel(value) },
];

function renderDatasetImportDetail(detail) {
  renderRecordView("#dataset-detail", detail, DATASET_IMPORT_RECORD_FIELDS, {
    rawLabel: "View raw import record",
    emptyState: {
      title: "Nothing selected yet.",
      body: "Choose an import or version from the tables above and select “Inspect” to see its full record here.",
    },
  });
}

function inspectDatasetRecord(row, type = "import") {
  const recordId = row?.id || null;
  state.selectedDatasetRecordId = recordId;
  setActiveRuntimeRow("#dataset-imports-table", type === "import" ? recordId || "" : "");
  setActiveRuntimeRow("#dataset-versions-table", type === "version" ? recordId || "" : "");
  if (type === "version") {
    renderDatasetVersionDetail(row);
  } else {
    renderDatasetImportDetail(row);
  }
}

async function refreshDatasetImports() {
  setTableLoading("#dataset-imports-table", {
    title: "Loading imports…",
    body: "Fetching dataset import history.",
  });
  const filters = rememberTableContext("#dataset-imports-table", currentTableContext("#dataset-imports-table", "#dataset-imports-filter-form"));
  const page = paginationParams("#dataset-imports-table", 15);
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  params.set("paginated", "true");
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  const payload = await apiFetch(`/admin/api/datasets/imports?${params.toString()}`);
  const rows = payload.items || [];
  state.dataImports = rows;
  const host = $("#dataset-imports-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Import", "Export", "Status", "Records", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.id;
      if (row.id === state.selectedDatasetRecordId) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${row.id}</strong></td>
        <td>${row.dataset_export_id}</td>
        <td>${statusBadge(row.status)}</td>
        <td>${row.record_count}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectDatasetRecord(row, "import");
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => inspectDatasetRecord(row, "import"), { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Imported datasets will appear here after processing completes.", {
      pageKey: "#dataset-imports-table",
      itemLabel: "imports",
      serverPagination: serverPaginationForPayload("#dataset-imports-table", payload, page.limit, () => refreshDatasetImports()),
    }),
  );
  refreshTrainingLifecycleView();
  return rows;
}

const DATASET_VERSION_RECORD_FIELDS = [
  { key: "version_name", label: "Version", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "domain", label: "Domain" },
  { key: "record_count", label: "Records", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "source_import_id", label: "Source Import", render: (value) => renderIdChip(value) },
  { key: "train_path", label: "Train Split", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "validation_path", label: "Validation Split", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "test_path", label: "Test Split", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "id", label: "Record ID", render: (value) => renderIdChip(value) },
  { key: "created_at", label: "Created", render: (value) => timeLabel(value) },
];

function renderDatasetVersionDetail(detail) {
  renderRecordView("#dataset-detail", detail, DATASET_VERSION_RECORD_FIELDS, {
    rawLabel: "View raw dataset version record",
    emptyState: {
      title: "Nothing selected yet.",
      body: "Choose an import or version from the tables above and select “Inspect” to see its full record here.",
    },
  });
}

async function refreshDatasetVersions() {
  setTableLoading("#dataset-versions-table", {
    title: "Loading dataset versions…",
    body: "Fetching normalized dataset versions and split metadata.",
  });
  const filters = rememberTableContext("#dataset-versions-table", currentTableContext("#dataset-versions-table", "#dataset-versions-filter-form"));
  const page = paginationParams("#dataset-versions-table", 15);
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  params.set("paginated", "true");
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  const payload = await apiFetch(`/admin/api/datasets/versions?${params.toString()}`);
  const rows = payload.items || [];
  state.dataVersions = rows;
  const host = $("#dataset-versions-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Version", "Domain", "Records", "Source", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.id;
      if (row.id === state.selectedDatasetRecordId) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${row.version_name}</strong><br/><span>${row.id}</span></td>
        <td>${row.domain}</td>
        <td>${row.record_count}</td>
        <td>${row.source_import_id || "-"}</td>
        <td></td>
      `;
      tr.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        inspectDatasetRecord(row, "version");
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => inspectDatasetRecord(row, "version"), { accent: true }));
      actions.appendChild(
        createActionButton("Train", () => {
          inspectDatasetRecord(row, "version");
          setFieldValue("#training-form", "dataset_version_id", row.id);
          logConsole("training form filled from dataset version", row);
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Dataset versions are created after imports are normalized and staged.", {
      pageKey: "#dataset-versions-table",
      itemLabel: "versions",
      serverPagination: serverPaginationForPayload("#dataset-versions-table", payload, page.limit, () => refreshDatasetVersions()),
    }),
  );
  refreshTrainingLifecycleView();
  return rows;
}

async function refreshDatasetViews() {
  const imports = await refreshDatasetImports();
  const versions = await refreshDatasetVersions();
  // #dataset-detail is shared by both the Imports and Versions "Inspect" actions
  // (each hands it a structurally distinct payload via its own renderer), so its
  // empty state is seeded here — once, from combined counts — rather than from
  // either sub-refresh, which would otherwise overwrite each other's message.
  const importCount = (imports || []).length;
  const versionCount = (versions || []).length;
  clearHost("#dataset-detail");
  if (!importCount && !versionCount) {
    $("#dataset-detail")?.appendChild(buildEmptyState({
      icon: "✎",
      title: "Nothing imported yet.",
      body: "Create a dataset export, then run an import from it — both the import record and the dataset version it produces will appear here for inspection.",
    }));
  } else {
    $("#dataset-detail")?.appendChild(buildEmptyState({
      icon: "→",
      title: "Select an import or version to inspect.",
      body: `${importCount} import${importCount === 1 ? "" : "s"} and ${versionCount} version${versionCount === 1 ? "" : "s"} available — choose “Inspect” on any row above to see its full record here.`,
    }));
  }
  renderOutput("#dataset-output", { imports, versions });
  return { imports, versions };
}

async function refreshDatasetPipeline() {
  const [candidates, exportsPayload, datasetViews, training] = await Promise.all([
    refreshCandidates(),
    refreshExports(),
    refreshDatasetViews(),
    refreshTrainingRuns(),
  ]);
  renderPipelineSummary({
    candidates,
    exports: exportsPayload,
    imports: datasetViews.imports,
    versions: datasetViews.versions,
    training,
  });
  return { candidates, exports: exportsPayload, ...datasetViews, training };
}

async function refreshTrainingRuns() {
  setTableLoading("#training-table", {
    title: "Loading training runs…",
    body: "Fetching learner run history and live progress snapshots.",
  });
  const filters = rememberTableContext("#training-table", currentTableContext("#training-table", "#training-filter-form"));
  const page = paginationParams("#training-table", 15);
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  params.set("paginated", "true");
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  const payload = await apiFetch(`/training/runs?${params.toString()}`);
  const rows = payload.items || [];
  state.trainingRuns = rows;
  renderTrainingSummary();
  const host = $("#training-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Run", "Dataset", "Mode", "Backend", "Status", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.id;
      if (row.id === state.selectedTrainingRunId) {
        tr.classList.add("active-row");
      }
      const progress = row.metrics?.progress || {};
      const progressLabel = progress.stage ? `${humanizeLabel(progress.stage)}${progress.step != null ? ` • step ${formattedValue(progress.step)}` : ""}` : "";
      tr.innerHTML = `
        <td><strong>${row.id}</strong><br/><span>${row.base_model}</span></td>
        <td>${row.dataset_version_id}</td>
        <td>${row.training_mode}</td>
        <td><span class="badge badge-info">${escapeHtml(humanizeLabel(row.trainer_backend || "custom"))}</span></td>
        <td>${statusBadge(row.status)}${progressLabel ? `<div class="cell-note">${escapeHtml(progressLabel)}</div>` : ""}</td>
        <td></td>
      `;
      tr.addEventListener("click", async (event) => {
        if (event.target.closest("button")) return;
        await inspectTrainingRun(row.id);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          await inspectTrainingRun(row.id);
        }, { accent: true }),
      );
      actions.appendChild(
        createActionButton("Evaluate", () => {
          inspectTrainingRun(row.id);
          setFieldValue("#evaluation-form", "training_run_id", row.id);
          logConsole("evaluation form filled from training run", row);
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Submit a training run to begin adapter creation for a dataset version.", {
      itemLabel: "training runs",
      pageKey: "#training-table",
      serverPagination: serverPaginationForPayload("#training-table", payload, page.limit, () => refreshTrainingRuns()),
    }),
  );
  syncTrainingPolling();
  refreshTrainingLifecycleView();
  return rows;
}

async function refreshEvaluations() {
  setTableLoading("#evaluation-table", {
    title: "Loading evaluations…",
    body: "Fetching evaluation runs, status, and promotion decisions.",
  });
  const filters = rememberTableContext("#evaluation-table", currentTableContext("#evaluation-table", "#evaluation-filter-form"));
  const page = paginationParams("#evaluation-table", 15);
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  params.set("paginated", "true");
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  const payload = await apiFetch(`/evaluation/runs?${params.toString()}`);
  const rows = payload.items || [];
  state.trainingEvaluations = rows;
  renderTrainingSummary();
  const host = $("#evaluation-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Evaluation", "Domain", "Status", "Promotion", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.id;
      if (row.id === state.selectedEvaluationId) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${row.id}</strong><br/><span>${row.training_run_id}</span></td>
        <td>${row.domain || "-"}</td>
        <td>${statusBadge(row.status || "-")}</td>
        <td>${statusBadge(row.promotion_status || "-")}</td>
        <td></td>
      `;
      tr.addEventListener("click", async (event) => {
        if (event.target.closest("button")) return;
        await inspectEvaluation(row.id);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          await inspectEvaluation(row.id);
        }, { accent: true }),
      );
      actions.appendChild(
        createActionButton("Prepare Deploy", async () => {
          const detail = await inspectEvaluation(row.id);
          const manifestPath = detail.result_json?.package_manifest_path || row.package_manifest_path || "";
          const alias = detail.result_json?.model_alias || deriveAliasFromManifest(manifestPath);
          setFieldValue("#deploy-form", "model_alias", alias);
          logConsole("deployment form prepared from evaluation", { evaluation_run_id: row.id, model_alias: alias, manifest_path: manifestPath });
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Evaluation runs will appear here once training outputs are scored.", {
      itemLabel: "evaluations",
      pageKey: "#evaluation-table",
      serverPagination: serverPaginationForPayload("#evaluation-table", payload, page.limit, () => refreshEvaluations()),
    }),
  );
  refreshTrainingLifecycleView();
  return rows;
}

async function refreshKpis() {
  const payload = await apiFetch("/evaluation/kpis");
  const metrics = Array.isArray(payload?.metrics) ? payload.metrics : [];
  const listenerRollups = Array.isArray(payload?.listener_rollups) ? payload.listener_rollups : [];
  const nodeRollups = Array.isArray(payload?.node_rollups) ? payload.node_rollups : [];
  const poolRollups = Array.isArray(payload?.pool_rollups) ? payload.pool_rollups : [];
  const metricMap = Object.fromEntries(metrics.map((item) => [item.metric_name, item]));
  const metricValue = (name) => metricMap[name]?.metric_value;
  renderMetricGrid("#kpi-metrics-grid", [
    { label: "TCO", badge: renderAmount(metricValue("total_cost_of_ownership"), { precision: 4, zeroMuted: false }), subvalue: "Production + learning pipeline" },
    { label: "Learning Spend", badge: renderAmount(metricValue("learning_pipeline_spend_total"), { precision: 4, zeroMuted: false }), subvalue: "Training + evaluation traffic" },
    { label: "Training Spend", badge: renderAmount(metricValue("training_pipeline_spend_total"), { precision: 4 }) },
    { label: "Evaluation Spend", badge: renderAmount(metricValue("evaluation_pipeline_spend_total"), { precision: 4 }) },
    { label: "Production Spend", badge: renderAmount(metricValue("production_request_spend_total"), { precision: 4 }) },
    { label: "Learning Share", value: `${((Number(metricValue("learning_pipeline_share_of_tco")) || 0) * 100).toFixed(1)}%`, subvalue: `${formattedValue(metricValue("learning_pipeline_request_count"))} attributed requests` },
    { label: "Node-Routed Spend", badge: renderAmount(metricValue("node_routed_request_spend_total"), { precision: 4 }), subvalue: `${formattedValue(metricValue("node_routed_request_count"))} requests` },
    { label: "Pooled Spend", badge: renderAmount(metricValue("pooled_request_spend_total"), { precision: 4 }), subvalue: `${formattedValue(metricValue("pooled_request_count"))} pooled requests` },
  ]);
  renderSimpleTable(
    "#kpi-output",
    "KPI Metrics",
    ["Metric", "Value", "Sample", "Policy"],
    metrics,
    (row) => {
      const tr = document.createElement("tr");
      const renderedValue = row.currency === "USD"
        ? renderAmount(row.metric_value, { precision: 4, zeroMuted: false })
        : `<span class="num">${escapeHtml(formattedValue(row.metric_value))}</span>`;
      tr.innerHTML = `
        <td><strong>${escapeHtml(humanizeLabel(row.metric_name || "-"))}</strong></td>
        <td>${renderedValue}</td>
        <td>${escapeHtml(formattedValue(row.sample_size))}</td>
        <td>${escapeHtml(row.policy_version || "-")}</td>
      `;
      return tr;
    },
    "KPI metrics will appear here once generated.",
  );
  renderSimpleTable(
    "#kpi-listener-rollups",
    "Listener Spend Concentration",
    ["Listener", "Spend", "Mix", "Share of TCO", "Actions"],
    listenerRollups,
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${renderIdChip(row.topology_id, { truncate: false })}</td>
        <td>${renderAmount(row.spend_total, { precision: 4, zeroMuted: false })}<br/><span>${renderAmount(row.production_spend_total, { precision: 4 })} prod / ${renderAmount(row.learning_spend_total, { precision: 4 })} learn</span></td>
        <td><span class="num">${escapeHtml(formattedValue(row.request_count))}</span><br/><span>${escapeHtml(formattedValue(row.production_request_count))} prod / ${escapeHtml(formattedValue(row.learning_request_count))} learn</span></td>
        <td><span class="num">${((Number(row.share_of_tco) || 0) * 100).toFixed(1)}%</span></td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Open Traffic", async () => {
        await openRequestHistoryContext({ listener_id: row.topology_id });
      }, { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    },
    "Listener-level spend concentration will appear here once inbound listener traffic is recorded.",
  );
  renderSimpleTable(
    "#kpi-node-rollups",
    "Node Spend Concentration",
    ["Node", "Role", "Spend", "Mix", "Share of TCO", "Actions"],
    nodeRollups,
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${renderIdChip(row.topology_id, { truncate: false })}${row.capacity_class ? `<br/><span>${escapeHtml(humanizeLabel(row.capacity_class))}</span>` : ""}</td>
        <td>${row.node_role ? escapeHtml(humanizeLabel(row.node_role)) : '<span class="empty-value">-</span>'}</td>
        <td>${renderAmount(row.spend_total, { precision: 4, zeroMuted: false })}<br/><span>${renderAmount(row.production_spend_total, { precision: 4 })} prod / ${renderAmount(row.learning_spend_total, { precision: 4 })} learn</span></td>
        <td><span class="num">${escapeHtml(formattedValue(row.request_count))}</span><br/><span>${escapeHtml(formattedValue(row.production_request_count))} prod / ${escapeHtml(formattedValue(row.learning_request_count))} learn</span></td>
        <td><span class="num">${((Number(row.share_of_tco) || 0) * 100).toFixed(1)}%</span></td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Open Traffic", async () => {
        await openRequestHistoryContext({ selected_node_id: row.topology_id });
      }, { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    },
    "Node-level spend concentration will appear here once node-routed traffic is recorded.",
  );
  renderSimpleTable(
    "#kpi-pool-rollups",
    "Pool Spend Concentration",
    ["Pool", "Spend", "Mix", "Share of TCO", "Actions"],
    poolRollups,
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${renderIdChip(row.topology_id, { truncate: false })}</td>
        <td>${renderAmount(row.spend_total, { precision: 4, zeroMuted: false })}<br/><span>${renderAmount(row.production_spend_total, { precision: 4 })} prod / ${renderAmount(row.learning_spend_total, { precision: 4 })} learn</span></td>
        <td><span class="num">${escapeHtml(formattedValue(row.request_count))}</span><br/><span>${escapeHtml(formattedValue(row.production_request_count))} prod / ${escapeHtml(formattedValue(row.learning_request_count))} learn</span></td>
        <td><span class="num">${((Number(row.share_of_tco) || 0) * 100).toFixed(1)}%</span></td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Open Traffic", async () => {
        await openRequestHistoryContext({ selected_pool_id: row.topology_id });
      }, { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    },
    "Pool-level spend concentration will appear here once pooled traffic is recorded.",
  );
  return payload;
}

async function refreshTrainingRuntimeStatus() {
  const payload = await apiFetch("/admin/api/training/runtime-status");
  renderTrainingRuntimeStatus(payload);
  return payload;
}

async function refreshTrainingStudioStatus() {
  const payload = await apiFetch("/admin/api/training/studio-status");
  renderTrainingStudioStatus(payload);
  return payload;
}

function getTrainingFormBody() {
  const data = new FormData($("#training-form"));
  return {
    dataset_version_id: data.get("dataset_version_id"),
    base_model: data.get("base_model"),
    training_mode: data.get("training_mode"),
    trainer_backend: data.get("trainer_backend") || "custom",
    epochs: Number(data.get("epochs") || 3),
    learning_rate: Number(data.get("learning_rate") || 0.0002),
    adapter_name: data.get("adapter_name") || null,
  };
}

async function runTrainingPreflight(trigger = null, { quietSuccess = false } = {}) {
  try {
    const payload = await withLoading(trigger, () => apiFetch("/training/preflight", {
      method: "POST",
      body: JSON.stringify(getTrainingFormBody()),
    }));
    if (payload.worker_runtime_status) {
      renderTrainingRuntimeStatus({ available: true, ...payload.worker_runtime_status });
    }
    renderTrainingPreflight(payload);
    if (!quietSuccess) {
      showToast(payload.ready ? "Training preflight passed." : "Training preflight reported blockers.", payload.ready ? "ok" : "warn");
    }
    return payload;
  } catch (error) {
    renderTrainingPreflight({
      ready: false,
      dataset_version_id: getTrainingFormBody().dataset_version_id || "",
      base_model: getTrainingFormBody().base_model || "",
      training_mode: getTrainingFormBody().training_mode || "",
      trainer_backend: getTrainingFormBody().trainer_backend || "custom",
      record_counts: {},
      checks: [],
      errors: [String(error)],
      warnings: [],
    });
    if (!quietSuccess) {
      showToast(`Training preflight failed: ${String(error)}`, "err");
    }
    throw error;
  }
}

async function inspectTrainingRun(runId) {
  state.selectedTrainingRunId = runId;
  state.selectedEvaluationId = null;
  setActiveRuntimeRow("#training-table", runId);
  setActiveRuntimeRow("#evaluation-table", "");
  const payload = await apiFetch(`/admin/api/training/runs/${runId}`);
  renderTrainingDetail(payload);
  syncTrainingPolling(payload);
  return payload;
}

async function inspectEvaluation(evaluationId) {
  state.selectedEvaluationId = evaluationId;
  state.selectedTrainingRunId = null;
  setActiveRuntimeRow("#evaluation-table", evaluationId);
  setActiveRuntimeRow("#training-table", "");
  const payload = await apiFetch(`/admin/api/evaluation/runs/${evaluationId}`);
  renderEvaluationDetail(payload);
  syncTrainingPolling();
  return payload;
}

function clearTrainingPolling() {
  if (state.trainingPollTimer) {
    window.clearInterval(state.trainingPollTimer);
    state.trainingPollTimer = null;
  }
}

function hasActiveTrainingRuns() {
  return (state.trainingRuns || []).some((row) => ["pending", "queued", "running"].includes(String(row.status || "").toLowerCase()));
}

function syncTrainingPolling(selectedRunPayload = null) {
  const selectedStatus = String(selectedRunPayload?.status || "").toLowerCase();
  const selectedActive = ["pending", "queued", "running"].includes(selectedStatus);
  const shouldPoll = state.activePanel === "training" && state.activeTrainingCollection === "runs" && (selectedActive || hasActiveTrainingRuns());
  if (!shouldPoll) {
    clearTrainingPolling();
    return;
  }
  if (state.trainingPollTimer) {
    return;
  }
  state.trainingPollTimer = window.setInterval(async () => {
    try {
      await refreshTrainingRuns();
      if (state.selectedTrainingRunId) {
        const latest = await apiFetch(`/admin/api/training/runs/${state.selectedTrainingRunId}`);
        renderTrainingDetail(latest);
        if (!["pending", "queued", "running"].includes(String(latest.status || "").toLowerCase()) && !hasActiveTrainingRuns()) {
          clearTrainingPolling();
        }
      } else if (!hasActiveTrainingRuns()) {
        clearTrainingPolling();
      }
    } catch (error) {
      clearTrainingPolling();
      logConsole("training polling failed", String(error));
    }
  }, 5000);
}

function renderLogTable(selector, rows, options = {}) {
  const { selectedKey = null, onInspect = null, serverPagination = null } = options;
  const host = $(selector);
  host.innerHTML = "";
  const tableOptions = tableOptionsForHost(host, selector, { itemLabel: "records" });
  if (serverPagination) {
    tableOptions.serverPagination = serverPagination;
  }
  host.appendChild(
    makeTable(["Time", "Level", "Component", "Message", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      const recordKey = buildOpsRecordKey(row);
      tr.dataset.recordId = recordKey;
      if (selectedKey && recordKey === selectedKey) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td>${timeLabel(row.timestamp)}</td>
        <td>${statusBadge(row.level || "-")}</td>
        <td>${row.component || "-"}</td>
        <td>${row.message || "-"}</td>
        <td></td>
      `;
      if (onInspect) {
        tr.addEventListener("click", async (event) => {
          if (event.target.closest("button")) return;
          await onInspect(row);
        });
      }
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", () => onInspect ? onInspect(row) : renderOpsRecordDetail(row), { accent: true }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "No records match the current filter.", tableOptions),
  );
}

function renderOperationalEventTable(selector, rows, options = {}) {
  const { selectedKey = null, onInspect = null, serverPagination = null } = options;
  const host = $(selector);
  host.innerHTML = "";
  const tableOptions = tableOptionsForHost(host, selector, { itemLabel: "events" });
  if (serverPagination) {
    tableOptions.serverPagination = serverPagination;
  }
  const columnMode = opsEventColumnModeForRows(rows);
  const headers = columnMode === "traffic"
    ? ["Time", "Request", "Route", "Performance", "Usage", "Origin", "Inbound", "Actions"]
    : ["Time", "Source", "Class", "Level", "Component", "Training", "Message", "Actions"];
  host.appendChild(
    makeTable(headers, rows, (row) => {
      const tr = document.createElement("tr");
      const recordKey = buildOpsRecordKey(row);
      tr.dataset.recordId = recordKey;
      if (selectedKey && recordKey === selectedKey) {
        tr.classList.add("active-row");
      }
      if (columnMode === "traffic") {
        tr.innerHTML = `
          <td>${timeLabel(row.timestamp)}</td>
          <td><strong>${escapeHtml(row.source_record_id || "-")}</strong><br/><span>${escapeHtml(row.requested_model || "-")}</span>${row.prompt_template_name ? `<br/><span>Prompt ${escapeHtml(row.prompt_template_name)}${row.prompt_template_version ? ` · v${escapeHtml(formattedValue(row.prompt_template_version))}` : ""}</span><br/>${renderPromptSelectionModeBadge(row.prompt_template_selection_mode, row.prompt_template_rollout_percentage)}` : ""}</td>
          <td><strong>${escapeHtml(row.selected_provider || "-")}</strong><br/><span>${escapeHtml(row.selected_model || row.requested_model || "-")}</span>${row.selected_pool_id ? `<br/>${renderIdChip(row.selected_pool_id, { truncate: false })}` : ""}${row.selected_node_id ? `<br/>${renderIdChip(row.selected_node_id, { truncate: false })}` : ""}</td>
          <td><strong>First:</strong> ${row.first_response_latency_ms == null ? '<span class="empty-value">-</span>' : `${escapeHtml(formattedValue(row.first_response_latency_ms))} ms`}<br/><strong>Total:</strong> ${row.latency_ms == null ? '<span class="empty-value">-</span>' : `${escapeHtml(formattedValue(row.latency_ms))} ms`}</td>
          <td><strong>Tokens:</strong> ${row.total_tokens == null ? '<span class="empty-value">-</span>' : escapeHtml(formattedValue(row.total_tokens))}${row.input_tokens != null || row.output_tokens != null ? `<br/><span>In ${escapeHtml(formattedValue(row.input_tokens || 0))} · Out ${escapeHtml(formattedValue(row.output_tokens || 0))}</span>` : ""}${row.cost_estimate != null ? `<br/><strong>Cost:</strong> ${renderAmount(row.cost_estimate, { precision: 4, zeroMuted: false })}` : ""}</td>
          <td><strong>${escapeHtml(humanizeLabel(row.traffic_origin || "interactive"))}</strong>${row.automation_scope ? `<br/><span>${escapeHtml(humanizeLabel(row.automation_scope))}</span>` : ""}<br/>${statusBadge(row.domain || "muted").replace("badge-muted", "badge-info")}<br/><span>${escapeHtml(row.task_type || "-")}</span></td>
          <td>${row.listener_id ? renderIdChip(row.listener_id, { truncate: false }) : '<span class="empty-value">Default</span>'}</td>
          <td></td>
        `;
      } else {
        tr.innerHTML = `
          <td>${timeLabel(row.timestamp)}</td>
          <td><span class="badge badge-info">${escapeHtml(humanizeLabel(row.event_source || "ops_log"))}</span></td>
          <td><span class="badge badge-muted">${escapeHtml(humanizeLabel(row.event_class || "log"))}</span></td>
          <td>${statusBadge(row.level || "-")}</td>
          <td>${escapeHtml(row.component || "-")}</td>
          <td>${boolBadge(Boolean(row.training_opportunity))}</td>
          <td>${escapeHtml(row.message || "-")}</td>
          <td></td>
        `;
      }
      if (onInspect) {
        tr.addEventListener("click", async (event) => {
          if (event.target.closest("button")) return;
          await onInspect(row);
        });
      }
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", () => onInspect ? onInspect(row) : renderOpsRecordDetail(row), { accent: true }),
      );
      if (row.event_source === "job" && row.source_record_id) {
        actions.appendChild(
          createActionButton("Retry", async () => {
            const result = await apiFetch(`/admin/api/jobs/${encodeURIComponent(row.source_record_id)}/retry`, {
              method: "POST",
              body: JSON.stringify({ reset_attempts: true, available_now: true }),
            });
            logConsole("job retry", result);
            showToast(`Job ${row.source_record_id} retried.`, "ok");
            await Promise.all([refreshOperationalEvents(), refreshJobs()]);
          }),
        );
      }
      if (row.event_source === "job" && row.source_record_id) {
        actions.appendChild(
          createActionButton("Cancel", async () => {
            const result = await apiFetch(`/admin/api/jobs/${encodeURIComponent(row.source_record_id)}/cancel`, { method: "POST" });
            logConsole("job cancel", result);
            showToast(`Job ${row.source_record_id} canceled.`, "warn");
            await Promise.all([refreshOperationalEvents(), refreshJobs()]);
          }, { destructive: true, confirmMessage: `Cancel job ${row.source_record_id}?` }),
        );
      }
      if (row.event_source === "runtime_event" && row.source_record_id) {
        actions.appendChild(
          createActionButton("Replay", async () => {
            const result = await apiFetch(`/admin/api/events/${encodeURIComponent(row.source_record_id)}/replay`, { method: "POST" });
            logConsole("event replay", result);
            showToast(`Runtime event ${row.source_record_id} replayed.`, "ok");
            await Promise.all([refreshOperationalEvents(), refreshEvents(), refreshJobs()]);
          }),
        );
      }
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "No operational events match the current filter.", tableOptions),
  );
}

function renderMcpTraceTable(selector, rows) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Server", "Tool", "Call", "Arguments", "Result"], rows || [], (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.server || "-")}</strong></td>
        <td>${escapeHtml(row.tool_name || "-")}</td>
        <td>${escapeHtml(row.tool_call_id || "-")}</td>
        <td><code>${escapeHtml(JSON.stringify(row.arguments || {}))}</code></td>
        <td><code>${escapeHtml(JSON.stringify(row.result || {}))}</code></td>
      `;
      return tr;
    }, "No MCP tool activity recorded for this request."),
  );
}

async function inspectOpsRecord(row) {
  const recordKey = buildOpsRecordKey(row);
  state.selectedOpsRecordKey = recordKey;
  state.selectedOpsRecord = row && Object.keys(row).length ? row : null;
  setActiveRuntimeRow("#ops-events-table", recordKey);
  if (row?.event_source === "request" && row?.source_record_id) {
    const detail = await apiFetch(`/admin/api/proxy/requests/${encodeURIComponent(row.source_record_id)}`);
    setOperationsInspectorMode("request");
    renderRequestDetail(detail);
    return;
  }
  renderOpsRecordDetail(row);
}

async function refreshOperationsSummary() {
  const summary = await apiFetch("/admin/api/ops/summary");
  const metrics = await apiFetch("/metrics");
  renderOpsSummaryChips(summary);
  renderMetricGrid("#ops-metrics-grid", [
    { label: "Jobs", value: String(Object.values(metrics.job_counts || {}).reduce((sum, value) => sum + Number(value || 0), 0)) },
    { label: "Events", value: String(Object.values(metrics.event_counts || {}).reduce((sum, value) => sum + Number(value || 0), 0)) },
    { label: "Routes", value: String(Object.keys(metrics.route_counts || {}).length) },
    { label: "Configured Providers", value: String(Object.values(metrics.provider_configuration || {}).filter(Boolean).length) },
    { label: "Node-Routed", value: String(metrics.topology_counts?.node_routed_routes ?? 0) },
    { label: "Pooled Routes", value: String(metrics.topology_counts?.pooled_routes ?? 0) },
  ]);
  renderMetricGrid("#ops-stream-grid", [
    { label: "Stream Starts", value: String(summary.streaming?.stream_start_count ?? 0) },
    { label: "Stream Complete", value: String(summary.streaming?.stream_complete_count ?? 0) },
    { label: "Stream Failed", value: String(summary.streaming?.stream_failed_count ?? 0) },
    {
      label: "Providers Cooling Down",
      value: String(Object.values(summary.provider_health || {}).filter((item) => item && item.cooled_down).length),
    },
  ]);
  const mcpRuntime = Object.values(summary.mcp_runtime || {});
  renderMetricGrid("#ops-mcp-grid", [
    { label: "MCP Servers Seen", value: String(mcpRuntime.length) },
    { label: "Validated", value: String(mcpRuntime.reduce((sum, item) => sum + Number(item.validation_count || 0), 0)) },
    { label: "Tool Calls", value: String(mcpRuntime.reduce((sum, item) => sum + Number(item.tool_call_count || 0), 0)) },
    { label: "Failures", value: String(mcpRuntime.reduce((sum, item) => sum + Number(item.failed_tool_calls || 0) + Number(item.failed_validations || 0), 0)) },
  ]);
  renderLogTable("#ops-mcp-table", mcpRuntime.map((item) => ({
    timestamp: item.last_tool_at || item.last_validation_at,
    level: item.last_error ? "ERROR" : "INFO",
    component: `mcp.${item.server}`,
    message: item.last_tool_name ? `Last tool: ${item.last_tool_name}` : "Validation activity",
    data: item,
  })));
  renderLogTable("#ops-stream-live-table", (summary.streaming && summary.streaming.recent_stream_summaries) || []);
  return { summary, metrics };
}

async function refreshOperationalEvents() {
  setTableLoading("#ops-events-table", {
    title: "Loading operational events…",
    body: "Fetching unified logs, request traffic, jobs, runtime events, and audit records.",
  });
  const page = paginationParams("#ops-events-table", 25);
  const filters = rememberTableContext("#ops-events-table", currentTableContext("#ops-events-table", "#ops-events-filter-form"));
  const params = new URLSearchParams(filters);
  params.set("paginated", "true");
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  const payload = await apiFetch(`/admin/api/ops/events?${params.toString()}`);
  renderOpsColumnPresetControls();
  renderSavedOpsPresetControls();
  renderOpsActiveViewStrip();
  renderOperationalEventTable("#ops-events-table", payload.items || [], {
    selectedKey: state.selectedOpsRecordKey,
    onInspect: inspectOpsRecord,
    serverPagination: serverPaginationForPayload("#ops-events-table", payload, page.limit, () => refreshOperationalEvents()),
  });
  return payload;
}

function currentSelectedOpsEvent() {
  return state.selectedOpsRecord && Object.keys(state.selectedOpsRecord).length ? state.selectedOpsRecord : null;
}

function opsEventDefaultDomain(event) {
  return String(event?.category || event?.event_source || "operations").replaceAll("_", "-");
}

function opsEventDefaultOperation(event) {
  return String(event?.event_class || event?.event_source || "event");
}

async function promoteSelectedOpsEvent() {
  const event = currentSelectedOpsEvent();
  if (!event) {
    showToast("Select an operational event first.", "warn");
    return;
  }
  const payload = await apiFetch("/admin/api/ops/events/promote-candidate", {
    method: "POST",
    body: JSON.stringify({
      event,
      domain: opsEventDefaultDomain(event),
      task_type: "event_review",
      approve_immediately: false,
    }),
  });
  logConsole("ops event promoted", payload);
  showToast(`Promoted event into candidate ${payload.candidate_id}.`, "ok");
}

async function openExportDraftFromOpsEvent() {
  const event = currentSelectedOpsEvent();
  if (!event) {
    showToast("Select an operational event first.", "warn");
    return;
  }
  switchPanel("data");
  switchCollection("data", "exports");
  await ensurePanelLoaded("data", true);
  setFieldValue("#export-form", "domain", opsEventDefaultDomain(event));
  setFieldValue("#export-form", "interaction_protocol", "");
  setFieldValue("#export-form", "interaction_operation", opsEventDefaultOperation(event));
  setFieldValue("#export-form", "interaction_outcome", event.event_class === "error" ? "failure" : "success");
  setFieldValue(
    "#export-form",
    "prompt_template_name",
    event.event_source === "request" ? event.prompt_template_name || "" : "",
  );
  setFieldValue(
    "#export-form",
    "prompt_template_version",
    event.event_source === "request" ? event.prompt_template_version || "" : "",
  );
  setFieldValue(
    "#export-form",
    "prompt_template_selection_mode",
    event.event_source === "request" ? event.prompt_template_selection_mode || "" : "",
  );
  showToast(`Seeded export draft from ${humanizeLabel(event.event_source || "event")} context.`, "ok");
}

async function openCanonicalRuntimeEventDirectory() {
  switchPanel("operations");
  switchSubview("operations", "monitor");
  await ensurePanelLoaded("operations", true);
  showToast("Opened the canonical operational event directory.", "info");
}

async function applyOpsPreset(preset) {
  const current = collectFormFilters("#ops-events-filter-form");
  const next = { ...current };
  const clearTrafficScope = () => {
    Object.assign(next, {
      event_source: "",
      selected_provider: "",
      selected_model: "",
      prompt_template_name: "",
      prompt_template_version: "",
      prompt_template_selection_mode: "",
      selected_pool_id: "",
      selected_node_id: "",
      traffic_origin: "",
      automation_scope: "",
    });
  };
  if (preset === "errors") {
    clearTrafficScope();
    Object.assign(next, { event_class: "error", sort_by: "timestamp", sort_dir: "desc" });
  } else if (preset === "traffic") {
    Object.assign(next, {
      event_class: "request",
      event_source: "request",
      level: "",
      component: "",
      category: "",
      promotable_only: "",
      sort_by: "timestamp",
      sort_dir: "desc",
    });
  } else if (preset === "audit") {
    clearTrafficScope();
    Object.assign(next, { event_class: "audit", sort_by: "timestamp", sort_dir: "desc" });
  } else if (preset === "training") {
    clearTrafficScope();
    Object.assign(next, { promotable_only: "true", sort_by: "timestamp", sort_dir: "desc" });
  } else if (preset === "listener") {
    const selectedListener = currentSelectedOpsEvent()?.listener_id
      || currentSelectedOpsEvent()?.data?.listener_id
      || currentSelectedOpsEvent()?.data?.metadata?.listener_id
      || current.listener_id;
    if (!selectedListener) {
      showToast("Select an event with a listener first, or enter a listener id.", "warn");
      return;
    }
    Object.assign(next, { listener_id: selectedListener, sort_by: "timestamp", sort_dir: "desc" });
  }
  setOperationalEventFilters(next);
  resetTablePage("#ops-events-table");
  await refreshOperationalEvents();
}

async function loadSavedOpsPreset(slot) {
  const next = currentSavedOpsPreset(slot);
  setOperationalEventFilters(next);
  resetTablePage("#ops-events-table");
  await refreshOperationalEvents();
}

async function applyOperationalEventFilters({ resetPage = true } = {}) {
  renderOpsEventTrafficScopeVisibility();
  rememberTableContext("#ops-events-table", collectFormFilters("#ops-events-filter-form"));
  if (resetPage) {
    resetTablePage("#ops-events-table");
  }
  await refreshOperationalEvents();
}

async function refreshOperationsLive() {
  const payload = await apiFetch("/admin/api/ops/live");
  renderOutput("#ops-live-output", payload);
  renderOpsSummaryChips(payload.summary || {});
  renderMetricGrid("#ops-stream-grid", [
    { label: "Stream Starts", value: String(payload.summary?.streaming?.stream_start_count ?? 0) },
    { label: "Stream Complete", value: String(payload.summary?.streaming?.stream_complete_count ?? 0) },
    { label: "Stream Failed", value: String(payload.summary?.streaming?.stream_failed_count ?? 0) },
    {
      label: "Providers Cooling Down",
      value: String(Object.values(payload.summary?.provider_health || {}).filter((item) => item && item.cooled_down).length),
    },
  ]);
  const mcpRuntime = Object.values(payload.summary?.mcp_runtime || {});
  renderMetricGrid("#ops-mcp-grid", [
    { label: "MCP Servers Seen", value: String(mcpRuntime.length) },
    { label: "Validated", value: String(mcpRuntime.reduce((sum, item) => sum + Number(item.validation_count || 0), 0)) },
    { label: "Tool Calls", value: String(mcpRuntime.reduce((sum, item) => sum + Number(item.tool_call_count || 0), 0)) },
    { label: "Failures", value: String(mcpRuntime.reduce((sum, item) => sum + Number(item.failed_tool_calls || 0) + Number(item.failed_validations || 0), 0)) },
  ]);
  renderLogTable("#ops-mcp-table", mcpRuntime.map((item) => ({
    timestamp: item.last_tool_at || item.last_validation_at,
    level: item.last_error ? "ERROR" : "INFO",
    component: `mcp.${item.server}`,
    message: item.last_tool_name ? `Last tool: ${item.last_tool_name}` : "Validation activity",
    data: item,
  })));
  renderLogTable("#ops-stream-live-table", (payload.summary?.streaming && payload.summary.streaming.recent_stream_summaries) || []);
  return payload;
}

async function inspectJob(jobId) {
  state.selectedJobId = jobId;
  state.selectedEventId = null;
  setActiveRuntimeRow("#jobs-table", jobId);
  const payload = await apiFetch(`/admin/api/jobs/${jobId}`);
  showDetailCard("#job-detail-card", "#job-detail-output", payload);
  return payload;
}

async function inspectEvent(eventId) {
  state.selectedEventId = eventId;
  state.selectedJobId = null;
  setActiveRuntimeRow("#events-table", eventId);
  const payload = await apiFetch(`/admin/api/events/${eventId}`);
  showDetailCard("#event-detail-card", "#event-detail-output", payload);
  return payload;
}

async function refreshJobs() {
  setTableLoading("#jobs-table", {
    title: "Loading jobs…",
    body: "Fetching current background job worklists.",
  });
  const filters = rememberTableContext("#jobs-table", currentTableContext("#jobs-table", "#jobs-filter-form"));
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  const page = paginationParams("#jobs-table", 15);
  params.set("paginated", "true");
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  const payload = await apiFetch(`/admin/api/jobs?${params.toString()}`);
  const rows = payload.items || [];
  state.runtimeJobs = rows;
  renderRuntimeSummary();
  const host = $("#jobs-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Job", "Status", "Attempts", "Type", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.id;
      if (row.id === state.selectedJobId) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${row.id}</strong></td>
        <td>${statusBadge(row.status)}</td>
        <td>${row.attempts}/${row.max_attempts}</td>
        <td>${row.job_type}</td>
        <td></td>
      `;
      tr.addEventListener("click", async (event) => {
        if (event.target.closest("button")) return;
        await inspectJob(row.id);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          await inspectJob(row.id);
        }, { accent: true }),
      );
      actions.appendChild(
        createActionButton("Retry", async () => {
          const result = await apiFetch(`/admin/api/jobs/${row.id}/retry`, {
            method: "POST",
            body: JSON.stringify({ reset_attempts: true, available_now: true }),
          });
          logConsole("job retry", result);
          showToast(`Job ${row.id} retried.`, "ok");
          await refreshJobs();
        }),
      );
      actions.appendChild(
        createActionButton("Cancel", async () => {
          const result = await apiFetch(`/admin/api/jobs/${row.id}/cancel`, { method: "POST" });
          logConsole("job cancel", result);
          showToast(`Job ${row.id} canceled.`, "warn");
          await refreshJobs();
        }, { destructive: true, confirmMessage: `Cancel job ${row.id}?` }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Queued and running jobs will appear here.", {
      itemLabel: "jobs",
      pageKey: "#jobs-table",
      serverPagination: serverPaginationForPayload("#jobs-table", payload, page.limit, () => refreshJobs()),
    }),
  );
}

async function refreshEvents() {
  setTableLoading("#events-table", {
    title: "Loading events…",
    body: "Fetching event history and processing state.",
  });
  const entries = rememberTableContext("#events-table", currentTableContext("#events-table", "#events-filter-form"));
  const params = new URLSearchParams();
  Object.entries(entries).forEach(([key, value]) => {
    if (!value) return;
    params.set(key, value);
  });
  const page = paginationParams("#events-table", 15);
  params.set("paginated", "true");
  params.set("limit", String(page.limit));
  params.set("offset", String(page.offset));
  const payload = await apiFetch(`/admin/api/events?${params.toString()}`);
  const rows = payload.items || [];
  state.runtimeEvents = rows;
  renderRuntimeSummary();
  const host = $("#events-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Event", "Type", "Source", "Processed", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.dataset.recordId = row.id;
      if (row.id === state.selectedEventId) {
        tr.classList.add("active-row");
      }
      tr.innerHTML = `
        <td><strong>${row.id}</strong></td>
        <td>${row.event_type}</td>
        <td>${row.source}</td>
        <td>${row.processed_at ? timeLabel(row.processed_at) : statusBadge("pending")}</td>
        <td></td>
      `;
      tr.addEventListener("click", async (event) => {
        if (event.target.closest("button")) return;
        await inspectEvent(row.id);
      });
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          await inspectEvent(row.id);
        }, { accent: true }),
      );
      actions.appendChild(
        createActionButton("Replay", async () => {
          const result = await apiFetch(`/admin/api/events/${row.id}/replay`, { method: "POST" });
          logConsole("event replay", result);
          await refreshEvents();
          await refreshJobs();
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Runtime events will appear here as the outbox processes work.", {
      itemLabel: "events",
      pageKey: "#events-table",
      serverPagination: serverPaginationForPayload("#events-table", payload, page.limit, () => refreshEvents()),
    }),
  );
}

async function initialize() {
  $("#token-input").value = state.token;
  enhanceFormLabels();
  restorePersistentTableContexts();
  setFoundationModelVisibilityScope(currentFoundationModelVisibilityScope());

  $$(".nav-link").forEach((button) => {
    button.addEventListener("click", () => switchPanel(button.dataset.panel));
  });
  window.addEventListener("hashchange", () => switchPanel(panelFromHash(), { updateHash: false }));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("#chat-model-picker-modal")?.classList.contains("active")) {
      closeChatModelPicker();
    }
  });
  switchPanel(panelFromHash(), { updateHash: false });

  $("#save-token").addEventListener("click", () => {
    state.token = $("#token-input").value.trim();
    localStorage.setItem("llmproxy.admin.token", state.token);
    state.loadedPanels.clear();
    setStatus("Token Saved", "ok");
    showToast("Operator token saved.", "ok");
    ensurePanelLoaded(state.activePanel).catch((error) => {
      setStatus("Token Required", "err");
      showToast(`Initial load failed: ${String(error)}`, "err");
      logConsole("initial load failed", String(error));
    });
  });

  $("#clear-token").addEventListener("click", () => {
    state.token = "";
    $("#token-input").value = "";
    localStorage.removeItem("llmproxy.admin.token");
    state.loadedPanels.clear();
    setStatus("Token Cleared", "warn");
    showToast("Operator token cleared.", "warn");
  });

  $("#check-connection").addEventListener("click", async (event) => {
    try {
      const payload = await withLoading(event.currentTarget, () => refreshHealth());
      setStatus(`Connected: ${payload.environment}`, "ok");
      showToast("Connection verified.", "ok");
      logConsole("health check", payload);
    } catch (error) {
      setStatus("Connection Failed", "err");
      showToast(`Connection failed: ${String(error)}`, "err");
      logConsole("health check failed", String(error));
    }
  });

  $("#clear-console").addEventListener("click", () => {
    $("#console-output").textContent = "";
  });
  $("#close-request-detail")?.addEventListener("click", () => $("#request-detail-card")?.classList.add("hidden"));
  $("#close-model-detail")?.addEventListener("click", () => $("#model-detail-card")?.classList.add("hidden"));
  $("#close-training-detail")?.addEventListener("click", () => $("#training-detail-card")?.classList.add("hidden"));
  $("#close-evaluation-detail")?.addEventListener("click", () => $("#evaluation-detail-card")?.classList.add("hidden"));
  $("#close-job-detail")?.addEventListener("click", () => $("#job-detail-card")?.classList.add("hidden"));
  $("#close-event-detail")?.addEventListener("click", () => $("#event-detail-card")?.classList.add("hidden"));
  $$("[data-subview-group]").forEach((button) => {
    button.addEventListener("click", () => switchSubview(button.dataset.subviewGroup, button.dataset.subview));
  });
  $$(".nav-sublink").forEach((button) => {
    button.addEventListener("click", async () => {
      const panel = normalizedPanel(button.dataset.panel);
      switchPanel(panel);
      switchSubview(button.dataset.subviewGroup, button.dataset.subview);
      if (state.token) {
        await ensurePanelLoaded(panel, true);
      }
    });
  });
  $$("[data-collection-group]").forEach((button) => {
    button.addEventListener("click", () => switchCollection(button.dataset.collectionGroup, button.dataset.collection));
  });
  switchSubview("overview", state.activeOverviewSubview);
  switchSubview("operations", state.activeOperationsSubview);
  switchSubview("proxy", state.activeProxySubview);
  switchSubview("models", state.activeModelsSubview);
  switchSubview("training", state.activeTrainingSubview);
  switchCollection("data", state.activeDataCollection);
  switchCollection("governance", state.activeGovernanceCollection);
  switchCollection("integrations", state.activeIntegrationsCollection);
  switchCollection("modelCatalog", state.activeModelCatalogCollection);
  switchCollection("modelRegister", state.activeModelRegisterCollection);
  switchCollection("modelRouting", state.activeModelRoutingCollection);
  switchCollection("training", state.activeTrainingCollection);
  switchCollection("runtime", state.activeRuntimeCollection);
  switchCollection("ops", state.activeOpsCollection);
  renderRequestDetail({});
  renderModelDetail({});
  renderModelDetail({}, "#model-routing-detail-summary-table");
  renderTrainingDetail({});
  renderTrainingPreflight({});
  refreshTrainingLifecycleView();
  renderTrainingRuntimeStatus({ available: false, detail: "No training-worker runtime report has been received yet." });
  renderTrainingStudioStatus({ enabled: false, configured: false, reachable: false, detail: "Studio status has not been loaded yet." });
  renderEvaluationDetail({});
  renderJobDetail({});
  renderEventDetail({});
  renderOpsRecordDetail({});
  renderOpsColumnPresetControls();
  renderSavedOpsPresetControls();
  renderOpsActiveViewStrip();
  renderOpsEventTrafficFilterOptions();
  renderAllPromptTemplatePickers();

  document.querySelector("[data-action='refresh-health']").addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshHealth());
      showToast("Health refreshed.", "ok");
    } catch (error) {
      showToast(`Health refresh failed: ${String(error)}`, "err");
      logConsole("refresh health failed", String(error));
    }
  });
  document.querySelector("[data-action='refresh-config']").addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshConfig());
      showToast("Config refreshed.", "ok");
    } catch (error) {
      showToast(`Config refresh failed: ${String(error)}`, "err");
      logConsole("refresh config failed", String(error));
    }
  });
  document.querySelector("[data-action='validate-config']").addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => validateConfig());
      showToast("Configuration validated.", "ok");
    } catch (error) {
      showToast(`Config validation failed: ${String(error)}`, "err");
      logConsole("validate config failed", String(error));
    }
  });
  document.querySelector("[data-action='refresh-health-secondary']")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshHealth());
    } catch (error) {
      showToast(`Health refresh failed: ${String(error)}`, "err");
      logConsole("health refresh failed", String(error));
    }
  });
  document.querySelector("[data-action='refresh-config-secondary']")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshConfig());
    } catch (error) {
      showToast(`Config refresh failed: ${String(error)}`, "err");
      logConsole("config refresh failed", String(error));
    }
  });

  $("#config-set-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/admin/api/config/set", { method: "POST", body: JSON.stringify(payload) }));
      logConsole("config set", result);
      showToast("Configuration updated.", "ok");
      await refreshConfig();
    } catch (error) {
      showToast(`Config update failed: ${String(error)}`, "err");
      logConsole("config set failed", String(error));
    }
  });

  $("#listener-editor-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const listenerId = String(data.get("listener_id") || "").trim();
    if (!listenerId) {
      showToast("Listener ID is required.", "err");
      return;
    }
    const listeners = [...currentInboundListeners()];
    const nextListener = {
      listener_id: listenerId,
      name: String(data.get("name") || "").trim() || listenerId,
      host: String(data.get("host") || "0.0.0.0").trim() || "0.0.0.0",
      port: Number(data.get("port") || 0),
      published_host: String(data.get("published_host") || "").trim() || null,
      published_port: Number(data.get("published_port") || 0) || null,
      exposes_admin: data.get("exposes_admin") === "on",
      exposes_platform_api: data.get("exposes_platform_api") === "on",
      exposes_proxy: data.get("exposes_proxy") === "on",
    };
    const existingIndex = listeners.findIndex((item) => String(item.listener_id || "") === String(state.selectedInboundListenerId || listenerId));
    if (existingIndex >= 0) {
      listeners.splice(existingIndex, 1, nextListener);
    } else {
      listeners.push(nextListener);
    }
    const payload = {
      listeners,
      env_file: String(data.get("env_file") || ".env.local"),
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/admin/api/config/inbound-listeners", {
        method: "POST",
        body: JSON.stringify(payload),
      }));
      state.selectedInboundListenerId = listenerId;
      replaceInboundListenerTopology(result.listeners || listeners);
      showToast("Inbound listener topology updated. Restart required.", "ok");
      logConsole("inbound listener topology updated", result);
    } catch (error) {
      showToast(`Listener update failed: ${String(error)}`, "err");
      logConsole("listener update failed", String(error));
    }
  });
  $("#new-listener-definition")?.addEventListener("click", (event) => {
    event.preventDefault();
    resetInboundListenerEditor();
  });
  $("#delete-listener-definition")?.addEventListener("click", async (event) => {
    event.preventDefault();
    const selected = currentSelectedInboundListener();
    if (!selected) {
      showToast("Select a listener to delete.", "warn");
      return;
    }
    const listeners = currentInboundListeners().filter((item) => String(item.listener_id || "") !== String(selected.listener_id || ""));
    const payload = {
      listeners,
      env_file: String($("#listener-editor-form [name='env_file']")?.value || ".env.local"),
    };
    try {
      const result = await withLoading(event.currentTarget, () => apiFetch("/admin/api/config/inbound-listeners", {
        method: "POST",
        body: JSON.stringify(payload),
      }));
      state.selectedInboundListenerId = null;
      replaceInboundListenerTopology(result.listeners || listeners);
      showToast("Inbound listener removed. Restart required.", "ok");
      logConsole("inbound listener removed", result);
    } catch (error) {
      showToast(`Listener delete failed: ${String(error)}`, "err");
      logConsole("listener delete failed", String(error));
    }
  });

  $("#chat-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const data = new FormData(event.currentTarget);
    try {
      const wantsStream = data.get("stream") === "on";
      const promptTemplateName = String(data.get("prompt_template_name") || "").trim();
      const promptTemplateVersion = String(data.get("prompt_template_version") || "").trim();
      const promptTemplateVariables = parseJsonObject(data.get("prompt_template_variables"), "Prompt template variables");
      const body = {
        model: data.get("model"),
        stream: wantsStream,
        temperature: Number(data.get("temperature")),
        max_tokens: Number(data.get("max_tokens")),
        metadata: {
          session_id: data.get("session_id"),
          listener_id: String(data.get("listener_id") || "").trim() || null,
          domain_hint: data.get("domain_hint") || null,
          task_type_hint: data.get("task_type_hint") || null,
          route_tags: csv(String(data.get("route_tags") || "")),
          region_hint: String(data.get("region_hint") || "").trim() || null,
        },
        messages: parseMessages(String(data.get("messages") || "")),
      };
      if (promptTemplateName) {
        body.metadata.prompt_template_name = promptTemplateName;
        body.metadata.prompt_template_variables = promptTemplateVariables;
        if (promptTemplateVersion) {
          body.metadata.prompt_template_version = Number(promptTemplateVersion);
        }
      }
      const mcpTools = parseMcpTools(String(data.get("mcp_tools") || ""));
      if (mcpTools.length && submitter.dataset.mode === "chat") {
        body.tools = mcpTools;
      }
      if (submitter.dataset.mode === "preview") {
        try {
          const result = await withLoading(submitter, () => apiFetch("/admin/api/proxy/route-preview", {
            method: "POST",
            body: JSON.stringify({
              model: body.model,
              temperature: body.temperature,
              max_tokens: body.max_tokens,
              messages: body.messages,
              session_id: body.metadata.session_id,
              listener_id: body.metadata.listener_id,
              domain_hint: body.metadata.domain_hint,
              task_type_hint: body.metadata.task_type_hint,
              region_hint: body.metadata.region_hint,
              route_tags: body.metadata.route_tags,
            }),
          }));
          renderRoutePreview(result);
          logConsole("route preview", result);
          showToast("Route preview generated.", "ok");
        } catch (error) {
          showToast(`Route preview failed: ${String(error)}`, "err");
          logConsole("route preview failed", String(error));
        }
        return;
      }
      const url = submitter.dataset.mode === "ensemble" ? "/proxy/ensemble" : "/v1/chat/completions";
      try {
        const result = await withLoading(submitter, async () => (
          wantsStream && submitter.dataset.mode === "chat"
            ? apiStream(url, body)
            : apiFetch(url, { method: "POST", body: JSON.stringify(body) })
        ));
        renderOutput("#chat-output", result);
        logConsole(`proxy ${submitter.dataset.mode}`, result);
        showToast(`${submitter.dataset.mode === "ensemble" ? "Ensemble" : "Chat"} request completed.`, "ok");
        await refreshOperationalEvents();
        const actualDetail = await fetchLatestRequestDetailBySession(body.metadata.session_id);
        if (actualDetail) {
          renderRouteComparison(actualDetail);
        }
      } catch (error) {
        showToast(`Proxy request failed: ${String(error)}`, "err");
        logConsole(`proxy ${submitter.dataset.mode} failed`, String(error));
      }
    } catch (error) {
      showToast(`Chat form error: ${String(error)}`, "err");
      logConsole("chat form error", String(error));
    }
  });
  $("#open-chat-model-picker")?.addEventListener("click", () => {
    openChatModelPicker().catch((error) => {
      showToast(`Model picker failed: ${String(error)}`, "err");
      logConsole("model picker failed", String(error));
    });
  });
  $("#chat-prompt-template-name")?.addEventListener("change", () => {
    renderPromptTemplatePicker("#chat-prompt-template-name", "#chat-prompt-template-version", {
      blankNameLabel: "No prompt template",
      unresolvedVersionLabel: "Live resolved version",
      blankVersionLabel: "Live resolved version",
    });
  });
  $("#open-emb-model-picker")?.addEventListener("click", () => {
    openEmbModelPicker().catch((error) => {
      showToast(`Embedding model picker failed: ${String(error)}`, "err");
      logConsole("embedding model picker failed", String(error));
    });
  });
  $("#apply-chat-model-picker")?.addEventListener("click", applyChatModelPickerSelection);
  $("#close-chat-model-picker")?.addEventListener("click", closeChatModelPicker);
  $("#cancel-chat-model-picker")?.addEventListener("click", closeChatModelPicker);
  $("#model-picker-search")?.addEventListener("input", (event) => {
    state.modelPickerQuery = String(event.currentTarget?.value || "");
    renderChatModelPicker();
  });
  $("#chat-model-picker-modal")?.addEventListener("click", (event) => {
    if (event.target?.dataset?.closeChatModelPicker === "true") {
      closeChatModelPicker();
    }
  });

  $("#embeddings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      model: data.get("model"),
      input: String(data.get("inputs") || "").split("\n").map((item) => item.trim()).filter(Boolean),
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/v1/embeddings", { method: "POST", body: JSON.stringify(body) }));
      const vectors = result?.data || [];
      renderMetricGrid("#embeddings-summary-grid", [
        { label: "Model", value: result?.model || "-" },
        { label: "Vectors Returned", value: String(vectors.length) },
        { label: "Dimensions", value: vectors[0]?.embedding ? String(vectors[0].embedding.length) : "-" },
        { label: "Tokens Used", value: result?.usage?.total_tokens != null ? String(result.usage.total_tokens) : "-" },
      ]);
      renderOutput("#embeddings-output", result);
      showToast("Embeddings generated.", "ok");
    } catch (error) {
      showToast(`Embeddings failed: ${String(error)}`, "err");
      logConsole("embeddings failed", String(error));
    }
  });

  $("#refresh-streaming-support").addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshStreamingSupport());
    } catch (error) {
      showToast(`Streaming support refresh failed: ${String(error)}`, "err");
      logConsole("streaming support refresh failed", String(error));
    }
  });
  $("#streaming-target-filter-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
  });
  $("#streaming-target-query")?.addEventListener("input", async (event) => {
    state.streamingSupportQuery = String(event.currentTarget.value || "");
    await refreshStreamingSupport();
  });
  $("#streaming-target-configured-only")?.addEventListener("change", async (event) => {
    state.streamingSupportConfiguredOnly = Boolean(event.currentTarget.checked);
    await refreshStreamingSupport();
  });
  $("#streaming-target-streamable-only")?.addEventListener("change", async (event) => {
    state.streamingSupportStreamableOnly = Boolean(event.currentTarget.checked);
    await refreshStreamingSupport();
  });
  $("#clear-streaming-target-filters")?.addEventListener("click", async () => {
    state.streamingSupportQuery = "";
    state.streamingSupportConfiguredOnly = false;
    state.streamingSupportStreamableOnly = false;
    const queryInput = $("#streaming-target-query");
    if (queryInput) queryInput.value = "";
    const configuredToggle = $("#streaming-target-configured-only");
    if (configuredToggle) configuredToggle.checked = false;
    const streamableToggle = $("#streaming-target-streamable-only");
    if (streamableToggle) streamableToggle.checked = false;
    await refreshStreamingSupport();
  });
  $("#governance-graph-filter-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
  });
  $("#governance-graph-query")?.addEventListener("input", async () => {
    rememberTableContext("#governance-graph", collectFormFilters("#governance-graph-filter-form"));
    refreshGovernanceGraphView();
  });
  $("#governance-graph-role")?.addEventListener("change", async () => {
    rememberTableContext("#governance-graph", collectFormFilters("#governance-graph-filter-form"));
    refreshGovernanceGraphView();
  });
  $("#governance-graph-status")?.addEventListener("change", async () => {
    rememberTableContext("#governance-graph", collectFormFilters("#governance-graph-filter-form"));
    refreshGovernanceGraphView();
  });
  $("#governance-graph-budgeted-only")?.addEventListener("change", async () => {
    rememberTableContext("#governance-graph", collectFormFilters("#governance-graph-filter-form"));
    refreshGovernanceGraphView();
  });
  $("#clear-governance-graph-filters")?.addEventListener("click", async () => {
    $("#governance-graph-filter-form")?.reset();
    rememberTableContext("#governance-graph", {});
    refreshGovernanceGraphView();
  });
  $("#integrations-graph-filter-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
  });
  $("#integrations-graph-query")?.addEventListener("input", async () => {
    rememberTableContext("#integrations-graph", collectFormFilters("#integrations-graph-filter-form"));
    refreshIntegrationGraphView();
  });
  $("#integrations-graph-protocol")?.addEventListener("change", async () => {
    rememberTableContext("#integrations-graph", collectFormFilters("#integrations-graph-filter-form"));
    refreshIntegrationGraphView();
  });
  $("#clear-integrations-graph-filters")?.addEventListener("click", async () => {
    $("#integrations-graph-filter-form")?.reset();
    rememberTableContext("#integrations-graph", {});
    refreshIntegrationGraphView();
  });
  $("#training-lifecycle-filter-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
  });
  $("#training-lifecycle-stage-mode")?.addEventListener("change", async () => {
    rememberTableContext("#training-lifecycle-graph", collectFormFilters("#training-lifecycle-filter-form"));
    refreshTrainingLifecycleView();
  });
  $("#training-lifecycle-hide-empty")?.addEventListener("change", async () => {
    rememberTableContext("#training-lifecycle-graph", collectFormFilters("#training-lifecycle-filter-form"));
    refreshTrainingLifecycleView();
  });
  $("#clear-training-lifecycle-filters")?.addEventListener("click", async () => {
    $("#training-lifecycle-filter-form")?.reset();
    rememberTableContext("#training-lifecycle-graph", {});
    refreshTrainingLifecycleView();
  });
  $("#refresh-provider-guides")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshProviderGuides());
    } catch (error) {
      showToast(`Provider guide refresh failed: ${String(error)}`, "err");
      logConsole("provider guides refresh failed", String(error));
    }
  });
  $("#refresh-provider-guides-secondary")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshProviderGuides());
    } catch (error) {
      showToast(`Provider guide refresh failed: ${String(error)}`, "err");
      logConsole("provider guides refresh failed", String(error));
    }
  });
  $("#refresh-mcp-servers").addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshMcpServers());
    } catch (error) {
      showToast(`MCP server refresh failed: ${String(error)}`, "err");
      logConsole("mcp server refresh failed", String(error));
    }
  });
  $("#refresh-mcp-servers-secondary")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshMcpServers());
    } catch (error) {
      showToast(`MCP server refresh failed: ${String(error)}`, "err");
      logConsole("mcp server refresh failed", String(error));
    }
  });
  $("#refresh-a2a-peers")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshA2APeers());
    } catch (error) {
      showToast(`A2A peer refresh failed: ${String(error)}`, "err");
      logConsole("a2a peer refresh failed", String(error));
    }
  });
  $("#refresh-a2a-peers-secondary")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshA2APeers());
    } catch (error) {
      showToast(`A2A peer refresh failed: ${String(error)}`, "err");
      logConsole("a2a peer refresh failed", String(error));
    }
  });
  $("#refresh-rest-endpoints")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshRestEndpoints());
    } catch (error) {
      showToast(`REST endpoint refresh failed: ${String(error)}`, "err");
      logConsole("rest endpoint refresh failed", String(error));
    }
  });
  $("#refresh-rest-endpoints-secondary")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshRestEndpoints());
    } catch (error) {
      showToast(`REST endpoint refresh failed: ${String(error)}`, "err");
      logConsole("rest endpoint refresh failed", String(error));
    }
  });
  $("#a2a-peer-invoke-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selectedPeer = currentSelectedA2APeer();
    if (!selectedPeer) {
      showToast("Select an A2A peer first.", "warn");
      return;
    }
    const data = new FormData(event.currentTarget);
    let inputPayload = {};
    try {
      inputPayload = parseJsonObject(data.get("input_json"), "A2A input");
    } catch (error) {
      showToast(`A2A invoke error: ${String(error)}`, "err");
      return;
    }
    try {
      const result = await withLoading(event.submitter, () => apiFetch(`/admin/api/a2a/peers/${encodeURIComponent(selectedPeer.peer)}/invoke`, {
        method: "POST",
        body: JSON.stringify({
          capability: String(data.get("capability") || "").trim(),
          input: inputPayload,
        }),
      }));
      renderOutput("#a2a-peer-output", result);
      inspectA2APeer(result, { rawLabel: "View raw invocation response" });
      showToast(`Invoked A2A peer ${selectedPeer.label || selectedPeer.peer}.`, "ok");
    } catch (error) {
      showToast(`A2A invoke failed: ${String(error)}`, "err");
      logConsole("a2a invoke failed", String(error));
    }
  });
  $("#validate-rest-endpoint")?.addEventListener("click", async (event) => {
    const selectedEndpoint = currentSelectedRestEndpoint();
    if (!selectedEndpoint) {
      showToast("Select a REST endpoint first.", "warn");
      return;
    }
    try {
      const result = await withLoading(event.currentTarget, () => apiFetch(`/admin/api/rest/endpoints/${encodeURIComponent(selectedEndpoint.endpoint_name)}/validate`, {
        method: "POST",
      }));
      renderOutput("#rest-endpoint-output", result);
      inspectRestEndpoint(result, { rawLabel: "View raw validation response" });
      showToast(`Validated REST endpoint ${selectedEndpoint.label || selectedEndpoint.endpoint_name}.`, "ok");
    } catch (error) {
      showToast(`REST validation failed: ${String(error)}`, "err");
      logConsole("rest validation failed", String(error));
    }
  });
  $("#rest-endpoint-invoke-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const selectedEndpoint = currentSelectedRestEndpoint();
    if (!selectedEndpoint) {
      showToast("Select a REST endpoint first.", "warn");
      return;
    }
    const data = new FormData(event.currentTarget);
    let inputPayload = {};
    try {
      inputPayload = parseJsonObject(data.get("input_json"), "REST input");
    } catch (error) {
      showToast(`REST invoke error: ${String(error)}`, "err");
      return;
    }
    try {
      const result = await withLoading(event.submitter, () => apiFetch(`/admin/api/rest/endpoints/${encodeURIComponent(selectedEndpoint.endpoint_name)}/invoke`, {
        method: "POST",
        body: JSON.stringify({
          method: String(data.get("method") || "").trim() || null,
          path: String(data.get("path") || "").trim() || null,
          input: inputPayload,
        }),
      }));
      renderOutput("#rest-endpoint-output", result);
      inspectRestEndpoint(result, { rawLabel: "View raw invocation response" });
      showToast(`Invoked REST endpoint ${selectedEndpoint.label || selectedEndpoint.endpoint_name}.`, "ok");
    } catch (error) {
      showToast(`REST invoke failed: ${String(error)}`, "err");
      logConsole("rest invoke failed", String(error));
    }
  });
  $("#streaming-validate-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const selectedTarget = currentStreamingSupportRow();
    if (!selectedTarget) {
      showToast("Select a stream target first.", "warn");
      return;
    }
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/admin/api/ops/streaming/validate", {
        method: "POST",
        body: JSON.stringify({
          provider_key: data.get("provider_key") || selectedTarget.provider_key || null,
          listener_id: data.get("listener_id") || null,
          requested_model: data.get("requested_model") || selectedTarget.model_id || "proxy-auto",
          execution_mode: data.get("execution_mode") || "training",
          validation_scope: data.get("validation_scope") || "default_only",
          target_filter: data.get("target_filter") || "all_streamable",
          max_concurrency: Number(data.get("max_concurrency") || 6),
          cache_ttl_seconds: Number(data.get("cache_ttl_seconds") || 900),
          use_cached_results: Boolean($("#streaming-use-cached-results")?.checked),
          owner_id: data.get("owner_id") || null,
          prompt: data.get("prompt") || "Say hello briefly.",
        }),
      }));
      showStreamingValidationResult(result);
      $("#streaming-validation-result-card")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      logConsole("streaming validation", result);
      showToast(
        result.success
          ? (result.validation_scope === "all_discovered"
              ? `Validated ${formattedValue(result.validated_count || 0)}/${formattedValue(result.target_count || 0)} discovered stream targets.`
              : (result.learning_pipeline_verified ? "Front-door streaming test and learning capture succeeded." : "Front-door streaming test succeeded."))
          : "Streaming validation returned an operator-visible failure.",
        result.success ? "ok" : "warn",
      );
    } catch (error) {
      showToast(`Streaming validation failed: ${String(error)}`, "err");
      logConsole("streaming validation failed", String(error));
    }
  });
  $("#streaming-target-filter")?.addEventListener("change", (event) => {
    const executionMode = String($("#streaming-execution-mode")?.value || "training");
    const ttlField = $("#streaming-cache-ttl-seconds");
    const useCached = $("#streaming-use-cached-results");
    const exhaustive = String(event.currentTarget.value || "") === "chat_capable_subset";
    if (ttlField && executionMode === "interactive" && exhaustive) {
      ttlField.value = "300";
    }
    if (useCached && executionMode !== "interactive") {
      useCached.checked = true;
    }
  });
  $("#model-monitor-provider-key")?.addEventListener("change", () => {
    renderModelMonitorProviderOptions();
  });
  $("#refresh-model-monitors")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshModelMonitors());
    } catch (error) {
      showToast(`Model monitor refresh failed: ${String(error)}`, "err");
      logConsole("model monitor refresh failed", String(error));
    }
  });
  $("#llm-timeseries-provider-key")?.addEventListener("change", async () => {
    renderLlmTimeseriesProviderOptions();
    rememberTableContext("#llm-timeseries-charts", collectFormFilters("#llm-timeseries-filter-form"));
    await refreshLlmTimeseries();
  });
  $("#llm-timeseries-model-id")?.addEventListener("change", async () => {
    rememberTableContext("#llm-timeseries-charts", collectFormFilters("#llm-timeseries-filter-form"));
    await refreshLlmTimeseries();
  });
  $("#llm-timeseries-window-hours")?.addEventListener("change", async () => {
    rememberTableContext("#llm-timeseries-charts", collectFormFilters("#llm-timeseries-filter-form"));
    await refreshLlmTimeseries();
  });
  $("#llm-timeseries-bucket-minutes")?.addEventListener("change", async () => {
    rememberTableContext("#llm-timeseries-charts", collectFormFilters("#llm-timeseries-filter-form"));
    await refreshLlmTimeseries();
  });
  $("#llm-timeseries-filter-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    rememberTableContext("#llm-timeseries-charts", collectFormFilters("#llm-timeseries-filter-form"));
    try {
      await withLoading(event.submitter, () => refreshLlmTimeseries(), "Refreshing…");
    } catch (error) {
      showToast(`LLM trend refresh failed: ${String(error)}`, "err");
      logConsole("llm trend refresh failed", String(error));
    }
  });
  $("#llm-timeseries-preset-picker")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-timeseries-preset]");
    if (!button) return;
    const presetKey = String(button.getAttribute("data-timeseries-preset") || "").trim().toLowerCase();
    const preset = llmTimeseriesMetricPresets[presetKey];
    if (!preset) return;
    persistLlmTimeseriesPreset(presetKey);
    persistLlmTimeseriesMetricSelection(preset.metrics);
    renderLlmTimeseriesPresetPicker();
    renderLlmTimeseriesMetricPicker();
    if (state.llmTimeseriesPayload) {
      renderLlmTimeseriesCharts(state.llmTimeseriesPayload);
    } else {
      await refreshLlmTimeseries();
    }
  });
  $("#llm-timeseries-metric-picker")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-metric-key]");
    if (!button) return;
    const metricKey = String(button.getAttribute("data-metric-key") || "").trim();
    if (!metricKey || !llmTimeseriesMetricDefinitions[metricKey]) return;
    const selected = new Set(selectedLlmTimeseriesMetrics());
    if (selected.has(metricKey)) {
      selected.delete(metricKey);
    } else {
      selected.add(metricKey);
    }
    persistLlmTimeseriesPreset("");
    persistLlmTimeseriesMetricSelection(Array.from(selected));
    renderLlmTimeseriesPresetPicker();
    renderLlmTimeseriesMetricPicker();
    if (state.llmTimeseriesPayload) {
      renderLlmTimeseriesCharts(state.llmTimeseriesPayload);
    } else {
      await refreshLlmTimeseries();
    }
  });
  $("#clear-llm-timeseries-filters")?.addEventListener("click", async () => {
    setFormFilters("#llm-timeseries-filter-form", {
      provider_key: readinessProviderModelOptions()?.[0]?.provider_key || "",
      model_id: "",
      window_hours: "168",
      bucket_minutes: "60",
      metric_preset: "",
      metrics: defaultLlmTimeseriesMetrics().join(","),
    });
    renderLlmTimeseriesProviderOptions();
    rememberTableContext("#llm-timeseries-charts", collectFormFilters("#llm-timeseries-filter-form"));
    await refreshLlmTimeseries();
  });
  $("#reset-model-monitor")?.addEventListener("click", () => {
    resetModelMonitorEditor();
  });
  $("#delete-model-monitor")?.addEventListener("click", async (event) => {
    const current = currentModelMonitor();
    if (!current) {
      showToast("Select a model monitor first.", "warn");
      return;
    }
    try {
      const remaining = (state.modelMonitorPayload?.monitors || []).filter((row) => row.monitor_id !== current.monitor_id);
      const result = await withLoading(event.currentTarget, () => apiFetch("/admin/api/config/model-monitors", {
        method: "POST",
        body: JSON.stringify({ monitors: remaining }),
      }));
      replaceModelMonitorPayload(result.monitors || []);
      resetModelMonitorEditor();
      showToast(`Deleted monitor for ${current.label || current.model_id}.`, "ok");
    } catch (error) {
      showToast(`Model monitor delete failed: ${String(error)}`, "err");
      logConsole("model monitor delete failed", String(error));
    }
  });
  $("#model-monitor-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = modelMonitorFormPayload();
    if (!payload.provider_key || !payload.model_id) {
      showToast("Choose a provider and model first.", "warn");
      return;
    }
    const currentRows = Array.isArray(state.modelMonitorPayload?.monitors) ? state.modelMonitorPayload.monitors : [];
    const nextRows = currentRows.filter((row) => row.monitor_id !== payload.monitor_id);
    nextRows.push({
      ...payload,
      monitor_id: payload.monitor_id || null,
      label: payload.label || payload.model_id,
    });
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/admin/api/config/model-monitors", {
        method: "POST",
        body: JSON.stringify({ monitors: nextRows }),
      }));
      replaceModelMonitorPayload(result.monitors || []);
      const saved = (result.monitors || []).find((row) => row.provider_key === payload.provider_key && row.model_id === payload.model_id)
        || (result.monitors || []).slice(-1)[0];
      if (saved) {
        inspectModelMonitor(saved);
      }
      showToast("Saved model monitor configuration.", "ok");
    } catch (error) {
      showToast(`Model monitor save failed: ${String(error)}`, "err");
      logConsole("model monitor save failed", String(error));
    }
  });

  $("#refresh-virtual-keys")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshVirtualKeys());
    } catch (error) {
      showToast(`Virtual key refresh failed: ${String(error)}`, "err");
      logConsole("virtual key refresh failed", String(error));
    }
  });
  $("#refresh-virtual-keys-secondary")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshVirtualKeys());
    } catch (error) {
      showToast(`Virtual key refresh failed: ${String(error)}`, "err");
      logConsole("virtual key refresh failed", String(error));
    }
  });
  $("#refresh-pricing")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshPricingCatalog());
    } catch (error) {
      showToast(`Pricing refresh failed: ${String(error)}`, "err");
      logConsole("pricing refresh failed", String(error));
    }
  });
  $("#refresh-pricing-secondary")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshPricingCatalog());
    } catch (error) {
      showToast(`Pricing refresh failed: ${String(error)}`, "err");
      logConsole("pricing refresh failed", String(error));
    }
  });
  $("#refresh-guardrails")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshGuardrails());
    } catch (error) {
      showToast(`Guardrail refresh failed: ${String(error)}`, "err");
      logConsole("guardrail refresh failed", String(error));
    }
  });
  $("#refresh-guardrails-secondary")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshGuardrails());
    } catch (error) {
      showToast(`Guardrail refresh failed: ${String(error)}`, "err");
      logConsole("guardrail refresh failed", String(error));
    }
  });
  $("#virtual-key-form-reset")?.addEventListener("click", () => {
    $("#virtual-key-form")?.reset();
    populateVirtualKeyForm();
  });
  $("#virtual-key-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const keyId = String(data.get("key_id") || "").trim();
    const body = {
      display_name: String(data.get("display_name") || "").trim() || null,
      owner_id: String(data.get("owner_id") || "").trim() || null,
      role: String(data.get("role") || "api").trim() || "api",
      models_allowed: csv(String(data.get("models_allowed") || "")),
      rpm_limit: String(data.get("rpm_limit") || "").trim() ? Number(data.get("rpm_limit")) : null,
      tpm_limit: String(data.get("tpm_limit") || "").trim() ? Number(data.get("tpm_limit")) : null,
      max_budget_usd: String(data.get("max_budget_usd") || "").trim() ? Number(data.get("max_budget_usd")) : null,
      budget_reset_period: String(data.get("budget_reset_period") || "").trim() || null,
      budget_reset_at: fromDatetimeLocalValue(data.get("budget_reset_at")),
      status: String(data.get("status") || "").trim() || null,
    };
    const method = keyId ? "PATCH" : "POST";
    const url = keyId ? `/admin/api/auth/virtual-keys/${encodeURIComponent(keyId)}` : "/admin/api/auth/virtual-keys";
    const payload = keyId ? body : Object.fromEntries(Object.entries(body).filter(([key]) => key !== "status"));
    try {
      const result = await withLoading(event.submitter, () => apiFetch(url, { method, body: JSON.stringify(payload) }));
      renderRecordView("#virtual-key-form-output", result, VIRTUAL_KEY_RECORD_FIELDS, { rawLabel: "View raw API response" });
      showToast(keyId ? "Virtual key updated." : "Virtual key issued.", "ok");
      if (!keyId && result.token) {
        showToast("Copy the new virtual key token now — it will not be shown again.", "warn");
      }
      populateVirtualKeyForm();
      await refreshVirtualKeys();
    } catch (error) {
      showToast(`Virtual key save failed: ${String(error)}`, "err");
      logConsole("virtual key save failed", String(error));
    }
  });

  $("#refresh-models").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshModels()); } catch (error) { showToast(`Models refresh failed: ${String(error)}`, "err"); logConsole("models refresh failed", String(error)); } });
  $("#refresh-local-models").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshLocalModels()); } catch (error) { showToast(`Local model refresh failed: ${String(error)}`, "err"); logConsole("local models refresh failed", String(error)); } });
  $("#refresh-policies").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshPolicies()); } catch (error) { showToast(`Policy refresh failed: ${String(error)}`, "err"); logConsole("policy refresh failed", String(error)); } });
  $("#routing-policy-filter-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
  });
  $("#routing-policy-query")?.addEventListener("input", async (event) => {
    state.routingPolicyQuery = String(event.currentTarget.value || "");
    await refreshPolicies();
  });
  $("#routing-policy-scoped-only")?.addEventListener("change", async (event) => {
    state.routingPolicyScopedOnly = Boolean(event.currentTarget.checked);
    await refreshPolicies();
  });
  $("#clear-routing-policy-filters")?.addEventListener("click", async () => {
    state.routingPolicyQuery = "";
    state.routingPolicyScopedOnly = false;
    const queryInput = $("#routing-policy-query");
    if (queryInput) queryInput.value = "";
    const scopedToggle = $("#routing-policy-scoped-only");
    if (scopedToggle) scopedToggle.checked = false;
    await refreshPolicies();
  });
  $("#foundation-open-provider-guide")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openFoundationProviderGuide(), "Opening…");
    } catch (error) {
      showToast(`Provider guide drill-down failed: ${String(error)}`, "err");
      logConsole("provider guide drill-down failed", String(error));
    }
  });
  $("#provider-guide-open-vendor")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openProviderGuideVendorContext(), "Opening…");
    } catch (error) {
      showToast(`Vendor workspace drill-down failed: ${String(error)}`, "err");
      logConsole("vendor workspace drill-down failed", String(error));
    }
  });
  $("#foundation-open-routing")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openFoundationRoutingContext(), "Opening…");
    } catch (error) {
      showToast(`Routing drill-down failed: ${String(error)}`, "err");
      logConsole("routing drill-down failed", String(error));
    }
  });
  $("#foundation-open-streaming")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openFoundationStreamingValidation(), "Opening…");
    } catch (error) {
      showToast(`Stream validation drill-down failed: ${String(error)}`, "err");
      logConsole("stream validation drill-down failed", String(error));
    }
  });
  $("#refresh-models-secondary")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshModels()); } catch (error) { showToast(`Models refresh failed: ${String(error)}`, "err"); logConsole("models refresh failed", String(error)); } });
  $("#foundation-visibility-scope")?.addEventListener("change", async (event) => {
    setFoundationModelVisibilityScope(String(event.currentTarget.value || "active"));
    try {
      await refreshModels();
    } catch (error) {
      showToast(`Model visibility refresh failed: ${String(error)}`, "err");
      logConsole("model visibility refresh failed", String(error));
    }
  });
  $("#refresh-local-models-secondary")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshLocalModels()); } catch (error) { showToast(`Local model refresh failed: ${String(error)}`, "err"); logConsole("local models refresh failed", String(error)); } });
  $("#refresh-local-runtime-status")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshLocalRuntimeStatus()); } catch (error) { showToast(`Runtime status refresh failed: ${String(error)}`, "err"); logConsole("local runtime refresh failed", String(error)); } });
  $("#reconcile-selected-runtime")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => runSelectedRuntimeReconcile(), "Reconciling…");
    } catch (error) {
      showToast(`Runtime reconcile failed: ${String(error)}`, "err");
      logConsole("runtime reconcile failed", String(error));
    }
  });
  $("#refresh-deployments")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDeployments()); } catch (error) { showToast(`Deployment inventory refresh failed: ${String(error)}`, "err"); logConsole("deployment inventory refresh failed", String(error)); } });
  $("#deployments-filter-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
  });
  $("#deployments-filter-query")?.addEventListener("input", async (event) => {
    state.deploymentInventoryQuery = String(event.currentTarget.value || "");
    await refreshDeployments();
  });
  $("#deployments-filter-stage")?.addEventListener("change", async (event) => {
    state.deploymentInventoryStage = String(event.currentTarget.value || "all");
    await refreshDeployments();
  });
  $("#clear-deployments-filters")?.addEventListener("click", async () => {
    state.deploymentInventoryQuery = "";
    state.deploymentInventoryStage = "all";
    const queryInput = $("#deployments-filter-query");
    if (queryInput) queryInput.value = "";
    const stageInput = $("#deployments-filter-stage");
    if (stageInput) stageInput.value = "all";
    await refreshDeployments();
  });
  $("#refresh-policies-secondary")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshPolicies()); } catch (error) { showToast(`Policy refresh failed: ${String(error)}`, "err"); logConsole("policy refresh failed", String(error)); } });
  $("#refresh-routing-nodes-secondary")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshPolicies(), "Refreshing…"); } catch (error) { showToast(`Node inventory refresh failed: ${String(error)}`, "err"); logConsole("node inventory refresh failed", String(error)); } });
  $("#refresh-routing-pools-secondary")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshPolicies(), "Refreshing…"); } catch (error) { showToast(`Pool inventory refresh failed: ${String(error)}`, "err"); logConsole("pool inventory refresh failed", String(error)); } });
  $("#refresh-prompts")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshPrompts());
    } catch (error) {
      showToast(`Prompt refresh failed: ${String(error)}`, "err");
      logConsole("prompt refresh failed", String(error));
    }
  });
  $("#refresh-prompts-secondary")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshPrompts());
    } catch (error) {
      showToast(`Prompt refresh failed: ${String(error)}`, "err");
      logConsole("prompt refresh failed", String(error));
    }
  });
  $("#prompt-compare-active")?.addEventListener("click", async (event) => {
    const detail = state.selectedPromptTemplateRecord;
    if (!detail?.name || !detail?.version) {
      showToast("Select a prompt version first.", "warn");
      return;
    }
    try {
      const result = await withLoading(
        event.currentTarget,
        () => apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}/comparison?compare_version=${encodeURIComponent(detail.version)}`),
        "Comparing…",
      );
      renderOutput("#prompt-rollout-output", result);
      showPromptComparisonResult(result);
    } catch (error) {
      showToast(`Prompt comparison failed: ${String(error)}`, "err");
      logConsole("prompt comparison failed", String(error));
    }
  });
  $("#prompt-start-canary")?.addEventListener("click", async (event) => {
    const detail = state.selectedPromptTemplateRecord;
    if (!detail?.name || !detail?.version) {
      showToast("Select a prompt version first.", "warn");
      return;
    }
    const trafficPercentage = Number($("#prompt-rollout-traffic-percentage")?.value || 10);
    try {
      const result = await withLoading(
        event.currentTarget,
        () => apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}/rollout`, {
          method: "POST",
          body: JSON.stringify({
            challenger_version: detail.version,
            mode: "canary",
            traffic_percentage: trafficPercentage,
          }),
        }),
        "Starting…",
      );
      renderOutput("#prompt-rollout-output", result);
      showToast(`Started ${formattedValue(trafficPercentage)}% prompt canary for ${detail.name} v${detail.version}.`, "ok");
      await refreshPrompts();
      const fresh = await apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}?version=${encodeURIComponent(detail.version)}`);
      inspectPromptTemplate(fresh);
    } catch (error) {
      showToast(`Prompt rollout failed: ${String(error)}`, "err");
      logConsole("prompt rollout failed", String(error));
    }
  });
  $("#prompt-stop-canary")?.addEventListener("click", async (event) => {
    const detail = state.selectedPromptTemplateRecord;
    if (!detail?.name) {
      showToast("Select a prompt family first.", "warn");
      return;
    }
    try {
      const result = await withLoading(
        event.currentTarget,
        () => apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}/rollout`, {
          method: "POST",
          body: JSON.stringify({ mode: "disabled" }),
        }),
        "Stopping…",
      );
      renderOutput("#prompt-rollout-output", result);
      showToast(`Stopped prompt canary for ${detail.name}.`, "ok");
      await refreshPrompts();
      const version = detail.version || detail.family_rollout?.active_version;
      if (version) {
        const fresh = await apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}?version=${encodeURIComponent(version)}`);
        inspectPromptTemplate(fresh);
      }
    } catch (error) {
      showToast(`Prompt rollout stop failed: ${String(error)}`, "err");
      logConsole("prompt rollout stop failed", String(error));
    }
  });
  $("#prompt-promote-challenger")?.addEventListener("click", async (event) => {
    const detail = state.selectedPromptTemplateRecord;
    if (!detail?.name || !detail?.version) {
      showToast("Select a challenger prompt version first.", "warn");
      return;
    }
    try {
      const result = await withLoading(
        event.currentTarget,
        () => apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}/promote-challenger?challenger_version=${encodeURIComponent(detail.version)}`, {
          method: "POST",
        }),
        "Promoting…",
      );
      renderOutput("#prompt-rollout-output", result);
      showToast(`Promoted ${detail.name} v${formattedValue(result.promoted_version)} to active.`, "ok");
      await refreshPrompts();
      const fresh = await apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}?version=${encodeURIComponent(result.promoted_version)}`);
      inspectPromptTemplate(fresh);
    } catch (error) {
      showToast(`Prompt promotion failed: ${String(error)}`, "err");
      logConsole("prompt promotion failed", String(error));
    }
  });
  $("#prompt-save-auto-promotion")?.addEventListener("click", async (event) => {
    const detail = state.selectedPromptTemplateRecord;
    if (!detail?.name) {
      showToast("Select a prompt family first.", "warn");
      return;
    }
    const form = $("#prompt-auto-promotion-form");
    const data = new FormData(form);
    const body = {
      enabled: String(data.get("enabled") || "false") === "true",
      minimum_challenger_requests: Number(data.get("minimum_challenger_requests") || 10),
      min_candidate_yield_improvement_pct: Number(data.get("min_candidate_yield_improvement_pct") || 2),
      max_error_rate_regression_pct: Number(data.get("max_error_rate_regression_pct") || 1),
      max_latency_regression_ms: Number(data.get("max_latency_regression_ms") || 250),
      max_cost_regression_usd: Number(data.get("max_cost_regression_usd") || 0.001),
    };
    try {
      const result = await withLoading(
        event.currentTarget,
        () => apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}/auto-promotion-policy`, {
          method: "POST",
          body: JSON.stringify(body),
        }),
        "Saving…",
      );
      renderOutput("#prompt-rollout-output", result);
      applyPromptAutoPromotionPolicyToForm(result.auto_promotion_policy);
      showToast(`Saved auto-promotion policy for ${detail.name}.`, "ok");
      await refreshPrompts();
      const version = detail.version || result.active_version || detail.family_rollout?.active_version;
      if (version) {
        const fresh = await apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}?version=${encodeURIComponent(version)}`);
        inspectPromptTemplate(fresh);
      }
    } catch (error) {
      showToast(`Auto-promotion policy save failed: ${String(error)}`, "err");
      logConsole("prompt auto-promotion policy save failed", String(error));
    }
  });
  $("#prompt-run-auto-promotion")?.addEventListener("click", async (event) => {
    const detail = state.selectedPromptTemplateRecord;
    if (!detail?.name) {
      showToast("Select a prompt family first.", "warn");
      return;
    }
    try {
      const result = await withLoading(
        event.currentTarget,
        () => apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}/auto-promotion/evaluate`, {
          method: "POST",
        }),
        "Evaluating…",
      );
      renderOutput("#prompt-rollout-output", result);
      showToast(result.executed ? `Auto-promotion executed for ${detail.name}.` : `Auto-promotion check completed for ${detail.name}.`, result.executed ? "ok" : "warn");
      await refreshPrompts();
      const familyVersion = result.promotion?.promoted_version || detail.version || result.family_rollout?.active_version;
      if (familyVersion) {
        const fresh = await apiFetch(`/admin/api/prompts/${encodeURIComponent(detail.name)}?version=${encodeURIComponent(familyVersion)}`);
        inspectPromptTemplate(fresh);
      }
    } catch (error) {
      showToast(`Auto-promotion check failed: ${String(error)}`, "err");
      logConsole("prompt auto-promotion check failed", String(error));
    }
  });

  $("#model-register-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      model_registry_id: data.get("model_registry_id"),
      model_alias: data.get("model_alias"),
      base_model: data.get("base_model"),
      adapter_type: data.get("adapter_type"),
      adapter_path: data.get("adapter_path"),
      runtime: data.get("runtime"),
      endpoint_url: data.get("endpoint_url"),
      domains: csv(String(data.get("domains") || "")),
      task_types: csv(String(data.get("task_types") || "")),
      quality: { promotion_status: data.get("status") || "approved" },
      status: data.get("status") || "approved",
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/proxy/models/register", { method: "POST", body: JSON.stringify(body) }));
      renderOutput("#model-register-output", result);
      showToast("Model registered.", "ok");
      await refreshLocalModels();
    } catch (error) {
      showToast(`Model registration failed: ${String(error)}`, "err");
      logConsole("model register failed", String(error));
    }
  });

  $("#vendor-model-register-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      provider_key: String(data.get("provider_key") || "").trim(),
      model_id: String(data.get("model_id") || "").trim(),
      domains: csv(String(data.get("domains") || "")),
      task_types: csv(String(data.get("task_types") || "")),
      tags: csv(String(data.get("tags") || "")),
      labels: csv(String(data.get("tags") || "")),
      regions: csv(String(data.get("regions") || "")),
      deployment_mode: String(data.get("deployment_mode") || "production"),
      canary_percent: 0,
      endpoint_url: String(data.get("endpoint_url") || "").trim() || null,
      fallback_chain: [],
      decision_rationale: "Onboarded from Models > Onboard vendor LLM workflow.",
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/deployment/routing-policies/frontier", { method: "POST", body: JSON.stringify(body) }));
      renderOutput("#vendor-model-register-output", result);
      showToast("Vendor LLM registered.", "ok");
      await Promise.all([refreshPolicies(), refreshModels()]);
    } catch (error) {
      showToast(`Vendor LLM registration failed: ${String(error)}`, "err");
      logConsole("vendor llm register failed", String(error));
    }
  });

  $("#local-runtime-config-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      const result = await withLoading(event.submitter, async () => {
        const envFile = ".env.local";
        const updates = [];
        const pairs = [
          ["LLMPROXY_OLLAMA_BASE_URL", String(data.get("ollama_base_url") || "").trim()],
          ["LLMPROXY_VLLM_BASE_URL", String(data.get("vllm_base_url") || "").trim()],
          ["LLMPROXY_LLAMA_CPP_BASE_URL", String(data.get("llama_cpp_base_url") || "").trim()],
          ["LLMPROXY_MLX_BASE_URL", String(data.get("mlx_base_url") || "").trim()],
        ];
        for (const [key, value] of pairs) {
          updates.push(await apiFetch("/admin/api/config/set", {
            method: "POST",
            body: JSON.stringify({ key, value, env_file: envFile }),
          }));
        }
        return { updated: true, env_file: envFile, updates };
      });
      renderOutput("#local-runtime-config-output", result);
      showToast("Local runtime endpoints saved.", "ok");
      await refreshLocalRuntimeStatus();
    } catch (error) {
      showToast(`Runtime endpoint save failed: ${String(error)}`, "err");
      logConsole("local runtime config save failed", String(error));
    }
  });

  $("#open-register-routing")?.addEventListener("click", () => {
    switchSubview("models", "routing");
  });

  $("#open-register-deploy")?.addEventListener("click", () => {
    switchSubview("models", "deploy");
  });

  $("#open-onboard-vendor-routing")?.addEventListener("click", () => {
    switchSubview("models", "routing");
  });

  $("#open-onboard-custom-runtime")?.addEventListener("click", () => {
    switchCollection("modelRegister", "runtime");
  });

  $("#open-onboard-custom-deploy")?.addEventListener("click", () => {
    switchSubview("models", "deploy");
  });

  $("#open-training-workbench")?.addEventListener("click", () => {
    switchSubview("training", "workbench");
  });
  $("#open-training-lifecycle-stage")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openTrainingLifecycleStageContext(), "Opening…");
    } catch (error) {
      showToast(`Lifecycle drill-down failed: ${String(error)}`, "err");
      logConsole("training lifecycle drill-down failed", String(error));
    }
  });
  $("#open-operations-topology-artifact")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openOperationsTopologyContext(currentSelectedOperationsTopologyArtifact()), "Opening…");
    } catch (error) {
      showToast(`Topology drill-down failed: ${String(error)}`, "err");
      logConsole("operations topology drill-down failed", String(error));
    }
  });
  $("#open-routing-graph-artifact")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openRoutingGraphContext(currentSelectedRoutingGraphArtifact()), "Opening…");
    } catch (error) {
      showToast(`Routing graph drill-down failed: ${String(error)}`, "err");
      logConsole("routing graph drill-down failed", String(error));
    }
  });
  $("#open-deployment-graph-artifact")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openDeploymentGraphContext(currentSelectedDeploymentGraphArtifact()), "Opening…");
    } catch (error) {
      showToast(`Deployment graph drill-down failed: ${String(error)}`, "err");
      logConsole("deployment graph drill-down failed", String(error));
    }
  });
  $("#open-integrations-graph-artifact")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openIntegrationGraphContext(currentSelectedIntegrationsGraphArtifact()), "Opening…");
    } catch (error) {
      showToast(`Integration graph drill-down failed: ${String(error)}`, "err");
      logConsole("integration graph drill-down failed", String(error));
    }
  });
  $("#open-governance-graph-artifact")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openGovernanceGraphContext(currentSelectedGovernanceGraphArtifact()), "Opening…");
    } catch (error) {
      showToast(`Governance graph drill-down failed: ${String(error)}`, "err");
      logConsole("governance graph drill-down failed", String(error));
    }
  });

  $("#frontier-policy-reset")?.addEventListener("click", () => {
    $("#frontier-policy-form")?.reset();
    setFieldValue("#frontier-policy-form", "entry_id", "");
    setFieldValue("#frontier-policy-form", "requested_models", "");
    setFieldValue("#frontier-policy-form", "deployment_mode", "production");
    setFieldValue("#frontier-policy-form", "canary_percent", "0.0");
    setFieldValue("#frontier-policy-form", "pool_weight", "1.0");
    setFieldValue("#frontier-policy-form", "balancing_strategy", "");
    setFieldValue("#frontier-policy-form", "affinity_key", "");
    setFieldValue("#frontier-policy-form", "supports_local_models", false);
    setFieldValue("#frontier-policy-form", "supports_training", false);
    setFieldValue("#frontier-policy-form", "forward_request_metadata", false);
  });

  $("#frontier-policy-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      entry_id: data.get("entry_id") || null,
      provider_key: data.get("provider_key"),
      model_id: data.get("model_id"),
      requested_models: csv(String(data.get("requested_models") || "")),
      domains: csv(String(data.get("domains") || "")),
      task_types: csv(String(data.get("task_types") || "")),
      tags: csv(String(data.get("tags") || "")),
      labels: csv(String(data.get("labels") || "")),
      regions: csv(String(data.get("regions") || "")),
      listener_ids: csv(String(data.get("listener_ids") || "")),
      deployment_mode: data.get("deployment_mode"),
      canary_percent: Number(data.get("canary_percent") || 0),
      endpoint_url: String(data.get("endpoint_url") || "").trim() || null,
      node_id: String(data.get("node_id") || "").trim() || null,
      node_role: String(data.get("node_role") || "").trim() || null,
      capacity_class: String(data.get("capacity_class") || "").trim() || null,
      node_labels: csv(String(data.get("node_labels") || "")),
      pool_id: String(data.get("pool_id") || "").trim() || null,
      pool_weight: Number(data.get("pool_weight") || 1),
      balancing_strategy: String(data.get("balancing_strategy") || "").trim() || null,
      affinity_key: String(data.get("affinity_key") || "").trim() || null,
      supports_local_models: data.get("supports_local_models") === "on",
      supports_training: data.get("supports_training") === "on",
      forward_request_metadata: data.get("forward_request_metadata") === "on",
      fallback_chain: parseFallbackChain(String(data.get("fallback_chain") || "")),
      decision_rationale: String(data.get("decision_rationale") || "").trim() || null,
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/deployment/routing-policies/frontier", { method: "POST", body: JSON.stringify(body) }));
      renderOutput("#frontier-policy-output", result);
      showToast(body.entry_id ? "Frontier policy entry updated." : "Frontier policy entry created.", "ok");
      await refreshPolicies();
    } catch (error) {
      showToast(`Frontier policy update failed: ${String(error)}`, "err");
      logConsole("frontier policy update failed", String(error));
    }
  });

  $("#routing-settings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const data = new FormData(event.currentTarget);
    let frontierDefaultEntries = [];
    try {
      frontierDefaultEntries = validateRoutingDefaultEntries(
        JSON.parse(String(data.get("frontier_default_entries") || "[]")),
      );
    } catch (error) {
      showToast(`Routing defaults invalid: ${String(error)}`, "err");
      renderOutput("#routing-settings-output", { saved: false, error: String(error) });
      return;
    }
    const body = {
      routing_strategy: String(data.get("routing_strategy") || "balanced"),
      frontier_default_entries: frontierDefaultEntries,
      env_file: String(data.get("env_file") || ".env.local"),
    };
    try {
      const result = await withLoading(submitter, () => apiFetch("/admin/api/routing/settings", { method: "POST", body: JSON.stringify(body) }));
      renderOutput("#routing-settings-output", result);
      showToast("Routing settings saved to env file.", "ok");
      await refreshConfig();
    } catch (error) {
      showToast(`Routing settings update failed: ${String(error)}`, "err");
      logConsole("routing settings update failed", String(error));
    }
  });

  $("#deploy-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const data = new FormData(event.currentTarget);
    const modelAlias = data.get("model_alias");
    try {
      if (submitter.dataset.mode === "rollback") {
        if (!window.confirm(`Roll back deployment for ${modelAlias}? This will affect live traffic.`)) {
          return;
        }
        const result = await withLoading(submitter, () => apiFetch(`/deployment/models/${modelAlias}/rollback`, { method: "POST" }));
        renderOutput("#deploy-output", result);
        showToast(`Deployment rolled back for ${modelAlias}.`, "warn");
        await Promise.all([refreshPolicies(), refreshDeployments()]);
        return;
      }
      const body = {
        deployment_mode: data.get("deployment_mode"),
        domains: csv(String(data.get("domains") || "")),
        task_types: csv(String(data.get("task_types") || "")),
        canary_percent: Number(data.get("canary_percent") || 0),
      };
      const result = await withLoading(submitter, () => apiFetch(`/deployment/models/${modelAlias}/activate`, { method: "POST", body: JSON.stringify(body) }));
      renderOutput("#deploy-output", result);
      showToast(`Deployment activated for ${modelAlias}.`, "ok");
      await Promise.all([refreshPolicies(), refreshDeployments()]);
    } catch (error) {
      showToast(`Deployment action failed: ${String(error)}`, "err");
      logConsole("deployment action failed", String(error));
    }
  });

  $("#automation-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const data = new FormData(event.currentTarget);
    const checkbox = document.querySelector('#automation-form [name="auto_deploy_approved_evaluations"]');
    const autoDeployEnabled = checkbox?.checked ? "true" : "false";
    try {
      const results = await withLoading(submitter, async () => {
        const first = await apiFetch("/admin/api/config/set", {
          method: "POST",
          body: JSON.stringify({
            key: "LLMPROXY_AUTO_DEPLOY_APPROVED_EVALUATIONS",
            value: autoDeployEnabled,
          }),
        });
        const second = await apiFetch("/admin/api/config/set", {
          method: "POST",
          body: JSON.stringify({
            key: "LLMPROXY_AUTO_DEPLOY_DEPLOYMENT_MODE",
            value: String(data.get("auto_deploy_deployment_mode") || "production"),
          }),
        });
        return { auto_deploy: first, deployment_mode: second };
      });
      renderOutput("#automation-output", results);
      showToast("Automation settings saved to env file.", "ok");
      await refreshConfig();
    } catch (error) {
      showToast(`Automation settings update failed: ${String(error)}`, "err");
      logConsole("automation settings update failed", String(error));
    }
  });

  $("#replicate-prediction-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const data = new FormData(event.currentTarget);
    let inputPayload = {};
    try {
      inputPayload = JSON.parse(String(data.get("input_json") || "{}"));
    } catch {
      showToast("Replicate input JSON is invalid.", "err");
      return;
    }
    const body = {
      model: data.get("model"),
      input: inputPayload,
      wait_for_completion: Boolean(document.querySelector('#replicate-prediction-form [name="wait_for_completion"]')?.checked),
    };
    try {
      const result = await withLoading(submitter, () => apiFetch(
        submitter.dataset.mode === "validate"
          ? "/admin/api/replicate/predictions/validate"
          : "/admin/api/replicate/predictions",
        { method: "POST", body: JSON.stringify(body) },
      ));
      renderInteractionTraceTable(
        "#replicate-interaction-trace-table",
        submitter.dataset.mode === "validate" ? result?.interaction_traces || [] : [],
        "No normalized interaction trace recorded for this validation call yet.",
      );
      renderOutput("#replicate-prediction-output", result);
      showToast(submitter.dataset.mode === "validate" ? "Replicate validation completed." : "Replicate prediction job queued.", "ok");
      if (submitter.dataset.mode !== "validate") {
        await refreshJobs();
      }
    } catch (error) {
      showToast(`Replicate action failed: ${String(error)}`, "err");
      logConsole("replicate action failed", String(error));
    }
  });

  $("#prompt-template-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      name: String(data.get("name") || "").trim(),
      description: String(data.get("description") || "").trim() || null,
      model_override: String(data.get("model_override") || "").trim() || null,
      status: String(data.get("status") || "").trim() || null,
      variables: csv(String(data.get("variables") || "")),
      template_text: String(data.get("template_text") || ""),
      metadata: {},
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/admin/api/prompts", { method: "POST", body: JSON.stringify(body) }));
      renderRecordView("#prompt-template-output", result, PROMPT_TEMPLATE_RECORD_FIELDS, { rawLabel: "View raw save response" });
      inspectPromptTemplate(result);
      showToast(`Prompt template saved as ${result.name} v${result.version}.`, "ok");
      await refreshPrompts();
    } catch (error) {
      showToast(`Prompt template save failed: ${String(error)}`, "err");
      logConsole("prompt template save failed", String(error));
    }
  });

  $("#refresh-candidates").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDatasetPipeline()); } catch (error) { showToast(`Candidates refresh failed: ${String(error)}`, "err"); logConsole("candidates refresh failed", String(error)); } });
  $("#refresh-candidates-secondary")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDatasetPipeline()); } catch (error) { showToast(`Candidates refresh failed: ${String(error)}`, "err"); logConsole("candidates refresh failed", String(error)); } });
  $("#refresh-exports").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDatasetPipeline()); } catch (error) { showToast(`Exports refresh failed: ${String(error)}`, "err"); logConsole("exports refresh failed", String(error)); } });
  $("#refresh-dataset-imports").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDatasetPipeline()); } catch (error) { showToast(`Dataset refresh failed: ${String(error)}`, "err"); logConsole("dataset imports refresh failed", String(error)); } });
  $("#refresh-dataset-versions").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDatasetPipeline()); } catch (error) { showToast(`Dataset refresh failed: ${String(error)}`, "err"); logConsole("dataset versions refresh failed", String(error)); } });
  $("#candidates-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    rememberTableContext("#candidates-table", collectFormFilters("#candidates-filter-form"));
    resetTablePage("#candidates-table");
    await refreshDatasetPipeline();
  });
  $("#candidates-prompt-template-name")?.addEventListener("change", () => {
    renderPromptTemplatePicker("#candidates-prompt-template-name", "#candidates-prompt-template-version", {
      blankNameLabel: "Any prompt template",
      unresolvedVersionLabel: "Choose template first",
      blankVersionLabel: "All versions for template",
    });
  });
  $("#clear-candidates-filters")?.addEventListener("click", async () => {
    const form = $("#candidates-filter-form");
    form?.reset();
    renderAllPromptTemplatePickers();
    rememberTableContext("#candidates-table", {});
    resetTablePage("#candidates-table");
    await refreshDatasetPipeline();
  });
  $("#exports-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    rememberTableContext("#exports-table", collectFormFilters("#exports-filter-form"));
    resetTablePage("#exports-table");
    await refreshDatasetPipeline();
  });
  $("#exports-prompt-template-name")?.addEventListener("change", () => {
    renderPromptTemplatePicker("#exports-prompt-template-name", "#exports-prompt-template-version", {
      blankNameLabel: "Any prompt template",
      unresolvedVersionLabel: "Choose template first",
      blankVersionLabel: "All versions for template",
    });
  });
  $("#dataset-imports-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    rememberTableContext("#dataset-imports-table", collectFormFilters("#dataset-imports-filter-form"));
    resetTablePage("#dataset-imports-table");
    await refreshDatasetPipeline();
  });
  $("#dataset-versions-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    rememberTableContext("#dataset-versions-table", collectFormFilters("#dataset-versions-filter-form"));
    resetTablePage("#dataset-versions-table");
    await refreshDatasetPipeline();
  });

  $("#export-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      domain: data.get("domain"),
      name: data.get("name") || null,
      min_quality_score: Number(data.get("min_quality_score") || 0),
      interaction_protocol: data.get("interaction_protocol") || null,
      interaction_operation: data.get("interaction_operation") || null,
      interaction_outcome: data.get("interaction_outcome") || null,
      prompt_template_name: data.get("prompt_template_name") || null,
      prompt_template_version: data.get("prompt_template_version") ? Number(data.get("prompt_template_version")) : null,
      prompt_template_selection_mode: data.get("prompt_template_selection_mode") || null,
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/proxy/export/jsonl", { method: "POST", body: JSON.stringify(body) }));
      switchCollection("data", "exports");
      inspectExport(result);
      showToast("Dataset export created.", "ok");
      await refreshDatasetPipeline();
    } catch (error) {
      showToast(`Export failed: ${String(error)}`, "err");
      logConsole("export failed", String(error));
    }
  });
  $("#export-prompt-template-name")?.addEventListener("change", () => {
    renderPromptTemplatePicker("#export-prompt-template-name", "#export-prompt-template-version", {
      blankNameLabel: "Any prompt template",
      unresolvedVersionLabel: "Choose template first",
      blankVersionLabel: "All versions for template",
    });
  });

  $("#dataset-import-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = Object.fromEntries(data.entries());
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/datasets/import", { method: "POST", body: JSON.stringify(body) }));
      switchCollection("data", "datasets");
      inspectDatasetRecord(result, "import");
      logConsole("dataset import", result);
      showToast("Dataset import submitted.", "ok");
      await refreshDatasetPipeline();
    } catch (error) {
      showToast(`Dataset import failed: ${String(error)}`, "err");
      logConsole("dataset import failed", String(error));
    }
  });

  $("#training-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = getTrainingFormBody();
    try {
      const preflight = await runTrainingPreflight(event.submitter, { quietSuccess: true });
      if (!preflight.ready) {
        showToast("Training submission blocked by preflight checks.", "warn");
        return;
      }
      const result = await withLoading(event.submitter, () => apiFetch("/training/runs", { method: "POST", body: JSON.stringify(body) }));
      switchCollection("training", "runs");
      await inspectTrainingRun(result.training_run_id || result.id);
      showToast("Training run submitted.", "ok");
      await Promise.all([refreshDatasetPipeline(), refreshTrainingRuns()]);
    } catch (error) {
      showToast(`Training submission failed: ${String(error)}`, "err");
      logConsole("training submission failed", String(error));
    }
  });
  $("#training-preflight-button")?.addEventListener("click", async (event) => {
    try {
      await runTrainingPreflight(event.currentTarget);
    } catch (error) {
      logConsole("training preflight failed", String(error));
    }
  });
  $("#refresh-training").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshTrainingRuns()); } catch (error) { showToast(`Training refresh failed: ${String(error)}`, "err"); logConsole("training refresh failed", String(error)); } });
  $("#training-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    rememberTableContext("#training-table", collectFormFilters("#training-filter-form"));
    resetTablePage("#training-table");
    await refreshTrainingRuns();
  });
  $("#refresh-evaluations").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshEvaluations()); } catch (error) { showToast(`Evaluation refresh failed: ${String(error)}`, "err"); logConsole("evaluation refresh failed", String(error)); } });
  $("#refresh-kpis").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshKpis()); } catch (error) { showToast(`KPI refresh failed: ${String(error)}`, "err"); logConsole("kpi refresh failed", String(error)); } });
  $("#refresh-kpis-secondary")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshKpis()); } catch (error) { showToast(`KPI refresh failed: ${String(error)}`, "err"); logConsole("kpi refresh failed", String(error)); } });
  $("#refresh-training-runtime")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshTrainingRuntimeStatus()); showToast("Training runtime refreshed.", "ok"); } catch (error) { showToast(`Training runtime refresh failed: ${String(error)}`, "err"); logConsole("training runtime refresh failed", String(error)); } });
  $("#refresh-training-studio")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshTrainingStudioStatus()); showToast("Training studio refreshed.", "ok"); } catch (error) { showToast(`Training studio refresh failed: ${String(error)}`, "err"); logConsole("training studio refresh failed", String(error)); } });
  $("#evaluation-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    rememberTableContext("#evaluation-table", collectFormFilters("#evaluation-filter-form"));
    resetTablePage("#evaluation-table");
    await refreshEvaluations();
  });

  $("#evaluation-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      training_run_id: data.get("training_run_id"),
      frontier_baseline_name: data.get("frontier_baseline_name") || null,
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/evaluation/runs", { method: "POST", body: JSON.stringify(body) }));
      switchCollection("training", "evaluations");
      await inspectEvaluation(result.id);
      showToast("Evaluation submitted.", "ok");
      await refreshEvaluations();
    } catch (error) {
      showToast(`Evaluation failed: ${String(error)}`, "err");
      logConsole("evaluation failed", String(error));
    }
  });

  $("#refresh-jobs").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshJobs()); } catch (error) { showToast(`Jobs refresh failed: ${String(error)}`, "err"); logConsole("jobs refresh failed", String(error)); } });
  $("#refresh-events").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshEvents()); } catch (error) { showToast(`Events refresh failed: ${String(error)}`, "err"); logConsole("events refresh failed", String(error)); } });
  $("#jobs-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    rememberTableContext("#jobs-table", collectFormFilters("#jobs-filter-form"));
    resetTablePage("#jobs-table");
    await refreshJobs();
  });
  $("#events-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    rememberTableContext("#events-table", collectFormFilters("#events-filter-form"));
    resetTablePage("#events-table");
    await refreshEvents();
  });
  $("#refresh-ops-summary").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshOperationsSummary()); } catch (error) { showToast(`Operations summary failed: ${String(error)}`, "err"); logConsole("ops summary refresh failed", String(error)); } });
  $("#refresh-ops-live").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => Promise.all([refreshOperationsLive(), refreshOperationalEvents()])); } catch (error) { showToast(`Operations live refresh failed: ${String(error)}`, "err"); logConsole("ops live refresh failed", String(error)); } });
  $("#refresh-operations-topology")?.addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshOperationsTopology()); } catch (error) { showToast(`Topology refresh failed: ${String(error)}`, "err"); logConsole("operations topology refresh failed", String(error)); } });
  $("#refresh-observability")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshObservability());
    } catch (error) {
      showToast(`Observability refresh failed: ${String(error)}`, "err");
      logConsole("observability refresh failed", String(error));
    }
  });
  $("#ops-events-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await applyOperationalEventFilters({ resetPage: true });
  });
  $("#clear-ops-events-filters").addEventListener("click", async (event) => {
    $("#ops-events-filter-form").reset();
    renderOpsEventTrafficFilterOptions();
    renderOpsEventTrafficScopeVisibility();
    rememberTableContext("#ops-events-table", {});
    resetTablePage("#ops-events-table");
    await withLoading(event.currentTarget, () => refreshOperationalEvents());
  });
  $("#ops-events-selected-provider")?.addEventListener("change", async () => {
    renderOpsEventTrafficFilterOptions();
    try {
      await applyOperationalEventFilters({ resetPage: true });
    } catch (error) {
      showToast(`Event filter failed: ${String(error)}`, "err");
      logConsole("ops event provider filter failed", String(error));
    }
  });
  $("#ops-events-selected-model")?.addEventListener("change", async () => {
    try {
      await applyOperationalEventFilters({ resetPage: true });
    } catch (error) {
      showToast(`Event filter failed: ${String(error)}`, "err");
      logConsole("ops event model filter failed", String(error));
    }
  });
  ["#ops-events-selected-pool", "#ops-events-selected-node", "#ops-events-traffic-origin", "#ops-events-automation-scope"].forEach((selector) => {
    $(selector)?.addEventListener("change", async () => {
      try {
        await applyOperationalEventFilters({ resetPage: true });
      } catch (error) {
        showToast(`Event filter failed: ${String(error)}`, "err");
        logConsole("ops event traffic selector filter failed", String(error));
      }
    });
  });
  $("#ops-events-prompt-template-name")?.addEventListener("change", async () => {
    renderPromptTemplatePicker("#ops-events-prompt-template-name", "#ops-events-prompt-template-version", {
      blankNameLabel: "Any prompt template",
      unresolvedVersionLabel: "Choose template first",
      blankVersionLabel: "All versions for template",
    });
    try {
      await applyOperationalEventFilters({ resetPage: true });
    } catch (error) {
      showToast(`Event filter failed: ${String(error)}`, "err");
      logConsole("ops event prompt filter failed", String(error));
    }
  });
  ["#ops-events-prompt-template-version", "#ops-events-prompt-selection-mode"].forEach((selector) => {
    $(selector)?.addEventListener("change", async () => {
      try {
        await applyOperationalEventFilters({ resetPage: true });
      } catch (error) {
        showToast(`Event filter failed: ${String(error)}`, "err");
        logConsole("ops event prompt filter failed", String(error));
      }
    });
  });
  $$("#ops-events-filter-form select").forEach((field) => {
    if (["ops-events-selected-provider", "ops-events-selected-model", "ops-events-selected-pool", "ops-events-selected-node", "ops-events-traffic-origin", "ops-events-automation-scope"].includes(field.id)) return;
    field.addEventListener("change", async () => {
      try {
        await applyOperationalEventFilters({ resetPage: true });
      } catch (error) {
        showToast(`Event filter failed: ${String(error)}`, "err");
        logConsole("ops event select filter failed", String(error));
      }
    });
  });
  $("#ops-promote-candidate")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => promoteSelectedOpsEvent());
    } catch (error) {
      showToast(`Event promotion failed: ${String(error)}`, "err");
      logConsole("ops event promotion failed", String(error));
    }
  });
  $("#ops-open-export-draft")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openExportDraftFromOpsEvent());
    } catch (error) {
      showToast(`Export draft seeding failed: ${String(error)}`, "err");
      logConsole("ops export draft failed", String(error));
    }
  });
  $("#ops-preset-errors")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => applyOpsPreset("errors"));
    } catch (error) {
      showToast(`Preset failed: ${String(error)}`, "err");
      logConsole("ops preset errors failed", String(error));
    }
  });
  $("#ops-preset-traffic")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => applyOpsPreset("traffic"));
    } catch (error) {
      showToast(`Preset failed: ${String(error)}`, "err");
      logConsole("ops preset traffic failed", String(error));
    }
  });
  $("#ops-preset-audit")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => applyOpsPreset("audit"));
    } catch (error) {
      showToast(`Preset failed: ${String(error)}`, "err");
      logConsole("ops preset audit failed", String(error));
    }
  });
  $("#ops-preset-training")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => applyOpsPreset("training"));
    } catch (error) {
      showToast(`Preset failed: ${String(error)}`, "err");
      logConsole("ops preset training failed", String(error));
    }
  });
  $("#ops-preset-listener")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => applyOpsPreset("listener"));
    } catch (error) {
      showToast(`Preset failed: ${String(error)}`, "err");
      logConsole("ops preset listener failed", String(error));
    }
  });
  $("#ops-columns-adaptive")?.addEventListener("click", async () => {
    setOpsEventColumnPreset("adaptive");
    renderOpsColumnPresetControls();
    await refreshOperationalEvents();
  });
  $("#ops-columns-events")?.addEventListener("click", async () => {
    setOpsEventColumnPreset("events");
    renderOpsColumnPresetControls();
    await refreshOperationalEvents();
  });
  $("#ops-columns-traffic")?.addEventListener("click", async () => {
    setOpsEventColumnPreset("traffic");
    renderOpsColumnPresetControls();
    await refreshOperationalEvents();
  });
  Object.keys(opsSavedPresetDefinitions).forEach((slot) => {
    $(`#ops-load-saved-${slot}`)?.addEventListener("click", async () => {
      await loadSavedOpsPreset(slot);
    });
  });
  $("#ops-save-current-preset")?.addEventListener("click", () => {
    const slot = $("#ops-save-preset-slot")?.value || "traffic";
    saveCurrentOpsPreset(slot);
    renderSavedOpsPresetControls();
    renderOpsActiveViewStrip();
    showToast(`Saved current event filters into ${humanizeLabel(slot)}.`, "ok");
  });
  $("#open-runtime-event-directory")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => openCanonicalRuntimeEventDirectory());
    } catch (error) {
      showToast(`Unable to open event directory: ${String(error)}`, "err");
      logConsole("open runtime event directory failed", String(error));
    }
  });
  $("#run-worker-once").addEventListener("click", async (event) => {
    try {
      const result = await withLoading(event.currentTarget, () => apiFetch("/admin/api/jobs/run-once", { method: "POST" }));
      logConsole("worker run once", result);
      showToast("Worker iteration executed.", "ok");
      await refreshJobs();
    } catch (error) {
      showToast(`Worker run failed: ${String(error)}`, "err");
      logConsole("worker run once failed", String(error));
    }
  });
  $("#run-scheduler-once").addEventListener("click", async (event) => {
    try {
      const result = await withLoading(event.currentTarget, () => apiFetch("/admin/api/scheduler/run-once", { method: "POST" }));
      logConsole("scheduler run once", result);
      showToast("Scheduler iteration executed.", "ok");
      await refreshEvents();
      await refreshJobs();
    } catch (error) {
      showToast(`Scheduler run failed: ${String(error)}`, "err");
      logConsole("scheduler run once failed", String(error));
    }
  });
  $("#process-events").addEventListener("click", async (event) => {
    try {
      const result = await withLoading(event.currentTarget, () => apiFetch("/admin/api/events/process", { method: "POST" }));
      logConsole("events process", result);
      showToast("Pending events processed.", "ok");
      await refreshEvents();
      await refreshJobs();
    } catch (error) {
      showToast(`Event processing failed: ${String(error)}`, "err");
      logConsole("events process failed", String(error));
    }
  });

  try {
    if (state.token) {
      await ensurePanelLoaded("overview");
      setStatus("Connected", "ok");
    }
  } catch (error) {
    setStatus("Token Required", "err");
    showToast(`Initial load failed: ${String(error)}`, "err");
    logConsole("initial load failed", String(error));
  }
}

window.addEventListener("DOMContentLoaded", () => {
  initialize().catch((error) => {
    setStatus("Initialization Failed", "err");
    showToast(`Initialization failed: ${String(error)}`, "err");
    logConsole("fatal init error", String(error));
  });
});

window.setInterval(() => {
  if (!state.token || state.activePanel !== "operations") {
    return;
  }
  refreshOperationsLive().catch((error) => logConsole("operations auto-refresh failed", String(error)));
}, 5000);
