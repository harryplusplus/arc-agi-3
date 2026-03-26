from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha1
from heapq import heappop, heappush
from itertools import count
from time import perf_counter
from typing import Any

from arcengine import ActionInput, GameAction


ACTION_ORDER = ("ACTION1", "ACTION2", "ACTION3", "ACTION4")
ACTION_NAME_TO_ENUM = {
    "ACTION1": GameAction.ACTION1,
    "ACTION2": GameAction.ACTION2,
    "ACTION3": GameAction.ACTION3,
    "ACTION4": GameAction.ACTION4,
}


class OfflinePlanningError(RuntimeError):
    pass


@dataclass(frozen=True)
class LevelPlan:
    level_index: int
    actions: tuple[str, ...]
    expansions: int
    elapsed_s: float
    remaining_goals: int
    steps_left: int
    lives_left: int

    def to_prompt_dict(self, preview_actions: int = 16) -> dict[str, Any]:
        return {
            "level_index": self.level_index,
            "remaining_actions": len(self.actions),
            "next_action": self.actions[0] if self.actions else None,
            "action_plan_preview": list(self.actions[:preview_actions]),
            "expansions": self.expansions,
            "elapsed_s": round(self.elapsed_s, 3),
            "remaining_goals": self.remaining_goals,
            "steps_left": self.steps_left,
            "lives_left": self.lives_left,
        }


@dataclass(frozen=True)
class SimpleGoal:
    position: tuple[int, int]
    shape_index: int
    color_index: int
    rotation_index: int


@dataclass(frozen=True)
class SimpleLevelSpec:
    level_index: int
    start_position: tuple[int, int]
    start_shape_index: int
    start_color_index: int
    start_rotation_index: int
    step_max: int
    step_decrement: int
    cell_width: int
    cell_height: int
    shape_cycle: int
    color_cycle: int
    rotation_cycle: int
    goals: tuple[SimpleGoal, ...]
    pushers: tuple[tuple[int, int, int, int, int, int], ...]
    all_goals_mask: int
    goal_index_by_position: tuple[tuple[tuple[int, int], int], ...]
    refill_index_by_position: tuple[tuple[tuple[int, int], int], ...]
    collision_items: tuple[tuple[int, int, str, int | None], ...]
    walls: frozenset[tuple[int, int]]
    shape_changers: frozenset[tuple[int, int]]
    color_changers: frozenset[tuple[int, int]]
    rotation_changers: frozenset[tuple[int, int]]


def state_key(game: Any) -> tuple[Any, ...]:
    return (
        int(game._current_level_index),
        int(game._score),
        int(game.gudziatsk.x),
        int(game.gudziatsk.y),
        int(game.fwckfzsyc),
        int(game.hiaauhahz),
        int(game.cklxociuu),
        tuple(bool(value) for value in game.lvrnuajbl),
        int(game._step_counter_ui.current_steps),
        int(game.aqygnziho),
        tuple(sorted((int(sprite.x), int(sprite.y), str(sprite.name)) for sprite in game.ofoahudlo)),
        tuple(sorted((int(sprite.x), int(sprite.y), str(sprite.name)) for sprite in game.byotxmvkt)),
        tuple(sorted((int(sprite.x), int(sprite.y), str(sprite.name)) for sprite in game.alsxlhizr)),
        tuple(
            (
                int(mover._start_x),
                int(mover._start_y),
                int(mover._sprite.x),
                int(mover._sprite.y),
                int(mover._dir),
            )
            for mover in game.wsoslqeku
        ),
        tuple(
            (
                int(pusher.start_x),
                int(pusher.start_y),
                int(pusher.sprite.x),
                int(pusher.sprite.y),
                bool(pusher.is_pushing),
                int(pusher.target_x),
                int(pusher.target_y),
                int(pusher._anim_elapsed),
                int(pusher._anim_duration),
                None if pusher.aqxtoxeino is None else int(pusher.aqxtoxeino.x),
                None if pusher.aqxtoxeino is None else int(pusher.aqxtoxeino.y),
            )
            for pusher in game.hasivfwip
        ),
    )


