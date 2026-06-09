#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_DIR="${REPO_ROOT}/infra/compose"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
ENV_EXAMPLE="${COMPOSE_DIR}/.env.example"
ENV_LOCAL="${COMPOSE_DIR}/.env.local"
PROFILE="core"
JSON_OUTPUT=0

log() {
  if [[ "${JSON_OUTPUT}" -ne 1 ]]; then
    printf '[llmproxy-start] %s\n' "$*"
  fi
}

die() {
  printf '[llmproxy-start] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
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
  ${REPO_ROOT}/scripts/start-local-macos.sh [--profile core|training|full] [--json]
  ${REPO_ROOT}/scripts/start-local-macos.sh --with-training

Options:
  --profile core|training|full
      core     Start postgres, redis, jaeger, api, worker, scheduler.
      training Start core services plus training-worker.
      full     Start core services plus training-worker and unsloth-studio.

  --with-training
      Backward-compatible alias for --profile full.

  --json
      Emit machine-readable JSON output.

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
      --json)
        JSON_OUTPUT=1
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

  [[ "$(uname -s)" == "Darwin" ]] || die "This start script is intended for macOS."
  [[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"

  require_command docker
  require_command curl

  if ! docker compose version >/dev/null 2>&1; then
    die "Docker Compose plugin is required. Install or enable Docker Desktop."
  fi

  local services=()
  local service_name=""
  while IFS= read -r service_name; do
    [[ -n "${service_name}" ]] && services+=("${service_name}")
  done < <(profile_services)

  log "Starting local llmProxy profile '${PROFILE}' without rebuilding..."
  if ! docker compose -f "${COMPOSE_FILE}" up -d --no-build "${services[@]}"; then
    die "Start failed. If images or containers do not exist yet, run ${REPO_ROOT}/scripts/install-local-macos.sh first."
  fi
  reconcile_optional_services

  local published_port health_url admin_url
  published_port="$(env_value "LLMPROXY_API_PORT")"
  [[ -n "${published_port}" ]] || published_port="8000"
  health_url="http://127.0.0.1:${published_port}/health"
  admin_url="http://127.0.0.1:${published_port}/admin"

  log "Waiting for ${health_url} ..."
  wait_for_health "${health_url}" || die "The stack did not become healthy in time. Inspect 'docker compose ps' and container logs."

  if [[ "${JSON_OUTPUT}" -eq 1 ]]; then
    cat <<EOF
{
  "script": "start-local-macos",
  "action": "start",
  "status": "ok",
  "profile": "$(json_escape "${PROFILE}")",
  "urls": {
    "admin": "$(json_escape "${admin_url}")",
    "health": "$(json_escape "${health_url}")"
  }
}
EOF
    exit 0
  fi

  cat <<EOF

llmProxy local stack is running.

Start profile: ${PROFILE}
Admin console: ${admin_url}
Health check:  ${health_url}

Useful next commands:
  docker compose -f ${COMPOSE_FILE} ps
  ${REPO_ROOT}/scripts/stop-local-macos.sh --profile ${PROFILE}
  ${REPO_ROOT}/scripts/teardown-local-macos.sh

EOF
}

main "$@"
