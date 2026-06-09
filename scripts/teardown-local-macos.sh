#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/compose/docker-compose.yml"
PROFILE="full"
JSON_OUTPUT=0

log() {
  if [[ "${JSON_OUTPUT}" -ne 1 ]]; then
    printf '[llmproxy-teardown] %s\n' "$*"
  fi
}

die() {
  printf '[llmproxy-teardown] ERROR: %s\n' "$*" >&2
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

usage() {
  cat <<EOF
Usage:
  ${REPO_ROOT}/scripts/teardown-local-macos.sh [--profile core|training|full] [--volumes] [--json]

Options:
  --profile core|training|full
      core     Remove core service containers only.
      training Remove core services plus training-worker.
      full     Remove the entire Compose project.

  --volumes
      For full teardown, remove Compose volumes in addition to containers and networks.
      For partial teardown, remove service containers and anonymous volumes.

  -h, --help
      Show this help text.
EOF
}

[[ -f "${COMPOSE_FILE}" ]] || die "Compose file not found: ${COMPOSE_FILE}"
command -v docker >/dev/null 2>&1 || die "Docker is required."

profile_services() {
  case "${PROFILE}" in
    core)
      printf '%s\n' postgres redis jaeger api worker scheduler
      ;;
    training)
      printf '%s\n' postgres redis jaeger api worker scheduler training-worker
      ;;
    full)
      printf '%s\n'
      ;;
    *)
      die "Unknown profile: ${PROFILE}"
      ;;
  esac
}

EXTRA_ARGS=()
REMOVE_VOLUMES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      [[ $# -ge 2 ]] || die "--profile requires a value: core, training, or full"
      PROFILE="$2"
      shift 2
      ;;
    --volumes)
      REMOVE_VOLUMES=1
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

log "Tearing down local llmProxy profile '${PROFILE}'..."
if [[ "${PROFILE}" == "full" ]]; then
  if [[ "${REMOVE_VOLUMES}" -eq 1 ]]; then
    docker compose -f "${COMPOSE_FILE}" down --volumes
  else
    docker compose -f "${COMPOSE_FILE}" down
  fi
else
  SERVICES=()
  while IFS= read -r service_name; do
    [[ -n "${service_name}" ]] && SERVICES+=("${service_name}")
  done < <(profile_services)
  RM_ARGS=(-f -s)
  if [[ "${REMOVE_VOLUMES}" -eq 1 ]]; then
    RM_ARGS+=(-v)
  fi
  docker compose -f "${COMPOSE_FILE}" rm "${RM_ARGS[@]}" "${SERVICES[@]}"
fi

if [[ "${JSON_OUTPUT}" -eq 1 ]]; then
  cat <<EOF
{
  "script": "teardown-local-macos",
  "action": "teardown",
  "status": "ok",
  "profile": "$(json_escape "${PROFILE}")",
  "remove_volumes": $([[ "${REMOVE_VOLUMES}" -eq 1 ]] && printf 'true' || printf 'false')
}
EOF
  exit 0
fi

log "Torn down."
