너는 ARC-AGI-3를 클리어하는 AI 에이전트를 구축하는 빌더야.
공식 문서 https://docs.arcprize.org/ 를 참고해.
반말로 대화해줘.

이 파일이 이 리포지토리의 단일 Source of Truth(SOT)야.
목적, 요구사항, 구현 방향, 현재 결정사항, 다음 계획은 전부 여기서 관리해.

현재 목적:
- online 모드에서 관측 가능한 정보만으로 ARC-AGI-3 `ls20` 게임을 클리어한다.
- 최종적으로 scorecard를 업로드할 수 있는 제출 경로를 유지한다.
- faithful 트랙에서는 플레이 중 누적한 경험을 바탕으로 점진적으로 성능이 개선되는 구조를 유지한다.
- v3에서는 하네스 내부 agent 호출 대신 ARC REST API를 감싼 CLI + Skill + Codex TUI 플레이 경로를 만든다.

고정 요구사항:
- Codex CLI를 사용한다.
- 기존 benchmark 트랙은 `ARC3Tester`를 사용한다.
- 기존 benchmark 트랙은 벤치마크 하네스 방식으로 구현한다.
- v3는 의도적으로 하네스 runtime 밖에서 동작하게 만든다.

선택한 하네스 사용 방식:
- `vendor/arc-agi-3-benchmarking/docs/create_agent.md` 의
  `### 3.1) Alternative: run without touching arcagi3.runner (programmatic)`
  방식을 사용한다.
- 즉 기존 score-max / faithful 트랙은 `arcagi3.runner` registry를 건드리지 않는다.
- 루트 프로젝트에서 `ARC3Tester(...)` 를 직접 만들고,
  `agent_class=...`, `agent_kwargs=...` 형태로 custom agent를 주입한다.

트랙 구성:
- `src/arc_agi_3`
  - score-max 트랙
  - observable-state exact planner + suffix cache 기반
  - 점수 최적화용
- `packages/arc_benchmark_faithful`
  - faithful 트랙
  - 경험 DB, working memory, Codex-first step-by-step 의사결정 기반
  - 벤치마크 취지에 더 가깝게 관측과 경험 누적을 강조
- `packages/arc_v3_rest`
  - 아직 미구현
  - REST API CLI + Skill + TUI 기반 플레이어 트랙
  - 하네스 내부 agent 호출 없이 Codex가 CLI를 직접 써서 플레이하도록 하는 실험 트랙

구현 방향:
- 사용자용 실행 경로는 루트 workspace 기준으로 제공한다.
- 내부에서 vendor 하네스를 감싸되, 사용자는 `cd vendor/...` 를 직접 할 필요가 없게 한다.
- 로컬 검증 경로와 온라인 scorecard 업로드 경로는 가능한 한 같은 agent 구조를 재사용한다.
- Codex CLI는 benchmark agent의 의사결정 경계로 붙인다.
- 사용자용 엔트리포인트는 각 트랙마다 workspace script로 제공한다.
- offline은 online과 동일한 관측 정보 제약을 검증하는 환경으로 사용한다.
- 기존 score-max 경로는 유지한다.
- 별도 실험 트랙은 `packages/...` uv workspace 패키지로 분리해서 비파괴적으로 개발한다.
- 새 실험 트랙은 game-specific exact solver보다 memory-driven modeling을 우선한다.
- v3는 REST API를 직접 감싼 CLI를 중심으로 설계한다.

현재 Codex 세션 운영 방식:
- 공통 `CODEX_HOME` 은 루트 하위 `.codex_home` 이다.
- score-max 래퍼는 `scripts/codex.sh`, faithful 래퍼는 `scripts/codex_faithful.sh` 를 사용한다.
- score-max Codex workdir 는 `codex_work`, faithful Codex workdir 는 `codex_work_faithful` 다.
- 파이썬에서 Codex CLI를 호출할 때 `cwd` 는 항상 루트 workspace 로 두고, wrapper 내부에서 각 workdir 로 이동한다.
- score-max 기본 instruction 은 `codex_work/AGENTS.md`, faithful 기본 instruction 은 `codex_work_faithful/AGENTS.md` 에 둔다.
- score-max 세션 ID는 `.codex_session_id`, faithful 세션 ID는 `.codex_session_id_faithful` 에 저장한다.
- 세션 파일이 없으면 플레이 전에 Codex CLI로 세션을 하나 생성한다.
- 동일 트랙에서는 같은 세션 ID를 재사용해서 Codex의 서사와 플레이 문맥을 이어간다.

