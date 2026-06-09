import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api import admin
from app.api.dependencies import virtual_key_hash
from app.config import Settings
from app.db.models import VirtualAPIKey
from app.main import app
from app.schemas.routing import RoutingDecision
from app.schemas.training import TrainingRuntimeDependencyStatus, TrainingStudioStatus, TrainingWorkerRuntimeStatus


def test_admin_console_page_serves() -> None:
    client = TestClient(app)
    response = client.get("/admin")
    assert response.status_code == 200
    assert "llmProxy Operator Console" in response.text
    assert "overview-summary-strip" in response.text
    assert "health-provider-table" in response.text
    assert "Connectivity &amp; Readiness" in response.text or "Connectivity & Readiness" in response.text
    assert "Platform Facts" in response.text
    assert "listener-table" in response.text
    assert "Inbound Listener Inventory" in response.text
    assert "Inbound Listener Editor" in response.text
    assert "listener-editor-form" in response.text
    assert "save-listener-definition" in response.text
    assert "config-table" in response.text
    assert "virtual-keys-table" in response.text
    assert "pricing-table" in response.text
    assert "guardrails-table" in response.text
    assert "governance-graph-summary-strip" in response.text
    assert "governance-graph" in response.text
    assert "Visual path from governed callers through model-cost exposure and the global guardrail policy." in response.text
    assert "Integrations" in response.text
    assert "Prompt Library" in response.text
    assert "panel-runtime" in response.text
    assert "panel-integrations" in response.text
    assert "nav-training-workbench" in response.text
    assert "nav-training-oversight" in response.text
    assert ">Core<" in response.text
    assert ">Learning<" in response.text
    assert ">Operations<" in response.text
    assert ">Optimization<" in response.text
    assert "nav-overview-config" in response.text
    assert "nav-operations-monitor" in response.text
    assert ">Events<" in response.text
    assert ">Inspection<" in response.text
    assert "nav-operations-traffic" not in response.text
    assert "nav-operations-topology" in response.text
    assert "nav-operations-readiness" in response.text
    assert "nav-proxy-playground" in response.text
    assert "nav-models-catalog" in response.text
    assert 'aria-label="Proxy drill-down"' not in response.text
    assert 'aria-label="Models drill-down"' not in response.text
    assert "pipeline-summary" in response.text
    assert ">Curation<" in response.text
    assert "Curation Workbench" in response.text
    assert "candidates-filter-form" in response.text
    assert "clear-candidates-filters" in response.text
    assert 'name="interaction_protocol"' in response.text
    assert 'name="interaction_operation"' in response.text
    assert 'name="interaction_outcome"' in response.text
    assert "kpi-metrics-grid" in response.text
    assert "kpi-listener-rollups" in response.text
    assert "kpi-node-rollups" in response.text
    assert "kpi-pool-rollups" in response.text
    assert "mcp-server-table" in response.text
    assert "a2a-peer-table" in response.text
    assert "provider-guide-table" in response.text
    assert "provider-guide-open-vendor" in response.text
    assert "refresh-a2a-peers-secondary" in response.text
    assert "refresh-rest-endpoints-secondary" in response.text
    assert "Reference Guides" in response.text
    assert "Endpoint Surfaces &amp; Reference Guides" in response.text or "Endpoint Surfaces & Reference Guides" in response.text
    assert "integrations-graph-summary-strip" in response.text
    assert "integrations-graph" in response.text
    assert "Visual path from llmProxy through protocol surfaces to executable integration endpoints." in response.text
    assert ">Connectivity<" in response.text
    assert "Endpoint Workbench" in response.text
    assert 'data-collection="a2a"' in response.text
    assert 'data-collection="rest"' in response.text
    assert "integrations-detail-pane-a2a" in response.text
    assert "integrations-detail-pane-rest" in response.text
    assert "a2a-peer-interaction-trace-table" in response.text
    assert "a2a-peer-invoke-form" in response.text
    assert "a2a-invoke-capability" in response.text
    assert "invoke-a2a-peer" in response.text
    assert "rest-endpoint-table" in response.text
    assert "rest-endpoint-detail" in response.text
    assert "rest-endpoint-invoke-form" in response.text
    assert "rest-endpoint-interaction-trace-table" in response.text
    assert "validate-rest-endpoint" in response.text
    assert "invoke-rest-endpoint" in response.text
    assert "provider-model-table" in response.text
    assert 'id="foundation-visibility-scope"' in response.text
    assert "Active + Historical" in response.text
    assert "Historical Only" in response.text
    assert "foundation-open-provider-guide" in response.text
    assert "foundation-open-routing" in response.text
    assert "foundation-open-streaming" in response.text
    assert "routing-policy-filter-form" in response.text
    assert "routing-policy-scoped-only" in response.text
    assert "routing-scope-banner" in response.text
    assert 'name="requested_models"' in response.text
    assert "direct 1:1 access" in response.text
    assert "explicit redirect rules" in response.text
    assert "vendor-model-register-form" in response.text
    assert "model-register-pane-runtime" in response.text
    assert "open-register-routing" in response.text
    assert "open-register-deploy" in response.text
    assert ">Onboard<" in response.text
    assert "Add Vendor Capacity" in response.text
    assert "Add Custom Package" in response.text
    assert "Selected Vendor Onboarding" in response.text
    assert "Selected Package Onboarding" in response.text
    assert "Vendor Capacity" in response.text
    assert "Runtime Endpoints" in response.text
    assert "Route This Vendor LLM" in response.text
    assert "Attach Runtime Or Deploy" in response.text
    assert "Runtime Endpoints &amp; Hosted Capacity" in response.text or "Runtime Endpoints & Hosted Capacity" in response.text
    assert "Connect Runtime Endpoints" in response.text
    assert "local-runtime-table" in response.text
    assert "local-runtime-detail-card" in response.text
    assert "local-runtime-detail-summary" in response.text
    assert "local-runtime-lifecycle-table" in response.text
    assert "reconcile-selected-runtime" in response.text
    assert "local-runtime-ops-output" in response.text
    assert "local-runtime-config-form" in response.text
    assert "refresh-local-runtime-status" in response.text
    assert "deployments-table" in response.text
    assert "deployments-filter-form" in response.text
    assert "deployments-filter-stage" in response.text
    assert "clear-deployments-filters" in response.text
    assert "deploy-graph-summary-strip" in response.text
    assert "deploy-graph" in response.text
    assert "open-deployment-graph-artifact" in response.text
    assert "Visual path from onboarded package through deployment state, runtime attachment, and live routing." in response.text
    assert "deploy-detail-card" in response.text
    assert "deploy-detail-summary" in response.text
    assert "refresh-deployments" in response.text
    assert "event-interaction-trace-table" in response.text
    assert "Event Directory" in response.text
    assert "One canonical event directory across logs, errors, audit records, jobs, runtime activity, and request traffic." in response.text
    assert "Readiness Workbench" in response.text
    assert "LLM Performance Trends" in response.text
    assert "llm-timeseries-filter-form" in response.text
    assert "llm-timeseries-summary-strip" in response.text
    assert "llm-timeseries-chart-grid" in response.text
    assert "llm-timeseries-metric-picker" in response.text
    assert "llm-timeseries-preset-picker" in response.text
    assert "ops-preset-traffic" in response.text
    assert "Time Series" in response.text
    assert '<select id="llm-timeseries-model-id" name="model_id"></select>' in response.text
    assert "llm-timeseries-busiest-models" in response.text
    assert "llm-timeseries-slowest-models" in response.text
    assert 'name="selected_provider"' in response.text
    assert 'name="selected_model"' in response.text
    assert 'id="ops-events-selected-provider"' in response.text
    assert 'id="ops-events-selected-model"' in response.text
    assert 'id="ops-events-selected-pool"' in response.text
    assert 'id="ops-events-selected-node"' in response.text
    assert 'id="ops-events-traffic-origin"' in response.text
    assert 'id="ops-events-automation-scope"' in response.text
    assert 'id="ops-traffic-scope-group"' in response.text
    assert 'name="created_after"' in response.text
    assert 'name="created_before"' in response.text
    assert "governance-graph-filter-form" in response.text
    assert "clear-governance-graph-filters" in response.text
    assert "routing-nodes-table" in response.text
    assert "routing-pools-table" in response.text
    assert "routing-topology-summary" in response.text
    assert "routing-graph-summary-strip" in response.text
    assert "routing-graph" in response.text
    assert "open-routing-graph-artifact" in response.text
    assert "Visual path from inbound listener scope through policy selection, pooled capacity, and outbound targets." in response.text
    assert "model-routing-detail-heading" in response.text
    assert "model-routing-related-table" in response.text
    assert "refresh-routing-nodes-secondary" in response.text
    assert "refresh-routing-pools-secondary" in response.text
    assert "operations-topology-graph" in response.text
    assert "operations-topology-detail-table" in response.text
    assert "open-operations-topology-artifact" in response.text
    assert "refresh-operations-topology" in response.text
    assert "Inbound To Outbound Mappings" in response.text
    assert 'name="listener_id"' in response.text
    assert 'name="selected_pool_id"' in response.text
    assert 'name="selected_node_id"' in response.text
    assert "clear-ops-events-filters" in response.text
    assert ">LLMs<" in response.text
    assert "Vendor LLM&#39;s" in response.text or "Vendor LLM's" in response.text
    assert "Custom LLM&#39;s" in response.text or "Custom LLM's" in response.text
    assert "request-mcp-trace-table" in response.text
    assert "ops-mcp-grid" in response.text
    assert "replicate-prediction-form" in response.text
    assert "replicate-interaction-trace-table" in response.text
    assert "open-integrations-graph-artifact" in response.text
    assert "integrations-graph-filter-form" in response.text
    assert "clear-integrations-graph-filters" in response.text
    assert "routing-settings-form" in response.text
    assert 'name="node_id"' in response.text
    assert 'name="pool_id"' in response.text
    assert 'name="balancing_strategy"' in response.text
    assert 'name="affinity_key"' in response.text
    assert 'name="forward_request_metadata"' in response.text
    assert "refresh-observability" in response.text
    assert "prompts-table" in response.text
    assert "prompt-template-form" in response.text
    assert "prompt-rollout-form" in response.text
    assert "prompt-compare-active" in response.text
    assert "prompt-start-canary" in response.text
    assert "prompt-promote-challenger" in response.text
    assert "prompt-stop-canary" in response.text
    assert "prompt-auto-promotion-form" in response.text
    assert "prompt-save-auto-promotion" in response.text
    assert "prompt-run-auto-promotion" in response.text
    assert 'id="chat-prompt-template-name"' in response.text
    assert 'id="chat-prompt-template-version"' in response.text
    assert 'id="candidates-prompt-template-name"' in response.text
    assert 'id="exports-prompt-template-name"' in response.text
    assert 'id="export-prompt-template-name"' in response.text
    assert 'id="export-prompt-template-selection-mode"' in response.text
    assert 'id="ops-events-prompt-selection-mode"' in response.text
    assert 'name="trainer_backend"' in response.text
    assert "training-lifecycle-graph" in response.text
    assert "training-lifecycle-detail-table" in response.text
    assert "open-training-lifecycle-stage" in response.text
    assert "training-lifecycle-filter-form" in response.text
    assert "clear-training-lifecycle-filters" in response.text
    assert "Learning Flow" in response.text
    assert "Open Selected Artifact" in response.text
    assert "training-progress-table" in response.text
    assert "training-traffic-summary-table" in response.text
    assert "training-traffic-keys-table" in response.text
    assert "training-traffic-requests-table" in response.text
    assert "training-preflight-output" in response.text
    assert "training-runtime-table" in response.text
    assert "training-studio-table" in response.text
    assert "open-training-studio" in response.text
    assert "Runtime &amp; KPI Oversight" in response.text or "Runtime & KPI Oversight" in response.text
    assert "Open Runs &amp; Evaluation" in response.text or "Open Runs & Evaluation" in response.text
    assert "refresh-training-runtime" in response.text
    assert "refresh-training-studio" in response.text
    assert "evaluation-traffic-summary-table" in response.text
    assert 'name="traffic_origin"' in response.text
    assert 'name="automation_scope"' in response.text
    assert 'name="prompt_template_name"' in response.text
    assert 'name="prompt_template_version"' in response.text
    assert 'name="prompt_template_variables"' in response.text
    assert 'name="route_tags"' in response.text
    assert 'name="region_hint"' in response.text
    assert 'name="listener_id"' in response.text
    assert 'name="listener_ids"' in response.text
    assert "open-governance-graph-artifact" in response.text
    assert "Summarize the routing decision for this request." in response.text
    assert "open-chat-model-picker" in response.text
    assert "open-emb-model-picker" in response.text
    assert "chat-model-picker-modal" in response.text
    assert "Choose Chat Model" in response.text
    assert "model-picker-search" in response.text
    assert "Streaming Diagnostics" in response.text
    assert "Connect Runtime Endpoints" in response.text
    assert "Open Streaming Diagnostics" in response.text
    assert "Request Composer" in response.text
    assert "Latest Chat / Ensemble Output" in response.text
    assert "Embedding Probe" in response.text
    assert "route-preview-grid" in response.text
    assert "route-preview-table" in response.text
    assert "route-preview-fallback-table" in response.text
    assert "route-comparison-table" in response.text
    assert "streaming-target-filter-form" in response.text
    assert "streaming-target-configured-only" in response.text
    assert "streaming-target-streamable-only" in response.text
    assert "Stream Readiness" in response.text
    assert "streaming-target-detail-card" in response.text
    assert "streaming-target-summary-table" in response.text
    assert "streaming-validation-result-card" in response.text
    assert "streaming-validation-summary-table" in response.text
    assert 'name="validation_scope"' in response.text
    assert "All Discovered Streamable Models" in response.text
    assert "streaming-validation-results-table" in response.text
    assert "Run Front-Door Stream Test" in response.text
    assert 'name="requested_model"' in response.text
    assert 'name="execution_mode"' in response.text
    assert 'name="owner_id"' in response.text
    assert "request-detail-card" in response.text
    assert "request-detail-summary-grid" in response.text
    assert "request-routing-table" in response.text
    assert "request-fallback-table" in response.text
    assert "request-interaction-trace-table" in response.text
    assert "training-detail-summary-table" in response.text
    assert "evaluation-detail-summary-table" in response.text
    assert "export-interaction-protocols-table" in response.text
    assert "job-detail-summary-table" in response.text
    assert "event-detail-summary-table" in response.text
    assert "ops-detail-summary-table" in response.text
    assert "ops-events-table" in response.text
    assert "ops-events-filter-form" in response.text
    assert "ops-active-view-strip" in response.text
    assert 'id="ops-history-scope"' in response.text
    assert "ops-filter-layout" in response.text
    assert "ops-view-control-grid" in response.text
    assert "clear-ops-events-filters" in response.text
    assert 'name="event_source"' in response.text
    assert 'name="promotable_only"' in response.text
    assert "ops-promote-candidate" in response.text
    assert "ops-open-export-draft" in response.text
    assert "ops-preset-errors" in response.text
    assert "ops-preset-traffic" in response.text
    assert "ops-preset-audit" in response.text
    assert "ops-preset-training" in response.text
    assert "ops-preset-listener" in response.text
    assert "ops-columns-adaptive" in response.text
    assert "ops-columns-events" in response.text
    assert "ops-columns-traffic" in response.text
    assert "ops-load-saved-traffic" in response.text
    assert "ops-load-saved-errors" in response.text
    assert "ops-save-current-preset" in response.text
    assert "Operational Events" in response.text
    assert "Open Event Directory" in response.text
    assert "Observability &gt; Events" in response.text or "Observability > Events" in response.text
    assert ">Runtime Control<" in response.text
    assert "Pending Event Queue" in response.text
    assert "Control Workbench" in response.text
    assert "job-detail-card" in response.text
    assert "event-detail-card" in response.text


