from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
STATE_ROOT = Path(os.getenv("AGI3_HOME", REPO_ROOT / ".agi3"))
SESSION_PATH = STATE_ROOT / "session.json"
COOKIES_PATH = STATE_ROOT / "cookies.json"
