#!/usr/bin/env python3
"""Aggregate <run>/raw.jsonl into per-N quantiles across trials and write <run>/summary.json,
<run>/index.html and one standalone SVG per sketch family in <run>/figures/<family>.svg.
If <run>/merge.jsonl exists, the merged trials go to <run>/merge_summary.json and one more SVG
per family, <run>/figures/<family>-merge.svg.

The theory lines are asap_sketchlib's own `theoretical_error`, asked through theory/
at each N with that N's data (such as the distinct count), so a bound that depends on
the data follows it."""

import argparse
import html
import json
import math
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from grid import BY_ID, FAMILIES, GAUSS_RANKS, MERGE_SHARDS, SKETCHES

THEORY = Path(__file__).resolve().parent / "theory"
# Share of a Gaussian within ±2σ: what ±2 standard errors hold.
TWO_SIGMA = math.erf(2 / math.sqrt(2))
# What the shaded area holds where there is no bound.
NO_BOUND_COVER = 0.95

W, H = 720, 340
ML, MR, MT, MB = 64, 144, 16, 44


def quantile(v: list[float], p: float) -> float:
    x = p * (len(v) - 1)
    i = math.floor(x)
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (x - i)


def theory_binary(meta: dict) -> str:
    """theory/'s binary, built if cargo is here, after checking it links the measured asap_sketchlib."""
    rev = re.search(r'asap_sketchlib = \{[^}]*rev = "([0-9a-f]+)"', (THEORY / "Cargo.toml").read_text()).group(1)
    m = re.search(r"\(git ([0-9a-f]+)\)", meta["asap_sketchlib"])
    if not m or not rev.startswith(m.group(1)):
        raise SystemExit(f"theory/Cargo.toml links asap_sketchlib {rev[:7]}, the run measured "
                         f"{meta['asap_sketchlib']}: set its rev to the measured commit")
    if shutil.which("cargo"):
        subprocess.run(["cargo", "build", "--release", "--locked", "--quiet",
                        "--manifest-path", str(THEORY / "Cargo.toml")], check=True)
    exe = THEORY / "target/release/theory"
    if not exe.exists():
        raise SystemExit(f"{exe} is missing and cargo is not on PATH to build it")
    return str(exe)


def theoretical_errors(meta: dict, queries: list[dict]) -> list[dict | None]:
    if not queries:
        return []
    r = subprocess.run([theory_binary(meta)], input=json.dumps(queries), capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"theory failed: {r.stderr.strip()}")
    return json.loads(r.stdout)


def theory_lines(s, bound: dict | None) -> tuple[list[tuple[str, float]], float]:
    """The lines one N's bound draws, as (label, value), and the share of trials they should hold."""
    if bound is None:
        return [], NO_BOUND_COVER
    eps = bound["epsilon"]
    if eps == 0:
        # An exact readout: one line at 0, whatever the sign.
        return [("exact", 0.0)], 1 - (bound["delta"] or 0.0)
    if bound["delta"] is None:
        # A standard error with no δ: draw ±2 SE, which a Gaussian estimate stays inside 95.4% of the time.
        lines = [("+2 SE", 2 * eps), ("−2 SE", -2 * eps)] if s.signed else [("2 SE", 2 * eps)]
        return lines, TWO_SIGMA
    lines = [("+ε", eps), ("−ε", -eps)] if s.signed else [("ε", eps)]
    return lines, 1 - bound["delta"]


def outside(s, lines: list[tuple[str, float]], v: list[float]) -> tuple[str, float] | None:
    """Share of trials past the theory line a reader would compare against."""
    if not lines:
        return None
    label, top = lines[0]
    if label == "exact":
        return "not exact", sum(x != 0 for x in v) / len(v)
    if s.signed:
        return f"outside ±{label.lstrip('+')}", sum(abs(x) > top for x in v) / len(v)
    return f"above {label}", sum(x > top for x in v) / len(v)


def reduce(xs: list[float], how: str) -> int:
    xs = sorted(xs)
    return round(xs[-1] if how == "max" else quantile(xs, 0.5))


