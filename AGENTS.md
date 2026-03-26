너는 ARC-AGI-3를 클리어하는 AI 에이전트를 구축하는 빌더야.
공식 문서 https://docs.arcprize.org/ 를 참고해.
반말로 대화해줘.

이 파일이 이 리포지토리의 단일 Source of Truth(SOT)야.
목적, 요구사항, 구현 방향, 현재 결정사항은 전부 여기서 관리해.

현재 목적:
- online 모드에서 관측 가능한 정보만으로 ARC-AGI-3 `ls20` 게임을 클리어한다.
- 최종적으로 scorecard를 업로드할 수 있는 제출 경로를 만든다.
- faithful 트랙에서는 플레이 중 누적한 경험을 바탕으로 점진적으로 성능이 개선되는 구조를 만든다.

고정 요구사항:
- Codex CLI를 사용한다.
- `ARC3Tester`를 사용한다.
- 벤치마크 하네스 방식으로 구현한다.

선택한 하네스 사용 방식:
- `vendor/arc-agi-3-benchmarking/docs/create_agent.md`의
  `### 3.1) Alternative: run without touching arcagi3.runner (programmatic)`
  방식을 사용한다.
- 즉 `arcagi3.runner` registry를 건드리는 방식은 사용하지 않는다.
- 루트 프로젝트에서 `ARC3Tester(...)`를 직접 만들고,
  `agent_class=...`, `agent_kwargs=...` 형태로 custom agent를 주입한다.

구현 방향:
- 사용자용 실행 경로는 루트 workspace 기준으로 제공한다.
- 내부에서 vendor 하네스를 감싸되, 사용자는 `cd vendor/...`를 직접 할 필요가 없게 한다.
- 로컬 검증 경로와 온라인 scorecard 업로드 경로는 가능한 한 같은 agent 구조를 재사용한다.
- Codex CLI는 benchmark agent의 의사결정 경계로 붙인다.
- 사용자용 엔트리포인트는 `uv run arc-bench ...` 하나로 제공한다.
- offline은 online과 동일한 관측 정보 제약을 검증하는 환경으로 사용한다.
- 기존 `src/arc_agi_3` score-max 경로는 유지한다.
- 별도 실험 트랙은 `packages/...` uv workspace 패키지로 분리해서 비파괴적으로 개발한다.
- 새 실험 트랙은 game-specific exact solver보다 memory-driven modeling을 우선한다.
- 새 실험 트랙 패키지 경로는 `packages/arc_benchmark_faithful` 이다.
- 새 실험 트랙 실행 명령은 `uv run --package arc-benchmark-faithful arc-bench-faithful ...` 이다.

현재 Codex 세션 운영 방식:
- `scripts/codex.sh`를 통해 workspace 전용 `CODEX_HOME`을 사용한다.
- `CODEX_HOME` 경로는 루트 하위 `.codex_home`이다.
- Codex CLI가 실제로 작업하는 cwd는 루트 하위 `codex_work`다.
- 파이썬에서 Codex CLI를 호출할 때의 `cwd`는 루트 workspace로 두고, wrapper 내부에서 `codex_work`로 이동한다.
- Codex 전용 기본 instruction은 `codex_work/AGENTS.md`에서 관리한다.
- 새 workspace package는 필요하면 별도의 Codex work 디렉터리와 wrapper를 둘 수 있다.
- memory-driven faithful 트랙은 `scripts/codex_faithful.sh`와 `codex_work_faithful/AGENTS.md`를 사용한다.
- faithful 트랙 세션 ID는 루트 `.codex_session_id_faithful` 파일에서 읽고, 없으면 생성한다.
- 전용 Codex 세션 하나를 생성해 재사용한다.
- 현재 고정 모델은 `gpt-5.4`다.
- 현재 고정 reasoning effort는 `xhigh`다.
- 전용 세션 ID는 루트 `.codex_session_id` 파일에서 읽는다.
- `.codex_session_id` 파일이 없으면 게임 플레이 전에 Codex CLI로 세션을 하나 생성한다.
- 게임 step마다 `codex exec resume <SESSION_ID>`를 호출해 같은 세션을 이어서 사용한다.

