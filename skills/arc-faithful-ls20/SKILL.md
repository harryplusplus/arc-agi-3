---
name: arc-faithful-ls20
description: Use when working inside this ARC-AGI-3 repo on the faithful ls20 benchmark track and you need to inspect checkpoints, results, the experience SQLite DB, or the faithful agent source before deciding what to do next.
---

# ARC Faithful LS20

Use this skill when the task is about the repo's faithful track, especially `ls20`.

## Workflow

1. Start from local evidence, not guesses.
2. Check the latest checkpoint or result JSON to see the current failure pattern.
3. Query the experience DB to see whether the state/action pattern is already known.
4. Read only the relevant faithful source files before proposing a change.
5. Prefer minimal changes tied to a concrete failure pattern.

## Priority Sources

- Repo SOT: `../AGENTS.md`
- Faithful agent: `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/agent.py`
- Faithful memory rules: `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/memory.py`
- Experience DB logic: `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/experience_db.py`
- Latest results and checkpoints: `../.artifacts/arc-bench-faithful`

## When To Inspect The DB

- The agent is looping.
- The score plateaus on the same level.
- You need to compare exact state priors vs coarse state priors.
- You need to see whether a special tile or action has already been overused.

Read [queries.md](references/queries.md) for ready-to-run inspection snippets.
Read [repo-map.md](references/repo-map.md) for the faithful track file map.
