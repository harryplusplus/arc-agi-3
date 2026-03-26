from __future__ import annotations

import json
import subprocess

from arc_agi_3.constants import (
    CODEX_MODEL,
    CODEX_REASONING_EFFORT,
    CODEX_SESSION_FILE,
    CODEX_WRAPPER,
    REPO_ROOT,
)


def ensure_codex_session() -> str:
    if CODEX_SESSION_FILE.exists():
        session_id = CODEX_SESSION_FILE.read_text(encoding="utf-8").strip()
        if session_id:
            return session_id

    session_id = create_codex_session()
    CODEX_SESSION_FILE.write_text(f"{session_id}\n", encoding="utf-8")
    return session_id


def create_codex_session() -> str:
    cmd = [
        str(CODEX_WRAPPER),
        "exec",
        "--json",
        "-m",
        CODEX_MODEL,
        "-c",
        f'model_reasoning_effort="{CODEX_REASONING_EFFORT}"',
        (
            "You are the dedicated Codex session for the ARC-AGI-3 benchmark agent in this "
            "repository. Preserve continuity across turns. Reply with READY only."
        ),
    ]
    completed = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to create Codex session\n"
            f"exit_code={completed.returncode}\n"
            f"stdout={completed.stdout}\n"
            f"stderr={completed.stderr}"
        )

    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
            if isinstance(thread_id, str) and thread_id:
                return thread_id

    raise RuntimeError(
        "Failed to parse thread.started event from Codex session creation\n"
        f"stdout={completed.stdout}\n"
        f"stderr={completed.stderr}"
    )
