const state = {
  token: localStorage.getItem("llmproxy.admin.token") || "",
  activePanel: "overview",
  opsPollTimer: null,
  loadedPanels: new Set(),
  lastRoutePreview: null,
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

function clearHost(selector) {
  const host = $(selector);
  if (host) {
    host.innerHTML = "";
  }
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

function renderSimpleTable(selector, title, columns, rows, rowRenderer, emptyMessage) {
  const host = $(selector);
  if (!host) return;
  host.innerHTML = "";
  if (title) {
    const heading = document.createElement("h4");
    heading.textContent = title;
    host.appendChild(heading);
  }
  host.appendChild(makeTable(columns, rows, rowRenderer, emptyMessage));
}

function formattedValue(value) {
  if (value == null || value === "") return "-";
  if (Array.isArray(value)) return value.join(", ") || "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function renderRequestDetail(payload) {
  const request = payload?.request || {};
  renderMetricGrid("#request-detail-summary-grid", [
    { label: "Request", value: request.id || "-" },
    { label: "Domain", value: request.domain || "-", subvalue: request.task_type || "No task type" },
    { label: "Model", value: request.requested_model || "-" },
    { label: "Success", value: request.successful ? "Yes" : "No" },
    { label: "Candidates", value: String((payload?.training_candidates || []).length) },
    { label: "Responses", value: String((payload?.model_responses || []).length) },
  ]);
  renderKeyValueTable("#request-detail-summary-table", [
    { key: "Session", value: formattedValue(request.session_id) },
    { key: "Route Type", value: formattedValue(request.route_type) },
    { key: "Quality Score", value: formattedValue(request.quality_score) },
    { key: "Cost Estimate", value: formattedValue(request.cost_estimate) },
    { key: "Created", value: formattedValue(request.created_at) },
  ]);
  renderSimpleTable(
    "#request-routing-table",
    "Routing Decisions",
    ["Provider", "Model", "Mode", "Latency", "Why"],
    payload?.routing_decisions || [],
    (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.selected_provider || "-")}</strong></td>
        <td>${escapeHtml(row.selected_model || "-")}</td>
        <td>${escapeHtml(row.selected_mode || "-")}</td>
        <td>${escapeHtml(formattedValue(row.predicted_latency_class))}</td>
        <td>${escapeHtml(row.decision_rationale || "-")}</td>
      `;
      return tr;
    },
    "No routing decisions recorded for this request.",
  );
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
}

function renderTrainingDetail(payload) {
  renderMetricGrid("#training-detail-summary-grid", [
    { label: "Run", value: payload?.id || "-" },
    { label: "Status", badge: statusBadge(payload?.status || "-") },
    { label: "Mode", value: payload?.training_mode || "-" },
    { label: "Base Model", value: payload?.base_model || "-" },
    { label: "Started", value: formattedValue(payload?.started_at) },
    { label: "Completed", value: formattedValue(payload?.completed_at) },
  ]);
  renderKeyValueTable("#training-detail-summary-table", [
    { key: "Dataset Version", value: formattedValue(payload?.dataset_version_id) },
    { key: "Artifact Path", value: formattedValue(payload?.artifact_path) },
    { key: "Status", value: formattedValue(payload?.status) },
  ]);
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
}

function renderEvaluationDetail(payload) {
  renderMetricGrid("#evaluation-detail-summary-grid", [
    { label: "Evaluation", value: payload?.id || "-" },
    { label: "Status", badge: statusBadge(payload?.status || "-") },
    { label: "Promotion", badge: statusBadge(payload?.promotion_status || "-") },
    { label: "Domain", value: payload?.domain || "-" },
    { label: "Overall", value: formattedValue(payload?.overall_score) },
    { label: "Value Gain", value: formattedValue(payload?.value_per_dollar_gain_vs_frontier) },
  ]);
  renderKeyValueTable("#evaluation-detail-summary-table", [
    { key: "Training Run", value: formattedValue(payload?.training_run_id) },
    { key: "Frontier Baseline", value: formattedValue(payload?.frontier_baseline_name) },
    { key: "Quality Delta", value: formattedValue(payload?.quality_delta_vs_frontier) },
    { key: "Created", value: formattedValue(payload?.created_at) },
  ]);
  renderKeyValueTable(
    "#evaluation-result-table",
    Object.entries(payload?.result_json || {}).map(([key, value]) => ({ key: humanizeLabel(key), value: formattedValue(value) })),
    { emptyMessage: "No evaluation result payload recorded." },
  );
}

function renderJobDetail(payload) {
  renderMetricGrid("#job-detail-summary-grid", [
    { label: "Job", value: payload?.id || "-" },
    { label: "Status", badge: statusBadge(payload?.status || "-") },
    { label: "Type", value: payload?.job_type || "-" },
    { label: "Attempts", value: `${payload?.attempts ?? 0}/${payload?.max_attempts ?? 0}` },
    { label: "Available", value: formattedValue(payload?.available_at) },
    { label: "Completed", value: formattedValue(payload?.completed_at) },
  ]);
  renderKeyValueTable("#job-detail-summary-table", [
    { key: "Claimed At", value: formattedValue(payload?.claimed_at) },
    { key: "Created At", value: formattedValue(payload?.created_at) },
    { key: "Last Error", value: formattedValue(payload?.last_error) },
  ]);
  renderKeyValueTable(
    "#job-payload-table",
    Object.entries(payload?.payload || {}).map(([key, value]) => ({ key: humanizeLabel(key), value: formattedValue(value) })),
    { emptyMessage: "No job payload recorded." },
  );
}

function renderEventDetail(payload) {
  renderMetricGrid("#event-detail-summary-grid", [
    { label: "Event", value: payload?.id || "-" },
    { label: "Type", value: payload?.event_type || "-" },
    { label: "Source", value: payload?.source || "-" },
    { label: "Processed", value: payload?.processed_at ? "Yes" : "No" },
    { label: "Occurred", value: formattedValue(payload?.occurred_at) },
    { label: "Processed At", value: formattedValue(payload?.processed_at) },
  ]);
  renderKeyValueTable("#event-detail-summary-table", [
    { key: "Event Id", value: formattedValue(payload?.event_id) },
    { key: "Type", value: formattedValue(payload?.event_type) },
    { key: "Source", value: formattedValue(payload?.source) },
  ]);
  renderKeyValueTable(
    "#event-payload-table",
    Object.entries(payload?.payload_json || {}).map(([key, value]) => ({ key: humanizeLabel(key), value: formattedValue(value) })),
    { emptyMessage: "No event payload recorded." },
  );
}

function renderOpsRecordDetail(payload) {
  renderMetricGrid("#ops-detail-summary-grid", [
    { label: "Component", value: payload?.component || "-" },
    { label: "Level", badge: statusBadge(payload?.level || "info") },
    { label: "Category", value: payload?.category || "-" },
    { label: "Timestamp", value: formattedValue(payload?.timestamp) },
  ]);
  renderKeyValueTable("#ops-detail-summary-table", [
    { key: "Message", value: formattedValue(payload?.message) },
    { key: "Component", value: formattedValue(payload?.component) },
    { key: "Level", value: formattedValue(payload?.level) },
    { key: "Timestamp", value: formattedValue(payload?.timestamp) },
  ]);
  renderOutput("#ops-detail-output", payload);
}

function renderRouteComparison(actualDetail) {
  const preview = state.lastRoutePreview;
  if (!preview || !actualDetail) {
    clearHost("#route-comparison-table");
    return;
  }
  const actualDecision = actualDetail?.routing_decisions?.[0] || {};
  renderKeyValueTable("#route-comparison-table", [
    { key: "Preview vs Actual Provider", value: `${formattedValue(preview.selected_provider)} -> ${formattedValue(actualDecision.selected_provider)}` },
    { key: "Preview vs Actual Model", value: `${formattedValue(preview.decision?.selected_model)} -> ${formattedValue(actualDecision.selected_model)}` },
    { key: "Preview vs Actual Mode", value: `${formattedValue(preview.decision?.selected_mode)} -> ${formattedValue(actualDecision.selected_mode)}` },
    { key: "Preview Domain", value: formattedValue(preview.classification?.domain) },
    { key: "Actual Request Id", value: formattedValue(actualDetail?.request?.id) },
  ], { emptyMessage: "No route comparison available yet." });
}

function showDetailCard(cardSelector, outputSelector, payload) {
  const card = $(cardSelector);
  if (card) {
    card.classList.remove("hidden");
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (cardSelector === "#request-detail-card") {
    renderRequestDetail(payload);
  } else if (cardSelector === "#training-detail-card") {
    renderTrainingDetail(payload);
  } else if (cardSelector === "#evaluation-detail-card") {
    renderEvaluationDetail(payload);
  } else if (cardSelector === "#job-detail-card") {
    renderJobDetail(payload);
  } else if (cardSelector === "#event-detail-card") {
    renderEventDetail(payload);
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

function normalizedPanel(panel) {
  return knownPanels.has(panel) ? panel : "overview";
}

function panelFromHash() {
  return normalizedPanel(window.location.hash.replace(/^#/, "").trim());
}

function switchPanel(panel, { updateHash = true } = {}) {
  const nextPanel = normalizedPanel(panel);
  state.activePanel = nextPanel;
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
    await Promise.all([refreshRequests(), refreshStreamingSupport()]);
  },
  governance: async () => {
    await Promise.all([refreshVirtualKeys(), refreshPricingCatalog(), refreshGuardrails()]);
  },
  models: async () => {
    await Promise.all([refreshModels(), refreshLocalModels(), refreshPolicies()]);
  },
  integrations: async () => {
    await Promise.all([refreshProviderGuides(), refreshMcpServers()]);
  },
  prompts: async () => {
    await refreshPrompts();
  },
  data: async () => {
    await refreshDatasetPipeline();
  },
  training: async () => {
    await Promise.all([refreshTrainingRuns(), refreshEvaluations(), refreshKpis()]);
  },
  operations: async () => {
    await Promise.all([refreshOperationsSummary(), refreshOperationsLive(), refreshObservability()]);
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
  const autoDeployCheckbox = document.querySelector('#automation-form [name="auto_deploy_approved_evaluations"]');
  if (autoDeployCheckbox) {
    autoDeployCheckbox.checked = Boolean(payload.llmproxy_auto_deploy_approved_evaluations);
  }
  setFieldValue("#automation-form", "auto_deploy_deployment_mode", payload.llmproxy_auto_deploy_deployment_mode || "production");
  setFieldValue("#routing-settings-form", "routing_strategy", payload.llmproxy_routing_strategy || "balanced");
  setFieldValue("#routing-settings-form", "frontier_default_entries", JSON.stringify(payload.llmproxy_frontier_default_entries || [], null, 2));
  return payload;
}

async function refreshProviderGuides() {
  const payload = await apiFetch("/admin/api/providers/guides");
  renderMetricGrid("#provider-guide-grid", [
    { label: "Named Guides", value: String(payload.provider_count || 0) },
    {
      label: "Configured Targets",
      value: String((payload.providers || []).filter((item) => item.configured).length),
    },
    {
      label: "Config Gaps",
      value: String((payload.providers || []).filter((item) => !item.configured).length),
    },
  ]);
  const host = $("#provider-guide-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Provider", "Configured", "Validation", "Config Keys", "Actions"], payload.providers || [], (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.label)}</strong><br/><span>${escapeHtml(row.provider_key)}</span></td>
        <td>${boolBadge(Boolean(row.configured))}</td>
        <td>${escapeHtml(row.validation_mode || "-")}</td>
        <td>${escapeHtml((row.config_keys || []).join(", "))}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => renderOutput("#provider-guide-output", row), { accent: true }));
      if (row.provider_key !== "replicate") {
        actions.appendChild(createActionButton("Validate", async () => {
          const result = await apiFetch("/admin/api/providers/validate", {
            method: "POST",
            body: JSON.stringify({ provider_key: row.provider_key, prompt: "Say hello briefly." }),
          });
          renderOutput("#provider-guide-output", result);
          showToast(`Validated ${row.label}.`, "ok");
        }));
      }
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Provider-specific guidance will appear here."),
  );
  renderOutput("#provider-guide-output", payload);
  return payload;
}

function renderRoutePreview(payload) {
  state.lastRoutePreview = payload;
  const decision = payload?.decision || {};
  const classification = payload?.classification || {};
  renderMetricGrid("#route-preview-grid", [
    { label: "Provider", value: payload?.selected_provider || "-" },
    { label: "Model", value: decision.selected_model || "-" },
    { label: "Mode", value: decision.selected_mode || "-" },
    { label: "Domain", value: classification.domain || "-", subvalue: classification.task_type || "No task type" },
    { label: "Latency Class", value: decision.predicted_latency_class || "-" },
    { label: "Cost Class", value: decision.predicted_cost_class || "-" },
  ]);
  renderKeyValueTable("#route-preview-table", [
    { key: "Policy Version", value: formattedValue(decision.policy_version) },
    { key: "Provider Family", value: formattedValue(decision.selected_provider_family) },
    { key: "Decision Rationale", value: formattedValue(decision.decision_rationale) },
    { key: "Shadows", value: formattedValue(payload?.shadow_provider_keys || []) },
    { key: "Fallback Chain", value: formattedValue((decision.fallback_chain || []).map((item) => `${item.order}:${item.provider}/${item.model}`)) },
    { key: "Route Tags", value: formattedValue(classification.route_tags || []) },
    { key: "Region", value: formattedValue(classification.region) },
  ], { emptyMessage: "Route preview will appear here once generated." });
  clearHost("#route-comparison-table");
  renderOutput("#route-preview-output", payload);
}

async function fetchLatestRequestDetailBySession(sessionId) {
  if (!sessionId) return null;
  const rows = await apiFetch(`/admin/api/proxy/requests?session_id=${encodeURIComponent(sessionId)}`);
  if (!Array.isArray(rows) || !rows.length) return null;
  return apiFetch(`/admin/api/proxy/requests/${encodeURIComponent(rows[0].id)}`);
}

async function refreshPrompts() {
  const payload = await apiFetch("/admin/api/prompts");
  const host = $("#prompts-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Name", "Version", "Variables", "Model", "Actions"], payload || [], (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.name)}</strong><br/><span>${escapeHtml(row.description || "")}</span></td>
        <td>${escapeHtml(String(row.version))}</td>
        <td>${escapeHtml((row.variables || []).join(", ") || "-")}</td>
        <td>${escapeHtml(row.model_override || "-")}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", async () => {
        const detail = await apiFetch(`/admin/api/prompts/${encodeURIComponent(row.name)}?version=${encodeURIComponent(row.version)}`);
        renderOutput("#prompt-detail-output", detail);
      }, { accent: true }));
      actions.appendChild(createActionButton("Render", async () => {
        const variables = Object.fromEntries((row.variables || []).map((name) => [name, `sample_${name}`]));
        const detail = await apiFetch(`/admin/api/prompts/${encodeURIComponent(row.name)}/render`, {
          method: "POST",
          body: JSON.stringify({ version: row.version, variables }),
        });
        renderOutput("#prompt-detail-output", detail);
      }));
      if (Number(row.version || 0) > 1) {
        actions.appendChild(createActionButton("Diff Prev", async () => {
          const detail = await apiFetch(
            `/admin/api/prompts/${encodeURIComponent(row.name)}/diff?from_version=${encodeURIComponent(Number(row.version) - 1)}&to_version=${encodeURIComponent(row.version)}`,
          );
          renderOutput("#prompt-detail-output", detail);
        }));
      }
      tr.children[4].appendChild(actions);
      return tr;
    }, "No prompt templates registered yet."),
  );
  return payload;
}

function formatVirtualKeyLimits(row) {
  const parts = [];
  if (row.rpm_limit != null) parts.push(`RPM ${row.rpm_limit}`);
  if (row.tpm_limit != null) parts.push(`TPM ${row.tpm_limit}`);
  if (row.max_budget_usd != null) parts.push(`$${Number(row.max_budget_usd).toFixed(2)}`);
  return parts.join(" / ") || "-";
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
  setFieldValue("#virtual-key-form", "budget_reset_period", row.budget_reset_period || "");
  setFieldValue("#virtual-key-form", "budget_reset_at", row.budget_reset_at || "");
  setFieldValue("#virtual-key-form", "status", row.status || "active");
}

async function refreshVirtualKeys() {
  const payload = await apiFetch("/admin/api/auth/virtual-keys");
  renderMetricGrid("#virtual-key-grid", [
    { label: "Total Keys", value: String(payload.length) },
    { label: "Active", value: String(payload.filter((item) => item.status === "active").length) },
    { label: "Budgeted", value: String(payload.filter((item) => item.max_budget_usd != null).length) },
    { label: "Rate Limited", value: String(payload.filter((item) => item.rpm_limit != null || item.tpm_limit != null).length) },
  ]);
  const host = $("#virtual-keys-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Key", "Role", "Limits", "Spend", "Status", "Actions"], payload || [], (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.display_name || row.key_prefix)}</strong><br/><span>${escapeHtml(row.key_prefix)}</span></td>
        <td>${escapeHtml(row.role || "-")}</td>
        <td>${escapeHtml(formatVirtualKeyLimits(row))}</td>
        <td>$${Number(row.spend_usd || 0).toFixed(4)}</td>
        <td>${statusBadge(row.status || "pending")}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => renderOutput("#virtual-keys-output", row), { accent: true }));
      actions.appendChild(createActionButton("Edit", () => {
        populateVirtualKeyForm(row);
        showToast(`Loaded ${row.key_prefix} into the form.`, "info");
      }));
      actions.appendChild(createActionButton("Rotate", async () => {
        const result = await apiFetch(`/admin/api/auth/virtual-keys/${encodeURIComponent(row.id)}/rotate`, { method: "POST" });
        renderOutput("#virtual-keys-output", result);
        renderOutput("#virtual-key-form-output", result);
        showToast(`Rotated ${row.key_prefix}. Store the new token now.`, "warn");
        await refreshVirtualKeys();
      }));
      actions.appendChild(createActionButton("Disable", async () => {
        const result = await apiFetch(`/admin/api/auth/virtual-keys/${encodeURIComponent(row.id)}/disable`, { method: "POST" });
        renderOutput("#virtual-keys-output", result);
        showToast(`Disabled ${row.key_prefix}.`, "warn");
        await refreshVirtualKeys();
      }, { destructive: true, confirmMessage: `Disable virtual key ${row.key_prefix}? Existing callers will stop working.` }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Issued virtual keys will appear here."),
  );
  renderOutput("#virtual-keys-output", payload);
  return payload;
}

async function refreshPricingCatalog() {
  const payload = await apiFetch("/admin/api/pricing/catalog");
  const rows = payload.items || [];
  renderMetricGrid("#pricing-grid", [
    { label: "Catalog Rows", value: String(payload.count || 0) },
    { label: "Providers", value: String(new Set(rows.map((item) => item.provider)).size) },
    { label: "Models With Output Pricing", value: String(rows.filter((item) => item.output_cost_per_token != null).length) },
  ]);
  const host = $("#pricing-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Provider", "Model", "Input / 1K", "Output / 1K"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.provider)}</strong></td>
        <td>${escapeHtml(row.model)}</td>
        <td>${escapeHtml(String(row.input_cost_per_token ?? "-"))}</td>
        <td>${escapeHtml(String(row.output_cost_per_token ?? "-"))}</td>
      `;
      return tr;
    }, "Pricing catalog rows will appear here."),
  );
  renderOutput("#pricing-output", payload);
  return payload;
}

