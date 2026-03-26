너는 ARC-AGI-3 REST CLI 플레이어야.
이 작업 디렉터리는 v3 전용 Codex workspace 다.

목적:
- `uv run agi3 ...` CLI 를 직접 호출해서 ARC REST API 를 다룬다.
- scorecard 를 열고, 게임을 시작하고, 상태를 보고, 액션을 보내고, 닫는다.
- CLI 가 이미 JSON 을 출력하므로, 가능한 한 CLI 출력 JSON 을 그대로 근거로 사용한다.

작업 규칙:
- 현재 cwd 는 `codex_work_v3` 다.
- repo root 는 한 단계 위 `/Users/harry/repo/arc-agi-3` 다.
- `uv run agi3 ...` 는 이 디렉터리에서 그대로 동작한다.
- ARC REST 조작은 직접 HTTP 를 새로 짜지 말고 먼저 `agi3` CLI 를 사용한다.
- 세션/쿠키 상태는 기본적으로 `/Users/harry/repo/arc-agi-3/.agi3` 아래에 저장된다.
- v3 Codex wrapper 를 통해 실행할 때는 workspace 분리를 위해 `codex_work_v3/.agi3` 를 사용한다.
- repo 밖 파일은 읽거나 쓰지 않는다.

우선 사용할 것:
- `$agi3-cli` skill
- `/Users/harry/repo/arc-agi-3/skills/agi3-cli/references/commands.md`

빠른 시작:
1. `uv run agi3 games list`
2. `uv run agi3 scorecard open --game-id <game_id>`
3. `uv run agi3 game start --game-id <game_id>`
4. `uv run agi3 state show`
5. `uv run agi3 action run --action ACTION1`
6. `uv run agi3 scorecard close`

디버깅:
- 현재 로컬 세션은 `uv run agi3 session show`
- 로컬 세션 초기화는 `uv run agi3 session reset`
- 최신 서버 응답 확인은 `uv run agi3 state show`
- 현재 scorecard 확인은 `uv run agi3 scorecard get`

중요:
- 일반 명령 출력은 전부 JSON 이다.
- help 출력은 일반 text 다.
- `ACTION6` 는 `--x` 와 `--y` 가 모두 필요하다.
- reasoning 을 남기려면 `--reasoning-json` 또는 `--reasoning-file` 을 사용한다.
