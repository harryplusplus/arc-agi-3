from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha1
from typing import Any

from arc_benchmark_faithful.constants import ACTION_DELTAS
from arc_benchmark_faithful.constants import RECENT_TRAJECTORY_LIMIT, WORKING_MEMORY_LIMIT


def state_digest(observable_state: Any) -> str:
    payload = {
        "level_index": int(observable_state.level_index),
        "player_x": int(observable_state.player_x),
        "player_y": int(observable_state.player_y),
        "shape_index": int(observable_state.shape_index),
        "color_index": int(observable_state.color_index),
        "rotation_index": int(observable_state.rotation_index),
        "steps_left": int(observable_state.steps_left),
        "lives_left": int(observable_state.lives_left),
        "board_ascii": str(observable_state.board_ascii),
    }
    return sha1(repr(payload).encode("utf-8")).hexdigest()


@dataclass
class PerceptualMemory:
    last_state_digest: str = ""
    last_board_ascii: str = ""
    board_ascii_available: bool = False
    forms_seen: list[list[int]] = field(default_factory=list)


@dataclass
class SemanticMemory:
    hypotheses: list[str] = field(default_factory=list)
    counters_detected: list[str] = field(default_factory=list)
    levels_seen: list[int] = field(default_factory=list)


@dataclass
class RuleStats:
    attempts: int = 0
    moved: int = 0
    blocked: int = 0
    score_gain: int = 0
    level_advances: int = 0


@dataclass
class RuleMemory:
    action_stats: dict[str, RuleStats] = field(default_factory=dict)


@dataclass
class PlannerMemory:
    objective: str = "explore_and_model"
    current_mode: str = "novelty"
    last_candidate_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class WorkingEntry:
    state_digest: str
    action: str | None
    score: int
    state: str


@dataclass
class WorkingMemory:
    recent: list[WorkingEntry] = field(default_factory=list)
    repeated_state_hits: dict[str, int] = field(default_factory=dict)
    attempted_pairs: dict[str, int] = field(default_factory=dict)


@dataclass
class GameMemory:
    game_id: str
    perceptual: PerceptualMemory = field(default_factory=PerceptualMemory)
    semantic: SemanticMemory = field(default_factory=SemanticMemory)
    rule: RuleMemory = field(default_factory=RuleMemory)
    planner: PlannerMemory = field(default_factory=PlannerMemory)
    working: WorkingMemory = field(default_factory=WorkingMemory)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameMemory":
        mem = cls(game_id=str(data["game_id"]))
        mem.perceptual = PerceptualMemory(**data.get("perceptual", {}))
        mem.semantic = SemanticMemory(**data.get("semantic", {}))
        rule_stats = {}
        for key, value in data.get("rule", {}).get("action_stats", {}).items():
            rule_stats[str(key)] = RuleStats(**value)
        mem.rule = RuleMemory(action_stats=rule_stats)
        mem.planner = PlannerMemory(**data.get("planner", {}))
        recent = [WorkingEntry(**entry) for entry in data.get("working", {}).get("recent", [])]
        mem.working = WorkingMemory(
            recent=recent,
            repeated_state_hits={str(k): int(v) for k, v in data.get("working", {}).get("repeated_state_hits", {}).items()},
            attempted_pairs={str(k): int(v) for k, v in data.get("working", {}).get("attempted_pairs", {}).items()},
        )
        return mem


def update_memory(
    memory: GameMemory,
    *,
    observable_state: Any,
    previous_observable_state: Any | None,
    last_action: str | None,
    result_score: int,
    result_state: str,
) -> None:
    digest = state_digest(observable_state)
    memory.perceptual.last_state_digest = digest
    memory.perceptual.last_board_ascii = str(observable_state.board_ascii)
    memory.perceptual.board_ascii_available = bool(observable_state.board_ascii)
    form = [
        int(observable_state.shape_index),
        int(observable_state.color_index),
        int(observable_state.rotation_index),
    ]
    if form not in memory.perceptual.forms_seen:
        memory.perceptual.forms_seen.append(form)
    level_index = int(observable_state.level_index)
    if level_index not in memory.semantic.levels_seen:
        memory.semantic.levels_seen.append(level_index)
    if "step_counter" not in memory.semantic.counters_detected:
        memory.semantic.counters_detected.append("step_counter")
    if "life_counter" not in memory.semantic.counters_detected:
        memory.semantic.counters_detected.append("life_counter")
    if memory.perceptual.board_ascii_available and "board_ascii_tracks_visible_objects" not in memory.semantic.hypotheses:
        memory.semantic.hypotheses.append("board_ascii_tracks_visible_objects")

    memory.working.repeated_state_hits[digest] = memory.working.repeated_state_hits.get(digest, 0) + 1
    memory.working.recent.append(
        WorkingEntry(
            state_digest=digest,
            action=last_action,
            score=int(result_score),
            state=str(result_state),
        )
    )
    memory.working.recent[:] = memory.working.recent[-WORKING_MEMORY_LIMIT:]

    if last_action:
        prior_digest = state_digest(previous_observable_state) if previous_observable_state is not None else digest
        pair_key = f"{prior_digest}:{last_action}"
        memory.working.attempted_pairs[pair_key] = memory.working.attempted_pairs.get(pair_key, 0) + 1
        stats = memory.rule.action_stats.setdefault(last_action, RuleStats())
        stats.attempts += 1
        if previous_observable_state is not None:
            moved = (
                int(previous_observable_state.player_x) != int(observable_state.player_x)
                or int(previous_observable_state.player_y) != int(observable_state.player_y)
            )
            if moved:
                stats.moved += 1
            else:
                stats.blocked += 1
            if int(previous_observable_state.level_index) != level_index:
                stats.level_advances += 1
                stats.score_gain += max(0, level_index - int(previous_observable_state.level_index))

    if memory.working.repeated_state_hits.get(digest, 0) >= 3:
        memory.planner.current_mode = "break_loop"
    else:
        memory.planner.current_mode = "novelty"


