"""Guided-disassembly validator tests: it must accept collision-free motions,
catch motions that sweep through a part, and support reposition-then-remove."""

from pathlib import Path

import pytest

from asmplan.guided import GRotate, GTranslate, GuidedOp, validate
from asmplan.loader import load_step

FIXTURES = Path(__file__).parent / "fixtures"


def _ids(asm):
    return {p.name: p.part_id for p in asm.parts}


def test_lifting_top_straight_up_is_valid():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    n = _ids(asm)
    res = validate(asm, [GuidedOp(n["top"], [GTranslate((0, 0, 1), 40)])])
    assert res.ok, res.collisions
    assert res.removals[0][0] == n["top"]


def test_pushing_mid_down_into_base_collides():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    n = _ids(asm)
    res = validate(asm, [GuidedOp(n["mid"], [GTranslate((0, 0, -1), 8)])])
    assert not res.ok
    assert any(c.other == n["base"] for c in res.collisions)


def test_full_stack_disassembly_top_down_is_valid():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    n = _ids(asm)
    ops = [
        GuidedOp(n["top"], [GTranslate((0, 0, 1), 40)]),
        GuidedOp(n["mid"], [GTranslate((0, 0, 1), 40)]),
        GuidedOp(n["base"], [GTranslate((0, 0, 1), 40)]),
    ]
    res = validate(asm, ops)
    assert res.ok, res.collisions
    assert [r[0] for r in res.removals] == [n["top"], n["mid"], n["base"]]


def test_motion_sweeping_through_a_part_is_caught_midpath():
    # translate top DOWNWARD far enough to pass through mid: collision recorded
    # at an intermediate fraction, not just the endpoint.
    asm = load_step(FIXTURES / "stacked_blocks.step")
    n = _ids(asm)
    res = validate(asm, [GuidedOp(n["top"], [GTranslate((0, 0, -1), 15)])])
    assert not res.ok
    assert any(0.0 < c.fraction < 1.0 for c in res.collisions)


def test_reposition_then_remove_tracks_pose():
    # rotate top a few degrees (reposition, stays), then lift it out.
    asm = load_step(FIXTURES / "stacked_blocks.step")
    n = _ids(asm)
    top = asm.by_id(n["top"])
    ops = [
        GuidedOp(n["top"], [GRotate((0, 0, 1), top.centroid, 10)], removes=False),
        GuidedOp(n["top"], [GTranslate((0, 0, 1), 40)], removes=True),
    ]
    res = validate(asm, ops)
    assert res.ok, res.collisions
    # only one removal recorded (the second op)
    assert [r[0] for r in res.removals] == [n["top"]]


def test_unknown_or_double_remove_raises():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    n = _ids(asm)
    with pytest.raises(ValueError, match="already removed"):
        validate(asm, [
            GuidedOp(n["top"], [GTranslate((0, 0, 1), 40)]),
            GuidedOp(n["top"], [GTranslate((0, 0, 1), 40)]),
        ])
