# agi3 command reference

Use these examples when you need exact flags, not as mandatory boilerplate.

## Basic flow

```bash
uv run agi3 games list
uv run agi3 scorecard open --game-id ls20-9607627b
uv run agi3 game start --game-id ls20-9607627b
uv run agi3 state show
uv run agi3 action run --action ACTION1
uv run agi3 scorecard close
```

## Session inspection

```bash
uv run agi3 session show
uv run agi3 session reset
```

## Scorecard inspection

```bash
uv run agi3 scorecard get
uv run agi3 scorecard get --card-id <card_id>
```

## ACTION6 with coordinates

```bash
uv run agi3 action run --action ACTION6 --x 32 --y 40
```

## Action reasoning

Inline JSON:

```bash
uv run agi3 action run \
  --action ACTION1 \
  --reasoning-json '{"summary":"probe the upper corridor"}'
```

File-based reasoning:

```bash
uv run agi3 action run \
  --action ACTION1 \
  --reasoning-file /absolute/path/to/reasoning.json
```