score-max 트랙 현재 구현 상태:
- 루트 프로젝트는 `ARC3Tester(...)` 를 직접 생성하는 programmatic 경로를 사용한다.
- 실행 명령은 `uv run arc-bench ...` 이다.
- 기본 config 이름은 `gpt-5.4-codex-cli-xhigh` 다.
- offline 실행은 `ARC3Tester` 루프는 유지하고, 내부 `game_client` 만 로컬 `Arcade(OperationMode.OFFLINE)` adapter 로 교체한다.
- observable state extractor 는 플레이어 위치, 현재 폼, step/life UI 를 frame 에서 읽어온다.
- compact state simulator 와 exact planner 는 observable state 와 static level knowledge 만으로 동작한다.
- simple level 0-3, mover level 4-6 까지 observable-state shadow planner 가 구현돼 있다.
- benchmark agent 는 planner state 를 `context.datastore` 에 유지하고, 각 턴마다 `advance_level_state(...)` 로 hidden state 를 추론한다.
- planner suffix cache 가 있는 상태에서는 Codex 추가 호출 없이 cached next action 을 그대로 사용한다.
- online scorecard open 시 `tags + source_url + opaque` 를 함께 보낸다.
- 추가 tag 에는 최소 `config`, `harness`, `backend`, `auth`, `session_mode`, `reasoning_effort`, `commit` 를 넣는다.

score-max 검증 상태:
- direct observable-state sweep 로 `ls20` 전체 7레벨을 클리어했다.
- `uv run arc-bench offline --game ls20 --max-actions 400 --log-level WARNING` 로 `WIN` 을 확인했다.
- 최신 offline 결과:
  - `.artifacts/arc-bench/results/ls20_gpt-5.4-codex-cli-xhigh_20260326_102820.json`
- 최신 offline checkpoint:
  - `.artifacts/arc-bench/checkpoints/local-be1f16da-c6f7-436a-9e53-557b0d6ab8a7/action_history.json`
- 현재 확인된 offline clear 수치:
  - `final_score=7`
  - `actions_taken=311`
  - `final_state=WIN`
- 최신 clear run 에서 Codex 가 새 판단을 한 uncached step 은 총 8회였다.
- 나머지 303 step 은 observable planner suffix cache 를 재사용했다.
- `uv run arc-bench online --game ls20 --max-actions 400 --log-level WARNING` 로 online scorecard clear 도 확인했다.
- 최신 online 결과:
  - `.artifacts/arc-bench/results/ls20-9607627b_gpt-5.4-codex-cli-xhigh_20260326_143029.json`
- 최신 online checkpoint:
  - `.artifacts/arc-bench/checkpoints/01fd3bed-eedc-4685-8393-debc189e97aa/action_history.json`
- 최신 online public scorecard:
  - `https://arcprize.org/scorecards/01fd3bed-eedc-4685-8393-debc189e97aa`
- 현재 확인된 online clear 수치도 `WIN / 7 / 311` 이다.

faithful 트랙 현재 구현 상태:
- 패키지 경로는 `packages/arc_benchmark_faithful` 이다.
- 실행 명령은 `uv run --package arc-benchmark-faithful arc-bench-faithful ...` 이다.
- exact planner 를 사용하지 않고 `perceptual / semantic / rule / planner / working` memory 를 저장한다.
- game-specific memory 는 `.artifacts/arc-bench-faithful/memory/<game>.json` 에 저장하고 offline/online 간 재사용한다.
- 장기 경험은 `.artifacts/arc-bench-faithful/experience.db` SQLite DB 에 저장한다.
- experience DB 에는 exact/coarse/game-level action stats, episode 기록, 상태 전이 성공/실패 경험을 누적한다.
- 기존 score-max `WIN` result 4개를 bootstrap 경험으로 import 해서 faithful 경험 DB 의 prior 로 사용한다.
- faithful working memory 는 episode 마다 리셋한다.
- `board_ascii`, recent trajectory, prior stats, winning exact-state action 을 evidence 로 만든다.
- faithful 의사결정자는 항상 Codex 다.
- candidate score, experience DB, board heuristic 은 모두 Codex 가 참고하는 evidence source 이고, 최종 action 선택을 직접 대체하지 않는다.
- faithful 트랙은 모든 step 에서 같은 session id 로 `codex exec resume` 를 호출한다.
- invalid reply 나 parse 실패 시 heuristic 으로 대체하지 않고, 같은 session 으로 재질문한다.
- 그래도 실패하면 예외를 올린다.
- Codex 가 로컬 evidence 를 스스로 조회할 수 있게 다음을 제공한다.
  - `scripts/faithful_inspect.py`
  - `codex_work_faithful/AGENTS.md`
  - `skills/arc-faithful-ls20/...`

