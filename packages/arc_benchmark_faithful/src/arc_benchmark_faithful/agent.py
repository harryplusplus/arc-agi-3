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

from arc_benchmark_faithful.constants import (
    CODEX_HOME,
    CODEX_MODEL,
    CODEX_REASONING_EFFORT,
    CODEX_STEP_MAX_RETRIES,
    CODEX_STEP_TIMEOUT_SECONDS,
    CODEX_WRAPPER,
    REPO_ROOT,
    SCORECARD_HARNESS,
)
from arc_benchmark_faithful.experience_db import ExperienceDB
from arc_benchmark_faithful.memory import (
    GameMemory,
    build_candidate_scores,
    coarse_state_digest,
    reset_working_memory,
    state_digest,
    summarize_memory,
    update_memory,
)
from arc_benchmark_faithful.memory_store import PersistentGameMemoryStore
from arc_benchmark_faithful.shared import ObservableState, observe_state

logger = logging.getLogger(__name__)

HELPER_SCRIPT = REPO_ROOT / "scripts" / "faithful_inspect.py"


class FaithfulCodexAgent(MultimodalAgent):
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
        self.memory_store = PersistentGameMemoryStore()
        self.experience_db = ExperienceDB()

        if not self.codex_wrapper.exists():
            raise FileNotFoundError(f"Codex wrapper not found: {self.codex_wrapper}")
        if not self.codex_session_id:
            raise ValueError("codex_session_id is required")

    def get_breakpoint_spec(self) -> BreakpointSpec | None:
        return None

    def step(self, context: SessionContext) -> GameStep:
        previous_observable = self._previous_observable(context)
        observable_state = self._observe_state(context, previous_observable)
        memory = self._load_memory(context)
        if not context.history.actions:
            reset_working_memory(memory)
        last_action = str(context.history.actions[-1].action) if context.history.actions else None
        result_score = int(context.game.current_score)
        result_state = str(context.game.current_state)

        update_memory(
            memory,
            observable_state=observable_state,
            previous_observable_state=previous_observable,
            last_action=last_action,
            result_score=result_score,
            result_state=result_state,
        )
        self.memory_store.save(memory)
        context.datastore["faithful_memory"] = memory.to_dict()
        memory_summary = summarize_memory(memory)

        available_actions = [self._normalize_action_name(action) for action in context.game.available_actions]
        experience_snapshot = self.experience_db.summarize(
            str(context.game.game_id),
            state_digest(observable_state),
            coarse_state_digest(observable_state),
            available_actions,
        )
        candidate_scores = build_candidate_scores(
            memory,
            observable_state=observable_state,
            available_actions=available_actions,
            experience_snapshot=experience_snapshot,
        )
        prompt = self._build_prompt(
            context,
            observable_state,
            memory_summary,
            candidate_scores,
            experience_snapshot.to_dict(),
        )
        payload, response_text, attempts = self._query_codex_decision(
            context,
            prompt=prompt,
            available_actions=available_actions,
            candidate_scores=candidate_scores,
        )

        action = payload.get("action")
        action_name = self._normalize_action_name(action["action"])
        action["action"] = action_name
        raw_reasoning = payload.get("reasoning")
        reasoning = dict(raw_reasoning) if isinstance(raw_reasoning, dict) else {"summary": str(raw_reasoning or "")}

        reasoning.setdefault("model", self.codex_model)
        reasoning.setdefault("harness", SCORECARD_HARNESS)
        reasoning.setdefault("config", self.config)
        reasoning.setdefault("codex_session_id", self.codex_session_id)
        reasoning.setdefault("codex_model", self.codex_model)
        reasoning.setdefault("codex_reasoning_effort", self.codex_reasoning_effort)
        reasoning.setdefault("decision_mode", "codex_resume")
        reasoning.setdefault("codex_attempts", attempts)
        reasoning["observable_state"] = observable_state.to_dict()
        reasoning["memory_snapshot"] = memory_summary
        reasoning["experience_snapshot"] = experience_snapshot.to_dict()
        reasoning["candidate_scores"] = candidate_scores
        return GameStep(action=action, reasoning=reasoning)

    def _previous_observable(self, context: SessionContext) -> ObservableState | None:
        payload = context.datastore.get("faithful_observable_state")
        if isinstance(payload, dict):
            return ObservableState(**payload)
        return None

    def _observe_state(
        self,
        context: SessionContext,
        previous: ObservableState | None,
    ) -> ObservableState:
        last_action = str(context.history.actions[-1].action) if context.history.actions else None
        observable_state = observe_state(
            context.frames.frame_grids[-1],
            level_index=int(context.game.current_score),
            previous_state=previous,
            last_action=last_action,
        )
        context.datastore["faithful_observable_state"] = observable_state.to_dict()
        return observable_state

    def _load_memory(self, context: SessionContext) -> GameMemory:
        payload = context.datastore.get("faithful_memory")
        game_id = str(context.game.game_id)
        if isinstance(payload, dict):
            return GameMemory.from_dict(payload)
        return self.memory_store.load(game_id)

    def _build_prompt(
        self,
        context: SessionContext,
        observable_state: ObservableState,
        memory_summary: dict[str, Any],
        candidate_scores: dict[str, float],
        experience_snapshot: dict[str, Any],
    ) -> str:
        prompt_memory = self._compact_memory_for_prompt(memory_summary)
        prompt_experience = self._compact_experience_for_prompt(experience_snapshot)
        dominant_winning_action = self._dominant_action(prompt_experience.get("winning_state_actions"))
        dominant_exact_action = self._dominant_action(prompt_experience.get("state_actions"))
        prompt_payload = {
            "task": (
                "Choose the next ARC-AGI-3 action. You are the decision-maker for this step. "
                "Use the current observation, recent trajectory, memory snapshot, and any local evidence you need. "
                "candidate_scores are advisory, not binding."
            ),
            "mode_guidance": (
                "If planner.current_mode is goal_probe, prioritize testing the goal with the newly changed form "
                "before revisiting changers. If planner.current_mode is break_loop, choose an action that breaks "
                "the current repeated trajectory instead of repeating it."
            ),
            "operating_rules": {
                "same_session": (
                    "This run reuses one Codex session. Keep continuity with earlier failed/successful steps and "
                    "earlier diagnostics in this same session."
                ),
                "decision_authority": "Do not defer to the heuristic. Make the final action choice yourself.",
                "when_uncertain": (
                    "Inspect local files or the SQLite DB before deciding. Prefer direct evidence over guesses."
                ),
                "decision_hierarchy": [
                    "If the current exact state has a uniquely dominant winning_state_actions choice, follow it.",
                    "Do not let break_loop override a uniquely dominant winning exact-state action.",
                    "If no dominant winning exact-state action exists, use exact-state priors and candidate_scores.",
                    "Use break_loop only when exact-state winning evidence is absent or genuinely ambiguous.",
                ],
                "output_contract": {
                    "required_json_shape": {
                        "action": {"action": "ACTION1"},
                        "reasoning": {"summary": "...", "hypothesis": "..."},
                    },
                    "requirements": [
                        "Return exactly one JSON object.",
                        "Use one of the available_actions.",
                        "Do not return markdown fences or extra text.",
                    ],
                },
            },
            "tooling": {
                "repo_root": str(REPO_ROOT),
                "codex_cwd": "codex_work_faithful",
                "helper_script": str(HELPER_SCRIPT),
                "suggested_commands": [
                    "python3 ../scripts/faithful_inspect.py episode-summary --game ls20",
                    "python3 ../scripts/faithful_inspect.py latest-results --limit 3",
                    "python3 ../scripts/faithful_inspect.py latest-checkpoint --prefix local- --limit 6",
                    "python3 ../scripts/faithful_inspect.py winning-actions --game ls20 --state-digest <digest>",
                    "python3 ../scripts/faithful_inspect.py state-priors --game ls20 --state-digest <digest> --coarse-digest <digest>",
                ],
                "important_files": [
                    "../AGENTS.md",
                    "../codex_work_faithful/AGENTS.md",
                    "../skills/arc-faithful-ls20/SKILL.md",
                    "../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/agent.py",
                    "../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/memory.py",
                    "../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/experience_db.py",
                ],
            },
            "game": {
                "game_id": context.game.game_id,
                "guid": context.game.guid,
                "level_index": observable_state.level_index,
                "current_score": context.game.current_score,
                "current_state": context.game.current_state,
                "available_actions": [self._normalize_action_name(action) for action in context.game.available_actions],
            },
            "observable_state": observable_state.to_dict(),
            "state_digest": state_digest(observable_state),
            "coarse_state_digest": coarse_state_digest(observable_state),
            "priority_signals": {
                "dominant_winning_exact_action": dominant_winning_action,
                "dominant_exact_action": dominant_exact_action,
                "top_candidate_action": self._default_suggested_action(candidate_scores),
            },
            "memory": prompt_memory,
            "experience": prompt_experience,
            "candidate_scores": candidate_scores,
            "recent_actions": [
                {
                    "action_num": record.action_num,
                    "action": record.action,
                    "result_score": record.result_score,
                    "result_state": record.result_state,
                }
                for record in context.history.actions[-6:]
            ],
        }
        return json.dumps(prompt_payload, ensure_ascii=True)

    def _compact_memory_for_prompt(self, memory_summary: dict[str, Any]) -> dict[str, Any]:
        planner = dict(memory_summary.get("planner") or {})
        working = dict(memory_summary.get("working") or {})
        perceptual = dict(memory_summary.get("perceptual") or {})
        return {
            "planner": {
                "current_mode": planner.get("current_mode"),
                "goal_probe_steps_remaining": planner.get("goal_probe_steps_remaining"),
            },
            "working": {
                "current_state_repeat_hits": working.get("current_state_repeat_hits"),
                "current_coarse_repeat_hits": working.get("current_coarse_repeat_hits"),
                "current_action_attempts": working.get("current_action_attempts"),
                "recent_unique_states": working.get("recent_unique_states"),
                "visited_special_tiles": (working.get("visited_special_tiles") or [])[-8:],
            },
            "perceptual": {
                "board_ascii_available": perceptual.get("board_ascii_available"),
                "forms_seen_count": len(perceptual.get("forms_seen") or []),
            },
        }

    def _compact_experience_for_prompt(self, experience_snapshot: dict[str, Any]) -> dict[str, Any]:
        def keep_nonzero(mapping: Any) -> dict[str, Any]:
            compact: dict[str, Any] = {}
            for action, stats in (mapping or {}).items():
                attempts = int((stats or {}).get("attempts", 0) or 0)
                if attempts <= 0:
                    continue
                compact[str(action)] = {
                    "attempts": attempts,
                    "moved_rate": (stats or {}).get("moved_rate"),
                    "blocked_rate": (stats or {}).get("blocked_rate"),
                    "avg_score_delta": (stats or {}).get("avg_score_delta"),
                    "avg_level_delta": (stats or {}).get("avg_level_delta"),
                    "self_loop_rate": (stats or {}).get("self_loop_rate"),
                }
            return compact

        return {
            "episode_count": experience_snapshot.get("episode_count"),
            "best_final_score": experience_snapshot.get("best_final_score"),
            "win_count": experience_snapshot.get("win_count"),
            "state_actions": keep_nonzero(experience_snapshot.get("state_actions")),
            "winning_state_actions": keep_nonzero(experience_snapshot.get("winning_state_actions")),
            "coarse_actions": keep_nonzero(experience_snapshot.get("coarse_actions")),
            "game_actions": keep_nonzero(experience_snapshot.get("game_actions")),
        }

    def _dominant_action(self, action_stats: Any) -> dict[str, Any] | None:
        ranked: list[tuple[str, int]] = []
        for action, stats in (action_stats or {}).items():
            attempts = int((stats or {}).get("attempts", 0) or 0)
            if attempts <= 0:
                continue
            ranked.append((str(action), attempts))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (-item[1], item[0]))
        if len(ranked) == 1:
            return {"action": ranked[0][0], "attempts": ranked[0][1], "margin_over_second": ranked[0][1]}
        first, second = ranked[0], ranked[1]
        if first[1] <= second[1]:
            return None
        return {"action": first[0], "attempts": first[1], "margin_over_second": first[1] - second[1]}

    def _default_suggested_action(self, candidate_scores: dict[str, float]) -> str:
        if not candidate_scores:
            return "ACTION1"
        return max(candidate_scores.items(), key=lambda item: (item[1], item[0]))[0]

    def _normalize_action_name(self, action: Any) -> str:
        action_name = str(action)
        if action_name.isdigit():
            return f"ACTION{action_name}"
        return action_name

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
            timeout=CODEX_STEP_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "codex exec resume failed\n"
                f"exit_code={completed.returncode}\nstdout={completed.stdout}\nstderr={completed.stderr}"
            )
        response_text = self._extract_agent_message(completed.stdout)
        if response_text is None:
            raise RuntimeError(f"No agent_message item found in codex output\nstdout={completed.stdout}")
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
        raise ValueError(f"Could not parse JSON from Codex response: {response_text}")

    def _query_codex_decision(
        self,
        context: SessionContext,
        *,
        prompt: str,
        available_actions: list[str],
        candidate_scores: dict[str, float],
    ) -> tuple[dict[str, Any], str, int]:
        repair_prompt = prompt
        last_error: Exception | None = None
        for attempt in range(1, CODEX_STEP_MAX_RETRIES + 1):
            response_text = self._run_codex(repair_prompt)
            context.append_model_call(
                ModelCallRecord(
                    step_name="faithful_codex_resume",
                    action_num=context.game.action_counter + 1,
                    provider="codex-cli",
                    model=self.codex_model,
                    messages=[{"role": "user", "content": repair_prompt}],
                    response=response_text,
                )
            )
            try:
                payload = self._parse_game_step(response_text)
                action = payload.get("action")
                if not isinstance(action, dict) or not action.get("action"):
                    raise ValueError("Missing action.action in JSON payload")
                action_name = self._normalize_action_name(action["action"])
                if action_name not in available_actions:
                    raise ValueError(f"Action {action_name!r} is not in available_actions={available_actions}")
                action["action"] = action_name
                return payload, response_text, attempt
            except Exception as exc:
                last_error = exc
                repair_payload = {
                    "task": "Your previous reply was invalid. Retry and return exactly one valid JSON object only.",
                    "error": str(exc),
                    "available_actions": available_actions,
                    "suggested_default_action": self._default_suggested_action(candidate_scores),
                    "required_json_shape": {
                        "action": {"action": "ACTION1"},
                        "reasoning": {"summary": "...", "hypothesis": "..."},
                    },
                }
                repair_prompt = json.dumps(repair_payload, ensure_ascii=True)
        raise RuntimeError(f"Codex failed to return a valid action after {CODEX_STEP_MAX_RETRIES} attempts: {last_error}")
