"""Lane C tests: plan.json I/O round-trip (validate on both ends) and the
human-instructions renderer."""

import pytest
from pydantic import ValidationError

from asmplan.emit import read_plan, render_instructions, write_plan
from asmplan.schema import (
    Plan,
    PartClass,
    PartIdentity,
    Screw,
    StabilityReport,
    Step,
    Translate,
)


def _plan() -> Plan:
    return Plan(
        parts=[
            PartIdentity(part_id="plate"),
            PartIdentity(part_id="screw1", name="M6x20", part_class=PartClass.SCREW),
        ],
        steps=[
            Step(order_index=0, part_id="plate", subgoal_text="Place the plate.",
                 motion=Translate(direction=(0, 0, -1), distance_mm=10.0)),
            Step(order_index=1, part_id="screw1", part_class=PartClass.SCREW,
                 precedes=["plate"], subgoal_text="Drive screw1 into the plate.",
                 motion=Screw(axis=(0, 0, 1), pitch_mm=1.0, turns=10.0),
                 stability=StabilityReport(stable=True)),
        ],
    )


def test_write_then_read_round_trips(tmp_path):
    p = write_plan(_plan(), tmp_path / "out" / "plan.json")
    assert p.exists()
    reloaded = read_plan(p)
    assert reloaded == _plan()


def test_read_rejects_malformed_plan(tmp_path):
    bad = tmp_path / "bad.json"
    # order_index 5 is non-contiguous -> must fail on read
    bad.write_text(
        '{"parts":[{"part_id":"a"}],"steps":[{"order_index":5,"part_id":"a"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        read_plan(bad)


def test_instructions_numbered_in_assembly_order():
    text = render_instructions(_plan())
    lines = [ln for ln in text.splitlines() if ln and ln[0].isdigit()]
    assert lines[0].startswith("1. Place the plate.")
    assert lines[1].startswith("2. Drive screw1 into the plate.")


def test_instructions_describe_motions():
    text = render_instructions(_plan())
    assert "slide 10 mm" in text
    assert "10 turns" in text
    assert "requires already-placed: plate" in text


def test_instructions_flag_instability():
    plan = Plan(
        parts=[PartIdentity(part_id="a")],
        steps=[Step(order_index=0, part_id="a",
                    stability=StabilityReport(stable=False, needs_fixture=True,
                                              notes="tips over"))],
    )
    text = render_instructions(plan)
    assert "⚠ stability: tips over" in text
    assert "needs a fixture/support here" in text
