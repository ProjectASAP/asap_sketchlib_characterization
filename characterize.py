#!/usr/bin/env python3
"""Run independent trials of each sketch through approxbench, one error value per trial.

Appends to <out>/raw.jsonl and skips (sketch, n, trial) rows already there, so an
interrupted run resumes. With --merge-shards S each trial instead splits its stream into S
shards, merges the S sketches and scores the merged one; those trials go to <out>/merge.jsonl.
"""

import argparse
import concurrent.futures as cf
import datetime
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from grid import BY_FAMILY, BY_ID, SKETCHES, UNMERGEABLE, n_grid

HERE = Path(__file__).resolve().parent
DEFAULT_BENCH = Path(os.environ.get("SKETCH_BENCH_DIR", HERE.parent / "sketch-bench"))
SKETCHLIB_DIR = Path(os.environ.get("ASAP_SKETCHLIB_DIR", HERE.parent / "asap_sketchlib"))


def sketchlib_version(bench_dir: Path) -> str:
    """The asap_sketchlib the sketch-bench crate links; Cargo.lock can hold other copies."""
    lock = (bench_dir / "Cargo.lock").read_text().split("[[package]]")
    bench = next(p for p in lock if 'name = "sketch-bench"' in p)
    # "asap_sketchlib", or "asap_sketchlib <version> (<source>)" when the lock has several.
    want = (re.search(r'"asap_sketchlib( [^"]*)?"', bench).group(1) or "").strip()
    for pkg in lock:
        if 'name = "asap_sketchlib"' not in pkg:
            continue
        version = re.search(r'version = "([^"]+)"', pkg).group(1)
        m = re.search(r'source = "([^"]+)"', pkg)
        source = m.group(1) if m else "path"
        have = f"{version} ({source.split('#')[0]})"
        if want and have != want and not have.startswith(want + " "):
            continue
        if source.startswith("registry+"):
            source = "crates.io"
        elif source.startswith("git+"):
            source = "git " + source.rsplit("#", 1)[-1][:7]
        return f"{version} ({source})"
    return "unknown"


def sketchlib_sha(version: str) -> str:
    """Short commit of the measured asap_sketchlib; a crates.io release resolves through its tag."""
    m = re.search(r"\(git ([0-9a-f]+)\)", version)
    if m:
        return m.group(1)
    r = subprocess.run(["git", "-C", str(SKETCHLIB_DIR), "rev-parse", "--short",
                        f"v{version.split()[0]}^{{commit}}"], capture_output=True, text=True)
    return r.stdout.strip() or version.split()[0]


def run_dir(bench_dir: Path) -> Path:
    """results/<sketchlib sha>: one directory per measured asap_sketchlib."""
    return Path(__file__).parent / "results" / sketchlib_sha(sketchlib_version(bench_dir))


def git_sha(path: Path) -> str:
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def host(bench_dir: Path) -> dict:
    """Where this invocation runs: machine, OS and the toolchain that built approxbench."""
    def sh(*cmd, cwd=None):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        return r.stdout.strip()
    if platform.system() == "Darwin":
        cpu = sh("sysctl", "-n", "machdep.cpu.brand_string")
        mem = int(sh("sysctl", "-n", "hw.memsize") or 0)
    else:
        info = Path("/proc/cpuinfo").read_text()
        cpu = re.search(r"model name\s*:\s*(.+)", info).group(1).strip()
        mem = int(re.search(r"MemTotal:\s*(\d+)", Path("/proc/meminfo").read_text()).group(1)) * 1024
    if os.environ.get("GITHUB_ACTIONS"):
        where = f"GitHub Actions {os.environ.get('ImageOS', '')} {os.environ.get('ImageVersion', '')}".strip()
    else:
        where = "local"
    return {
        "where": where, "cpu": cpu, "cores": os.cpu_count(), "memory_gib": round(mem / 2**30, 1),
        "os": platform.platform(), "rustc": sh("rustc", "-V", cwd=bench_dir),
        "rustflags": os.environ.get("RUSTFLAGS", ""),
    }


def run_trial(binary: str, sketch_id: str, n: int, trial: int, tmp: str, shards: int = 0) -> dict:
    s = BY_ID[sketch_id]
    argv, spec = s.data(n, trial)
    stem = os.path.join(tmp, f"{sketch_id}_{n}_{trial}_{shards}")
    if spec is not None:
        with open(stem + ".yaml", "w") as f:
            f.write(spec)
        argv = ["--spec", stem + ".yaml"] + argv
    report = stem + ".jsonl"
    config = f"{s.config} seed={trial + 1}" if s.seeded else s.config
    cmd = [binary, "sketchbench", "--variant", s.variant, "--library", "lib",
           "--config", config, "--comparator", s.comparator, *argv, *s.extra,
           "--metrics", "accuracy", "--operations", "merge" if shards else "query",
           "--runs", "1", "--warmup-runs", "0", "--report", report]
    if shards:
        cmd += ["--merge-shards", str(shards), "--merge-split", "contiguous"]
    if s.trial_mode:
        cmd += ["--trials", "1", "--trial-start", str(trial), "--trial-mode", s.trial_mode]
    env = dict(os.environ, BENCH_WARMUP_SECS="0")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{r.stderr.strip()[-2000:]}")
    with open(report) as f:
        acc = json.loads(f.readline())["bench"]["accuracy"]
    for p in (report, stem + ".yaml"):
        if os.path.exists(p):
            os.remove(p)
    out = {"sketch": sketch_id, "n": n, "trial": trial, "value": s.value(acc, n), "acc": acc}
    return {**out, "shards": shards} if shards else out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="run directory (default results/<asap_sketchlib sha>)")
    ap.add_argument("--bench-dir", type=Path, default=DEFAULT_BENCH)
    ap.add_argument("--binary", help="approxbench path (default <bench-dir>/target/release/approxbench)")
    ap.add_argument("--sketches", default=",".join(s.id for s in SKETCHES),
                    help="comma-separated sketch ids and/or family names (a family runs its three configs)")
    ap.add_argument("--trials", type=int, default=256)
    ap.add_argument("--lg-min", type=int, default=8)
    ap.add_argument("--lg-max", type=int, default=20)
    ap.add_argument("--ppo", type=int, default=2, help="points per octave of N")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--merge-shards", type=int, default=0,
                    help="merge S shards per trial instead of one sketch; a family name then runs its "
                         "middle config, and the trials go to merge.jsonl")
    args = ap.parse_args()

    binary = args.binary or str(args.bench_dir / "target/release/approxbench")
    args.out = args.out or run_dir(args.bench_dir)
    asked = [i for i in args.sketches.split(",") if i]
    unknown = [i for i in asked if i not in BY_ID and i not in BY_FAMILY]
    if unknown:
        ap.error(f"unknown sketches {unknown}; known families: {list(BY_FAMILY)}; ids: {list(BY_ID)}")
    S = args.merge_shards
    if S == 1 or S < 0:
        ap.error("--merge-shards takes 2 or more (0 runs the unmerged sketch)")

    def expand(i):
        if i not in BY_FAMILY:
            return [i]
        f = BY_FAMILY[i]
        return ([f.merged.id] if f.merged else []) if S else [c.id for c in f.configs]
    ids = list(dict.fromkeys(s for i in asked for s in expand(i)))
    if S:
        cant = [i for i in ids if BY_ID[i].family in UNMERGEABLE]
        if cant:
            ap.error(f"{cant} have no merge in sketch-bench")
    ns = n_grid(args.lg_min, args.lg_max, args.ppo)

    args.out.mkdir(parents=True, exist_ok=True)
    raw_path = args.out / ("merge.jsonl" if S else "raw.jsonl")
    done = set()
    if raw_path.exists():
        for line in raw_path.open():
            r = json.loads(line)
            if r.get("shards", 0) == S:
                done.add((r["sketch"], r["n"], r["trial"]))
    jobs = [(i, n, t) for i in ids for n in ns for t in range(args.trials) if (i, n, t) not in done]

    meta = {
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "asap_sketchlib": sketchlib_version(args.bench_dir),
        "sketch_bench": dict.fromkeys(ids, git_sha(args.bench_dir)),
        "sketches": [] if S else ids, "trials": {} if S else {i: args.trials for i in ids}, "n": ns,
        "runs": [{
            "date": datetime.datetime.now().isoformat(timespec="seconds"),
            "sketches": ids, "trials": args.trials, **({"merge_shards": S} if S else {}),
            "sketch_bench": git_sha(args.bench_dir),
            "host": host(args.bench_dir), "command": ["characterize.py", *sys.argv[1:]],
        }],
    }
    if S:
        # Merged trials per config and shard count; trials/sketches stay the unmerged ones.
        meta["merge"] = {i: {str(S): args.trials} for i in ids}
    meta_path = args.out / "meta.json"
    if meta_path.exists():
        # A run directory holds one asap_sketchlib; later invocations add sketches to it.
        old = json.loads(meta_path.read_text())
        if old["asap_sketchlib"] != meta["asap_sketchlib"]:
            ap.error(f"{args.out} measured asap_sketchlib {old['asap_sketchlib']}, this build links {meta['asap_sketchlib']}")
        meta["date"] = old["date"]
        meta["sketch_bench"] = {**old.get("sketch_bench", {}), **meta["sketch_bench"]}
        old_trials = old["trials"] if isinstance(old["trials"], dict) else dict.fromkeys(old["sketches"], old["trials"])
        meta["trials"] = {**old_trials, **meta["trials"]}
        meta["sketches"] = old["sketches"] + [i for i in meta["sketches"] if i not in old["sketches"]]
        meta["n"] = sorted(set(old["n"]) | set(ns))
        meta["runs"] = old.get("runs", []) + meta["runs"]
        merge = {i: dict(v) for i, v in old.get("merge", {}).items()}
        for i, v in meta.get("merge", {}).items():
            merge.setdefault(i, {}).update(v)
        if merge:
            meta["merge"] = merge
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"{len(jobs)} trials to run ({len(done)} already in {raw_path})", flush=True)

    failures = []
    start = time.time()
    with tempfile.TemporaryDirectory() as tmp, raw_path.open("a") as raw, \
            cf.ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(run_trial, binary, i, n, t, tmp, S): (i, n, t) for i, n, t in jobs}
        step = max(1, len(jobs) // 20)
        for k, fut in enumerate(cf.as_completed(futures), 1):
            try:
                raw.write(json.dumps(fut.result()) + "\n")
            except Exception as e:  # noqa: BLE001
                failures.append((futures[fut], str(e)))
            if k % step == 0 or k == len(jobs):
                raw.flush()
                print(f"  {k}/{len(jobs)}  {time.time() - start:.0f}s", flush=True)

    for job, err in failures[:5]:
        print(f"FAILED {job}: {err}", file=sys.stderr)
    if failures:
        print(f"{len(failures)} trials failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