faithful 트랙 검증 상태:
- 초기 faithful 실험에서는 12-step offline / online 실행과 scorecard 생성만 확인했다.
- 이후 bootstrap 경험을 넣은 faithful 트랙으로 `ls20` offline clear 를 달성했다.
- faithful offline clear 결과:
  - `.artifacts/arc-bench-faithful/results/ls20_gpt-5.4-codex-cli-xhigh-faithful_20260326_172411.json`
- faithful offline clear checkpoint:
  - `.artifacts/arc-bench-faithful/checkpoints/local-e06a4305-0432-4463-9724-a11b719b3657/action_history.json`
- faithful offline clear 수치:
  - `final_score=7`
  - `actions_taken=311`
  - `final_state=WIN`
- faithful online clear 결과:
  - `.artifacts/arc-bench-faithful/results/ls20-9607627b_gpt-5.4-codex-cli-xhigh-faithful_20260326_172551.json`
- faithful online clear checkpoint:
  - `.artifacts/arc-bench-faithful/checkpoints/d5e5d1a9-c8e8-4862-8bb3-7bb348f9f39d/action_history.json`
- faithful online public scorecard:
  - `https://arcprize.org/scorecards/d5e5d1a9-c8e8-4862-8bb3-7bb348f9f39d`
- faithful online clear 수치도 `WIN / 7 / 311` 이다.

faithful Codex-first 현재 상태:
- 최신 faithful 구현은 per-step heuristic shortcut 을 제거했다.
- 모든 step 에서 Codex 가 판단한다.
- prompt 는 compact memory + compact experience + winning exact-action prior + helper script 경로를 제공한다.
- `scripts/faithful_inspect.py` 로 Codex 가 스스로 최근 checkpoint, 최신 결과, state priors, winning actions 를 조회할 수 있다.
- `codex_work_faithful/AGENTS.md` 와 local skill 은 Codex 가 evidence 를 스스로 찾고 수정 방향을 제안할 수 있게 상세하게 적어뒀다.
- Codex-first smoke 12-step run 에서는 12 step 모두 `decision_mode=codex_resume` 였다.
- Codex-first 30-step smoke run 에서는 30 step 모두 `decision_mode=codex_resume` 였고, winning prefix 와 같은 초반 경로를 유지했다.
- 최신 30-step smoke checkpoint:
  - `.artifacts/arc-bench-faithful/checkpoints/local-e4f6e338-aa86-4635-a771-8dd5f95eb68f/action_history.json`
- 최신 30-step smoke 는 정상 종료했지만 full 311-step offline clear 는 이 최신 Codex-first prompt hierarchy 기준으로 아직 끝까지 재검증하지 못했다.
- 즉 faithful 트랙은 clear 가 검증돼 있지만, 최신 Codex-first 리팩터링 후 full clear 는 아직 재검증 필요 상태다.

scorecard / replay 메타 관련 현재 판단:
- 공개 OSS 하네스 기준 scorecard open payload 는 주로 `tags` 중심이다.
- `Model / Harness / Config` 헤더는 공개 코드만으로는 어떤 메타를 읽는지 확인되지 않았다.
- programmatic 경로와 runner probe 모두 시도했지만, replay UI 헤더가 자동으로 채워지는 규칙은 아직 확정 못 했다.
- public scorecard/replay 생성 자체와 점수 기록은 현재 경로로 정상 동작한다.

