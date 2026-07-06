"""Human-readable assembly instructions rendered from a validated Plan.

Reads the stable semantic core (order + subgoal) and, when present, describes
the advisory motion in plain language ("slide 10.0 mm", "turn 10.0 rotations").
"""

from __future__ import annotations

from asmplan.schema import Plan, Screw, Translate


def _fmt_vec(v: tuple[float, float, float]) -> str:
    return f"({v[0]:g}, {v[1]:g}, {v[2]:g})"


def _describe_motion(motion) -> str:
    if isinstance(motion, Translate):
        return f"slide {motion.distance_mm:g} mm along {_fmt_vec(motion.direction)}"
    if isinstance(motion, Screw):
        return (
            f"drive along axis {_fmt_vec(motion.axis)}: "
            f"{motion.turns:g} turns ({motion.pitch_mm:g} mm pitch)"
        )
    return ""


def render_instructions(plan: Plan) -> str:
    """Return a numbered, human-readable instruction list for the plan."""
    # Prefer human part names over internal ids wherever we surface a part.
    display = {p.part_id: (p.name or p.part_id) for p in plan.parts}

    lines: list[str] = []
    lines.append("Assembly instructions")
    lines.append(f"(units: {plan.source_unit}; {len(plan.steps)} steps)")
    lines.append("")

    for n, step in enumerate(plan.ordered_steps(), start=1):
        name = display.get(step.part_id, step.part_id)
        subgoal = step.subgoal_text or f"Install {name}."
        line = f"{n}. {subgoal}"
        if step.motion is not None:
            line += f"  [{_describe_motion(step.motion)}]"
        lines.append(line)

        detail: list[str] = []
        if step.precedes:
            deps = ", ".join(display.get(d, d) for d in step.precedes)
            detail.append(f"requires already-placed: {deps}")
        if step.stability is not None and not step.stability.stable:
            note = step.stability.notes or "unstable at this step"
            detail.append(f"⚠ stability: {note}")
        if step.stability is not None and step.stability.needs_fixture:
            detail.append("needs a fixture/support here")
        for d in detail:
            lines.append(f"     - {d}")

    return "\n".join(lines) + "\n"
