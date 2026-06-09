#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_DIR="${REPO_ROOT}/infra/compose"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
ENV_EXAMPLE="${COMPOSE_DIR}/.env.example"
ENV_LOCAL="${COMPOSE_DIR}/.env.local"
OPENAI_KEY_FILE="${REPO_ROOT}/openai-api.key"
ANTHROPIC_KEY_FILE="${REPO_ROOT}/anthropic-api.key"
PROFILE="core"
REPORT_ONLY=0
JSON_OUTPUT=0
INSTALL_DEPS=0

log() {
  printf '[llmproxy-install] %s\n' "$*"
}

warn() {
  printf '[llmproxy-install] WARN: %s\n' "$*" >&2
}

die() {
  printf '[llmproxy-install] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

have_command() {
  command -v "$1" >/dev/null 2>&1
}

json_escape() {
  printf '%s' "${1:-}" | awk '
    BEGIN { ORS="" }
    {
      gsub(/\\/,"\\\\")
      gsub(/"/,"\\\"")
      gsub(/\r/,"\\r")
      gsub(/\n/,"\\n")
      print
    }
  '
}

usage() {
  cat <<EOF
Usage:
  ${REPO_ROOT}/scripts/install-local-macos.sh [--profile core|training|full] [--report] [--json] [--install-deps]
  ${REPO_ROOT}/scripts/install-local-macos.sh --with-training

Options:
  --profile core|training|full
      core     Start postgres, redis, jaeger, api, worker, scheduler.
      training Start core services plus training-worker.
      full     Start core services plus training-worker and unsloth-studio.

  --with-training
      Backward-compatible alias for --profile full.

  --report
      Print preflight and live provider-readiness summaries. If the stack is not
      running yet, only the preflight summary is shown.

  --json
      Emit the report in JSON form. Intended for use with --report.

  --install-deps
      Install missing macOS prerequisites when possible, including Homebrew,
      curl, and Docker Desktop.

  -h, --help
      Show this help text.
EOF
}

profile_services() {
  case "${PROFILE}" in
    core)
      printf '%s\n' postgres redis jaeger api worker scheduler
      ;;
    training)
      printf '%s\n' postgres redis jaeger api worker scheduler training-worker
      ;;
    full)
      printf '%s\n' postgres redis jaeger api worker scheduler training-worker unsloth-studio
      ;;
    *)
      die "Unknown profile: ${PROFILE}"
      ;;
  esac
}

reconcile_optional_services() {
  case "${PROFILE}" in
    core)
      docker compose -f "${COMPOSE_FILE}" stop training-worker unsloth-studio >/dev/null 2>&1 || true
      ;;
    training)
      docker compose -f "${COMPOSE_FILE}" stop unsloth-studio >/dev/null 2>&1 || true
      ;;
    full)
      ;;
  esac
}

ensure_homebrew() {
  if have_command brew; then
    return 0
  fi
  log "Homebrew is missing. Installing Homebrew..."
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  have_command brew || die "Homebrew installation finished, but 'brew' is still unavailable."
}

install_missing_dependencies() {
  local installed_any=0

  if ! have_command curl; then
    ensure_homebrew
    log "Installing curl..."
    brew install curl
    installed_any=1
  fi

  if [[ ! -d "/Applications/Docker.app" ]] || ! have_command docker || ! docker compose version >/dev/null 2>&1; then
    ensure_homebrew
    log "Installing Docker Desktop..."
    brew install --cask docker
    installed_any=1
  fi

  if [[ "${installed_any}" -eq 1 ]]; then
    hash -r
  fi
}

dependency_summary_json() {
  local docker_cli docker_compose curl_cli brew_cli docker_app
  docker_cli=false
  docker_compose=false
  curl_cli=false
  brew_cli=false
  docker_app=false
  have_command docker && docker_cli=true
  docker compose version >/dev/null 2>&1 && docker_compose=true
  have_command curl && curl_cli=true
  have_command brew && brew_cli=true
  [[ -d "/Applications/Docker.app" ]] && docker_app=true

  cat <<EOF
{
  "docker_cli": ${docker_cli},
  "docker_compose": ${docker_compose},
  "curl": ${curl_cli},
  "homebrew": ${brew_cli},
  "docker_desktop_app": ${docker_app}
}
EOF
}

env_value() {
  local key="$1"
  local source_file
  for source_file in "${ENV_LOCAL}" "${ENV_EXAMPLE}"; do
    [[ -f "${source_file}" ]] || continue
    local value=""
    value="$(awk -F= -v target="${key}" '$1 == target {print substr($0, index($0, "=") + 1)}' "${source_file}" | tail -n 1)"
    if [[ -n "${value}" ]]; then
      printf '%s\n' "${value}"
      return 0
    fi
  done
}