def test_admin_static_asset_serves() -> None:
    client = TestClient(app)
    response = client.get("/admin/static/app.js")
    assert response.status_code == 200
    assert "initialize" in response.text
    assert "refreshDatasetPipeline" in response.text
    assert "renderMetricGrid" in response.text
    assert "showDetailCard" in response.text
    assert "validateRoutingDefaultEntries" in response.text
    assert "syncSidebarNavGroups" in response.text
    assert "refreshObservability" in response.text
    assert 'activeOperationsSubview: "monitor"' in response.text
    assert 'activeTrainingSubview: "workbench"' in response.text
    assert "tablePages" in response.text
    assert "tablePageSizes" in response.text
    assert "tableContexts" in response.text
    assert "setTableLoading" in response.text
    assert "buildTablePaginationControls" in response.text
    assert "serverPaginationForPayload" in response.text
    assert "restorePersistentTableContexts" in response.text
    assert "renderInboundListenerTable" in response.text
    assert "refreshOperationsTopology" in response.text
    assert "refreshOperationalEvents" in response.text
    assert "promoteSelectedOpsEvent" in response.text
    assert "openExportDraftFromOpsEvent" in response.text
    assert "applyOpsPreset" in response.text
    assert "openCanonicalRuntimeEventDirectory" in response.text
    assert "openOperationsTopologyContext" in response.text
    assert "Platform API" in response.text
    assert "Open Traffic" in response.text
    assert "/admin/api/ops/events?" in response.text
    assert "/admin/api/config/inbound-listeners" in response.text
    assert "Listener Spend Concentration" in response.text
    assert '/training/runs?' in response.text
    assert '/evaluation/runs?' in response.text
    assert "/models/local?" in response.text
    assert "/proxy/training-candidates?" in response.text
    assert "clear-candidates-filters" in response.text
    assert "/admin/api/exports?" in response.text
    assert "/admin/api/datasets/imports?" in response.text
    assert "/admin/api/datasets/versions?" in response.text
    assert "refreshPrompts" in response.text
    assert "refreshVirtualKeys" in response.text
    assert "refreshPricingCatalog" in response.text
    assert "refreshGuardrails" in response.text
    assert "refreshA2APeers" in response.text
    assert "refreshRestEndpoints" in response.text
    assert "inspectA2APeer" in response.text
    assert "inspectRestEndpoint" in response.text
    assert "seedA2AInvokeForm" in response.text
    assert "seedRestInvokeForm" in response.text
    assert "currentSelectedA2APeer" in response.text
    assert "currentSelectedRestEndpoint" in response.text
    assert "/admin/api/a2a/peers/" in response.text
    assert "/admin/api/a2a/peers?" in response.text
    assert "/admin/api/rest/endpoints?" in response.text
    assert "/admin/api/rest/endpoints/" in response.text
    assert "renderRoutePreview" in response.text
    assert "renderRequestDetail" in response.text
    assert "No normalized interaction traces were recorded for this event." in response.text
    assert "renderInteractionTraceTable" in response.text
    assert "No normalized interaction trace recorded for this A2A peer yet." in response.text
    assert "No normalized interaction trace recorded for this validation call yet." in response.text
    assert "No normalized interaction trace recorded for this REST endpoint yet." in response.text
    assert "normalizeFallbackChain" in response.text
    assert "renderFallbackChainTable" in response.text
    assert "Fallback Order" in response.text
    assert "openRequestHistoryContext" in response.text
    assert 'switchSubview("operations", "monitor")' in response.text
    assert "Open Traffic" in response.text
    assert "renderOpsColumnPresetControls" in response.text
    assert "renderSavedOpsPresetControls" in response.text
    assert "renderOpsActiveViewStrip" in response.text
    assert "renderOpsEventTrafficFilterOptions" in response.text
    assert "renderOpsEventTrafficScopeVisibility" in response.text
    assert "opsEventTrafficFiltersActive" in response.text
    assert "All discovered pools" in response.text
    assert "All discovered nodes" in response.text
    assert "All traffic origins" in response.text
    assert "loadSavedOpsPreset" in response.text
    assert "saveCurrentOpsPreset" in response.text
    assert "nav-operations-traffic" not in response.text
    assert "renderTrainingDetail" in response.text
    assert "runTrainingPreflight" in response.text
    assert "refreshTrainingRuntimeStatus" in response.text
    assert "renderTrainingRuntimeStatus" in response.text
    assert "refreshTrainingStudioStatus" in response.text
    assert "renderTrainingStudioStatus" in response.text
    assert "renderPipelineTrafficTables" in response.text
    assert "#candidates-filter-form" in response.text
    assert "listener_ids" in response.text
    assert "listener_id" in response.text
    assert "renderConnectivitySnapshotTable" in response.text
    assert "renderLlmTimeseriesCharts" in response.text
    assert "renderLlmTimeseriesChartGroups" in response.text
    assert "renderLlmTimeseriesLeaderboards" in response.text
    assert "renderLlmTimeseriesPresetPicker" in response.text
    assert "renderLlmTimeseriesMetricPicker" in response.text
    assert "loadLlmTimeseriesModel" in response.text
    assert "refreshLlmTimeseries" in response.text
    assert "/admin/api/ops/llm-timeseries?" in response.text
    assert "provider_429_count" in response.text
    assert "exact_cache_hit_count" in response.text
    assert "stream_partial_abort_count" in response.text
    assert "Open Vendor" in response.text
    assert "openConnectivityVendorContext" in response.text
    assert "openProviderGuideVendorContext" in response.text
    assert "Vendor LLM registered." in response.text


def test_admin_console_is_not_served_on_non_admin_listener() -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_inbound_listeners=[
            {
                "listener_id": "admin",
                "host": "0.0.0.0",
                "port": 8000,
                "published_host": "127.0.0.1",
                "published_port": 8000,
                "exposes_admin": True,
                "exposes_platform_api": True,
                "exposes_proxy": True,
            },
            {
                "listener_id": "public-api",
                "host": "0.0.0.0",
                "port": 8001,
                "published_host": "127.0.0.1",
                "published_port": 8001,
                "exposes_admin": False,
                "exposes_platform_api": False,
                "exposes_proxy": True,
            },
        ]
    )
    client = TestClient(app, base_url="http://127.0.0.1:8001")
    response = client.get("/admin")
    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "This listener does not expose the admin surface."


