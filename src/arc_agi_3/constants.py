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
CODEX_HOME = REPO_ROOT / ".codex-home"
CODEX_MODEL = "gpt-5.4"
CODEX_REASONING_EFFORT = "xhigh"
CODEX_SESSION_ID = "019d290a-0d8e-7f03-9903-4494c14c4746"

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

SYSTEM_INSTRUCTION = """You are controlling an ARC-AGI-3 game agent.
Return exactly one JSON object and nothing else.

Valid output shapes:
{"action":{"action":"ACTION1"},"reasoning":{"summary":"why"}}
{"action":{"action":"ACTION6","x":12,"y":34},"reasoning":{"summary":"why"}}

Rules:
- Choose exactly one action from the available actions.
- For ACTION6, include integer x and y in [0, 127].
- reasoning must be a small JSON object.
- Do not use markdown fences.
- Do not explain outside the JSON object.
"""
