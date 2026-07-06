"""Emit layer — renderers over a validated Plan.

plan.json is canonical; human instructions and the 3D animation are pure
renderers of it. Nothing here computes geometry.
"""

from asmplan.emit.plan_io import read_plan, write_plan
from asmplan.emit.instructions import render_instructions

__all__ = ["read_plan", "write_plan", "render_instructions"]
