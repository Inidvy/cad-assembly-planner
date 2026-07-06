"""Read/write plan.json with validation on BOTH ends.

Producers call write_plan (validates before it touches disk); consumers call
read_plan (validates what they load). A malformed plan never silently flows
through the pipeline.
"""

from __future__ import annotations

from pathlib import Path

from asmplan.schema import Plan


def write_plan(plan: Plan, path: str | Path) -> Path:
    """Validate `plan` and write it as indented JSON. Returns the written path."""
    # Re-validate: guards against a Plan mutated after construction.
    validated = Plan.model_validate(plan.model_dump())
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(validated.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_plan(path: str | Path) -> Plan:
    """Load and validate a plan.json. Raises pydantic ValidationError if bad."""
    text = Path(path).read_text(encoding="utf-8")
    return Plan.model_validate_json(text)
