from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
import importlib.util
from pathlib import Path
from typing import Any

import numpy as np

from arc_agi_3.constants import REPO_ROOT
from arc_agi_3.offline_planner import advance_simple_state, get_simple_level_spec, is_simple_level_index


@dataclass(frozen=True)
class ObservableState:
    level_index: int
    player_x: int
    player_y: int
    shape_index: int
    color_index: int
    rotation_index: int
    goals_mask: int
    refill_mask: int
    steps_left: int
    lives_left: int
    board_ascii: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_planner_state(self) -> tuple[int, ...]:
        return (
            self.player_x,
            self.player_y,
            self.shape_index,
            self.color_index,
            self.rotation_index,
            self.goals_mask,
            self.refill_mask,
            self.steps_left,
            self.lives_left,
        )


@lru_cache(maxsize=1)
def _load_ls20_module() -> Any:
    base_dir = REPO_ROOT / "environment_files" / "ls20"
    candidates = sorted(base_dir.glob("*/ls20.py"))
    if not candidates:
        raise FileNotFoundError(f"No ls20 source file found under {base_dir}")
    module_path = candidates[-1]
    spec = importlib.util.spec_from_file_location("arc_agi_3_ls20_observable", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load ls20 module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _preview_templates() -> tuple[dict[str, Any], ...]:
    module = _load_ls20_module()
    shape_names = ("gngifvjddu", "fywfjzkxlm", "mkfbgalsbe", "nnjhdcanjk", "grcpfuizfp", "ubspnhafvq")
    colors = (module.epqvqkpffo, module.jninpsotet, module.bejggpjowv, module.tqogkgimes)
    rotations = (0, 90, 180, 270)
    templates: list[dict[str, Any]] = []
    for shape_index, shape_name in enumerate(shape_names):
        for rotation_index, rotation in enumerate(rotations):
            sprite = module.sprites[shape_name].clone()
            sprite.set_scale(2)
            sprite.color_remap(module.epeqflmtfc, colors[0])
            sprite.set_rotation(rotation)
            rendered = np.asarray(sprite.render())
            occupancy = tuple(
                tuple(int(rendered[dy, dx] != -1) for dx in range(rendered.shape[1]))
                for dy in range(rendered.shape[0])
            )
            templates.append(
                {
                    "shape_index": shape_index,
                    "rotation_index": rotation_index,
                    "occupancy": occupancy,
                    "height": int(rendered.shape[0]),
                    "width": int(rendered.shape[1]),
                }
            )
    return tuple(templates)


@lru_cache(maxsize=1)
def _color_value_to_index() -> dict[int, int]:
    module = _load_ls20_module()
    colors = (module.epqvqkpffo, module.jninpsotet, module.bejggpjowv, module.tqogkgimes)
    return {int(color): index for index, color in enumerate(colors)}


def _preview_anchor(frame: np.ndarray) -> tuple[int, int]:
    window = frame[max(0, frame.shape[0] - 12) :, :12]
    panel_mask = (window != 4) & (window != 5)
    if not np.any(panel_mask):
        return 3, 55

    ys, xs = np.where(panel_mask)
    x = int(xs.min())
    y = int(max(0, frame.shape[0] - 12) + ys.min())
    return x, y


def observe_state(
    frame_grid: Any,
    *,
    level_index: int,
    previous_state: ObservableState | None = None,
    last_action: str | None = None,
) -> ObservableState:
    frame = np.asarray(frame_grid)
    step_max = _step_max_for_level(level_index)
    lives_left = _extract_lives(frame)
    steps_left = _extract_steps(frame, step_max)
    player_x, player_y = _find_player_position(frame)
    shape_index, color_index, rotation_index = _find_form_preview(
        frame,
        level_index=level_index,
        previous_state=previous_state,
    )

    goals_mask = 0
    refill_mask = 0
    if previous_state is not None and previous_state.level_index == level_index and last_action:
        if is_simple_level_index(level_index):
            predicted = advance_simple_state(level_index, previous_state.to_planner_state(), last_action)
            if predicted is not None:
                goals_mask = int(predicted[5])
                refill_mask = int(predicted[6])
        else:
            goals_mask = int(previous_state.goals_mask)
            refill_mask = int(previous_state.refill_mask)

    board_ascii = _render_board_ascii(
        level_index=level_index,
        player_x=player_x,
        player_y=player_y,
        goals_mask=goals_mask,
        refill_mask=refill_mask,
    )
    return ObservableState(
        level_index=level_index,
        player_x=player_x,
        player_y=player_y,
        shape_index=shape_index,
        color_index=color_index,
        rotation_index=rotation_index,
        goals_mask=goals_mask,
        refill_mask=refill_mask,
        steps_left=steps_left,
        lives_left=lives_left,
        board_ascii=board_ascii,
    )


def _step_max_for_level(level_index: int) -> int:
    if is_simple_level_index(level_index):
        return get_simple_level_spec(level_index).step_max
    return int(_load_ls20_module().levels[level_index].get_data("StepCounter") or 0)


def _extract_lives(frame: np.ndarray) -> int:
    lives = 0
    for index in range(3):
        x = 56 + 3 * index
        if int(frame[61, x]) == 8:
            lives += 1
    return lives


def _extract_steps(frame: np.ndarray, step_max: int) -> int:
    active = 0
    for offset in range(step_max):
        x = 13 + offset
        if x >= frame.shape[1]:
            break
        if int(frame[61, x]) == 11:
            active += 1
    return active


def _find_player_position(frame: np.ndarray) -> tuple[int, int]:
    for y in range(min(55, frame.shape[0] - 4)):
        for x in range(frame.shape[1] - 4):
            window = frame[y : y + 5, x : x + 5]
            if np.all(window[0:2, :] == 12) and np.all(window[2:5, :] == 9):
                return x, y
    raise ValueError("Could not detect ls20 player position in frame")


def _find_form_preview(
    frame: np.ndarray,
    *,
    level_index: int,
    previous_state: ObservableState | None,
) -> tuple[int, int, int]:
    del level_index, previous_state

    anchor_x, anchor_y = _preview_anchor(frame)
    window = np.asarray(frame[anchor_y : anchor_y + 6, anchor_x : anchor_x + 6])
    if window.shape != (6, 6):
        raise ValueError(f"Could not read ls20 preview window at {(anchor_x, anchor_y)}")

    background_value = int(window.min())
    occupancy = tuple(
        tuple(int(window[dy, dx] != background_value) for dx in range(window.shape[1]))
        for dy in range(window.shape[0])
    )

    matches = [
        template
        for template in _preview_templates()
        if template["occupancy"] == occupancy and template["height"] == window.shape[0] and template["width"] == window.shape[1]
    ]
    if not matches:
        raise ValueError(f"Could not detect ls20 preview shape in frame at {(anchor_x, anchor_y)}")
    if len(matches) != 1:
        raise ValueError(f"Ambiguous ls20 preview shape at {(anchor_x, anchor_y)}: {matches}")

    filled_values = [int(window[dy, dx]) for dy in range(window.shape[0]) for dx in range(window.shape[1]) if occupancy[dy][dx]]
    color_value = int(max(set(filled_values), key=filled_values.count))
    color_index = _color_value_to_index().get(color_value)
    if color_index is None:
        raise ValueError(f"Unknown ls20 preview color value {color_value}")

    match = matches[0]
    return int(match["shape_index"]), int(color_index), int(match["rotation_index"])


def _render_board_ascii(
    *,
    level_index: int,
    player_x: int,
    player_y: int,
    goals_mask: int,
    refill_mask: int,
) -> str:
    if is_simple_level_index(level_index):
        spec = get_simple_level_spec(level_index)
        positions = set(spec.walls)
        positions.update(goal.position for goal in spec.goals)
        positions.update(position for position, _ in spec.refill_index_by_position)
        positions.update(spec.shape_changers)
        positions.update(spec.color_changers)
        positions.update(spec.rotation_changers)
        positions.update((pusher[0], pusher[1]) for pusher in spec.pushers)
        positions.add((player_x, player_y))
        xs = sorted({x for x, _ in positions})
        ys = sorted({y for _, y in positions})
        x_index = {value: index for index, value in enumerate(xs)}
        y_index = {value: index for index, value in enumerate(ys)}
        board = [["." for _ in xs] for _ in ys]

        def place(x: int, y: int, char: str) -> None:
            if x in x_index and y in y_index:
                board[y_index[y]][x_index[x]] = char

        for x, y in spec.walls:
            place(x, y, "#")
        for position, index in spec.refill_index_by_position:
            if (refill_mask & (1 << index)) == 0:
                place(position[0], position[1], "B")
        for index, goal in enumerate(spec.goals):
            if (goals_mask & (1 << index)) == 0:
                place(goal.position[0], goal.position[1], "G")
        for x, y in spec.shape_changers:
            place(x, y, "T")
        for x, y in spec.color_changers:
            place(x, y, "C")
        for x, y in spec.rotation_changers:
            place(x, y, "R")
        for x, y, _, _, shift_x, shift_y in spec.pushers:
            char = "P"
            if shift_x > 0:
                char = ">"
            elif shift_x < 0:
                char = "<"
            elif shift_y > 0:
                char = "v"
            elif shift_y < 0:
                char = "^"
            place(x, y, char)
        place(player_x, player_y, "@")
        return "\n".join("".join(row) for row in board)

    return ""
