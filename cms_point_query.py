#!/usr/bin/env python3
"""Count-Min point-query error in DataSketches' CMS setup, one row per implementation.

One fixed stream; each trial shifts every key, which re-draws every hash position.
Writes <out>/cms_point_query.jsonl (resumable) and <out>/figures/cms_point_query.svg.
"""

import argparse
import datetime
import concurrent.futures as cf
import csv
import html
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

from characterize import DEFAULT_BENCH, git_sha, run_dir, sketchlib_version
from report import FIG_STYLE, quantile, wrap

HERE = Path(__file__).parent
BENCH = DEFAULT_BENCH / "target/release/approxbench"
DS_TSV = HERE / "reference_datasketches_cms_point_query.tsv"
N, KEYS, SKEW, ROWS, COLS = 1 << 16, 1024, 0.7, 3, 272
BOUND = math.e / COLS * N
RANKS = [0.5, 1 - math.exp(-ROWS), 1.0]
IMPLS = [
    ("cms-fastpath-vector2d", "lib", "asap_sketchlib Count-Min, fast path"),
    ("cms-regularpath-vector2d", "lib", "asap_sketchlib Count-Min, regular path"),
    ("cms", "datasketches", "DataSketches Count-Min, same trials"),
]


def spec(trial: int) -> str:
    return ("column_num: 1\ncolumn_label: [key]\n"
            f"row_num: {N}\ncolumn_spec:\n  - data_type: i64\n    shift: {trial << 24}\n"
            f"    distribution:\n      kind: zipf\n      skewness: {SKEW}\n"
            f"      population_size: {KEYS}\n      seed: 1\n")


def run(variant: str, library: str, trial: int, tmp: str) -> dict:
    stem = os.path.join(tmp, f"{variant}_{library}_{trial}")
    Path(stem + ".yaml").write_text(spec(trial))
    cmd = [str(BENCH), "sketchbench", "--variant", variant, "--library", library,
           "--config", f"rows={ROWS} cols={COLS}", "--comparator", "frequency",
           "--spec", stem + ".yaml", "--dtype", "i64",
           "--metrics", "accuracy", "--operations", "query", "--runs", "1", "--warmup-runs", "0",
           "--report", stem + ".jsonl"]
    subprocess.run(cmd, check=True, capture_output=True, stdin=subprocess.DEVNULL,
                   env=dict(os.environ, BENCH_WARMUP_SECS="0"))
    acc = json.loads(Path(stem + ".jsonl").read_text().splitlines()[0])["bench"]["accuracy"]
    for p in (stem + ".yaml", stem + ".jsonl"):
        os.remove(p)
    return {"variant": variant, "library": library, "trial": trial,
            "top1": acc["aae_top1"], "mean_all": acc["aae_all"], "n": acc["stream_items"]}


