from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from requests import Session
from requests.cookies import cookiejar_from_dict
from requests.utils import dict_from_cookiejar

from agi3.json_output import Agi3Error


class ArcRestClient:
    DEFAULT_BASE_URL = "https://three.arcprize.org"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        cookies_path: Path | None = None,
        session: Session | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key or os.getenv("ARC_API_KEY")
        if not self.api_key:
            raise Agi3Error(
                "ARC_API_KEY가 필요해. 환경변수나 루트 .env에 설정해줘.",
                error_type="missing_api_key",
            )

        self.base_url = (base_url or os.getenv("ARC_URL_BASE") or self.DEFAULT_BASE_URL).rstrip("/")
        self.cookies_path = cookies_path
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "X-API-Key": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self._load_cookies()

    def _load_cookies(self) -> None:
        if not self.cookies_path or not self.cookies_path.exists():
            return
        payload = json.loads(self.cookies_path.read_text())
        self.session.cookies.update(cookiejar_from_dict(payload))

    def _save_cookies(self) -> None:
        if not self.cookies_path:
            return
        self.cookies_path.parent.mkdir(parents=True, exist_ok=True)
        self.cookies_path.write_text(
            json.dumps(dict_from_cookiejar(self.session.cookies), indent=2, ensure_ascii=False, sort_keys=True)
        )

    def _request(self, method: str, path: str, *, json_payload: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            json=json_payload,
            timeout=self.timeout_seconds,
        )
        self._save_cookies()
        try:
            payload = response.json()
        except ValueError as exc:
            raise Agi3Error(
                "서버 응답이 JSON이 아니야.",
                error_type="invalid_json_response",
                status_code=response.status_code,
                details={"text": response.text},
            ) from exc
        if response.status_code != 200:
            raise Agi3Error(
                "ARC API 요청이 실패했어.",
                error_type="api_error",
                status_code=response.status_code,
                details={"response": payload},
            )
        return payload

    def list_games(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/games")
        return list(payload)

    def open_scorecard(
        self,
        *,
        game_ids: list[str] | None = None,
        card_id: str | None = None,
        tags: list[str] | None = None,
        source_url: str | None = None,
        opaque: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if game_ids:
            data["game_ids"] = game_ids
        if card_id:
            data["card_id"] = card_id
        if tags:
            data["tags"] = tags
        if source_url:
            data["source_url"] = source_url
        if opaque:
            data["opaque"] = opaque
        payload = self._request("POST", "/api/scorecard/open", json_payload=data)
        return dict(payload)

    def get_scorecard(self, *, card_id: str, game_id: str | None = None) -> dict[str, Any]:
        path = f"/api/scorecard/{card_id}"
        if game_id:
            path = f"{path}/{game_id}"
        payload = self._request("GET", path)
        return dict(payload)

    def close_scorecard(self, *, card_id: str) -> dict[str, Any]:
        payload = self._request("POST", "/api/scorecard/close", json_payload={"card_id": card_id})
        return dict(payload)

    def start_game(
        self,
        *,
        card_id: str,
        game_id: str,
        guid: str | None = None,
        reasoning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {"card_id": card_id, "game_id": game_id}
        if guid:
            data["guid"] = guid
        if reasoning is not None:
            data["reasoning"] = reasoning
        payload = self._request("POST", "/api/cmd/RESET", json_payload=data)
        return dict(payload)

    def run_action(
        self,
        *,
        action: str,
        game_id: str,
        guid: str,
        reasoning: dict[str, Any] | None = None,
        x: int | None = None,
        y: int | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "game_id": game_id,
            "guid": guid,
        }
        if reasoning is not None:
            data["reasoning"] = reasoning
        if x is not None:
            data["x"] = x
        if y is not None:
            data["y"] = y
        payload = self._request("POST", f"/api/cmd/{action}", json_payload=data)
        return dict(payload)