def aggregate(raw_path: Path, meta: dict) -> dict:
    vals = defaultdict(lambda: defaultdict(list))
    # sketch -> N -> Data field -> one value per trial
    data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    unknown = set()
    for line in raw_path.open():
        r = json.loads(line)
        if r["sketch"] not in BY_ID:
            unknown.add(r["sketch"])
            continue
        vals[r["sketch"]][r["n"]].append(r["value"])
        b = BY_ID[r["sketch"]].bound
        if b:
            for f, (key, _) in b.data.items():
                data[r["sketch"]][r["n"]][f].append(r["acc"][key])
    if unknown:
        raise SystemExit(f"{raw_path} has sketch ids grid.py does not know: {sorted(unknown)}")

    keys, queries = [], []
    for sid, by_n in vals.items():
        b = BY_ID[sid].bound
        for n in by_n if b else ():
            d = dict(b.fixed)
            for f, (_, how) in b.data.items():
                d[f] = reduce(data[sid][n][f], how)
            keys.append((sid, n))
            queries.append({"algorithm": b.algorithm, "statistic": b.statistic, "params": b.params,
                            "data": d, "delta": b.delta, "impl": b.impl})
    bounds = dict(zip(keys, theoretical_errors(meta, queries)))

    out = {}
    for sid, by_n in vals.items():
        s = BY_ID[sid]
        rows = []
        for n in sorted(by_n):
            t = bounds.get((sid, n))
            # An exact bound holds in any metric; any other must be in the figure's.
            if t and t["epsilon"] > 0 and t["metric"] != s.bound.metric:
                raise SystemExit(f"{sid}: asap_sketchlib bounds {s.bound.statistic} in {t['metric']}, "
                                 f"the figure plots {s.bound.metric}")
            rows.append(make_row(s, n, by_n[n], t))
        out[sid] = rows
    return out


def make_row(s, n: int, values: list[float], t: dict | None) -> dict:
    """One N of one config: quantiles across trials, the band its bound speaks about, and the bound."""
    lines, c = theory_lines(s, t)
    v = sorted(values)
    o = outside(s, lines, v)
    band = ([quantile(v, (1 - c) / 2), quantile(v, (1 + c) / 2)] if s.signed
            else [v[0], quantile(v, c)])
    return {
        "n": n, "trials": len(v), "min": v[0], "max": v[-1],
        "mean": sum(v) / len(v),
        "q": [quantile(v, p) for p in GAUSS_RANKS],
        "band": band, "cover": c,
        "theory": t, "lines": lines,
        "outside_label": o[0] if o else None,
        "outside": o[1] if o else None,
    }


def aggregate_merge(run: Path, summary: dict) -> dict:
    """merge.jsonl as {id: {shards: rows}}.

    Each N is held to the unmerged sketch's bound: merging the shards should answer like one
    sketch over the whole stream. "same" is the share of trials whose merged error equals the
    unmerged trial's on the same data, which a sketch that merges exactly keeps at 1.
    """
    path = run / "merge.jsonl"
    if not path.exists():
        return {}
    merged = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))  # id -> S -> N -> trial -> value
    for line in path.open():
        r = json.loads(line)
        if r["sketch"] not in BY_ID:
            raise SystemExit(f"{path} has sketch id {r['sketch']} grid.py does not know")
        merged[r["sketch"]][r["shards"]][r["n"]][r["trial"]] = r["value"]
    single = defaultdict(dict)  # (id, N) -> trial -> value
    for line in (run / "raw.jsonl").open():
        r = json.loads(line)
        if r["sketch"] in merged:
            single[(r["sketch"], r["n"])][r["trial"]] = r["value"]
    out = {}
    for sid, by_shards in merged.items():
        s = BY_ID[sid]
        theory = {r["n"]: r["theory"] for r in summary.get(sid, [])}
        out[sid] = {}
        for shards in sorted(by_shards):
            rows = []
            for n in sorted(by_shards[shards]):
                trials = by_shards[shards][n]
                row = make_row(s, n, list(trials.values()), theory.get(n))
                base = single.get((sid, n), {})
                paired = [t for t in trials if t in base]
                row["paired"] = len(paired)
                row["same"] = sum(trials[t] == base[t] for t in paired) / len(paired) if paired else None
                # The bound is drawn once, with the unmerged sketch.
                row["lines"] = []
                rows.append(row)
            out[sid][str(shards)] = rows
    return out


# One color per config position, so a config keeps its color while its family fills in
# (Okabe-Ito blue, orange, bluish green; the blue lightens in dark mode).
COLORS = ("#0072B2", "#E69F00", "#009E73")
DARK_COLORS = ("#56B4E9", "#E69F00", "#009E73")
GRAY = "#8a8984"
# How far past the data a theory line may stretch the y axis.
OFF_SCALE = 8


