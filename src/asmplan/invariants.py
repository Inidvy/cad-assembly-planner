"""Invariant oracle — the HARD test gate.

We assert properties true of ANY valid plan, not exact reproduction of a golden
file (sequences are non-unique; directions tie; floats vary across platforms).

Two tiers:
  - Plan-level invariants: pure, need only the Plan. Available now.
  - Geometry/physics invariants: need a collision/stability checker; they accept
    an injected callable so this module stays dependency-free. Skipped (returns
    UNCHECKED) when no checker is supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from asmplan.schema import Plan, PartClass, Screw, Step


@dataclass
class InvariantResult:
    name: str
    ok: bool
    detail: str = ""

    @property
    def checked(self) -> bool:
        return self.ok is not None


UNCHECKED = "unchecked (no geometry/physics checker supplied)"


# ── Plan-level invariants (pure) ─────────────────────────────────────────────

def precedence_respected(plan: Plan) -> InvariantResult:
    order_of = {s.part_id: s.order_index for s in plan.steps}
    for s in plan.steps:
        for dep in s.precedes:
            if order_of.get(dep, 1 << 30) >= s.order_index:
                return InvariantResult(
                    "precedence_respected", False,
                    f"{dep!r} not placed before {s.part_id!r}",
                )
    return InvariantResult("precedence_respected", True)


def part_count_matches(plan: Plan, expected: int) -> InvariantResult:
    n = len(plan.steps)
    return InvariantResult(
        "part_count_matches", n == expected,
        "" if n == expected else f"expected {expected} steps, got {n}",
    )


def every_part_placed_once(plan: Plan) -> InvariantResult:
    ids = [s.part_id for s in plan.steps]
    part_ids = {p.part_id for p in plan.parts}
    ok = len(ids) == len(set(ids)) == len(part_ids)
    return InvariantResult(
        "every_part_placed_once", ok,
        "" if ok else "parts and steps do not correspond one-to-one",
    )


def fasteners_use_screw_motion(plan: Plan) -> InvariantResult:
    """Advisory-but-expected: a fastener step should carry a Screw motion once
    motion generation has run. Steps with no motion yet are ignored."""
    for s in plan.steps:
        if s.part_class.is_fastener and s.motion is not None:
            if not isinstance(s.motion, Screw):
                return InvariantResult(
                    "fasteners_use_screw_motion", False,
                    f"fastener {s.part_id!r} has non-screw motion",
                )
    return InvariantResult("fasteners_use_screw_motion", True)


def reversible_for_disassembly(plan: Plan) -> InvariantResult:
    """Reversing the assembly order must yield a valid disassembly order: a part
    may be removed only after everything that depends on it (precedes edges into
    it) is already removed. If assembly respects precedence, the reverse does by
    construction — this checks it independently as a guard against bad plans."""
    # dependents[x] = parts that require x to be present (i.e. list x in precedes)
    dependents: dict[str, list[str]] = {p.part_id: [] for p in plan.parts}
    for s in plan.steps:
        for dep in s.precedes:
            dependents.setdefault(dep, []).append(s.part_id)

    order_of = {s.part_id: s.order_index for s in plan.steps}
    removal_order = sorted(order_of, key=lambda pid: -order_of[pid])
    removed: set[str] = set()
    for pid in removal_order:
        for d in dependents.get(pid, []):
            if d not in removed:
                return InvariantResult(
                    "reversible_for_disassembly", False,
                    f"cannot remove {pid!r} before its dependent {d!r}",
                )
        removed.add(pid)
    return InvariantResult("reversible_for_disassembly", True)


# ── Geometry/physics invariants (need an injected checker) ───────────────────

# A StepChecker takes a Step and returns (ok, detail).
StepChecker = Callable[[Step], tuple[bool, str]]


def collision_free(
    plan: Plan, checker: Optional[StepChecker] = None
) -> InvariantResult:
    if checker is None:
        return InvariantResult("collision_free", True, UNCHECKED)
    for s in plan.ordered_steps():
        ok, detail = checker(s)
        if not ok:
            return InvariantResult("collision_free", False, f"{s.part_id}: {detail}")
    return InvariantResult("collision_free", True)


def per_step_stable(
    plan: Plan, checker: Optional[StepChecker] = None
) -> InvariantResult:
    if checker is None:
        # Fall back to any stability reports already attached to the plan.
        for s in plan.steps:
            if s.stability is not None and not s.stability.stable:
                return InvariantResult(
                    "per_step_stable", False,
                    f"{s.part_id}: {s.stability.notes or 'unstable'}",
                )
        return InvariantResult("per_step_stable", True, UNCHECKED)
    for s in plan.ordered_steps():
        ok, detail = checker(s)
        if not ok:
            return InvariantResult("per_step_stable", False, f"{s.part_id}: {detail}")
    return InvariantResult("per_step_stable", True)


def check_all(
    plan: Plan,
    expected_parts: Optional[int] = None,
    collision_checker: Optional[StepChecker] = None,
    stability_checker: Optional[StepChecker] = None,
) -> list[InvariantResult]:
    """Run every invariant and return the results. Callers assert `.ok` on the
    subset they care about; unsupplied geometry checkers report UNCHECKED."""
    results = [
        precedence_respected(plan),
        every_part_placed_once(plan),
        fasteners_use_screw_motion(plan),
        reversible_for_disassembly(plan),
        collision_free(plan, collision_checker),
        per_step_stable(plan, stability_checker),
    ]
    if expected_parts is not None:
        results.insert(1, part_count_matches(plan, expected_parts))
    return results