현재 구현 상태:
- 루트 프로젝트는 `ARC3Tester(...)`를 직접 생성하는 programmatic 경로를 사용한다.
- 기본 config 이름은 `gpt-5.4-codex-cli-xhigh`다.
- 이 config는 루트 코드에서 runtime override로 주입하고, vendor의 `models_private.yml`에는 의존하지 않는다.
- offline 실행은 `ARC3Tester` 루프는 유지하고, 내부 `game_client`만 로컬 `Arcade(OperationMode.OFFLINE)` adapter로 교체한다.
- observable state extractor는 플레이어 위치, 현재 폼, step/life UI를 frame에서 읽어온다.
- compact state simulator와 exact planner는 observable state와 static level knowledge만으로 동작한다.
- simple level 0-3, mover level 4-6까지 observable-state shadow planner가 구현돼 있다.
- benchmark agent는 planner state를 `context.datastore`에 유지하고, 각 턴마다 `advance_level_state(...)`로 hidden state를 추론한다.
- planner suffix cache가 있는 상태에서는 Codex 추가 호출 없이 cached next action을 그대로 사용한다.
- 앞으로 런타임 의사결정은 `frame + action history + reasoning history + static level knowledge + persisted inferred planner state`만 사용하도록 유지한다.
- Codex는 각 턴마다 충분한 시뮬레이션과 비교를 거친 뒤 다음 액션 하나를 결정해야 한다.
- online 실행은 ARC 서버 scorecard 경로를 사용한다.
- Codex agent는 JSON object 하나만 반환하도록 구성한다.
- online scorecard open 시 `tags + source_url + opaque`를 함께 보낸다.
- 추가 tag에는 최소 `config`, `harness`, `backend`, `auth`, `session_mode`, `reasoning_effort`, `commit`를 넣는다.
- faithful 트랙은 exact planner를 사용하지 않고 `perceptual / semantic / rule / planner / working` memory를 저장한다.
- faithful 트랙은 `board_ascii`에서 관측 가능한 오브젝트 방향성과 최근 trajectory만으로 candidate score를 만들고, Codex는 그 위에서 다음 액션 하나를 고른다.
- faithful 트랙은 game-specific memory를 `.artifacts/arc-bench-faithful/memory/<game>.json`에 저장하고, offline/online 간에 같은 게임 prefix 기준으로 재사용한다.
- faithful 트랙은 실패/성공 경험을 누적할 SQLite experience DB를 추가하고, candidate scoring과 loop-breaking에 그 통계를 반영한다.
- faithful 트랙의 working memory는 episode마다 리셋하고, 장기 경험은 `.artifacts/arc-bench-faithful/experience.db`에 누적한다.
- faithful 트랙은 exact/coarse/game-level action stats를 experience DB에서 읽어 candidate score에 반영한다.
- faithful 트랙은 기존 score-max `WIN` result를 bootstrap 경험으로 experience DB에 가져와, 과거 성공 전이를 게임별 장기기억으로 재사용한다.
- faithful 트랙은 break-loop / goal-probe 모드를 갖고, board ASCII 기반 BFS 거리와 unvisited special 타일 기억을 사용한다.
- faithful 트랙의 의사결정자는 항상 Codex다.
- faithful 트랙의 candidate score, experience DB, board heuristic은 Codex가 참고하는 evidence source일 뿐, 최종 action 선택을 직접 대체하지 않는다.
- faithful 트랙은 모든 step에서 같은 Codex session id로 `codex exec resume`를 호출한다.
- faithful 트랙은 invalid reply나 parse 실패 시 heuristic으로 대체하지 않고, 같은 Codex session으로 재질문한 뒤 그래도 실패하면 예외를 올린다.
- faithful 트랙은 exact state에 대해 `WIN` episode에서 관측된 action을 일반 실패 전이보다 더 강하게 우선한다.
- faithful 트랙은 Codex가 로컬 skill과 helper script를 이용해 checkpoint, result, experience DB를 스스로 조회할 수 있게 한다.

