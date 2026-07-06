"""Stage 4/5 sequencer + motion tests: precedence, fastener-last ordering,
screw motion, and the unsolvable-assembly diagnostic."""

from pathlib import Path

import pytest

from asmplan.classify import classify_assembly
from asmplan.loader import load_step
from asmplan.motion import build_plan
from asmplan.schema import PartClass, Screw
from asmplan.sequencer import SequencingError, sequence

FIXTURES = Path(__file__).parent / "fixtures"


def test_screw_is_assembled_last_after_plate():
    asm = load_step(FIXTURES / "plate_and_screw.step")
    seq = sequence(asm, classify_assembly(asm))
    order = [s.part_id for s in seq.steps]
    name = {p.part_id: p.name for p in asm.parts}
    screw_id = next(pid for pid, nm in name.items() if nm and "M6" in nm)
    plate_id = next(pid for pid, nm in name.items() if nm == "plate")
    # plate placed before screw; screw depends on plate
    assert order.index(plate_id) < order.index(screw_id)
    screw_step = next(s for s in seq.steps if s.part_id == screw_id)
    assert plate_id in screw_step.precedes


def test_screw_gets_screw_motion_with_turns():
    asm = load_step(FIXTURES / "plate_and_screw.step")
    plan = build_plan(sequence(asm, classify_assembly(asm)), asm)
    name = {p.part_id: p.name for p in asm.parts}
    screw_id = next(pid for pid, nm in name.items() if nm and "M6" in nm)
    step = next(s for s in plan.ordered_steps() if s.part_id == screw_id)
    assert isinstance(step.motion, Screw)
    assert step.motion.pitch_mm == 1.0
    assert step.motion.turns > 0


def test_stacked_precedence_chain():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    seq = sequence(asm, classify_assembly(asm))
    by_name = {p.name: p.part_id for p in asm.parts}
    steps = {s.part_id: s for s in seq.steps}
    # mid rests on base; top rests on mid
    assert by_name["base"] in steps[by_name["mid"]].precedes
    assert by_name["mid"] in steps[by_name["top"]].precedes


def test_trapped_cube_raises_diagnostic():
    asm = load_step(FIXTURES / "trapped_cube.step")
    with pytest.raises(SequencingError) as exc:
        sequence(asm, classify_assembly(asm))
    diag = exc.value.diagnostic
    assert diag["stuck_parts"]                      # names the stuck parts
    assert set(diag["stuck_parts"]) == {p.part_id for p in asm.parts}
    assert diag["blocking"]                         # and who blocks each direction