def state_digest(game_or_key: Any) -> str:
    key = game_or_key if isinstance(game_or_key, tuple) else state_key(game_or_key)
    return sha1(repr(key).encode("utf-8")).hexdigest()


def dominance_signature(game: Any) -> tuple[Any, ...]:
    return (
        int(game._current_level_index),
        int(game._score),
        int(game.gudziatsk.x),
        int(game.gudziatsk.y),
        int(game.fwckfzsyc),
        int(game.hiaauhahz),
        int(game.cklxociuu),
        tuple(bool(value) for value in game.lvrnuajbl),
        tuple(sorted((int(sprite.x), int(sprite.y), str(sprite.name)) for sprite in game.ofoahudlo)),
        tuple(sorted((int(sprite.x), int(sprite.y), str(sprite.name)) for sprite in game.byotxmvkt)),
        tuple(sorted((int(sprite.x), int(sprite.y), str(sprite.name)) for sprite in game.alsxlhizr)),
        tuple(
            (
                int(mover._start_x),
                int(mover._start_y),
                int(mover._sprite.x),
                int(mover._sprite.y),
                int(mover._dir),
            )
            for mover in game.wsoslqeku
        ),
    )


def summarize_game(game: Any) -> dict[str, Any]:
    remaining_goals = []
    for index, goal in enumerate(game.plrpelhym):
        if game.lvrnuajbl[index]:
            continue
        remaining_goals.append(
            {
                "index": index,
                "position": [int(goal.x), int(goal.y)],
                "required_shape_index": int(game.ldxlnycps[index]),
                "required_color_index": int(game.yjdexjsoa[index]),
                "required_rotation_index": int(game.ehwheiwsk[index]),
            }
        )

    refills = sorted((int(sprite.x), int(sprite.y)) for sprite in game.current_level.get_sprites_by_tag("npxgalaybz"))
    movers = [
        {
            "region_start": [int(mover._start_x), int(mover._start_y)],
            "position": [int(mover._sprite.x), int(mover._sprite.y)],
            "dir": int(mover._dir),
        }
        for mover in game.wsoslqeku
    ]

    return {
        "level_index": int(game._current_level_index),
        "score": int(game._score),
        "player_position": [int(game.gudziatsk.x), int(game.gudziatsk.y)],
        "player_shape_index": int(game.fwckfzsyc),
        "player_color_index": int(game.hiaauhahz),
        "player_rotation_index": int(game.cklxociuu),
        "steps_left": int(game._step_counter_ui.current_steps),
        "lives_left": int(game.aqygnziho),
        "remaining_goals": remaining_goals,
        "remaining_refills": refills,
        "moving_transformers": movers,
        "board_ascii": _render_board_ascii(game),
    }


