from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv

import arcagi3.arc3tester as arc3tester_module
import arcagi3.utils.task_utils as task_utils_module
from arcagi3.arc3tester import ARC3Tester
from arcagi3.schemas import ModelConfig

from arc_benchmark_faithful.agent import FaithfulCodexAgent
from arc_benchmark_faithful.constants import (
    CHECKPOINT_DIR,
    CODEX_MODEL_CONFIG,
    CODEX_REASONING_EFFORT,
    DEFAULT_CONFIG,
    DEFAULT_GAME,
    ENV_FILE,
    REPO_ROOT,
    RESULTS_DIR,
    SCORECARD_AUTH,
    SCORECARD_BACKEND,
    SCORECARD_HARNESS,
    SCORECARD_SESSION_MODE,
)
from arc_benchmark_faithful.local_client import LocalArcGameClient
from arc_benchmark_faithful.scorecard_client import MetadataGameClient
from arc_benchmark_faithful.session import ensure_codex_session

_ORIGINAL_READ_MODELS_CONFIG = task_utils_module.read_models_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Memory-driven ARC-AGI-3 benchmark entrypoint")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    for mode in ("offline", "online"):
        subparser = subparsers.add_parser(mode)
        subparser.add_argument("--game", default=DEFAULT_GAME)
        subparser.add_argument("--config", default=DEFAULT_CONFIG)
        subparser.add_argument("--max-actions", type=int, default=60)
        subparser.add_argument("--max-episode-actions", type=int, default=0)
        subparser.add_argument("--num-plays", type=int, default=1)
        subparser.add_argument("--checkpoint-id")
        subparser.add_argument("--save-results-dir", default=str(RESULTS_DIR))
        subparser.add_argument("--checkpoint-dir", default=str(CHECKPOINT_DIR))
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


def _git_output(*args: str) -> str | None:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def build_scorecard_source_url() -> str | None:
    remote_url = _git_output("remote", "get-url", "origin")
    commit = _git_output("rev-parse", "HEAD")
    if not remote_url or not commit:
        return None
    if remote_url.startswith("git@github.com:"):
        remote_url = "https://github.com/" + remote_url[len("git@github.com:") :]
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]
    if remote_url.startswith("https://github.com/"):
        return f"{remote_url}/tree/{commit}"
    return remote_url


def build_scorecard_metadata(config_name: str) -> tuple[list[str], str | None, dict[str, object]]:
    commit = _git_output("rev-parse", "HEAD")
    extra_tags = [
        f"config:{config_name}",
        f"harness:{SCORECARD_HARNESS}",
        f"backend:{SCORECARD_BACKEND}",
        f"auth:{SCORECARD_AUTH}",
        f"session_mode:{SCORECARD_SESSION_MODE}",
        f"reasoning_effort:{CODEX_REASONING_EFFORT}",
        "memory_mode:game_specific",
    ]
    if commit:
        extra_tags.append(f"commit:{commit[:12]}")
    opaque: dict[str, object] = {
        "config": config_name,
        "harness": SCORECARD_HARNESS,
        "backend": SCORECARD_BACKEND,
        "auth": SCORECARD_AUTH,
        "session_mode": SCORECARD_SESSION_MODE,
        "reasoning_effort": CODEX_REASONING_EFFORT,
        "memory_mode": "game_specific",
    }
    if commit:
        opaque["repo_commit"] = commit
    return extra_tags, build_scorecard_source_url(), opaque


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
        agent_class=FaithfulCodexAgent,
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
    raise RuntimeError(f"Game reference '{game_ref}' is ambiguous")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    load_root_env()
    install_model_config_override()
    ensure_environment(args.mode)

    tester = build_tester(args)
    tester.agent_kwargs["codex_session_id"] = ensure_codex_session()
    if args.mode == "offline":
        tester.game_client = LocalArcGameClient()
        game_id = args.game
    else:
        extra_tags, source_url, opaque = build_scorecard_metadata(args.config)
        tester.game_client = MetadataGameClient(
            metadata_tags=extra_tags,
            source_url=source_url,
            opaque=opaque,
        )
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
