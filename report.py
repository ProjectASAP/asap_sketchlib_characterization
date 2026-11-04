#!/usr/bin/env python3
"""Aggregate <run>/raw.jsonl into per-N quantiles across trials and write <run>/summary.json,
<run>/index.html and one standalone SVG per sketch in <run>/figures/."""

import argparse
import html
import json
import math
from collections import defaultdict
from pathlib import Path

from grid import BY_ID, GAUSS_RANKS, SKETCHES

W, H = 720, 340
ML, MR, MT, MB = 64, 144, 16, 44


def quantile(v: list[float], p: float) -> float:
    x = p * (len(v) - 1)
    i = math.floor(x)
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (x - i)


def outside(sketch, v: list[float]) -> tuple[str, float] | None:
    """Share of trials past the theory line a reader would compare against."""
    if not sketch.theory:
        return None
    if sketch.signed:
        two = [t for t in sketch.theory if t.label.startswith("+2 ")]
        line = two[0] if two else max(sketch.theory, key=lambda t: t.value)
        label = line.label.lstrip("+").split(" (")[0]
        return f"outside ±{label}", sum(abs(x) > line.value for x in v) / len(v)
    eps = sketch.theory[0].value
    return f"above {sketch.theory[0].label}", sum(x > eps for x in v) / len(v)


def aggregate(raw_path: Path) -> dict:
    vals = defaultdict(lambda: defaultdict(list))
    for line in raw_path.open():
        r = json.loads(line)
        vals[r["sketch"]][r["n"]].append(r["value"])
    out = {}
    for sid, by_n in vals.items():
        s = BY_ID[sid]
        rows = []
        for n in sorted(by_n):
            v = sorted(by_n[n])
            o = outside(s, v)
            c = s.cover
            band = ([quantile(v, (1 - c) / 2), quantile(v, (1 + c) / 2)] if s.signed
                    else [v[0], quantile(v, c)])
            rows.append({
                "n": n, "trials": len(v), "min": v[0], "max": v[-1],
                "mean": sum(v) / len(v),
                "q": [quantile(v, p) for p in GAUSS_RANKS],
                "band": band,
                "outside_label": o[0] if o else None,
                "outside": o[1] if o else None,
            })
        out[sid] = rows
    return out


def band_label(s) -> str:
    """What the shaded area holds, in words."""
    if s.cover >= 1:
        text = "all trials"
    else:
        pct = f"{s.cover * 100:.3g}%"
        text = f"middle {pct} of trials" if s.signed else f"{pct} of trials are below its top edge"
    return text + (" (the share the bound covers)" if s.theory else "")


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


def plot(sid: str, rows: list[dict]) -> tuple[list[str], list[float]]:
    """The plot area's SVG elements in a W x H frame, and each N's x position."""
    s = BY_ID[sid]
    lg = [math.log2(r["n"]) for r in rows]
    x0, x1 = math.floor(min(lg)), math.ceil(max(lg))
    x1 = max(x1, x0 + 1)
    tvals = [t.value for t in s.theory]
    top = max([r["band"][1] for r in rows] + tvals)
    if s.signed:
        bottom = min([r["band"][0] for r in rows] + tvals)
        m = max(abs(top), abs(bottom)) * 1.08 or 1.0
        y0, y1 = -m, m
    else:
        y0, y1 = 0.0, top * 1.1 or 1.0

    def px(l):
        return ML + (l - x0) / (x1 - x0) * (W - ML - MR)

    def py(v):
        return MT + (y1 - v) / (y1 - y0) * (H - MT - MB)

    xs = [px(l) for l in lg]
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
    if s.signed:
        parts.append(f'<line class="zero" x1="{ML}" x2="{W - MR}" y1="{py(0):.1f}" y2="{py(0):.1f}"/>')

    upper = " ".join(f"{x:.1f},{py(r['band'][1]):.1f}" for x, r in zip(xs, rows))
    lower = " ".join(f"{x:.1f},{py(r['band'][0]):.1f}" for x, r in reversed(list(zip(xs, rows))))
    parts.append(f'<polygon class="band" points="{upper} {lower}"/>')
    med = " ".join(f"{x:.1f},{py(r['q'][3]):.1f}" for x, r in zip(xs, rows))
    parts.append(f'<polyline class="median" points="{med}"/>')

    for t in s.theory:
        y = py(t.value)
        if MT <= y <= H - MB:
            parts.append(f'<line class="theory" x1="{ML}" x2="{W - MR}" y1="{y:.1f}" y2="{y:.1f}"/>')
            parts.append(f'<text class="tlabel" x="{W - MR + 6}" y="{y + 4:.1f}">{html.escape(t.label)}</text>')
    return parts, xs


