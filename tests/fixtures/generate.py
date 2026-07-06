"""Generate synthetic STEP fixtures with build123d.

Each fixture is a known assembly whose correct plan we understand by
construction. Run this module to (re)generate the .step files next to it:

    python tests/fixtures/generate.py

Parts are separate, labeled solids in a compound so the loader sees N distinct
named bodies — mirroring how a real CAD assembly export looks.
"""

from __future__ import annotations

from pathlib import Path

from build123d import Box, Cylinder, Compound, Pos

HERE = Path(__file__).parent


def _export(compound: Compound, name: str) -> Path:
    from build123d import export_step

    path = HERE / f"{name}.step"
    export_step(compound, str(path))
    return path


def stacked_blocks() -> Compound:
    """Three boxes stacked in +Z. Correct assembly order: bottom -> top."""
    base = Box(30, 30, 10);           base.label = "base"
    mid = Pos(0, 0, 10) * Box(24, 24, 10); mid.label = "mid"
    top = Pos(0, 0, 20) * Box(18, 18, 10); top.label = "top"
    asm = Compound(children=[base, mid, top]); asm.label = "stacked_blocks"
    return asm


def plate_and_screw() -> Compound:
    """A plate with a screw through it. Screw (named, catalog-matchable) sits in
    the plate's hole; correct order: plate first, then screw."""
    plate = Box(40, 40, 8);  plate.label = "plate"
    # A simple screw proxy: shaft + head FUSED into one solid (a screw is a
    # single body), along +Z, seated in the plate.
    shaft = Pos(0, 0, 4) * Cylinder(radius=3, height=16)
    head = Pos(0, 0, 13) * Cylinder(radius=5, height=3)
    screw = shaft + head          # fuse -> single solid
    screw.label = "ISO 4762 M6x20"
    asm = Compound(children=[plate, screw]); asm.label = "plate_and_screw"
    return asm


FIXTURES = {
    "stacked_blocks": stacked_blocks,
    "plate_and_screw": plate_and_screw,
}


def generate_all() -> list[Path]:
    return [_export(fn(), name) for name, fn in FIXTURES.items()]


if __name__ == "__main__":
    for p in generate_all():
        print("wrote", p)
