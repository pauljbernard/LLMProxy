const state = {
  token: localStorage.getItem("llmproxy.admin.token") || "",
  activePanel: "overview",
  opsPollTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function logConsole(label, payload) {
  const output = $("#console-output");
  const rendered = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
  const stamp = new Date().toISOString();
  output.textContent = `[${stamp}] ${label}\n${rendered}\n\n${output.textContent}`;
}

function setStatus(text, ok = true) {
  const pill = $("#status-pill");
  pill.textContent = text;
  pill.style.background = ok ? "#edf9f2" : "#fff0ea";
  pill.style.color = ok ? "#18573f" : "#8f3d1c";
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

function makeTable(columns, rows, rowRenderer) {
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
  rows.forEach((row) => tbody.appendChild(rowRenderer(row)));
  table.appendChild(tbody);
  return table;
}

function createActionButton(label, handler, accent = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `button micro${accent ? " accent" : ""}`;
  button.textContent = label;
  button.addEventListener("click", handler);
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
  if (panel === "operations" && state.token) {
    refreshOperationsLive().catch((error) => logConsole("operations live refresh failed", String(error)));
  }
}

async function refreshHealth() {
  const payload = await apiFetch("/health");
  renderOutput("#health-output", payload);
  return payload;
}

async function refreshConfig() {
  const payload = await apiFetch("/admin/api/config");
  renderOutput("#config-output", payload);
  return payload;
}

async function validateConfig() {
  const payload = await apiFetch("/admin/api/config/validate");
  logConsole("config validate", payload);
  renderOutput("#config-output", payload);
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
        <td>${row.domain || "-"}</td>
        <td>${row.task_type || "-"}</td>
        <td>${row.requested_model}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          const detail = await apiFetch(`/admin/api/proxy/requests/${row.id}`);
          renderOutput("#request-detail-output", detail);
        }, true),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }),
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
        <td>${row.configured ? "yes" : "no"}</td>
        <td>${row.supports_streaming ? "yes" : "no"}</td>
        <td>${row.provider_family}</td>
      `;
      return tr;
    }),
  );
  renderOutput("#streaming-support-output", payload);
  return payload;
}

async function refreshModels() {
  renderOutput("#models-output", await apiFetch("/v1/models"));
}

async function refreshLocalModels() {
  renderOutput("#local-models-output", await apiFetch("/models/local"));
}

async function refreshPolicies() {
  renderOutput("#policies-output", await apiFetch("/deployment/routing-policies"));
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
        <td>${row.approval_status}</td>
        <td>${row.quality_score}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Approve", async () => {
          const result = await apiFetch(`/proxy/training-candidates/${row.id}/approve`, { method: "POST" });
          logConsole("candidate approve", result);
          await refreshCandidates();
        }, true),
      );
      actions.appendChild(
        createActionButton("Reject", async () => {
          const result = await apiFetch(`/proxy/training-candidates/${row.id}/reject`, { method: "POST" });
          logConsole("candidate reject", result);
          await refreshCandidates();
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }),
  );
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
        <td>${row.created_at || "-"}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => renderOutput("#exports-output", row), true));
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
    }),
  );
  renderOutput("#exports-output", payload);
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
        <td>${row.status}</td>
        <td>${row.record_count}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(createActionButton("Inspect", () => renderOutput("#dataset-output", row), true));
      tr.lastElementChild.appendChild(actions);
      return tr;
    }),
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
      actions.appendChild(createActionButton("Inspect", () => renderOutput("#dataset-output", row), true));
      actions.appendChild(
        createActionButton("Train", () => {
          setFieldValue("#training-form", "dataset_version_id", row.id);
          logConsole("training form filled from dataset version", row);
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }),
  );
  return payload;
}

async function refreshDatasetViews() {
  const imports = await refreshDatasetImports();
  const versions = await refreshDatasetVersions();
  renderOutput("#dataset-output", { imports, versions });
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
        <td>${row.status}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          renderOutput("#training-output", await apiFetch(`/admin/api/training/runs/${row.id}`));
        }, true),
      );
      actions.appendChild(
        createActionButton("Evaluate", () => {
          setFieldValue("#evaluation-form", "training_run_id", row.id);
          setFieldValue("#training-show-form", "training_run_id", row.id);
          logConsole("evaluation form filled from training run", row);
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }),
  );
  renderOutput("#training-output", payload);
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
        <td>${row.promotion_status || "-"}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          const detail = await apiFetch(`/admin/api/evaluation/runs/${row.id}`);
          renderOutput("#evaluation-output", detail);
        }, true),
      );
      actions.appendChild(
        createActionButton("Prepare Deploy", async () => {
          const detail = await apiFetch(`/admin/api/evaluation/runs/${row.id}`);
          const manifestPath = detail.result_json?.package_manifest_path || row.package_manifest_path || "";
          const alias = detail.result_json?.model_alias || deriveAliasFromManifest(manifestPath);
          setFieldValue("#deploy-form", "model_alias", alias);
          setFieldValue("#evaluation-show-form", "evaluation_run_id", row.id);
          renderOutput("#evaluation-output", detail);
          logConsole("deployment form prepared from evaluation", { evaluation_run_id: row.id, model_alias: alias, manifest_path: manifestPath });
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }),
  );
  renderOutput("#evaluation-output", payload);
}

async function refreshKpis() {
  renderOutput("#kpi-output", await apiFetch("/evaluation/kpis"));
}

function renderLogTable(selector, rows) {
  const host = $(selector);
  host.innerHTML = "";
  host.appendChild(
    makeTable(["Time", "Level", "Component", "Message", "Actions"], rows, (row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.timestamp || "-"}</td>
        <td>${row.level || "-"}</td>
        <td>${row.component || "-"}</td>
        <td>${row.message || "-"}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", () => renderOutput("#ops-detail-output", row), true),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }),
  );
}

async function refreshOperationsSummary() {
  const summary = await apiFetch("/admin/api/ops/summary");
  const metrics = await apiFetch("/metrics");
  renderOutput("#ops-summary-output", summary);
  renderOutput("#ops-metrics-output", metrics);
  renderOutput("#ops-stream-output", summary.streaming || {});
  renderOutput("#ops-stream-live-output", (summary.streaming && summary.streaming.recent_stream_summaries) || []);
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
  renderOutput("#ops-summary-output", payload.summary);
  renderOutput("#ops-stream-output", payload.summary?.streaming || {});
  renderOutput("#ops-stream-live-output", (payload.summary?.streaming && payload.summary.streaming.recent_stream_summaries) || []);
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
        <td>${row.status}</td>
        <td>${row.attempts}/${row.max_attempts}</td>
        <td>${row.job_type}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          renderOutput("#job-detail-output", await apiFetch(`/admin/api/jobs/${row.id}`));
        }, true),
      );
      actions.appendChild(
        createActionButton("Retry", async () => {
          const result = await apiFetch(`/admin/api/jobs/${row.id}/retry`, {
            method: "POST",
            body: JSON.stringify({ reset_attempts: true, available_now: true }),
          });
          logConsole("job retry", result);
          await refreshJobs();
        }),
      );
      actions.appendChild(
        createActionButton("Cancel", async () => {
          const result = await apiFetch(`/admin/api/jobs/${row.id}/cancel`, { method: "POST" });
          logConsole("job cancel", result);
          await refreshJobs();
        }),
      );
      tr.lastElementChild.appendChild(actions);
      return tr;
    }),
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
        <td>${row.processed_at || "pending"}</td>
        <td></td>
      `;
      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.appendChild(
        createActionButton("Inspect", async () => {
          renderOutput("#event-detail-output", await apiFetch(`/admin/api/events/${row.id}`));
        }, true),
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
    }),
  );
}

