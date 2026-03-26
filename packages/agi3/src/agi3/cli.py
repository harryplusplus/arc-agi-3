from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv

from agi3.client import ArcRestClient
from agi3.json_output import Agi3Error, emit_error, emit_success
from agi3.paths import REPO_ROOT
from agi3.references import (
    ACTION1_URL,
    GAMES_LIST_URL,
    RESET_URL,
    REST_OVERVIEW_URL,
    SCORECARD_CLOSE_URL,
    SCORECARD_GET_URL,
    SCORECARD_OPEN_URL,
)
from agi3.session import SessionStore

MAIN_HELP = (
    "ARC-AGI-3 REST CLI.\n\n"
    "Reference URLs:\n"
    f"- REST overview: {REST_OVERVIEW_URL}\n"
    f"- Games list: {GAMES_LIST_URL}\n"
    f"- Open scorecard: {SCORECARD_OPEN_URL}\n"
    f"- Reset/start game: {RESET_URL}\n"
    f"- Action commands: {ACTION1_URL}\n"
    f"- Close scorecard: {SCORECARD_CLOSE_URL}"
)

app = typer.Typer(help=MAIN_HELP, no_args_is_help=True, add_completion=False)
games_app = typer.Typer(
    help=f"List available games.\nReference: {GAMES_LIST_URL}",
    no_args_is_help=True,
    add_completion=False,
)
scorecard_app = typer.Typer(
    help=f"Manage scorecards.\nReferences: {SCORECARD_OPEN_URL} | {SCORECARD_GET_URL} | {SCORECARD_CLOSE_URL}",
    no_args_is_help=True,
    add_completion=False,
)
session_app = typer.Typer(
    help=f"Inspect or reset local v3 session state.\nReference: {REST_OVERVIEW_URL}",
    no_args_is_help=True,
    add_completion=False,
)
game_app = typer.Typer(
    help=f"Start or reset a game instance.\nReference: {RESET_URL}",
    no_args_is_help=True,
    add_completion=False,
)
state_app = typer.Typer(
    help=f"Show the last stored game state from the active session.\nReference: {REST_OVERVIEW_URL}",
    no_args_is_help=True,
    add_completion=False,
)
action_app = typer.Typer(
    help=f"Run an ARC action against the active game session.\nReference: {ACTION1_URL}",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(games_app, name="games")
app.add_typer(scorecard_app, name="scorecard")
app.add_typer(session_app, name="session")
app.add_typer(game_app, name="game")
app.add_typer(state_app, name="state")
app.add_typer(action_app, name="action")

VALID_ACTIONS = {"ACTION1", "ACTION2", "ACTION3", "ACTION4", "ACTION5", "ACTION6", "ACTION7"}


@dataclass
class Runtime:
    client: ArcRestClient
    session_store: SessionStore


def create_runtime() -> Runtime:
    load_dotenv(REPO_ROOT / ".env", override=False)
    session_store = SessionStore()
    session_store.ensure()
    client = ArcRestClient(cookies_path=session_store.cookies_path)
    return Runtime(client=client, session_store=session_store)


def _load_reasoning(reasoning_json: str | None, reasoning_file: Path | None) -> dict[str, Any] | None:
    if reasoning_json and reasoning_file:
        raise Agi3Error(
            "reasoning은 --reasoning-json 이나 --reasoning-file 중 하나만 써.",
            error_type="invalid_reasoning_input",
        )
    if reasoning_json:
        value = json.loads(reasoning_json)
        if not isinstance(value, dict):
            raise Agi3Error("reasoning JSON은 object 여야 해.", error_type="invalid_reasoning_input")
        return value
    if reasoning_file:
        value = json.loads(reasoning_file.read_text())
        if not isinstance(value, dict):
            raise Agi3Error("reasoning 파일은 JSON object 여야 해.", error_type="invalid_reasoning_input")
        return value
    return None


def _require_card_id(session: dict[str, Any], card_id: str | None) -> str:
    resolved = card_id or session.get("card_id")
    if not resolved:
        raise Agi3Error(
            "활성 scorecard가 없어. 먼저 `agi3 scorecard open` 을 실행해.",
            error_type="missing_card_id",
        )
    return str(resolved)


def _require_guid(session: dict[str, Any]) -> str:
    guid = session.get("guid")
    if not guid:
        raise Agi3Error(
            "활성 guid가 없어. 먼저 `agi3 game start` 를 실행해.",
            error_type="missing_guid",
        )
    return str(guid)


def _require_game_id(session: dict[str, Any], game_id: str | None = None) -> str:
    resolved = game_id or session.get("game_id")
    if not resolved:
        raise Agi3Error(
            "활성 game_id가 없어. `--game-id` 를 주거나 먼저 `agi3 game start` 를 실행해.",
            error_type="missing_game_id",
        )
    return str(resolved)


@games_app.command("list", help=f"List available games.\nReference: {GAMES_LIST_URL}")
def games_list() -> None:
    command = "games.list"
    try:
        runtime = create_runtime()
        games = runtime.client.list_games()
        emit_success(command, GAMES_LIST_URL, {"games": games})
    except Agi3Error as exc:
        emit_error(command, GAMES_LIST_URL, exc)
        raise typer.Exit(1) from exc


@scorecard_app.command("open", help=f"Open a scorecard.\nReference: {SCORECARD_OPEN_URL}")
def scorecard_open(
    game_ids: list[str] = typer.Option(None, "--game-id", help="Repeatable game ID"),
    card_id: str | None = typer.Option(None, "--card-id"),
    tags: list[str] = typer.Option(None, "--tag", help="Repeatable scorecard tag"),
    source_url: str | None = typer.Option(None, "--source-url"),
    opaque_json: str | None = typer.Option(None, "--opaque-json"),
) -> None:
    command = "scorecard.open"
    try:
        runtime = create_runtime()
        opaque = json.loads(opaque_json) if opaque_json else None
        if opaque is not None and not isinstance(opaque, dict):
            raise Agi3Error("opaque JSON은 object 여야 해.", error_type="invalid_opaque_json")
        response = runtime.client.open_scorecard(
            game_ids=list(game_ids or []),
            card_id=card_id,
            tags=list(tags or []),
            source_url=source_url,
            opaque=opaque,
        )
        runtime.session_store.record_scorecard_open(
            card_id=str(response.get("card_id")),
            game_ids=list(game_ids or []),
            response=response,
        )
        emit_success(command, SCORECARD_OPEN_URL, {"scorecard": response})
    except (Agi3Error, json.JSONDecodeError) as exc:
        error = exc if isinstance(exc, Agi3Error) else Agi3Error(
            "opaque JSON 파싱에 실패했어.",
            error_type="invalid_opaque_json",
            details={"input": opaque_json},
        )
        emit_error(command, SCORECARD_OPEN_URL, error)
        raise typer.Exit(1) from exc


@scorecard_app.command("get", help=f"Retrieve a scorecard.\nReference: {SCORECARD_GET_URL}")
def scorecard_get(
    card_id: str | None = typer.Option(None, "--card-id"),
    game_id: str | None = typer.Option(None, "--game-id"),
) -> None:
    command = "scorecard.get"
    try:
        runtime = create_runtime()
        session = runtime.session_store.load()
        resolved_card_id = _require_card_id(session, card_id)
        response = runtime.client.get_scorecard(card_id=resolved_card_id, game_id=game_id)
        emit_success(command, SCORECARD_GET_URL, {"scorecard": response})
    except Agi3Error as exc:
        emit_error(command, SCORECARD_GET_URL, exc)
        raise typer.Exit(1) from exc


@scorecard_app.command("close", help=f"Close a scorecard.\nReference: {SCORECARD_CLOSE_URL}")
def scorecard_close(card_id: str | None = typer.Option(None, "--card-id")) -> None:
    command = "scorecard.close"
    try:
        runtime = create_runtime()
        session = runtime.session_store.load()
        resolved_card_id = _require_card_id(session, card_id)
        response = runtime.client.close_scorecard(card_id=resolved_card_id)
        runtime.session_store.mark_scorecard_closed(card_id=resolved_card_id, response=response)
        emit_success(command, SCORECARD_CLOSE_URL, {"scorecard": response})
    except Agi3Error as exc:
        emit_error(command, SCORECARD_CLOSE_URL, exc)
        raise typer.Exit(1) from exc


@session_app.command("show", help=f"Show the active v3 session.\nReference: {REST_OVERVIEW_URL}")
def session_show() -> None:
    command = "session.show"
    try:
        runtime = create_runtime()
        session = runtime.session_store.load()
        emit_success(
            command,
            REST_OVERVIEW_URL,
            {
                "session": session,
                "paths": {
                    "state_root": str(runtime.session_store.state_root),
                    "session_path": str(runtime.session_store.session_path),
                    "cookies_path": str(runtime.session_store.cookies_path),
                },
            },
        )
    except Agi3Error as exc:
        emit_error(command, REST_OVERVIEW_URL, exc)
        raise typer.Exit(1) from exc


@session_app.command("reset", help=f"Reset local v3 session state.\nReference: {REST_OVERVIEW_URL}")
def session_reset(
    keep_cookies: bool = typer.Option(False, "--keep-cookies", help="Keep persisted cookies"),
) -> None:
    command = "session.reset"
    try:
        runtime = create_runtime()
        removed = runtime.session_store.clear(include_cookies=not keep_cookies)
        emit_success(command, REST_OVERVIEW_URL, removed)
    except Agi3Error as exc:
        emit_error(command, REST_OVERVIEW_URL, exc)
        raise typer.Exit(1) from exc


@game_app.command("start", help=f"Start or reset a game instance.\nReference: {RESET_URL}")
def game_start(
    game_id: str = typer.Option(..., "--game-id"),
    card_id: str | None = typer.Option(None, "--card-id"),
    guid: str | None = typer.Option(None, "--guid"),
    reasoning_json: str | None = typer.Option(None, "--reasoning-json"),
    reasoning_file: Path | None = typer.Option(None, "--reasoning-file"),
) -> None:
    command = "game.start"
    try:
        runtime = create_runtime()
        session = runtime.session_store.load()
        resolved_card_id = _require_card_id(session, card_id)
        reasoning = _load_reasoning(reasoning_json, reasoning_file)
        response = runtime.client.start_game(
            card_id=resolved_card_id,
            game_id=game_id,
            guid=guid,
            reasoning=reasoning,
        )
        runtime.session_store.record_game_response(
            command=command,
            response=response,
            card_id=resolved_card_id,
            game_id=game_id,
            reasoning=reasoning,
        )
        emit_success(command, RESET_URL, {"state": response})
    except (Agi3Error, json.JSONDecodeError) as exc:
        error = exc if isinstance(exc, Agi3Error) else Agi3Error(
            "reasoning JSON 파싱에 실패했어.",
            error_type="invalid_reasoning_input",
        )
        emit_error(command, RESET_URL, error)
        raise typer.Exit(1) from exc


@state_app.command("show", help=f"Show the last stored state snapshot.\nReference: {REST_OVERVIEW_URL}")
def state_show() -> None:
    command = "state.show"
    try:
        runtime = create_runtime()
        session = runtime.session_store.load()
        last_response = session.get("last_response")
        if not last_response:
            raise Agi3Error(
                "저장된 상태가 없어. 먼저 `agi3 game start` 나 `agi3 action run` 을 실행해.",
                error_type="missing_state_snapshot",
            )
        emit_success(
            command,
            REST_OVERVIEW_URL,
            {
                "card_id": session.get("card_id"),
                "game_id": session.get("game_id"),
                "guid": session.get("guid"),
                "summary": session.get("last_response_summary"),
                "state": last_response,
            },
        )
    except Agi3Error as exc:
        emit_error(command, REST_OVERVIEW_URL, exc)
        raise typer.Exit(1) from exc


@action_app.command("run", help=f"Run an ARC action.\nReference: {ACTION1_URL}")
def action_run(
    action: str = typer.Option(..., "--action"),
    x: int | None = typer.Option(None, "--x"),
    y: int | None = typer.Option(None, "--y"),
    game_id: str | None = typer.Option(None, "--game-id"),
    reasoning_json: str | None = typer.Option(None, "--reasoning-json"),
    reasoning_file: Path | None = typer.Option(None, "--reasoning-file"),
) -> None:
    command = "action.run"
    try:
        normalized_action = action.upper()
        if normalized_action not in VALID_ACTIONS:
            raise Agi3Error(
                "지원하지 않는 action 이야.",
                error_type="invalid_action",
                details={"action": action, "valid_actions": sorted(VALID_ACTIONS)},
            )
        if normalized_action == "ACTION6" and (x is None or y is None):
            raise Agi3Error(
                "ACTION6 은 --x 와 --y 가 둘 다 필요해.",
                error_type="missing_action_coordinates",
            )
        if normalized_action != "ACTION6" and (x is not None or y is not None):
            raise Agi3Error(
                "좌표는 ACTION6 에만 줄 수 있어.",
                error_type="unexpected_action_coordinates",
            )
        runtime = create_runtime()
        session = runtime.session_store.load()
        resolved_game_id = _require_game_id(session, game_id)
        guid = _require_guid(session)
        reasoning = _load_reasoning(reasoning_json, reasoning_file)
        response = runtime.client.run_action(
            action=normalized_action,
            game_id=resolved_game_id,
            guid=guid,
            reasoning=reasoning,
            x=x,
            y=y,
        )
        runtime.session_store.record_game_response(
            command=command,
            response=response,
            game_id=resolved_game_id,
            action=normalized_action,
            reasoning=reasoning,
        )
        emit_success(command, ACTION1_URL, {"state": response})
    except (Agi3Error, json.JSONDecodeError) as exc:
        error = exc if isinstance(exc, Agi3Error) else Agi3Error(
            "reasoning JSON 파싱에 실패했어.",
            error_type="invalid_reasoning_input",
        )
        emit_error(command, ACTION1_URL, error)
        raise typer.Exit(1) from exc


def main() -> None:
    app()