def build_candidate_scores(
    memory: GameMemory,
    *,
    observable_state: Any,
    available_actions: list[str],
) -> dict[str, float]:
    scores: dict[str, float] = {}
    recent_actions = [entry.action for entry in memory.working.recent if entry.action][-RECENT_TRAJECTORY_LIMIT:]
    current_digest = state_digest(observable_state)
    repeated_hits = memory.working.repeated_state_hits.get(current_digest, 0)
    board_adjustments = _board_action_adjustments(observable_state)
    for action in available_actions:
        score = 0.0
        pair_key = f"{current_digest}:{action}"
        score -= 0.75 * memory.working.attempted_pairs.get(pair_key, 0)
        if recent_actions and action == recent_actions[-1]:
            score -= 0.5
        if action in recent_actions[-3:]:
            score -= 0.25
        stats = memory.rule.action_stats.get(action)
        if stats and stats.attempts:
            score += 0.4 * (stats.moved / stats.attempts)
            score -= 0.3 * (stats.blocked / stats.attempts)
            score += 0.1 * stats.level_advances
        if repeated_hits >= 2 and action in recent_actions[-2:]:
            score -= 1.0
        if action == "ACTION7":
            score -= 2.0
        score += board_adjustments.get(action, 0.0)
        scores[action] = score
    memory.planner.last_candidate_scores = scores
    return scores


def _board_action_adjustments(observable_state: Any) -> dict[str, float]:
    board_ascii = str(getattr(observable_state, "board_ascii", "") or "")
    lines = board_ascii.splitlines()
    if not lines:
        return {}

    player_rc: tuple[int, int] | None = None
    targets: list[tuple[int, int]] = []
    for row_index, line in enumerate(lines):
        for col_index, char in enumerate(line):
            if char == "@":
                player_rc = (row_index, col_index)
            elif char not in {".", "#"}:
                targets.append((row_index, col_index))

    if player_rc is None:
        return {}

    def nearest_distance(position: tuple[int, int]) -> int:
        if not targets:
            return 0
        row, col = position
        return min(abs(target_row - row) + abs(target_col - col) for target_row, target_col in targets)

    base_distance = nearest_distance(player_rc)
    adjustments: dict[str, float] = {}
    for action, (dx, dy) in ACTION_DELTAS.items():
        row = player_rc[0] + (1 if dy > 0 else -1 if dy < 0 else 0)
        col = player_rc[1] + (1 if dx > 0 else -1 if dx < 0 else 0)
        if row < 0 or row >= len(lines) or col < 0 or col >= len(lines[row]):
            adjustments[action] = -2.0
            continue
        next_char = lines[row][col]
        score = 0.0
        if next_char == "#":
            score -= 2.0
        else:
            next_distance = nearest_distance((row, col))
            score += 0.25 * (base_distance - next_distance)
            if next_char not in {".", "@", "#"}:
                score += 1.0
        adjustments[action] = score
    return adjustments


def summarize_memory(memory: GameMemory) -> dict[str, Any]:
    return {
        "perceptual": asdict(memory.perceptual),
        "semantic": {
            "hypotheses": list(memory.semantic.hypotheses[-8:]),
            "counters_detected": list(memory.semantic.counters_detected),
            "levels_seen": list(memory.semantic.levels_seen[-8:]),
        },
        "rule": {
            action: asdict(stats) for action, stats in memory.rule.action_stats.items()
        },
        "planner": asdict(memory.planner),
        "working": {
            "recent": [asdict(entry) for entry in memory.working.recent[-RECENT_TRAJECTORY_LIMIT:]],
            "repeated_state_hits": dict(memory.working.repeated_state_hits),
        },
    }
