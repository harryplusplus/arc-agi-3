from __future__ import annotations

import json
from pathlib import Path

from arc_benchmark_faithful.constants import MEMORY_DIR
from arc_benchmark_faithful.memory import GameMemory


class PersistentGameMemoryStore:
    def __init__(self, root: Path = MEMORY_DIR):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def canonical_game_id(self, game_id: str) -> str:
        if "-" not in game_id:
            return game_id
        prefix, _, suffix = game_id.partition("-")
        if prefix.startswith("ls") and suffix:
            return prefix
        return game_id

    def _path(self, game_id: str) -> Path:
        canonical = self.canonical_game_id(game_id)
        safe = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in canonical)
        return self.root / f"{safe}.json"

    def load(self, game_id: str) -> GameMemory:
        path = self._path(game_id)
        if not path.exists():
            return GameMemory(game_id=self.canonical_game_id(game_id))
        return GameMemory.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, memory: GameMemory) -> None:
        path = self._path(memory.game_id)
        path.write_text(json.dumps(memory.to_dict(), ensure_ascii=True, indent=2), encoding="utf-8")