async function refreshGuardrails() {
  const payload = await apiFetch("/admin/api/guardrails/settings");
  renderMetricGrid("#guardrails-grid", [
    { label: "Prompt Injection Blocking", badge: boolBadge(Boolean(payload.prompt_injection_blocking_enabled)) },
    { label: "PII Output Masking", badge: boolBadge(Boolean(payload.pii_output_masking_enabled)) },
    { label: "Pre Hooks", value: String((payload.pre_hooks || []).length) },
    { label: "Post Hooks", value: String((payload.post_hooks || []).length) },
  ]);
  renderKeyValueTable("#guardrails-table", [
    { key: "Prompt Injection Blocking", value: payload.prompt_injection_blocking_enabled ? "Enabled" : "Disabled" },
    { key: "PII Output Masking", value: payload.pii_output_masking_enabled ? "Enabled" : "Disabled" },
    { key: "Pre Hooks", value: (payload.pre_hooks || []).join(", ") || "-" },
    { key: "Post Hooks", value: (payload.post_hooks || []).join(", ") || "-" },
    { key: "Blocked Output Patterns", value: String((payload.blocked_output_patterns || []).length) },
  ], { emptyMessage: "No guardrail settings available." });
  renderOutput("#guardrails-output", payload);
  return payload;
}

