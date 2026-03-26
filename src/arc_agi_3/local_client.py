from __future__ import annotations

from typing import Any

from arc_agi import Arcade, OperationMode
from arcengine import GameAction


ACTION_ID_TO_NAME = {
    1: "ACTION1",
    2: "ACTION2",
    3: "ACTION3",
    4: "ACTION4",
    5: "ACTION5",
    6: "ACTION6",
    7: "ACTION7",
}


class LocalArcGameClient:
    ROOT_URL = "offline://arcade"

    def __init__(self):
        self.arcade = Arcade(operation_mode=OperationMode.OFFLINE)
        self._env_by_card_id: dict[str, Any] = {}
        self._card_id_by_guid: dict[str, str] = {}

    def reset_game(self, card_id: str, game_id: str, guid: str | None = None) -> dict[str, Any]:
        env = self.arcade.make(
            game_id,
            scorecard_id=card_id,
            save_recording=False,
            include_frame_data=True,
        )
        frame = env.reset()
        self._env_by_card_id[card_id] = env
        self._card_id_by_guid[frame.guid] = card_id
        return self._frame_to_state(frame)

    def execute_action(self, action: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = data or {}
        guid = payload.get("guid")
        if not guid:
            raise ValueError("guid is required for local execute_action")
        card_id = self._card_id_by_guid.get(str(guid))
        if not card_id:
            raise KeyError(f"No local environment found for guid={guid}")
        env = self._env_by_card_id[card_id]

        step_data = {}
        if "x" in payload:
            step_data["x"] = payload["x"]
        if "y" in payload:
            step_data["y"] = payload["y"]

        frame = env.step(
            GameAction[action],
            data=step_data or None,
            reasoning=payload.get("reasoning"),
        )
        self._card_id_by_guid[frame.guid] = card_id
        return self._frame_to_state(frame)

    def close_scorecard(self, card_id: str) -> dict[str, Any]:
        return {"card_id": card_id, "mode": "offline"}

    def get_env_for_guid(self, guid: str) -> Any:
        card_id = self._card_id_by_guid.get(str(guid))
        if not card_id:
            raise KeyError(f"No local environment found for guid={guid}")
        return self._env_by_card_id[card_id]

    def get_game_for_guid(self, guid: str) -> Any:
        return self.get_env_for_guid(guid)._game

    def _frame_to_state(self, frame: Any) -> dict[str, Any]:
        state = getattr(frame.state, "name", str(frame.state))
        return {
            "guid": frame.guid,
            "levels_completed": int(frame.levels_completed),
            "state": state,
            "frame": [
                grid.tolist() if hasattr(grid, "tolist") else grid for grid in list(frame.frame)
            ],
            "available_actions": [
                ACTION_ID_TO_NAME.get(int(action_id), f"ACTION{int(action_id)}")
                for action_id in list(frame.available_actions)
            ],
        }