def solve_current_level(
    game: Any,
    *,
    time_limit_s: float,
    expansion_limit: int,
) -> LevelPlan:
    if _can_use_simple_planner(game):
        return _solve_simple_level(
            game,
            time_limit_s=max(time_limit_s, 120.0),
            expansion_limit=max(expansion_limit, 2_000_000),
        )

    level_index = int(game._current_level_index)
    start_score = int(game._score)
    start_key = state_key(game)
    best_cost = {start_key: 0}
    parents: dict[tuple[Any, ...], tuple[tuple[Any, ...], str] | None] = {start_key: None}
    pareto_resources: dict[tuple[Any, ...], list[tuple[int, int, int]]] = {
        dominance_signature(game): [(int(game._step_counter_ui.current_steps), int(game.aqygnziho), 0)]
    }
    frontier: list[tuple[int, int, int, Any, tuple[Any, ...]]] = []
    tie_breaker = count()
    heappush(frontier, (_heuristic(game), 0, next(tie_breaker), clone_game(game), start_key))

    started_at = perf_counter()
    expansions = 0

    while frontier:
        if perf_counter() - started_at > time_limit_s:
            raise OfflinePlanningError(
                f"Offline planner exceeded time limit on level {level_index}: {time_limit_s:.1f}s"
            )

        _, cost_so_far, _, current_game, current_key = heappop(frontier)
        if cost_so_far != best_cost.get(current_key):
            continue

        if _is_goal_state(current_game, level_index, start_score):
            actions = _reconstruct_actions(parents, current_key)
            return LevelPlan(
                level_index=level_index,
                actions=actions,
                expansions=expansions,
                elapsed_s=perf_counter() - started_at,
                remaining_goals=sum(1 for value in current_game.lvrnuajbl if not value),
                steps_left=int(current_game._step_counter_ui.current_steps),
                lives_left=int(current_game.aqygnziho),
            )

        expansions += 1
        if expansions > expansion_limit:
            raise OfflinePlanningError(
                f"Offline planner exceeded expansion limit on level {level_index}: {expansion_limit}"
            )

        for action_name in ACTION_ORDER:
            next_game, frame_state = _apply_action(current_game, action_name)
            if frame_state == "GAME_OVER":
                continue

            next_key = state_key(next_game)
            next_cost = cost_so_far + 1
            if next_cost >= best_cost.get(next_key, 1 << 60):
                continue
            next_signature = dominance_signature(next_game)
            next_steps = int(next_game._step_counter_ui.current_steps)
            next_lives = int(next_game.aqygnziho)
            resource_frontier = pareto_resources.get(next_signature, [])
            if _is_dominated(resource_frontier, next_steps, next_lives, next_cost):
                continue

            best_cost[next_key] = next_cost
            parents[next_key] = (current_key, action_name)
            pareto_resources[next_signature] = _add_pareto_resource(
                resource_frontier,
                next_steps,
                next_lives,
                next_cost,
            )

            priority = next_cost + _heuristic(next_game)
            heappush(frontier, (priority, next_cost, next(tie_breaker), next_game, next_key))

    raise OfflinePlanningError(f"Offline planner could not find a solution for level {level_index}")


