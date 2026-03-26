from __future__ import annotations

from collections import deque
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


def coarse_state_digest(observable_state: Any) -> str:
    payload = {
        "level_index": int(observable_state.level_index),
        "player_x": int(observable_state.player_x),
        "player_y": int(observable_state.player_y),
        "shape_index": int(observable_state.shape_index),
        "color_index": int(observable_state.color_index),
        "rotation_index": int(observable_state.rotation_index),
        "board_ascii": str(observable_state.board_ascii),
    }
    return sha1(repr(payload).encode("utf-8")).hexdigest()


@dataclass
class PerceptualMemory:
    last_state_digest: str = ""
    last_coarse_state_digest: str = ""
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
    goal_probe_steps_remaining: int = 0
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
    coarse_repeated_hits: dict[str, int] = field(default_factory=dict)
    attempted_pairs: dict[str, int] = field(default_factory=dict)
    visited_special_tiles: list[str] = field(default_factory=list)


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
            coarse_repeated_hits={str(k): int(v) for k, v in data.get("working", {}).get("coarse_repeated_hits", {}).items()},
            attempted_pairs={str(k): int(v) for k, v in data.get("working", {}).get("attempted_pairs", {}).items()},
            visited_special_tiles=[str(value) for value in data.get("working", {}).get("visited_special_tiles", [])],
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
    coarse_digest = coarse_state_digest(observable_state)
    memory.perceptual.last_state_digest = digest
    memory.perceptual.last_coarse_state_digest = coarse_digest
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
    current_player_rc = _find_player_rc(str(observable_state.board_ascii))
    previous_board_ascii = str(getattr(previous_observable_state, "board_ascii", "") or "")
    if current_player_rc is not None and previous_board_ascii:
        previous_lines = previous_board_ascii.splitlines()
        row, col = current_player_rc
        if row < len(previous_lines) and col < len(previous_lines[row]):
            previous_char = previous_lines[row][col]
            if previous_char in {"B", "G", "T", "C", "R"}:
                visited_key = f"{int(observable_state.level_index)}:{row}:{col}:{previous_char}"
                if visited_key not in memory.working.visited_special_tiles:
                    memory.working.visited_special_tiles.append(visited_key)

    form_changed = False
    if previous_observable_state is not None:
        form_changed = any(
            int(getattr(previous_observable_state, field_name)) != int(getattr(observable_state, field_name))
            for field_name in ("shape_index", "color_index", "rotation_index")
        )

    memory.working.repeated_state_hits[digest] = memory.working.repeated_state_hits.get(digest, 0) + 1
    memory.working.coarse_repeated_hits[coarse_digest] = memory.working.coarse_repeated_hits.get(coarse_digest, 0) + 1
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

    if form_changed:
        memory.planner.goal_probe_steps_remaining = 6
    elif memory.planner.goal_probe_steps_remaining > 0:
        memory.planner.goal_probe_steps_remaining -= 1

    if memory.planner.goal_probe_steps_remaining > 0:
        memory.planner.current_mode = "goal_probe"
    elif (
        memory.working.repeated_state_hits.get(digest, 0) >= 3
        or memory.working.coarse_repeated_hits.get(coarse_digest, 0) >= 4
        or _recent_cycle_detected(memory)
    ):
        memory.planner.current_mode = "break_loop"
    else:
        memory.planner.current_mode = "novelty"


def reset_working_memory(memory: GameMemory) -> None:
    memory.working = WorkingMemory()
    memory.planner.current_mode = "novelty"
    memory.planner.goal_probe_steps_remaining = 0
    memory.planner.last_candidate_scores = {}


