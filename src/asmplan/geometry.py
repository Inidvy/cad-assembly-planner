"""Geometry domain types shared by the pipeline's middle stages.

These wrap OCP (OpenCASCADE) shapes with the derived quantities the planner
needs (centroid, bounding box) so downstream stages don't each re-derive them.
Kept separate from schema.py: schema.py is the emit CONTRACT, this is internal
geometry state that never leaves the process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Vec3 = tuple[float, float, float]


@dataclass
class LoadedPart:
    part_id: str            # stable id assigned by the loader (e.g. "p0")
    name: str | None        # STEP part name, if any (drives classification)
    shape: Any = field(repr=False)   # OCP TopoDS_Shape (opaque here)
    centroid: Vec3 = (0.0, 0.0, 0.0)     # mm
    bbox_min: Vec3 = (0.0, 0.0, 0.0)     # mm
    bbox_max: Vec3 = (0.0, 0.0, 0.0)     # mm

    @property
    def bbox_size(self) -> Vec3:
        return tuple(hi - lo for lo, hi in zip(self.bbox_min, self.bbox_max))  # type: ignore[return-value]


@dataclass
class LoadedAssembly:
    parts: list[LoadedPart]
    source_unit: str        # unit the geometry was normalized FROM/TO (mm)

    def by_id(self, part_id: str) -> LoadedPart:
        for p in self.parts:
            if p.part_id == part_id:
                return p
        raise KeyError(part_id)