def present(f, summary: dict) -> list[tuple[int, object, list[dict]]]:
    """The family's configs that have trials, each with its color index."""
    return [(i, s, summary[s.id]) for i, s in enumerate(f.configs) if s.id in summary]


class View:
    """One curve of a merge figure, standing in for a Sketch where a figure only needs its names."""

    def __init__(self, s, label: str, legend: str, tlabel: str | None = None):
        self.id, self.config, self.label, self.legend = s.id, s.config, label, legend
        self.tlabel = tlabel or label


def same_text(rows: list[dict]) -> str:
    paired = sum(r["paired"] for r in rows)
    if not paired:
        return "no unmerged trials to compare"
    same = sum(r["same"] * r["paired"] for r in rows) / paired
    if same == 1:
        return "identical to one sketch in every trial"
    return f"identical to one sketch in {same:.1%} of trials"


def merge_present(f, summary: dict, merged: dict) -> list[tuple[int, object, list[dict]]]:
    """The family's merge figure: its middle config unmerged, then merged from each shard count."""
    s = f.merged
    if s is None or s.id not in merged or s.id not in summary:
        return []
    cfgs = [(0, View(s, "one sketch", f"one sketch · {bound_summary(summary[s.id])}", "bound"), summary[s.id])]
    for k, shards in enumerate(MERGE_SHARDS, 1):
        rows = merged[s.id].get(str(shards))
        if rows:
            cfgs.append((k, View(s, f"{shards} shards", f"{shards} shards merged · {same_text(rows)}"), rows))
    return cfgs if len(cfgs) > 1 else []


MERGE_NOTE = (f"each trial's stream cut into {' or '.join(map(str, MERGE_SHARDS))} contiguous shards, one sketch "
              "per shard, merged into one and scored against the whole stream; one sketch is the same trials unmerged")


def band_label(signed: bool, rows: list[dict]) -> str:
    """What the shaded areas hold, in words, over every config's rows."""
    covers = sorted({round(r["cover"], 6) for r in rows})
    bounded = any(r["theory"] for r in rows)
    if len(covers) > 1:
        return "at each N, the share of trials that config's bound covers there"
    c = covers[0]
    if c >= 1:
        text = "all trials"
    else:
        pct = f"{c * 100:.3g}%"
        text = f"middle {pct} of trials" if signed else f"{pct} of trials are below its top edge"
    return text + (" (the share the bound covers)" if bounded else "")


def bound_summary(rows: list[dict]) -> str:
    """One config's bound in a few words: ε and δ as asap_sketchlib returned them."""
    ts = [r["theory"] for r in rows if r["theory"]]
    if not ts:
        return "no bound"
    eps = sorted({t["epsilon"] for t in ts})
    text = "ε = " + (fmt(eps[0]) if len(eps) == 1 else f"{fmt(eps[0])} … {fmt(eps[-1])}")
    deltas = sorted({t["delta"] for t in ts if t["delta"] is not None})
    text += f", δ = {', '.join(fmt(d) for d in deltas)}" if deltas else " (standard error)"
    missing = len(rows) - len(ts)
    return text + (f"; none at {missing} of {len(rows)} N" if missing else "")


def theory_note(f, cfgs) -> str:
    """The family's bound: asap_sketchlib's statistic, contracts and metric, or why there is none."""
    lead = f.lead
    if lead.bound is None:
        return lead.theory_note
    ts = [r["theory"] for _, _, rows in cfgs for r in rows if r["theory"]]
    if not ts:
        return f"none: asap_sketchlib has no bound for {lead.bound.algorithm} {lead.bound.statistic}"
    contracts = ", ".join(dict.fromkeys(t["contract"] for t in ts))
    metrics = ", ".join(dict.fromkeys(t["metric"] for t in ts))
    return f"asap_sketchlib {lead.bound.algorithm} {lead.bound.statistic}: {contracts} ({metrics})"


def fmt(x: float) -> str:
    if x == 0:
        return "0"
    return f"{x:.3g}" if 1e-3 <= abs(x) < 1e4 else f"{x:.2e}"


def n_label(n: int) -> str:
    for unit, div in (("M", 1 << 20), ("K", 1 << 10)):
        if n >= div and n % div == 0:
            return f"{n // div}{unit}"
    return str(n)


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    span = hi - lo
    raw = span / count
    mag = 10 ** math.floor(math.log10(raw))
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=10 * mag)
    first = math.ceil(lo / step) * step
    ticks, t = [], first
    while t <= hi + step * 1e-9:
        ticks.append(round(t, 12))
        t += step
    return ticks