async function refreshObservability() {
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

async function refreshMcpServers() {
  const payload = await apiFetch("/admin/api/mcp/servers");
  renderMetricGrid("#mcp-server-grid", [
    { label: "Configured Servers", value: String(payload.server_count || 0) },
    { label: "Exposed Tools", value: String(payload.tool_count || 0) },
    {
      label: "Healthy Servers",
      value: String((payload.servers || []).filter((item) => item.configured && !item.error).length),
    },
    {
      label: "Servers With Errors",
      value: String((payload.servers || []).filter((item) => item.error).length),
    },
  ]);
  const host = $("#mcp-server-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Server", "Transport", "Configured", "Tools", "Status", "Actions"], payload.servers || [], (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.server)}</strong></td>
        <td>${escapeHtml(row.transport || "-")}</td>
        <td>${boolBadge(Boolean(row.configured))}</td>
        <td>${escapeHtml(String(row.tool_count ?? 0))}</td>
        <td>${row.error ? statusBadge("failed") : statusBadge(row.configured ? "connected" : "pending")}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => renderOutput("#mcp-server-output", row), { accent: true }));
      actions.appendChild(createActionButton("Validate", async () => {
        const result = await apiFetch(`/admin/api/mcp/servers/${encodeURIComponent(row.server)}/validate`, {
          method: "POST",
        });
        renderOutput("#mcp-server-output", result);
        showToast(`Validated MCP server ${row.server}.`, "ok");
        await refreshMcpServers();
      }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Configured MCP servers will appear here."),
  );
  renderOutput("#mcp-server-output", payload);
  return payload;
}

