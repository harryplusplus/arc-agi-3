너는 ARC-AGI-3를 클리어하는 AI 에이전트를 구축하는 빌더야.
공식 문서 https://docs.arcprize.org/ 를 참고해.
반말로 대화해줘.

이 파일이 이 리포지토리의 단일 Source of Truth(SOT)야.
목적, 요구사항, 구현 방향, 현재 결정사항은 전부 여기서 관리해.

현재 목적:
- ARC-AGI-3 `ls20` 게임을 클리어한다.
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

현재 Codex 세션 운영 방식:
- `scripts/codex.sh`를 통해 workspace 전용 `CODEX_HOME`을 사용한다.
- `CODEX_HOME` 경로는 루트 하위 `.codex-home`이다.
- 전용 Codex 세션 하나를 생성해 재사용한다.
- 현재 고정 모델은 `gpt-5.4`다.
- 현재 고정 reasoning effort는 `xhigh`다.
- 현재 전용 세션 ID는 `019d290a-0d8e-7f03-9903-4494c14c4746`다.
- 파이썬 코드에서는 이 세션 ID를 상수로 참조한다.

현재 핵심 결정사항:
- `codex exec`를 매 step 새로 호출할지, `resume`으로 세션을 이어갈지 결정해야 한다.
- 로컬 검증용 client adapter 범위를 어디까지 둘지 결정해야 한다.
- 온라인 scorecard metadata를 어떤 형식으로 남길지 결정해야 한다.

작업 원칙:
- 목적, 요구사항, 구현 방향이 바뀌면 다른 문서보다 먼저 `AGENTS.md`를 업데이트한다.
- `계획.md`는 사용하지 않는다.
- `arc_agi.Arcade(...)` 직접 호출 중심의 사용자용 경로가 아니라 benchmark harness 중심 경로를 우선한다.
- 먼저 로컬에서 `ls20`를 안정적으로 클리어하고, 그다음 온라인 scorecard 업로드로 확장한다.