def plot(f, cfgs) -> tuple[list[str], list[int], list[float]]:
    """The plot area's SVG elements in a W x H frame, every N drawn, and each N's x position."""
    signed = f.lead.signed
    ns = sorted({r["n"] for _, _, rows in cfgs for r in rows})
    lg = [math.log2(n) for n in ns]
    x0, x1 = math.floor(min(lg)), math.ceil(max(lg))
    x1 = max(x1, x0 + 1)
    every = [r for _, _, rows in cfgs for r in rows]
    # The axis holds the bands and every theory line within OFF_SCALE times their reach; a
    # line past that is left off and marked at the right edge, so a vacuous bound cannot
    # flatten the data.
    reach = max(abs(v) for r in every for v in r["band"])
    tvals = [v for r in every for _, v in r["lines"]]
    tvals = [v for v in tvals if abs(v) <= OFF_SCALE * reach] if reach > 0 else tvals
    top = max([r["band"][1] for r in every] + tvals)
    if signed:
        bottom = min([r["band"][0] for r in every] + tvals)
        m = max(abs(top), abs(bottom)) * 1.08 or 1.0
        y0, y1 = -m, m
    else:
        y0, y1 = 0.0, top * 1.1 or 1.0

    def px(l):
        return ML + (l - x0) / (x1 - x0) * (W - ML - MR)

    def py(v):
        return MT + (y1 - v) / (y1 - y0) * (H - MT - MB)

    xof = {n: px(math.log2(n)) for n in ns}
    parts = []
    for t in nice_ticks(y0, y1):
        y = py(t)
        parts.append(f'<line class="grid" x1="{ML}" x2="{W - MR}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tick" x="{ML - 8}" y="{y + 4:.1f}" text-anchor="end">{fmt(t)}</text>')
    for l in range(x0, x1 + 1, 2):
        x = px(l)
        parts.append(f'<line class="grid" x1="{x:.1f}" x2="{x:.1f}" y1="{MT}" y2="{H - MB}"/>')
        parts.append(f'<text class="tick" x="{x:.1f}" y="{H - MB + 18}" text-anchor="middle">{n_label(2 ** l)}</text>')
    parts.append(f'<text class="axis" x="{(ML + W - MR) / 2:.0f}" y="{H - 6}" text-anchor="middle">stream length N</text>')
    if signed:
        parts.append(f'<line class="zero" x1="{ML}" x2="{W - MR}" y1="{py(0):.1f}" y2="{py(0):.1f}"/>')

    # The widest band first, so a narrower one stays visible on top of it.
    def width(rows):
        return sum(r["band"][1] - r["band"][0] for r in rows) / len(rows)
    for i, _, rows in sorted(cfgs, key=lambda c: -width(c[2])):
        upper = " ".join(f"{xof[r['n']]:.1f},{py(r['band'][1]):.1f}" for r in rows)
        lower = " ".join(f"{xof[r['n']]:.1f},{py(r['band'][0]):.1f}" for r in reversed(rows))
        parts.append(f'<polygon class="band c{i}" points="{upper} {lower}"/>')
    for i, _, rows in cfgs:
        med = " ".join(f"{xof[r['n']]:.1f},{py(r['q'][3]):.1f}" for r in rows)
        parts.append(f'<polyline class="median c{i}" points="{med}"/>')

    # Each config's theory lines, broken where an N has no bound and flat where the bound
    # does not depend on N. Its top line is labeled with the config at the right edge.
    labels = []
    for i, s, rows in cfgs:
        # The top line: the first one the last bounded N draws.
        first = next((r["lines"][0][0] for r in reversed(rows) if r["lines"]), None)
        for label in dict.fromkeys(l for r in rows for l, _ in r["lines"]):
            runs, cur, off = [], [], False
            for r in rows:
                v = dict(r["lines"]).get(label)
                if v is not None and not y0 <= v <= y1:
                    off, v = True, None
                if v is None:
                    runs, cur = runs + [cur] if cur else runs, []
                else:
                    cur.append((xof[r["n"]], v))
            runs += [cur] if cur else []
            for run in runs[:]:
                if len(run) == 1:
                    run = [(run[0][0] - 4, run[0][1]), (run[0][0] + 4, run[0][1])]
                pts = [(ML, run[0][1])] if run[0][0] == xof[ns[0]] else []
                pts += run + ([(W - MR, run[-1][1])] if run[-1][0] == xof[ns[-1]] else [])
                parts.append(f'<polyline class="theory c{i}" points="{" ".join(f"{x:.1f},{py(v):.1f}" for x, v in pts)}"/>')
            if label != first:
                continue
            if runs:
                labels.append([py(runs[-1][-1][1]) + 4, i, getattr(s, "tlabel", s.label) + (" ↑" if off else "")])
            elif off:
                labels.append([MT + 8, i, f"{getattr(s, 'tlabel', s.label)} ↑"])
    # Keep the right-edge labels at least a line apart, in their order.
    labels.sort()
    for k in range(1, len(labels)):
        labels[k][0] = max(labels[k][0], labels[k - 1][0] + 12)
    for y, i, text in labels:
        parts.append(f'<text class="tlabel c{i}" x="{W - MR + 6}" y="{y:.1f}">{html.escape(text)}</text>')
    return parts, ns, [xof[n] for n in ns]