async function validateConfig() {
  const payload = await apiFetch("/admin/api/config/validate");
  logConsole("config validate", payload);
  renderOutput("#provider-guide-output", payload.provider_guides || []);
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
          renderMcpTraceTable("#request-mcp-trace-table", detail.mcp_trace || []);
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
  const host = $("#policies-table");
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Version", "Type", "Domains", "Tags", "Regions", "Mode", "Provider", "Model", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
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
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => showDetailCard("#model-detail-card", "#model-detail-output", row.detail), { accent: true }));
      if (row.detail?.entry?.entry_type === "frontier") {
        actions.appendChild(createActionButton("Edit", () => {
          const entry = row.detail.entry;
          setFieldValue("#frontier-policy-form", "entry_id", entry.entry_id || "");
          setFieldValue("#frontier-policy-form", "provider_key", entry.provider_key || "");
          setFieldValue("#frontier-policy-form", "model_id", entry.model_id || "");
          setFieldValue("#frontier-policy-form", "domains", (entry.domains || []).join(","));
          setFieldValue("#frontier-policy-form", "task_types", (entry.task_types || []).join(","));
          setFieldValue("#frontier-policy-form", "tags", (entry.tags || entry.labels || []).join(","));
          setFieldValue("#frontier-policy-form", "regions", (entry.regions || []).join(","));
          setFieldValue("#frontier-policy-form", "deployment_mode", entry.deployment_mode || "production");
          setFieldValue("#frontier-policy-form", "canary_percent", String(entry.canary_percent ?? 0));
          setFieldValue("#frontier-policy-form", "endpoint_url", entry.endpoint_url || "");
          setFieldValue("#frontier-policy-form", "fallback_chain", (entry.fallback_chain || []).map((item) => `${item.provider}:${item.model}`).join(","));
          setFieldValue("#frontier-policy-form", "decision_rationale", entry.decision_rationale || "");
          renderOutput("#frontier-policy-output", row.detail);
        }));
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
    makeTable(["Evaluation", "Domain", "Status", "Promotion", "Actions"], payload, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.id}</strong><br/><span>${row.training_run_id}</span></td>
        <td>${row.domain || "-"}</td>
        <td>${statusBadge(row.status || "-")}</td>
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
        createActionButton("Inspect", () => renderOpsRecordDetail(row), { accent: true }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "No records match the current filter."),
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
  window.addEventListener("hashchange", () => switchPanel(panelFromHash(), { updateHash: false }));
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
      await refreshRequests();
      const actualDetail = await fetchLatestRequestDetailBySession(body.metadata.session_id);
      if (actualDetail) {
        renderRouteComparison(actualDetail);
      }
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

  $("#refresh-virtual-keys")?.addEventListener("click", async (event) => {
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
  $("#refresh-guardrails")?.addEventListener("click", async (event) => {
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
      budget_reset_at: String(data.get("budget_reset_at") || "").trim() || null,
      status: String(data.get("status") || "").trim() || null,
    };
    const method = keyId ? "PATCH" : "POST";
    const url = keyId ? `/admin/api/auth/virtual-keys/${encodeURIComponent(keyId)}` : "/admin/api/auth/virtual-keys";
    const payload = keyId ? body : Object.fromEntries(Object.entries(body).filter(([key]) => key !== "status"));
    try {
      const result = await withLoading(event.submitter, () => apiFetch(url, { method, body: JSON.stringify(payload) }));
      renderOutput("#virtual-key-form-output", result);
      showToast(keyId ? "Virtual key updated." : "Virtual key issued.", "ok");
      if (!keyId && result.token) {
        showToast("Store the new virtual key token now.", "warn");
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

  $("#frontier-policy-reset")?.addEventListener("click", () => {
    $("#frontier-policy-form")?.reset();
    setFieldValue("#frontier-policy-form", "entry_id", "");
    setFieldValue("#frontier-policy-form", "deployment_mode", "production");
    setFieldValue("#frontier-policy-form", "canary_percent", "0.0");
  });

  $("#frontier-policy-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      entry_id: data.get("entry_id") || null,
      provider_key: data.get("provider_key"),
      model_id: data.get("model_id"),
      domains: csv(String(data.get("domains") || "")),
      task_types: csv(String(data.get("task_types") || "")),
      tags: csv(String(data.get("tags") || "")),
      labels: csv(String(data.get("tags") || "")),
      regions: csv(String(data.get("regions") || "")),
      deployment_mode: data.get("deployment_mode"),
      canary_percent: Number(data.get("canary_percent") || 0),
      endpoint_url: String(data.get("endpoint_url") || "").trim() || null,
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
      variables: csv(String(data.get("variables") || "")),
      template_text: String(data.get("template_text") || ""),
      metadata: {},
    };
    try {
      const result = await withLoading(event.submitter, () => apiFetch("/admin/api/prompts", { method: "POST", body: JSON.stringify(body) }));
      renderOutput("#prompt-template-output", result);
      showToast(`Prompt template saved as ${result.name} v${result.version}.`, "ok");
      await refreshPrompts();
    } catch (error) {
      showToast(`Prompt template save failed: ${String(error)}`, "err");
      logConsole("prompt template save failed", String(error));
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
  $("#refresh-observability")?.addEventListener("click", async (event) => {
    try {
      await withLoading(event.currentTarget, () => refreshObservability());
    } catch (error) {
      showToast(`Observability refresh failed: ${String(error)}`, "err");
      logConsole("observability refresh failed", String(error));
    }
  });
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
