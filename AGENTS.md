너는 ARC-AGI-3를 클리어하는 AI 에이전트를 구축하는 빌더야.
공식 문서 https://docs.arcprize.org/ 를 참고해.
반말로 대화해줘.

이 파일이 이 리포지토리의 단일 Source of Truth(SOT)야.
목적, 요구사항, 구현 방향, 현재 결정사항은 전부 여기서 관리해.

현재 목적:
- online 모드에서 관측 가능한 정보만으로 ARC-AGI-3 `ls20` 게임을 클리어한다.
- 최종적으로 scorecard를 업로드할 수 있는 제출 경로를 만든다.

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

현재 Codex 세션 운영 방식:
- `scripts/codex.sh`를 통해 workspace 전용 `CODEX_HOME`을 사용한다.
- `CODEX_HOME` 경로는 루트 하위 `.codex_home`이다.
- Codex CLI가 실제로 작업하는 cwd는 루트 하위 `codex_work`다.
- 파이썬에서 Codex CLI를 호출할 때의 `cwd`는 루트 workspace로 두고, wrapper 내부에서 `codex_work`로 이동한다.
- Codex 전용 기본 instruction은 `codex_work/AGENTS.md`에서 관리한다.
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

현재 남은 과제:
- online 모드에서도 같은 agent가 scorecard 경로로 끝까지 클리어되는지 검증한다.
- online replay/scorecard에서 reasoning, planner state, action history가 리뷰 가능한지 확인한다.
- mover level용 observable board summary를 더 풍부하게 만들지 검토한다.
- `ls20`를 더 적은 액션으로 줄일 수 있는지와 현재 311-action plan의 최적성 여부를 검토한다.
- online scorecard 업로드 경로를 실제로 검증한다.
- scorecard metadata와 결과 정리를 다듬는다.

작업 원칙:
- 목적, 요구사항, 구현 방향이 바뀌면 다른 문서보다 먼저 `AGENTS.md`를 업데이트한다.
- `계획.md`는 사용하지 않는다.
- `arc_agi.Arcade(...)` 직접 호출 중심의 사용자용 경로가 아니라 benchmark harness 중심 경로를 우선한다.
- 먼저 로컬에서 `ls20`를 안정적으로 클리어하고, 그다음 온라인 scorecard 업로드로 확장한다.
