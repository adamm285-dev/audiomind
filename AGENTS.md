# AGENTS.md — Operational Harness Protocol
<!-- Conforming to SPEC-001 v1.9.0 -->

## 1. The Operational Ontology
You are operating inside a deterministic cybernetic control system, not an unconstrained environment. The codebase is organized across three layers that hold the 7 pillars, governed by a teleological anchor:

- **0. Teleological Anchor (The Target):** `roadmap.md` (Pillar 3: The North Star). Macro acceptance contract: `[INTENT]` vs `[MEASURED]`. Your sole task is driving the measured delta to zero.
- **1. Semantic Layer (What Exists):** `spine.md` (Pillar 1: Constitutional Invariants & Axioms), `wiring.yaml` (Pillar 2: Subsystem Boundaries & Dependency Mesh), and `app_map.md` (Pillar 5: Repository Cartography). You cannot invent entities or subsystems outside this declared schema.
- **2. Kinetic Layer (The Laws of Motion):** Gate T AST boundary audits (`sdcs verify --topology`), Gate M cartography drift checks (`sdcs map --check`), Gate C (Contract Immutability), Gate L mock ledger reconciliation (`sdcs verify --mocks`), and physical pre-commit hooks (`.githooks/pre-commit`). Every code mutation is a kinetic state transition; attempts to violate topological contracts are physically rejected on disk.
- **3. Dynamic Layer (Memory & Time Evolution):** `decisions.md` (Pillar 6: Negative Episodic Memory / Graveyard), `evals.md` (Pillar 7: Positive Episodic Memory / Empirical Standing & SHA-256 fixture locks), `state.md` (Pillar 4: Active Working Blackboard <= 300 tokens), and `sessions/manifest.jsonl` (+1 Flight Recorder Causal Lineage).

## 2. Turn 1 Boot Hydration Order (7 Pillars)
On Turn 1 of any task, you MUST hydrate state across the 7 cognitive pillars in this exact sequence:
1. `spine.md`        -> Constitutional invariants & forbidden actions (Pillar 1: The Law)
2. `roadmap.md`      -> Active milestone [INTENT] vs [MEASURED] (Pillar 3: The North Star)
3. `app_map.md`      -> Repository cartography (resolve target paths first) (Pillar 5: The Compass)
4. `decisions.md`    -> Negative episodic memory (rejected hypotheses) (Pillar 6: The Graveyard)
5. `evals.md`        -> Verified empirical baseline & ground truth (Pillar 7: Positive Ground Truth)
6. `state.md`        -> Turn-by-turn active working memory (Pillar 4: The Blackboard)
7. `wiring.yaml`     -> Declarative topology & subsystem boundaries (Pillar 2: The Mesh)

## +1 Flight Recorder Invariant
CRITICAL INVARIANT: NEVER inspect or hydrate `sessions/*.md` on boot.
`sessions/*.md` serves as an immutable post-hoc flight recorder, NOT boot context. Auto-loading historical sessions recreates context drift and episodic amnesia. Query individual sessions or `sessions/manifest.jsonl` on demand for forensic debugging (`sdcs session`).

## 3. The 4-Phase Autonomous Execution Cycle
Execute every turn through the 4-phase engine:
1. **Orientation:** Hydrate constraints and ground truth from the Semantic and Dynamic layers.
2. **Planning:** Formulate atomic diffs against `state.md` respecting boundaries in `wiring.yaml`.
3. **Execution:** Apply code mutations and verify against kinetic gates (Gate T AST audits) and empirical baselines (`evals.md`).
4. **Close-Out:** Prune `state.md` (<= 300 tokens), log rejections in `decisions.md`, and record shift progress in `sessions/`.

## 4. Invariant Rules
- **Context Isolation:** Consult `app_map.md` and load only what is strictly relevant to the task (use `sdcs map -s <subsystem>` for focused slicing).
- **No Task Queue in Roadmap:** Active tasks live strictly in `state.md`.
- **Non-Regression:** Never undo a decision or retry a measured rejection documented in `decisions.md` without explicit human sign-off.
- **Topological Invariant (Gate T):** Code must respect subsystem boundary contracts declared in `wiring.yaml`. Prohibited imports will be rejected and serialized to `decisions.md`.
- **Wiring Mutation Invariant (Pillar 2):** When introducing new subsystems, modules, or packages, update `wiring.yaml` in-stride with code modifications. Modifying `wiring.yaml` to relax existing architectural boundaries, add circular dependencies, or bypass Gate T rejections without explicit human authorization (`SDCS_ALLOW_INVARIANT_MUTATION=1`) is strictly forbidden.
- **Empirical Standing:** Verify changes against the baseline scorecard in `evals.md`. Run `sdcs eval record <Asset-ID>|all` (or `sdcs audit`) when adding, recalibrating, or modifying test fixtures.
- **Empirical Verification:** Always run existing tests, typechecks, and eval gates before reporting completion.
- **Mock Ledger Invariant (Gate L):** Any product code that stands in for real behavior (simulated responses, seeded or hardcoded data, demo-only keys or endpoints, offline stubs) gets a `MOCK(M-NNN)` comment marker and a matching entry in `MOCKS.md`, in the same commit. Remove markers and entry together. Never add a fallback that reports a failed call as a success. `sdcs verify --mocks` enforces this.

## 5. Mid-Shift Checkpoint Protocol ("prepare for compact")
When instructed to "prepare for compact", or when context window exhaustion nears prior to session compaction:
1. **Topology & Subsystem Audit:** Run `sdcs verify --topology` to verify that all imports comply with `wiring.yaml`. If new modules or packages were created during the shift, ensure they are declared in `wiring.yaml`.
2. **Flight Recorder Checkpoint:** Write an immutable checkpoint log to `sessions/YYYY-MM-DD_<topic>.md` capturing work completed, verification status, active blockers, and immediate post-compact next steps. Update `sessions/manifest.jsonl` via `sdcs session index`.
3. **Blackboard Pruning (`state.md`):** Aggressively prune and overwrite `state.md` strictly to <= 300 tokens containing only:
   - `## Current Objective`
   - `## Status & Gate Verification`
   - `## Immediate Next Action (Post-Compact)`
4. **Episodic Sweeps:**
   - Log any rejected approaches or failed experiments to `decisions.md`.
   - Synchronize `app_map.md` if files were created, moved, or deleted (`sdcs map --sync`).
   - Update `roadmap.md` [MEASURED] blocks if milestones or acceptance criteria were met.
5. **Readiness Signal:** Output a brief confirmation that all 7 pillars and the flight recorder are synchronized, and state: "Ready for compaction."

## 6. Close-Out Protocol (Mandatory)
Before completing your shift:
1. Prune and overwrite `state.md` with current verification status (<= 300 token budget via `sdcs verify --state`).
2. Update `roadmap.md` [MEASURED] blocks with real test telemetry.
3. If an attempted optimization or architecture failed, log it to `decisions.md`.
4. Update `app_map.md` and verify cartography matches disk via Gate M (`sdcs map --check` / `sdcs map --sync`).
5. Verify `wiring.yaml` matches codebase topology (`sdcs verify --topology`).
6. Emit an immutable handoff log to `sessions/YYYY-MM-DD_<topic>.md` and sync index (`sdcs session index`).
