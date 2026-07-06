"""Stage 3 — Contact / Disassembly-Freedom Analysis (DFA).

Build, for a static assembly, the directional blocking graph the sequencer needs:

  * for each part, along which candidate DIRECTIONS it is free to move, and which
    other parts block each direction,
  * which parts are in CONTACT (derived from the blocking relation).

Method:
  * Candidate directions per part = 6 global axes ∪ the part's own principal
    axes (a fastener's insertion axis is one of these).
  * BROAD phase: AABB overlap after a step cull — skip far pairs cheaply.
  * NARROW phase: translate the part a small step along d and measure the
    OVERLAP VOLUME with the neighbour. Overlap > eps => blocked. Tangential
    sliding produces no new overlap (free); clearance-fits (shaft in a larger
    hole) produce no overlap (free) — which a pure touch test cannot tell apart.

Narrow-phase backends: fast MESH intersection (manifold3d) for parts that
tessellate to watertight volumes, with an exact OpenCASCADE boolean FALLBACK for
the few parts whose mesh isn't a clean volume. Mesh is ~13x faster and matches
the boolean result to within tessellation tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import trimesh

from asmplan.classify import Classification
from asmplan.emit.tessellate import tessellate
from asmplan.geometry import LoadedAssembly, LoadedPart, Vec3

_OVERLAP_EPS = 1e-1      # mm^3; common-volume above this = blocked
_STEP_FRAC = 0.1         # step = 10% of the part's smallest bbox dimension
_STEP_MIN = 0.5          # mm floor for the probe step
_MESH_DEFLECTION = 0.5   # tessellation fineness for the collision meshes

_GLOBAL_AXES: list[Vec3] = [
    (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1),
]


# ── narrow-phase backends ────────────────────────────────────────────────────

def _build_mesh(shape) -> Optional[trimesh.Trimesh]:
    """Collision mesh for a shape, or None if it has no triangles. Meshes that
    aren't perfectly watertight are kept — the manifold boolean handles them
    robustly (check_volume=False); only a hard boolean failure falls back to OCC."""
    verts, tris = tessellate(shape, _MESH_DEFLECTION)
    if not tris:
        return None
    return trimesh.Trimesh(vertices=np.array(verts), faces=np.array(tris),
                           process=True)


def _mesh_overlap(stepped_a: trimesh.Trimesh, b: trimesh.Trimesh) -> Optional[float]:
    """Intersection volume of two meshes, or None if the mesh boolean fails
    (caller falls back to OCC). check_volume=False lets manifold process meshes
    that aren't strictly closed, which OCC tessellation occasionally produces."""
    try:
        inter = stepped_a.intersection(b, check_volume=False)
        if inter is None or len(inter.faces) == 0:
            return 0.0
        return abs(float(inter.volume))
    except Exception:
        return None


def _translated_shape(shape, d: Vec3, dist: float):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf, gp_Vec

    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(d[0] * dist, d[1] * dist, d[2] * dist))
    return BRepBuilderAPI_Transform(shape, trsf, True).Shape()


def _occ_overlap(stepped_shape, other_shape) -> float:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    try:
        common = BRepAlgoAPI_Common(stepped_shape, other_shape)
        if not common.IsDone():
            return 0.0
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(common.Shape(), props)
        return abs(props.Mass())
    except Exception:
        return 0.0


# ── directions ───────────────────────────────────────────────────────────────

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
    meshes = {p.part_id: _build_mesh(p.shape) for p in parts}
    part_by_id = {p.part_id: p for p in parts}

    blocking: dict[str, list[tuple[Vec3, frozenset[str]]]] = {}
    for p in parts:
        step = max(_STEP_MIN, _STEP_FRAC * min(p.bbox_size))
        dirs = _candidate_directions(p)
        if classifications and classifications.get(p.part_id) \
                and classifications[p.part_id].axis:
            ax = classifications[p.part_id].axis
            dirs = _dedup_directions(dirs + [ax, (-ax[0], -ax[1], -ax[2])])

        p_mesh = meshes[p.part_id]
        per_dir: list[tuple[Vec3, frozenset[str]]] = []
        for d in dirs:
            stepped_mesh = None
            if p_mesh is not None:
                stepped_mesh = p_mesh.copy().apply_translation(np.array(d) * step)
            stepped_shape = None  # lazy OCC fallback

            blockers: set[str] = set()
            for q in parts:
                if q.part_id == p.part_id:
                    continue
                if not _aabb_overlaps(p, d, step, q):
                    continue
                q_mesh = meshes[q.part_id]
                vol: Optional[float] = None
                if stepped_mesh is not None and q_mesh is not None:
                    vol = _mesh_overlap(stepped_mesh, q_mesh)
                if vol is None:  # no mesh path, or mesh boolean failed
                    if stepped_shape is None:
                        stepped_shape = _translated_shape(p.shape, d, step)
                    vol = _occ_overlap(stepped_shape, q.shape)
                if vol > _OVERLAP_EPS:
                    blockers.add(q.part_id)
            per_dir.append((d, frozenset(blockers)))
        blocking[p.part_id] = per_dir

    # Contacts derived from the blocking relation: if q blocks p within a step
    # (or vice-versa), the two parts interact -> use for precedence.
    contacts: set[frozenset[str]] = set()
    for pid, per_dir in blocking.items():
        for _, blk in per_dir:
            for q in blk:
                contacts.add(frozenset((pid, q)))

    return ContactGraph(contacts=contacts, blocking=blocking)
