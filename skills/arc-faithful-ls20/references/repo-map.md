# Repo Map

## Faithful track

- Entry point:
  `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/bench.py`
- Decision policy:
  `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/agent.py`
- Memory scoring and loop logic:
  `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/memory.py`
- Long-term JSON memory:
  `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/memory_store.py`
- SQLite experience DB:
  `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/experience_db.py`
- Reference win bootstrap source:
  `../.artifacts/arc-bench/results`
- Local game client:
  `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/local_client.py`
- Scorecard metadata client:
  `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/scorecard_client.py`
- Session bootstrap:
  `../packages/arc_benchmark_faithful/src/arc_benchmark_faithful/session.py`

## Shared repo context

- Root SOT:
  `../AGENTS.md`
- Faithful Codex workspace prompt:
  `../codex_work_faithful/AGENTS.md`
- Faithful wrapper:
  `../scripts/codex_faithful.sh`
- Faithful helper inspector:
  `../scripts/faithful_inspect.py`

## Artifacts

- Experience DB:
  `../.artifacts/arc-bench-faithful/experience.db`
- Result JSON:
  `../.artifacts/arc-bench-faithful/results`
- Checkpoints:
  `../.artifacts/arc-bench-faithful/checkpoints`
- Persistent memory JSON:
  `../.artifacts/arc-bench-faithful/memory`

## Useful searches

```bash
rg -n "break_loop|goal_probe|visited_special|experience" ../packages/arc_benchmark_faithful
rg -n "final_score|result_score|observable_state" ../.artifacts/arc-bench-faithful/checkpoints -g 'action_history.json'
```
