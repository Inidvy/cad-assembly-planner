"""Stage 4 — Sequencer.

NOTE: this module currently holds only the Milestone-A THIN-SLICE sequencer
(`sequence_by_z`) — a trivial global-+Z, bottom-up ordering that is correct for
axis-aligned stacked assemblies and exists to prove the end-to-end loop. The
real contact-graph-driven sequencing (disassembly->reverse, precedence from the
DFA stage, diagnostic-on-failure, subassembly search) lands in P4/P6 and will
supersede this for general assemblies.
"""

from __future__ import annotations

from asmplan.geometry import LoadedAssembly
from asmplan.schema import Plan, PartClass, PartIdentity, Step, Translate

# Nominal top-down approach distance (mm). Real distance-to-contact is computed
# by the P7 motion-generation stage from the contact geometry.
_NOMINAL_APPROACH_MM = 20.0


def sequence_by_z(assembly: LoadedAssembly) -> Plan:
    """Order parts bottom-up by centroid Z and emit a validated Plan.

    Encodes a simple precedence chain (each part requires the one below), which
    is exactly the stacking constraint for a vertical assembly.
    """
    ordered = sorted(assembly.parts, key=lambda p: p.centroid[2])

    parts = [PartIdentity(part_id=p.part_id, name=p.name) for p in ordered]
    steps: list[Step] = []
    prev_id: str | None = None
    for i, p in enumerate(ordered):
        label = p.name or p.part_id
        steps.append(
            Step(
                order_index=i,
                part_id=p.part_id,
                part_class=PartClass.GENERIC,
                precedes=[prev_id] if prev_id else [],
                subgoal_text=f"Place {label}.",
                motion=Translate(direction=(0.0, 0.0, -1.0),
                                 distance_mm=_NOMINAL_APPROACH_MM),
            )
        )
        prev_id = p.part_id

    return Plan(source_unit=assembly.source_unit, parts=parts, steps=steps)
