"""Gate A/B — the full pipeline must produce an invariant-passing plan.

Loader -> Classifier -> Sequencer(DFA) -> Motion/Plan -> Emit, validated by the
invariant oracle (not exact golden match).
"""

from pathlib import Path

from asmplan.classify import classify_assembly
from asmplan.cli import run
from asmplan.emit import read_plan
from asmplan.invariants import check_all
from asmplan.loader import load_step
from asmplan.motion import build_plan
from asmplan.sequencer import sequence

FIXTURES = Path(__file__).parent / "fixtures"


def _plan_for(name: str):
    asm = load_step(FIXTURES / f"{name}.step")
    cls = classify_assembly(asm)
    return build_plan(sequence(asm, cls), asm), asm


def _plan_invariants_pass(plan, expected_parts):
    results = check_all(plan, expected_parts=expected_parts)
    plan_level = [r for r in results
                  if r.name not in ("collision_free", "per_step_stable")]
    failed = [r for r in plan_level if not r.ok]
    assert not failed, f"invariant failures: {[(r.name, r.detail) for r in failed]}"


def test_stacked_blocks_plan_passes_invariants():
    plan, _ = _plan_for("stacked_blocks")
    _plan_invariants_pass(plan, expected_parts=3)


def test_stacked_blocks_order_is_bottom_up():
    plan, asm = _plan_for("stacked_blocks")
    name = {p.part_id: p.name for p in asm.parts}
    assert [name[s.part_id] for s in plan.ordered_steps()] == ["base", "mid", "top"]


def test_plate_and_screw_plan_passes_invariants():
    plan, _ = _plan_for("plate_and_screw")
    _plan_invariants_pass(plan, expected_parts=2)


def test_cli_run_writes_artifacts(tmp_path):
    plan_path = run(str(FIXTURES / "stacked_blocks.step"), str(tmp_path / "out"))
    assert plan_path.exists()
    plan = read_plan(plan_path)              # re-validates on read
    assert len(plan.steps) == 3
    assert (tmp_path / "out" / "instructions.txt").read_text(encoding="utf-8")
