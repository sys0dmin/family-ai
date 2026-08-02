#!/usr/bin/env bash
set -euo pipefail

UV_VERSION="0.11.31"
ROOT="/srv/family-ai"

die() {
  echo "release error: $*" >&2
  exit 1
}

configure_component() {
  case "$1" in
    gateway)
      COMPONENT_ROOT="$ROOT/gateway"
      CONFIG_FILE="/etc/family-ai/gateway.env"
      SERVICES=("family-ai-gateway.service" "family-ai-admin.service")
      HEALTH_URLS=("http://127.0.0.1:8000/healthz" "http://127.0.0.1:8001/api/healthz")
      HEALTH_TIMEOUT=60
      ;;
    speech)
      COMPONENT_ROOT="$ROOT/speech"
      CONFIG_FILE="/etc/family-ai/speech.env"
      SERVICES=("family-ai-speech.service")
      HEALTH_URLS=("http://127.0.0.1:8010/healthz")
      HEALTH_TIMEOUT=240
      ;;
    *)
      die "unknown component: $1"
      ;;
  esac
}

assert_commit() {
  [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "version must be a full Git commit SHA"
}

read_manifest() {
  local archive="$1"
  python3 - "$archive" <<'PY'
import json
import sys
import tarfile

with tarfile.open(sys.argv[1], "r:gz") as bundle:
    member = bundle.getmember("release.json")
    manifest = json.load(bundle.extractfile(member))
print(manifest["schema"])
print(manifest["component"])
print(manifest["commit"])
print(manifest["lock_sha256"])
PY
}

verify_archive_members() {
  local archive="$1"
  python3 - "$archive" <<'PY'
import pathlib
import sys
import tarfile

with tarfile.open(sys.argv[1], "r:gz") as bundle:
    for member in bundle.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"unsafe archive member: {member.name}")
PY
}

ensure_uv() {
  UV="$ROOT/tools/uv-$UV_VERSION/bin/uv"
  if [[ ! -x "$UV" ]]; then
    local tool_environment="$ROOT/tools/uv-$UV_VERSION"
    rm -rf -- "$tool_environment"
    python3 -m venv "$tool_environment"
    "$tool_environment/bin/python" -m pip install \
      --quiet --disable-pip-version-check "uv==$UV_VERSION"
  fi
}

prepare_release() {
  local component="$1" archive="$2" expected_sha="$3" commit="$4"
  configure_component "$component"
  assert_commit "$commit"
  [[ -f "$archive" ]] || die "archive not found"
  [[ "$(sha256sum "$archive" | cut -d' ' -f1)" == "$expected_sha" ]] ||
    die "archive checksum mismatch"
  verify_archive_members "$archive"

  mapfile -t manifest < <(read_manifest "$archive")
  [[ "${manifest[0]}" == "family-ai-release/v1" ]] || die "unsupported manifest schema"
  [[ "${manifest[1]}" == "$component" ]] || die "component mismatch"
  [[ "${manifest[2]}" == "$commit" ]] || die "commit mismatch"

  local release="$COMPONENT_ROOT/releases/$commit"
  if [[ ! -d "$release" ]]; then
    local staging="$COMPONENT_ROOT/releases/.${commit}.tmp"
    rm -rf -- "$staging"
    mkdir -p -- "$staging"
    tar -xzf "$archive" -C "$staging"
    mv -- "$staging" "$release"
  fi

  ensure_uv
  local lock_sha="${manifest[3]}"
  local environment="$COMPONENT_ROOT/venvs/$lock_sha"
  if [[ ! -f "$environment/.family-ai-complete" ]]; then
    rm -rf -- "$environment"
    UV_PROJECT_ENVIRONMENT="$environment" "$UV" sync \
      --frozen --no-dev --project "$release"
    touch "$environment/.family-ai-complete"
  fi

  ln -sfn -- "$environment" "$release/.venv"
  ln -sfn -- "$CONFIG_FILE" "$release/.env"
  (
    cd "$release"
    "$environment/bin/python" -c \
      "$([[ "$component" == "gateway" ]] && echo 'import gateway.app.main, gateway.admin.main' || echo 'import family_ai_speech.main')"
  )
  echo "prepared $component $commit"
}

