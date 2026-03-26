#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CODEX_WORK_DIR="${REPO_ROOT}/codex_work"
CODEX_HOME_DIR="${REPO_ROOT}/.codex_home"

mkdir -p "${CODEX_HOME_DIR}" "${CODEX_WORK_DIR}"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex binary not found in PATH" >&2
  exit 127
fi

cd "${CODEX_WORK_DIR}"

exec env CODEX_HOME="${CODEX_HOME_DIR}" codex "$@"
