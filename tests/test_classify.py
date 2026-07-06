"""Stage 2 classifier + catalog tests."""

from pathlib import Path

from asmplan.catalog import coarse_pitch_mm, parse_designation
from asmplan.classify import classify_assembly, classify_part
from asmplan.geometry import LoadedPart
from asmplan.loader import load_step
from asmplan.schema import PartClass

FIXTURES = Path(__file__).parent / "fixtures"


# ── catalog ──────────────────────────────────────────────────────────────────

def test_coarse_pitch_lookup():
    assert coarse_pitch_mm(6.0) == 1.0
    assert coarse_pitch_mm(8.0) == 1.25
    assert coarse_pitch_mm(99.0) is None


def test_parse_full_iso_designation():
    spec = parse_designation("ISO 4762 M6x20")
    assert spec.part_class == PartClass.SCREW
    assert spec.diameter_mm == 6.0
    assert spec.pitch_mm == 1.0
    assert spec.matched_standard and spec.matched_metric


def test_parse_hex_bolt_and_nut():
    assert parse_designation("ISO 4014 M10x40").part_class == PartClass.BOLT
    assert parse_designation("ISO 4032 M10 nut").part_class == PartClass.NUT


def test_parse_bare_metric_assumes_screw():
    spec = parse_designation("M4x12")
    assert spec.part_class == PartClass.SCREW
    assert spec.pitch_mm == 0.7


def test_parse_non_fastener_returns_none():
    assert parse_designation("base_plate") is None
    assert parse_designation("housing") is None
    assert parse_designation(None) is None


# ── classifier (with geometry) ───────────────────────────────────────────────

def test_screw_fixture_classified_with_axis_and_pitch():
    asm = load_step(FIXTURES / "plate_and_screw.step")
    result = classify_assembly(asm)
    screw = next(c for pid, c in result.items()
                 if asm.by_id(pid).name and "M6" in asm.by_id(pid).name)
    assert screw.part_class == PartClass.SCREW
    assert screw.pitch_mm == 1.0
    assert not screw.flagged_for_review
    # screw fixture runs along +Z -> axis should be ~ (0,0,1)
    assert screw.axis is not None
    assert abs(screw.axis[2]) > 0.9


def test_plate_is_generic():
    asm = load_step(FIXTURES / "plate_and_screw.step")
    result = classify_assembly(asm)
    plate = next(c for pid, c in result.items()
                 if asm.by_id(pid).name == "plate")
    assert plate.part_class == PartClass.GENERIC


def test_low_confidence_fastener_flagged():
    # "screw" keyword, no size -> no pitch -> must be flagged for review.
    part = LoadedPart(part_id="x", name="mounting screw", shape=None)
    c = classify_part(part)
    assert c.part_class == PartClass.SCREW
    assert c.flagged_for_review