def chart(sid: str, rows: list[dict]) -> str:
    s = BY_ID[sid]
    body, xs = plot(sid, rows)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(s.title)} error quantiles vs N">',
             *body]
    tips = []
    for r in rows:
        q = r["q"]
        lines = [f"<b>N = {r['n']:,}</b> · {r['trials']} trials",
                 f"99.87%: {fmt(q[6])}", f"97.7%: {fmt(q[5])}", f"84.1%: {fmt(q[4])}",
                 f"median: {fmt(q[3])}", f"15.9%: {fmt(q[2])}", f"2.3%: {fmt(q[1])}",
                 f"0.13%: {fmt(q[0])}"]
        if r["outside"] is not None:
            lines.append(f"{r['outside_label']}: {r['outside']:.2%}")
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
.theory{stroke:#52514e;stroke-width:1.25;stroke-dasharray:5 4}
"""
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


def figure(sid: str, rows: list[dict]) -> str:
    """One sketch as a standalone SVG: title, axis labels, legend, no script."""
    s = BY_ID[sid]
    body, _ = plot(sid, rows)
    trials = max(r["trials"] for r in rows)
    w = FIG_ML + W
    sub = wrap(s.config, w - FIG_ML - ML - 8, 6.4) + wrap(f"{s.data_note} · {trials} trials per N", w - FIG_ML - ML - 8, 6.4)
    top = 40 + 15 * len(sub)
    h = top + H + FIG_LEGEND
    ymid = top + MT + (H - MT - MB) / 2
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">',
           f'<style>{FIG_STYLE}</style>',
           f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
           f'<text class="title" x="{FIG_ML + ML}" y="22">{html.escape(s.title)}</text>',
           *(f'<text class="sub" x="{FIG_ML + ML}" y="{40 + 15 * i}">{html.escape(line)}</text>' for i, line in enumerate(sub)),
           f'<text class="axis" transform="translate(16 {ymid:.0f}) rotate(-90)" text-anchor="middle">'
           f'{html.escape(s.metric)}</text>',
           f'<g transform="translate({FIG_ML} {top})">', *body, '</g>']
    items = [("band", f"shaded: {band_label(s)}"), ("median", "median")]
    if s.theory:
        items.append(("theory", f"theory: {s.theory_note}"))
    x, y = FIG_ML + ML, top + H + 14
    for cls, label in items:
        if x > FIG_ML + ML and x + 24 + 5.6 * len(label) > w - 8:
            x, y = FIG_ML + ML, y + 20
        if cls == "band":
            out.append(f'<rect class="{cls}" x="{x}" y="{y - 9}" width="18" height="10" rx="2"/>')
        else:
            out.append(f'<line class="{cls}" x1="{x}" x2="{x + 18}" y1="{y - 4}" y2="{y - 4}"/>')
        out.append(f'<text class="legend" x="{x + 24}" y="{y}">{html.escape(label)}</text>')
        x += 24 + 5.6 * len(label) + 18
    out.append("</svg>")
    return "".join(out)


def figure_name(s) -> str:
    return f"{s.id}_{s.config.replace(' ', '_').replace('=', '')}.svg"


def table(sid: str, rows: list[dict]) -> str:
    olabel = next((r["outside_label"] for r in rows if r["outside_label"]), None)
    head = ["N", "trials", "min", "0.13%", "2.3%", "15.9%", "median", "84.1%", "97.7%", "99.87%", "max", "mean"]
    if olabel:
        head.append(olabel)
    out = ["<table><thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in head) + "</tr></thead><tbody>"]
    for r in rows:
        cells = [f"{r['n']:,}", str(r["trials"]), fmt(r["min"]), *map(fmt, r["q"]), fmt(r["max"]), fmt(r["mean"])]
        if olabel:
            cells.append(f"{r['outside']:.2%}")
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


CSS = """
:root{--surface:#fcfcfb;--card:#ffffff;--text:#0b0b0b;--text2:#52514e;--muted:#8a8984;--rule:#e6e5e1;
--band3:#cde2fb;--band2:#9ec5f4;--band1:#6da7ec;--median:#1c5cab;--theory:#52514e}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--surface:#1a1a19;--card:#222221;--text:#f0efec;
--text2:#c3c2b7;--muted:#8f8e88;--rule:#34332f;--band3:#0d366b;--band2:#184f95;--band1:#256abf;--median:#9ec5f4;--theory:#c3c2b7}}
:root[data-theme="dark"]{--surface:#1a1a19;--card:#222221;--text:#f0efec;--text2:#c3c2b7;--muted:#8f8e88;--rule:#34332f;
--band3:#0d366b;--band2:#184f95;--band1:#256abf;--median:#9ec5f4;--theory:#c3c2b7}
*{box-sizing:border-box}
body{margin:0;background:var(--surface);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1440px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px}
.meta{color:var(--text2);margin:0 0 12px}
.read{color:var(--text2);max-width:900px;margin:0 0 20px}
.legend{display:flex;flex-wrap:wrap;gap:16px;margin:0 0 20px;color:var(--text2);font-size:13px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:18px;height:10px;border-radius:2px;display:inline-block}
.grid-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,620px),1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--rule);border-radius:8px;padding:16px;position:relative}
.card h2{font-size:16px;margin:0}
.card .sub{color:var(--text2);font-size:12.5px;margin:2px 0 8px}
svg{width:100%;height:auto;display:block}
.grid{stroke:var(--rule);stroke-width:1}
.zero{stroke:var(--muted);stroke-width:1}
.tick,.tlabel{fill:var(--text2);font-size:11px}
.axis{fill:var(--text2);font-size:12px}
.band{fill:var(--band2)}
.median{fill:none;stroke:var(--median);stroke-width:2}
.theory{stroke:var(--theory);stroke-width:1.25;stroke-dasharray:5 4}
.cursor{stroke:var(--text2);stroke-width:1}
.hit{fill:transparent;cursor:crosshair}
.tip{position:absolute;pointer-events:none;background:var(--card);border:1px solid var(--rule);border-radius:6px;
padding:6px 8px;font-size:12px;line-height:1.45;box-shadow:0 2px 8px rgba(0,0,0,.12);display:none;white-space:nowrap;z-index:2}
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
    let left=e.clientX-r.left+14;if(left+w>r.width-8)left=e.clientX-r.left-w-14;
    tip.style.left=left+'px';tip.style.top=(e.clientY-r.top+10)+'px';
  });
  hit.addEventListener('mouseleave',()=>{cur.setAttribute('visibility','hidden');tip.style.display='none'});
});
"""


def page(run: Path, summary: dict) -> str:
    meta = json.loads((run / "meta.json").read_text())
    ns = sorted({r["n"] for rows in summary.values() for r in rows})
    trials = max(r["trials"] for rows in summary.values() for r in rows)
    cards = []
    for s in SKETCHES:
        sid = s.id
        if sid not in summary:
            continue
        rows = summary[sid]
        cards.append(
            f'<section class="card"><h2>{html.escape(s.title)} <span style="font-weight:400;color:var(--text2)">'
            f'{html.escape(s.config)}</span></h2>'
            f'<p class="sub">y: {html.escape(s.metric)} · data: {html.escape(s.data_note)}<br>'
            f'theory: {html.escape(s.theory_note)}<br>shaded: {html.escape(band_label(s))}</p>'
            f'{chart(sid, rows)}<div class="tip"></div>'
            f'<details><summary>Table</summary><div class="tbl">{table(sid, rows)}</div></details></section>')
    legend = ('<div class="legend">'
              '<span><i class="sw" style="background:var(--band2)"></i>share of trials the bound covers</span>'
              '<span><i class="sw" style="background:var(--median);height:2px"></i>median</span>'
              '<span><i class="sw" style="border-top:2px dashed var(--theory);height:0"></i>theory</span></div>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sketch accuracy</title>
<style>{CSS}</style></head><body><main>
<h1>Sketch accuracy characterization</h1>
<p class="meta">{html.escape(meta['date'])} · asap_sketchlib {html.escape(meta['asap_sketchlib'])} ·
sketch-bench {html.escape(', '.join(sorted(set(meta['sketch_bench'].values()))))} · up to {trials} trials per point ·
N = {ns[0]:,} … {ns[-1]:,}</p>
<p class="read">Each trial runs one sketch over a fresh stream and records one error value. At each N the shaded
area holds the share of trials the theory speaks about (for example 95% when δ = 5%; 95% where there is no
theory), and the line is the median. Dashed lines are the library's theoretical error: the shaded area should stay
inside them. Each card says what its shaded area holds; hover a point for more quantiles.</p>
{legend}
<div class="grid-cards">{''.join(cards)}</div>
</main><script>{JS}</script></body></html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run", type=Path)
    args = ap.parse_args()
    summary = aggregate(args.run / "raw.jsonl")
    (args.run / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    (args.run / "index.html").write_text(page(args.run, summary))
    figs = args.run / "figures"
    figs.mkdir(exist_ok=True)
    for s in SKETCHES:
        if s.id in summary:
            (figs / figure_name(s)).write_text(figure(s.id, summary[s.id]))
    print(args.run / "index.html")
    print(figs)


if __name__ == "__main__":
    main()
