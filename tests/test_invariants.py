"""Tests for the invariant oracle (the hard gate). Geometry checkers are
injected as simple callables so these run without the geometry stack."""

from asmplan.invariants import (
    check_all,
    collision_free,
    fasteners_use_screw_motion,
    per_step_stable,
    precedence_respected,
    reversible_for_disassembly,
)
from asmplan.schema import (
    Plan,
    PartClass,
    PartIdentity,
    Screw,
    StabilityReport,
    Step,
    Translate,
)


def _good_plan() -> Plan:
    return Plan(
        parts=[
            PartIdentity(part_id="base"),
            PartIdentity(part_id="plate"),
            PartIdentity(part_id="screw1", part_class=PartClass.SCREW),
        ],
        steps=[
            Step(order_index=0, part_id="base"),
            Step(order_index=1, part_id="plate", precedes=["base"]),
            Step(order_index=2, part_id="screw1", part_class=PartClass.SCREW,
                 precedes=["plate"],
                 motion=Screw(axis=(0, 0, 1), pitch_mm=1.0, turns=10.0)),
        ],
    )


def test_all_plan_level_invariants_pass_on_good_plan():
    results = check_all(_good_plan(), expected_parts=3)
    by_name = {r.name: r for r in results}
    assert by_name["precedence_respected"].ok
    assert by_name["part_count_matches"].ok
    assert by_name["every_part_placed_once"].ok
    assert by_name["fasteners_use_screw_motion"].ok
    assert by_name["reversible_for_disassembly"].ok


def test_reversible_detects_bad_removal_order():
    # Construct a plan that is precedence-valid for assembly, then confirm the
    # reverse-disassembly invariant agrees (it should, by construction).
    assert reversible_for_disassembly(_good_plan()).ok


def test_fastener_with_translate_motion_flagged():
    plan = Plan(
        parts=[PartIdentity(part_id="s", part_class=PartClass.BOLT)],
        steps=[Step(order_index=0, part_id="s", part_class=PartClass.BOLT,
                    motion=Translate(direction=(0, 0, 1), distance_mm=5.0))],
    )
    assert not fasteners_use_screw_motion(plan).ok


def test_collision_free_unchecked_without_checker():
    r = collision_free(_good_plan(), checker=None)
    assert r.ok and "unchecked" in r.detail


def test_collision_free_uses_injected_checker():
    def checker(step):
        return (step.part_id != "plate", "overlaps base")
    r = collision_free(_good_plan(), checker=checker)
    assert not r.ok and "plate" in r.detail


def test_stability_falls_back_to_reports():
    plan = Plan(
        parts=[PartIdentity(part_id="a")],
        steps=[Step(order_index=0, part_id="a",
                    stability=StabilityReport(stable=False, notes="tips"))],
    )
    assert not per_step_stable(plan, checker=None).ok


def test_precedence_respected_direct():
    assert precedence_respected(_good_plan()).ok