set_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  local tmp_file
  tmp_file="$(mktemp)"
  if [[ -f "${file}" ]] && grep -q "^${key}=" "${file}"; then
    awk -v key="${key}" -v value="${value}" '
      index($0, key "=") == 1 { print key "=" value; next }
      { print }
    ' "${file}" > "${tmp_file}"
    mv "${tmp_file}" "${file}"
    return
  fi
  if [[ -f "${file}" ]]; then
    cat "${file}" > "${tmp_file}"
  fi
  {
    [[ -s "${tmp_file}" ]] && printf '\n'
    printf '%s=%s\n' "${key}" "${value}"
  } >> "${tmp_file}"
  mv "${tmp_file}" "${file}"
}

wait_for_docker() {
  local attempts=120
  local i
  for ((i = 1; i <= attempts; i += 1)); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_health() {
  local url="$1"
  local attempts=120
  local i
  for ((i = 1; i <= attempts; i += 1)); do
    local body=""
    if body="$(curl -fsS "${url}" 2>/dev/null)"; then
      if printf '%s' "${body}" | tr -d '\n' | grep -q '"status":"ok"'; then
        return 0
      fi
    fi
    sleep 2
  done
  return 1
}

build_report_context() {
  REPORT_DOCKER_STATE="not ready"
  REPORT_ENV_LOCAL_STATE="missing"
  REPORT_OPENAI_KEY_STATE="missing"
  REPORT_ANTHROPIC_KEY_STATE="missing"
  REPORT_PUBLISHED_PORT="$(env_value "LLMPROXY_API_PORT")"
  [[ -n "${REPORT_PUBLISHED_PORT}" ]] || REPORT_PUBLISHED_PORT="8000"
  REPORT_BEARER_TOKEN="$(env_value "LLMPROXY_BEARER_TOKEN")"
  [[ -n "${REPORT_BEARER_TOKEN}" ]] || REPORT_BEARER_TOKEN="change-me"
  REPORT_OLLAMA_BASE_URL="$(env_value "LLMPROXY_OLLAMA_BASE_URL" || true)"
  REPORT_OPENAI_MODEL="$(env_value "LLMPROXY_OPENAI_MODEL" || true)"
  REPORT_ANTHROPIC_MODEL="$(env_value "LLMPROXY_ANTHROPIC_MODEL" || true)"
  REPORT_ADMIN_URL="http://127.0.0.1:${REPORT_PUBLISHED_PORT}/admin"
  REPORT_HEALTH_URL="http://127.0.0.1:${REPORT_PUBLISHED_PORT}/health"
  REPORT_JAEGER_URL="http://127.0.0.1:16686"

  have_command docker && docker info >/dev/null 2>&1 && REPORT_DOCKER_STATE="ready"
  [[ -f "${ENV_LOCAL}" ]] && REPORT_ENV_LOCAL_STATE="present"
  [[ -f "${OPENAI_KEY_FILE}" ]] && REPORT_OPENAI_KEY_STATE="detected"
  [[ -f "${ANTHROPIC_KEY_FILE}" ]] && REPORT_ANTHROPIC_KEY_STATE="detected"
}

print_preflight_report() {
  build_report_context

  cat <<EOF

Preflight Summary
  Install profile:    ${PROFILE}
  Docker Desktop:     ${REPORT_DOCKER_STATE}
  Compose file:       ${COMPOSE_FILE}
  Local overrides:    ${REPORT_ENV_LOCAL_STATE} (${ENV_LOCAL})
  API port:           ${REPORT_PUBLISHED_PORT}
  Bearer token:       ${REPORT_BEARER_TOKEN}
  OpenAI key file:    ${REPORT_OPENAI_KEY_STATE}
  Anthropic key file: ${REPORT_ANTHROPIC_KEY_STATE}
  Ollama base URL:    ${REPORT_OLLAMA_BASE_URL}
  OpenAI model:       ${REPORT_OPENAI_MODEL}
  Anthropic model:    ${REPORT_ANTHROPIC_MODEL}

EOF
}

print_preflight_report_json() {
  build_report_context

  cat <<EOF
{
  "profile": "$(json_escape "${PROFILE}")",
  "docker_state": "$(json_escape "${REPORT_DOCKER_STATE}")",
  "compose_file": "$(json_escape "${COMPOSE_FILE}")",
  "local_overrides": {
    "state": "$(json_escape "${REPORT_ENV_LOCAL_STATE}")",
    "path": "$(json_escape "${ENV_LOCAL}")"
  },
  "api_port": "$(json_escape "${REPORT_PUBLISHED_PORT}")",
  "bearer_token": "$(json_escape "${REPORT_BEARER_TOKEN}")",
  "key_files": {
    "openai": "$(json_escape "${REPORT_OPENAI_KEY_STATE}")",
    "anthropic": "$(json_escape "${REPORT_ANTHROPIC_KEY_STATE}")"
  },
  "defaults": {
    "ollama_base_url": "$(json_escape "${REPORT_OLLAMA_BASE_URL}")",
    "openai_model": "$(json_escape "${REPORT_OPENAI_MODEL}")",
    "anthropic_model": "$(json_escape "${REPORT_ANTHROPIC_MODEL}")"
  },
  "dependencies": $(dependency_summary_json),
  "urls": {
    "admin": "$(json_escape "${REPORT_ADMIN_URL}")",
    "health": "$(json_escape "${REPORT_HEALTH_URL}")",
    "jaeger": "$(json_escape "${REPORT_JAEGER_URL}")"
  }
}
EOF
}

stack_running() {
  have_command docker || return 1
  docker compose version >/dev/null 2>&1 || return 1
  local container_id=""
  container_id="$(docker compose -f "${COMPOSE_FILE}" ps -q api 2>/dev/null | head -n 1)"
  [[ -n "${container_id}" ]] || return 1
  [[ "$(docker inspect -f '{{.State.Running}}' "${container_id}" 2>/dev/null)" == "true" ]]
}

print_live_provider_report() {
  stack_running || {
    warn "Live provider report unavailable because the API stack is not running."
    return 0
  }

  docker compose -f "${COMPOSE_FILE}" exec -T api python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=10) as response:
    data = json.load(response)

readiness = data.get("provider_readiness", [])
live = []
configured_unavailable = []
missing = []

for entry in readiness:
    family = entry.get("provider_family") or entry.get("provider_name") or entry.get("provider_key")
    status = entry.get("status") or "unknown"
    healthy = entry.get("healthy_model_count") or 0
    total = entry.get("model_count") or 0
    note = entry.get("note") or ""
    descriptor = f"{family} ({healthy}/{total}, {status})"
    if note:
        descriptor = f"{descriptor} - {note}"
    if entry.get("configured"):
        if healthy > 0:
            live.append(descriptor)
        else:
            configured_unavailable.append(descriptor)
    else:
        missing.append(descriptor)

print("")
print("Live Provider Report")
print("  Live providers:")
if live:
    for item in live:
        print(f"    - {item}")
else:
    print("    - none")

print("  Configured but unavailable:")
if configured_unavailable:
    for item in configured_unavailable:
        print(f"    - {item}")
else:
    print("    - none")

print("  Missing configuration:")
if missing:
    for item in missing:
        print(f"    - {item}")
else:
    print("    - none")
print("")
PY
}

