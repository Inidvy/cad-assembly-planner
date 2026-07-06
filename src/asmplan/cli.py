"""asmplan CLI — run the full pipeline end-to-end on a STEP file.

    asmplan <file.step> [--out DIR]

Pipeline: Loader -> Classifier -> Sequencer(DFA) -> Motion/Plan -> Emit.
Writes plan.json + instructions.txt to DIR (default ./out). On an unsolvable
assembly it prints the sequencer's diagnostic and exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from asmplan.classify import classify_assembly
from asmplan.emit import render_instructions, write_animation, write_plan
from asmplan.loader import AssemblyLoadError, load_step
from asmplan.motion import build_plan
from asmplan.sequencer import SequencingError, sequence


def run(step_path: str, out_dir: str) -> Path:
    assembly = load_step(step_path)
    classifications = classify_assembly(assembly)
    seq = sequence(assembly, classifications)
    plan = build_plan(seq, assembly)

    out = Path(out_dir)
    plan_path = write_plan(plan, out / "plan.json")
    (out / "instructions.txt").write_text(render_instructions(plan), encoding="utf-8")
    anim_path = write_animation(plan, assembly, out / "animation.html")

    flagged = [p.part_id for p in plan.parts if p.flagged_for_review]
    print(f"Loaded {len(assembly.parts)} parts (unit: {assembly.source_unit}).")
    print(f"Assembly order: {' -> '.join(s.part_id for s in plan.ordered_steps())}")
    if flagged:
        print(f"Flagged for review (low-confidence class): {', '.join(flagged)}")
    print(f"Wrote {plan_path}, {out / 'instructions.txt'}, {anim_path}")
    return plan_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="asmplan")
    parser.add_argument("step_file", help="path to a STEP assembly file")
    parser.add_argument("--out", default="out", help="output directory (default: out)")
    args = parser.parse_args(argv)

    try:
        run(args.step_file, args.out)
    except AssemblyLoadError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except SequencingError as e:
        print(f"error: {e}", file=sys.stderr)
        print("diagnostic:", file=sys.stderr)
        print(json.dumps(e.diagnostic, indent=2), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