def chart(f, cfgs, title: str | None = None) -> str:
    body, ns, xs = plot(f, cfgs)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title or f.title)} error quantiles vs N">',
             *body]
    tips = []
    for n in ns:
        lines = [f"<b>N = {n:,}</b>"]
        for i, s, rows in cfgs:
            r = next((r for r in rows if r["n"] == n), None)
            if r is None:
                continue
            q = r["q"]
            text = (f'<i class="sw c{i}"></i> <b>{html.escape(s.label)}</b> · {r["trials"]} trials · median {fmt(q[3])} · '
                    + (f"2.3% … 97.7%: {fmt(q[1])} … {fmt(q[5])}" if f.lead.signed
                       else f"97.7%: {fmt(q[5])} · 99.87%: {fmt(q[6])}"))
            if r["theory"]:
                text += f" · ε {fmt(r['theory']['epsilon'])}"
            if r["outside"] is not None:
                text += f" · {r['outside_label']}: {r['outside']:.2%}"
            if r.get("same") is not None:
                text += f" · identical to one sketch: {r['same']:.1%}"
            lines.append(text)
        tips.append("<br>".join(lines))
    parts.append(f'<line class="cursor" x1="0" x2="0" y1="{MT}" y2="{H - MB}" visibility="hidden"/>')
    parts.append(f'<rect class="hit" x="{ML}" y="{MT}" width="{W - ML - MR}" height="{H - MT - MB}" '
                 f'data-xs="{html.escape(json.dumps([round(x, 1) for x in xs]))}" '
                 f'data-tips="{html.escape(json.dumps(tips))}"/>')
    parts.append("</svg>")
    return "".join(parts)


FIG_STYLE = """
text{font-family:Helvetica,Arial,sans-serif;fill:#52514e}
.title{font-size:16px;font-weight:600;fill:#0b0b0b}.sub{font-size:11.5px}
.tick,.tlabel,.legend{font-size:11px}.axis{font-size:12px}
.grid{stroke:#e6e5e1;stroke-width:1}.zero{stroke:#8a8984;stroke-width:1}
.band{fill:#b6d3f7}
.median{fill:none;stroke:#1c5cab;stroke-width:2}
.theory{fill:none;stroke:#52514e;stroke-width:1.25;stroke-dasharray:5 4}
""" + "".join(f".band.c{i}{{fill:{c};fill-opacity:.35}}.median.c{i},.theory.c{i}{{stroke:{c}}}.tlabel.c{i}{{fill:{c}}}"
              for i, c in enumerate(COLORS)) + f".band.gray{{fill:{GRAY};fill-opacity:.35}}.median.gray,.theory.gray{{stroke:{GRAY}}}\n"
FIG_ML, FIG_LEGEND = 28, 52


