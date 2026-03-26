from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

import arcagi3.arc3tester as arc3tester_module
import arcagi3.utils.task_utils as task_utils_module
from arcagi3.arc3tester import ARC3Tester
from arcagi3.schemas import ModelConfig

from arc_agi_3.agent import CodexResumeAgent
from arc_agi_3.constants import (
    CODEX_MODEL_CONFIG,
    DEFAULT_CHECKPOINT_DIR,
    DEFAULT_CONFIG,
    DEFAULT_GAME,
    DEFAULT_RESULTS_DIR,
    ENV_FILE,
)
from arc_agi_3.local_client import LocalArcGameClient

_ORIGINAL_READ_MODELS_CONFIG = task_utils_module.read_models_config

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ARC-AGI-3 benchmark harness entrypoint")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    for mode in ("offline", "online"):
        subparser = subparsers.add_parser(mode)
        subparser.add_argument("--game", default=DEFAULT_GAME)
        subparser.add_argument("--config", default=DEFAULT_CONFIG)
        subparser.add_argument("--max-actions", type=int, default=40)
        subparser.add_argument("--max-episode-actions", type=int, default=0)
        subparser.add_argument("--num-plays", type=int, default=1)
        subparser.add_argument("--checkpoint-id")
        subparser.add_argument("--save-results-dir", default=str(DEFAULT_RESULTS_DIR))
        subparser.add_argument("--checkpoint-dir", default=str(DEFAULT_CHECKPOINT_DIR))
        subparser.add_argument("--log-level", default="INFO")

    return parser


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_root_env() -> None:
    load_dotenv(ENV_FILE, override=False)


def install_model_config_override() -> None:
    def patched_read_models_config(config: str) -> ModelConfig:
        if config == DEFAULT_CONFIG:
            return ModelConfig(**CODEX_MODEL_CONFIG)
        return _ORIGINAL_READ_MODELS_CONFIG(config)

    task_utils_module.read_models_config = patched_read_models_config
    arc3tester_module.read_models_config = patched_read_models_config


def ensure_environment(mode: str) -> None:
    if mode == "online" and not os.getenv("ARC_API_KEY"):
        raise RuntimeError("ARC_API_KEY is required for online runs")


def build_tester(args: argparse.Namespace) -> ARC3Tester:
    checkpoint_dir = Path(args.checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    save_results_dir = Path(args.save_results_dir)
    save_results_dir.mkdir(parents=True, exist_ok=True)

    return ARC3Tester(
        config=args.config,
        save_results_dir=str(save_results_dir),
        max_actions=args.max_actions,
        num_plays=args.num_plays,
        max_episode_actions=args.max_episode_actions,
        submit_scorecard=args.mode == "online",
        agent_class=CodexResumeAgent,
        agent_kwargs={
            "checkpoint_dir": str(checkpoint_dir),
            "use_vision": False,
            "show_images": False,
        },
    )


def resolve_game_id(tester: ARC3Tester, game_ref: str) -> str:
    if "-" in game_ref:
        return game_ref

    candidates: list[dict[str, object]] = []
    game_ref_lower = game_ref.lower()
    for game in tester.game_client.list_games():
        game_id = str(game.get("game_id", ""))
        title = str(game.get("title", ""))
        if game_id.lower() == game_ref_lower or title.lower() == game_ref_lower:
            return game_id
        if game_id.lower().startswith(f"{game_ref_lower}-") or title.lower().startswith(game_ref_lower):
            candidates.append(game)

    if len(candidates) == 1:
        return str(candidates[0]["game_id"])
    if not candidates:
        raise RuntimeError(f"Could not resolve game reference '{game_ref}' from list_games()")
    raise RuntimeError(
        f"Game reference '{game_ref}' is ambiguous: "
        + ", ".join(str(candidate.get("game_id")) for candidate in candidates)
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)
    load_root_env()
    install_model_config_override()
    ensure_environment(args.mode)

    tester = build_tester(args)
    if args.mode == "offline":
        tester.game_client = LocalArcGameClient()
        game_id = args.game
    else:
        game_id = resolve_game_id(tester, args.game)
    result = tester.play_game(
        game_id,
        card_id=args.checkpoint_id,
        resume_from_checkpoint=bool(args.checkpoint_id),
    )

    print(
        json.dumps(
            {
                "game_id": result.game_id,
                "config": result.config,
                "final_state": result.final_state,
                "final_score": result.final_score,
                "actions_taken": result.actions_taken,
                "card_id": result.card_id,
                "scorecard_url": result.scorecard_url,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
