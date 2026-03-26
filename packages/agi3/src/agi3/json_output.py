from __future__ import annotations

import json
from typing import Any

import typer


class Agi3Error(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_type: str = "agi3_error",
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.status_code = status_code
        self.details = details or {}


def emit_success(command: str, reference_url: str, data: Any) -> None:
    typer.echo(
        json.dumps(
            {
                "ok": True,
                "command": command,
                "reference_url": reference_url,
                "data": data,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def emit_error(command: str, reference_url: str, error: Agi3Error) -> None:
    typer.echo(
        json.dumps(
            {
                "ok": False,
                "command": command,
                "reference_url": reference_url,
                "error": {
                    "type": error.error_type,
                    "message": error.message,
                    "status_code": error.status_code,
                    "details": error.details,
                },
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )
