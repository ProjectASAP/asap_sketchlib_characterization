#!/usr/bin/env python3
"""Merge run directories written by separate characterize.py / cms_point_query.py jobs into one.

Every part must have measured the same asap_sketchlib.
"""

import argparse
import json
import sys
from pathlib import Path

from grid import SKETCHES

DATA = ("raw.jsonl", "cms_point_query.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", type=Path)
    ap.add_argument("parts", type=Path, nargs="+")
    args = ap.parse_args()

    meta: dict = {}
    for part in args.parts:
        m = json.loads((part / "meta.json").read_text())
        if meta and m["asap_sketchlib"] != meta["asap_sketchlib"]:
            print(f"{part} measured asap_sketchlib {m['asap_sketchlib']}, "
                  f"the others {meta['asap_sketchlib']}", file=sys.stderr)
            return 1
        meta["date"] = min(meta.get("date", m["date"]), m["date"])
        meta["asap_sketchlib"] = m["asap_sketchlib"]
        meta["sketch_bench"] = {**meta.get("sketch_bench", {}), **m.get("sketch_bench", {})}
        meta["trials"] = {**meta.get("trials", {}), **m.get("trials", {})}
        meta["n"] = sorted(set(meta.get("n", [])) | set(m.get("n", [])))
        meta["runs"] = meta.get("runs", []) + m.get("runs", [])
    order = [s.id for s in SKETCHES]
    meta["sketches"] = [i for i in order if i in meta["trials"]]

    args.out.mkdir(parents=True, exist_ok=True)
    for name in DATA:
        lines = [l for part in args.parts if (part / name).exists()
                 for l in (part / name).read_text().splitlines() if l]
        if lines:
            (args.out / name).write_text("\n".join(lines) + "\n")
    (args.out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
