from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]
ENV_FILE = REPO_ROOT / ".env"

ARTIFACTS_ROOT = REPO_ROOT / ".artifacts" / "arc-bench-faithful"
RESULTS_DIR = ARTIFACTS_ROOT / "results"
CHECKPOINT_DIR = ARTIFACTS_ROOT / "checkpoints"
MEMORY_DIR = ARTIFACTS_ROOT / "memory"
EXPERIENCE_DB_PATH = ARTIFACTS_ROOT / "experience.db"

DEFAULT_GAME = "ls20"
DEFAULT_CONFIG = "gpt-5.4-codex-cli-xhigh-faithful"

CODEX_HOME = REPO_ROOT / ".codex_home"
CODEX_WORK_DIR = REPO_ROOT / "codex_work_faithful"
CODEX_WRAPPER = REPO_ROOT / "scripts" / "codex_faithful.sh"
CODEX_SESSION_FILE = REPO_ROOT / ".codex_session_id_faithful"
CODEX_MODEL = "gpt-5.4"
CODEX_REASONING_EFFORT = "xhigh"

SCORECARD_HARNESS = "memory_agent_programmatic"
SCORECARD_BACKEND = "codex-cli"
SCORECARD_AUTH = "codex-oauth"
SCORECARD_SESSION_MODE = "resume"

WORKING_MEMORY_LIMIT = 16
RECENT_TRAJECTORY_LIMIT = 12

CODEX_MODEL_CONFIG = {
    "name": DEFAULT_CONFIG,
    "model_name": CODEX_MODEL,
    "provider": "codex-cli",
    "is_multimodal": False,
    "api_type": "codex_exec_resume",
    "pricing": {
        "date": "2026-03-27",
        "input": 0.0,
        "output": 0.0,
    },
    "reasoning": {
        "effort": CODEX_REASONING_EFFORT,
    },
}

ACTION_DELTAS = {
    "ACTION1": (0, -5),
    "ACTION2": (0, 5),
    "ACTION3": (-5, 0),
    "ACTION4": (5, 0),
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
