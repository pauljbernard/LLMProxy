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
  { key: "domain", label: "Domain", render: (value) => `<span class="badge badge-info">${escapeHtml(value || "-")}</span>` },
  { key: "task_type", label: "Task Type", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(value)}</span>` },
  { key: "requested_model", label: "Requested Model", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "successful", label: "Outcome", render: (value) => (value ? '<span class="badge badge-ok">Successful</span>' : '<span class="badge badge-err">Failed</span>') },
  { key: "session_id", label: "Session", hideEmpty: true, render: (value) => renderIdChip(value) },
  { key: "route_type", label: "Route Type", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "quality_score", label: "Quality Score", render: (value) => (value == null ? '<span class="empty-value">Not scored</span>' : `<span class="num">${escapeHtml(formattedValue(value))}</span>`) },
  { key: "cost_estimate", label: "Cost Estimate", render: (value) => (value == null ? '<span class="empty-value">-</span>' : renderAmount(value, { precision: 4 })) },
  { key: "created_at", label: "Created", render: (value) => timeLabel(value) },
];

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
  renderRecordView("#request-detail-summary-table", request, REQUEST_RECORD_FIELDS, {
    rawLabel: "View raw request record",
    emptyState: { title: "No request selected.", body: "Choose a request from the history table to see its full detail here." },
  });
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

const ROUTE_COMPARISON_RECORD_FIELDS = [
  { key: "provider", label: "Provider: Preview → Actual", value: (c) => `${formattedValue(c.preview?.selected_provider)} -> ${formattedValue(c.actualDecision?.selected_provider)}` },
  { key: "model", label: "Model: Preview → Actual", value: (c) => `${formattedValue(c.preview?.decision?.selected_model)} -> ${formattedValue(c.actualDecision?.selected_model)}` },
  { key: "mode", label: "Mode: Preview → Actual", value: (c) => `${formattedValue(c.preview?.decision?.selected_mode)} -> ${formattedValue(c.actualDecision?.selected_mode)}` },
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

function renderModelInfoDetail(model) {
  renderRecordView("#model-detail-summary-table", model, MODEL_INFO_FIELDS, {
    rawLabel: "View raw model record",
    emptyState: {
      title: "No model selected.",
      body: "Choose a proxy-exposed model from the table above to inspect its identifier. For its routing configuration, look up the matching entry in the Routing Policies table.",
    },
  });
}

const LOCAL_PACKAGE_FIELDS = [
  { key: "model_alias", label: "Model Alias", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "model_registry_id", label: "Registry ID", render: (value) => renderIdChip(value) },
  { key: "base_model", label: "Base Model", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "adapter_type", label: "Adapter Type", render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "promotion_status", label: "Promotion Status", render: (value) => statusBadge(value) },
  { key: "domains", label: "Domains", render: (value) => renderList(value, { emptyLabel: "No domains configured" }) },
  { key: "artifact_paths", label: "Artifact Paths", render: (value) => (Array.isArray(value) && value.length ? `<pre class="value-pre">${escapeHtml(value.join("\n"))}</pre>` : '<span class="empty-value">No artifacts recorded</span>') },
];

function renderLocalPackageDetail(pkg) {
  renderRecordView("#model-detail-summary-table", pkg, LOCAL_PACKAGE_FIELDS, {
    rawLabel: "View raw model package record",
    emptyState: {
      title: "No package selected.",
      body: "Choose a registered local package from the table above to inspect its manifest, training domains, and promotion status.",
    },
  });
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
  { key: "domains", label: "Domains", render: (value) => renderList(value, { emptyLabel: "All domains" }) },
  { key: "task_types", label: "Task Types", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "All task types" }) },
  { key: "tags", label: "Tags", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No tags configured" }) },
  { key: "labels", label: "Labels", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No labels configured" }) },
  { key: "regions", label: "Regions", hideEmpty: true, render: (value) => renderList(value, { emptyLabel: "No region restriction" }) },
  { key: "fallback_chain", label: "Fallback Chain", hideEmpty: true, render: (value) => renderList((value || []).map((item) => `${item.order}: ${item.provider}/${item.model}`), { emptyLabel: "No fallback chain configured" }) },
  { key: "decision_rationale", label: "Decision Rationale", hideEmpty: true },
  { key: "artifact_path", label: "Artifact Path", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "quality_summary", label: "Quality Summary", value: (record) => (record.quality_summary && Object.keys(record.quality_summary).length ? record.quality_summary : null), hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(JSON.stringify(value, null, 2))}</pre>` },
];

