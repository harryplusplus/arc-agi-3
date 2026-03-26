from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from arcagi3.schemas import GameActionRecord, GameResult

from arc_benchmark_faithful.constants import EXPERIENCE_DB_PATH, SCOREMAX_RESULTS_DIR
from arc_benchmark_faithful.memory import coarse_state_digest, state_digest
from arc_benchmark_faithful.memory_store import canonical_game_id


@dataclass
class ActionExperience:
    attempts: int = 0
    moved_rate: float = 0.0
    blocked_rate: float = 0.0
    avg_score_delta: float = 0.0
    avg_level_delta: float = 0.0
    self_loop_rate: float = 0.0


@dataclass
class ExperienceSnapshot:
    game_id: str
    episode_count: int = 0
    best_final_score: int = 0
    win_count: int = 0
    state_actions: dict[str, ActionExperience] | None = None
    winning_state_actions: dict[str, ActionExperience] | None = None
    coarse_actions: dict[str, ActionExperience] | None = None
    game_actions: dict[str, ActionExperience] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "episode_count": self.episode_count,
            "best_final_score": self.best_final_score,
            "win_count": self.win_count,
            "state_actions": {
                action: vars(stats) for action, stats in (self.state_actions or {}).items()
            },
            "winning_state_actions": {
                action: vars(stats) for action, stats in (self.winning_state_actions or {}).items()
            },
            "coarse_actions": {
                action: vars(stats) for action, stats in (self.coarse_actions or {}).items()
            },
            "game_actions": {
                action: vars(stats) for action, stats in (self.game_actions or {}).items()
            },
        }


