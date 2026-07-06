"""plan.json schema — the canonical contract for the whole pipeline.

Two layers, by deliberate design (see docs/.../design.md):

    ┌─ STABLE SEMANTIC CORE ─────────────────────────────┐
    │ parts[]   : identity + class (what each thing is)  │  <- the contract a
    │ steps[]   : order + precedence + subgoal text      │     future VLA/robot
    │             (the assembly STORY)                   │     consumes
    └────────────────────────────────────────────────────┘
    ┌─ ADVISORY LAYER (best-effort, not a frozen API) ───┐
    │ step.motion    : Translate | Screw (metric)        │
    │ step.stability : per-step physics result           │
    └────────────────────────────────────────────────────┘

Everything downstream (human instructions, 3D animation, later the robot) reads
a validated Plan. Producers validate on write, consumers validate on read.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.0"

Vec3 = tuple[float, float, float]


class PartClass(str, Enum):
    """Semantic class of a part. Fasteners drive screw-motion generation and
    precedence; everything else is a GENERIC body in v1."""

    SCREW = "screw"
    BOLT = "bolt"
    NUT = "nut"
    WASHER = "washer"
    GENERIC = "generic"

    @property
    def is_fastener(self) -> bool:
        return self in (PartClass.SCREW, PartClass.BOLT, PartClass.NUT)


# ── Advisory: motion primitives (discriminated union on `kind`) ──────────────

class Translate(BaseModel):
    """Insert/remove a part by sliding it along `direction` for `distance_mm`."""

    kind: Literal["translate"] = "translate"
    direction: Vec3
    distance_mm: float = Field(ge=0.0)


class Screw(BaseModel):
    """Drive a fastener along `axis` with a helical motion.

    turns = insertion_depth_mm / pitch_mm. Pitch comes from the fastener
    catalog, not measured geometry.
    """

    kind: Literal["screw"] = "screw"
    axis: Vec3
    pitch_mm: float = Field(gt=0.0)
    turns: float = Field(ge=0.0)


MotionPrimitive = Annotated[Union[Translate, Screw], Field(discriminator="kind")]


# ── Advisory: physics/stability result for a step ────────────────────────────

class StabilityReport(BaseModel):
    stable: bool
    needs_fixture: bool = False
    notes: str = ""


# ── Stable semantic core ─────────────────────────────────────────────────────

class PartIdentity(BaseModel):
    """What a part IS. `confidence` is the classifier's certainty; low-confidence
    fastener matches are surfaced (flagged_for_review), never silently trusted."""

    part_id: str
    name: Optional[str] = None
    part_class: PartClass = PartClass.GENERIC
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    flagged_for_review: bool = False


class Step(BaseModel):
    """One assembly action. Core fields (order/part/precedes/subgoal) are the
    stable contract; motion/stability are advisory."""

    order_index: int = Field(ge=0)
    part_id: str
    part_class: PartClass = PartClass.GENERIC
    # part_ids that MUST already be assembled before this step (precedence edges)
    precedes: list[str] = Field(default_factory=list)
    subgoal_text: str = ""
    motion: Optional[MotionPrimitive] = None
    stability: Optional[StabilityReport] = None


class Plan(BaseModel):
    """A validated assembly plan. Constructing one runs the cross-field checks."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    source_unit: str = "mm"
    parts: list[PartIdentity]
    steps: list[Step]

    @model_validator(mode="after")
    def _check_consistency(self) -> "Plan":
        part_ids = {p.part_id for p in self.parts}
        if len(part_ids) != len(self.parts):
            raise ValueError("duplicate part_id in parts")

        # order_index must be the contiguous sequence 0..N-1 (any permutation)
        indices = sorted(s.order_index for s in self.steps)
        if indices != list(range(len(self.steps))):
            raise ValueError(
                f"order_index must be a contiguous 0..{len(self.steps) - 1} set, "
                f"got {indices}"
            )

        step_part_ids = [s.part_id for s in self.steps]
        if len(set(step_part_ids)) != len(step_part_ids):
            raise ValueError("a part appears in more than one step")

        for s in self.steps:
            if s.part_id not in part_ids:
                raise ValueError(f"step references unknown part_id {s.part_id!r}")
            for dep in s.precedes:
                if dep not in part_ids:
                    raise ValueError(
                        f"step {s.part_id!r} precedes unknown part_id {dep!r}"
                    )
                if dep == s.part_id:
                    raise ValueError(f"step {s.part_id!r} precedes itself")

        # precedence must be satisfiable by the given order: every dependency of
        # a step must appear at an EARLIER order_index.
        order_of = {s.part_id: s.order_index for s in self.steps}
        for s in self.steps:
            for dep in s.precedes:
                if order_of[dep] >= s.order_index:
                    raise ValueError(
                        f"precedence violated: {dep!r} must come before "
                        f"{s.part_id!r} but its order_index is not earlier"
                    )
        return self

    def ordered_steps(self) -> list[Step]:
        return sorted(self.steps, key=lambda s: s.order_index)
