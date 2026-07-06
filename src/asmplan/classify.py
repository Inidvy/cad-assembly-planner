"""Stage 2 — Classifier.

Identify fasteners from part NAME + catalog, sanity-checked against geometry,
and compute each fastener's insertion axis. Confidence-scored: a low-confidence
or pitch-less fastener is FLAGGED for review, never silently trusted.

    name ──parse_designation──▶ FastenerSpec (class, diameter, pitch)
    shape ──principal inertia──▶ axis (for screws/bolts)
                    │
                    ▼
             Classification(part_class, confidence, flagged, axis, pitch)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from asmplan.catalog import parse_designation
from asmplan.geometry import LoadedAssembly, LoadedPart, Vec3
from asmplan.schema import PartClass

# A fastener match below this confidence, or missing its pitch, gets flagged.
_FLAG_CONFIDENCE = 0.75


@dataclass
class Classification:
    part_class: PartClass
    confidence: float
    flagged_for_review: bool = False
    axis: Optional[Vec3] = None       # unit insertion axis (screws/bolts)
    pitch_mm: Optional[float] = None


def _principal_long_axis(shape) -> Optional[Vec3]:
    """Unit vector along the part's axis of least inertia (the long/symmetry
    axis of an elongated body like a screw). None if it can't be computed."""
    try:
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps

        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        pp = props.PrincipalProperties()
        ix, iy, iz = pp.Moments()
        axes = [
            (ix, pp.FirstAxisOfInertia()),
            (iy, pp.SecondAxisOfInertia()),
            (iz, pp.ThirdAxisOfInertia()),
        ]
        _, axis = min(axes, key=lambda t: t[0])  # least moment = long axis
        v = (axis.X(), axis.Y(), axis.Z())
        n = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5
        if n == 0:
            return None
        # Orient consistently: point the axis toward +Z hemisphere for stability.
        v = (v[0] / n, v[1] / n, v[2] / n)
        if v[2] < 0:
            v = (-v[0], -v[1], -v[2])
        return v
    except Exception:
        return None


def _confidence(spec) -> float:
    """Score how sure we are of a fastener identity from what the name gave us."""
    if spec.matched_standard and spec.matched_metric:
        return 0.97
    if spec.matched_keyword and spec.matched_metric:
        return 0.95
    if spec.matched_metric:            # bare "M6x20", assumed screw
        return 0.80
    if spec.matched_keyword:           # "screw" with no size -> no pitch
        return 0.60
    return 0.50


def classify_part(part: LoadedPart) -> Classification:
    spec = parse_designation(part.name)
    if spec is None:
        # Not a fastener — a generic body. High confidence in "not a fastener".
        return Classification(part_class=PartClass.GENERIC, confidence=0.9)

    conf = _confidence(spec)
    axis = None
    if spec.part_class in (PartClass.SCREW, PartClass.BOLT):
        axis = _principal_long_axis(part.shape)

    needs_pitch = spec.part_class in (PartClass.SCREW, PartClass.BOLT, PartClass.NUT)
    flagged = conf < _FLAG_CONFIDENCE or (needs_pitch and spec.pitch_mm is None)

    return Classification(
        part_class=spec.part_class,
        confidence=conf,
        flagged_for_review=flagged,
        axis=axis,
        pitch_mm=spec.pitch_mm,
    )


def classify_assembly(assembly: LoadedAssembly) -> dict[str, Classification]:
    return {p.part_id: classify_part(p) for p in assembly.parts}