class ExperienceDB:
    def __init__(self, path: Path = EXPERIENCE_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_key TEXT PRIMARY KEY,
                    game_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    final_score INTEGER NOT NULL,
                    final_state TEXT NOT NULL,
                    actions_taken INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_key TEXT NOT NULL,
                    game_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    state_digest TEXT NOT NULL,
                    action TEXT NOT NULL,
                    next_state_digest TEXT,
                    moved INTEGER NOT NULL DEFAULT 0,
                    score_delta INTEGER NOT NULL DEFAULT 0,
                    level_delta INTEGER NOT NULL DEFAULT 0,
                    terminal INTEGER NOT NULL DEFAULT 0,
                    self_loop INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS state_action_stats (
                    game_id TEXT NOT NULL,
                    state_digest TEXT NOT NULL,
                    action TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    moved_count INTEGER NOT NULL DEFAULT 0,
                    blocked_count INTEGER NOT NULL DEFAULT 0,
                    total_score_delta INTEGER NOT NULL DEFAULT 0,
                    total_level_delta INTEGER NOT NULL DEFAULT 0,
                    terminal_count INTEGER NOT NULL DEFAULT 0,
                    self_loop_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (game_id, state_digest, action)
                );

                CREATE TABLE IF NOT EXISTS coarse_state_action_stats (
                    game_id TEXT NOT NULL,
                    coarse_state_digest TEXT NOT NULL,
                    action TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    moved_count INTEGER NOT NULL DEFAULT 0,
                    blocked_count INTEGER NOT NULL DEFAULT 0,
                    total_score_delta INTEGER NOT NULL DEFAULT 0,
                    total_level_delta INTEGER NOT NULL DEFAULT 0,
                    terminal_count INTEGER NOT NULL DEFAULT 0,
                    self_loop_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (game_id, coarse_state_digest, action)
                );

                CREATE TABLE IF NOT EXISTS game_action_stats (
                    game_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    moved_count INTEGER NOT NULL DEFAULT 0,
                    blocked_count INTEGER NOT NULL DEFAULT 0,
                    total_score_delta INTEGER NOT NULL DEFAULT 0,
                    total_level_delta INTEGER NOT NULL DEFAULT 0,
                    terminal_count INTEGER NOT NULL DEFAULT 0,
                    self_loop_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (game_id, action)
                );
                """
            )

    def summarize(
        self,
        game_id: str,
        state_digest_value: str,
        coarse_state_digest_value: str,
        available_actions: list[str],
    ) -> ExperienceSnapshot:
        canonical = canonical_game_id(game_id)
        with self._connect() as connection:
            episode_row = connection.execute(
                """
                SELECT COUNT(*) AS episode_count,
                       COALESCE(MAX(final_score), 0) AS best_final_score,
                       COALESCE(SUM(CASE WHEN final_state = 'WIN' THEN 1 ELSE 0 END), 0) AS win_count
                FROM episodes
                WHERE game_id = ?
                """,
                (canonical,),
            ).fetchone()

            state_rows = connection.execute(
                """
                SELECT action, attempts, moved_count, blocked_count,
                       total_score_delta, total_level_delta, terminal_count, self_loop_count
                FROM state_action_stats
                WHERE game_id = ? AND state_digest = ?
                """,
                (canonical, state_digest_value),
            ).fetchall()

            coarse_rows = connection.execute(
                """
                SELECT action, attempts, moved_count, blocked_count,
                       total_score_delta, total_level_delta, terminal_count, self_loop_count
                FROM coarse_state_action_stats
                WHERE game_id = ? AND coarse_state_digest = ?
                """,
                (canonical, coarse_state_digest_value),
            ).fetchall()

            winning_state_rows = connection.execute(
                """
                SELECT t.action,
                       COUNT(*) AS attempts,
                       COALESCE(SUM(t.moved), 0) AS moved_count,
                       COALESCE(SUM(CASE WHEN t.moved = 0 THEN 1 ELSE 0 END), 0) AS blocked_count,
                       COALESCE(SUM(t.score_delta), 0) AS total_score_delta,
                       COALESCE(SUM(t.level_delta), 0) AS total_level_delta,
                       COALESCE(SUM(t.terminal), 0) AS terminal_count,
                       COALESCE(SUM(t.self_loop), 0) AS self_loop_count
                FROM transitions t
                JOIN episodes e ON e.episode_key = t.episode_key
                WHERE t.game_id = ? AND t.state_digest = ? AND e.final_state = 'WIN'
                GROUP BY t.action
                """,
                (canonical, state_digest_value),
            ).fetchall()

            game_rows = connection.execute(
                """
                SELECT action, attempts, moved_count, blocked_count,
                       total_score_delta, total_level_delta, terminal_count, self_loop_count
                FROM game_action_stats
                WHERE game_id = ?
                """,
                (canonical,),
            ).fetchall()

        snapshot = ExperienceSnapshot(
            game_id=canonical,
            episode_count=int(episode_row["episode_count"] or 0),
            best_final_score=int(episode_row["best_final_score"] or 0),
            win_count=int(episode_row["win_count"] or 0),
            state_actions={},
            winning_state_actions={},
            coarse_actions={},
            game_actions={},
        )

        for row in state_rows:
            snapshot.state_actions[str(row["action"])] = self._row_to_action_experience(row)
        for row in winning_state_rows:
            snapshot.winning_state_actions[str(row["action"])] = self._row_to_action_experience(row)
        for row in coarse_rows:
            snapshot.coarse_actions[str(row["action"])] = self._row_to_action_experience(row)
        for row in game_rows:
            snapshot.game_actions[str(row["action"])] = self._row_to_action_experience(row)

        for action in available_actions:
            snapshot.state_actions.setdefault(action, ActionExperience())
            snapshot.winning_state_actions.setdefault(action, ActionExperience())
            snapshot.coarse_actions.setdefault(action, ActionExperience())
            snapshot.game_actions.setdefault(action, ActionExperience())
        return snapshot

    def record_game_result(self, result: GameResult, mode: str) -> None:
        canonical = canonical_game_id(result.game_id)
        episode_key = str(result.card_id or f"{canonical}:{result.timestamp.isoformat()}")
        actions = list(result.actions)

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT 1 FROM episodes WHERE episode_key = ?",
                (episode_key,),
            ).fetchone()
            if existing is not None:
                return
            connection.execute(
                """
                INSERT OR REPLACE INTO episodes (
                    episode_key, game_id, mode, final_score, final_state, actions_taken
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    episode_key,
                    canonical,
                    mode,
                    int(result.final_score),
                    str(result.final_state),
                    int(result.actions_taken),
                ),
            )
            connection.execute("DELETE FROM transitions WHERE episode_key = ?", (episode_key,))

            previous_score = 0
            for index, action_record in enumerate(actions, start=1):
                transition = self._transition_from_record(actions, index - 1, previous_score)
                previous_score = int(action_record.result_score)
                if transition is None:
                    continue

                connection.execute(
                    """
                    INSERT INTO transitions (
                        episode_key, game_id, step_index, state_digest, action, next_state_digest,
                        moved, score_delta, level_delta, terminal, self_loop
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_key,
                        canonical,
                        index,
                        transition["state_digest"],
                        transition["action"],
                        transition["next_state_digest"],
                        transition["moved"],
                        transition["score_delta"],
                        transition["level_delta"],
                        transition["terminal"],
                        transition["self_loop"],
                    ),
                )

                self._upsert_state_action_stats(
                    connection,
                    table="state_action_stats",
                    key_values=(canonical, transition["state_digest"], transition["action"]),
                    transition=transition,
                )
                self._upsert_state_action_stats(
                    connection,
                    table="coarse_state_action_stats",
                    key_values=(canonical, transition["coarse_state_digest"], transition["action"]),
                    transition=transition,
                )
                self._upsert_state_action_stats(
                    connection,
                    table="game_action_stats",
                    key_values=(canonical, transition["action"]),
                    transition=transition,
                )

    def bootstrap_reference_results(
        self,
        game_id: str,
        *,
        results_dir: Path = SCOREMAX_RESULTS_DIR,
    ) -> int:
        canonical = canonical_game_id(game_id)
        imported = 0
        if not results_dir.exists():
            return imported
        for path in sorted(results_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text())
                result = GameResult(**payload)
            except Exception:
                continue
            if canonical_game_id(result.game_id) != canonical:
                continue
            if str(result.final_state) != "WIN":
                continue
            if self._episode_exists(result):
                continue
            self.record_game_result(result, mode="bootstrap")
            imported += 1
        return imported

    def _episode_exists(self, result: GameResult) -> bool:
        canonical = canonical_game_id(result.game_id)
        episode_key = str(result.card_id or f"{canonical}:{result.timestamp.isoformat()}")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM episodes WHERE episode_key = ?",
                (episode_key,),
            ).fetchone()
        return row is not None

    def _upsert_state_action_stats(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        key_values: tuple[Any, ...],
        transition: dict[str, Any],
    ) -> None:
        if table == "state_action_stats":
            connection.execute(
                """
                INSERT INTO state_action_stats (
                    game_id, state_digest, action, attempts, moved_count, blocked_count,
                    total_score_delta, total_level_delta, terminal_count, self_loop_count
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id, state_digest, action) DO UPDATE SET
                    attempts = attempts + 1,
                    moved_count = moved_count + excluded.moved_count,
                    blocked_count = blocked_count + excluded.blocked_count,
                    total_score_delta = total_score_delta + excluded.total_score_delta,
                    total_level_delta = total_level_delta + excluded.total_level_delta,
                    terminal_count = terminal_count + excluded.terminal_count,
                    self_loop_count = self_loop_count + excluded.self_loop_count
                """,
                (
                    *key_values,
                    transition["moved"],
                    1 - transition["moved"],
                    transition["score_delta"],
                    transition["level_delta"],
                    transition["terminal"],
                    transition["self_loop"],
                ),
            )
            return

        if table == "coarse_state_action_stats":
            connection.execute(
                """
                INSERT INTO coarse_state_action_stats (
                    game_id, coarse_state_digest, action, attempts, moved_count, blocked_count,
                    total_score_delta, total_level_delta, terminal_count, self_loop_count
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id, coarse_state_digest, action) DO UPDATE SET
                    attempts = attempts + 1,
                    moved_count = moved_count + excluded.moved_count,
                    blocked_count = blocked_count + excluded.blocked_count,
                    total_score_delta = total_score_delta + excluded.total_score_delta,
                    total_level_delta = total_level_delta + excluded.total_level_delta,
                    terminal_count = terminal_count + excluded.terminal_count,
                    self_loop_count = self_loop_count + excluded.self_loop_count
                """,
                (
                    *key_values,
                    transition["moved"],
                    1 - transition["moved"],
                    transition["score_delta"],
                    transition["level_delta"],
                    transition["terminal"],
                    transition["self_loop"],
                ),
            )
            return

        connection.execute(
            """
            INSERT INTO game_action_stats (
                game_id, action, attempts, moved_count, blocked_count,
                total_score_delta, total_level_delta, terminal_count, self_loop_count
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id, action) DO UPDATE SET
                attempts = attempts + 1,
                moved_count = moved_count + excluded.moved_count,
                blocked_count = blocked_count + excluded.blocked_count,
                total_score_delta = total_score_delta + excluded.total_score_delta,
                total_level_delta = total_level_delta + excluded.total_level_delta,
                terminal_count = terminal_count + excluded.terminal_count,
                self_loop_count = self_loop_count + excluded.self_loop_count
            """,
            (
                *key_values,
                transition["moved"],
                1 - transition["moved"],
                transition["score_delta"],
                transition["level_delta"],
                transition["terminal"],
                transition["self_loop"],
            ),
        )

    def _transition_from_record(
        self,
        actions: list[GameActionRecord],
        index: int,
        previous_score: int,
    ) -> dict[str, Any] | None:
        record = actions[index]
        reasoning = record.reasoning or {}
        observable_state = reasoning.get("observable_state")
        if not isinstance(observable_state, dict):
            return None

        state_digest_value = state_digest(SimpleNamespace(**observable_state))
        coarse_state_digest_value = coarse_state_digest(SimpleNamespace(**observable_state))
        current_level_index = int(observable_state.get("level_index", previous_score))
        score_delta = int(record.result_score) - int(previous_score)
        level_delta = int(record.result_score) - current_level_index

        if index + 1 < len(actions):
            next_reasoning = actions[index + 1].reasoning or {}
            next_observable_state = next_reasoning.get("observable_state")
            if isinstance(next_observable_state, dict):
                next_state_digest = state_digest(SimpleNamespace(**next_observable_state))
                moved = int(
                    int(observable_state.get("player_x", 0)) != int(next_observable_state.get("player_x", 0))
                    or int(observable_state.get("player_y", 0)) != int(next_observable_state.get("player_y", 0))
                )
            else:
                next_state_digest = None
                moved = 1 if score_delta > 0 or level_delta > 0 else 0
        else:
            next_state_digest = f"terminal:{record.result_state}:{record.result_score}"
            moved = 1 if score_delta > 0 or level_delta > 0 else 0

        return {
            "state_digest": state_digest_value,
            "coarse_state_digest": coarse_state_digest_value,
            "action": str(record.action),
            "next_state_digest": next_state_digest,
            "moved": moved,
            "score_delta": score_delta,
            "level_delta": level_delta,
            "terminal": int(str(record.result_state) in {"WIN", "GAME_OVER"}),
            "self_loop": int(next_state_digest == state_digest_value),
        }

    def _row_to_action_experience(self, row: sqlite3.Row) -> ActionExperience:
        attempts = int(row["attempts"] or 0)
        if attempts <= 0:
            return ActionExperience()
        moved_count = int(row["moved_count"] or 0)
        blocked_count = int(row["blocked_count"] or 0)
        return ActionExperience(
            attempts=attempts,
            moved_rate=moved_count / attempts,
            blocked_rate=blocked_count / attempts,
            avg_score_delta=float(row["total_score_delta"] or 0) / attempts,
            avg_level_delta=float(row["total_level_delta"] or 0) / attempts,
            self_loop_rate=float(row["self_loop_count"] or 0) / attempts,
        )
