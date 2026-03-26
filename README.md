# ARC-AGI-3 Play

### Development Environment

1. Clone this repository:

```sh
git clone https://github.com/harryplusplus/arc-agi-3.git
cd arc-agi-3
git submodule update --init --recursive
```

2. Sync project with `uv sync --locked` command.

### Run

Offline:

```sh
uv run arc-bench offline --game ls20 --max-actions 400 --log-level WARNING
```

Online:

```sh
uv run arc-bench online --game ls20 --max-actions 400 --log-level WARNING
```

### Architecture

This repository uses the ARC benchmarking harness programmatically through `ARC3Tester` instead of editing `arcagi3.runner`.

High-level flow:

1. `uv run arc-bench ...`
2. `src/arc_agi_3/bench.py`
3. `ARC3Tester`
4. game client
5. `CodexResumeAgent`
6. observable-state extractor
7. shadow planner
8. ARC action

Core pieces:

- `src/arc_agi_3/bench.py`
  - Root entrypoint.
  - Loads `.env`.
  - Injects the local `gpt-5.4-codex-cli-xhigh` model config at runtime.
  - Creates `ARC3Tester(...)` directly.
  - Chooses the game client:
    - offline: `LocalArcGameClient`
    - online: `MetadataGameClient`

- `src/arc_agi_3/agent.py`
  - Defines `CodexResumeAgent`.
  - Reuses one dedicated Codex session via `codex exec resume <SESSION_ID>`.
  - Stores inferred planner state in `context.datastore`.
  - Calls Codex only when a new plan prefix is needed.
  - Reuses cached suffix actions for the rest of the level when possible.

- `src/arc_agi_3/ls20_observable.py`
  - Extracts only visible state from the frame.
  - Current extractor reads:
    - player position
    - current form preview
    - step counter
    - lives
  - This is the runtime observation surface used by the agent.

- `src/arc_agi_3/offline_planner.py`
  - Contains the observable-state shadow simulator and planner.
  - Covers:
    - simple levels
    - mover levels
    - hidden-state carry-over through inferred planner state
  - Produces exact action plans for `ls20`.
  - Builds suffix caches so later steps can skip extra Codex calls.

- `src/arc_agi_3/local_client.py`
  - Offline adapter.
  - Keeps the same benchmark-agent loop, but swaps the backend game client for local `Arcade(OperationMode.OFFLINE)`.

- `src/arc_agi_3/scorecard_client.py`
  - Online adapter.
  - Extends the default harness game client to attach scorecard metadata.
  - Adds:
    - extra tags
    - `source_url`
    - `opaque`

### Decision Flow

For each step:

1. The harness provides the latest frame and action history.
2. `observe_state(...)` converts the frame into visible state.
3. The agent advances the inferred planner state from the previous step.
4. The planner computes the shortest remaining action sequence for the current level.
5. If the suffix is already cached, the next action is used directly.
6. Otherwise Codex receives:
   - recent history
   - frame grids
   - observable state
   - inferred planner state
   - planner summary
7. Codex returns one JSON action object.
8. If Codex disagrees with the exact planner, the planner action wins.

### Core Algorithm

The agent is not using Codex as a pure every-step policy.

It uses a two-layer decision system:

1. observable-state reconstruction
2. exact shadow planning

#### Observable-State Reconstruction

The runtime agent only trusts information that is available from the current frame and action history.

That means:

- visible frame data is read directly
- hidden mechanics are carried forward through an inferred planner state
- local game internals are not used at runtime to choose actions

The planner state includes:

- player position
- current shape / color / rotation
- remaining goals / refills
- steps / lives
- mover state for later levels

#### Exact Shadow Planner

`offline_planner.py` contains a compact simulator for `ls20`.

It mirrors the game mechanics at the level needed to plan:

- movement
- changers
- goals
- refills
- pushers
- movers

For the current inferred state, it searches for the shortest remaining action sequence for the current level.

#### Suffix Cache

The planner does not re-solve the whole level on every step.

When it finds a plan like:

```text
[A1, A2, A3, A4]
```

it also stores every remaining suffix:

```text
state0 -> [A1, A2, A3, A4]
state1 -> [A2, A3, A4]
state2 -> [A3, A4]
state3 -> [A4]
```

So after the first solve, later steps can often skip replanning and just reuse the next cached action for the new state.

This is why the agent can clear long levels without calling Codex every turn.

#### When Codex Is Actually Called

Codex is called when:

- a new level starts
- the current state has no cached suffix
- the planner needs a fresh plan prefix

Codex is not called when:

- the exact next action is already known from the suffix cache

In the latest 311-action winning run:

- Codex made 8 uncached decisions
- 303 actions were reused from cached planner suffixes

#### Planner Override

Codex still receives:

- recent action history
- frame grids
- observable state
- inferred planner state
- planner summary

and returns one JSON action object.

But if Codex suggests an action that does not match the exact planner result, the planner action is used.

That makes Codex a bounded decision layer on top of an exact per-level planner, not the final source of truth for action execution.

### Why Offline Matters

The offline path is not a separate toy implementation.

- It uses the same `ARC3Tester` loop.
- It uses the same `CodexResumeAgent`.
- It uses the same observable-state input discipline.
- The only backend swap is the game client:
  - offline uses a local environment
  - online uses ARC scorecards

Because of that, offline clear is used as the main safety check before online scorecard runs.

### Scorecard Metadata

Online scorecards are opened with both harness-generated tags and repository-specific metadata.

Current extra metadata includes:

- `config:gpt-5.4-codex-cli-xhigh`
- `harness:arc3tester-programmatic`
- `backend:codex-cli`
- `auth:codex-oauth`
- `session_mode:resume`
- `reasoning_effort:xhigh`
- `commit:<git sha>`

The online client also sends:

- `source_url`
- `opaque`

so the scorecard can be traced back to the exact repository revision and runtime setup.
