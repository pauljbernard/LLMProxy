const state = {
  token: localStorage.getItem("llmproxy.admin.token") || "",
  activePanel: "overview",
  opsPollTimer: null,
  loadedPanels: new Set(),
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

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

function showToast(message, tone = "info") {
  const region = $("#toast-region");
  if (!region) return;
  const toast = document.createElement("div");
  toast.className = `toast ${tone}`;
  toast.textContent = message;
  region.appendChild(toast);
  window.setTimeout(() => {
    toast.remove();
  }, 3500);
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
  return events;
}

function renderOutput(selector, payload) {
  $(selector).textContent = JSON.stringify(payload, null, 2);
}

function renderMetricGrid(selector, items) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  const entries = items.filter((item) => item && item.label);
  if (!entries.length) {
    host.innerHTML = '<div class="empty-state"><strong>No metrics available.</strong>Metrics will appear here when data is available.</div>';
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

function renderKeyValueTable(selector, rows, { emptyMessage = "No values available.", allowEdit = false } = {}) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
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
    }, emptyMessage),
  );
}

function showDetailCard(cardSelector, outputSelector, payload) {
  const card = $(cardSelector);
  if (card) {
    card.classList.remove("hidden");
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  renderOutput(outputSelector, payload);
}

function statusBadge(value) {
  const map = {
    connected: ["ok", "Connected"],
    configured: ["ok", "Configured"],
    completed: ["ok", "Completed"],
    approved: ["ok", "Approved"],
    running: ["info", "Running"],
    active: ["info", "Active"],
    processing: ["info", "Processing"],
    pending: ["warn", "Pending"],
    queued: ["warn", "Queued"],
    unprocessed: ["warn", "Unprocessed"],
    failed: ["err", "Failed"],
    rejected: ["err", "Rejected"],
    canceled: ["err", "Canceled"],
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
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function timeLabel(isoString) {
  if (!isoString) return "-";
  return `<span title="${escapeHtml(isoString)}">${escapeHtml(relativeTime(isoString))}</span>`;
}

function setFieldValue(formSelector, name, value) {
  const field = document.querySelector(`${formSelector} [name="${name}"]`);
  if (field) {
    field.value = value ?? "";
  }
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
  renderMetricGrid("#pipeline-summary", [
    { label: "Candidates", value: String(candidates.length), subvalue: "Traffic captured for review" },
    { label: "Exports", value: String(exports.length), subvalue: "Curated training datasets" },
    { label: "Imports", value: String(imports.length), subvalue: "Ingestion attempts" },
    { label: "Versions", value: String(versions.length), subvalue: "Versioned dataset snapshots" },
    { label: "Training", value: String(training.length), subvalue: "Model adaptation runs" },
  ]);
}

function csv(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
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

function makeTable(columns, rows, rowRenderer, emptyMessage = "No records available yet.") {
  const table = document.createElement("table");
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
    td.innerHTML = `<div class="empty-state"><strong>No data yet.</strong>${escapeHtml(emptyMessage)}</div>`;
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    rows.forEach((row) => tbody.appendChild(rowRenderer(row)));
  }
  table.appendChild(tbody);
  return table;
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

function switchPanel(panel) {
  state.activePanel = panel;
  $$(".panel").forEach((node) => node.classList.toggle("active", node.dataset.panel === panel));
  $$(".nav-link").forEach((node) => node.classList.toggle("active", node.dataset.panel === panel));
  if (state.token) {
    ensurePanelLoaded(panel).catch((error) => {
      showToast(`Failed to load ${panel}: ${String(error)}`, "err");
      logConsole(`${panel} load failed`, String(error));
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
    await Promise.all([refreshRequests(), refreshStreamingSupport()]);
  },
  models: async () => {
    await Promise.all([refreshModels(), refreshLocalModels(), refreshPolicies()]);
  },
  data: async () => {
    await refreshDatasetPipeline();
  },
  training: async () => {
    await Promise.all([refreshTrainingRuns(), refreshEvaluations(), refreshKpis()]);
  },
  operations: async () => {
    await Promise.all([refreshOperationsSummary(), refreshOperationsLive(), refreshJobs(), refreshEvents()]);
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

async function refreshHealth() {
  const payload = await apiFetch("/health");
  renderMetricGrid("#health-status-grid", Object.entries(payload.provider_families_configured || {}).map(([key, configured]) => ({
    label: humanizeLabel(key),
    badge: boolBadge(configured),
    subvalue: configured ? "Configured" : "Not configured",
  })));
  renderKeyValueTable("#health-meta-table", [
    { key: "Status", value: payload.status },
    { key: "Environment", value: payload.environment },
    { key: "Database Backend", value: payload.database_backend },
    { key: "Redis Configured", value: payload.redis_configured ? "Yes" : "No" },
    { key: "Logs Path", value: payload.logs_path },
  ]);
  return payload;
}

async function refreshConfig() {
  const payload = await apiFetch("/admin/api/config");
  renderMetricGrid("#config-provider-grid", Object.entries(payload.provider_configuration || {}).map(([key, configured]) => ({
    label: humanizeLabel(key),
    badge: boolBadge(configured),
    subvalue: configured ? "Ready" : "Missing config",
  })));
  const rows = Object.entries(payload)
    .filter(([key]) => key !== "provider_configuration")
    .map(([key, value]) => ({ key, value: typeof value === "object" ? JSON.stringify(value) : String(value ?? "") }));
  renderKeyValueTable("#config-table", rows, {
    emptyMessage: "Configuration values will appear here once loaded.",
    allowEdit: true,
  });
  return payload;
}

async function validateConfig() {
  const payload = await apiFetch("/admin/api/config/validate");
  logConsole("config validate", payload);
}

async function refreshRequests(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && params.set(key, value));
  const payload = await apiFetch(`/admin/api/proxy/requests?${params.toString()}`);
  const host = $("#requests-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Request", "Domain", "Task", "Mode", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.id}</strong><br/><span>${row.session_id}</span></td>
        <td>${statusBadge(row.domain || "muted").replace("badge-muted", "badge-info")}</td>
        <td>${row.task_type || "-"}</td>
        <td>${row.requested_model}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          const detail = await apiFetch(`/admin/api/proxy/requests/${row.id}`);
          showDetailCard("#request-detail-card", "#request-detail-output", detail);
        }, { accent: true }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Requests will appear here after traffic flows through the proxy."),
  );
}

async function refreshStreamingSupport() {
  const payload = await apiFetch("/admin/api/proxy/streaming-support");
  const host = $("#streaming-support-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Provider", "Model", "Configured", "Streaming", "Family"], payload.providers, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.provider_name}</strong></td>
        <td>${row.model_id}</td>
        <td>${boolBadge(row.configured)}</td>
        <td>${boolBadge(row.supports_streaming)}</td>
        <td>${row.provider_family}</td>
      `;
      return tr;
    }, "Provider streaming support will render here once configuration is loaded."),
  );
  renderOutput("#streaming-support-output", payload);
  return payload;
}

async function refreshModels() {
  const payload = await apiFetch("/v1/models");
  const host = $("#models-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Model", "Type", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.id)}</strong></td>
        <td>${escapeHtml(row.object || "model")}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => showDetailCard("#model-detail-card", "#model-detail-output", row), { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Proxy-exposed models will appear here."),
  );
  return payload;
}

async function refreshLocalModels() {
  const payload = await apiFetch("/models/local");
  const host = $("#local-models-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Alias", "Base Model", "Domains", "Status", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.model_alias)}</strong></td>
        <td>${escapeHtml(row.base_model)}</td>
        <td>${escapeHtml((row.domains || []).join(", ") || "-")}</td>
        <td>${statusBadge(row.promotion_status || "-")}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => showDetailCard("#model-detail-card", "#model-detail-output", row), { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Registered local packages will appear here."),
  );
  return payload;
}

async function refreshPolicies() {
  const payload = await apiFetch("/deployment/routing-policies");
  const rows = payload.flatMap((policyVersion) => {
    const entries = Array.isArray(policyVersion.policy?.entries) ? policyVersion.policy.entries : [];
    if (!entries.length) {
      return [{
        policy_version: policyVersion.policy_version,
        domain: "-",
        mode: "-",
        provider: "-",
        canary_percent: 0,
        detail: policyVersion,
      }];
    }
    return entries.map((entry) => ({
      policy_version: policyVersion.policy_version,
      domain: entry.domain || "-",
      mode: entry.mode || "-",
      provider: entry.provider || "-",
      canary_percent: entry.canary_percent ?? 0,
      detail: { policy_version: policyVersion.policy_version, entry },
    }));
  });
  const host = $("#policies-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Version", "Domain", "Mode", "Provider", "Canary", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.policy_version)}</strong></td>
        <td>${escapeHtml(row.domain)}</td>
        <td>${escapeHtml(row.mode)}</td>
        <td>${escapeHtml(row.provider)}</td>
        <td>${escapeHtml(String(row.canary_percent))}%</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => showDetailCard("#model-detail-card", "#model-detail-output", row.detail), { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Routing policies will appear here as versions are published."),
  );
  return payload;
}

async function refreshCandidates() {
  const payload = await apiFetch("/proxy/training-candidates");
  const host = $("#candidates-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Candidate", "Domain", "Status", "Score", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.id}</strong><br/><span>${row.task_type}</span></td>
        <td>${row.domain}</td>
        <td>${statusBadge(row.approval_status)}</td>
        <td>${row.quality_score}</td>
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
    }, "Traffic will begin generating candidates automatically."),
  );
  return payload;
}

async function refreshExports() {
  const data = new FormData($("#exports-filter-form"));
  const params = new URLSearchParams();
  Object.entries(Object.fromEntries(data.entries())).forEach(([key, value]) => value && params.set(key, value));
  const payload = await apiFetch(`/admin/api/exports?${params.toString()}`);
  const host = $("#exports-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Export", "Domain", "Records", "Created", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.dataset_export_id}</strong><br/><span>${row.id}</span></td>
        <td>${row.domain || "-"}</td>
        <td>${row.record_count}</td>
        <td>${timeLabel(row.created_at)}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => renderOutput("#exports-output", row), { accent: true }));
      actions.appendChild(
        createActionButton("Use for Import", () => {
          setFieldValue("#dataset-import-form", "dataset_export_id", row.dataset_export_id);
          setFieldValue("#dataset-import-form", "manifest_path", row.manifest_path);
          setFieldValue("#dataset-import-form", "data_path", row.data_path);
          logConsole("dataset import form filled", row);
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Create a dataset export to move approved candidates into the learner pipeline."),
  );
  renderOutput("#exports-output", payload);
  return payload;
}

async function refreshDatasetImports() {
  const data = new FormData($("#dataset-imports-filter-form"));
  const params = new URLSearchParams();
  Object.entries(Object.fromEntries(data.entries())).forEach(([key, value]) => value && params.set(key, value));
  const payload = await apiFetch(`/admin/api/datasets/imports?${params.toString()}`);
  const host = $("#dataset-imports-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Import", "Export", "Status", "Records", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.id}</strong></td>
        <td>${row.dataset_export_id}</td>
        <td>${statusBadge(row.status)}</td>
        <td>${row.record_count}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => renderOutput("#dataset-output", row), { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Imported datasets will appear here after processing completes."),
  );
  return payload;
}

async function refreshDatasetVersions() {
  const data = new FormData($("#dataset-versions-filter-form"));
  const params = new URLSearchParams();
  Object.entries(Object.fromEntries(data.entries())).forEach(([key, value]) => value && params.set(key, value));
  const payload = await apiFetch(`/admin/api/datasets/versions?${params.toString()}`);
  const host = $("#dataset-versions-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Version", "Domain", "Records", "Source", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.version_name}</strong><br/><span>${row.id}</span></td>
        <td>${row.domain}</td>
        <td>${row.record_count}</td>
        <td>${row.source_import_id || "-"}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => renderOutput("#dataset-output", row), { accent: true }));
      actions.appendChild(
        createActionButton("Train", () => {
          setFieldValue("#training-form", "dataset_version_id", row.id);
          logConsole("training form filled from dataset version", row);
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Dataset versions are created after imports are normalized and staged."),
  );
  return payload;
}

async function refreshDatasetViews() {
  const imports = await refreshDatasetImports();
  const versions = await refreshDatasetVersions();
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
  const data = new FormData($("#training-filter-form"));
  const filters = Object.fromEntries(data.entries());
  const payload = applyClientFilters(await apiFetch("/training/runs"), filters);
  const host = $("#training-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Run", "Dataset", "Mode", "Status", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.id}</strong><br/><span>${row.base_model}</span></td>
        <td>${row.dataset_version_id}</td>
        <td>${row.training_mode}</td>
        <td>${statusBadge(row.status)}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          showDetailCard("#training-detail-card", "#training-detail-output", await apiFetch(`/admin/api/training/runs/${row.id}`));
        }, { accent: true }),
      );
      actions.appendChild(
        createActionButton("Evaluate", () => {
          setFieldValue("#evaluation-form", "training_run_id", row.id);
          logConsole("evaluation form filled from training run", row);
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Submit a training run to begin adapter creation for a dataset version."),
  );
  return payload;
}

async function refreshEvaluations() {
  const data = new FormData($("#evaluation-filter-form"));
  const filters = Object.fromEntries(data.entries());
  const payload = applyClientFilters(await apiFetch("/evaluation/runs"), filters);
  const host = $("#evaluation-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Evaluation", "Domain", "Score", "Promotion", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.id}</strong><br/><span>${row.training_run_id}</span></td>
        <td>${row.domain || "-"}</td>
        <td>${row.overall_score ?? "-"}</td>
        <td>${statusBadge(row.promotion_status || "-")}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          const detail = await apiFetch(`/admin/api/evaluation/runs/${row.id}`);
          showDetailCard("#evaluation-detail-card", "#evaluation-detail-output", detail);
        }, { accent: true }),
      );
      actions.appendChild(
        createActionButton("Prepare Deploy", async () => {
          const detail = await apiFetch(`/admin/api/evaluation/runs/${row.id}`);
          const manifestPath = detail.result_json?.package_manifest_path || row.package_manifest_path || "";
          const alias = detail.result_json?.model_alias || deriveAliasFromManifest(manifestPath);
          setFieldValue("#deploy-form", "model_alias", alias);
          showDetailCard("#evaluation-detail-card", "#evaluation-detail-output", detail);
          logConsole("deployment form prepared from evaluation", { evaluation_run_id: row.id, model_alias: alias, manifest_path: manifestPath });
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Evaluation runs will appear here once training outputs are scored."),
  );
  return payload;
}

async function refreshKpis() {
  const payload = await apiFetch("/evaluation/kpis");
  renderMetricGrid("#kpi-metrics-grid", [
    { label: "Requests", value: String(payload.request_count ?? 0) },
    { label: "Recent Errors", value: String(payload.recent_error_count ?? 0) },
    { label: "Recent Audit", value: String(payload.recent_audit_count ?? 0) },
    { label: "Latest Request", value: payload.latest_request_id || "-", subvalue: "Most recent request id" },
  ]);
  renderKeyValueTable(
    "#kpi-output",
    Object.entries(payload).map(([key, value]) => ({ key: humanizeLabel(key), value: typeof value === "object" ? JSON.stringify(value) : String(value ?? "") })),
    { emptyMessage: "KPI values will appear here once generated." },
  );
  return payload;
}

function renderLogTable(selector, rows) {
  const host = $(selector);
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Time", "Level", "Component", "Message", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${timeLabel(row.timestamp)}</td>
        <td>${statusBadge(row.level || "-")}</td>
        <td>${row.component || "-"}</td>
        <td>${row.message || "-"}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", () => renderOutput("#ops-detail-output", row), { accent: true }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "No records match the current filter."),
  );
}

async function refreshOperationsSummary() {
  const summary = await apiFetch("/admin/api/ops/summary");
  const metrics = await apiFetch("/metrics");
  renderMetricGrid("#ops-summary-grid", [
    { label: "Requests", value: String(summary.request_count ?? 0) },
    { label: "Recent Errors", value: String(summary.recent_error_count ?? 0) },
    { label: "Recent Audit", value: String(summary.recent_audit_count ?? 0) },
    { label: "Latest Request", value: summary.latest_request_id || "-", subvalue: "Most recent request id" },
    { label: "Latest Eval", value: summary.latest_evaluation_run_id || "-", subvalue: "Most recent evaluation run" },
  ]);
  renderMetricGrid("#ops-metrics-grid", [
    { label: "Jobs", value: String(Object.values(metrics.job_counts || {}).reduce((sum, value) => sum + Number(value || 0), 0)) },
    { label: "Events", value: String(Object.values(metrics.event_counts || {}).reduce((sum, value) => sum + Number(value || 0), 0)) },
    { label: "Routes", value: String(Object.keys(metrics.route_counts || {}).length) },
    { label: "Configured Providers", value: String(Object.values(metrics.provider_configuration || {}).filter(Boolean).length) },
  ]);
  renderMetricGrid("#ops-stream-grid", [
    { label: "Stream Starts", value: String(summary.streaming?.stream_start_count ?? 0) },
    { label: "Stream Complete", value: String(summary.streaming?.stream_complete_count ?? 0) },
    { label: "Stream Failed", value: String(summary.streaming?.stream_failed_count ?? 0) },
  ]);
  renderLogTable("#ops-stream-live-table", (summary.streaming && summary.streaming.recent_stream_summaries) || []);
  return { summary, metrics };
}

async function refreshOperationsLogs() {
  const payload = await apiFetch(`/admin/api/ops/logs?${toQueryString("#ops-logs-filter-form")}`);
  renderLogTable("#ops-logs-table", payload);
  return payload;
}

async function refreshOperationsErrors() {
  const payload = await apiFetch(`/admin/api/ops/errors?${toQueryString("#ops-errors-filter-form")}`);
  renderLogTable("#ops-errors-table", payload);
  return payload;
}

async function refreshOperationsAudit() {
  const payload = await apiFetch(`/admin/api/ops/audit?${toQueryString("#ops-audit-filter-form")}`);
  renderLogTable("#ops-audit-table", payload);
  return payload;
}

async function refreshOperationsLive() {
  const payload = await apiFetch("/admin/api/ops/live");
  renderOutput("#ops-live-output", payload);
  renderMetricGrid("#ops-summary-grid", [
    { label: "Requests", value: String(payload.summary?.request_count ?? 0) },
    { label: "Recent Errors", value: String(payload.summary?.recent_error_count ?? 0) },
    { label: "Recent Audit", value: String(payload.summary?.recent_audit_count ?? 0) },
  ]);
  renderMetricGrid("#ops-stream-grid", [
    { label: "Stream Starts", value: String(payload.summary?.streaming?.stream_start_count ?? 0) },
    { label: "Stream Complete", value: String(payload.summary?.streaming?.stream_complete_count ?? 0) },
    { label: "Stream Failed", value: String(payload.summary?.streaming?.stream_failed_count ?? 0) },
  ]);
  renderLogTable("#ops-stream-live-table", (payload.summary?.streaming && payload.summary.streaming.recent_stream_summaries) || []);
  renderLogTable("#ops-logs-table", payload.logs);
  renderLogTable("#ops-errors-table", payload.errors);
  renderLogTable("#ops-audit-table", payload.audit);
  return payload;
}

async function refreshJobs() {
  const data = new FormData($("#jobs-filter-form"));
  const params = new URLSearchParams();
  Object.entries(Object.fromEntries(data.entries())).forEach(([key, value]) => value && params.set(key, value));
  const payload = await apiFetch(`/admin/api/jobs?${params.toString()}`);
  const host = $("#jobs-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Job", "Status", "Attempts", "Type", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.id}</strong></td>
        <td>${statusBadge(row.status)}</td>
        <td>${row.attempts}/${row.max_attempts}</td>
        <td>${row.job_type}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          showDetailCard("#job-detail-card", "#job-detail-output", await apiFetch(`/admin/api/jobs/${row.id}`));
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
    }, "Queued and running jobs will appear here."),
  );
}

async function refreshEvents() {
  const data = new FormData($("#events-filter-form"));
  const entries = Object.fromEntries(data.entries());
  const params = new URLSearchParams();
  Object.entries(entries).forEach(([key, value]) => {
    if (!value) return;
    params.set(key, value);
  });
  const payload = await apiFetch(`/admin/api/events?${params.toString()}`);
  const host = $("#events-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Event", "Type", "Source", "Processed", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.id}</strong></td>
        <td>${row.event_type}</td>
        <td>${row.source}</td>
        <td>${row.processed_at ? timeLabel(row.processed_at) : statusBadge("pending")}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          showDetailCard("#event-detail-card", "#event-detail-output", await apiFetch(`/admin/api/events/${row.id}`));
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
    }, "Runtime events will appear here as the outbox processes work."),
  );
}

async function initialize() {
  $("#token-input").value = state.token;
  enhanceFormLabels();

  $$(".nav-link").forEach((button) => {
    button.addEventListener("click", () => switchPanel(button.dataset.panel));
  });

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

  $("#chat-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const data = new FormData(event.currentTarget);
    const wantsStream = data.get("stream") === "on";
    const body = {
      model: data.get("model"),
      stream: wantsStream,
      temperature: Number(data.get("temperature")),
      max_tokens: Number(data.get("max_tokens")),
      metadata: {
        session_id: data.get("session_id"),
        domain_hint: data.get("domain_hint") || null,
        task_type_hint: data.get("task_type_hint") || null,
      },
      messages: parseMessages(String(data.get("messages") || "")),
    };
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
      await refreshRequests();
    } catch (error) {
      showToast(`Proxy request failed: ${String(error)}`, "err");
      logConsole(`proxy ${submitter.dataset.mode} failed`, String(error));
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
      renderOutput("#embeddings-output", result);
      showToast("Embeddings generated.", "ok");
    } catch (error) {
      showToast(`Embeddings failed: ${String(error)}`, "err");
      logConsole("embeddings failed", String(error));
    }
  });

  $("#request-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await refreshRequests(Object.fromEntries(data.entries()));
  });
  $("#refresh-requests").addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshRequests());
    } catch (error) {
      showToast(`Request refresh failed: ${String(error)}`, "err");
      logConsole("requests refresh failed", String(error));
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
  $("#streaming-validate-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/admin/api/ops/streaming/validate", {
        method: "POST",
        body: JSON.stringify({
          provider_key: data.get("provider_key") || null,
          prompt: data.get("prompt") || "Say hello briefly.",
        }),
      }));
      renderOutput("#streaming-support-output", result);
      logConsole("streaming validation", result);
      showToast(result.success ? "Streaming validation succeeded." : "Streaming validation returned an operator-visible failure.", result.success ? "ok" : "warn");
    } catch (error) {
      showToast(`Streaming validation failed: ${String(error)}`, "err");
      logConsole("streaming validation failed", String(error));
    }
  });

  $("#refresh-models").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshModels()); } catch (error) { showToast(`Models refresh failed: ${String(error)}`, "err"); logConsole("models refresh failed", String(error)); } });
  $("#refresh-local-models").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshLocalModels()); } catch (error) { showToast(`Local model refresh failed: ${String(error)}`, "err"); logConsole("local models refresh failed", String(error)); } });
  $("#refresh-policies").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshPolicies()); } catch (error) { showToast(`Policy refresh failed: ${String(error)}`, "err"); logConsole("policy refresh failed", String(error)); } });

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
        await refreshPolicies();
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
      await refreshPolicies();
    } catch (error) {
      showToast(`Deployment action failed: ${String(error)}`, "err");
      logConsole("deployment action failed", String(error));
    }
  });

  $("#refresh-candidates").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDatasetPipeline()); } catch (error) { showToast(`Candidates refresh failed: ${String(error)}`, "err"); logConsole("candidates refresh failed", String(error)); } });
  $("#refresh-exports").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDatasetPipeline()); } catch (error) { showToast(`Exports refresh failed: ${String(error)}`, "err"); logConsole("exports refresh failed", String(error)); } });
  $("#refresh-dataset-imports").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDatasetPipeline()); } catch (error) { showToast(`Dataset refresh failed: ${String(error)}`, "err"); logConsole("dataset imports refresh failed", String(error)); } });
  $("#refresh-dataset-versions").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshDatasetPipeline()); } catch (error) { showToast(`Dataset refresh failed: ${String(error)}`, "err"); logConsole("dataset versions refresh failed", String(error)); } });
  $("#exports-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshDatasetPipeline();
  });
  $("#dataset-imports-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshDatasetPipeline();
  });
  $("#dataset-versions-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshDatasetPipeline();
  });

  $("#export-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      domain: data.get("domain"),
      name: data.get("name") || null,
      min_quality_score: Number(data.get("min_quality_score") || 0),
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/proxy/export/jsonl", { method: "POST", body: JSON.stringify(body) }));
      renderOutput("#exports-output", result);
      showToast("Dataset export created.", "ok");
      await refreshDatasetPipeline();
    } catch (error) {
      showToast(`Export failed: ${String(error)}`, "err");
      logConsole("export failed", String(error));
    }
  });

  $("#dataset-import-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = Object.fromEntries(data.entries());
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/datasets/import", { method: "POST", body: JSON.stringify(body) }));
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
    const data = new FormData(event.currentTarget);
    const body = {
      dataset_version_id: data.get("dataset_version_id"),
      base_model: data.get("base_model"),
      training_mode: data.get("training_mode"),
      epochs: Number(data.get("epochs") || 3),
      learning_rate: Number(data.get("learning_rate") || 0.0002),
      adapter_name: data.get("adapter_name") || null,
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/training/runs", { method: "POST", body: JSON.stringify(body) }));
      showDetailCard("#training-detail-card", "#training-detail-output", result);
      showToast("Training run submitted.", "ok");
      await Promise.all([refreshDatasetPipeline(), refreshTrainingRuns()]);
    } catch (error) {
      showToast(`Training submission failed: ${String(error)}`, "err");
      logConsole("training submission failed", String(error));
    }
  });
  $("#refresh-training").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshTrainingRuns()); } catch (error) { showToast(`Training refresh failed: ${String(error)}`, "err"); logConsole("training refresh failed", String(error)); } });
  $("#training-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshTrainingRuns();
  });
  $("#refresh-evaluations").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshEvaluations()); } catch (error) { showToast(`Evaluation refresh failed: ${String(error)}`, "err"); logConsole("evaluation refresh failed", String(error)); } });
  $("#refresh-kpis").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshKpis()); } catch (error) { showToast(`KPI refresh failed: ${String(error)}`, "err"); logConsole("kpi refresh failed", String(error)); } });
  $("#evaluation-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
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
      showDetailCard("#evaluation-detail-card", "#evaluation-detail-output", result);
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
    await refreshJobs();
  });
  $("#events-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshEvents();
  });
  $("#refresh-ops-summary").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshOperationsSummary()); } catch (error) { showToast(`Operations summary failed: ${String(error)}`, "err"); logConsole("ops summary refresh failed", String(error)); } });
  $("#refresh-ops-live").addEventListener("click", async (event) => { try { await withLoading(event.currentTarget, () => refreshOperationsLive()); } catch (error) { showToast(`Operations live refresh failed: ${String(error)}`, "err"); logConsole("ops live refresh failed", String(error)); } });
  $("#ops-logs-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshOperationsLogs();
  });
  $("#ops-errors-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshOperationsErrors();
  });
  $("#ops-audit-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshOperationsAudit();
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
