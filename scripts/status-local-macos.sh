#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_DIR="${REPO_ROOT}/infra/compose"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
ENV_EXAMPLE="${COMPOSE_DIR}/.env.example"
ENV_LOCAL="${COMPOSE_DIR}/.env.local"
JSON_OUTPUT=0

log() {
  printf '[llmproxy-status] %s\n' "$*"
}

die() {
  printf '[llmproxy-status] ERROR: %s\n' "$*" >&2
  exit 1
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
  ${REPO_ROOT}/scripts/status-local-macos.sh [--json]

Options:
  --json
      Emit machine-readable JSON output.

  -h, --help
      Show this help text.
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

detect_state() {
  RUNNING_SERVICES=()
  if have_command docker && docker compose version >/dev/null 2>&1; then
    while IFS= read -r service_name; do
      [[ -n "${service_name}" ]] && RUNNING_SERVICES+=("${service_name}")
    done < <(docker compose -f "${COMPOSE_FILE}" ps --services --status running 2>/dev/null || true)
  fi

  local running_joined=" ${RUNNING_SERVICES[*]-} "

  CORE_PRESENT=1
  local core_service
  for core_service in postgres redis jaeger api worker scheduler; do
    if [[ "${running_joined}" != *" ${core_service} "* ]]; then
      CORE_PRESENT=0
      break
    fi
  done

  TRAINING_PRESENT=0
  [[ "${running_joined}" == *" training-worker "* ]] && TRAINING_PRESENT=1
  STUDIO_PRESENT=0
  [[ "${running_joined}" == *" unsloth-studio "* ]] && STUDIO_PRESENT=1

  if [[ ${#RUNNING_SERVICES[@]} -eq 0 ]]; then
    LIFECYCLE_STATE="down"
    RUNNING_PROFILE="none"
  elif [[ "${CORE_PRESENT}" -eq 1 && "${TRAINING_PRESENT}" -eq 0 && "${STUDIO_PRESENT}" -eq 0 ]]; then
    LIFECYCLE_STATE="running"
    RUNNING_PROFILE="core"
  elif [[ "${CORE_PRESENT}" -eq 1 && "${TRAINING_PRESENT}" -eq 1 && "${STUDIO_PRESENT}" -eq 0 ]]; then
    LIFECYCLE_STATE="running"
    RUNNING_PROFILE="training"
  elif [[ "${CORE_PRESENT}" -eq 1 && "${TRAINING_PRESENT}" -eq 1 && "${STUDIO_PRESENT}" -eq 1 ]]; then
    LIFECYCLE_STATE="running"
    RUNNING_PROFILE="full"
  else
    LIFECYCLE_STATE="partial"
    RUNNING_PROFILE="mixed"
  fi
}

health_url() {
  local port
  port="$(env_value "LLMPROXY_API_PORT")"
  [[ -n "${port}" ]] || port="8000"
  printf 'http://127.0.0.1:%s/health\n' "${port}"
}

admin_url() {
  local port
  port="$(env_value "LLMPROXY_API_PORT")"
  [[ -n "${port}" ]] || port="8000"
  printf 'http://127.0.0.1:%s/admin\n' "${port}"
}

unsloth_url() {
  printf 'http://127.0.0.1:8888\n'
}

print_text_status() {
  detect_state
  local hurl aurl jurl surl
  hurl="$(health_url)"
  aurl="$(admin_url)"
  jurl="http://127.0.0.1:16686"
  surl="$(unsloth_url)"

  cat <<EOF

Local Status
  Lifecycle state: ${LIFECYCLE_STATE}
  Running profile: ${RUNNING_PROFILE}
  Running services: ${RUNNING_SERVICES[*]-none}
  Admin URL:       ${aurl}
  Health URL:      ${hurl}
  Jaeger URL:      ${jurl}
  Unsloth URL:     ${surl}

EOF

  if [[ "${LIFECYCLE_STATE}" == "down" ]]; then
    return 0
  fi

  if curl -fsS "${hurl}" >/dev/null 2>&1; then
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

print("Provider Readiness")
print("  Live providers:")
for item in live or ["none"]:
    print(f"    - {item}")
print("  Configured but unavailable:")
for item in configured_unavailable or ["none"]:
    print(f"    - {item}")
print("  Missing configuration:")
for item in missing or ["none"]:
    print(f"    - {item}")
PY
  else
    log "API health endpoint is not currently reachable."
  fi
}

print_json_status() {
  detect_state
  local running_json health_json
  running_json="$(printf '%s\n' "${RUNNING_SERVICES[@]-}" | awk 'BEGIN { printf "["; first=1 } NF { if (!first) printf ","; gsub(/\\/,"\\\\"); gsub(/"/,"\\\""); printf "\"%s\"", $0; first=0 } END { printf "]" }')"
  health_json="null"
  if [[ "${LIFECYCLE_STATE}" != "down" ]] && have_command curl && curl -fsS "$(health_url)" >/dev/null 2>&1; then
    health_json="$(curl -fsS "$(health_url)")"
  fi

  cat <<EOF
{
  "lifecycle_state": "$(json_escape "${LIFECYCLE_STATE}")",
  "running_profile": "$(json_escape "${RUNNING_PROFILE}")",
  "running_services": ${running_json},
  "urls": {
    "admin": "$(json_escape "$(admin_url)")",
    "health": "$(json_escape "$(health_url)")",
    "jaeger": "http://127.0.0.1:16686",
    "unsloth": "$(json_escape "$(unsloth_url)")"
  },
  "health": ${health_json}
}
EOF
}

main() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
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

  [[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"

  if [[ "${JSON_OUTPUT}" -eq 1 ]]; then
    print_json_status
  else
    print_text_status
  fi
}

main "$@"
