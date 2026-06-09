#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/compose/docker-compose.yml"
PROFILE="full"
JSON_OUTPUT=0

log() {
  if [[ "${JSON_OUTPUT}" -ne 1 ]]; then
    printf '[llmproxy-stop] %s\n' "$*"
  fi
}

die() {
  printf '[llmproxy-stop] ERROR: %s\n' "$*" >&2
  exit 1
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

[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
command -v docker >/dev/null 2>&1 || die "Docker is required."

usage() {
  cat <<EOF
Usage:
  ${REPO_ROOT}/scripts/stop-local-macos.sh [--profile core|training|full] [--json]

Profiles:
  core     Stop postgres, redis, jaeger, api, worker, scheduler.
  training Stop core services plus training-worker.
  full     Stop every managed local service, including unsloth-studio.
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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      [[ $# -ge 2 ]] || die "--profile requires a value: core, training, or full"
      PROFILE="$2"
      shift 2
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

SERVICES=()
while IFS= read -r service_name; do
  [[ -n "${service_name}" ]] && SERVICES+=("${service_name}")
done < <(profile_services)

log "Stopping local llmProxy profile '${PROFILE}'..."
docker compose -f "${COMPOSE_FILE}" stop "${SERVICES[@]}"

if [[ "${JSON_OUTPUT}" -eq 1 ]]; then
  cat <<EOF
{
  "script": "stop-local-macos",
  "action": "stop",
  "status": "ok",
  "profile": "$(json_escape "${PROFILE}")"
}
EOF
  exit 0
fi

log "Stopped."