def test_platform_api_is_not_served_on_proxy_only_listener() -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_inbound_listeners=[
            {
                "listener_id": "admin",
                "host": "0.0.0.0",
                "port": 8000,
                "published_host": "127.0.0.1",
                "published_port": 8000,
                "exposes_admin": True,
                "exposes_platform_api": True,
                "exposes_proxy": True,
            },
            {
                "listener_id": "public-api",
                "host": "0.0.0.0",
                "port": 8001,
                "published_host": "127.0.0.1",
                "published_port": 8001,
                "exposes_admin": False,
                "exposes_platform_api": False,
                "exposes_proxy": True,
            },
        ]
    )
    client = TestClient(app, base_url="http://127.0.0.1:8001")
    response = client.get("/training/runs", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "This listener does not expose the platform API surface."


def test_proxy_api_is_served_on_proxy_listener() -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_inbound_listeners=[
            {
                "listener_id": "admin",
                "host": "0.0.0.0",
                "port": 8000,
                "published_host": "127.0.0.1",
                "published_port": 8000,
                "exposes_admin": True,
                "exposes_platform_api": True,
                "exposes_proxy": True,
            },
            {
                "listener_id": "public-api",
                "host": "0.0.0.0",
                "port": 8001,
                "published_host": "127.0.0.1",
                "published_port": 8001,
                "exposes_admin": False,
                "exposes_platform_api": False,
                "exposes_proxy": True,
            },
        ]
    )
    client = TestClient(app, base_url="http://127.0.0.1:8001")
    response = client.get("/v1/models", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()

    assert response.status_code == 200


def test_admin_route_preview_endpoint(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        admin,
        "classify_request",
        lambda request: {
            "domain": "coding",
            "task_type": "analysis",
            "privacy_level": "standard",
            "complexity": "medium",
            "route_tags": ["latency"],
            "region": "us-east",
        },
    )
    monkeypatch.setattr(
        admin,
        "select_route",
        lambda request_id, request, classification, settings, session=None: (
            captured.update({"listener_id": request.metadata.listener_id}) or SimpleNamespace(
            provider_key="groq",
            shadow_provider_keys=["openai"],
            selected_entry={"provider_key": "groq", "model_id": "llama-3.3-70b-versatile"},
            decision=RoutingDecision(
                routing_decision_id="rd_123",
                session_id=request.metadata.session_id,
                request_id=request_id,
                policy_version="policy_v1",
                selected_provider="groq",
                selected_provider_family="groq",
                selected_model="llama-3.3-70b-versatile",
                selected_mode="production",
                selected_entry_id="entry_groq_1",
                selected_pool_id="east-pool",
                selected_node_id="node-east-1",
                selected_node_role="execution",
                selected_node_labels=["gpu", "east"],
                selected_capacity_class="gpu-large",
                selected_balancing_strategy="session_affinity",
                selected_affinity_key="session_id",
                ranked_alternatives=[],
                decision_rationale="Prefer latency-optimized frontier route.",
                predicted_cost_class="low",
                predicted_latency_class="low",
                fallback_chain=[],
            ),
        )),
    )
    client = TestClient(app)
    response = client.post(
        "/admin/api/proxy/route-preview",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "proxy-auto",
            "temperature": 0.2,
            "max_tokens": 256,
            "session_id": "sess_preview",
            "listener_id": "internal-tools",
            "domain_hint": "coding",
            "task_type_hint": "analysis",
            "region_hint": "us-east",
            "route_tags": ["latency"],
            "messages": [{"role": "user", "content": "Review this patch."}],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_provider"] == "groq"
    assert payload["decision"]["selected_model"] == "llama-3.3-70b-versatile"
    assert payload["decision"]["selected_pool_id"] == "east-pool"
    assert payload["decision"]["selected_node_id"] == "node-east-1"
    assert payload["decision"]["selected_balancing_strategy"] == "session_affinity"
    assert payload["classification"]["domain"] == "coding"
    assert captured["listener_id"] == "internal-tools"


def test_list_proxy_requests_filters_by_selected_node_and_pool(monkeypatch) -> None:
    request_rows = [
        SimpleNamespace(
            id="req_1",
            session_id="sess_1",
            domain="coding",
            task_type="analysis",
            requested_model="proxy-auto",
            created_at=None,
            request_json={"metadata": {"listener_id": "admin", "prompt_template_name": "architecture_review", "prompt_template_version": 2}},
            effective_request_json={"metadata": {"prompt_template_selection_mode": "active", "prompt_template_rollout_percentage": 15.0}},
        ),
        SimpleNamespace(
            id="req_2",
            session_id="sess_2",
            domain="coding",
            task_type="analysis",
            requested_model="proxy-auto",
            created_at=None,
            request_json={"metadata": {"listener_id": "internal-tools", "prompt_template_name": "incident_summary", "prompt_template_version": 4}},
            effective_request_json={"metadata": {"prompt_template_selection_mode": "challenger_canary", "prompt_template_rollout_percentage": 15.0}},
        ),
    ]

    class FakeSession:
        def execute(self, _statement):
            class Result:
                def scalars(self_inner):
                    class Scalars:
                        def all(self_innermost):
                            return request_rows

                        def __iter__(self_innermost):
                            return iter(request_rows)

                    return Scalars()

            return Result()

    monkeypatch.setattr(admin, "request_summary_payload", lambda row: {
        "id": row.id,
        "session_id": row.session_id,
        "domain": row.domain,
        "task_type": row.task_type,
        "requested_model": row.requested_model,
        "listener_id": row.request_json.get("metadata", {}).get("listener_id"),
        "prompt_template_name": row.request_json.get("metadata", {}).get("prompt_template_name"),
        "prompt_template_version": row.request_json.get("metadata", {}).get("prompt_template_version"),
        "prompt_template_selection_mode": row.effective_request_json.get("metadata", {}).get("prompt_template_selection_mode"),
        "prompt_template_rollout_percentage": row.effective_request_json.get("metadata", {}).get("prompt_template_rollout_percentage"),
        "traffic_origin": "interactive",
        "automation_scope": None,
    })
    monkeypatch.setattr(
        admin,
        "latest_routing_decisions_by_request",
        lambda session, request_ids: {
            "req_1": SimpleNamespace(
                selected_provider="openai",
                selected_model="gpt-5.5",
                selected_mode="production",
                selected_pool_id="east-pool",
                selected_node_id="node-east-1",
                selected_node_role="execution",
                selected_balancing_strategy="session_affinity",
                selected_affinity_key="session_id",
            ),
            "req_2": SimpleNamespace(
                selected_provider="openai",
                selected_model="gpt-5.5",
                selected_mode="production",
                selected_pool_id="west-pool",
                selected_node_id="node-west-1",
                selected_node_role="execution",
                selected_balancing_strategy="session_affinity",
                selected_affinity_key="session_id",
            ),
        },
    )

    filtered_by_node = admin.list_proxy_requests(limit=20, session=FakeSession(), selected_node_id="node-east-1")
    assert [row["id"] for row in filtered_by_node] == ["req_1"]

    filtered_by_pool = admin.list_proxy_requests(limit=20, session=FakeSession(), selected_pool_id="west-pool")
    assert [row["id"] for row in filtered_by_pool] == ["req_2"]

    filtered_by_listener = admin.list_proxy_requests(limit=20, session=FakeSession(), listener_id="internal-tools")
    assert [row["id"] for row in filtered_by_listener] == ["req_2"]

    filtered_by_prompt = admin.list_proxy_requests(
        limit=20,
        session=FakeSession(),
        prompt_template_name="incident_summary",
        prompt_template_version=4,
    )
    assert [row["id"] for row in filtered_by_prompt] == ["req_2"]

    filtered_by_rollout = admin.list_proxy_requests(
        limit=20,
        session=FakeSession(),
        prompt_template_selection_mode="challenger_canary",
    )
    assert [row["id"] for row in filtered_by_rollout] == ["req_2"]


def test_admin_local_runtime_status_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        admin,
        "build_local_runtime_status",
        lambda session, settings: [
            {
                "runtime": "ollama",
                "configured": True,
                "reachable": True,
                "base_url": "http://localhost:11434",
                "package_alias_count": 2,
                "deployed_alias_count": 1,
                "active_route_count": 1,
                "models_visible": 3,
                "detail": "Runtime responded.",
                "package_aliases": ["coding-lora-v1", "coding-lora-v2"],
                "deployed_aliases": ["coding-lora-v2"],
                "active_route_aliases": ["coding-lora-v2"],
            }
        ],
    )
    client = TestClient(app)
    response = client.get("/admin/api/models/local-runtimes", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["runtime"] == "ollama"
    assert payload[0]["reachable"] is True
    assert payload[0]["package_alias_count"] == 2
    assert payload[0]["deployed_alias_count"] == 1


def test_admin_config_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/config")
    assert response.status_code == 401


def test_admin_config_returns_payload() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/config", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["llmproxy_openai_model"] == "gpt-5"
    assert "llmproxy_routing_strategy" in payload
    assert "llmproxy_logs_path" in payload


def test_admin_routing_settings_returns_payload() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/routing/settings", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert "llmproxy_routing_strategy" in payload
    assert "llmproxy_frontier_default_entries" in payload


def test_admin_routing_settings_update_persists_env_values(tmp_path) -> None:
    client = TestClient(app)
    env_file = tmp_path / ".env.routing"
    response = client.post(
        "/admin/api/routing/settings",
        headers={"Authorization": "Bearer change-me"},
        json={
            "routing_strategy": "latency",
            "frontier_default_entries": [
                {"provider_key": "groq", "model_id": "llama-3.3-70b-versatile", "domains": ["general"], "deployment_mode": "production"}
            ],
            "env_file": str(env_file),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["saved"] is True
    text = env_file.read_text(encoding="utf-8")
    assert "LLMPROXY_ROUTING_STRATEGY=latency" in text
    assert "LLMPROXY_FRONTIER_DEFAULT_ENTRIES=" in text


def test_admin_inbound_listener_update_persists_env_values(tmp_path) -> None:
    client = TestClient(app)
    env_file = tmp_path / ".env.listeners"
    response = client.post(
        "/admin/api/config/inbound-listeners",
        headers={"Authorization": "Bearer change-me"},
        json={
            "listeners": [
                {
                    "listener_id": "admin",
                    "name": "Admin",
                    "host": "0.0.0.0",
                    "port": 8000,
                    "published_host": "127.0.0.1",
                    "published_port": 8000,
                    "exposes_admin": True,
                    "exposes_platform_api": True,
                    "exposes_proxy": True,
                },
                {
                    "listener_id": "internal-tools",
                    "name": "Internal Tools",
                    "host": "0.0.0.0",
                    "port": 8001,
                    "published_host": "127.0.0.1",
                    "published_port": 8001,
                    "exposes_admin": False,
                    "exposes_platform_api": False,
                    "exposes_proxy": True,
                },
            ],
            "env_file": str(env_file),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] is True
    assert payload["restart_required"] is True
    assert payload["listeners"][0]["listener_id"] == "admin"
    text = env_file.read_text(encoding="utf-8")
    assert "LLMPROXY_INBOUND_LISTENERS=" in text
    assert "\"listener_id\": \"admin\"" in text


def test_admin_model_monitor_update_persists_env_values(tmp_path) -> None:
    client = TestClient(app)
    env_file = tmp_path / ".env.monitors"
    response = client.post(
        "/admin/api/config/model-monitors",
        headers={"Authorization": "Bearer change-me"},
        json={
            "monitors": [
                {
                    "provider_key": "anthropic",
                    "model_id": "claude-sonnet-4-6",
                    "frequency_minutes": 30,
                    "monitor_mode": "frontdoor_stream",
                    "enabled": True,
                }
            ],
            "env_file": str(env_file),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"] is True
    assert payload["restart_required"] is True
    assert payload["monitors"][0]["provider_key"] == "anthropic"
    text = env_file.read_text(encoding="utf-8")
    assert "LLMPROXY_MODEL_MONITORS=" in text
    assert "\"model_id\": \"claude-sonnet-4-6\"" in text


def test_admin_provider_guides_returns_cloudflare_tgi_and_replicate() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/providers/guides", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    provider_keys = {item["provider_key"] for item in payload["providers"]}
    assert "cloudflare_workers_ai" in provider_keys
    assert "huggingface_tgi" in provider_keys
    assert "replicate" in provider_keys


def test_admin_pricing_catalog_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/pricing/catalog", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert any(item["provider"] == "openai" and item["model"] == "gpt-5.5" for item in payload["items"])


def test_admin_guardrails_settings_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/guardrails/settings", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert "prompt_injection_blocking_enabled" in payload
    assert "pii_output_masking_enabled" in payload
    assert "blocked_output_patterns" in payload


def test_admin_training_runtime_status_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        admin,
        "get_reported_training_runtime_status",
        lambda: TrainingWorkerRuntimeStatus(
            ready=True,
            backend_import_ready=True,
            unsloth_command_configured=True,
            unsloth_command="python scripts/unsloth_backend.py",
            internal_api_base_url="http://api:8000",
            cuda_available=True,
            device_count=2,
            torch_version="2.7.0",
            unsloth_version="2026.6.0",
            dependencies=[
                TrainingRuntimeDependencyStatus(name="torch", available=True, detail="importable"),
                TrainingRuntimeDependencyStatus(name="unsloth", available=True, detail="importable"),
            ],
            errors=[],
            warnings=[],
        ),
    )
    client = TestClient(app)
    response = client.get("/admin/api/training/runtime-status", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["cuda_available"] is True
    assert payload["device_count"] == 2
    assert payload["backend_import_ready"] is True


def test_admin_training_studio_status_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        admin,
        "get_training_studio_status",
        lambda settings: TrainingStudioStatus(
            enabled=True,
            configured=True,
            external_url="http://127.0.0.1:8888",
            internal_url="http://unsloth-studio:8888",
            password_configured=True,
            reachable=True,
            status_code=302,
            detail="Studio responded.",
            notes=["Studio is deployed from the upstream unsloth/unsloth image."],
        ),
    )
    client = TestClient(app)
    response = client.get("/admin/api/training/studio-status", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["reachable"] is True
    assert payload["external_url"] == "http://127.0.0.1:8888"


def test_admin_observability_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/observability", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["prometheus"]["path"] == "/metrics/prometheus"
    assert "job_name" in payload["prometheus"]["scrape_config"]
    assert "service_name" in payload["otel"]


def test_admin_routing_topology_inventory_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        admin,
        "build_routing_topology_inventory",
        lambda session: {
            "policy_version": "rpol_live",
            "summary": {"node_count": 1, "pool_count": 1},
            "nodes": [
                {
                    "node_id": "node-east-1",
                    "node_role": "execution",
                    "capacity_class": "gpu-large",
                    "recent_request_count": 4,
                    "successful_request_count": 3,
                    "failed_request_count": 1,
                    "avg_latency_ms": 44.5,
                    "p95_latency_ms": 60,
                    "cooled_down": False,
                    "cooled_provider_count": 0,
                    "last_seen_at": "2026-06-08T12:00:00Z",
                    "pool_count": 1,
                    "entry_count": 2,
                    "provider_count": 1,
                    "model_count": 1,
                    "providers": ["openai"],
                    "models": ["gpt-5.5"],
                    "pool_ids": ["east-pool"],
                    "balancing_strategies": ["session_affinity"],
                    "node_labels": ["gpu", "east"],
                    "supports_local_models": True,
                    "supports_training": False,
                }
            ],
            "pools": [
                {
                    "pool_id": "east-pool",
                    "balancing_strategy": "session_affinity",
                    "affinity_key": "session_id",
                    "recent_request_count": 4,
                    "successful_request_count": 3,
                    "failed_request_count": 1,
                    "avg_latency_ms": 44.5,
                    "p95_latency_ms": 60,
                    "cooled_down": False,
                    "cooled_provider_count": 0,
                    "last_seen_at": "2026-06-08T12:00:00Z",
                    "entry_count": 2,
                    "node_count": 1,
                    "provider_count": 1,
                    "model_count": 1,
                    "total_weight": 2.0,
                    "providers": ["openai"],
                    "models": ["gpt-5.5"],
                    "node_ids": ["node-east-1"],
                    "node_roles": ["execution"],
                    "capacity_classes": ["gpu-large"],
                }
            ],
        },
    )
    client = TestClient(app)
    response = client.get("/admin/api/topology/routing-inventory", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["policy_version"] == "rpol_live"
    assert payload["nodes"][0]["node_id"] == "node-east-1"
    assert payload["pools"][0]["pool_id"] == "east-pool"


def test_admin_prompt_templates_endpoints(monkeypatch) -> None:
    created = []

    class FakeSession:
        def __init__(self) -> None:
            self.committed = False

        def execute(self, statement):
            text = str(statement).lower()

            class ScalarOneResult:
                def __init__(self_inner, value):
                    self_inner._value = value

                def scalar_one(self_inner):
                    return self_inner._value

            class ScalarList:
                def __init__(self_inner, items):
                    self_inner._items = items

                def all(self_inner):
                    return list(self_inner._items)

                def first(self_inner):
                    return self_inner._items[0] if self_inner._items else None

                def __iter__(self_inner):
                    return iter(self_inner._items)

            class Result:
                def __init__(self_inner, items):
                    self_inner._items = items

                def scalars(self_inner):
                    return ScalarList(self_inner._items)

            def filtered_rows():
                rows = list(created)
                for criterion in getattr(statement, "_where_criteria", ()):
                    key = getattr(getattr(criterion, "left", None), "key", None)
                    value = getattr(getattr(criterion, "right", None), "value", None)
                    operator_name = getattr(getattr(criterion, "operator", None), "__name__", "")
                    if key == "name" and operator_name == "eq":
                        rows = [row for row in rows if row.name == value]
                    elif key == "version" and operator_name == "eq":
                        rows = [row for row in rows if row.version == value]
                    elif key == "version" and operator_name == "ne":
                        rows = [row for row in rows if row.version != value]
                    elif key == "status" and operator_name == "eq":
                        rows = [row for row in rows if row.status == value]
                order_by = tuple(getattr(statement, "_order_by_clauses", ()) or ())
                if any("version" in str(clause).lower() and "desc" in str(clause).lower() for clause in order_by):
                    rows.sort(key=lambda item: item.version, reverse=True)
                limit_clause = getattr(statement, "_limit_clause", None)
                if limit_clause is not None:
                    rows = rows[: int(limit_clause.value)]
                return rows

            if "coalesce(max" in text:
                rows = filtered_rows()
                return ScalarOneResult(max((item.version for item in rows), default=0))
            entity = None
            if getattr(statement, "column_descriptions", None):
                entity = statement.column_descriptions[0].get("entity")
            if entity is admin.PromptTemplate:
                return Result(filtered_rows())
            return Result([])

        def add(self, item):
            created.append(item)

        def commit(self):
            self.committed = True

        def refresh(self, item):
            if getattr(item, "created_at", None) is None:
                item.created_at = datetime.now(timezone.utc)

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    create_response = client.post(
        "/admin/api/prompts",
        headers={"Authorization": "Bearer change-me"},
        json={
            "name": "architecture_review",
            "description": "Architecture review system prompt",
            "template_text": "Review {service_name} for {constraints}.",
            "variables": ["service_name", "constraints"],
            "model_override": "gpt-5.5",
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.json()
    assert created_payload["name"] == "architecture_review"
    assert created_payload["version"] == 1
    assert created_payload["status"] == "active"
    assert created_payload["metrics"] == {}

    create_draft_response = client.post(
        "/admin/api/prompts",
        headers={"Authorization": "Bearer change-me"},
        json={
            "name": "architecture_review",
            "description": "Draft revision",
            "template_text": "Draft review {service_name} for {constraints}.",
            "variables": ["service_name", "constraints"],
        },
    )
    assert create_draft_response.status_code == 201
    draft_payload = create_draft_response.json()
    assert draft_payload["version"] == 2
    assert draft_payload["status"] == "draft"

    list_response = client.get("/admin/api/prompts", headers={"Authorization": "Bearer change-me"})
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "architecture_review"
    assert {item["status"] for item in list_response.json()} == {"active", "draft"}
    assert all("metrics" in item for item in list_response.json())

    current_response = client.get("/admin/api/prompts/architecture_review", headers={"Authorization": "Bearer change-me"})
    assert current_response.status_code == 200
    assert current_response.json()["version"] == 1
    assert current_response.json()["status"] == "active"
    assert current_response.json()["metrics"] == {}
    assert current_response.json()["family_rollout"]["mode"] == "disabled"

    activate_response = client.post(
        "/admin/api/prompts/architecture_review/2/status",
        headers={"Authorization": "Bearer change-me"},
        json={"status": "active"},
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["version"] == 2
    assert activate_response.json()["status"] == "active"

    rollout_response = client.post(
        "/admin/api/prompts/architecture_review/rollout",
        headers={"Authorization": "Bearer change-me"},
        json={"challenger_version": 1, "mode": "canary", "traffic_percentage": 15},
    )
    assert rollout_response.status_code == 200
    assert rollout_response.json()["challenger_version"] == 1
    assert rollout_response.json()["mode"] == "canary"

    comparison_response = client.get(
        "/admin/api/prompts/architecture_review/comparison?compare_version=1",
        headers={"Authorization": "Bearer change-me"},
    )
    assert comparison_response.status_code == 200
    assert comparison_response.json()["baseline"]["version"] == 2
    assert comparison_response.json()["comparison"]["version"] == 1
    assert "recommendation" in comparison_response.json()

    policy_response = client.post(
        "/admin/api/prompts/architecture_review/auto-promotion-policy",
        headers={"Authorization": "Bearer change-me"},
        json={
            "enabled": True,
            "minimum_challenger_requests": 5,
            "min_candidate_yield_improvement_pct": 2.0,
            "max_error_rate_regression_pct": 1.0,
            "max_latency_regression_ms": 250.0,
            "max_cost_regression_usd": 0.001,
        },
    )
    assert policy_response.status_code == 200
    assert policy_response.json()["auto_promotion_policy"]["enabled"] is True

    auto_eval_response = client.post(
        "/admin/api/prompts/architecture_review/auto-promotion/evaluate",
        headers={"Authorization": "Bearer change-me"},
    )
    assert auto_eval_response.status_code == 200
    assert auto_eval_response.json()["executed"] is False

    promote_response = client.post(
        "/admin/api/prompts/architecture_review/promote-challenger?challenger_version=1",
        headers={"Authorization": "Bearer change-me"},
    )
    assert promote_response.status_code == 400

    render_response = client.post(
        "/admin/api/prompts/architecture_review/render",
        headers={"Authorization": "Bearer change-me"},
        json={"variables": {"service_name": "billing", "constraints": "high availability"}},
    )
    diff_response = client.get(
        "/admin/api/prompts/architecture_review/diff?from_version=1&to_version=2",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()
    assert render_response.status_code == 200
    assert "Draft review billing" in render_response.json()["rendered_text"]
    assert diff_response.status_code == 200
    assert diff_response.json()["name"] == "architecture_review"


def test_admin_replicate_prediction_queue_endpoint(monkeypatch) -> None:
    queued_job = type("Job", (), {"id": "job_rep_1", "job_type": "replicate.prediction"})()

    class FakeSession:
        def commit(self):
            return None

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr("app.api.admin.enqueue_replicate_prediction_job", lambda session, model, input_payload, wait_for_completion: queued_job)
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.post(
        "/admin/api/replicate/predictions",
        headers={"Authorization": "Bearer change-me"},
        json={"model": "black-forest-labs/flux-schnell", "input": {"prompt": "A cat"}, "wait_for_completion": True},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["queued"] is True
    assert payload["job_id"] == "job_rep_1"
    assert payload["job_type"] == "replicate.prediction"


def test_admin_replicate_prediction_validate_endpoint(monkeypatch) -> None:
    async def fake_run_replicate_prediction(
        *,
        settings,
        model,
        input_payload,
        wait_for_completion,
        include_interaction_trace=False,
        transport=None,
    ):
        if include_interaction_trace:
            return {
                "result": {"id": "pred_1", "status": "succeeded", "output": "ok"},
                "interaction_traces": [{"protocol": "rest", "operation": "prediction_create"}],
                "interaction_protocols": {"rest": 1},
            }
        return {"id": "pred_1", "status": "succeeded", "output": "ok"}

    monkeypatch.setattr("app.api.admin.run_replicate_prediction", fake_run_replicate_prediction)
    client = TestClient(app)
    response = client.post(
        "/admin/api/replicate/predictions/validate",
        headers={"Authorization": "Bearer change-me"},
        json={"model": "replicate/hello-world", "input": {"text": "Alice"}, "wait_for_completion": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "replicate/hello-world"
    assert payload["result"]["status"] == "succeeded"
    assert payload["interaction_protocols"] == {"rest": 1}
    assert payload["interaction_traces"][0]["protocol"] == "rest"


def test_admin_provider_validate_endpoint_returns_structured_failure(monkeypatch) -> None:
    class FakeProvider:
        provider_family = "huggingface_tgi"
        model_id = "tgi"

        async def invoke(self, request):
            raise RuntimeError("connection refused")

    monkeypatch.setattr("app.api.admin.get_provider_registry", lambda settings, session=None: {"huggingface_tgi": FakeProvider()})
    client = TestClient(app)
    response = client.post(
        "/admin/api/providers/validate",
        headers={"Authorization": "Bearer change-me"},
        json={"provider_key": "huggingface_tgi"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["provider_key"] == "huggingface_tgi"
    assert "connection refused" in payload["error"]


def test_admin_virtual_keys_create_list_and_disable() -> None:
    created: list[VirtualAPIKey] = []

    class FakeScalarResult:
        def __init__(self, items):
            self.items = items

        def all(self):
            return self.items

    class FakeExecuteResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return FakeScalarResult(self.items)

    class FakeSession:
        def add(self, item):
            if item.status is None:
                item.status = "active"
            if item.spend_usd is None:
                item.spend_usd = Decimal("0")
            created.append(item)

        def commit(self):
            return None

        def refresh(self, item):
            if item.created_at is None:
                item.created_at = datetime.now(timezone.utc)

        def execute(self, statement):
            return FakeExecuteResult(created)

        def get(self, model, key):
            for item in created:
                if item.id == key:
                    return item
            return None

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    create_response = client.post(
        "/admin/api/auth/virtual-keys",
        headers={"Authorization": "Bearer change-me"},
        json={
            "display_name": "Team A",
            "owner_id": "team_a",
            "models_allowed": ["gpt-5.5", "proxy-auto"],
            "rpm_limit": 90,
            "tpm_limit": 9000,
            "max_budget_usd": 25.0,
            "budget_reset_period": "monthly",
        },
    )
    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["token"].startswith("sk-")
    assert created_payload["models_allowed"] == ["gpt-5.5", "proxy-auto"]
    assert created_payload["rpm_limit"] == 90
    assert created_payload["tpm_limit"] == 9000
    assert created_payload["budget_reset_period"] == "monthly"
    assert created[0].key_hash == virtual_key_hash(created_payload["token"])

    list_response = client.get(
        "/admin/api/auth/virtual-keys",
        headers={"Authorization": "Bearer change-me"},
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == created_payload["id"]

    disable_response = client.post(
        f"/admin/api/auth/virtual-keys/{created_payload['id']}/disable",
        headers={"Authorization": "Bearer change-me"},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["status"] == "disabled"

    update_response = client.patch(
        f"/admin/api/auth/virtual-keys/{created_payload['id']}",
        headers={"Authorization": "Bearer change-me"},
        json={
            "models_allowed": ["proxy-auto"],
            "rpm_limit": 120,
            "tpm_limit": 12000,
            "max_budget_usd": 50.0,
            "budget_reset_period": "weekly",
            "display_name": "Team A Updated",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["models_allowed"] == ["proxy-auto"]
    assert update_response.json()["rpm_limit"] == 120
    assert update_response.json()["tpm_limit"] == 12000
    assert update_response.json()["budget_reset_period"] == "weekly"
    assert update_response.json()["display_name"] == "Team A Updated"

    rotate_response = client.post(
        f"/admin/api/auth/virtual-keys/{created_payload['id']}/rotate",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()
    assert rotate_response.status_code == 200
    rotated = rotate_response.json()
    assert rotated["token"].startswith("sk-")
    assert rotated["previous_key_prefix"] == created_payload["key_prefix"]


def test_admin_ops_live_returns_summary_and_logs(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(llmproxy_logs_path="/tmp/logs")

    class FakeScalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

        def first(self):
            return self._items[0] if self._items else None

        def __iter__(self):
            return iter(self._items)

    class FakeResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return FakeScalars(self._items)

    class FakeSession:
        def execute(self, _statement):
            return FakeResult([])

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr(
        "app.api.admin.tail_log_records",
        lambda settings, **kwargs: [{"level": "INFO", "message": "ok", "component": "test", "category": "runtime", "timestamp": "2026-06-05T00:00:00Z"}],
    )
    monkeypatch.setattr(
        "app.services.observability.build_streaming_telemetry",
        lambda settings, limit=500: {
            "stream_start_count": 1,
            "stream_complete_count": 1,
            "stream_failed_count": 0,
            "chunk_counts_by_provider": {"ollama": 4},
            "recent_stream_summaries": [{"component": "proxy.shadow", "provider": "ollama", "chunk_count": 4}],
        },
    )
    monkeypatch.setattr(
        "app.services.observability.provider_health_snapshot",
        lambda: {"openai": {"consecutive_failures": 2, "cooled_down": True, "cooldown_remaining_seconds": 30.0}},
    )
    monkeypatch.setattr(
        "app.services.observability.mcp_runtime_snapshot",
        lambda: {"cluster": {"server": "cluster", "tool_call_count": 2, "validation_count": 1, "failed_tool_calls": 0, "failed_validations": 0, "last_tool_name": "status_lookup", "last_tool_at": "2026-06-05T00:00:00Z", "last_validation_at": "2026-06-05T00:00:00Z", "last_error": None}},
    )
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.get("/admin/api/ops/live", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert payload["logs"][0]["message"] == "ok"
    assert payload["summary"]["streaming"]["stream_complete_count"] == 1
    assert payload["summary"]["provider_health"]["openai"]["cooled_down"] is True
    assert payload["summary"]["mcp_runtime"]["cluster"]["tool_call_count"] == 2


def test_admin_operations_logs_supports_listener_filter(monkeypatch) -> None:
    captured = {}

    def fake_tail_log_records(settings, **kwargs):
        captured.update(kwargs)
        return [{
            "level": "INFO",
            "message": "ok",
            "component": "proxy",
            "category": "runtime",
            "timestamp": "2026-06-05T00:00:00Z",
            "data": {"listener_id": "internal-tools"},
        }]

    monkeypatch.setattr("app.api.admin.tail_log_records", fake_tail_log_records)
    client = TestClient(app)
    response = client.get(
        "/admin/api/ops/logs?listener_id=internal-tools&paginated=true&limit=1&offset=0",
        headers={"Authorization": "Bearer change-me"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["data"]["listener_id"] == "internal-tools"
    assert captured["listener_id"] == "internal-tools"


def test_admin_operational_events_supports_class_and_listener_filters(monkeypatch) -> None:
    class FakeScalars:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

        def all(self):
            return self.items

    class FakeExecuteResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return FakeScalars(self.items)

    class FakeSession:
        def execute(self, _statement):
            return FakeExecuteResult([])

    def fake_session():
        yield FakeSession()

    def fake_tail_log_records(settings, **kwargs):
        return [
            {
                "level": "INFO",
                "message": "normal",
                "component": "proxy",
                "category": "runtime",
                "timestamp": "2026-06-05T00:00:00Z",
                "data": {"listener_id": "internal-tools"},
            },
            {
                "level": "ERROR",
                "message": "failed",
                "component": "proxy",
                "category": "runtime",
                "timestamp": "2026-06-05T00:01:00Z",
                "data": {"listener_id": "internal-tools"},
            },
            {
                "level": "INFO",
                "message": "audited",
                "component": "admin.config",
                "category": "audit",
                "audit": True,
                "timestamp": "2026-06-05T00:02:00Z",
                "data": {"listener_id": "admin"},
            },
        ]

    monkeypatch.setattr("app.api.admin.tail_log_records", fake_tail_log_records)
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.get(
        "/admin/api/ops/events?event_class=error&listener_id=internal-tools&paginated=true&limit=10&offset=0",
        headers={"Authorization": "Bearer change-me"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["event_class"] == "error"
    assert payload["items"][0]["training_opportunity"] is True
    assert payload["items"][0]["data"]["listener_id"] == "internal-tools"
    app.dependency_overrides.pop(admin.get_session, None)


def test_admin_operational_events_supports_log_class(monkeypatch) -> None:
    class FakeScalars:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

        def all(self):
            return self.items

    class FakeExecuteResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return FakeScalars(self.items)

    class FakeSession:
        def execute(self, _statement):
            return FakeExecuteResult([])

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr(
        "app.api.admin.tail_log_records",
        lambda settings, **kwargs: [
            {
                "level": "INFO",
                "message": "chat served",
                "component": "proxy.chat",
                "category": "runtime",
                "timestamp": "2026-06-05T00:00:00Z",
                "data": {"listener_id": "admin"},
            }
        ],
    )
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.get(
        "/admin/api/ops/events?event_class=log&paginated=true&limit=10&offset=0",
        headers={"Authorization": "Bearer change-me"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["event_class"] == "log"
    assert payload["items"][0]["component"] == "proxy.chat"
    app.dependency_overrides.pop(admin.get_session, None)


def test_admin_operational_events_supports_historical_scope(monkeypatch) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 6, 9, 12, 0, tzinfo=tz or timezone.utc)

    class FakeScalars:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

        def all(self):
            return self.items

    class FakeExecuteResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return FakeScalars(self.items)

    class FakeSession:
        def execute(self, _statement):
            return FakeExecuteResult([])

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr("app.api.admin.datetime", FrozenDateTime)
    monkeypatch.setattr(
        "app.api.admin.tail_log_records",
        lambda settings, **kwargs: [
            {
                "level": "INFO",
                "message": "recent",
                "component": "proxy.chat",
                "category": "runtime",
                "timestamp": "2026-06-09T10:00:00Z",
                "data": {"listener_id": "admin"},
            },
            {
                "level": "INFO",
                "message": "historical",
                "component": "proxy.chat",
                "category": "runtime",
                "timestamp": "2026-06-05T10:00:00Z",
                "data": {"listener_id": "admin"},
            },
        ],
    )
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.get(
        "/admin/api/ops/events?history_scope=historical&event_class=log&paginated=true&limit=10&offset=0",
        headers={"Authorization": "Bearer change-me"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["message"] == "historical"
    app.dependency_overrides.pop(admin.get_session, None)


def test_admin_llm_timeseries_aggregates_vendor_and_model_rows(tmp_path) -> None:
    request_rows = [
        SimpleNamespace(
            id="req_a",
            requested_model="gpt-5",
        ),
        SimpleNamespace(
            id="req_b",
            requested_model="gpt-5",
        ),
        SimpleNamespace(
            id="req_c",
            requested_model="gpt-4o",
        ),
        SimpleNamespace(
            id="req_d",
            requested_model="gpt-4o-mini",
        ),
    ]
    routing_rows = [
        SimpleNamespace(
            request_log_id="req_a",
            selected_provider="openai",
            selected_model="gpt-5",
            selected_mode="production",
            created_at=datetime(2026, 6, 9, 10, 5, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            request_log_id="req_b",
            selected_provider="openai",
            selected_model="gpt-5",
            selected_mode="fallback",
            created_at=datetime(2026, 6, 9, 10, 35, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            request_log_id="req_c",
            selected_provider="openai",
            selected_model="gpt-4o",
            selected_mode="production",
            created_at=datetime(2026, 6, 9, 11, 10, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            request_log_id="req_d",
            selected_provider="openai",
            selected_model="gpt-4o",
            selected_mode="production",
            created_at=datetime(2026, 6, 9, 11, 25, tzinfo=timezone.utc),
        ),
    ]
    selected_rows = [
        SimpleNamespace(
            request_log_id="req_a",
            provider="openai",
            model="gpt-5",
            response_role="selected_response",
            latency_ms=120,
            input_tokens=40,
            output_tokens=16,
            cost_estimate=Decimal("0.1200"),
            response_json={"streamed": True, "first_response_latency_ms": 45},
            created_at=datetime(2026, 6, 9, 10, 5, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            request_log_id="req_b",
            provider="openai",
            model="gpt-5",
            response_role="selected_response",
            latency_ms=180,
            input_tokens=48,
            output_tokens=20,
            cost_estimate=Decimal("0.1800"),
            response_json={"streamed": True, "first_response_latency_ms": 60},
            created_at=datetime(2026, 6, 9, 10, 35, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            request_log_id="req_c",
            provider="openai",
            model="gpt-4o",
            response_role="selected_response",
            latency_ms=90,
            input_tokens=22,
            output_tokens=12,
            cost_estimate=Decimal("0.0900"),
            response_json={"streamed": False},
            created_at=datetime(2026, 6, 9, 11, 10, tzinfo=timezone.utc),
        ),
    ]

    class FakeScalars:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

        def all(self):
            return self.items

    class FakeExecuteResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return FakeScalars(self.items)

    class FakeSession:
        def execute(self, _statement):
            entity = (_statement.column_descriptions[0] or {}).get("entity")
            entity_name = getattr(entity, "__name__", "")
            if entity_name == "RoutingDecisionRecord":
                return FakeExecuteResult(routing_rows)
            if entity_name == "ModelResponse":
                return FakeExecuteResult(selected_rows)
            if entity_name == "RequestLog":
                return FakeExecuteResult(request_rows)
            return FakeExecuteResult([])

    def fake_session():
        yield FakeSession()

    def fake_settings():
        yield Settings(llmproxy_logs_path=str(tmp_path))

    app.dependency_overrides[admin.get_session] = fake_session
    app.dependency_overrides[admin.get_runtime_settings] = fake_settings
    client = TestClient(app)
    response = client.get(
        "/admin/api/ops/llm-timeseries?provider_key=openai&window_hours=24&bucket_minutes=60",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.pop(admin.get_session, None)
    app.dependency_overrides.pop(admin.get_runtime_settings, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_key"] == "openai"
    assert payload["request_count"] == 4
    assert payload["summary"]["success_rate_pct"] == 75.0
    assert payload["summary"]["error_rate_pct"] == 25.0
    assert payload["summary"]["fallback_rate_pct"] == 25.0
    assert payload["summary"]["redirect_rate_pct"] == 25.0
    assert payload["summary"]["avg_first_response_latency_ms"] == 65.0
    assert payload["summary"]["p95_first_response_latency_ms"] == 90.0
    assert payload["summary"]["avg_total_latency_ms"] == 130.0
    assert payload["summary"]["p95_total_latency_ms"] == 180.0
    assert payload["summary"]["avg_input_tokens"] == 36.67
    assert payload["summary"]["avg_output_tokens"] == 16.0
    assert payload["summary"]["avg_total_tokens"] == 52.67
    assert payload["summary"]["avg_output_tokens_per_second"] == 125.93
    assert payload["summary"]["avg_cost_per_request"] == 0.13
    assert payload["summary"]["total_cost_usd"] == 0.39
    assert payload["summary"]["cost_per_1k_requests"] == 97.5
    assert payload["summary"]["rate_limit_event_count"] == 0
    assert payload["summary"]["stream_start_count"] == 0
    assert payload["summary"]["stream_complete_count"] == 0
    assert payload["summary"]["stream_failure_count"] == 0
    assert payload["summary"]["cache_hit_count"] == 0
    assert payload["summary"]["cache_miss_count"] == 0
    assert payload["summary"]["exact_cache_hit_count"] == 0
    assert payload["summary"]["semantic_cache_hit_count"] == 0
    assert payload["summary"]["provider_429_count"] == 0
    assert payload["summary"]["provider_429_request_count"] == 0
    assert payload["summary"]["provider_429_stream_count"] == 0
    assert payload["summary"]["stream_partial_abort_count"] == 0
    assert payload["summary"]["stream_prelude_failure_count"] == 0
    model_rollups = {row["model_id"]: row for row in payload["model_rollups"]}
    assert model_rollups["gpt-5"]["request_count"] == 2
    assert model_rollups["gpt-5"]["fallback_rate_pct"] == 50.0
    assert model_rollups["gpt-5"]["p95_total_latency_ms"] == 180.0
    assert model_rollups["gpt-5"]["exact_cache_hit_count"] == 0
    assert model_rollups["gpt-4o"]["redirect_rate_pct"] == 50.0
    assert model_rollups["gpt-4o"]["semantic_cache_hit_count"] == 0
    populated = [item for item in payload["series"] if item["request_count"]]
    assert len(populated) == 2
    assert populated[0]["request_count"] == 2
    assert populated[0]["success_rate_pct"] == 100.0
    assert populated[0]["fallback_rate_pct"] == 50.0
    assert populated[0]["avg_first_response_latency_ms"] == 52.5
    assert populated[0]["p95_first_response_latency_ms"] == 60.0
    assert populated[1]["request_count"] == 2
    assert populated[1]["success_rate_pct"] == 50.0
    assert populated[1]["error_rate_pct"] == 50.0
    assert populated[1]["redirect_rate_pct"] == 50.0
    assert populated[1]["avg_first_response_latency_ms"] == 90.0
    assert populated[1]["p95_total_latency_ms"] == 90.0


def test_admin_llm_timeseries_surfaces_log_backed_monitoring_metrics(monkeypatch, tmp_path) -> None:
    from app.services import llm_timeseries

    class FakeScalars:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

        def all(self):
            return self.items

    class FakeExecuteResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return FakeScalars(self.items)

    class FakeSession:
        def execute(self, _statement):
            return FakeExecuteResult([])

    def fake_session():
        yield FakeSession()

    def fake_settings():
        yield Settings(llmproxy_logs_path=str(tmp_path))

    records = [
        (
            {"timestamp": "2026-06-09T10:00:00+00:00", "component": "proxy.chat", "category": "stream", "message": "Streaming chat started", "data": {"provider_key": "openai", "model_id": "gpt-5"}},
            datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc),
        ),
        (
            {"timestamp": "2026-06-09T10:00:02+00:00", "component": "proxy.chat", "category": "stream", "message": "Streaming chat completed", "data": {"provider_key": "openai", "model_id": "gpt-5"}},
            datetime(2026, 6, 9, 10, 0, 2, tzinfo=timezone.utc),
        ),
        (
            {"timestamp": "2026-06-09T10:01:00+00:00", "component": "proxy.chat", "category": "cache", "message": "Response cache evaluated", "data": {"provider_key": "openai", "model_id": "gpt-5", "cache_outcome": "hit", "cache_layer": "exact"}},
            datetime(2026, 6, 9, 10, 1, tzinfo=timezone.utc),
        ),
        (
            {"timestamp": "2026-06-09T10:02:00+00:00", "component": "proxy.chat", "category": "cache", "message": "Response cache evaluated", "data": {"provider_key": "openai", "model_id": "gpt-5", "cache_outcome": "miss", "cache_layer": "semantic"}},
            datetime(2026, 6, 9, 10, 2, tzinfo=timezone.utc),
        ),
        (
            {"timestamp": "2026-06-09T10:03:00+00:00", "component": "proxy.chat", "category": "rate_limit", "message": "Rate limit denied request", "data": {"provider_key": "openai", "requested_model": "gpt-5"}},
            datetime(2026, 6, 9, 10, 3, tzinfo=timezone.utc),
        ),
        (
            {"timestamp": "2026-06-09T10:04:00+00:00", "component": "proxy.chat", "category": "provider_limit", "message": "Upstream provider returned 429", "data": {"provider_key": "openai", "model_id": "gpt-5", "phase": "request"}},
            datetime(2026, 6, 9, 10, 4, tzinfo=timezone.utc),
        ),
        (
            {"timestamp": "2026-06-09T10:05:00+00:00", "component": "proxy.chat", "category": "provider_limit", "message": "Upstream provider returned 429", "data": {"provider_key": "openai", "model_id": "gpt-5", "phase": "stream"}},
            datetime(2026, 6, 9, 10, 5, tzinfo=timezone.utc),
        ),
        (
            {"timestamp": "2026-06-09T10:06:00+00:00", "component": "proxy.chat", "category": "stream", "message": "Streaming chat failed", "data": {"provider_key": "openai", "model_id": "gpt-5", "stream_abort_phase": "partial_abort"}},
            datetime(2026, 6, 9, 10, 6, tzinfo=timezone.utc),
        ),
        (
            {"timestamp": "2026-06-09T10:07:00+00:00", "component": "proxy.chat", "category": "stream", "message": "Streaming chat failed", "data": {"provider_key": "openai", "model_id": "gpt-5", "stream_abort_phase": "prelude_failure"}},
            datetime(2026, 6, 9, 10, 7, tzinfo=timezone.utc),
        ),
    ]

    monkeypatch.setattr(llm_timeseries, "_iter_relevant_ops_records", lambda _settings, *, since: iter(records))

    app.dependency_overrides[admin.get_session] = fake_session
    app.dependency_overrides[admin.get_runtime_settings] = fake_settings
    client = TestClient(app)
    response = client.get(
        "/admin/api/ops/llm-timeseries?provider_key=openai&model_id=gpt-5&window_hours=24&bucket_minutes=60",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.pop(admin.get_session, None)
    app.dependency_overrides.pop(admin.get_runtime_settings, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["stream_start_count"] == 1
    assert payload["summary"]["stream_complete_count"] == 1
    assert payload["summary"]["rate_limit_event_count"] == 1
    assert payload["summary"]["cache_hit_count"] == 1
    assert payload["summary"]["cache_miss_count"] == 1
    assert payload["summary"]["exact_cache_hit_count"] == 1
    assert payload["summary"]["semantic_cache_hit_count"] == 0
    assert payload["summary"]["cache_hit_rate_pct"] == 50.0
    assert payload["summary"]["exact_cache_hit_rate_pct"] == 50.0
    assert payload["summary"]["semantic_cache_hit_rate_pct"] == 0.0
    assert payload["summary"]["stream_complete_rate_pct"] == 100.0
    assert payload["summary"]["provider_429_count"] == 2
    assert payload["summary"]["provider_429_request_count"] == 1
    assert payload["summary"]["provider_429_stream_count"] == 1
    assert payload["summary"]["stream_failure_count"] == 2
    assert payload["summary"]["stream_partial_abort_count"] == 1
    assert payload["summary"]["stream_prelude_failure_count"] == 1
    populated = [item for item in payload["series"] if any(item[key] for key in ("stream_start_count", "cache_hit_count", "rate_limit_event_count", "provider_429_count", "stream_failure_count"))]
    assert len(populated) == 1
    assert populated[0]["stream_start_count"] == 1
    assert populated[0]["stream_complete_count"] == 1
    assert populated[0]["stream_failure_count"] == 2
    assert populated[0]["stream_partial_abort_count"] == 1
    assert populated[0]["stream_prelude_failure_count"] == 1
    assert populated[0]["cache_hit_count"] == 1
    assert populated[0]["cache_miss_count"] == 1
    assert populated[0]["exact_cache_hit_count"] == 1
    assert populated[0]["semantic_cache_hit_count"] == 0
    assert populated[0]["rate_limit_event_count"] == 1
    assert populated[0]["provider_429_count"] == 2
    assert populated[0]["provider_429_request_count"] == 1
    assert populated[0]["provider_429_stream_count"] == 1


def test_admin_operational_events_supports_event_source_filter(monkeypatch) -> None:
    class FakeScalars:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

        def all(self):
            return self.items

    class FakeExecuteResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return FakeScalars(self.items)

    class FakeSession:
        def execute(self, statement):
            entity = statement.column_descriptions[0].get("entity")
            if entity is admin.JobQueueRecord:
                return FakeExecuteResult([
                    SimpleNamespace(
                        id="job_1",
                        job_type="evaluation.run",
                        status="pending",
                        attempts=0,
                        max_attempts=3,
                        available_at=None,
                        payload_json={"listener_id": "internal-tools"},
                        created_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
                        updated_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
                    )
                ])
            if entity is admin.IntegrationEvent:
                return FakeExecuteResult([
                    SimpleNamespace(
                        id="evt_1",
                        event_type="evaluation.completed",
                        source="scheduler",
                        payload_json={"listener_id": "admin"},
                        processed_at=None,
                        occurred_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
                        created_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
                    )
                ])
            return FakeExecuteResult([])

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr("app.api.admin.tail_log_records", lambda *args, **kwargs: [])
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.get(
        "/admin/api/ops/events?event_source=job&paginated=true&limit=10&offset=0",
        headers={"Authorization": "Bearer change-me"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["event_source"] == "job"
    assert payload["items"][0]["event_class"] == "job"
    app.dependency_overrides.pop(admin.get_session, None)


def test_admin_operational_events_supports_request_source_filter(monkeypatch) -> None:
    class FakeScalars:
        def __init__(self, items):
            self.items = items

        def __iter__(self):
            return iter(self.items)

        def all(self):
            return self.items

    class FakeExecuteResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return FakeScalars(self.items)

    request_rows = [
        admin.RequestLog(
            id="req_1",
            session_id="sess_1",
            request_json={
                "metadata": {
                    "listener_id": "admin",
                    "traffic_origin": "interactive",
                    "prompt_template_name": "architecture_review",
                    "prompt_template_version": 2,
                }
            },
            effective_request_json={
                "metadata": {
                    "prompt_template_name": "architecture_review",
                    "prompt_template_version": 2,
                    "prompt_template_selection_mode": "active",
                    "prompt_template_rollout_percentage": 15.0,
                }
            },
            requested_model="gpt-5",
            domain="general",
            task_type="chat",
            complexity="medium",
            privacy_level="standard",
            created_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        ),
        admin.RequestLog(
            id="req_2",
            session_id="sess_2",
            request_json={
                "metadata": {
                    "listener_id": "admin",
                    "traffic_origin": "interactive",
                    "prompt_template_name": "incident_summary",
                    "prompt_template_version": 4,
                }
            },
            effective_request_json={
                "metadata": {
                    "prompt_template_name": "incident_summary",
                    "prompt_template_version": 4,
                    "prompt_template_selection_mode": "challenger_canary",
                    "prompt_template_rollout_percentage": 15.0,
                }
            },
            requested_model="gpt-5",
            domain="general",
            task_type="chat",
            complexity="medium",
            privacy_level="standard",
            created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        ),
    ]

    response_rows = [
        admin.ModelResponse(
            id="resp_1",
            request_log_id="req_1",
            provider="openai",
            provider_family="OpenAI",
            model="gpt-5",
            latency_ms=320,
            input_tokens=120,
            output_tokens=80,
            cost_estimate=Decimal("0.010500"),
            finish_reason="stop",
            response_role="selected_response",
            response_json={"first_response_latency_ms": 140},
            created_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        ),
        admin.ModelResponse(
            id="resp_2",
            request_log_id="req_2",
            provider="openai",
            provider_family="OpenAI",
            model="gpt-5",
            latency_ms=750,
            input_tokens=200,
            output_tokens=150,
            cost_estimate=Decimal("0.025000"),
            finish_reason="stop",
            response_role="selected_response",
            response_json={"first_response_latency_ms": 220},
            created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        ),
    ]

    class FakeSession:
        def execute(self, statement):
            entity = statement.column_descriptions[0].get("entity")
            if entity is admin.RequestLog:
                return FakeExecuteResult(request_rows)
            if entity is admin.ModelResponse:
                return FakeExecuteResult(response_rows)
            return FakeExecuteResult([])

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr("app.api.admin.tail_log_records", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        "app.api.admin.latest_routing_decisions_by_request",
        lambda session, request_ids: {
            "req_1": SimpleNamespace(
                selected_provider="openai",
                selected_model="gpt-5",
                selected_mode="production",
                selected_pool_id="pool_main",
                selected_node_id="node_a",
                selected_node_role="primary",
                selected_balancing_strategy="weighted",
                selected_affinity_key=None,
            ),
            "req_2": SimpleNamespace(
                selected_provider="openai",
                selected_model="gpt-5",
                selected_mode="production",
                selected_pool_id="pool_main",
                selected_node_id="node_a",
                selected_node_role="primary",
                selected_balancing_strategy="weighted",
                selected_affinity_key=None,
            ),
        },
    )
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.get(
        "/admin/api/ops/events?event_source=request&selected_provider=openai&selected_model=gpt-5"
        "&listener_id=admin&prompt_template_name=incident_summary&prompt_template_version=4"
        "&prompt_template_selection_mode=challenger_canary"
        "&sort_by=latency_ms&sort_dir=desc&paginated=true&limit=10&offset=0",
        headers={"Authorization": "Bearer change-me"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["source_record_id"] == "req_2"
    assert payload["items"][0]["event_source"] == "request"
    assert payload["items"][0]["event_class"] == "request"
    assert payload["items"][0]["selected_provider"] == "openai"
    assert payload["items"][0]["selected_model"] == "gpt-5"
    assert payload["items"][0]["prompt_template_name"] == "incident_summary"
    assert payload["items"][0]["prompt_template_version"] == 4
    assert payload["items"][0]["prompt_template_selection_mode"] == "challenger_canary"
    assert payload["items"][0]["selected_pool_id"] == "pool_main"
    assert payload["items"][0]["selected_node_id"] == "node_a"
    assert payload["items"][0]["latency_ms"] == 750
    assert payload["items"][0]["first_response_latency_ms"] == 220
    assert payload["items"][0]["input_tokens"] == 200
    assert payload["items"][0]["output_tokens"] == 150
    assert payload["items"][0]["total_tokens"] == 350
    assert payload["items"][0]["cost_estimate"] == 0.025
    app.dependency_overrides.pop(admin.get_session, None)


def test_admin_promote_operational_event_candidate(monkeypatch) -> None:
    promoted = SimpleNamespace(id="cand_1", approval_status="pending", export_eligible=False)

    class FakeSession:
        def __init__(self):
            self.committed = False

        def commit(self):
            self.committed = True

    fake_session_instance = FakeSession()

    def fake_session():
        yield fake_session_instance

    monkeypatch.setattr(
        "app.api.admin._promote_operational_event_to_candidate",
        lambda session, **kwargs: promoted,
    )
    monkeypatch.setattr("app.api.admin.log_record", lambda *args, **kwargs: None)
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.post(
        "/admin/api/ops/events/promote-candidate",
        headers={"Authorization": "Bearer change-me"},
        json={
            "event": {
                "event_source": "ops_log",
                "event_class": "error",
                "message": "provider failed",
            },
            "domain": "operations",
            "task_type": "event_review",
            "approve_immediately": False,
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "promoted": True,
        "candidate_id": "cand_1",
        "approval_status": "pending",
        "export_eligible": False,
    }
    assert fake_session_instance.committed is True
    app.dependency_overrides.pop(admin.get_session, None)


def test_admin_streaming_support_returns_capabilities(monkeypatch) -> None:
    class FakeSession:
        def execute(self, _statement):
            class FakeResult:
                def scalars(self):
                    class FakeScalars:
                        def first(self):
                            return None
                    return FakeScalars()
            return FakeResult()

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr(
        "app.api.admin.list_provider_capabilities",
        lambda settings, session=None: [
            type(
                "Capability",
                (),
                {
                    "model_dump": lambda self, mode="json": {
                        "provider_name": "openai",
                        "provider_family": "OpenAI",
                        "model_id": "gpt-5.5",
                        "supports_streaming": True,
                        "supports_embeddings": True,
                        "supports_tools": False,
                        "max_context_tokens": 128000,
                        "max_output_tokens": 8192,
                    }
                },
            )()
        ],
    )
    monkeypatch.setattr("app.api.admin._streaming_route_examples", lambda session, settings: [{"requested_model": "proxy-auto", "selected_provider": "openai", "supports_streaming": True}])
    app.dependency_overrides[admin.get_runtime_settings] = lambda: admin.Settings(llmproxy_openai_api_key="")
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.get("/admin/api/proxy/streaming-support", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"][0]["provider_name"] == "openai"
    assert payload["providers"][0]["configured"] is False
    assert payload["route_examples"][0]["selected_provider"] == "openai"


def test_admin_streaming_validate_returns_chunk_preview(monkeypatch) -> None:
    async def fake_run_frontdoor_stream_validation_suite(*, request, settings, session, principal):
        return {
            "success": True,
            "listener_id": "admin",
            "listener_url": "http://127.0.0.1:8000",
            "requested_model": "gpt-5.5",
            "provider_key": "openai",
            "provider_family": "OpenAI",
            "model": "gpt-5.5",
            "execution_mode": "training",
            "traffic_origin": "learning_pipeline",
            "automation_owner_id": "train_stream_probe_test",
            "learning_pipeline_verified": True,
            "candidate_captured": True,
            "candidate_id": "cand_stream_test",
            "request_id": "req_stream_test",
            "preview_text": "Hello world",
            "finish_reason": "stop",
            "validation_scope": "default_only",
            "validated_by": principal.role,
        }

    monkeypatch.setattr(admin, "_run_frontdoor_stream_validation_suite", fake_run_frontdoor_stream_validation_suite)
    client = TestClient(app)
    response = client.post(
        "/admin/api/ops/streaming/validate",
        headers={"Authorization": "Bearer change-me"},
        json={"provider_key": "openai", "requested_model": "gpt-5.5", "execution_mode": "training", "prompt": "hello"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["provider_key"] == "openai"
    assert payload["preview_text"] == "Hello world"
    assert payload["finish_reason"] == "stop"
    assert payload["learning_pipeline_verified"] is True
    assert payload["candidate_id"] == "cand_stream_test"
    assert payload["validation_scope"] == "default_only"


def test_admin_streaming_validate_supports_all_discovered_scope(monkeypatch) -> None:
    async def fake_run_frontdoor_stream_validation_suite(*, request, settings, session, principal):
        assert request.validation_scope == "all_discovered"
        return {
            "success": False,
            "validation_scope": "all_discovered",
            "provider_key": request.provider_key,
            "requested_model": "gpt-5",
            "target_count": 2,
            "validated_count": 1,
            "failed_count": 1,
            "discovered_model_count": 3,
            "streamable_model_count": 2,
            "skipped_model_count": 1,
            "skipped_models": ["text-embedding-3-small"],
            "results": [
                {
                    "success": True,
                    "requested_model": "gpt-5",
                    "provider_key": "openai",
                    "model": "gpt-5",
                    "chunk_count": 2,
                },
                {
                    "success": False,
                    "requested_model": "gpt-5-mini",
                    "provider_key": "openai",
                    "model": "gpt-5-mini",
                    "chunk_count": 0,
                    "error": "probe failed",
                },
            ],
            "validated_by": principal.role,
        }

    monkeypatch.setattr(admin, "_run_frontdoor_stream_validation_suite", fake_run_frontdoor_stream_validation_suite)
    client = TestClient(app)
    response = client.post(
        "/admin/api/ops/streaming/validate",
        headers={"Authorization": "Bearer change-me"},
        json={"provider_key": "openai", "requested_model": "proxy-auto", "execution_mode": "training", "validation_scope": "all_discovered", "prompt": "hello"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["validation_scope"] == "all_discovered"
    assert payload["target_count"] == 2
    assert payload["validated_count"] == 1
    assert payload["failed_count"] == 1
    assert payload["streamable_model_count"] == 2
    assert payload["skipped_models"] == ["text-embedding-3-small"]
    assert [item["requested_model"] for item in payload["results"]] == ["gpt-5", "gpt-5-mini"]


def test_run_frontdoor_stream_validation_suite_supports_default_scope(monkeypatch) -> None:
    from app.api.dependencies import AuthPrincipal

    calls: list[str] = []

    async def fake_run_frontdoor_stream_validation(*, request, settings, session, principal):
        calls.append(request.requested_model)
        return {
            "success": True,
            "requested_model": request.requested_model,
            "provider_key": request.provider_key,
            "model": request.requested_model,
            "chunk_count": 1,
            "validated_by": principal.role,
        }

    monkeypatch.setattr(admin, "_run_frontdoor_stream_validation", fake_run_frontdoor_stream_validation)
    monkeypatch.setattr(
        admin,
        "get_provider_registry",
        lambda settings, session=None: {"openai": type("Provider", (), {"model_id": "gpt-5", "provider_family": "OpenAI"})()},
    )

    result = asyncio.run(
        admin._run_frontdoor_stream_validation_suite(
            request=admin.StreamingValidationRequest(
                provider_key="openai",
                requested_model="proxy-auto",
                execution_mode="interactive",
                validation_scope="default_only",
            ),
            settings=Settings(),
            session=None,
            principal=AuthPrincipal(token="change-me", role="operator"),
        )
    )

    assert calls == ["gpt-5"]
    assert result["success"] is True
    assert result["requested_model"] == "gpt-5"
    assert result["validation_scope"] == "default_only"
    assert result["target_count"] == 1
    assert result["validated_count"] == 1


def test_run_frontdoor_stream_validation_suite_supports_all_discovered_scope(monkeypatch) -> None:
    from app.api.dependencies import AuthPrincipal
    from app.schemas.provider import ProviderCapability

    calls: list[str] = []

    async def fake_run_frontdoor_stream_validation(*, request, settings, session, principal):
        calls.append(request.requested_model)
        if request.requested_model == "gpt-5-mini":
            raise RuntimeError("probe failed")
        return {
            "success": True,
            "requested_model": request.requested_model,
            "provider_key": request.provider_key,
            "model": request.requested_model,
            "chunk_count": 2,
            "validated_by": principal.role,
        }

    async def fake_list_provider_capabilities_async(settings, session=None, *, allowed_models=None):
        return [
            ProviderCapability(provider_family="OpenAI", provider_name="openai", model_id="gpt-5", supports_streaming=True, supports_tools=True),
            ProviderCapability(provider_family="OpenAI", provider_name="openai", model_id="gpt-5-mini", supports_streaming=True, supports_tools=True),
            ProviderCapability(provider_family="OpenAI", provider_name="openai", model_id="text-embedding-3-small", supports_streaming=False, supports_embeddings=True),
        ]

    monkeypatch.setattr(admin, "_run_frontdoor_stream_validation", fake_run_frontdoor_stream_validation)
    monkeypatch.setattr(admin, "list_provider_capabilities_async", fake_list_provider_capabilities_async)
    monkeypatch.setattr(
        admin,
        "get_provider_registry",
        lambda settings, session=None: {"openai": type("Provider", (), {"model_id": "gpt-5", "provider_family": "OpenAI"})()},
    )

    result = asyncio.run(
        admin._run_frontdoor_stream_validation_suite(
            request=admin.StreamingValidationRequest(
                provider_key="openai",
                requested_model="proxy-auto",
                execution_mode="interactive",
                validation_scope="all_discovered",
            ),
            settings=Settings(),
            session=None,
            principal=AuthPrincipal(token="change-me", role="operator"),
        )
    )

    assert calls == ["gpt-5", "gpt-5-mini"]
    assert result["success"] is False
    assert result["validation_scope"] == "all_discovered"
    assert result["target_count"] == 2
    assert result["validated_count"] == 1
    assert result["failed_count"] == 1
    assert result["streamable_model_count"] == 2
    assert result["skipped_model_count"] == 1
    assert result["skipped_models"] == ["text-embedding-3-small"]
    assert [item["requested_model"] for item in result["results"]] == ["gpt-5", "gpt-5-mini"]


def test_run_frontdoor_stream_validation_suite_uses_cache_and_subset_filter(monkeypatch) -> None:
    from app.api.dependencies import AuthPrincipal
    from app.schemas.provider import ProviderCapability

    admin.STREAMING_VALIDATION_SUITE_CACHE.clear()
    calls: list[str] = []

    async def fake_run_frontdoor_stream_validation(*, request, settings, session, principal):
        calls.append(request.requested_model)
        return {
            "success": True,
            "requested_model": request.requested_model,
            "provider_key": request.provider_key,
            "model": request.requested_model,
            "validated_by": principal.role,
        }

    async def fake_list_provider_capabilities_async(settings, session=None, *, allowed_models=None):
        return [
            ProviderCapability(provider_family="OpenAI", provider_name="openai", model_id="gpt-5", supports_streaming=True, supports_tools=True),
            ProviderCapability(provider_family="OpenAI", provider_name="openai", model_id="computer-use-preview", supports_streaming=True, supports_tools=True),
            ProviderCapability(provider_family="OpenAI", provider_name="openai", model_id="gpt-5-mini", supports_streaming=True, supports_tools=True),
        ]

    monkeypatch.setattr(admin, "_run_frontdoor_stream_validation", fake_run_frontdoor_stream_validation)
    monkeypatch.setattr(admin, "list_provider_capabilities_async", fake_list_provider_capabilities_async)
    monkeypatch.setattr(
        admin,
        "get_provider_registry",
        lambda settings, session=None: {"openai": type("Provider", (), {"model_id": "gpt-5", "provider_family": "OpenAI"})()},
    )

    request = admin.StreamingValidationRequest(
        provider_key="openai",
        requested_model="proxy-auto",
        execution_mode="interactive",
        validation_scope="all_discovered",
        target_filter="chat_capable_subset",
        max_concurrency=3,
        cache_ttl_seconds=900,
        use_cached_results=True,
    )

    first = asyncio.run(
        admin._run_frontdoor_stream_validation_suite(
            request=request,
            settings=Settings(),
            session=None,
            principal=AuthPrincipal(token="change-me", role="operator"),
        )
    )
    second = asyncio.run(
        admin._run_frontdoor_stream_validation_suite(
            request=request,
            settings=Settings(),
            session=None,
            principal=AuthPrincipal(token="change-me", role="operator"),
        )
    )

    assert calls == ["gpt-5", "gpt-5-mini"]
    assert first["chat_capable_subset_count"] == 2
    assert first["target_filter"] == "chat_capable_subset"
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["validated_count"] == 2


def test_admin_mcp_servers_returns_inventory(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_mcp_servers={
            "cluster": {
                "transport": "stdio",
                "command": "python3",
                "args": ["/tmp/mcp_server.py"],
                "timeout_seconds": 12.0,
            }
        }
    )
    monkeypatch.setattr(
        "app.api.admin._list_mcp_tools",
        lambda settings, server_name: __import__("asyncio").sleep(0, result=[
            {"name": "status_lookup", "description": "Get status", "inputSchema": {"type": "object"}}
        ]),
    )
    client = TestClient(app)
    response = client.get("/admin/api/mcp/servers", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["server_count"] == 1
    assert payload["tool_count"] == 1
    assert payload["servers"][0]["server"] == "cluster"
    assert payload["servers"][0]["tools"][0]["name"] == "status_lookup"


def test_admin_mcp_server_validate_returns_diagnostics(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_mcp_servers={
            "cluster": {
                "transport": "stdio",
                "command": "python3",
                "args": ["/tmp/mcp_server.py"],
                "timeout_seconds": 12.0,
            }
        }
    )
    monkeypatch.setattr(
        "app.api.admin.inspect_mcp_server",
        lambda settings, server_name: __import__("asyncio").sleep(
            0,
            result={
                "server": server_name,
                "transport": "stdio",
                "command": "python3",
                "args": ["/tmp/mcp_server.py"],
                "cwd": None,
                "timeout_seconds": 12.0,
                "tool_count": 1,
                "tools": [{"name": "status_lookup", "description": "Get status", "input_schema": {"type": "object"}}],
                "validated": True,
                "latency_ms": 7,
            },
        ),
    )
    client = TestClient(app)
    response = client.post("/admin/api/mcp/servers/cluster/validate", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["server"] == "cluster"
    assert payload["validated"] is True
    assert payload["latency_ms"] == 7


def test_admin_a2a_peers_returns_inventory(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_a2a_peers={
            "planner": {
                "label": "Planner Agent",
                "endpoint": "http://example.test:9000",
                "transport": "http",
                "protocol": "a2a",
                "capabilities": ["plan", "delegate"],
            }
        }
    )
    monkeypatch.setattr(
        "app.api.admin.list_a2a_peers",
        lambda settings: __import__("asyncio").sleep(
            0,
            result=[
                {
                    "peer": "planner",
                    "label": "Planner Agent",
                    "transport": "http",
                    "protocol": "a2a",
                    "configured": True,
                    "capability_count": 2,
                    "capabilities": ["plan", "delegate"],
                }
            ],
        ),
    )
    client = TestClient(app)
    response = client.get("/admin/api/a2a/peers", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["peer_count"] == 1
    assert payload["capability_count"] == 2
    assert payload["peers"][0]["peer"] == "planner"


def test_admin_a2a_peer_validate_returns_diagnostics(monkeypatch) -> None:
    class FakeSession:
        commit_count = 0
        rollback_count = 0

        def commit(self):
            self.commit_count += 1

        def rollback(self):
            self.rollback_count += 1

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_a2a_peers={
            "planner": {
                "label": "Planner Agent",
                "endpoint": "http://example.test:9000",
            }
        }
    )
    emitted = []
    app.dependency_overrides[admin.get_session] = fake_session
    monkeypatch.setattr(
        "app.api.admin.inspect_a2a_peer",
        lambda settings, peer_name: __import__("asyncio").sleep(
            0,
            result={
                "peer": peer_name,
                "label": "Planner Agent",
                "transport": "http",
                "protocol": "a2a",
                "configured": True,
                "validated": True,
                "status_code": 200,
                "latency_ms": 9,
                "discovered_capabilities": ["plan", "delegate"],
                "interaction_traces": [{"protocol": "a2a", "operation": "discovery_document"}],
                "interaction_protocols": {"a2a": 1},
            },
        ),
    )
    monkeypatch.setattr(
        "app.api.admin.emit_event",
        lambda session, event_type, source, payload: emitted.append((event_type, source, payload)),
    )
    client = TestClient(app)
    response = client.post("/admin/api/a2a/peers/planner/validate", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["peer"] == "planner"
    assert payload["validated"] is True
    assert payload["latency_ms"] == 9
    assert payload["interaction_protocols"] == {"a2a": 1}
    assert emitted[0][0] == "integration.a2a.validated"


def test_admin_a2a_peer_invoke_returns_result(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_a2a_peers={
            "planner": {
                "label": "Planner Agent",
                "endpoint": "http://example.test:9000",
            }
        }
    )
    monkeypatch.setattr(
        "app.api.admin.invoke_a2a_peer",
        lambda settings, peer_name, capability, input_payload: __import__("asyncio").sleep(
            0,
            result={
                "peer": peer_name,
                "label": "Planner Agent",
                "protocol": "a2a",
                "invoked": True,
                "invoked_capability": capability,
                "status_code": 200,
                "result": {"status": "ok"},
                "interaction_traces": [{"protocol": "a2a", "operation": "invoke_capability"}],
                "interaction_protocols": {"a2a": 1},
            },
        ),
    )
    client = TestClient(app)
    response = client.post(
        "/admin/api/a2a/peers/planner/invoke",
        headers={"Authorization": "Bearer change-me"},
        json={"capability": "plan", "input": {"goal": "Review this request"}},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["peer"] == "planner"
    assert payload["invoked"] is True
    assert payload["invoked_capability"] == "plan"
    assert payload["interaction_protocols"] == {"a2a": 1}


def test_admin_rest_endpoints_returns_inventory(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_rest_endpoints={
            "status_api": {
                "label": "Status API",
                "endpoint": "http://example.test:9100",
                "method": "POST",
            }
        }
    )
    monkeypatch.setattr(
        "app.api.admin.list_rest_endpoints",
        lambda settings: __import__("asyncio").sleep(
            0,
            result=[
                {
                    "endpoint_name": "status_api",
                    "label": "Status API",
                    "protocol": "rest",
                    "transport": "http",
                    "configured": True,
                    "default_method": "POST",
                }
            ],
        ),
    )
    client = TestClient(app)
    response = client.get("/admin/api/rest/endpoints", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["endpoint_count"] == 1
    assert payload["configured_count"] == 1
    assert payload["endpoints"][0]["endpoint_name"] == "status_api"


def test_admin_rest_endpoint_validate_returns_diagnostics(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_rest_endpoints={
            "status_api": {
                "label": "Status API",
                "endpoint": "http://example.test:9100",
            }
        }
    )
    monkeypatch.setattr(
        "app.api.admin.inspect_rest_endpoint",
        lambda settings, endpoint_name: __import__("asyncio").sleep(
            0,
            result={
                "endpoint_name": endpoint_name,
                "label": "Status API",
                "protocol": "rest",
                "configured": True,
                "validated": True,
                "status_code": 200,
                "latency_ms": 11,
                "interaction_traces": [{"protocol": "rest", "operation": "validate_endpoint"}],
                "interaction_protocols": {"rest": 1},
            },
        ),
    )
    client = TestClient(app)
    response = client.post("/admin/api/rest/endpoints/status_api/validate", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["endpoint_name"] == "status_api"
    assert payload["validated"] is True
    assert payload["interaction_protocols"] == {"rest": 1}


def test_admin_rest_endpoint_invoke_returns_result(monkeypatch) -> None:
    class FakeSession:
        commit_count = 0
        rollback_count = 0

        def commit(self):
            self.commit_count += 1

        def rollback(self):
            self.rollback_count += 1

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_rest_endpoints={
            "status_api": {
                "label": "Status API",
                "endpoint": "http://example.test:9100",
            }
        }
    )
    emitted = []
    app.dependency_overrides[admin.get_session] = fake_session
    monkeypatch.setattr(
        "app.api.admin.invoke_rest_endpoint",
        lambda settings, endpoint_name, method, path, input_payload: __import__("asyncio").sleep(
            0,
            result={
                "endpoint_name": endpoint_name,
                "label": "Status API",
                "protocol": "rest",
                "invoked": True,
                "invoked_method": method,
                "status_code": 200,
                "result": {"status": "ok"},
                "interaction_traces": [{"protocol": "rest", "operation": "invoke_endpoint"}],
                "interaction_protocols": {"rest": 1},
            },
        ),
    )
    monkeypatch.setattr(
        "app.api.admin.emit_event",
        lambda session, event_type, source, payload: emitted.append((event_type, source, payload)),
    )
    client = TestClient(app)
    response = client.post(
        "/admin/api/rest/endpoints/status_api/invoke",
        headers={"Authorization": "Bearer change-me"},
        json={"method": "POST", "path": "/api/status", "input": {"id": "1234"}},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["endpoint_name"] == "status_api"
    assert payload["invoked"] is True
    assert payload["invoked_method"] == "POST"
    assert payload["interaction_protocols"] == {"rest": 1}
    assert emitted[0][0] == "integration.rest.invoked"


def test_admin_jobs_retry_requires_operator() -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(llmproxy_automation_tokens=["automation-token"])
    client = TestClient(app)
    response = client.post(
        "/admin/api/jobs/job_1/retry",
        headers={"Authorization": "Bearer automation-token"},
        json={"reset_attempts": True, "available_now": True},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 403


def test_admin_jobs_retry_mutates_job(monkeypatch) -> None:
    from datetime import datetime, timezone

    job = type(
        "Job",
        (),
            {
                "id": "job_1",
                "job_type": "kpi.generate",
                "status": "failed",
                "payload_json": {},
            "attempts": 3,
            "max_attempts": 3,
            "available_at": datetime.now(timezone.utc),
            "claimed_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
            "last_error": "boom",
            "created_at": datetime.now(timezone.utc),
        },
    )()

    class FakeSession:
        def get(self, model, key):
            assert key == "job_1"
            return job

        def commit(self):
            return None

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.post(
        "/admin/api/jobs/job_1/retry",
        headers={"Authorization": "Bearer change-me"},
        json={"reset_attempts": True, "available_now": True},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["retried"] is True
    assert payload["job"]["status"] == "pending"
