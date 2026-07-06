"""P1 schema tests: round-trip, discriminated motion union, and the cross-field
validators that make plan.json a real contract (not just a dict)."""

import json

import pytest
from pydantic import ValidationError

from asmplan.schema import (
    SCHEMA_VERSION,
    Plan,
    PartClass,
    PartIdentity,
    Screw,
    StabilityReport,
    Step,
    Translate,
)


def _plate_and_screw() -> Plan:
    """Plate goes in first, then the screw that fastens it (screw precedes plate)."""
    return Plan(
        source_unit="mm",
        parts=[
            PartIdentity(part_id="plate", part_class=PartClass.GENERIC),
            PartIdentity(
                part_id="screw1", name="ISO 4762 M6x20", part_class=PartClass.SCREW,
                confidence=0.95,
            ),
        ],
        steps=[
            Step(
                order_index=0, part_id="plate", part_class=PartClass.GENERIC,
                subgoal_text="Place the plate.",
                motion=Translate(direction=(0, 0, -1), distance_mm=10.0),
            ),
            Step(
                order_index=1, part_id="screw1", part_class=PartClass.SCREW,
                precedes=["plate"], subgoal_text="Drive screw1 into the plate.",
                motion=Screw(axis=(0, 0, 1), pitch_mm=1.0, turns=10.0),
                stability=StabilityReport(stable=True),
            ),
        ],
    )


def test_valid_plan_constructs():
    plan = _plate_and_screw()
    assert plan.schema_version == SCHEMA_VERSION
    assert [s.part_id for s in plan.ordered_steps()] == ["plate", "screw1"]


def test_round_trip_json_preserves_everything():
    plan = _plate_and_screw()
    dumped = plan.model_dump_json()
    reloaded = Plan.model_validate_json(dumped)
    assert reloaded == plan
    # advisory motion union re-hydrates to the correct concrete type
    assert isinstance(reloaded.ordered_steps()[1].motion, Screw)
    assert isinstance(reloaded.ordered_steps()[0].motion, Translate)


def test_motion_union_discriminates_on_kind():
    raw = json.loads(_plate_and_screw().model_dump_json())
    assert raw["steps"][1]["motion"]["kind"] == "screw"
    assert raw["steps"][0]["motion"]["kind"] == "translate"


def test_screw_turns_match_depth_over_pitch():
    # 10mm insertion at 1mm pitch = 10 turns (documents the motion.py contract)
    s = Screw(axis=(0, 0, 1), pitch_mm=1.0, turns=10.0)
    assert s.turns == pytest.approx(10.0)


def test_negative_distance_rejected():
    with pytest.raises(ValidationError):
        Translate(direction=(0, 0, 1), distance_mm=-5.0)


def test_zero_pitch_rejected():
    with pytest.raises(ValidationError):
        Screw(axis=(0, 0, 1), pitch_mm=0.0, turns=1.0)


def test_duplicate_part_id_rejected():
    with pytest.raises(ValidationError, match="duplicate part_id"):
        Plan(
            parts=[PartIdentity(part_id="a"), PartIdentity(part_id="a")],
            steps=[Step(order_index=0, part_id="a")],
        )


def test_non_contiguous_order_index_rejected():
    with pytest.raises(ValidationError, match="contiguous"):
        Plan(
            parts=[PartIdentity(part_id="a"), PartIdentity(part_id="b")],
            steps=[
                Step(order_index=0, part_id="a"),
                Step(order_index=2, part_id="b"),
            ],
        )


def test_step_referencing_unknown_part_rejected():
    with pytest.raises(ValidationError, match="unknown part_id"):
        Plan(
            parts=[PartIdentity(part_id="a")],
            steps=[Step(order_index=0, part_id="ghost")],
        )


def test_unknown_precedence_target_rejected():
    with pytest.raises(ValidationError, match="unknown part_id"):
        Plan(
            parts=[PartIdentity(part_id="a")],
            steps=[Step(order_index=0, part_id="a", precedes=["ghost"])],
        )


def test_precedence_ordering_enforced():
    # screw precedes plate but is scheduled BEFORE it -> invalid
    with pytest.raises(ValidationError, match="precedence violated"):
        Plan(
            parts=[
                PartIdentity(part_id="plate"),
                PartIdentity(part_id="screw1", part_class=PartClass.SCREW),
            ],
            steps=[
                Step(order_index=0, part_id="screw1", precedes=["plate"]),
                Step(order_index=1, part_id="plate"),
            ],
        )


def test_part_appearing_twice_in_steps_rejected():
    with pytest.raises(ValidationError, match="more than one step"):
        Plan(
            parts=[PartIdentity(part_id="a")],
            steps=[
                Step(order_index=0, part_id="a"),
                Step(order_index=1, part_id="a"),
            ],
        )


def test_fastener_class_helper():
    assert PartClass.SCREW.is_fastener
    assert PartClass.NUT.is_fastener
    assert not PartClass.GENERIC.is_fastener
