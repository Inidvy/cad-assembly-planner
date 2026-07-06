"""Stage 5/6 — Motion generation + Plan assembly.

Turn a SequenceResult (the stable semantic order + precedence) into a validated
Plan, attaching the ADVISORY motion primitives:

  * fasteners (screw/bolt with a known axis + pitch) -> Screw(turns = engagement
    length / pitch),
  * everything else -> Translate along its insertion direction.

Motion values are advisory approximations (see design: the metric layer is not
the frozen robot contract). Exact distance-to-contact is a later refinement.
"""

from __future__ import annotations

from asmplan.geometry import LoadedAssembly, Vec3
from asmplan.schema import (
    Plan,
    PartClass,
    PartIdentity,
    Screw,
    Step,
    Translate,
)
from asmplan.sequencer import SequenceResult


def _clean_vec(v: Vec3, tol: float = 1e-9) -> Vec3:
    """Snap floating-point noise (|x| < tol) to 0 so axes read cleanly."""
    return tuple(0.0 if abs(x) < tol else round(x, 6) for x in v)  # type: ignore[return-value]


def _projected_extent(bbox_size: Vec3, direction: Vec3) -> float:
    """Approximate how far a part spans along `direction` (mm)."""
    return sum(abs(direction[i]) * bbox_size[i] for i in range(3))


def build_plan(seq: SequenceResult, assembly: LoadedAssembly) -> Plan:
    size_of = {p.part_id: p.bbox_size for p in assembly.parts}

    parts = [
        PartIdentity(
            part_id=s.part_id,
            name=s.name,
            part_class=s.part_class,
            confidence=s.confidence,
            flagged_for_review=s.flagged_for_review,
        )
        for s in seq.steps
    ]

    steps: list[Step] = []
    for i, s in enumerate(seq.steps):
        label = s.name or s.part_id
        bbox = size_of.get(s.part_id, (0.0, 0.0, 0.0))

        motion = None
        subgoal = f"Place {label}."
        is_screw = s.part_class in (PartClass.SCREW, PartClass.BOLT)
        if is_screw and s.axis and s.pitch_mm:
            length = _projected_extent(bbox, s.axis)
            turns = round(length / s.pitch_mm, 1) if s.pitch_mm else 0.0
            # drive along the insertion direction (into the assembly)
            axis = s.axis if _dot(s.axis, s.insert_direction) >= 0 else _neg(s.axis)
            motion = Screw(axis=_clean_vec(axis), pitch_mm=s.pitch_mm, turns=turns)
            subgoal = f"Drive {label} along its axis ({turns:g} turns)."
        else:
            dist = round(_projected_extent(bbox, s.insert_direction) or 10.0, 2)
            motion = Translate(direction=_clean_vec(s.insert_direction), distance_mm=dist)
            subgoal = f"Place {label} (slide {dist:g} mm)."

        steps.append(
            Step(
                order_index=i,
                part_id=s.part_id,
                part_class=s.part_class,
                precedes=s.precedes,
                subgoal_text=subgoal,
                motion=motion,
            )
        )

    return Plan(source_unit=seq.source_unit, parts=parts, steps=steps)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _neg(a: Vec3) -> Vec3:
    return (-a[0], -a[1], -a[2])