def wrap(text: str, width: float, char_px: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split(" "):
        if cur and (len(cur) + 1 + len(word)) * char_px > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return lines + [cur]


def figure(f, cfgs, title: str | None = None, note: str | None = None) -> str:
    """One family as a standalone SVG: title, axis labels, legend, no script.

    `note` replaces the line naming the configs (a merge figure names its one config and the split)."""
    body, _, _ = plot(f, cfgs)
    lead = f.lead
    every = [r for _, _, rows in cfgs for r in rows]
    trials = max(r["trials"] for r in every)
    w = FIG_ML + W
    textw = w - FIG_ML - ML - 8
    sub = (wrap(note or "configs: " + " | ".join(s.config for _, s, _ in cfgs), textw, 6.4)
           + wrap(f"{lead.data_note} · {trials} trials per N", textw, 6.4))
    top = 40 + 15 * len(sub)
    # First the configs, one color each; then, on a new row, what the shapes mean.
    items = [(f"c{i}", getattr(s, "legend", None) or f"{s.label} · {bound_summary(rows)}") for i, s, rows in cfgs]
    items += [None, ("band gray", f"shaded: {band_label(lead.signed, every)}"), ("median gray", "median"),
              ("theory gray", f"theory: {theory_note(f, cfgs)}")]
    legend, x, y = [], FIG_ML + ML, top + H + 14
    for item in items:
        if item is None:
            x, y = FIG_ML + ML, y + 20
            continue
        cls, label = item
        if x > FIG_ML + ML and x + 24 + 5.6 * len(label) > w - 8:
            x, y = FIG_ML + ML, y + 20
        if cls.startswith("c"):
            legend.append(f'<rect class="band {cls}" x="{x}" y="{y - 9}" width="18" height="10" rx="2"/>'
                          f'<line class="median {cls}" x1="{x}" x2="{x + 18}" y1="{y - 4}" y2="{y - 4}"/>')
        elif cls.startswith("band"):
            legend.append(f'<rect class="{cls}" x="{x}" y="{y - 9}" width="18" height="10" rx="2"/>')
        else:
            legend.append(f'<line class="{cls}" x1="{x}" x2="{x + 18}" y1="{y - 4}" y2="{y - 4}"/>')
        # A label wider than the figure continues on the next lines, under its own start.
        lines = wrap(label, w - 8 - (x + 24), 5.6)
        for k, line in enumerate(lines):
            legend.append(f'<text class="legend" x="{x + 24}" y="{y + 16 * k}">{html.escape(line)}</text>')
        y += 16 * (len(lines) - 1)
        x = x + 24 + 5.6 * len(lines[0]) + 18 if len(lines) == 1 else w
    h = max(top + H + FIG_LEGEND, y + 18)
    ymid = top + MT + (H - MT - MB) / 2
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
           f'<style>{FIG_STYLE}</style>',
           f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
           f'<text class="title" x="{FIG_ML + ML}" y="22">{html.escape(title or f.title)}</text>',
           *(f'<text class="sub" x="{FIG_ML + ML}" y="{40 + 15 * i}">{html.escape(line)}</text>' for i, line in enumerate(sub)),
           f'<text class="axis" transform="translate(16 {ymid:.0f}) rotate(-90)" text-anchor="middle">'
           f'{html.escape(lead.metric)}</text>',
           f'<g transform="translate({FIG_ML} {top})">', *body, '</g>', *legend, "</svg>"]
    return "".join(out)