def published() -> list[float]:
    """DataSketches' published quantiles, the median over its 1024 items at each rank."""
    rows = [r for r in csv.reader(DS_TSV.open(), delimiter="\t") if not r[0].startswith("#")]
    col = {c: i for i, c in enumerate(rows[0])}
    out = []
    for p in RANKS:
        v = sorted(float(r[col[f"Q_{round(p, 2):.5f}"]]) for r in rows[1:])
        out.append(v[len(v) // 2])
    return out


def figure(rows: list[tuple[str, list[float], float | None, str]], trials: int) -> str:
    W, ML, MR, ROW = 860, 300, 150, 46
    x1 = max(BOUND, max(q[-1] for _, q, _, _ in rows)) * 1.08
    px = lambda v: ML + v / x1 * (W - ML - MR)
    head = [("title", "Count-Min point-query error, DataSketches' setup"),
            ("ask", "How far above the true count is one point query, and how often does it pass the bound εN?")]
    sub = wrap(f"w = {COLS}, d = {ROWS}: ε = e/w = {math.e / COLS:.4f}, δ = e^−d = {math.exp(-ROWS):.3f}. "
               f"One stream of N = 2^16 items, Zipf({SKEW}) over {KEYS} keys. {trials} trials; each trial renames "
               "every key, which re-draws every hash position. Error = estimate − true count of the most "
               "frequent key.", W - 40, 6.4)
    top = 66 + 15 * len(sub) + 12
    plot_h = ROW * len(rows)
    h = top + plot_h + 96
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}">',
           f'<style>{FIG_STYLE}.row{{font-size:12px;fill:#0b0b0b}}.ask{{font-size:12.5px;fill:#0b0b0b}}</style>',
           f'<rect width="{W}" height="{h}" fill="#ffffff"/>',
           f'<text class="title" x="20" y="24">{html.escape(head[0][1])}</text>',
           f'<text class="ask" x="20" y="45">{html.escape(head[1][1])}</text>',
           *(f'<text class="sub" x="20" y="{66 + 15 * i}">{html.escape(s)}</text>' for i, s in enumerate(sub))]
    step = 100 if x1 < 1200 else 200
    for t in range(0, int(x1) + 1, step):
        x = px(t)
        out.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{top + plot_h}"/>')
        out.append(f'<text class="tick" x="{x:.1f}" y="{top + plot_h + 16}" text-anchor="middle">{t}</text>')
    out.append(f'<text class="axis" x="{(ML + W - MR) / 2:.0f}" y="{top + plot_h + 36}" text-anchor="middle">'
               "error of one point query (counts above the true count)</text>")
    out.append(f'<text class="axis" x="{W - MR + 12}" y="{top - 6}">95% within</text>')
    out.append(f'<text class="axis" x="{W - 60}" y="{top - 6}">past εN</text>')
    for i, (label, q, beyond, note) in enumerate(rows):
        yc = top + ROW * i + ROW / 2
        out.append(f'<text class="row" x="{ML - 12}" y="{yc + 1:.1f}" text-anchor="end">{html.escape(label)}</text>')
        if note:
            out.append(f'<text class="tick" x="{ML - 12}" y="{yc + 15:.1f}" text-anchor="end">{html.escape(note)}</text>')
        med, p95, top_v = q
        out.append(f'<line x1="{px(p95):.1f}" x2="{px(top_v):.1f}" y1="{yc:.1f}" y2="{yc:.1f}" stroke="#8a8984" stroke-width="1.25"/>')
        out.append(f'<circle cx="{px(top_v):.1f}" cy="{yc:.1f}" r="3" fill="#8a8984"/>')
        out.append(f'<rect class="band1" x="{px(0):.1f}" y="{yc - 9:.1f}" width="{px(p95) - px(0):.1f}" height="18" rx="2"/>')
        out.append(f'<line x1="{px(med):.1f}" x2="{px(med):.1f}" y1="{yc - 13:.1f}" y2="{yc + 13:.1f}" stroke="#0b0b0b" stroke-width="2.5"/>')
        out.append(f'<text class="row" x="{W - MR + 12}" y="{yc + 4:.1f}">{p95:.0f}</text>')
        text = "—" if beyond is None else f"{beyond:.2%}"
        out.append(f'<text class="row" x="{W - 60}" y="{yc + 4:.1f}">{text}</text>')
    xb = px(BOUND)
    out.append(f'<line class="theory" x1="{xb:.1f}" x2="{xb:.1f}" y1="{top - 4}" y2="{top + plot_h}"/>')
    out.append(f'<text class="tlabel" x="{xb - 4:.1f}" y="{top - 6}" text-anchor="end">bound εN = {BOUND:.0f}</text>')

    y = top + plot_h + 60
    x = 20
    for cls, label in (("band1", "95% of trials are within the bar"), ("median", "median"),
                       ("max", "largest single trial")):
        if cls == "median":
            out.append(f'<line x1="{x + 9}" x2="{x + 9}" y1="{y - 11}" y2="{y + 1}" stroke="#0b0b0b" stroke-width="2.5"/>')
        elif cls == "max":
            out.append(f'<line x1="{x}" x2="{x + 15}" y1="{y - 4}" y2="{y - 4}" stroke="#8a8984" stroke-width="1.25"/>'
                       f'<circle cx="{x + 15}" cy="{y - 4}" r="3" fill="#8a8984"/>')
        else:
            out.append(f'<rect class="{cls}" x="{x}" y="{y - 9}" width="18" height="10" rx="2"/>')
        out.append(f'<text class="legend" x="{x + 24}" y="{y}">{label}</text>')
        x += 24 + 5.6 * len(label) + 18
    note = (f"Theory: at most δ = {math.exp(-ROWS):.0%} of queries land past the dashed line, so every bar "
            "must end left of it.")
    out.append(f'<text class="sub" x="20" y="{y + 24}">{html.escape(note)}</text>')
    out.append("</svg>")
    return "".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="run directory (default results/<asap_sketchlib sha>)")
    ap.add_argument("--trials", type=int, default=8192)
    args = ap.parse_args()
    args.out = args.out or run_dir(DEFAULT_BENCH)
    args.out.mkdir(parents=True, exist_ok=True)
    meta_path = args.out / "meta.json"
    version = sketchlib_version(DEFAULT_BENCH)
    meta = (json.loads(meta_path.read_text()) if meta_path.exists() else
            {"date": datetime.datetime.now().isoformat(timespec="seconds"), "asap_sketchlib": version})
    if meta["asap_sketchlib"] != version:
        ap.error(f"{args.out} measured asap_sketchlib {meta['asap_sketchlib']}, this build links {version}")
    meta.setdefault("sketch_bench", {})["cms_point_query"] = git_sha(DEFAULT_BENCH)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    raw = args.out / "cms_point_query.jsonl"
    done = set()
    if raw.exists():
        done = {(r["variant"], r["library"], r["trial"]) for r in map(json.loads, raw.open())}
    jobs = [(v, lib, t) for v, lib, _ in IMPLS for t in range(args.trials) if (v, lib, t) not in done]
    with tempfile.TemporaryDirectory() as tmp, raw.open("a") as f, \
            cf.ThreadPoolExecutor(os.cpu_count()) as pool:
        for r in pool.map(lambda j: run(*j, tmp), jobs):
            f.write(json.dumps(r) + "\n")

    vals: dict[tuple[str, str], list[float]] = {}
    for r in map(json.loads, raw.open()):
        assert r["n"] == N
        vals.setdefault((r["variant"], r["library"]), []).append(r["top1"])
    rows = []
    for v, lib, label in IMPLS:
        e = sorted(vals[(v, lib)])
        rows.append((label, [quantile(e, p) for p in RANKS], sum(x > BOUND for x in e) / len(e),
                     f"sketch-bench {v} / {lib}"))
    rows.append(("DataSketches characterization, published", published(), None,
                 "its own stream; median of its 1024 items"))
    svg = args.out / "figures" / "cms_point_query.svg"
    svg.parent.mkdir(exist_ok=True)
    svg.write_text(figure(rows, args.trials))
    print(svg)


if __name__ == "__main__":
    main()
