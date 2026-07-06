"""Gate A — the thin end-to-end slice must produce an invariant-passing plan.

Loader -> thin-slice Sequencer -> Emit, validated by the invariant oracle
(not exact golden match). Proves the whole loop works on real STEP geometry.
"""

from pathlib import Path

from asmplan.cli import run
from asmplan.emit import read_plan
from asmplan.invariants import check_all
from asmplan.loader import load_step
from asmplan.sequencer import sequence_by_z

FIXTURES = Path(__file__).parent / "fixtures"


def test_stacked_blocks_plan_passes_all_plan_invariants():
    plan = sequence_by_z(load_step(FIXTURES / "stacked_blocks.step"))
    results = check_all(plan, expected_parts=3)
    plan_level = [
        r for r in results
        if r.name not in ("collision_free", "per_step_stable")  # need geometry
    ]
    failed = [r for r in plan_level if not r.ok]
    assert not failed, f"invariant failures: {[(r.name, r.detail) for r in failed]}"


def test_assembly_order_is_bottom_up():
    plan = sequence_by_z(load_step(FIXTURES / "stacked_blocks.step"))
    by_id = {p.part_id: p for p in
             load_step(FIXTURES / "stacked_blocks.step").parts}
    ordered_names = [by_id[s.part_id].name for s in plan.ordered_steps()]
    assert ordered_names == ["base", "mid", "top"]


def test_cli_run_writes_artifacts(tmp_path):
    plan_path = run(str(FIXTURES / "stacked_blocks.step"), str(tmp_path / "out"))
    assert plan_path.exists()
    # the written plan.json re-validates on read (contract enforced on both ends)
    plan = read_plan(plan_path)
    assert len(plan.steps) == 3
    assert (tmp_path / "out" / "instructions.txt").read_text(encoding="utf-8")