restart_services() {
  local service
  for service in "${SERVICES[@]}"; do
    sudo systemctl restart "$service"
  done
}

wait_for_health() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  local url all_ready
  while (( SECONDS < deadline )); do
    all_ready=true
    for url in "${HEALTH_URLS[@]}"; do
      if ! curl --silent --fail --max-time 5 "$url" >/dev/null 2>&1; then
        all_ready=false
        break
      fi
    done
    [[ "$all_ready" == true ]] && return 0
    sleep 2
  done
  return 1
}

run_gateway_smoke() {
  local release="$1"
  [[ -x "$release/.venv/bin/python" ]] || die "smoke-test release is unavailable"
  [[ -f "$release/gateway/smoke.py" ]] || die "release has no functional smoke-test"
  (
    cd "$release"
    "$release/.venv/bin/python" -m gateway.smoke \
      --gateway-url "http://127.0.0.1:8000" \
      --admin-url "http://127.0.0.1:8001" \
      --timeout 120
  )
}

version_for_target() {
  local target="$1"
  case "$target" in
    "$COMPONENT_ROOT/releases/"*) basename "$target" ;;
    *) echo "legacy" ;;
  esac
}

activate_release() {
  local component="$1" commit="$2" functional_smoke="${3:-true}"
  configure_component "$component"
  assert_commit "$commit"
  local release="$COMPONENT_ROOT/releases/$commit"
  [[ -x "$release/.venv/bin/python" ]] || die "release is not prepared: $commit"

  local old_target=""
  if [[ -L "$COMPONENT_ROOT/current" ]]; then
    old_target="$(readlink -f "$COMPONENT_ROOT/current")"
  fi
  if [[ "$old_target" == "$release" ]]; then
    wait_for_health || die "$component health-check failed"
    if [[ "$component" == "gateway" && "$functional_smoke" == "true" ]]; then
      run_gateway_smoke "$release" || die "gateway functional smoke-test failed"
    fi
    echo "$commit" >"$COMPONENT_ROOT/deployed-version"
    echo "$component already runs verified release $commit"
    return 0
  fi

  ln -sfn -- "$release" "$COMPONENT_ROOT/current.next"
  mv -Tf -- "$COMPONENT_ROOT/current.next" "$COMPONENT_ROOT/current"
  restart_services

  local release_ready=false
  if wait_for_health; then
    release_ready=true
    if [[ "$component" == "gateway" && "$functional_smoke" == "true" ]]; then
      if ! run_gateway_smoke "$release"; then
        release_ready=false
        echo "functional smoke-test failed" >&2
      fi
    fi
  fi

  if [[ "$release_ready" == true ]]; then
    if [[ -n "$old_target" ]]; then
      ln -sfn -- "$old_target" "$COMPONENT_ROOT/previous"
    fi
    echo "$commit" >"$COMPONENT_ROOT/deployed-version"
    echo "deployed $component $commit"
    return 0
  fi

  echo "release verification failed, restoring previous code" >&2
  if [[ -n "$old_target" ]]; then
    ln -sfn -- "$old_target" "$COMPONENT_ROOT/current.next"
    mv -Tf -- "$COMPONENT_ROOT/current.next" "$COMPONENT_ROOT/current"
    restart_services
    wait_for_health || die "rollback health-check also failed"
    version_for_target "$old_target" >"$COMPONENT_ROOT/deployed-version"
  else
    rm -f -- "$COMPONENT_ROOT/current"
    for service in "${SERVICES[@]}"; do
      sudo systemctl stop "$service" || true
    done
    echo "unavailable" >"$COMPONENT_ROOT/deployed-version"
  fi
  die "deployment rolled back after failed release verification"
}

