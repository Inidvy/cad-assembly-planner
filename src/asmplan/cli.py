"""asmplan CLI — run the (thin-slice) pipeline end-to-end on a STEP file.

    asmplan <file.step> [--out DIR]

Produces plan.json + instructions.txt in DIR (default ./out) and prints a
summary. This is the Milestone-A loop: Loader -> thin-slice Sequencer -> Emit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from asmplan.emit import render_instructions, write_plan
from asmplan.loader import AssemblyLoadError, load_step
from asmplan.sequencer import sequence_by_z


def run(step_path: str, out_dir: str) -> Path:
    assembly = load_step(step_path)
    plan = sequence_by_z(assembly)

    out = Path(out_dir)
    plan_path = write_plan(plan, out / "plan.json")
    (out / "instructions.txt").write_text(render_instructions(plan), encoding="utf-8")

    print(f"Loaded {len(assembly.parts)} parts (unit: {assembly.source_unit}).")
    print(f"Assembly order: {' -> '.join(s.part_id for s in plan.ordered_steps())}")
    print(f"Wrote {plan_path} and {out / 'instructions.txt'}")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
