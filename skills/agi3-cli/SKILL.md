---
name: agi3-cli
description: Use when working with the `agi3` CLI to play ARC-AGI-3 through the REST API, manage scorecards, inspect or reset the local ARC session, start or reset a game, inspect the latest stored frame/state, or run ACTION1-ACTION7 with JSON reasoning payloads.
---

# agi3 CLI

Use `uv run agi3 ...` from the repo root. Let the CLI manage ARC REST calls, sticky cookies, and `.agi3/session.json` state for you.

If you need exact flags or copy-paste examples, read [references/commands.md](references/commands.md).

## Quick start

1. Run `uv run agi3 games list` to find a `game_id`.
2. Run `uv run agi3 scorecard open --game-id <game_id>` to open a scorecard.
3. Run `uv run agi3 game start --game-id <game_id>` to create or reset the current run and store `guid`.
4. Run `uv run agi3 state show` to inspect the latest stored server response.
5. Run `uv run agi3 action run --action ACTION1` or another action.
6. Run `uv run agi3 scorecard close` when done.

## Working rules

- Read JSON fields from CLI output instead of scraping prose. The CLI prints JSON for normal command output.
- Treat `agi3 state show` as the current observable snapshot. There is no separate GET-state endpoint in this workflow; the CLI shows the latest stored response.
- Use `agi3 session show` before debugging odd behavior. It shows current `card_id`, `game_id`, `guid`, and the last stored response summary.
- Use `agi3 session reset` if local session state or cookies get out of sync.
- Use `--reasoning-json` or `--reasoning-file` when you want action reasoning to appear in the replay or scorecard logs.
- Use `ACTION6` only with both `--x` and `--y`.

## What to inspect when stuck

- Read [references/commands.md](references/commands.md) for exact command examples.
- Run `uv run agi3 session show` to check whether the active `card_id` and `guid` are present.
- Run `uv run agi3 state show` to inspect `available_actions`, `levels_completed`, `state`, and the stored frame.
- Run `uv run agi3 scorecard get` to inspect the current server-side scorecard.
