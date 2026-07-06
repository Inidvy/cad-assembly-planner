"""Stage 3 — Contact / Disassembly-Freedom Analysis (DFA).

Build, for a static assembly, the directional blocking graph the sequencer needs:

  * which parts are in CONTACT,
  * for each part, along which candidate DIRECTIONS it is free to move, and
    which other parts block each direction.

Method (see design + eng review):
  * Candidate directions per part = 6 global axes ∪ the part's own principal
    axes (fasteners' insertion axis is one of these).
  * BROAD phase: AABB overlap after a step cull — skip far pairs cheaply.
  * NARROW phase: translate the part a small step along d and measure the
    OVERLAP VOLUME with the neighbour. Overlap > eps => blocked. This correctly
    treats tangential sliding (no new overlap) as free and clearance-fits
    (shaft in a larger hole) as free, which a pure touch test cannot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from asmplan.classify import Classification
from asmplan.geometry import LoadedAssembly, LoadedPart, Vec3

_CONTACT_TOL = 1e-4      # mm; min distance below this = in contact
_OVERLAP_EPS = 1e-3      # mm^3; common-volume above this = blocked
_STEP_FRAC = 0.1         # step = 10% of the part's smallest bbox dimension
_STEP_MIN = 0.5          # mm floor for the probe step

_GLOBAL_AXES: list[Vec3] = [
    (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
]


# ── OCC helpers ──────────────────────────────────────────────────────────────

def _translated(shape, d: Vec3, dist: float):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf, gp_Vec

    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(d[0] * dist, d[1] * dist, d[2] * dist))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def _min_distance(a, b) -> float:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    return BRepExtrema_DistShapeShape(a, b).Value()


def _overlap_volume(a, b) -> float:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    try:
        common = BRepAlgoAPI_Common(a, b)
        if not common.IsDone():
            return 0.0
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(common.Shape(), props)
        return props.Mass()
    except Exception:
        return 0.0


def _principal_axes(shape) -> list[Vec3]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    pp = props.PrincipalProperties()
    out: list[Vec3] = []
    for ax in (pp.FirstAxisOfInertia(), pp.SecondAxisOfInertia(),
               pp.ThirdAxisOfInertia()):
        v = (ax.X(), ax.Y(), ax.Z())
        n = (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5
        if n > 0:
            out.append((v[0] / n, v[1] / n, v[2] / n))
    return out


# ── direction bookkeeping ────────────────────────────────────────────────────

def _dedup_directions(dirs: list[Vec3]) -> list[Vec3]:
    seen: set[tuple[int, int, int]] = set()
    out: list[Vec3] = []
    for d in dirs:
        key = (round(d[0], 3), round(d[1], 3), round(d[2], 3))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _candidate_directions(part: LoadedPart) -> list[Vec3]:
    dirs = list(_GLOBAL_AXES)
    for ax in _principal_axes(part.shape):
        dirs.append(ax)
        dirs.append((-ax[0], -ax[1], -ax[2]))
    return _dedup_directions(dirs)


def _aabb_overlaps(part: LoadedPart, d: Vec3, step: float, other: LoadedPart) -> bool:
    """Cheap broad-phase: does `part`'s AABB, shifted by step*d, overlap other's?"""
    lo = tuple(part.bbox_min[i] + d[i] * step for i in range(3))
    hi = tuple(part.bbox_max[i] + d[i] * step for i in range(3))
    for i in range(3):
        if hi[i] < other.bbox_min[i] or other.bbox_max[i] < lo[i]:
            return False
    return True


# ── the graph ────────────────────────────────────────────────────────────────

@dataclass
class ContactGraph:
    contacts: set[frozenset[str]]
    # part_id -> list of (direction, frozenset of part_ids that block it)
    blocking: dict[str, list[tuple[Vec3, frozenset[str]]]]

    def in_contact(self, a: str, b: str) -> bool:
        return frozenset((a, b)) in self.contacts

    def free_direction(self, part_id: str, present: set[str]) -> Optional[Vec3]:
        """A direction along which `part_id` can leave, given the parts still
        present. None if the part is blocked in every candidate direction."""
        others = present - {part_id}
        for d, blockers in self.blocking[part_id]:
            if not (blockers & others):
                return d
        return None

    def is_removable(self, part_id: str, present: set[str]) -> bool:
        return self.free_direction(part_id, present) is not None


def build_contact_graph(
    assembly: LoadedAssembly,
    classifications: Optional[dict[str, Classification]] = None,
) -> ContactGraph:
    parts = assembly.parts
    contacts: set[frozenset[str]] = set()

    # Contacts (symmetric): min distance ~ 0. AABB-near cull first.
    for i, p in enumerate(parts):
        for q in parts[i + 1:]:
            if not _aabb_overlaps(p, (0, 0, 0), _CONTACT_TOL + 0.1, q):
                continue
            if _min_distance(p.shape, q.shape) <= _CONTACT_TOL:
                contacts.add(frozenset((p.part_id, q.part_id)))

    blocking: dict[str, list[tuple[Vec3, frozenset[str]]]] = {}
    for p in parts:
        step = max(_STEP_MIN, _STEP_FRAC * min(p.bbox_size))
        dirs = _candidate_directions(p)
        # For a fastener, make sure its insertion axis (± ) is present.
        if classifications and classifications.get(p.part_id, None) \
                and classifications[p.part_id].axis:
            ax = classifications[p.part_id].axis
            dirs = _dedup_directions(dirs + [ax, (-ax[0], -ax[1], -ax[2])])

        per_dir: list[tuple[Vec3, frozenset[str]]] = []
        for d in dirs:
            blockers: set[str] = set()
            stepped = None
            for q in parts:
                if q.part_id == p.part_id:
                    continue
                if not _aabb_overlaps(p, d, step, q):
                    continue  # broad-phase cull
                if stepped is None:
                    stepped = _translated(p.shape, d, step)
                if _overlap_volume(stepped, q.shape) > _OVERLAP_EPS:
                    blockers.add(q.part_id)
            per_dir.append((d, frozenset(blockers)))
        blocking[p.part_id] = per_dir

    return ContactGraph(contacts=contacts, blocking=blocking)