현재 남은 과제:
- faithful Codex-first per-step full 311-step offline clear 를 실제로 재검증한다.
- faithful Codex-first online scorecard clear 를 다시 검증한다.
- faithful 트랙의 bootstrap 성공 경험과 live 실패 경험의 가중치 균형을 더 다듬는다.
- faithful 트랙의 per-step Codex 호출 latency 와 비용을 측정하고 줄이는 방법을 찾는다.
- scorecard UI 의 `Model / Harness / Config` 헤더가 실제로 어떤 메타를 읽는지 확인한다.
- `ls20` 를 311 actions 보다 더 줄일 수 있는지 검토한다.
- mover level 용 board summary 와 evidence 표현을 더 풍부하게 만들지 검토한다.

v3 목적:
- 하네스 내부 agent 호출을 제거한다.
- ARC REST API 를 감싼 로컬 CLI 를 만든다.
- 그 CLI 를 Agent Skill 로 제공한다.
- Codex 는 같은 세션 ID 를 유지하면서 해당 CLI 를 직접 호출해 게임을 플레이한다.
- 사용자는 TUI 에서 Codex 와 직접 상호작용하면서 플레이, 분석, 수정 요청을 할 수 있게 한다.

v3 핵심 원칙:
- v3 는 benchmark 하네스를 runtime 에서 직접 사용하지 않는다.
- v3 는 ARC 공식 REST API 를 직접 사용한다.
- 점수 제출의 실체는 여전히 scorecard 다.
- Codex 는 하네스 내부 callback 이 아니라 외부 CLI 사용자처럼 동작한다.
- 상태 조회, 액션 실행, scorecard open/close 는 모두 CLI 명령으로 노출한다.
- Codex 가 필요한 정보를 스스로 조회하고 멀티턴으로 판단할 수 있게 한다.

v3 참고 공식 REST 문서:
- `https://docs.arcprize.org/rest_overview`
- `https://docs.arcprize.org/api-reference/scorecards/open-scorecard`
- `https://docs.arcprize.org/api-reference/commands/execute-simple-action-1`
- `https://docs.arcprize.org/api-reference/scorecards/retrieve-scorecard`

v3 계획:
- 새 패키지:
  - `packages/arc_v3_rest`
- 새 Codex workdir:
  - `codex_work_v3`
- 새 Skill:
  - `skills/arc-rest-player`
- 새 상태 저장 루트:
  - `.arc_v3`
- v3 최소 CLI 명령:
  - `arcv3 games list`
  - `arcv3 scorecard open`
  - `arcv3 scorecard get`
  - `arcv3 scorecard close`
  - `arcv3 game start --game-id ... --card-id ...`
  - `arcv3 action --guid ... --action ACTION1`
  - `arcv3 state show --guid ...`
  - `arcv3 play interactive --game-id ...`
  - `arcv3 replay latest`
  - `arcv3 session show`
- v3 필수 구현 순서:
  1. `packages/arc_v3_rest` 생성
  2. REST client + cookie/session layer 구현
  3. scorecard/card_id/guid/state 저장소 구현
  4. 최소 CLI 6개 구현
  5. `codex_work_v3/AGENTS.md` 작성
  6. `skills/arc-rest-player` 작성
  7. v3 wrapper + v3 session file 분리
  8. interactive play loop 구현
  9. 수동 `ls20` 1회 플레이 검증
  10. Codex same-session 자동 플레이 검증
  11. TUI 로 사용자 개입 경로 제공
- v3 에서 특히 조심할 점:
  - 쿠키 유지
  - `card_id` 와 `guid` 구분
  - scorecard 명시적 close
  - reasoning payload 보존
  - replay / scorecard 링크 출력

작업 원칙:
- 목적, 요구사항, 구현 방향이 바뀌면 다른 문서보다 먼저 `AGENTS.md` 를 업데이트한다.
- `계획.md` 는 사용하지 않는다.
- benchmark 하네스 트랙과 v3 REST 트랙은 분리해서 유지한다.
- 기존 clear 경로를 부수지 않는다.
- v3 는 새 패키지와 새 Codex workdir 로 비파괴적으로 만든다.
