#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = REPO_ROOT / ".artifacts" / "arc-bench-faithful"
RESULTS_DIR = ARTIFACTS_ROOT / "results"
CHECKPOINT_DIR = ARTIFACTS_ROOT / "checkpoints"
EXPERIENCE_DB = ARTIFACTS_ROOT / "experience.db"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(EXPERIENCE_DB)
    connection.row_factory = sqlite3.Row
    return connection


def cmd_episode_summary(args: argparse.Namespace) -> None:
    with _connect() as connection:
        summary = connection.execute(
            """
            SELECT COUNT(*) AS episode_count,
                   COALESCE(MAX(final_score), 0) AS best_final_score,
                   COALESCE(SUM(CASE WHEN final_state = 'WIN' THEN 1 ELSE 0 END), 0) AS win_count
            FROM episodes
            WHERE game_id = ?
            """,
            (args.game,),
        ).fetchone()
        recent = [
            dict(row)
            for row in connection.execute(
                """
                SELECT episode_key, mode, final_score, final_state, actions_taken, recorded_at
                FROM episodes
                WHERE game_id = ?
                ORDER BY recorded_at DESC
                LIMIT ?
                """,
                (args.game, args.limit),
            )
        ]
    print(json.dumps({"summary": dict(summary), "recent": recent}, ensure_ascii=True))


def cmd_latest_results(args: argparse.Namespace) -> None:
    results: list[dict[str, object]] = []
    for path in sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[: args.limit]:
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        results.append(
            {
                "path": str(path),
                "game_id": payload.get("game_id"),
                "final_score": payload.get("final_score"),
                "final_state": payload.get("final_state"),
                "actions_taken": payload.get("actions_taken"),
                "card_id": payload.get("card_id"),
            }
        )
    print(json.dumps(results, ensure_ascii=True))


def _latest_checkpoint_dir(prefix: str) -> Path:
    candidates = sorted(CHECKPOINT_DIR.glob(f"{prefix}*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No checkpoint found for prefix={prefix!r}")
    return candidates[0]


def cmd_latest_checkpoint(args: argparse.Namespace) -> None:
    prefix = args.prefix or "local-"
    checkpoint_dir = _latest_checkpoint_dir(prefix)
    path = checkpoint_dir / "action_history.json"
    payload = json.loads(path.read_text())
    tail = payload[-args.limit :]
    print(
        json.dumps(
            {
                "checkpoint_dir": str(checkpoint_dir),
                "count": len(payload),
                "tail": tail,
            },
            ensure_ascii=True,
        )
    )


def cmd_state_priors(args: argparse.Namespace) -> None:
    with _connect() as connection:
        exact = [
            dict(row)
            for row in connection.execute(
                """
                SELECT action, attempts, moved_count, blocked_count, total_score_delta,
                       total_level_delta, self_loop_count
                FROM state_action_stats
                WHERE game_id = ? AND state_digest = ?
                ORDER BY action
                """,
                (args.game, args.state_digest),
            )
        ]
        coarse = []
        if args.coarse_digest:
            coarse = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT action, attempts, moved_count, blocked_count, total_score_delta,
                           total_level_delta, self_loop_count
                    FROM coarse_state_action_stats
                    WHERE game_id = ? AND coarse_state_digest = ?
                    ORDER BY action
                    """,
                    (args.game, args.coarse_digest),
                )
            ]
    print(json.dumps({"exact": exact, "coarse": coarse}, ensure_ascii=True))


def cmd_winning_actions(args: argparse.Namespace) -> None:
    with _connect() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT t.action, COUNT(*) AS attempts
                FROM transitions t
                JOIN episodes e ON e.episode_key = t.episode_key
                WHERE t.game_id = ? AND t.state_digest = ? AND e.final_state = 'WIN'
                GROUP BY t.action
                ORDER BY attempts DESC, t.action
                """,
                (args.game, args.state_digest),
            )
        ]
    print(json.dumps(rows, ensure_ascii=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect faithful benchmark artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    episode_summary = subparsers.add_parser("episode-summary")
    episode_summary.add_argument("--game", default="ls20")
    episode_summary.add_argument("--limit", type=int, default=10)
    episode_summary.set_defaults(func=cmd_episode_summary)

    latest_results = subparsers.add_parser("latest-results")
    latest_results.add_argument("--limit", type=int, default=5)
    latest_results.set_defaults(func=cmd_latest_results)

    latest_checkpoint = subparsers.add_parser("latest-checkpoint")
    latest_checkpoint.add_argument("--prefix", default="local-")
    latest_checkpoint.add_argument("--limit", type=int, default=8)
    latest_checkpoint.set_defaults(func=cmd_latest_checkpoint)

    state_priors = subparsers.add_parser("state-priors")
    state_priors.add_argument("--game", default="ls20")
    state_priors.add_argument("--state-digest", required=True)
    state_priors.add_argument("--coarse-digest")
    state_priors.set_defaults(func=cmd_state_priors)

    winning_actions = subparsers.add_parser("winning-actions")
    winning_actions.add_argument("--game", default="ls20")
    winning_actions.add_argument("--state-digest", required=True)
    winning_actions.set_defaults(func=cmd_winning_actions)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