function renderPolicyEntryDetail(wrapper) {
  const entry = wrapper?.entry || {};
  const flattened = { policy_version: wrapper?.policy_version, entry_index: wrapper?.entry_index, ...entry };
  renderRecordView("#model-detail-summary-table", flattened, POLICY_ENTRY_RECORD_FIELDS, {
    rawLabel: "View raw policy entry record",
    emptyState: {
      title: "No policy entry selected.",
      body: "Choose an entry from the Routing Policies table above to inspect its provider, routing dimensions, and rollout configuration.",
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

function renderPolicyVersionDetail(policyVersion) {
  renderRecordView("#model-detail-summary-table", policyVersion, POLICY_VERSION_RECORD_FIELDS, {
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
function renderModelDetail(payload) {
  if (payload && typeof payload === "object" && payload.entry && typeof payload.entry === "object") {
    renderPolicyEntryDetail(payload);
  } else if (payload && Array.isArray(payload.artifact_paths)) {
    renderLocalPackageDetail(payload);
  } else if (payload && payload.policy && typeof payload.policy === "object") {
    renderPolicyVersionDetail(payload);
  } else {
    renderModelInfoDetail(payload);
  }
}

function showDetailCard(cardSelector, outputSelector, payload) {
  const card = $(cardSelector);
  if (card) {
    card.classList.remove("hidden");
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  if (cardSelector === "#request-detail-card") {
    renderRequestDetail(payload);
  } else if (cardSelector === "#model-detail-card") {
    renderModelDetail(payload);
  } else if (cardSelector === "#training-detail-card") {
    renderTrainingDetail(payload);
  } else if (cardSelector === "#evaluation-detail-card") {
    renderEvaluationDetail(payload);
  } else if (cardSelector === "#job-detail-card") {
    renderJobDetail(payload);
  } else if (cardSelector === "#event-detail-card") {
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
    renderOutput(outputSelector, payload);
  }
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

function makeTable(columns, rows, rowRenderer, emptyState = "No records available yet.") {
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
    const config = typeof emptyState === "string" ? { title: "No data yet.", body: emptyState } : emptyState;
    td.appendChild(buildEmptyState(config));
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
      actions.appendChild(createActionButton("Inspect", () => renderRecordView("#provider-guide-detail", row, PROVIDER_GUIDE_RECORD_FIELDS, { rawLabel: "View raw provider guide" }), { accent: true }));
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
  const guideCount = (payload.providers || []).length;
  clearHost("#provider-guide-detail");
  $("#provider-guide-detail")?.appendChild(buildEmptyState({
    icon: "→",
    title: "Select a provider to inspect.",
    body: `${guideCount} provider guide${guideCount === 1 ? "" : "s"} available — choose “Inspect” on any row to see its full configuration, recommended endpoint, and setup notes here.`,
  }));
  renderOutput("#provider-guide-output", payload);
  return payload;
}

const ROUTE_PREVIEW_RECORD_FIELDS = [
  { key: "policy_version", label: "Policy Version", value: (p) => p?.decision?.policy_version, hideEmpty: true },
  { key: "selected_provider_family", label: "Provider Family", value: (p) => p?.decision?.selected_provider_family, hideEmpty: true },
  { key: "decision_rationale", label: "Decision Rationale", value: (p) => p?.decision?.decision_rationale, hideEmpty: true },
  { key: "shadow_provider_keys", label: "Shadows", value: (p) => p?.shadow_provider_keys || [], render: (value) => renderList(value, { emptyLabel: "No shadow routing configured" }) },
  { key: "fallback_chain", label: "Fallback Chain", value: (p) => (p?.decision?.fallback_chain || []).map((item) => `${item.order}: ${item.provider}/${item.model}`), render: (value) => renderList(value, { emptyLabel: "No fallback chain configured" }) },
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
    { label: "Domain", value: classification.domain || "-", subvalue: classification.task_type || "No task type" },
    { label: "Latency Class", value: decision.predicted_latency_class || "-" },
    { label: "Cost Class", value: decision.predicted_cost_class || "-" },
  ]);
  renderRecordView("#route-preview-table", payload, ROUTE_PREVIEW_RECORD_FIELDS, {
    rawLabel: "View raw route preview",
    emptyState: { title: "No route preview yet.", body: "Submit the form above to preview how a request would be routed." },
  });
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
  { key: "id", label: "Template ID", render: (value) => renderIdChip(value) },
  { key: "description", label: "Description", hideEmpty: true },
  { key: "model_override", label: "Model Override", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "variables", label: "Variables", render: (value) => renderList(value, { emptyLabel: "No variables — renders as static text" }) },
  { key: "template_text", label: "Template Text", render: (value) => `<pre class="value-pre">${escapeHtml(value || "")}</pre>` },
  { key: "metadata", label: "Metadata", value: (record) => (record.metadata && Object.keys(record.metadata).length ? record.metadata : null), hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(JSON.stringify(value, null, 2))}</pre>` },
  { key: "created_at", label: "Created", render: (value) => timeLabel(value) },
];

function renderPromptTemplateDetail(detail) {
  renderRecordView("#prompt-detail-output", detail, PROMPT_TEMPLATE_RECORD_FIELDS, {
    rawLabel: "View raw prompt template record",
    emptyState: {
      title: "No prompt template selected.",
      body: "Choose a version from the table above and select “Inspect” to see its full text, variables, and metadata here.",
    },
  });
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
        renderPromptTemplateDetail(detail);
      }, { accent: true }));
      actions.appendChild(createActionButton("Render", async () => {
        const variables = Object.fromEntries((row.variables || []).map((name) => [name, `sample_${name}`]));
        const detail = await apiFetch(`/admin/api/prompts/${encodeURIComponent(row.name)}/render`, {
          method: "POST",
          body: JSON.stringify({ version: row.version, variables }),
        });
        renderPromptRenderResult(detail);
      }));
      if (Number(row.version || 0) > 1) {
        actions.appendChild(createActionButton("Diff Prev", async () => {
          const detail = await apiFetch(
            `/admin/api/prompts/${encodeURIComponent(row.name)}/diff?from_version=${encodeURIComponent(Number(row.version) - 1)}&to_version=${encodeURIComponent(row.version)}`,
          );
          renderPromptDiffResult(detail);
        }));
      }
      tr.children[4].appendChild(actions);
      return tr;
    }, "No prompt templates registered yet."),
  );
  const promptCount = (payload || []).length;
  clearHost("#prompt-detail-output");
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

async function refreshVirtualKeys() {
  const payload = await apiFetch("/admin/api/auth/virtual-keys");
  const directoryCount = $("#virtual-key-directory-count");
  if (directoryCount) {
    directoryCount.textContent = payload.length ? `${payload.length} key${payload.length === 1 ? "" : "s"} on file` : "";
  }
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
        <td><span class="cell-primary">${escapeHtml(row.display_name || row.key_prefix)}</span><span class="cell-secondary">${escapeHtml(row.key_prefix)}</span></td>
        <td><span class="badge badge-info">${escapeHtml(row.role || "-")}</span></td>
        <td>${escapeHtml(formatVirtualKeyLimits(row))}</td>
        <td>${renderAmount(row.spend_usd || 0, { precision: 4 })}</td>
        <td>${statusBadge(row.status || "pending")}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => {
        showVirtualKeyRecord(row);
        $("#virtual-keys-output")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, { accent: true }));
      actions.appendChild(createActionButton("Edit", () => {
        populateVirtualKeyForm(row);
        showToast(`Loaded ${row.key_prefix} into the form below.`, "info");
        $("#virtual-key-form")?.scrollIntoView({ behavior: "smooth", block: "center" });
      }));
      actions.appendChild(createActionButton("Rotate", async () => {
        const result = await apiFetch(`/admin/api/auth/virtual-keys/${encodeURIComponent(row.id)}/rotate`, { method: "POST" });
        showVirtualKeyRecord(result, { rawLabel: "View raw rotation response" });
        renderRecordView("#virtual-key-form-output", result, VIRTUAL_KEY_RECORD_FIELDS, { rawLabel: "View raw rotation response" });
        showToast(`Rotated ${row.key_prefix}. Store the new token now — it will not be shown again.`, "warn");
        await refreshVirtualKeys();
      }, { confirmMessage: `Rotate ${row.key_prefix}? The current token will stop working immediately and a new one will be issued.` }));
      actions.appendChild(createActionButton("Disable", async () => {
        const result = await apiFetch(`/admin/api/auth/virtual-keys/${encodeURIComponent(row.id)}/disable`, { method: "POST" });
        showVirtualKeyRecord(result, { rawLabel: "View raw response" });
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
    }),
  );
  if (!payload?.length) {
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
      body: `${payload.length} key${payload.length === 1 ? "" : "s"} on file. Choose “Inspect” on any row in the directory to view its full configuration, limits, and spend here.`,
    }));
  }
  return payload;
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
    makeTable(["Provider", "Model", "Input / 1M", "Output / 1M", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><span class="badge badge-info">${escapeHtml(row.provider)}</span></td>
        <td><span class="cell-primary">${escapeHtml(row.model)}</span></td>
        <td>${row.input_cost_per_token == null ? '<span class="empty-value">-</span>' : renderAmount(Number(row.input_cost_per_token) * 1_000_000, { precision: 2 })}</td>
        <td>${row.output_cost_per_token == null ? '<span class="empty-value">-</span>' : renderAmount(Number(row.output_cost_per_token) * 1_000_000, { precision: 2 })}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => {
        renderRecordView("#pricing-output", row, PRICING_RECORD_FIELDS, { rawLabel: "View raw catalog entry" });
      }, { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, {
      icon: "$",
      title: "Pricing catalog is empty.",
      body: "Per-token costs for connected providers and models will be listed here as they are registered.",
    }),
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
  renderMetricGrid("#guardrails-grid", [
    { label: "Prompt Injection Blocking", badge: boolBadge(Boolean(payload.prompt_injection_blocking_enabled)) },
    { label: "PII Output Masking", badge: boolBadge(Boolean(payload.pii_output_masking_enabled)) },
    { label: "Pre Hooks", value: String((payload.pre_hooks || []).length) },
    { label: "Post Hooks", value: String((payload.post_hooks || []).length) },
  ]);
  renderRecordView("#guardrails-table", payload, GUARDRAILS_RECORD_FIELDS, {
    raw: false,
    emptyState: { title: "No guardrail settings available.", body: "Guardrail configuration will appear here once it is available." },
  });
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
      actions.appendChild(createActionButton("Inspect", () => renderRecordView("#mcp-server-detail", row, MCP_SERVER_RECORD_FIELDS, { rawLabel: "View raw server config" }), { accent: true }));
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
  const serverCount = (payload.servers || []).length;
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

const STREAMING_VALIDATION_RECORD_FIELDS = [
  { key: "success", label: "Result", render: (value) => (value ? '<span class="badge badge-ok">Validated</span>' : '<span class="badge badge-err">Failed</span>') },
  { key: "provider_key", label: "Provider", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "provider_family", label: "Provider Family", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "model", label: "Model", hideEmpty: true, render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "error", label: "Error Detail", hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(value)}</pre>` },
  { key: "preview_text", label: "Streamed Preview", hideEmpty: true, render: (value) => `<pre class="value-pre">${escapeHtml(value)}</pre>` },
  { key: "finish_reason", label: "Finish Reason", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
  { key: "input_tokens", label: "Input Tokens", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "output_tokens", label: "Output Tokens", hideEmpty: true, render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "validated_by", label: "Validated By", hideEmpty: true, render: (value) => `<span class="badge badge-muted">${escapeHtml(humanizeLabel(value))}</span>` },
];

function showStreamingValidationResult(result) {
  renderRecordView("#streaming-support-output", result, STREAMING_VALIDATION_RECORD_FIELDS, {
    rawLabel: "View raw validation response",
    emptyState: {
      icon: "▷",
      title: "No validation run yet.",
      body: "Choose “Validate Frontier Stream” below to confirm a configured provider streams correctly and preview what it returns.",
    },
  });
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
  showStreamingValidationResult(null);
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
      actions.appendChild(createActionButton("Inspect", () => showDetailCard("#model-detail-card", null, row), { accent: true }));
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
      actions.appendChild(createActionButton("Inspect", () => showDetailCard("#model-detail-card", null, row), { accent: true }));
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
      actions.appendChild(createActionButton("Inspect", () => showDetailCard("#model-detail-card", null, row.detail), { accent: true }));
      if (row.detail?.entry?.entry_type === "frontier") {
        actions.appendChild(createActionButton("Edit", () => {
          const entry = row.detail.entry;
          setFieldValue("#frontier-policy-form", "entry_id", entry.entry_id || "");
          setFieldValue("#frontier-policy-form", "provider_key", entry.provider_key || "");
          setFieldValue("#frontier-policy-form", "model_id", entry.model_id || "");
          setFieldValue("#frontier-policy-form", "domains", (entry.domains || []).join(","));
          setFieldValue("#frontier-policy-form", "task_types", (entry.task_types || []).join(","));
          setFieldValue("#frontier-policy-form", "tags", (entry.tags || []).join(","));
          setFieldValue("#frontier-policy-form", "labels", (entry.labels || []).join(","));
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

const EXPORT_RECORD_FIELDS = [
  { key: "dataset_export_id", label: "Export ID", render: (value) => renderIdChip(value) },
  { key: "domain", label: "Domain", render: (value) => `<span class="cell-primary">${escapeHtml(value || "-")}</span>` },
  { key: "record_count", label: "Records", render: (value) => `<span class="num">${escapeHtml(formattedValue(value))}</span>` },
  { key: "schema_version", label: "Schema Version" },
  { key: "manifest_path", label: "Manifest Path", render: (value) => renderIdChip(value, { truncate: false }) },
  { key: "data_path", label: "Data Path", render: (value) => renderIdChip(value, { truncate: false }) },
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
      actions.appendChild(createActionButton("Inspect", () => renderExportDetail(row), { accent: true }));
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
  const exportCount = (payload || []).length;
  clearHost("#export-detail");
  if (!exportCount) {
    $("#export-detail")?.appendChild(buildEmptyState({
      icon: "✎",
      title: "No exports created yet.",
      body: "Bundle approved, export-eligible candidates into a dataset using the form below — each export will appear here for inspection and reuse as an import source.",
    }));
  } else {
    $("#export-detail")?.appendChild(buildEmptyState({
      icon: "→",
      title: "Select an export to inspect.",
      body: `${exportCount} export${exportCount === 1 ? "" : "s"} available — choose “Inspect” to see its manifest and data paths, or “Use for Import” to copy its IDs into the import form below.`,
    }));
  }
  renderOutput("#exports-output", payload);
  return payload;
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
      actions.appendChild(createActionButton("Inspect", () => renderDatasetImportDetail(row), { accent: true }));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }, "Imported datasets will appear here after processing completes."),
  );
  return payload;
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
      actions.appendChild(createActionButton("Inspect", () => renderDatasetVersionDetail(row), { accent: true }));
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
      showStreamingValidationResult(result);
      $("#streaming-support-output")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
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
      labels: csv(String(data.get("labels") || "")),
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
      renderRecordView("#prompt-template-output", result, PROMPT_TEMPLATE_RECORD_FIELDS, { rawLabel: "View raw save response" });
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
