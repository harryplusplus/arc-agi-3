#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CODEX_HOME_DIR="${REPO_ROOT}/.codex-home"

mkdir -p "${CODEX_HOME_DIR}"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex binary not found in PATH" >&2
  exit 127
fi

exec env CODEX_HOME="${CODEX_HOME_DIR}" codex "$@"
