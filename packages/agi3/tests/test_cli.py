from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from agi3.cli import app
from agi3.session import SessionStore


runner = CliRunner()


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def list_games(self):
        self.calls.append(("list_games", {}))
        return [{"game_id": "ls20-9607627b", "title": "LS20"}]

    def open_scorecard(self, **kwargs):
        self.calls.append(("open_scorecard", kwargs))
        return {"card_id": "card-123", "opened": True}

    def get_scorecard(self, **kwargs):
        self.calls.append(("get_scorecard", kwargs))
        return {"card_id": kwargs["card_id"], "state": "OPEN"}

    def close_scorecard(self, **kwargs):
        self.calls.append(("close_scorecard", kwargs))
        return {"card_id": kwargs["card_id"], "closed": True}

    def start_game(self, **kwargs):
        self.calls.append(("start_game", kwargs))
        return {
            "guid": "guid-123",
            "levels_completed": 0,
            "state": "IN_PROGRESS",
            "frame": [[[1, 2], [3, 4]]],
            "available_actions": ["ACTION1", "ACTION2", "ACTION6"],
        }

    def run_action(self, **kwargs):
        self.calls.append(("run_action", kwargs))
        return {
            "guid": kwargs["guid"],
            "levels_completed": 1,
            "state": "IN_PROGRESS",
            "frame": [[[9, 9], [9, 9]]],
            "available_actions": ["ACTION1", "ACTION2"],
        }


class FakeRuntime:
    def __init__(self, state_root: Path):
        self.session_store = SessionStore(state_root)
        self.session_store.ensure()
        self.client = FakeClient()


def make_runtime(tmp_path: Path) -> FakeRuntime:
    return FakeRuntime(tmp_path / ".agi3_test")


def parse_output(result) -> dict:
    assert result.exit_code == 0, result.stdout
    return json.loads(result.stdout)


def parse_error(result) -> dict:
    assert result.exit_code == 1, result.stdout
    return json.loads(result.stdout)


def test_main_help_includes_reference_urls():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "https://docs.arcprize.org/rest_overview" in result.stdout
    assert "https://docs.arcprize.org/api-reference/scorecards/open-scorecard" in result.stdout


def test_games_list_outputs_json(monkeypatch, tmp_path: Path):
    runtime = make_runtime(tmp_path)
    monkeypatch.setattr("agi3.cli.create_runtime", lambda: runtime)
    result = runner.invoke(app, ["games", "list"])
    payload = parse_output(result)
    assert payload["ok"] is True
    assert payload["command"] == "games.list"
    assert payload["data"]["games"][0]["game_id"] == "ls20-9607627b"


def test_scorecard_open_persists_card_id(monkeypatch, tmp_path: Path):
    runtime = make_runtime(tmp_path)
    monkeypatch.setattr("agi3.cli.create_runtime", lambda: runtime)
    result = runner.invoke(app, ["scorecard", "open", "--game-id", "ls20-9607627b", "--tag", "model:gpt-5.4"])
    payload = parse_output(result)
    assert payload["data"]["scorecard"]["card_id"] == "card-123"
    session = runtime.session_store.load()
    assert session["card_id"] == "card-123"
    assert session["scorecard_game_ids"] == ["ls20-9607627b"]


def test_scorecard_open_help_has_reference():
    result = runner.invoke(app, ["scorecard", "open", "--help"])
    assert result.exit_code == 0
    assert "https://docs.arcprize.org/api-reference/scorecards/open-scorecard" in result.stdout


def test_game_start_stores_guid_and_state(monkeypatch, tmp_path: Path):
    runtime = make_runtime(tmp_path)
    runtime.session_store.save({"card_id": "card-123"})
    monkeypatch.setattr("agi3.cli.create_runtime", lambda: runtime)
    result = runner.invoke(app, ["game", "start", "--game-id", "ls20-9607627b"])
    payload = parse_output(result)
    assert payload["data"]["state"]["guid"] == "guid-123"
    session = runtime.session_store.load()
    assert session["guid"] == "guid-123"
    assert session["game_id"] == "ls20-9607627b"
    assert session["last_response_summary"]["frame_shape"] == [2, 2]


def test_action_run_updates_session(monkeypatch, tmp_path: Path):
    runtime = make_runtime(tmp_path)
    runtime.session_store.save({"card_id": "card-123", "game_id": "ls20-9607627b", "guid": "guid-123"})
    monkeypatch.setattr("agi3.cli.create_runtime", lambda: runtime)
    result = runner.invoke(app, ["action", "run", "--action", "ACTION1"])
    payload = parse_output(result)
    assert payload["data"]["state"]["levels_completed"] == 1
    session = runtime.session_store.load()
    assert session["last_action"] == "ACTION1"
    assert session["last_response_summary"]["levels_completed"] == 1


def test_action6_requires_coordinates(monkeypatch, tmp_path: Path):
    runtime = make_runtime(tmp_path)
    runtime.session_store.save({"card_id": "card-123", "game_id": "ls20-9607627b", "guid": "guid-123"})
    monkeypatch.setattr("agi3.cli.create_runtime", lambda: runtime)
    result = runner.invoke(app, ["action", "run", "--action", "ACTION6"])
    payload = parse_error(result)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "missing_action_coordinates"


def test_state_show_returns_last_response(monkeypatch, tmp_path: Path):
    runtime = make_runtime(tmp_path)
    runtime.session_store.save(
        {
            "card_id": "card-123",
            "game_id": "ls20-9607627b",
            "guid": "guid-123",
            "last_response": {"guid": "guid-123", "state": "IN_PROGRESS", "frame": [[[1]]]},
            "last_response_summary": {"guid": "guid-123", "state": "IN_PROGRESS"},
        }
    )
    monkeypatch.setattr("agi3.cli.create_runtime", lambda: runtime)
    result = runner.invoke(app, ["state", "show"])
    payload = parse_output(result)
    assert payload["data"]["state"]["guid"] == "guid-123"
    assert payload["data"]["summary"]["state"] == "IN_PROGRESS"


def test_session_reset_clears_files(monkeypatch, tmp_path: Path):
    runtime = make_runtime(tmp_path)
    runtime.session_store.save({"card_id": "card-123"})
    runtime.session_store.cookies_path.write_text("{}")
    monkeypatch.setattr("agi3.cli.create_runtime", lambda: runtime)
    result = runner.invoke(app, ["session", "reset"])
    payload = parse_output(result)
    assert payload["data"]["session_removed"] is True
    assert payload["data"]["cookies_removed"] is True
