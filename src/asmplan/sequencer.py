"""Stage 4 — Sequencer (assembly by disassembly).

Repeatedly remove a currently-free part (using the Stage-3 blocking graph) until
the assembly is empty; the reverse of that removal order is a valid assembly
order. Precedence edges come from contacts: of two touching parts, the one
assembled earlier must be placed first.

On failure (a set of mutually-blocking parts with no free member) we raise a
SequencingError carrying a DIAGNOSTIC — which parts are stuck and who blocks
them — never a blank "no order".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from asmplan.classify import Classification
from asmplan.contact import ContactGraph, build_contact_graph
from asmplan.geometry import LoadedAssembly, Vec3
from asmplan.schema import PartClass


@dataclass
class AssemblyStep:
    part_id: str
    name: Optional[str]
    part_class: PartClass
    confidence: float
    flagged_for_review: bool
    precedes: list[str]          # part_ids that must already be assembled
    insert_direction: Vec3       # unit vector to insert along (= -removal dir)
    axis: Optional[Vec3] = None  # fastener insertion axis, if any
    pitch_mm: Optional[float] = None


@dataclass
class SequenceResult:
    steps: list[AssemblyStep]    # in assembly order (index 0 first)
    source_unit: str
    contact_graph: ContactGraph = field(repr=False, default=None)


class SequencingError(ValueError):
    def __init__(self, message: str, diagnostic: dict):
        super().__init__(message)
        self.diagnostic = diagnostic


def _select_to_remove(candidates, assembly, classifications) -> str:
    """Pick which free part to remove next in disassembly. Prefer fasteners
    (so they end up assembled LAST), then the outermost (highest centroid),
    then part_id for determinism."""
    centroid_z = {p.part_id: p.centroid[2] for p in assembly.parts}

    def key(pid: str):
        is_fast = bool(classifications and classifications.get(pid)
                       and classifications[pid].part_class.is_fastener)
        return (is_fast, centroid_z.get(pid, 0.0), pid)

    return max(candidates, key=key)


def sequence(
    assembly: LoadedAssembly,
    classifications: Optional[dict[str, Classification]] = None,
) -> SequenceResult:
    graph = build_contact_graph(assembly, classifications)
    present = {p.part_id for p in assembly.parts}

    removal_order: list[str] = []
    removal_dir: dict[str, Vec3] = {}

    while present:
        candidates = [pid for pid in present if graph.is_removable(pid, present)]
        if not candidates:
            # Mutual block: report each stuck part and who blocks it per direction.
            stuck = {}
            for pid in sorted(present):
                blockers_by_dir = {
                    str(tuple(round(x, 2) for x in d)): sorted(b & (present - {pid}))
                    for d, b in graph.blocking[pid]
                }
                stuck[pid] = blockers_by_dir
            raise SequencingError(
                f"no valid disassembly order: {len(present)} parts mutually block "
                f"({', '.join(sorted(present))})",
                diagnostic={"stuck_parts": sorted(present), "blocking": stuck},
            )
        chosen = _select_to_remove(candidates, assembly, classifications)
        removal_dir[chosen] = graph.free_direction(chosen, present)
        removal_order.append(chosen)
        present.discard(chosen)

    # Assembly order = reverse of removal.
    asm_order = list(reversed(removal_order))
    order_index = {pid: i for i, pid in enumerate(asm_order)}

    # Precedence from contacts: earlier-assembled neighbour precedes the later.
    part_by_id = {p.part_id: p for p in assembly.parts}
    steps: list[AssemblyStep] = []
    for pid in asm_order:
        precedes = []
        for other in asm_order:
            if other == pid:
                continue
            if order_index[other] < order_index[pid] and graph.in_contact(pid, other):
                precedes.append(other)

        cls = classifications.get(pid) if classifications else None
        # Insertion direction is the reverse of the direction it was removed.
        rem = removal_dir[pid]
        insert = (-rem[0], -rem[1], -rem[2])
        steps.append(
            AssemblyStep(
                part_id=pid,
                name=part_by_id[pid].name,
                part_class=cls.part_class if cls else PartClass.GENERIC,
                confidence=cls.confidence if cls else 1.0,
                flagged_for_review=cls.flagged_for_review if cls else False,
                precedes=precedes,
                insert_direction=insert,
                axis=cls.axis if cls else None,
                pitch_mm=cls.pitch_mm if cls else None,
            )
        )

    return SequenceResult(steps=steps, source_unit=assembly.source_unit,
                          contact_graph=graph)