def table(sid: str, rows: list[dict]) -> str:
    labels = list(dict.fromkeys(r["outside_label"] for r in rows if r["outside_label"]))
    olabel = labels[0] if len(labels) == 1 else ("past the bound" if labels else None)
    head = ["N", "trials", "min", "0.13%", "2.3%", "15.9%", "median", "84.1%", "97.7%", "99.87%", "max", "mean"]
    if olabel:
        head += ["bound ε", "δ", olabel]
    out = ["<table><thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in head) + "</tr></thead><tbody>"]
    for r in rows:
        cells = [f"{r['n']:,}", str(r["trials"]), fmt(r["min"]), *map(fmt, r["q"]), fmt(r["max"]), fmt(r["mean"])]
        if olabel:
            t = r["theory"]
            cells += ([fmt(t["epsilon"]), "SE" if t["delta"] is None else fmt(t["delta"]), f"{r['outside']:.2%}"]
                      if t else ["", "", ""])
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def color_vars(colors) -> str:
    return "".join(f"--c{i}:{c};" for i, c in enumerate(colors))


CSS = """
:root{--surface:#fcfcfb;--card:#ffffff;--text:#0b0b0b;--text2:#52514e;--muted:#8a8984;--rule:#e6e5e1;--theory:#52514e;""" + color_vars(COLORS) + """}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--surface:#1a1a19;--card:#222221;--text:#f0efec;
--text2:#c3c2b7;--muted:#8f8e88;--rule:#34332f;--theory:#c3c2b7;""" + color_vars(DARK_COLORS) + """}}
:root[data-theme="dark"]{--surface:#1a1a19;--card:#222221;--text:#f0efec;--text2:#c3c2b7;--muted:#8f8e88;--rule:#34332f;
--theory:#c3c2b7;""" + color_vars(DARK_COLORS) + """}
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1440px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px}
.meta{color:var(--text2);margin:0 0 12px}
.read{color:var(--text2);max-width:900px;margin:0 0 20px}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:0 0 20px;color:var(--text2);font-size:13px}
.legend span,.cfgs span{display:inline-flex;align-items:center;gap:6px}
.sw{width:18px;height:10px;border-radius:2px;display:inline-block;vertical-align:middle}
.grid-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,620px),1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:16px;position:relative}
.card h2{font-size:16px;margin:0}
.card h3{font-size:13px;margin:10px 0 0;font-weight:600}
.card .sub{color:var(--text2);font-size:12.5px;margin:2px 0 8px}
.cfgs{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12.5px;margin:0 0 8px}
.cfgs code{color:var(--text2);font-size:11.5px}
svg{width:100%;height:auto;display:block}
.grid{stroke:var(--rule);stroke-width:1}
.zero{stroke:var(--muted);stroke-width:1}
.tick,.tlabel{fill:var(--text2);font-size:11px}
.axis{fill:var(--text2);font-size:12px}
.median{fill:none;stroke-width:2}
.theory{fill:none;stroke:var(--theory);stroke-width:1.25;stroke-dasharray:5 4}
""" + "".join(f".band.c{i}{{fill:var(--c{i});fill-opacity:.35}}.median.c{i},.theory.c{i}{{stroke:var(--c{i})}}"
              f".tlabel.c{i}{{fill:var(--c{i})}}.sw.c{i}{{background:var(--c{i})}}" for i in range(len(COLORS))) + """
.cursor{stroke:var(--text2);stroke-width:1}
.hit{fill:transparent;cursor:crosshair}
.tip{position:absolute;pointer-events:none;background:var(--card);border:1px solid var(--rule);border-radius:6px;
padding:6px 8px;font-size:12px;line-height:1.5;box-shadow:0 2px 8px rgba(0,0,0,.12);display:none;z-index:2;
width:max-content;max-width:min(520px,calc(100% - 16px))}
details{margin-top:8px}summary{cursor:pointer;color:var(--text2);font-size:13px}
.tbl{overflow-x:auto}
table{border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums;margin-top:6px}
th,td{padding:3px 8px;text-align:right;border-bottom:1px solid var(--rule);white-space:nowrap}
th{color:var(--text2);font-weight:600}
"""

JS = """
document.querySelectorAll('.card').forEach(card=>{
  const svg=card.querySelector('svg'),hit=card.querySelector('.hit'),cur=card.querySelector('.cursor'),tip=card.querySelector('.tip');
  const xs=JSON.parse(hit.dataset.xs),tips=JSON.parse(hit.dataset.tips);
  hit.addEventListener('mousemove',e=>{
    const pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY;
    const p=pt.matrixTransform(svg.getScreenCTM().inverse());
    let i=0;xs.forEach((x,k)=>{if(Math.abs(x-p.x)<Math.abs(xs[i]-p.x))i=k});
    cur.setAttribute('x1',xs[i]);cur.setAttribute('x2',xs[i]);cur.setAttribute('visibility','visible');
    tip.innerHTML=tips[i];tip.style.display='block';
    const r=card.getBoundingClientRect(),w=tip.offsetWidth;
    let left=e.clientX-r.left+14;if(left+w>r.width-8)left=Math.max(8,e.clientX-r.left-w-14);
    tip.style.left=left+'px';tip.style.top=(e.clientY-r.top+10)+'px';
  });
  hit.addEventListener('mouseleave',()=>{cur.setAttribute('visibility','hidden');tip.style.display='none'});
});
"""


def card(f, cfgs, title: str | None = None, note: str | None = None) -> str:
    lead = f.lead
    every = [r for _, _, rows in cfgs for r in rows]
    chips = "".join(f'<span><i class="sw c{i}"></i><b>{html.escape(s.label)}</b> <code>{html.escape(s.config)}</code>'
                    f' {html.escape(bound_summary(rows) if not hasattr(s, "legend") else s.legend.split(" · ", 1)[1])}</span>'
                    for i, s, rows in cfgs)
    tables = "".join(f'<h3><i class="sw c{i}"></i> {html.escape(s.label)} <code>{html.escape(s.config)}</code></h3>'
                     f'<div class="tbl">{table(s.id, rows)}</div>' for i, s, rows in cfgs)
    return (f'<section class="card"><h2>{html.escape(title or f.title)}</h2>'
            f'<p class="sub">y: {html.escape(lead.metric)} · data: {html.escape(lead.data_note)}<br>'
            + (f'{html.escape(note)}<br>' if note else '')
            + f'theory: {html.escape(theory_note(f, cfgs))}<br>shaded: {html.escape(band_label(lead.signed, every))}</p>'
            f'<div class="cfgs">{chips}</div>'
            f'{chart(f, cfgs, title)}<div class="tip"></div>'
            f'<details><summary>Tables</summary>{tables}</details></section>')


def page(run: Path, summary: dict, merged: dict) -> str:
    meta = json.loads((run / "meta.json").read_text())
    ns = sorted({r["n"] for rows in summary.values() for r in rows})
    trials = max(r["trials"] for rows in summary.values() for r in rows)
    hosts = sorted({h["where"] + (f", {h['cpu']}, {h['cores']} cores" if h["cores"] else "")
                    for h in (run["host"] for run in meta.get("runs", []))})
    cards = [card(f, cfgs) for f in FAMILIES if (cfgs := present(f, summary))]
    merge_cards = [card(f, cfgs, f"{f.title}, merged", f"config {f.merged.config}: {MERGE_NOTE}")
                   for f in FAMILIES if (cfgs := merge_present(f, summary, merged))]
    merge_section = (f"""<h2 style="margin:32px 0 4px">Merged sketches</h2>
<p class="read">Each card takes one config of a sketch and runs the same trials again with sketch-bench's merge:
{html.escape(MERGE_NOTE)}. A sketch that merges exactly gives the unmerged error in every trial; the legend and the
hover say how often that held. The dashed lines are the unmerged sketch's bound, which a merged sketch should keep.</p>
<div class="grid-cards">{''.join(merge_cards)}</div>""" if merge_cards else "")
    legend = ('<div class="legend">'
              '<span><i class="sw c0"></i><i class="sw c1"></i><i class="sw c2"></i>one color per config</span>'
              '<span><i class="sw" style="background:var(--muted);opacity:.5"></i>share of trials the bound covers</span>'
              '<span><i class="sw" style="background:var(--muted);height:2px"></i>median</span>'
              '<span><i class="sw" style="border-top:2px dashed var(--theory);height:0"></i>theory</span></div>')
    shown = sum(1 for f in FAMILIES if present(f, summary))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sketch accuracy</title>
<style>{CSS}</style></head><body><main>
<h1>Sketch accuracy characterization</h1>
<p class="meta">{html.escape(meta['date'])} · asap_sketchlib {html.escape(meta['asap_sketchlib'])} ·
sketch-bench {html.escape(', '.join(sorted(set(meta['sketch_bench'].values()))))} · {shown} sketches, {len(summary)} configs ·
up to {trials} trials per point · N = {ns[0]:,} … {ns[-1]:,}{''.join(f' · ran on {html.escape(h)}' for h in hosts)}</p>
<p class="read">Each trial runs one sketch over a fresh stream and records one error value. Each card draws one sketch
at up to three configs that differ in one parameter, one color each. At each N a config's shaded area holds the
share of trials its theory speaks about (for example 95% when δ = 5%; 95% where there is no theory), and its solid
line is the median. Dashed lines are asap_sketchlib's own theoretical error (<code>SketchAnalytics::theoretical_error</code>),
asked at each N: each shaded area should stay inside its own dashed lines. Hover a point for every config's quantiles.</p>
{legend}
<div class="grid-cards">{''.join(cards)}</div>
{merge_section}
</main><script>{JS}</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run", type=Path)
    args = ap.parse_args()
    meta = json.loads((args.run / "meta.json").read_text())
    summary = aggregate(args.run / "raw.jsonl", meta)
    (args.run / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    merged = aggregate_merge(args.run, summary)
    if merged:
        (args.run / "merge_summary.json").write_text(json.dumps(merged, indent=1) + "\n")
    (args.run / "index.html").write_text(page(args.run, summary, merged))
    figs = args.run / "figures"
    figs.mkdir(exist_ok=True)
    for f in FAMILIES:
        cfgs = present(f, summary)
        if cfgs:
            (figs / f"{f.id}.svg").write_text(figure(f, cfgs))
        cfgs = merge_present(f, summary, merged)
        if cfgs:
            (figs / f"{f.id}-merge.svg").write_text(
                figure(f, cfgs, f"{f.title}, merged", f"config {f.merged.config}: {MERGE_NOTE}"))
    print(args.run / "index.html")
    print(figs)


if __name__ == "__main__":
    main()
