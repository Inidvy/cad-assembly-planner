# CAD/STEP → Robot Assembly Planner — Design (v1)

Date: 2026-07-06
Status: Design approved in brainstorming + eng review; awaiting final spec sign-off.

## Goal

Read a STEP assembly file (full assembly, every part a separate solid in its
final assembled position, product structure intact) and produce an ordered
**assembly plan**: what goes in, in what order, with per-step motions and
human-readable instructions, plus a 3D step-by-step animation to validate it.

The plan is designed so a later phase (simulated robot, then a real robot
driven by a VLA/VLM policy) can consume it. This project is the software
"brain" only — no robot hardware.

## Scope decisions (from eng review)

- **Fastener ID** by STEP part-name/metadata + cylindrical primitive + head
  geometry matched to a DIN/ISO catalog; pitch looked up, not measured.
  Geometric thread detection is **deferred to v2**.
- **v1 includes physics**: subassembly (grouped-part) removal and
  physics-based stability validation (gravity, fixturing, press/snap-fit
  awareness) are IN scope. This is a deliberately ambitious v1 that partly
  bridges into the simulation phase.
- **plan.json semantic core is the stable contract**; metric motions are an
  advisory layer (a VLA needs ordering/precedence/identity/subgoals, not
  frozen motion primitives).

### NOT in scope
- Geometric thread detection (v2 fallback).
- Grasp/gripper planning, approach-retract, re-grasp, part-feeder poses (robot
  phase).
- Mating-pose inference (parts are given in final position).
- General ML part classification, e.g. PointNet/MCB (v2).
- Full VLA action schema (plan.json stops at semantic + advisory-motion level).

## Architecture

```
STEP file
  │
  ▼
[1] Loader
     - parse assembly, product structure, per-instance placement matrices
     - read STEP length unit; normalize ALL geometry to mm; FAIL LOUD if no unit
     - validation gate: assert >=2 separable solids; warn on missing structure;
       print inventory; hard-fail on fused/flat input
  │  parts[] (solid, transform, name/metadata), source_unit
  ▼
[2] Classifier
     - fastener ID by name/metadata + cylinder primitive + head geometry
       -> DIN/ISO catalog match; pitch looked up
     - CONFIDENCE-SCORED; low-confidence matches flagged for review, never a
       silent guess
     - compute fastener axis; non-fasteners tagged generic body
  │  parts[] + {class, confidence, axis, pitch}
  ▼
[3] Contact / DFA
     - contact via CLEARANCE/epsilon band (does moving by e cause interference
       within tolerance), NOT exact touch -> catches clearance-fit blockers
     - broad-phase (AABB / spatial grid) -> narrow-phase exact OCCT only on
       candidate pairs; cache contact graph
     - removal directions per part = {6 global axes} U {face normals / cylinder
       axes}; fasteners use their own screw axis
     - SUBASSEMBLY removal: search for grouped-part cut-sets when no single
       part is free
  │  contact graph, per-part/-group removal directions
  ▼
[4] Sequencer
     - assembly-by-disassembly: plan disassembly, reverse for assembly order
     - precedence constraints (screw after the part it fastens)
     - on no valid order: emit DIAGNOSTIC (blocked parts, tried directions,
       mutual-block cycles) — never a blank error
  │  candidate assembly order + precedence graph
  ▼
[5] Physics / Stability Validator            (NEW — in scope via review)
     - re-validate the reversed sequence is physically assemblable
     - per-step stability under gravity; fixturing needs; press/snap-fit force
       awareness; flag unstable steps
     - engine: PyBullet/MuJoCo-class, or static stability analysis
  │  validated order + per-step stability report
  ▼
[6] Motion gen                               (ADVISORY layer)
     - Translate(vector, distance-to-contact)
     - Screw(axis, turns = insertion_depth / pitch)
  │  motions[]
  ▼
[7] Emit
     - plan.json = versioned Pydantic schema, validated on write AND read
     - STABLE CORE: ordering, precedence graph, part identity, per-step subgoal
       text
     - ADVISORY: metric motion primitives (tagged union), stability report
     - human-readable instructions + 3D animation are pure RENDERERS of the
       validated plan.json
```

Each stage is an isolated module with a typed contract (imports the shared
Pydantic models). Independently testable against small fixtures.

## Data contract: plan.json

Versioned Pydantic model, `schema_version` field. Two layers:

- **Stable semantic core** (the contract downstream/VLA depends on):
  `steps[]` with `{order_index, part_id, part_class, precedes[], subgoal_text}`,
  plus the precedence graph and part-identity table.
- **Advisory layer** (best-effort, not a frozen API): motion primitives
  (`Translate | Screw`), per-step stability report, source_unit metadata.

Validate on write (producer) and on read (consumer).

## Tech stack

- Python 3.x
- **pythonOCC (OpenCASCADE)** — geometry core: STEP load, product structure,
  booleans/interference.
- **Pydantic** — plan.json schema + validation.
- **PyBullet or MuJoCo** — Stage 5 stability validation.
- **build123d / CadQuery** — author synthetic test fixtures.
- Viewer: tessellate B-rep → three.js (web) or pyrender for the animation
  (decoupled from the exact geometry engine).

## Testing

- **Synthetic fixtures** built programmatically (build123d/CadQuery):
  plate+screw, stacked blocks, bracket+2 bolts, a clearance-fit case, an
  over-constrained (no-order) case, a stability/gravity case, and per-unit
  (mm/inch/meter) loader cases.
- **Oracle = invariants** (hard, blocking), not exact reproduction:
  precedence respected, every motion collision-free, sequence reverses cleanly,
  part count matches, fasteners seated, per-step stability holds.
- **Golden plan.json** kept as a soft, non-blocking snapshot for eyeballing
  diffs — allowed to change on legit tie-breaks/float noise.
- Framework: pytest.

### Coverage targets (all P1 for implementation)
Loader (structure, unit×3, guard), Classifier (named/unnamed/non-fastener,
axis+pitch, low-confidence flag), Contact (graph, clearance-band, global+local
dirs, subassembly cut-set, blocked part), Sequencer (order, precedence,
diagnostic-on-failure), Physics (per-step stability, unstable flag), Motion
(translate vector+mm, screw turns=depth/pitch), Emit (schema round-trip, human
text, animation smoke).

## Build order (parallelizable)

1. **Lane 0 (first):** plan.json Pydantic schema — everything depends on it.
2. Parallel: **Lane A** Loader · **Lane B** Classifier+catalog · **Lane C**
   Emit renderers (human text + animation).
3. Merge A+B, then **Lane D** (sequential, shared geometry/graph/solver):
   Stage 3 Contact/DFA → Stage 4 Sequencer → Stage 5 Physics Validator →
   Stage 6 Motion gen.

Conflict flag: Lanes A and D both touch the geometry module — merge A before
starting D.

## Open questions / risks carried forward

- **v1 correctness falsifiability** (outside-voice finding 8): mitigated by the
  Stage 5 physics validator (v1 can now self-check assemblability), but
  consider closing the loop on one real assembly in sim as an early milestone.
- Subassembly cut-set search is NP-hard in general; bound the search and log
  when a cap is hit (no silent truncation).
- Nested-assembly instance transform frames are a real unit/placement risk —
  test with a nested fixture, not just flat.
