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
    # Plate (z -4..4) with a through clearance hole (radius 3.5) for the screw.
    plate = Box(40, 40, 8) - Cylinder(radius=3.5, height=20)
    plate.label = "plate"
    # Screw = shaft (through the hole, z -6..4) + head (resting on plate top,
    # z 4..7) FUSED into one solid. Head (r=5) > hole (r=3.5) so it seats on top;
    # shaft (r=3) clears the hole. Removable straight up; plate slides down off it.
    shaft = Pos(0, 0, -1) * Cylinder(radius=3, height=10)
    head = Pos(0, 0, 5.5) * Cylinder(radius=5, height=3)
    screw = shaft + head          # fuse -> single solid
    screw.label = "ISO 4762 M6x20"
    asm = Compound(children=[plate, screw]); asm.label = "plate_and_screw"
    return asm


def trapped_cube() -> Compound:
    """A cube sealed inside a hollow box (internal cavity, no opening). The cube
    cannot leave in ANY direction and the shell cannot move off it -> the
    sequencer must report an unsolvable assembly, not a blank error."""
    shell = Box(20, 20, 20) - Box(10, 10, 10)   # sealed void, 0.5mm clearance
    shell.label = "shell"
    cube = Box(9, 9, 9)
    cube.label = "trapped_cube"
    asm = Compound(children=[shell, cube]); asm.label = "trapped_cube"
    return asm


FIXTURES = {
    "stacked_blocks": stacked_blocks,
    "plate_and_screw": plate_and_screw,
    "trapped_cube": trapped_cube,
}


def generate_all() -> list[Path]:
    return [_export(fn(), name) for name, fn in FIXTURES.items()]


if __name__ == "__main__":
    for p in generate_all():
        print("wrote", p)