def build_suffix_plan_cache(game: Any, actions: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    cache: dict[str, tuple[str, ...]] = {}
    current_game = clone_game(game)
    cache[state_digest(current_game)] = actions
    for index, action_name in enumerate(actions, start=1):
        current_game, _ = _apply_action(current_game, action_name)
        cache[state_digest(current_game)] = actions[index:]
    return cache


def _apply_action(game: Any, action_name: str) -> tuple[Any, str]:
    next_game = clone_game(game)
    frame = next_game.perform_action(ActionInput(id=ACTION_NAME_TO_ENUM[action_name]), raw=True)
    frame_state = getattr(frame.state, "name", str(frame.state))
    return next_game, frame_state


def clone_game(game: Any) -> Any:
    memo = {
        id(game._clean_levels): game._clean_levels,
        id(game.ijessuuig): game.ijessuuig,
        id(game.tnkekoeuk): game.tnkekoeuk,
        id(game.dhksvilbb): game.dhksvilbb,
    }
    return deepcopy(game, memo)


def _advanced_to_next_level(current_game: Any, next_game: Any, level_index: int, start_score: int) -> bool:
    return (
        int(next_game._current_level_index) > level_index
        or int(next_game._score) > start_score
        or int(next_game._score) > int(current_game._score)
    )


def _is_goal_state(game: Any, level_index: int, start_score: int) -> bool:
    state_name = getattr(game._state, "name", str(game._state))
    return state_name == "WIN" or int(game._current_level_index) > level_index or int(game._score) > start_score


def _reconstruct_actions(
    parents: dict[tuple[Any, ...], tuple[tuple[Any, ...], str] | None],
    goal_key: tuple[Any, ...],
) -> tuple[str, ...]:
    actions: list[str] = []
    current_key = goal_key
    while True:
        parent_info = parents[current_key]
        if parent_info is None:
            break
        parent_key, action_name = parent_info
        actions.append(action_name)
        current_key = parent_key
    actions.reverse()
    return tuple(actions)


def _heuristic(game: Any) -> int:
    remaining_indices = [index for index, value in enumerate(game.lvrnuajbl) if not value]
    if not remaining_indices:
        return 0

    player_x = int(game.gudziatsk.x)
    player_y = int(game.gudziatsk.y)
    cell_width = max(1, int(game.gisrhqpee))
    cell_height = max(1, int(game.tbwnoxqgc))
    remaining_goal_bonus = max(0, len(remaining_indices) - 1)

    best = 1 << 30
    for index in remaining_indices:
        goal = game.plrpelhym[index]
        grid_distance = (
            abs(player_x - int(goal.x)) // cell_width
            + abs(player_y - int(goal.y)) // cell_height
        )
        shape_steps = _forward_cycle_distance(
            int(game.fwckfzsyc),
            int(game.ldxlnycps[index]),
            len(game.ijessuuig),
        )
        color_steps = _forward_cycle_distance(
            int(game.hiaauhahz),
            int(game.yjdexjsoa[index]),
            len(game.tnkekoeuk),
        )
        rotation_steps = _forward_cycle_distance(
            int(game.cklxociuu),
            int(game.ehwheiwsk[index]),
            len(game.dhksvilbb),
        )
        transform_steps = shape_steps + color_steps + rotation_steps
        changer_distance = _first_required_changer_distance(game, shape_steps, color_steps, rotation_steps)
        best = min(best, grid_distance + transform_steps + changer_distance)

    return best + remaining_goal_bonus


def _forward_cycle_distance(current: int, target: int, cycle_size: int) -> int:
    return (target - current) % cycle_size


def _render_board_ascii(game: Any) -> str:
    cell_width = max(1, int(game.gisrhqpee))
    cell_height = max(1, int(game.tbwnoxqgc))
    xs: list[int] = []
    ys: list[int] = []
    for sprite in game.current_level._sprites:
        if hasattr(sprite, "x") and hasattr(sprite, "y"):
            xs.append(int(sprite.x))
            ys.append(int(sprite.y))
    xs.append(int(game.gudziatsk.x))
    ys.append(int(game.gudziatsk.y))
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    x_values = list(range(min_x, max_x + cell_width, cell_width))
    y_values = list(range(min_y, max_y + cell_height, cell_height))
    board = [["." for _ in x_values] for _ in y_values]
    x_index = {value: idx for idx, value in enumerate(x_values)}
    y_index = {value: idx for idx, value in enumerate(y_values)}

    def place(x: int, y: int, char: str) -> None:
        if x not in x_index or y not in y_index:
            return
        board[y_index[y]][x_index[x]] = char

    for sprite in game.current_level.get_sprites_by_tag("ihdgageizm"):
        place(int(sprite.x), int(sprite.y), "#")
    for sprite in game.current_level.get_sprites_by_tag("npxgalaybz"):
        place(int(sprite.x), int(sprite.y), "B")
    for sprite in game.current_level.get_sprites_by_tag("ttfwljgohq"):
        place(int(sprite.x), int(sprite.y), "T")
    for sprite in game.current_level.get_sprites_by_tag("soyhouuebz"):
        place(int(sprite.x), int(sprite.y), "C")
    for sprite in game.current_level.get_sprites_by_tag("rhsxkxzdjz"):
        place(int(sprite.x), int(sprite.y), "R")

    for index, goal in enumerate(game.plrpelhym):
        if game.lvrnuajbl[index]:
            continue
        place(int(goal.x), int(goal.y), "G")

    for mover in game.wsoslqeku:
        char = "M"
        tags = set(getattr(mover._sprite, "tags", []) or [])
        if "ttfwljgohq" in tags:
            char = "t"
        elif "soyhouuebz" in tags:
            char = "c"
        elif "rhsxkxzdjz" in tags:
            char = "r"
        place(int(mover._sprite.x), int(mover._sprite.y), char)

    for pusher in game.hasivfwip:
        char = "P"
        if int(pusher.dx) == 1:
            char = ">"
        elif int(pusher.dx) == -1:
            char = "<"
        elif int(pusher.dy) == 1:
            char = "v"
        elif int(pusher.dy) == -1:
            char = "^"
        place(int(pusher.sprite.x), int(pusher.sprite.y), char)

    place(int(game.gudziatsk.x), int(game.gudziatsk.y), "@")
    return "\n".join("".join(row) for row in board)


def _first_required_changer_distance(
    game: Any,
    shape_steps: int,
    color_steps: int,
    rotation_steps: int,
) -> int:
    player_x = int(game.gudziatsk.x)
    player_y = int(game.gudziatsk.y)
    cell_width = max(1, int(game.gisrhqpee))
    cell_height = max(1, int(game.tbwnoxqgc))

    candidate_distances: list[int] = []
    if shape_steps > 0:
        candidate_distances.extend(
            (
                abs(player_x - int(sprite.x)) // cell_width
                + abs(player_y - int(sprite.y)) // cell_height
            )
            for sprite in game.current_level.get_sprites_by_tag("ttfwljgohq")
        )
    if color_steps > 0:
        candidate_distances.extend(
            (
                abs(player_x - int(sprite.x)) // cell_width
                + abs(player_y - int(sprite.y)) // cell_height
            )
            for sprite in game.current_level.get_sprites_by_tag("soyhouuebz")
        )
    if rotation_steps > 0:
        candidate_distances.extend(
            (
                abs(player_x - int(sprite.x)) // cell_width
                + abs(player_y - int(sprite.y)) // cell_height
            )
            for sprite in game.current_level.get_sprites_by_tag("rhsxkxzdjz")
        )

    if not candidate_distances:
        return 0
    return min(candidate_distances)


def _is_dominated(frontier: list[tuple[int, int, int]], steps: int, lives: int, cost: int) -> bool:
    for known_steps, known_lives, known_cost in frontier:
        if known_steps >= steps and known_lives >= lives and known_cost <= cost:
            return True
    return False


def _add_pareto_resource(
    frontier: list[tuple[int, int, int]],
    steps: int,
    lives: int,
    cost: int,
) -> list[tuple[int, int, int]]:
    kept: list[tuple[int, int, int]] = []
    for known_steps, known_lives, known_cost in frontier:
        if steps >= known_steps and lives >= known_lives and cost <= known_cost:
            continue
        kept.append((known_steps, known_lives, known_cost))
    kept.append((steps, lives, cost))
    return kept


def _can_use_simple_planner(game: Any) -> bool:
    return not game.wsoslqeku


def _solve_simple_level(
    game: Any,
    *,
    time_limit_s: float,
    expansion_limit: int,
) -> LevelPlan:
    spec = _build_simple_level_spec(game)
    initial_state = (
        spec.start_position[0],
        spec.start_position[1],
        spec.start_shape_index,
        spec.start_color_index,
        spec.start_rotation_index,
        0,
        0,
        spec.step_max,
        int(game.aqygnziho),
    )
    best_cost = {initial_state: 0}
    parents: dict[tuple[int, ...], tuple[tuple[int, ...], str] | None] = {initial_state: None}
    frontier: list[tuple[int, int, int, tuple[int, ...]]] = []
    tie_breaker = count()
    heappush(frontier, (_simple_heuristic(initial_state, spec), 0, next(tie_breaker), initial_state))

    started_at = perf_counter()
    expansions = 0

    while frontier:
        if perf_counter() - started_at > time_limit_s:
            raise OfflinePlanningError(
                f"Offline planner exceeded time limit on level {spec.level_index}: {time_limit_s:.1f}s"
            )

        _, cost_so_far, _, current_state = heappop(frontier)
        if cost_so_far != best_cost.get(current_state):
            continue

        if _simple_is_goal_state(current_state, spec):
            return LevelPlan(
                level_index=spec.level_index,
                actions=_reconstruct_simple_actions(parents, current_state),
                expansions=expansions,
                elapsed_s=perf_counter() - started_at,
                remaining_goals=_simple_remaining_goal_count(current_state, spec),
                steps_left=current_state[7],
                lives_left=current_state[8],
            )

        expansions += 1
        if expansions > expansion_limit:
            raise OfflinePlanningError(
                f"Offline planner exceeded expansion limit on level {spec.level_index}: {expansion_limit}"
            )

        for action_name in ACTION_ORDER:
            next_state = _simple_apply_action(current_state, action_name, spec)
            if next_state is None:
                continue
            next_cost = cost_so_far + 1
            if next_cost >= best_cost.get(next_state, 1 << 60):
                continue
            best_cost[next_state] = next_cost
            parents[next_state] = (current_state, action_name)
            priority = next_cost + _simple_heuristic(next_state, spec)
            heappush(frontier, (priority, next_cost, next(tie_breaker), next_state))

    raise OfflinePlanningError(f"Offline planner could not find a solution for level {spec.level_index}")


def _build_simple_level_spec(game: Any) -> SimpleLevelSpec:
    goals = tuple(
        SimpleGoal(
            position=(int(goal.x), int(goal.y)),
            shape_index=int(game.ldxlnycps[index]),
            color_index=int(game.yjdexjsoa[index]),
            rotation_index=int(game.ehwheiwsk[index]),
        )
        for index, goal in enumerate(game.plrpelhym)
    )
    refills = tuple(sorted((int(sprite.x), int(sprite.y)) for sprite in game.current_level.get_sprites_by_tag("npxgalaybz")))
    goal_index_by_position = tuple((goal.position, index) for index, goal in enumerate(goals))
    refill_index_by_position = tuple((position, index) for index, position in enumerate(refills))
    collision_items: list[tuple[int, int, str, int | None]] = []
    for sprite in game.current_level._sprites:
        tags = set(sprite.tags or [])
        if "ihdgageizm" in tags:
            collision_items.append((int(sprite.x), int(sprite.y), "wall", None))
            continue
        if "rjlbuycveu" in tags:
            collision_items.append(
                (
                    int(sprite.x),
                    int(sprite.y),
                    "goal",
                    _lookup_position(goal_index_by_position, (int(sprite.x), int(sprite.y))),
                )
            )
            continue
        if "npxgalaybz" in tags:
            collision_items.append(
                (
                    int(sprite.x),
                    int(sprite.y),
                    "refill",
                    _lookup_position(refill_index_by_position, (int(sprite.x), int(sprite.y))),
                )
            )
            continue
        if "ttfwljgohq" in tags:
            collision_items.append((int(sprite.x), int(sprite.y), "shape", None))
            continue
        if "soyhouuebz" in tags:
            collision_items.append((int(sprite.x), int(sprite.y), "color", None))
            continue
        if "rhsxkxzdjz" in tags:
            collision_items.append((int(sprite.x), int(sprite.y), "rotation", None))
    return SimpleLevelSpec(
        level_index=int(game._current_level_index),
        start_position=(int(game.ltwrkifkx), int(game.zyoimjaei)),
        start_shape_index=int(game.current_level.get_data("StartShape")),
        start_color_index=int(game.tnkekoeuk.index(game.current_level.get_data("StartColor"))),
        start_rotation_index=int(game.dhksvilbb.index(game.current_level.get_data("StartRotation"))),
        step_max=int(game._step_counter_ui.osgviligwp),
        step_decrement=int(game._step_counter_ui.efipnixsvl),
        cell_width=int(game.gisrhqpee),
        cell_height=int(game.tbwnoxqgc),
        shape_cycle=len(game.ijessuuig),
        color_cycle=len(game.tnkekoeuk),
        rotation_cycle=len(game.dhksvilbb),
        goals=goals,
        pushers=tuple(
            (
                int(pusher.sprite.x),
                int(pusher.sprite.y),
                int(pusher.width),
                int(pusher.height),
                int(pusher.dx * pusher.width * pusher.ullzqnksoj(game.gudziatsk)),
                int(pusher.dy * pusher.height * pusher.ullzqnksoj(game.gudziatsk)),
            )
            for pusher in game.hasivfwip
        ),
        all_goals_mask=(1 << len(goals)) - 1,
        goal_index_by_position=goal_index_by_position,
        refill_index_by_position=refill_index_by_position,
        collision_items=tuple(collision_items),
        walls=frozenset((int(sprite.x), int(sprite.y)) for sprite in game.current_level.get_sprites_by_tag("ihdgageizm")),
        shape_changers=frozenset((int(sprite.x), int(sprite.y)) for sprite in game.current_level.get_sprites_by_tag("ttfwljgohq")),
        color_changers=frozenset((int(sprite.x), int(sprite.y)) for sprite in game.current_level.get_sprites_by_tag("soyhouuebz")),
        rotation_changers=frozenset((int(sprite.x), int(sprite.y)) for sprite in game.current_level.get_sprites_by_tag("rhsxkxzdjz")),
    )


def _simple_apply_action(
    state: tuple[int, ...],
    action_name: str,
    spec: SimpleLevelSpec,
) -> tuple[int, ...] | None:
    x, y, shape, color, rotation, goals_mask, refill_mask, steps_left, lives_left = state
    dx, dy = _delta_for_action(action_name, spec)
    target = (x + dx, y + dy)

    goal_index: int | None = None
    consumed_refill = False

    for item_x, item_y, item_kind, item_index in spec.collision_items:
        if not _collides_with_target(item_x, item_y, target, spec):
            continue
        if item_kind == "wall":
            return _simple_decrement_or_reset(state, spec)
        if item_kind == "goal":
            goal_index = item_index
            if goal_index is not None and not _bit_is_set(goals_mask, goal_index):
                goal = spec.goals[goal_index]
                if (shape, color, rotation) != (
                    goal.shape_index,
                    goal.color_index,
                    goal.rotation_index,
                ):
                    return state
        elif item_kind == "refill":
            if item_index is not None and not _bit_is_set(refill_mask, item_index):
                refill_mask |= 1 << item_index
                steps_left = spec.step_max
                consumed_refill = True
        elif item_kind == "shape":
            shape = (shape + 1) % spec.shape_cycle
        elif item_kind == "color":
            color = (color + 1) % spec.color_cycle
        elif item_kind == "rotation":
            rotation = (rotation + 1) % spec.rotation_cycle

    x, y = target
    next_state = (x, y, shape, color, rotation, goals_mask, refill_mask, steps_left, lives_left)
    if not consumed_refill:
        next_state = _simple_decrement_or_reset(next_state, spec)
        if next_state is None:
            return None
        x, y, shape, color, rotation, goals_mask, refill_mask, steps_left, lives_left = next_state
    else:
        x, y, shape, color, rotation, goals_mask, refill_mask, steps_left, lives_left = next_state

    for pusher_x, pusher_y, pusher_width, pusher_height, shift_x, shift_y in spec.pushers:
        if not _rects_overlap(x, y, spec.cell_width, spec.cell_height, pusher_x, pusher_y, pusher_width, pusher_height):
            continue
        if shift_x == 0 and shift_y == 0:
            continue
        x, y = x + shift_x, y + shift_y
        for item_x, item_y, item_kind, item_index in spec.collision_items:
            if not _collides_with_target(item_x, item_y, (x, y), spec):
                continue
            if item_kind == "refill":
                if item_index is not None and not _bit_is_set(refill_mask, item_index):
                    refill_mask |= 1 << item_index
                    steps_left = spec.step_max
            elif item_kind == "shape":
                shape = (shape + 1) % spec.shape_cycle
            elif item_kind == "color":
                color = (color + 1) % spec.color_cycle
            elif item_kind == "rotation":
                rotation = (rotation + 1) % spec.rotation_cycle
        return (x, y, shape, color, rotation, goals_mask, refill_mask, steps_left, lives_left)

    goal_index = _lookup_position(spec.goal_index_by_position, (x, y))
    if goal_index is not None and not _bit_is_set(goals_mask, goal_index):
        goal = spec.goals[goal_index]
        if (shape, color, rotation) == (
            goal.shape_index,
            goal.color_index,
            goal.rotation_index,
        ):
            goals_mask |= 1 << goal_index
            return (x, y, shape, color, rotation, goals_mask, refill_mask, steps_left, lives_left)
    return (x, y, shape, color, rotation, goals_mask, refill_mask, steps_left, lives_left)


def _simple_decrement_or_reset(
    state: tuple[int, ...],
    spec: SimpleLevelSpec,
) -> tuple[int, ...] | None:
    x, y, shape, color, rotation, goals_mask, refill_mask, steps_left, lives_left = state
    steps_left -= spec.step_decrement
    if steps_left >= 0:
        return (x, y, shape, color, rotation, goals_mask, refill_mask, steps_left, lives_left)

    lives_left -= 1
    if lives_left <= 0:
        return None
    return (
        spec.start_position[0],
        spec.start_position[1],
        spec.start_shape_index,
        spec.start_color_index,
        spec.start_rotation_index,
        0,
        0,
        spec.step_max,
        lives_left,
    )


def _simple_heuristic(state: tuple[int, ...], spec: SimpleLevelSpec) -> int:
    x, y, shape, color, rotation, goals_mask, _, _, _ = state
    remaining_goal_bonus = max(0, _simple_remaining_goal_count(state, spec) - 1)
    best = 1 << 30
    for index, goal in enumerate(spec.goals):
        if _bit_is_set(goals_mask, index):
            continue
        grid_distance = (
            abs(x - goal.position[0]) // spec.cell_width
            + abs(y - goal.position[1]) // spec.cell_height
        )
        shape_steps = _forward_cycle_distance(shape, goal.shape_index, spec.shape_cycle)
        color_steps = _forward_cycle_distance(color, goal.color_index, spec.color_cycle)
        rotation_steps = _forward_cycle_distance(rotation, goal.rotation_index, spec.rotation_cycle)
        changer_distance = _simple_first_required_changer_distance(
            (x, y),
            spec,
            shape_steps,
            color_steps,
            rotation_steps,
        )
        best = min(best, grid_distance + shape_steps + color_steps + rotation_steps + changer_distance)
    return best + remaining_goal_bonus


def _simple_first_required_changer_distance(
    position: tuple[int, int],
    spec: SimpleLevelSpec,
    shape_steps: int,
    color_steps: int,
    rotation_steps: int,
) -> int:
    candidate_distances: list[int] = []
    if shape_steps > 0:
        candidate_distances.extend(
            (
                abs(position[0] - changer[0]) // spec.cell_width
                + abs(position[1] - changer[1]) // spec.cell_height
            )
            for changer in spec.shape_changers
        )
    if color_steps > 0:
        candidate_distances.extend(
            (
                abs(position[0] - changer[0]) // spec.cell_width
                + abs(position[1] - changer[1]) // spec.cell_height
            )
            for changer in spec.color_changers
        )
    if rotation_steps > 0:
        candidate_distances.extend(
            (
                abs(position[0] - changer[0]) // spec.cell_width
                + abs(position[1] - changer[1]) // spec.cell_height
            )
            for changer in spec.rotation_changers
        )
    if not candidate_distances:
        return 0
    return min(candidate_distances)


def _simple_is_goal_state(state: tuple[int, ...], spec: SimpleLevelSpec) -> bool:
    return state[5] == spec.all_goals_mask


def _simple_remaining_goal_count(state: tuple[int, ...], spec: SimpleLevelSpec) -> int:
    goals_mask = state[5]
    return sum(1 for index in range(len(spec.goals)) if not _bit_is_set(goals_mask, index))


def _reconstruct_simple_actions(
    parents: dict[tuple[int, ...], tuple[tuple[int, ...], str] | None],
    goal_state: tuple[int, ...],
) -> tuple[str, ...]:
    actions: list[str] = []
    current_state = goal_state
    while True:
        parent_info = parents[current_state]
        if parent_info is None:
            break
        parent_state, action_name = parent_info
        actions.append(action_name)
        current_state = parent_state
    actions.reverse()
    return tuple(actions)


def _delta_for_action(action_name: str, spec: SimpleLevelSpec) -> tuple[int, int]:
    if action_name == "ACTION1":
        return (0, -spec.cell_height)
    if action_name == "ACTION2":
        return (0, spec.cell_height)
    if action_name == "ACTION3":
        return (-spec.cell_width, 0)
    return (spec.cell_width, 0)


def _lookup_position(items: tuple[tuple[tuple[int, int], int], ...], position: tuple[int, int]) -> int | None:
    for item_position, index in items:
        if item_position == position:
            return index
    return None


def _bit_is_set(mask: int, index: int) -> bool:
    return (mask & (1 << index)) != 0


def _collides_with_target(
    item_x: int,
    item_y: int,
    target: tuple[int, int],
    spec: SimpleLevelSpec,
) -> bool:
    return (
        item_x >= target[0]
        and item_x < target[0] + spec.cell_width
        and item_y >= target[1]
        and item_y < target[1] + spec.cell_height
    )


def _rects_overlap(
    ax: int,
    ay: int,
    aw: int,
    ah: int,
    bx: int,
    by: int,
    bw: int,
    bh: int,
) -> bool:
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah
