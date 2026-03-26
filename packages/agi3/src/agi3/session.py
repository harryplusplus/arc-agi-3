from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agi3.paths import COOKIES_PATH, SESSION_PATH, STATE_ROOT


def summarize_state_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}

    frames = payload.get("frame") or []
    first_frame = frames[0] if isinstance(frames, list) and frames else []
    frame_height = len(first_frame) if isinstance(first_frame, list) else 0
    frame_width = len(first_frame[0]) if frame_height and isinstance(first_frame[0], list) else 0

    return {
        "guid": payload.get("guid"),
        "state": payload.get("state"),
        "levels_completed": payload.get("levels_completed"),
        "available_actions": payload.get("available_actions") or [],
        "frame_count": len(frames) if isinstance(frames, list) else 0,
        "frame_shape": [frame_height, frame_width] if frame_height and frame_width else None,
    }


class SessionStore:
    def __init__(self, state_root: Path = STATE_ROOT) -> None:
        self.state_root = Path(state_root)
        self.session_path = self.state_root / SESSION_PATH.name
        self.cookies_path = self.state_root / COOKIES_PATH.name

    def ensure(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        self.ensure()
        if not self.session_path.exists():
            return {}
        return json.loads(self.session_path.read_text())

    def save(self, session: dict[str, Any]) -> dict[str, Any]:
        self.ensure()
        payload = dict(session)
        payload["updated_at"] = datetime.now(UTC).isoformat()
        self.session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return payload

    def record_scorecard_open(
        self,
        *,
        card_id: str,
        game_ids: list[str],
        response: dict[str, Any],
    ) -> dict[str, Any]:
        session = self.load()
        session.update(
            {
                "card_id": card_id,
                "scorecard_game_ids": game_ids,
                "last_command": "scorecard.open",
                "last_response": response,
                "last_response_summary": summarize_state_payload(response),
            }
        )
        return self.save(session)

    def record_game_response(
        self,
        *,
        command: str,
        response: dict[str, Any],
        game_id: str | None = None,
        card_id: str | None = None,
        action: str | None = None,
        reasoning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session = self.load()
        if card_id:
            session["card_id"] = card_id
        if game_id:
            session["game_id"] = game_id
        if response.get("guid"):
            session["guid"] = response["guid"]
        session["last_command"] = command
        session["last_action"] = action
        session["last_reasoning"] = reasoning
        session["last_response"] = response
        session["last_response_summary"] = summarize_state_payload(response)
        return self.save(session)

    def mark_scorecard_closed(self, *, card_id: str, response: dict[str, Any]) -> dict[str, Any]:
        session = self.load()
        session["last_closed_card_id"] = card_id
        session["last_command"] = "scorecard.close"
        session["last_response"] = response
        session["last_response_summary"] = summarize_state_payload(response)
        if session.get("card_id") == card_id:
            session["card_id"] = None
            session["guid"] = None
            session["game_id"] = None
        return self.save(session)

    def clear(self, *, include_cookies: bool = True) -> dict[str, Any]:
        removed = {
            "session_removed": False,
            "cookies_removed": False,
            "session_path": str(self.session_path),
            "cookies_path": str(self.cookies_path),
        }
        if self.session_path.exists():
            self.session_path.unlink()
            removed["session_removed"] = True
        if include_cookies and self.cookies_path.exists():
            self.cookies_path.unlink()
            removed["cookies_removed"] = True
        return removed
