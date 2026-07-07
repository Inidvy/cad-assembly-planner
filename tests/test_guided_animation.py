"""Guided-disassembly animation embeds parts + ops and is self-contained HTML."""

import json
import re
from pathlib import Path

from asmplan.emit.guided_animation import render_guided_animation, write_guided_animation
from asmplan.guided import GRotate, GTranslate, GuidedOp
from asmplan.loader import load_step

FIXTURES = Path(__file__).parent / "fixtures"


def _ops(asm):
    n = {p.name: p.part_id for p in asm.parts}
    top = asm.by_id(n["top"])
    return [
        GuidedOp(n["top"], [GRotate((0, 0, 1), top.centroid, 8)], removes=False,
                 label="unlock: rotate top 8°"),
        GuidedOp(n["top"], [GTranslate((0, 0, 1), 40)], label="remove top"),
        GuidedOp(n["mid"], [GTranslate((0, 0, 1), 40)], label="remove mid"),
        GuidedOp(n["base"], [GTranslate((0, 0, 1), 40)], label="remove base"),
    ]


def test_render_embeds_ops_and_parts():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    html = render_guided_animation(asm, _ops(asm))
    data = json.loads(re.search(r"const D=(\{.*?\}), parts=", html, re.DOTALL).group(1))
    assert len(data["ops"]) == 4
    assert data["ops"][0]["segments"][0]["kind"] == "rotate"
    assert data["ops"][1]["segments"][0]["kind"] == "translate"
    assert {p["id"] for p in data["parts"]} == {p.part_id for p in asm.parts}


def test_write_creates_self_contained_html(tmp_path):
    asm = load_step(FIXTURES / "stacked_blocks.step")
    out = write_guided_animation(asm, _ops(asm), tmp_path / "guided.html")
    text = out.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert "three.module.js" in text