def build_candidate_scores(
    memory: GameMemory,
    *,
    observable_state: Any,
    available_actions: list[str],
    experience_snapshot: Any | None = None,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    recent_actions = [entry.action for entry in memory.working.recent if entry.action][-RECENT_TRAJECTORY_LIMIT:]
    current_digest = state_digest(observable_state)
    repeated_hits = memory.working.repeated_state_hits.get(current_digest, 0)
    coarse_hits = memory.working.coarse_repeated_hits.get(coarse_state_digest(observable_state), 0)
    board_adjustments = _board_action_adjustments(
        observable_state,
        prefer_special_tiles=_prefer_special_tiles(memory),
        visited_special_tiles=set(memory.working.visited_special_tiles),
    )
    inverse_actions = {
        "ACTION1": "ACTION2",
        "ACTION2": "ACTION1",
        "ACTION3": "ACTION4",
        "ACTION4": "ACTION3",
    }
    for action in available_actions:
        score = 0.0
        pair_key = f"{current_digest}:{action}"
        score -= 0.75 * memory.working.attempted_pairs.get(pair_key, 0)
        if recent_actions and action == recent_actions[-1]:
            score -= 0.5
        if recent_actions and action == inverse_actions.get(recent_actions[-1]):
            score -= 0.9
        if action in recent_actions[-3:]:
            score -= 0.25
        if len(recent_actions) >= 3 and recent_actions[-3] == action and recent_actions[-2] == inverse_actions.get(action) and recent_actions[-1] == action:
            score -= 1.25
        stats = memory.rule.action_stats.get(action)
        if stats and stats.attempts:
            score += 0.4 * (stats.moved / stats.attempts)
            score -= 0.3 * (stats.blocked / stats.attempts)
            score += 0.1 * stats.level_advances
        if repeated_hits >= 2 and action in recent_actions[-2:]:
            score -= 1.0
        if coarse_hits >= 3 and action in recent_actions[-4:]:
            score -= 0.8
        if action == "ACTION7":
            score -= 2.0
        score += board_adjustments.get(action, 0.0)
        score += _experience_score_adjustment(
            experience_snapshot,
            action,
            planner_mode=memory.planner.current_mode,
        )
        scores[action] = score
    memory.planner.last_candidate_scores = scores
    return scores


def _prefer_special_tiles(memory: GameMemory) -> bool:
    if memory.planner.goal_probe_steps_remaining > 0:
        return False
    if memory.planner.current_mode == "break_loop":
        return True
    recent = memory.working.recent[-6:]
    if len(recent) < 4:
        return False
    scores = {entry.score for entry in recent}
    states = {entry.state for entry in recent}
    return len(scores) == 1 and states == {"NOT_FINISHED"}


def _recent_cycle_detected(memory: GameMemory) -> bool:
    recent_states = [entry.state_digest for entry in memory.working.recent[-8:]]
    recent_actions = [entry.action for entry in memory.working.recent[-8:] if entry.action]
    if len(recent_states) < 8:
        return False
    if recent_states[-8:-4] == recent_states[-4:]:
        return True
    if len(recent_actions) >= 8 and recent_actions[-8:-4] == recent_actions[-4:]:
        return True
    return len(set(recent_states)) <= 4


def _board_action_adjustments(
    observable_state: Any,
    *,
    prefer_special_tiles: bool,
    visited_special_tiles: set[str],
) -> dict[str, float]:
    board_ascii = str(getattr(observable_state, "board_ascii", "") or "")
    lines = board_ascii.splitlines()
    if not lines:
        return {}

    player_rc: tuple[int, int] | None = None
    targets_by_type: dict[str, list[tuple[int, int]]] = {}
    for row_index, line in enumerate(lines):
        for col_index, char in enumerate(line):
            if char == "@":
                player_rc = (row_index, col_index)
            elif char not in {".", "#"}:
                targets_by_type.setdefault(char, []).append((row_index, col_index))

    if player_rc is None:
        return {}

    level_index = int(observable_state.level_index)
    special_chars = {"B", "T", "C", "R"}
    unvisited_special_targets: dict[str, list[tuple[int, int]]] = {}
    for char in special_chars:
        for row, col in targets_by_type.get(char, []):
            if f"{level_index}:{row}:{col}:{char}" not in visited_special_tiles:
                unvisited_special_targets.setdefault(char, []).append((row, col))

    focus_unvisited_specials = prefer_special_tiles and any(unvisited_special_targets.values())

    def nearest_distance(position: tuple[int, int], targets: list[tuple[int, int]]) -> int:
        if not targets:
            return 0
        queue = deque([(position[0], position[1], 0)])
        visited = {position}
        target_set = set(targets)
        while queue:
            row, col, distance = queue.popleft()
            if (row, col) in target_set:
                return distance
            for delta_row, delta_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                next_row = row + delta_row
                next_col = col + delta_col
                if next_row < 0 or next_row >= len(lines):
                    continue
                if next_col < 0 or next_col >= len(lines[next_row]):
                    continue
                if lines[next_row][next_col] == "#":
                    continue
                next_position = (next_row, next_col)
                if next_position in visited:
                    continue
                visited.add(next_position)
                queue.append((next_row, next_col, distance + 1))
        row, col = position
        return min(abs(target_row - row) + abs(target_col - col) for target_row, target_col in targets) + 8

    def typed_bonus(position: tuple[int, int]) -> float:
        bonuses = {
            "G": 0.65,
            "B": 0.35,
            "T": 0.35,
            "C": 0.35,
            "R": 0.35,
            ">": -0.2,
            "<": -0.2,
            "^": -0.2,
            "v": -0.2,
            "P": -0.2,
        }
        row, col = position
        if row < 0 or row >= len(lines) or col < 0 or col >= len(lines[row]):
            return -2.0
        char = lines[row][col]
        bonus = bonuses.get(char, 0.0)
        special_key = f"{int(observable_state.level_index)}:{row}:{col}:{char}"
        if char in {"B", "G", "T", "C", "R"}:
            if special_key in visited_special_tiles:
                bonus -= 0.3 if char != "G" else 0.15
            else:
                bonus += 0.35 if char != "G" else 0.15
        if focus_unvisited_specials:
            if char in special_chars:
                if special_key in visited_special_tiles:
                    bonus -= 0.8
                else:
                    bonus += 1.6
            elif char == "G":
                bonus -= 0.35
        return bonus

    distance_targets = {
        "goal": [] if focus_unvisited_specials else targets_by_type.get("G", []),
        "refill": unvisited_special_targets.get("B", []) if focus_unvisited_specials else targets_by_type.get("B", []),
        "shape": unvisited_special_targets.get("T", []) if focus_unvisited_specials else targets_by_type.get("T", []),
        "color": unvisited_special_targets.get("C", []) if focus_unvisited_specials else targets_by_type.get("C", []),
        "rotation": unvisited_special_targets.get("R", []) if focus_unvisited_specials else targets_by_type.get("R", []),
    }
    distance_weights = {
        "goal": 0.05 if focus_unvisited_specials else (0.15 if prefer_special_tiles else 0.45),
        "refill": 0.85 if focus_unvisited_specials else (0.35 if prefer_special_tiles else 0.2),
        "shape": 0.85 if focus_unvisited_specials else (0.35 if prefer_special_tiles else 0.2),
        "color": 0.85 if focus_unvisited_specials else (0.35 if prefer_special_tiles else 0.2),
        "rotation": 0.85 if focus_unvisited_specials else (0.35 if prefer_special_tiles else 0.2),
    }
    base_distances = {
        key: nearest_distance(player_rc, values)
        for key, values in distance_targets.items()
        if values
    }
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
            next_position = (row, col)
            for key, targets in distance_targets.items():
                if not targets:
                    continue
                distance_delta = base_distances[key] - nearest_distance(next_position, targets)
                score += distance_weights[key] * distance_delta
            score += typed_bonus(next_position)
        adjustments[action] = score
    return adjustments


def _experience_score_adjustment(
    experience_snapshot: Any | None,
    action: str,
    *,
    planner_mode: str,
) -> float:
    if experience_snapshot is None:
        return 0.0

    state_actions = getattr(experience_snapshot, "state_actions", {}) or {}
    winning_state_actions = getattr(experience_snapshot, "winning_state_actions", {}) or {}
    coarse_actions = getattr(experience_snapshot, "coarse_actions", {}) or {}
    game_actions = getattr(experience_snapshot, "game_actions", {}) or {}

    state_total_attempts = sum(int(getattr(stats, "attempts", 0) or 0) for stats in state_actions.values())
    winning_state_total_attempts = sum(int(getattr(stats, "attempts", 0) or 0) for stats in winning_state_actions.values())
    coarse_total_attempts = sum(int(getattr(stats, "attempts", 0) or 0) for stats in coarse_actions.values())
    state_nonzero_actions = sum(1 for stats in state_actions.values() if int(getattr(stats, "attempts", 0) or 0) > 0)

    score = 0.0
    score += _action_experience_score(winning_state_actions.get(action), factor=2.8)
    score += _action_experience_score(state_actions.get(action), factor=1.25)
    score += _action_experience_score(
        coarse_actions.get(action),
        factor=0.45 if planner_mode == "break_loop" else 0.6,
    )
    score += _action_experience_score(
        game_actions.get(action),
        factor=0.0 if planner_mode == "break_loop" else 0.35,
    )

    action_winning_state_attempts = int(getattr(winning_state_actions.get(action), "attempts", 0) or 0)
    if winning_state_total_attempts > 0:
        if action_winning_state_attempts > 0:
            score += 4.0 * (action_winning_state_attempts / winning_state_total_attempts)
        else:
            score -= 1.5
        return score

    action_state_attempts = int(getattr(state_actions.get(action), "attempts", 0) or 0)
    if state_total_attempts > 0:
        if action_state_attempts > 0:
            score += 1.6 * (action_state_attempts / state_total_attempts)
            if state_nonzero_actions == 1:
                score += 1.2
        else:
            score -= 0.6
    elif planner_mode == "break_loop" and coarse_total_attempts > 0:
        action_coarse_attempts = int(getattr(coarse_actions.get(action), "attempts", 0) or 0)
        if action_coarse_attempts <= 0:
            score -= 0.35

    best_final_score = int(getattr(experience_snapshot, "best_final_score", 0) or 0)
    episode_count = int(getattr(experience_snapshot, "episode_count", 0) or 0)
    if best_final_score > 0 and episode_count > 0:
        score += min(0.4, 0.05 * best_final_score)
    return score


def _action_experience_score(stats: Any | None, *, factor: float) -> float:
    if stats is None:
        return 0.0
    attempts = int(getattr(stats, "attempts", 0) or 0)
    if attempts <= 0:
        return 0.0
    confidence = min(1.0, attempts / 4.0)
    moved_rate = float(getattr(stats, "moved_rate", 0.0) or 0.0)
    blocked_rate = float(getattr(stats, "blocked_rate", 0.0) or 0.0)
    avg_score_delta = float(getattr(stats, "avg_score_delta", 0.0) or 0.0)
    avg_level_delta = float(getattr(stats, "avg_level_delta", 0.0) or 0.0)
    self_loop_rate = float(getattr(stats, "self_loop_rate", 0.0) or 0.0)
    raw = (
        0.9 * moved_rate
        - 0.9 * blocked_rate
        + 2.0 * avg_level_delta
        + 0.5 * avg_score_delta
        - 0.8 * self_loop_rate
    )
    return factor * confidence * raw


def summarize_memory(memory: GameMemory) -> dict[str, Any]:
    current_digest = memory.perceptual.last_state_digest
    current_coarse_digest = memory.perceptual.last_coarse_state_digest
    current_coarse_hits = memory.working.coarse_repeated_hits.get(current_coarse_digest, 0) if current_coarse_digest else 0
    current_action_attempts: dict[str, int] = {}
    if current_digest:
        prefix = f"{current_digest}:"
        for pair_key, count in memory.working.attempted_pairs.items():
            if pair_key.startswith(prefix):
                current_action_attempts[pair_key[len(prefix) :]] = count
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
            "current_state_repeat_hits": memory.working.repeated_state_hits.get(current_digest, 0),
            "current_coarse_repeat_hits": current_coarse_hits,
            "current_action_attempts": current_action_attempts,
            "recent_unique_states": len({entry.state_digest for entry in memory.working.recent}),
            "visited_special_tiles": list(memory.working.visited_special_tiles[-12:]),
        },
    }


def _find_player_rc(board_ascii: str) -> tuple[int, int] | None:
    for row_index, line in enumerate(board_ascii.splitlines()):
        col_index = line.find("@")
        if col_index >= 0:
            return row_index, col_index
    return None