rollback_release() {
  local component="$1" target="${2:-}"
  configure_component "$component"
  if [[ -z "$target" ]]; then
    [[ -L "$COMPONENT_ROOT/previous" ]] || die "previous release is not recorded"
    target="$(readlink -f "$COMPONENT_ROOT/previous")"
  else
    assert_commit "$target"
    target="$COMPONENT_ROOT/releases/$target"
  fi
  [[ -x "$target/.venv/bin/python" ]] || die "rollback target is not prepared"
  case "$target" in
    "$COMPONENT_ROOT/releases/"*)
      activate_release "$component" "$(basename "$target")" false
      ;;
    *)
      local old_target
      old_target="$(readlink -f "$COMPONENT_ROOT/current")"
      ln -sfn -- "$target" "$COMPONENT_ROOT/current.next"
      mv -Tf -- "$COMPONENT_ROOT/current.next" "$COMPONENT_ROOT/current"
      restart_services
      wait_for_health || die "legacy rollback health-check failed"
      ln -sfn -- "$old_target" "$COMPONENT_ROOT/previous"
      echo "legacy" >"$COMPONENT_ROOT/deployed-version"
      echo "rolled back $component to legacy"
      ;;
  esac
}

migrate_gateway() {
  local commit="${1:-}"
  configure_component gateway
  if [[ -z "$commit" ]]; then
    commit="$(cat "$COMPONENT_ROOT/deployed-version")"
  fi
  assert_commit "$commit"
  local release="$COMPONENT_ROOT/releases/$commit"
  [[ -x "$release/.venv/bin/alembic" ]] || die "release is not prepared: $commit"
  (
    cd "$release"
    "$release/.venv/bin/alembic" -c alembic.ini upgrade head
  )
  echo "migrated gateway schema with $commit"
}

show_status() {
  local component="$1"
  configure_component "$component"
  local version="legacy"
  [[ -f "$COMPONENT_ROOT/deployed-version" ]] && version="$(cat "$COMPONENT_ROOT/deployed-version")"
  printf '%s %s\n' "$component" "$version"
  local service
  for service in "${SERVICES[@]}"; do
    printf '%s %s\n' "$service" "$(systemctl is-active "$service" || true)"
  done
}

smoke_gateway() {
  configure_component gateway
  [[ -L "$COMPONENT_ROOT/current" ]] || die "gateway has no active release"
  run_gateway_smoke "$(readlink -f "$COMPONENT_ROOT/current")"
}

ACTION="${1:-}"
COMPONENT="${2:-}"
case "$ACTION" in
  prepare)
    [[ $# -eq 5 ]] || die "usage: prepare COMPONENT ARCHIVE SHA256 COMMIT"
    prepare_release "$COMPONENT" "$3" "$4" "$5"
    ;;
  deploy)
    [[ $# -eq 5 ]] || die "usage: deploy COMPONENT ARCHIVE SHA256 COMMIT"
    prepare_release "$COMPONENT" "$3" "$4" "$5"
    activate_release "$COMPONENT" "$5"
    ;;
  activate)
    [[ $# -eq 3 ]] || die "usage: activate COMPONENT COMMIT"
    activate_release "$COMPONENT" "$3"
    ;;
  rollback)
    [[ $# -le 3 ]] || die "usage: rollback COMPONENT [COMMIT]"
    rollback_release "$COMPONENT" "${3:-}"
    ;;
  migrate)
    [[ "$COMPONENT" == "gateway" ]] || die "migrations belong only to gateway"
    migrate_gateway "${3:-}"
    ;;
  smoke)
    [[ $# -eq 2 ]] || die "usage: smoke gateway"
    [[ "$COMPONENT" == "gateway" ]] || die "full smoke-test runs from gateway"
    smoke_gateway
    ;;
  status)
    show_status "$COMPONENT"
    ;;
  *)
    die "unknown action"
    ;;
esac
