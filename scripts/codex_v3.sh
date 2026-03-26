#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
CODEX_HOME_DIR="${REPO_ROOT}/.codex_home"
CODEX_WORK_DIR="${REPO_ROOT}/codex_work_v3"
CODEX_SKILLS_DIR="${CODEX_HOME_DIR}/skills"
REPO_SKILL_DIR="${REPO_ROOT}/skills/agi3-cli"
CODEX_SKILL_LINK="${CODEX_SKILLS_DIR}/agi3-cli"
UV_CACHE_DIR="${CODEX_WORK_DIR}/.uv_cache"
AGI3_HOME_DIR="${CODEX_WORK_DIR}/.agi3"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex command not found" >&2
  exit 127
fi

HAS_SANDBOX_FLAG=0
for ARG in "$@"; do
  case "${ARG}" in
    -s|--sandbox|--full-auto|--dangerously-bypass-approvals-and-sandbox)
      HAS_SANDBOX_FLAG=1
      ;;
  esac
done

if [ "${HAS_SANDBOX_FLAG}" -eq 0 ]; then
  set -- --dangerously-bypass-approvals-and-sandbox "$@"
fi

mkdir -p "${CODEX_HOME_DIR}" "${CODEX_WORK_DIR}" "${CODEX_SKILLS_DIR}" "${UV_CACHE_DIR}" "${AGI3_HOME_DIR}"
if [ -d "${REPO_SKILL_DIR}" ]; then
  ln -snf "${REPO_SKILL_DIR}" "${CODEX_SKILL_LINK}"
fi

cd "${CODEX_WORK_DIR}"
exec env CODEX_HOME="${CODEX_HOME_DIR}" UV_CACHE_DIR="${UV_CACHE_DIR}" AGI3_HOME="${AGI3_HOME_DIR}" codex "$@"
