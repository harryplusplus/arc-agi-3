from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from arcagi3.agent import MultimodalAgent
from arcagi3.breakpoints.manager import BreakpointManager
from arcagi3.breakpoints.spec import BreakpointSpec, load_breakpoint_spec
from arcagi3.game_client import GameClient
from arcagi3.schemas import GameStep, ModelCallRecord
from arcagi3.utils.context import SessionContext

from arc_agi_3.constants import (
    ACTION_DESCRIPTIONS,
    CODEX_HOME,
    CODEX_MODEL,
    CODEX_REASONING_EFFORT,
    CODEX_WRAPPER,
    OFFLINE_PLANNER_EXPANSION_LIMIT,
    OFFLINE_PLANNER_PREVIEW_ACTIONS,
    OFFLINE_PLANNER_TIME_LIMIT_S,
    REPO_ROOT,
)
from arc_agi_3.local_client import LocalArcGameClient
from arc_agi_3.offline_planner import (
    OfflinePlanningError,
    build_suffix_plan_cache,
    solve_current_level,
    state_digest,
    summarize_game,
)

logger = logging.getLogger(__name__)


class CodexResumeAgent(MultimodalAgent):
    def __init__(
        self,
        config: str,
        game_client: GameClient,
        card_id: str,
        max_actions: int = 40,
        num_plays: int = 1,
        max_episode_actions: int = 0,
        checkpoint_frequency: int = 1,
        checkpoint_dir: str | None = None,
        breakpoints_enabled: bool = False,
        breakpoint_ws_url: str = "ws://localhost:8765/ws",
        breakpoint_schema_path: str | None = None,
        codex_wrapper: Path = CODEX_WRAPPER,
        codex_home: Path = CODEX_HOME,
        codex_session_id: str | None = None,
        codex_model: str = CODEX_MODEL,
        codex_reasoning_effort: str = CODEX_REASONING_EFFORT,
        use_vision: bool = False,
        show_images: bool = False,
        memory_word_limit: int = 500,
    ):
        self.config = config
        self.game_client = game_client
        self.card_id = card_id
        self.max_actions = max_actions
        self.num_plays = num_plays
        self.max_episode_actions = max_episode_actions
        self.provider = None
        self.checkpoint_frequency = checkpoint_frequency
        self.checkpoint_dir = checkpoint_dir
        self._breakpoints_enabled = breakpoints_enabled
        self._breakpoint_ws_url = breakpoint_ws_url
        self._breakpoint_schema_path = breakpoint_schema_path
        self._breakpoint_config_spec = load_breakpoint_spec(breakpoint_schema_path)
        self.breakpoint_manager: BreakpointManager | None = None
        if self._breakpoints_enabled and self._breakpoint_config_spec:
            self.breakpoint_manager = BreakpointManager(
                enabled=True,
                ws_url=self._breakpoint_ws_url,
                spec=self._breakpoint_config_spec,
                hooks={},
            )
            self.breakpoint_manager.update_identity(config=self.config, card_id=self.card_id)

        self.codex_wrapper = Path(codex_wrapper)
        self.codex_home = Path(codex_home)
        self.codex_session_id = codex_session_id or ""
        self.codex_model = codex_model
        self.codex_reasoning_effort = codex_reasoning_effort
        self.use_vision = use_vision
        self.show_images = show_images
        self.memory_word_limit = memory_word_limit
        self._offline_plan_cache: dict[str, tuple[str, ...]] = {}
        self._offline_plan_meta: dict[str, Any] = {}

        if not self.codex_wrapper.exists():
            raise FileNotFoundError(f"Codex wrapper not found: {self.codex_wrapper}")
        if not self.codex_session_id:
            raise ValueError("codex_session_id is required")
        if not self._session_file_exists():
            raise FileNotFoundError(
                "Dedicated Codex session file not found under CODEX_HOME. "
                f"Expected session {self.codex_session_id} in {self.codex_home}"
            )

    def get_breakpoint_spec(self) -> BreakpointSpec | None:
        return None

    def step(self, context: SessionContext) -> GameStep:
        planner_summary: dict[str, Any] | None = None
        planner_action: str | None = None
        planner_error: str | None = None
        local_game: Any | None = None

        if isinstance(self.game_client, LocalArcGameClient) and context.game.guid:
            try:
                local_game = self.game_client.get_game_for_guid(context.game.guid)
                planner_summary, planner_action = self._get_offline_planner_summary(local_game)
            except OfflinePlanningError as exc:
                planner_error = str(exc)
                logger.warning("Offline planner failed: %s", exc)
            except Exception:
                logger.exception("Unexpected offline planner failure")
                planner_error = "offline planner crashed unexpectedly"

        prompt = self._build_prompt(
            context,
            planner_summary=planner_summary,
            planner_error=planner_error,
            local_game=local_game,
        )
        response_text = self._run_codex(prompt)
        payload = self._parse_game_step(response_text)

        context.append_model_call(
            ModelCallRecord(
                step_name="codex_resume",
                action_num=context.game.action_counter + 1,
                provider="codex-cli",
                model=self.codex_model,
                messages=[{"role": "user", "content": prompt}],
                response=response_text,
            )
        )

        action = payload.get("action")
        if not isinstance(action, dict) or not action.get("action"):
            raise ValueError(f"Codex response missing action payload: {payload}")
        codex_action_name = str(action.get("action"))

        reasoning = payload.get("reasoning")
        if not isinstance(reasoning, dict):
            reasoning = {"raw_reasoning": str(reasoning) if reasoning is not None else ""}
        reasoning.setdefault("codex_session_id", self.codex_session_id)
        reasoning.setdefault("codex_model", self.codex_model)
        reasoning.setdefault("codex_reasoning_effort", self.codex_reasoning_effort)
        if planner_summary is not None:
            reasoning.setdefault("planner", planner_summary)
        if planner_error is not None:
            reasoning.setdefault("planner_error", planner_error)
        if planner_action and codex_action_name != planner_action:
            reasoning["codex_requested_action"] = codex_action_name
            reasoning["planner_override"] = True
            action = {"action": planner_action}

        return GameStep(action=action, reasoning=reasoning)

    def _session_file_exists(self) -> bool:
        pattern = f"**/*{self.codex_session_id}.jsonl"
        return any(self.codex_home.joinpath("sessions").glob(pattern))

    def _build_prompt(
        self,
        context: SessionContext,
        *,
        planner_summary: dict[str, Any] | None = None,
        planner_error: str | None = None,
        local_game: Any | None = None,
    ) -> str:
        frames = [frame for frame in context.frames.frame_grids]
        last_actions = [
            {
                "action_num": record.action_num,
                "action": record.action,
                "result_score": record.result_score,
                "result_state": record.result_state,
                "reasoning": record.reasoning,
            }
            for record in context.history.actions[-8:]
        ]
        prompt_payload = {
            "task": (
                "Choose the next ARC-AGI-3 action for this state and reply as the required JSON object. "
                "If planner guidance is present, it comes from an offline shortest-path search over the real game "
                "simulator and should be followed to minimize remaining actions."
            ),
            "game": {
                "game_id": context.game.game_id,
                "guid": context.game.guid,
                "current_score": context.game.current_score,
                "current_state": context.game.current_state,
                "play_num": context.game.play_num,
                "play_action_counter": context.game.play_action_counter,
                "action_counter": context.game.action_counter,
                "available_actions": list(context.game.available_actions),
                "available_action_descriptions": {
                    action: ACTION_DESCRIPTIONS.get(action, action)
                    for action in context.game.available_actions
                },
            },
            "history": {
                "recent_actions": last_actions,
            },
        }
        if planner_summary is not None:
            prompt_payload["planner"] = planner_summary
        if planner_error is not None:
            prompt_payload["planner_error"] = planner_error
        if local_game is not None:
            prompt_payload["symbolic_state"] = summarize_game(local_game)
        else:
            prompt_payload["observation"] = {
                "frame_grids": frames,
            }
        return json.dumps(prompt_payload, ensure_ascii=True)

    def _get_offline_planner_summary(self, local_game: Any) -> tuple[dict[str, Any], str]:
        digest = state_digest(local_game)
        cached_actions = self._offline_plan_cache.get(digest)
        if cached_actions:
            planner_summary = dict(self._offline_plan_meta.get(digest, {}))
            planner_summary["remaining_actions"] = len(cached_actions)
            planner_summary["next_action"] = cached_actions[0]
            planner_summary["action_plan_preview"] = list(cached_actions[:OFFLINE_PLANNER_PREVIEW_ACTIONS])
            return planner_summary, cached_actions[0]

        level_plan = solve_current_level(
            local_game,
            time_limit_s=OFFLINE_PLANNER_TIME_LIMIT_S,
            expansion_limit=OFFLINE_PLANNER_EXPANSION_LIMIT,
        )
        suffix_cache = build_suffix_plan_cache(local_game, level_plan.actions)
        base_summary = level_plan.to_prompt_dict(preview_actions=OFFLINE_PLANNER_PREVIEW_ACTIONS)
        for suffix_digest, suffix_actions in suffix_cache.items():
            self._offline_plan_cache[suffix_digest] = suffix_actions
            summary = dict(base_summary)
            summary["remaining_actions"] = len(suffix_actions)
            summary["next_action"] = suffix_actions[0] if suffix_actions else None
            summary["action_plan_preview"] = list(suffix_actions[:OFFLINE_PLANNER_PREVIEW_ACTIONS])
            summary["cached"] = suffix_digest != digest
            self._offline_plan_meta[suffix_digest] = summary

        return self._offline_plan_meta[digest], self._offline_plan_cache[digest][0]

    def _run_codex(self, prompt: str) -> str:
        cmd = [
            str(self.codex_wrapper),
            "exec",
            "resume",
            self.codex_session_id,
            "--json",
            prompt,
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
                "codex exec resume failed\n"
                f"exit_code={completed.returncode}\n"
                f"stdout={completed.stdout}\n"
                f"stderr={completed.stderr}"
            )

        response_text = self._extract_agent_message(completed.stdout)
        if response_text is None:
            raise RuntimeError(
                "No agent_message item found in codex output\n"
                f"stdout={completed.stdout}\n"
                f"stderr={completed.stderr}"
            )
        return response_text

    def _extract_agent_message(self, stdout: str) -> str | None:
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "item.completed":
                continue
            item = event.get("item") or {}
            if item.get("type") == "agent_message":
                return str(item.get("text", ""))
        return None

    def _parse_game_step(self, response_text: str) -> dict[str, Any]:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()

        decoder = json.JSONDecoder()
        for index, char in enumerate(cleaned):
            if char != "{":
                continue
            try:
                payload, _ = decoder.raw_decode(cleaned[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        raise ValueError(f"Could not parse JSON object from codex response: {response_text}")