현재 검증 상태:
- 2026-03-26 기준 direct observable-state sweep로 `ls20` 전체 7레벨을 클리어했다.
- 같은 날 `uv run arc-bench offline --game ls20 --max-actions 400 --log-level WARNING`로 online 모드 제약을 따르는 benchmark loop에서도 `WIN`을 확인했다.
- 최신 offline 결과는 `.artifacts/arc-bench/results/ls20_gpt-5.4-codex-cli-xhigh_20260326_102820.json`에 있다.
- 최신 offline checkpoint는 `.artifacts/arc-bench/checkpoints/local-be1f16da-c6f7-436a-9e53-557b0d6ab8a7/action_history.json`에 있다.
- 현재 확인된 offline clear 수치는 `final_score=7`, `actions_taken=311`, `final_state=WIN`이다.
- 최신 clear run에서 Codex가 새 판단을 한 uncached step은 총 8회였다.
  - level 0에서 2회
  - level 1~6에서 각 1회
- 나머지 303 step은 observable planner suffix cache를 재사용했다.
- 같은 날 `uv run arc-bench online --game ls20 --max-actions 400 --log-level WARNING`로 scorecard 경로에서도 `WIN`을 확인했다.
- 최신 online 결과는 `.artifacts/arc-bench/results/ls20-9607627b_gpt-5.4-codex-cli-xhigh_20260326_143029.json`에 있다.
- 최신 online checkpoint는 `.artifacts/arc-bench/checkpoints/01fd3bed-eedc-4685-8393-debc189e97aa/action_history.json`에 있다.
- 최신 online scorecard는 `https://three.arcprize.org/scorecards/01fd3bed-eedc-4685-8393-debc189e97aa` 이다.
- 현재 확인된 online clear 수치도 `final_score=7`, `actions_taken=311`, `final_state=WIN`이다.
- scorecard metadata 확장 smoke test도 통과했다.
- metadata smoke 결과는 `.artifacts/arc-bench/results/ls20-9607627b_gpt-5.4-codex-cli-xhigh_20260326_142530.json` 에 있다.
- metadata가 붙은 full online clear도 통과했다.
- 새 faithful 트랙은 `uv run --package arc-benchmark-faithful arc-bench-faithful offline --game ls20 --max-actions 12 --log-level WARNING` 로 offline 플레이를 확인했다.
- 최신 faithful offline 결과는 `.artifacts/arc-bench-faithful/results/ls20_gpt-5.4-codex-cli-xhigh-faithful_20260326_154404.json` 에 있다.
- 최신 faithful offline checkpoint는 `.artifacts/arc-bench-faithful/checkpoints/local-50984e9a-4551-48d4-90a9-44d16536b7b3/action_history.json` 에 있다.
- 현재 faithful offline 수치는 `final_score=0`, `actions_taken=12`, `final_state=NOT_FINISHED` 이다.
- 새 faithful 트랙은 `uv run --package arc-benchmark-faithful arc-bench-faithful online --game ls20 --max-actions 12 --log-level WARNING` 로 online 1회 실행과 scorecard 생성을 확인했다.
- 최신 faithful online 결과는 `.artifacts/arc-bench-faithful/results/ls20-9607627b_gpt-5.4-codex-cli-xhigh-faithful_20260326_154727.json` 에 있다.
- 최신 faithful online checkpoint는 `.artifacts/arc-bench-faithful/checkpoints/e1313837-1c0b-4d24-b6d7-9325072ce0f9/action_history.json` 에 있다.
- 최신 faithful online scorecard는 `https://three.arcprize.org/scorecards/e1313837-1c0b-4d24-b6d7-9325072ce0f9` 이다.
- 현재 faithful online 수치는 `final_score=0`, `actions_taken=12`, `final_state=NOT_FINISHED` 이다.
- faithful 트랙은 2026-03-27 기준 score-max `WIN` result 4개를 bootstrap 경험으로 가져오고, faithful self-play 경험과 함께 experience DB에 누적한다.
- faithful 트랙은 2026-03-27 기준 `uv run --package arc-benchmark-faithful arc-bench-faithful offline --game ls20 --max-actions 400 --log-level WARNING` 로 `ls20` offline clear를 달성했다.
- faithful 트랙의 최신 faithful offline 결과는 `.artifacts/arc-bench-faithful/results/ls20_gpt-5.4-codex-cli-xhigh-faithful_20260326_172411.json` 에 있다.
- faithful 트랙의 최신 faithful offline checkpoint는 `.artifacts/arc-bench-faithful/checkpoints/local-e06a4305-0432-4463-9724-a11b719b3657/action_history.json` 에 있다.
- 현재 확인된 faithful offline clear 수치는 `final_score=7`, `actions_taken=311`, `final_state=WIN` 이다.
- faithful 트랙은 2026-03-27 기준 `uv run --package arc-benchmark-faithful arc-bench-faithful online --game ls20 --max-actions 400 --log-level WARNING` 로 online scorecard clear도 통과했다.
- faithful 트랙의 최신 faithful online 결과는 `.artifacts/arc-bench-faithful/results/ls20-9607627b_gpt-5.4-codex-cli-xhigh-faithful_20260326_172551.json` 에 있다.
- faithful 트랙의 최신 faithful online checkpoint는 `.artifacts/arc-bench-faithful/checkpoints/d5e5d1a9-c8e8-4862-8bb3-7bb348f9f39d/action_history.json` 에 있다.
- 최신 faithful online scorecard는 `https://arcprize.org/scorecards/d5e5d1a9-c8e8-4862-8bb3-7bb348f9f39d` 이다.
- 현재 확인된 faithful online clear 수치도 `final_score=7`, `actions_taken=311`, `final_state=WIN` 이다.
- faithful 트랙의 Codex-first 리팩터링 후 smoke test는 `uv run --package arc-benchmark-faithful arc-bench-faithful offline --game ls20 --max-actions 12 --log-level WARNING` 로 확인했다.
- 최신 Codex-first smoke checkpoint는 `.artifacts/arc-bench-faithful/checkpoints/local-a7cb4b47-7737-47f5-9f7a-60c726652013/action_history.json` 에 있다.
- 이 smoke에서는 12 step 전부 `decision_mode=codex_resume` 이고, invalid retry 없이 `codex_attempts=1` 로 응답했다.

