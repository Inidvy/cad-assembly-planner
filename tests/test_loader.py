"""Stage 1 loader tests against real generated STEP fixtures."""

from pathlib import Path

import pytest

from asmplan.loader import AssemblyLoadError, load_step

FIXTURES = Path(__file__).parent / "fixtures"


def test_stacked_blocks_loads_three_named_parts():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    assert asm.source_unit == "mm"
    assert len(asm.parts) == 3
    names = {p.name for p in asm.parts}
    assert names == {"base", "mid", "top"}


def test_centroids_ordered_in_z():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    by_name = {p.name: p for p in asm.parts}
    # base sits lowest, top highest (centroid z increases up the stack)
    assert by_name["base"].centroid[2] < by_name["mid"].centroid[2]
    assert by_name["mid"].centroid[2] < by_name["top"].centroid[2]


def test_bbox_size_is_positive():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    for p in asm.parts:
        sx, sy, sz = p.bbox_size
        assert sx > 0 and sy > 0 and sz > 0


def test_plate_and_screw_names_survive():
    asm = load_step(FIXTURES / "plate_and_screw.step")
    names = {p.name for p in asm.parts}
    assert "plate" in names
    assert any("M6" in (n or "") for n in names)  # catalog-matchable screw name


def test_missing_file_raises():
    with pytest.raises(AssemblyLoadError, match="not found"):
        load_step(FIXTURES / "does_not_exist.step")


def test_single_solid_fails_loud(tmp_path):
    # A single box is NOT an assembly — the >=2-solid guard must fire.
    from build123d import Box, export_step

    solo = tmp_path / "solo.step"
    export_step(Box(10, 10, 10), str(solo))
    with pytest.raises(AssemblyLoadError, match=">=2 separable solids"):
        load_step(solo)
