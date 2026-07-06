"""Emit animation tests: tessellation produces triangles, and the rendered HTML
embeds each part's geometry + motion so it can play back."""

import json
import re
from pathlib import Path

from asmplan.classify import classify_assembly
from asmplan.emit.animation import render_animation, write_animation
from asmplan.emit.tessellate import tessellate
from asmplan.loader import load_step
from asmplan.motion import build_plan
from asmplan.sequencer import sequence

FIXTURES = Path(__file__).parent / "fixtures"


def _plan_and_asm(name):
    asm = load_step(FIXTURES / f"{name}.step")
    plan = build_plan(sequence(asm, classify_assembly(asm)), asm)
    return plan, asm


def test_tessellate_returns_triangles():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    verts, tris = tessellate(asm.parts[0].shape)
    assert len(verts) > 0 and len(tris) > 0
    # every triangle indexes valid vertices
    for a, b, c in tris:
        assert 0 <= a < len(verts) and 0 <= b < len(verts) and 0 <= c < len(verts)


def test_animation_embeds_all_parts_with_geometry():
    plan, asm = _plan_and_asm("plate_and_screw")
    html = render_animation(plan, asm)
    m = re.search(r"const DATA = (\{.*?\});", html, re.DOTALL)
    assert m, "embedded DATA blob not found"
    data = json.loads(m.group(1))
    assert len(data["parts"]) == len(asm.parts)
    for p in data["parts"]:
        assert p["verts"] and p["tris"]
        assert "order" in p and "kind" in p and "dir" in p


def test_animation_marks_screw_motion():
    plan, asm = _plan_and_asm("plate_and_screw")
    data = json.loads(re.search(r"const DATA = (\{.*?\});",
                                render_animation(plan, asm), re.DOTALL).group(1))
    screw = next(p for p in data["parts"] if "M6" in p["name"])
    assert screw["kind"] == "screw"
    assert screw["turns"] > 0


def test_write_animation_creates_html(tmp_path):
    plan, asm = _plan_and_asm("stacked_blocks")
    out = write_animation(plan, asm, tmp_path / "animation.html")
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "three.module.js" in text  # viewer wired up