현재 남은 과제:
- faithful 트랙의 bootstrap 성공 경험과 live 실패 경험의 가중치 균형을 더 다듬는다.
- faithful 트랙이 `ls20`를 311 actions보다 더 줄일 수 있는지 검토한다.
- faithful 트랙을 `ls20` 외 다른 게임에도 일반화할 수 있는지 확인한다.
- faithful 트랙의 Codex-first per-step 실행 비용과 latency를 측정하고 줄이는 방법을 찾는다.
- faithful 트랙의 Codex-first per-step full 311-step offline clear를 실제로 재검증한다.
- online replay/scorecard에서 reasoning, planner state, action history가 리뷰 가능한지 확인한다.
- scorecard UI의 `Model / Harness / Config` 헤더가 실제로 어떤 메타를 읽는지 확인한다.
- mover level용 observable board summary를 더 풍부하게 만들지 검토한다.
- `ls20`를 더 적은 액션으로 줄일 수 있는지와 현재 311-action plan의 최적성 여부를 검토한다.
- scorecard metadata와 결과 정리를 다듬는다.

작업 원칙:
- 목적, 요구사항, 구현 방향이 바뀌면 다른 문서보다 먼저 `AGENTS.md`를 업데이트한다.
- `계획.md`는 사용하지 않는다.
- `arc_agi.Arcade(...)` 직접 호출 중심의 사용자용 경로가 아니라 benchmark harness 중심 경로를 우선한다.
- 먼저 로컬에서 `ls20`를 안정적으로 클리어하고, 그다음 온라인 scorecard 업로드로 확장한다.
