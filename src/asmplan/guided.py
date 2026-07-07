"""Human-guided disassembly resolution.

When the auto planner can't sequence an interlocked core (parts that need
rotate-to-unlock / multi-step / grouped motion), the person who knows the model
specifies the disassembly motions here, and this module VALIDATES that each
motion is collision-free against the parts still present — using the same mesh
overlap engine as the DFA. Steps that only reposition a part (to unlock another)
are supported alongside steps that remove it.

Motions are sampled along their path (not just endpoints) so a motion that
sweeps THROUGH another part is caught, not just one that ends inside it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import trimesh
import trimesh.transformations as tf

from asmplan.emit.tessellate import tessellate
from asmplan.geometry import LoadedAssembly, Vec3

_OVERLAP_EPS = 0.5     # mm^3
_MESH_DEFLECTION = 0.5


# ── motion segments (guided input) ───────────────────────────────────────────

@dataclass
class GTranslate:
    direction: Vec3
    distance: float          # mm

    def matrix(self, t: float) -> np.ndarray:
        d = np.array(self.direction, float)
        n = np.linalg.norm(d) or 1.0
        return tf.translation_matrix(d / n * self.distance * t)


@dataclass
class GRotate:
    axis: Vec3
    center: Vec3
    angle_deg: float

    def matrix(self, t: float) -> np.ndarray:
        return tf.rotation_matrix(np.radians(self.angle_deg * t),
                                  np.array(self.axis, float),
                                  point=np.array(self.center, float))


Segment = GTranslate | GRotate


@dataclass
class GuidedOp:
    part_id: str
    segments: list[Segment]
    removes: bool = True       # False = reposition only (part stays, to unlock)
    label: str = ""


# ── validation result ────────────────────────────────────────────────────────

@dataclass
class Collision:
    op_index: int
    part_id: str
    segment_index: int
    fraction: float            # where along the segment it collided (0..1)
    other: str
    overlap: float


@dataclass
class GuidedResult:
    ok: bool
    collisions: list[Collision] = field(default_factory=list)
    # per removed part, in disassembly order: (part_id, final transform 4x4)
    removals: list[tuple[str, np.ndarray]] = field(default_factory=list)


def _overlap(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    try:
        inter = a.intersection(b, check_volume=False)
        return abs(float(inter.volume)) if inter is not None and len(inter.faces) else 0.0
    except Exception:
        return 0.0


def validate(assembly: LoadedAssembly, ops: list[GuidedOp], samples: int = 8
             ) -> GuidedResult:
    """Simulate the guided disassembly, checking every sampled pose for a
    collision between the moving part and the parts still present."""
    base: dict[str, trimesh.Trimesh] = {}
    for p in assembly.parts:
        v, f = tessellate(p.shape, _MESH_DEFLECTION)
        base[p.part_id] = trimesh.Trimesh(vertices=np.array(v), faces=np.array(f),
                                          process=True)

    pose: dict[str, np.ndarray] = {p.part_id: np.eye(4) for p in assembly.parts}
    present: set[str] = {p.part_id for p in assembly.parts}

    result = GuidedResult(ok=True)
    for oi, op in enumerate(ops):
        if op.part_id not in present:
            raise ValueError(f"op {oi}: part {op.part_id!r} already removed")
        start_pose = pose[op.part_id]
        for si, seg in enumerate(op.segments):
            for k in range(1, samples + 1):
                t = k / samples
                moved = base[op.part_id].copy()
                moved.apply_transform(start_pose @ seg.matrix(t))
                for q in present:
                    if q == op.part_id:
                        continue
                    other = base[q].copy()
                    other.apply_transform(pose[q])
                    ov = _overlap(moved, other)
                    if ov > _OVERLAP_EPS:
                        result.ok = False
                        result.collisions.append(
                            Collision(oi, op.part_id, si, round(t, 3), q, round(ov, 2)))
            start_pose = start_pose @ seg.matrix(1.0)  # commit this segment
        pose[op.part_id] = start_pose
        if op.removes:
            present.discard(op.part_id)
            result.removals.append((op.part_id, start_pose.copy()))
    return result