async function initialize() {
  $("#token-input").value = state.token;

  $$(".nav-link").forEach((button) => {
    button.addEventListener("click", () => switchPanel(button.dataset.panel));
  });

  $("#save-token").addEventListener("click", () => {
    state.token = $("#token-input").value.trim();
    localStorage.setItem("llmproxy.admin.token", state.token);
    setStatus("Token Saved", true);
  });

  $("#clear-token").addEventListener("click", () => {
    state.token = "";
    $("#token-input").value = "";
    localStorage.removeItem("llmproxy.admin.token");
    setStatus("Token Cleared", false);
  });

  $("#check-connection").addEventListener("click", async () => {
    try {
      const payload = await refreshHealth();
      setStatus(`Connected: ${payload.environment}`, true);
      logConsole("health check", payload);
    } catch (error) {
      setStatus("Connection Failed", false);
      logConsole("health check failed", String(error));
    }
  });

  $("#clear-console").addEventListener("click", () => {
    $("#console-output").textContent = "";
  });

  document.querySelector("[data-action='refresh-health']").addEventListener("click", () => refreshHealth().catch((error) => logConsole("refresh health failed", String(error))));
  document.querySelector("[data-action='refresh-config']").addEventListener("click", () => refreshConfig().catch((error) => logConsole("refresh config failed", String(error))));
  document.querySelector("[data-action='validate-config']").addEventListener("click", () => validateConfig().catch((error) => logConsole("validate config failed", String(error))));

  $("#config-set-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    const result = await apiFetch("/admin/api/config/set", { method: "POST", body: JSON.stringify(payload) });
    logConsole("config set", result);
    await refreshConfig();
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
    const result =
      wantsStream && submitter.dataset.mode === "chat"
        ? await apiStream(url, body)
        : await apiFetch(url, { method: "POST", body: JSON.stringify(body) });
    renderOutput("#chat-output", result);
    logConsole(`proxy ${submitter.dataset.mode}`, result);
    await refreshRequests();
  });

  $("#embeddings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      model: data.get("model"),
      input: String(data.get("inputs") || "").split("\n").map((item) => item.trim()).filter(Boolean),
    };
    const result = await apiFetch("/v1/embeddings", { method: "POST", body: JSON.stringify(body) });
    renderOutput("#embeddings-output", result);
  });

  $("#request-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await refreshRequests(Object.fromEntries(data.entries()));
  });
  $("#refresh-requests").addEventListener("click", () => refreshRequests().catch((error) => logConsole("requests refresh failed", String(error))));
  $("#refresh-streaming-support").addEventListener("click", () => refreshStreamingSupport().catch((error) => logConsole("streaming support refresh failed", String(error))));
  $("#streaming-validate-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const result = await apiFetch("/admin/api/ops/streaming/validate", {
      method: "POST",
      body: JSON.stringify({
        provider_key: data.get("provider_key") || null,
        prompt: data.get("prompt") || "Say hello briefly.",
      }),
    });
    renderOutput("#streaming-support-output", result);
    logConsole("streaming validation", result);
  });

  $("#refresh-models").addEventListener("click", () => refreshModels().catch((error) => logConsole("models refresh failed", String(error))));
  $("#refresh-local-models").addEventListener("click", () => refreshLocalModels().catch((error) => logConsole("local models refresh failed", String(error))));
  $("#refresh-policies").addEventListener("click", () => refreshPolicies().catch((error) => logConsole("policy refresh failed", String(error))));

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
    const result = await apiFetch("/proxy/models/register", { method: "POST", body: JSON.stringify(body) });
    renderOutput("#model-register-output", result);
    await refreshLocalModels();
  });

  $("#deploy-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    const data = new FormData(event.currentTarget);
    const modelAlias = data.get("model_alias");
    if (submitter.dataset.mode === "rollback") {
      const result = await apiFetch(`/deployment/models/${modelAlias}/rollback`, { method: "POST" });
      renderOutput("#deploy-output", result);
      await refreshPolicies();
      return;
    }
    const body = {
      deployment_mode: data.get("deployment_mode"),
      domains: csv(String(data.get("domains") || "")),
      task_types: csv(String(data.get("task_types") || "")),
      canary_percent: Number(data.get("canary_percent") || 0),
    };
    const result = await apiFetch(`/deployment/models/${modelAlias}/activate`, { method: "POST", body: JSON.stringify(body) });
    renderOutput("#deploy-output", result);
    await refreshPolicies();
  });

  $("#refresh-candidates").addEventListener("click", () => refreshCandidates().catch((error) => logConsole("candidates refresh failed", String(error))));
  $("#refresh-exports").addEventListener("click", () => refreshExports().catch((error) => logConsole("exports refresh failed", String(error))));
  $("#refresh-dataset-imports").addEventListener("click", () => refreshDatasetViews().catch((error) => logConsole("dataset imports refresh failed", String(error))));
  $("#refresh-dataset-versions").addEventListener("click", () => refreshDatasetViews().catch((error) => logConsole("dataset versions refresh failed", String(error))));
  $("#exports-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshExports();
  });
  $("#dataset-imports-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshDatasetViews();
  });
  $("#dataset-versions-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshDatasetViews();
  });

  $("#export-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = {
      domain: data.get("domain"),
      name: data.get("name") || null,
      min_quality_score: Number(data.get("min_quality_score") || 0),
    };
    const result = await apiFetch("/proxy/export/jsonl", { method: "POST", body: JSON.stringify(body) });
    renderOutput("#exports-output", result);
    await refreshExports();
  });

  $("#dataset-import-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const body = Object.fromEntries(data.entries());
    const result = await apiFetch("/datasets/import", { method: "POST", body: JSON.stringify(body) });
    logConsole("dataset import", result);
    await refreshDatasetViews();
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
    const result = await apiFetch("/training/runs", { method: "POST", body: JSON.stringify(body) });
    renderOutput("#training-output", result);
    await refreshTrainingRuns();
  });
  $("#refresh-training").addEventListener("click", () => refreshTrainingRuns().catch((error) => logConsole("training refresh failed", String(error))));
  $("#training-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshTrainingRuns();
  });
  $("#training-show-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const result = await apiFetch(`/admin/api/training/runs/${data.get("training_run_id")}`);
    renderOutput("#training-output", result);
  });

  $("#refresh-evaluations").addEventListener("click", () => refreshEvaluations().catch((error) => logConsole("evaluation refresh failed", String(error))));
  $("#refresh-kpis").addEventListener("click", () => refreshKpis().catch((error) => logConsole("kpi refresh failed", String(error))));
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
    const result = await apiFetch("/evaluation/runs", { method: "POST", body: JSON.stringify(body) });
    renderOutput("#evaluation-output", result);
    await refreshEvaluations();
  });
  $("#evaluation-show-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const result = await apiFetch(`/admin/api/evaluation/runs/${data.get("evaluation_run_id")}`);
    renderOutput("#evaluation-output", result);
  });

  $("#refresh-jobs").addEventListener("click", () => refreshJobs().catch((error) => logConsole("jobs refresh failed", String(error))));
  $("#refresh-events").addEventListener("click", () => refreshEvents().catch((error) => logConsole("events refresh failed", String(error))));
  $("#jobs-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshJobs();
  });
  $("#events-filter-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await refreshEvents();
  });
  $("#refresh-ops-summary").addEventListener("click", () => refreshOperationsSummary().catch((error) => logConsole("ops summary refresh failed", String(error))));
  $("#refresh-ops-live").addEventListener("click", () => refreshOperationsLive().catch((error) => logConsole("ops live refresh failed", String(error))));
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
  $("#run-worker-once").addEventListener("click", async () => {
    const result = await apiFetch("/admin/api/jobs/run-once", { method: "POST" });
    logConsole("worker run once", result);
    await refreshJobs();
  });
  $("#run-scheduler-once").addEventListener("click", async () => {
    const result = await apiFetch("/admin/api/scheduler/run-once", { method: "POST" });
    logConsole("scheduler run once", result);
    await refreshEvents();
    await refreshJobs();
  });
  $("#process-events").addEventListener("click", async () => {
    const result = await apiFetch("/admin/api/events/process", { method: "POST" });
    logConsole("events process", result);
    await refreshEvents();
    await refreshJobs();
  });

  try {
    if (state.token) {
      await refreshHealth();
      await refreshConfig();
      await refreshRequests();
      await refreshStreamingSupport();
      await refreshModels();
      await refreshLocalModels();
      await refreshPolicies();
      await refreshCandidates();
      await refreshExports();
      await refreshDatasetViews();
      await refreshTrainingRuns();
      await refreshEvaluations();
      await refreshKpis();
      await refreshOperationsSummary();
      await refreshOperationsLive();
      await refreshJobs();
      await refreshEvents();
      setStatus("Connected", true);
    }
  } catch (error) {
    setStatus("Token Required", false);
    logConsole("initial load failed", String(error));
  }
}

window.addEventListener("DOMContentLoaded", () => {
  initialize().catch((error) => {
    setStatus("Initialization Failed", false);
    logConsole("fatal init error", String(error));
  });
});

window.setInterval(() => {
  if (!state.token || state.activePanel !== "operations") {
    return;
  }
  refreshOperationsLive().catch((error) => logConsole("operations auto-refresh failed", String(error)));
}, 5000);
