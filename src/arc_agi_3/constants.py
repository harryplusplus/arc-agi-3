from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
ARTIFACTS_ROOT = REPO_ROOT / ".artifacts" / "arc-bench"
DEFAULT_RESULTS_DIR = ARTIFACTS_ROOT / "results"
DEFAULT_CHECKPOINT_DIR = ARTIFACTS_ROOT / "checkpoints"

DEFAULT_GAME = "ls20"
DEFAULT_CONFIG = "gpt-5.4-codex-cli-xhigh"

CODEX_WRAPPER = REPO_ROOT / "scripts" / "codex.sh"
CODEX_WORK_DIR = REPO_ROOT / "codex_work"
CODEX_HOME = REPO_ROOT / ".codex_home"
CODEX_AGENTS_FILE = CODEX_WORK_DIR / "AGENTS.md"
CODEX_SESSION_FILE = REPO_ROOT / ".codex_session_id"
CODEX_MODEL = "gpt-5.4"
CODEX_REASONING_EFFORT = "xhigh"
OFFLINE_PLANNER_TIME_LIMIT_S = 120.0
OFFLINE_PLANNER_EXPANSION_LIMIT = 2_000_000
OFFLINE_PLANNER_PREVIEW_ACTIONS = 16
SCORECARD_HARNESS = "arc3tester-programmatic"
SCORECARD_BACKEND = "codex-cli"
SCORECARD_AUTH = "codex-oauth"
SCORECARD_SESSION_MODE = "resume"

CODEX_MODEL_CONFIG = {
    "name": DEFAULT_CONFIG,
    "model_name": CODEX_MODEL,
    "provider": "codex-cli",
    "is_multimodal": False,
    "api_type": "codex_exec_resume",
    "pricing": {
        "date": "2026-03-26",
        "input": 0.0,
        "output": 0.0,
    },
    "reasoning": {
        "effort": CODEX_REASONING_EFFORT,
    },
}

ACTION_DESCRIPTIONS = {
    "ACTION1": "Move Up",
    "ACTION2": "Move Down",
    "ACTION3": "Move Left",
    "ACTION4": "Move Right",
    "ACTION5": "Perform Action",
    "ACTION6": "Click object on screen",
    "ACTION7": "Undo",
}
