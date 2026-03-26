#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
CODEX_HOME_DIR="${REPO_ROOT}/.codex_home"
CODEX_WORK_DIR="${REPO_ROOT}/codex_work_faithful"
CODEX_SKILLS_DIR="${CODEX_HOME_DIR}/skills"
REPO_SKILL_DIR="${REPO_ROOT}/skills/arc-faithful-ls20"
CODEX_SKILL_LINK="${CODEX_SKILLS_DIR}/arc-faithful-ls20"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex command not found" >&2
  exit 127
fi

mkdir -p "${CODEX_HOME_DIR}" "${CODEX_WORK_DIR}" "${CODEX_SKILLS_DIR}"
if [ -d "${REPO_SKILL_DIR}" ]; then
  ln -snf "${REPO_SKILL_DIR}" "${CODEX_SKILL_LINK}"
fi
cd "${CODEX_WORK_DIR}"
exec env CODEX_HOME="${CODEX_HOME_DIR}" codex "$@"
