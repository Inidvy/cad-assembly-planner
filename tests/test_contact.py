"""Stage 3 contact/DFA tests against real STEP geometry."""

from pathlib import Path

from asmplan.classify import classify_assembly
from asmplan.contact import build_contact_graph
from asmplan.loader import load_step

FIXTURES = Path(__file__).parent / "fixtures"


def _ids_by_name(asm):
    return {p.name: p.part_id for p in asm.parts}


def test_stacked_contacts_are_adjacent_only():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    g = build_contact_graph(asm)
    n = _ids_by_name(asm)
    assert g.in_contact(n["base"], n["mid"])
    assert g.in_contact(n["mid"], n["top"])
    # base and top are 10mm apart -> NOT in contact
    assert not g.in_contact(n["base"], n["top"])


def test_mid_blocked_downward_by_base():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    g = build_contact_graph(asm)
    n = _ids_by_name(asm)
    # With everything present, moving mid straight down (-Z) is blocked by base.
    down_blockers = [
        blockers for d, blockers in g.blocking[n["mid"]]
        if d == (0, 0, -1)
    ][0]
    assert n["base"] in down_blockers


def test_top_is_removable_upward_when_all_present():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    g = build_contact_graph(asm)
    n = _ids_by_name(asm)
    present = {p.part_id for p in asm.parts}
    # top rests on mid; it must be free to lift straight up (+Z).
    assert g.is_removable(n["top"], present)
    d = g.free_direction(n["top"], present)
    assert d is not None


def test_base_not_removable_upward_through_stack():
    asm = load_step(FIXTURES / "stacked_blocks.step")
    g = build_contact_graph(asm)
    n = _ids_by_name(asm)
    present = {p.part_id for p in asm.parts}
    # base has mid+top sitting on it: +Z is blocked. (It may still be free
    # sideways in pure geometry — physics handles stability later.)
    up_blockers = [
        blockers for d, blockers in g.blocking[n["base"]]
        if d == (0, 0, 1)
    ][0]
    assert n["mid"] in up_blockers


def test_screw_axis_is_a_candidate_direction():
    asm = load_step(FIXTURES / "plate_and_screw.step")
    cls = classify_assembly(asm)
    g = build_contact_graph(asm, cls)
    n = _ids_by_name(asm)
    screw_id = next(pid for name, pid in n.items() if name and "M6" in name)
    dirs = [d for d, _ in g.blocking[screw_id]]
    # the +Z-ish insertion axis must be among the candidate directions
    assert any(abs(d[2]) > 0.9 for d in dirs)
