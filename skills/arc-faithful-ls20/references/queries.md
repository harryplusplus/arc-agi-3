# Query Snippets

Use these only when you need concrete evidence.

## Latest checkpoint

```bash
python3 - <<'PY'
import json
from pathlib import Path
root = Path('../.artifacts/arc-bench-faithful/checkpoints')
path = sorted(root.glob('local-*'), key=lambda p: p.stat().st_mtime, reverse=True)[0] / 'action_history.json'
obj = json.loads(path.read_text())
print(path)
print({'count': len(obj), 'tail': [entry['action'] for entry in obj[-12:]]})
PY
```

Or use the helper:

```bash
python3 ../scripts/faithful_inspect.py latest-checkpoint --prefix local- --limit 8
```

## Latest result files

```bash
ls -t ../.artifacts/arc-bench-faithful/results/*.json | head
```

Or use the helper:

```bash
python3 ../scripts/faithful_inspect.py latest-results --limit 5
```

## Episode and score summary

```bash
python3 - <<'PY'
import sqlite3
con = sqlite3.connect('../.artifacts/arc-bench-faithful/experience.db')
print(con.execute('select count(*), max(final_score) from episodes').fetchone())
print(list(con.execute('select final_score from episodes order by recorded_at desc limit 10')))
PY
```

## Game-level action priors

```bash
python3 - <<'PY'
import sqlite3
con = sqlite3.connect('../.artifacts/arc-bench-faithful/experience.db')
for row in con.execute("""
select action, attempts, moved_count, blocked_count, total_score_delta, total_level_delta
from game_action_stats
where game_id = 'ls20'
order by action
"""):
    print(row)
PY
```

## Exact vs coarse state priors

Pull the current `state_digest` and `coarse_state_digest` from recent reasoning payloads first, then query:

```bash
python3 - <<'PY'
import sqlite3
con = sqlite3.connect('../.artifacts/arc-bench-faithful/experience.db')
state_digest = 'REPLACE_ME'
coarse_digest = 'REPLACE_ME'
print('exact')
for row in con.execute("""
select action, attempts, moved_count, blocked_count, self_loop_count
from state_action_stats
where game_id = 'ls20' and state_digest = ?
order by action
""", (state_digest,)):
    print(row)
print('coarse')
for row in con.execute("""
select action, attempts, moved_count, blocked_count, self_loop_count
from coarse_state_action_stats
where game_id = 'ls20' and coarse_state_digest = ?
order by action
""", (coarse_digest,)):
    print(row)
PY
```

## Winning exact-state transitions

Use this when failed repeats are drowning out a known successful action:

```bash
python3 - <<'PY'
import sqlite3
con = sqlite3.connect('../.artifacts/arc-bench-faithful/experience.db')
state_digest = 'REPLACE_ME'
for row in con.execute("""
select t.action, count(*) as attempts
from transitions t
join episodes e on e.episode_key = t.episode_key
where t.game_id = 'ls20' and t.state_digest = ? and e.final_state = 'WIN'
group by t.action
order by attempts desc, t.action
""", (state_digest,)):
    print(row)
PY
```

## Score change points

```bash
python3 - <<'PY'
import json
from pathlib import Path
root = Path('../.artifacts/arc-bench-faithful/checkpoints')
path = sorted(root.glob('local-*'), key=lambda p: p.stat().st_mtime, reverse=True)[0] / 'action_history.json'
obj = json.loads(path.read_text())
prev = None
for entry in obj:
    if entry['result_score'] != prev:
        obs = entry.get('reasoning', {}).get('observable_state', {})
        print(entry['action_num'], entry['action'], entry['result_score'], obs.get('shape_index'), obs.get('color_index'), obs.get('rotation_index'))
        prev = entry['result_score']
PY
```
