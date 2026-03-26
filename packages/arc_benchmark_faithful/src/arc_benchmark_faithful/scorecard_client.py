from __future__ import annotations

from typing import Any, Dict, List, Optional

from arcagi3.game_client import GameClient
from arcagi3.utils.retry import retry_with_exponential_backoff


class MetadataGameClient(GameClient):
    def __init__(
        self,
        *args,
        metadata_tags: Optional[List[str]] = None,
        source_url: Optional[str] = None,
        opaque: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.metadata_tags = tuple(metadata_tags or ())
        self.source_url = source_url
        self.opaque = opaque

    def open_scorecard(
        self,
        game_ids: List[str],
        card_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        @retry_with_exponential_backoff(max_retries=self.max_retries)
        def _call():
            url = f"{self.ROOT_URL}/api/scorecard/open"
            merged_tags = list(dict.fromkeys([*(tags or []), *self.metadata_tags]))
            data: Dict[str, Any] = {}
            if card_id:
                data["card_id"] = card_id
            if game_ids:
                data["game_ids"] = game_ids
            if merged_tags:
                data["tags"] = merged_tags
            if self.source_url:
                data["source_url"] = self.source_url
            if self.opaque is not None:
                data["opaque"] = self.opaque
            response = self._session.post(url, json=data)
            if response.status_code != 200:
                response.raise_for_status()
            return response.json()

        return _call()