print_live_provider_report_json() {
  stack_running || {
    printf 'null\n'
    return 0
  }
  curl -fsS "${REPORT_HEALTH_URL}"
}

print_json_report() {
  local live_json
  build_report_context
  live_json="$(print_live_provider_report_json)"
  cat <<EOF
{
  "script": "install-local-macos",
  "report_only": true,
  "preflight": $(print_preflight_report_json),
  "live": ${live_json}
}
EOF
}

prepare_env_local() {
  if [[ ! -f "${ENV_LOCAL}" ]]; then
    cat > "${ENV_LOCAL}" <<'EOF'
# Local overrides for macOS Docker Desktop bootstrap.
# This file is ignored by git.
EOF
    log "Created ${ENV_LOCAL}"
  fi

  if [[ -f "${OPENAI_KEY_FILE}" ]]; then
    local openai_key
    openai_key="$(tr -d '\r\n' < "${OPENAI_KEY_FILE}")"
    if [[ -n "${openai_key}" ]]; then
      set_env_value "${ENV_LOCAL}" "LLMPROXY_OPENAI_API_KEY" "${openai_key}"
      set_env_value "${ENV_LOCAL}" "LLMPROXY_OPENAI_BASE_URL" "https://api.openai.com/v1"
      log "Configured OpenAI overrides from ${OPENAI_KEY_FILE}"
    fi
  else
    warn "No ${OPENAI_KEY_FILE} found. OpenAI will keep the default local/mock configuration."
  fi

  if [[ -f "${ANTHROPIC_KEY_FILE}" ]]; then
    local anthropic_key
    anthropic_key="$(tr -d '\r\n' < "${ANTHROPIC_KEY_FILE}")"
    if [[ -n "${anthropic_key}" ]]; then
      set_env_value "${ENV_LOCAL}" "LLMPROXY_ANTHROPIC_API_KEY" "${anthropic_key}"
      set_env_value "${ENV_LOCAL}" "LLMPROXY_ANTHROPIC_BASE_URL" "https://api.anthropic.com/v1"
      log "Configured Anthropic overrides from ${ANTHROPIC_KEY_FILE}"
    fi
  else
    warn "No ${ANTHROPIC_KEY_FILE} found. Anthropic will remain unconfigured unless you add a key later."
  fi
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --profile)
        [[ $# -ge 2 ]] || die "--profile requires a value: core, training, or full"
        PROFILE="$2"
        shift 2
        ;;
      --with-training)
        PROFILE="full"
        shift
        ;;
      --report)
        REPORT_ONLY=1
        shift
        ;;
      --json)
        JSON_OUTPUT=1
        shift
        ;;
      --install-deps)
        INSTALL_DEPS=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done

  [[ "$(uname -s)" == "Darwin" ]] || die "This bootstrap script is intended for macOS."
  [[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
  [[ -f "${ENV_EXAMPLE}" ]] || die "Compose env example not found: ${ENV_EXAMPLE}"

  if [[ "${JSON_OUTPUT}" -eq 1 && "${REPORT_ONLY}" -ne 1 ]]; then
    die "--json is intended for report mode. Use --report --json."
  fi

  if [[ "${INSTALL_DEPS}" -eq 1 ]]; then
    install_missing_dependencies
  fi

  if [[ "${REPORT_ONLY}" -eq 0 ]]; then
    have_command docker || die "Docker is missing. Rerun with --install-deps to install prerequisites automatically."
    have_command curl || die "curl is missing. Rerun with --install-deps to install prerequisites automatically."
  fi

  if [[ "${REPORT_ONLY}" -eq 1 && "${JSON_OUTPUT}" -eq 1 ]]; then
    prepare_env_local
    print_json_report
    exit 0
  fi

  require_command docker
  require_command curl

  if ! docker compose version >/dev/null 2>&1; then
    die "Docker Compose plugin is required. Install or enable Docker Desktop, or rerun with --install-deps."
  fi

  if ! docker info >/dev/null 2>&1; then
    if [[ -d "/Applications/Docker.app" ]]; then
      log "Docker daemon not ready. Launching Docker Desktop..."
      open -a Docker || true
    fi
    wait_for_docker || die "Docker Desktop is not ready. Start Docker Desktop and rerun this script."
  fi

  prepare_env_local
  print_preflight_report

  if [[ "${REPORT_ONLY}" -eq 1 ]]; then
    print_live_provider_report
    exit 0
  fi

  log "Starting local llmProxy stack with profile '${PROFILE}'..."
  local services=()
  local service_name=""
  while IFS= read -r service_name; do
    [[ -n "${service_name}" ]] && services+=("${service_name}")
  done < <(profile_services)
  docker compose -f "${COMPOSE_FILE}" up -d --build "${services[@]}"
  reconcile_optional_services

  local published_port bearer_token health_url admin_url jaeger_url
  published_port="$(env_value "LLMPROXY_API_PORT")"
  [[ -n "${published_port}" ]] || published_port="8000"
  bearer_token="$(env_value "LLMPROXY_BEARER_TOKEN")"
  [[ -n "${bearer_token}" ]] || bearer_token="change-me"
  health_url="http://127.0.0.1:${published_port}/health"
  admin_url="http://127.0.0.1:${published_port}/admin"
  jaeger_url="http://127.0.0.1:16686"

  log "Waiting for ${health_url} ..."
  wait_for_health "${health_url}" || die "The stack did not become healthy in time. Inspect 'docker compose ps' and container logs."
  print_live_provider_report

  cat <<EOF

llmProxy local stack is running.

Install profile: ${PROFILE}
Admin console: ${admin_url}
Health check:  ${health_url}
Jaeger UI:     ${jaeger_url}
Bearer token:  ${bearer_token}

Useful next commands:
  docker compose -f ${COMPOSE_FILE} ps
  ${REPO_ROOT}/scripts/install-local-macos.sh --report
  ${REPO_ROOT}/scripts/start-local-macos.sh --profile ${PROFILE}
  ${REPO_ROOT}/scripts/stop-local-macos.sh
  ${REPO_ROOT}/scripts/teardown-local-macos.sh
  ${REPO_ROOT}/scripts/install-local-macos.sh --profile full

EOF
}

main "$@"
