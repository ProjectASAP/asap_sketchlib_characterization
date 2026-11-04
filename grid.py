"""The sketches characterized, the data each trial sees, and the theory each is drawn against.

One trial is one approxbench run at one stream length N; trials differ in their
data, so each sees a fresh key set, and seeded sketches take seed = trial + 1.
"""

import math
from dataclasses import dataclass, field
from typing import Callable

# Ranks of the Gaussian -3..+3 sigma points, as in the DataSketches pitchfork plots.
GAUSS_RANKS = [0.00135, 0.02275, 0.15866, 0.5, 0.84134, 0.97725, 0.99865]

ZIPF_SKEW = 1.1
ZIPF_KEYS = 10_000
# Keeps every trial's Zipf keys disjoint from every other trial's.
ZIPF_SHIFT = 1 << 24


@dataclass(frozen=True)
class Theory:
    label: str
    value: float


@dataclass(frozen=True)
class Sketch:
    id: str
    title: str
    variant: str
    config: str
    comparator: str
    data: Callable[[int, int], tuple[list[str], str | None]]
    data_note: str
    value: Callable[[dict, int], float]
    metric: str
    signed: bool
    theory: list[Theory] = field(default_factory=list)
    theory_note: str = ""
    # Share of trials the shaded area holds: what the bound promises, or 95% without one.
    cover: float = 0.95
    # Adds seed=<trial + 1> to the config.
    seeded: bool = False
    extra: tuple[str, ...] = ()


def n_grid(lg_min: int, lg_max: int, ppo: int) -> list[int]:
    return sorted({round(2 ** (lg_min + i / ppo)) for i in range((lg_max - lg_min) * ppo + 1)})


def uniform_keys(n: int, trial: int):
    return ["--dataset", "uniform", "--size", str(n), "--cardinality", str(10**12),
            "--dtype", "i64", "--seed", str(trial + 1)], None


def pareto_values(n: int, trial: int):
    return ["--dataset", "pareto", "--pareto-alpha", "2", "--pareto-scale", "1000",
            "--size", str(n), "--cardinality", "1", "--dtype", "f64", "--seed", str(trial + 1)], None


def zipf_shifted(n: int, trial: int):
    spec = (
        "column_num: 1\n"
        "column_label: [key]\n"
        f"row_num: {n}\n"
        "column_spec:\n"
        "  - data_type: i64\n"
        f"    shift: {trial * ZIPF_SHIFT}\n"
        "    distribution:\n"
        "      kind: zipf\n"
        f"      skewness: {ZIPF_SKEW}\n"
        f"      population_size: {ZIPF_KEYS}\n"
        f"      seed: {trial + 1}\n"
    )
    return ["--dtype", "i64"], spec


def keyed_weights(n: int, trial: int):
    """UnivMon's keyed stream: Zipf u64 keys, each with a uniform weight in [1, 100]."""
    spec = (
        "column_num: 2\n"
        "column_label: [key, value]\n"
        f"row_num: {n}\n"
        "column_spec:\n"
        "  - data_type: u64\n"
        f"    shift: {trial * ZIPF_SHIFT}\n"
        "    distribution:\n"
        "      kind: zipf\n"
        f"      skewness: {ZIPF_SKEW}\n"
        f"      population_size: {UM_KEYS}\n"
        f"      seed: {2 * trial + 1}\n"
        "  - data_type: i64\n"
        "    distribution:\n"
        "      kind: uniform\n"
        "      lower_bound: 1.0\n"
        "      upper_bound: 100.0\n"
        f"      seed: {2 * trial + 2}\n"
    )
    return ["--dtype", "u64"], spec


def hydra_records(value_type: str):
    """Hydra's records: label key1 uniform over 200, label key2 Zipf over 50, a Zipf value."""
    def data(n: int, trial: int):
        spec = (
            "column_num: 3\n"
            "column_label: [key1, key2, value]\n"
            f"row_num: {n}\n"
            "column_spec:\n"
            "  - data_type: string\n"
            "    distribution:\n"
            "      kind: uniform\n"
            "      lower_bound: 0.0\n"
            "      upper_bound: 200.0\n"
            f"      seed: {3 * trial + 1}\n"
            "  - data_type: string\n"
            "    distribution:\n"
            "      kind: zipf\n"
            "      skewness: 1.1\n"
            "      population_size: 50\n"
            f"      seed: {3 * trial + 2}\n"
            f"  - data_type: {value_type}\n"
            "    distribution:\n"
            "      kind: zipf\n"
            "      skewness: 1.2\n"
            "      population_size: 1000\n"
            f"      seed: {3 * trial + 3}\n"
        )
        return ["--dtype", value_type], spec
    return data


def median_failure(d: int, beta: float) -> float:
    need = (d + 1) // 2
    return sum(math.comb(d, i) * beta**i * (1 - beta) ** (d - i) for i in range(need, d + 1))


def count_sketch_eps(w: int, d: int, delta: float) -> float:
    """sketch_analytics.md CountSketch: eps = sqrt(q / beta), q = 1/w, P_med(d, beta) <= delta."""
    lo, hi = 0.0, 0.5
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if median_failure(d, mid) <= delta else (lo, mid)
    return math.sqrt((1 / w) / lo)


def rse_lines(c: float, m: int, unit: str = "RSE") -> list[Theory]:
    rse = c / math.sqrt(m)
    return [Theory(f"{s:+d} {unit}", s * rse) for s in (-2, 2)]


# Share of a Gaussian within ±2σ.
TWO_SIGMA = math.erf(2 / math.sqrt(2))


def two_sided(eps: float, note: str) -> list[Theory]:
    return [Theory(f"+ε ({note})", eps), Theory("−ε", -eps)]


def hll_rel(acc: dict, n: int) -> float:
    return acc["estimate"] / acc["truth"] - 1


def univmon_l2_eps(w: int) -> float:
    """sketch_analytics.md CountSketchWithL2Norm: eps = 1 - sqrt(1 - sqrt(20q)), q = 1/w."""
    return 1 - math.sqrt(1 - math.sqrt(20 / w))


def kmv_eps(k: int, delta: float) -> float:
    """sketch_analytics.md Kmv: the smallest ε whose two Chernoff terms sum to at most δ."""
    def fail(e):
        over = math.exp(-e * e * (k - 1) / ((1 + e) * (2 + e)))
        return over + (math.exp(-e * e * (k - 1) / (2 * (1 - e))) if e < 1 else 0.0)
    lo, hi = 0.0, 1.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if fail(mid) <= delta else (mid, hi)
    return hi


LG_K, KLL_K, DD_ALPHA, ROWS, COLS = 12, 200, 0.01, 3, 1024
KMV_K, KMV_DELTA, SS_CAPACITY = 4096, 0.05, 1024
KLL_EPS = 2.296 / KLL_K**0.9723
KLL_NOTE = "uniform i64 values, new values per trial; compaction seed = trial + 1"
TOPK = 32
UM_KEYS, UM_HEAP, UM_LAYERS = 100_000, 64, 14
HYDRA_GRID = "rows=3 cols=1024"
HYDRA_DATA_NOTE = ("label key1 uniform over 200 values, key2 Zipf(1.1) over 50, value Zipf(1.2) over 1000; "
                   "grouped by key1, new draws per trial")
TOPK_NOTE = f"Zipf(s = {ZIPF_SKEW}) over {ZIPF_KEYS} keys, key set shifted per trial"
UM_NOTE = (f"Zipf(s = {ZIPF_SKEW}) u64 keys over {UM_KEYS:,}, each weighted uniform in [1, 100], "
           "key set shifted per trial")

SKETCHES = [
    Sketch(
        id="hll", title="HyperLogLog (Classic)", variant="hll",
        config=f"lg_k={LG_K}", comparator="cardinality",
        data=uniform_keys, data_note="uniform i64 keys over [0, 1e12), new keys per trial",
        value=hll_rel, metric="estimate / truth − 1", signed=True,
        theory=rse_lines(1.04, 1 << LG_K), cover=TWO_SIGMA,
        theory_note=f"RSE = 1.04/√m, m = {1 << LG_K}",
    ),
    Sketch(
        id="hll-hip", title="HyperLogLog (HIP)", variant="hll-hip",
        config=f"lg_k={LG_K}", comparator="cardinality",
        data=uniform_keys, data_note="uniform i64 keys over [0, 1e12), new keys per trial",
        value=hll_rel, metric="estimate / truth − 1", signed=True,
        theory=rse_lines(math.sqrt(math.log(2)), 1 << LG_K), cover=TWO_SIGMA,
        theory_note=f"RSE = √(ln 2)/√m, m = {1 << LG_K}",
    ),
    *[Sketch(
        id=sid, title=title, variant=variant,
        config=f"k={KLL_K}", comparator="rank-error", seeded=True, extra=("--quantiles", "0.5"),
        data=uniform_keys, data_note=KLL_NOTE,
        value=lambda acc, n: acc["rank_err_q0.5"], metric=f"rank error of the median query{how}",
        signed=False,
        theory=[Theory("ε (99%, one query)", KLL_EPS)], cover=0.99,
        theory_note=f"ε = 2.296/k^0.9723, k = {KLL_K}",
    ) for sid, title, variant, how in (
        ("kll", "KLL", "kll-percall", ""),
        ("kll-cdf", "KLL (CDF)", "kll-cdf", ", read from one cdf()"),
        ("kll-dynamic", "KLL (dynamic)", "kll-dynamic", ""),
    )],
    Sketch(
        id="dd", title="DDSketch", variant="dd",
        config=f"alpha={DD_ALPHA}", comparator="relative-value-error",
        data=pareto_values, data_note="Pareto(α = 2, scale 1000) f64 values, new values per trial",
        value=lambda acc, n: acc["max_relative_value_error"],
        metric="max relative value error over 101 quantiles", signed=False,
        theory=[Theory("α (hard bound)", DD_ALPHA)], cover=1.0,
        theory_note=f"ε = α = {DD_ALPHA}",
    ),
    Sketch(
        id="cms", title="Count-Min", variant="cms-fastpath-vector2d",
        config=f"rows={ROWS} cols={COLS}", comparator="frequency",
        data=zipf_shifted,
        data_note=f"Zipf(s = {ZIPF_SKEW}) over {ZIPF_KEYS} keys, key set shifted per trial",
        value=lambda acc, n: acc["aae_top1"] / n, metric="error of the top key / N",
        signed=False,
        theory=[Theory(f"ε = e/w (δ = e^−{ROWS})", math.e / COLS)], cover=1 - math.exp(-ROWS),
        theory_note=f"ε = e/w, δ = e^−d = {math.exp(-ROWS):.3f}",
    ),
    Sketch(
        id="cs", title="Count Sketch", variant="countsketch-fastpath-vector2d",
        config=f"rows={ROWS} cols={COLS}", comparator="frequency",
        data=zipf_shifted,
        data_note=f"Zipf(s = {ZIPF_SKEW}) over {ZIPF_KEYS} keys, key set shifted per trial",
        value=lambda acc, n: acc["aae_top1"] / acc["stream_l2"], metric="|error| of the top key / ‖f‖₂",
        signed=False,
        theory=[Theory("ε (δ = 0.01)", count_sketch_eps(COLS, ROWS, 0.01))], cover=0.99,
        theory_note="ε = √(q/β), q = 1/w, P_med(d, β) = 0.01",
    ),
    Sketch(
        id="hll-ertl", title="HyperLogLog (Ertl)", variant="hll-ertl",
        config=f"lg_k={LG_K}", comparator="cardinality",
        data=uniform_keys, data_note="uniform i64 keys over [0, 1e12), new keys per trial",
        value=hll_rel, metric="estimate / truth − 1", signed=True,
        theory=rse_lines(1.04, 1 << LG_K), cover=TWO_SIGMA,
        theory_note=f"RSE = 1.04/√m, m = {1 << LG_K}",
    ),
    Sketch(
        id="kmv", title="KMV", variant="kmv",
        config=f"k={KMV_K}", comparator="cardinality",
        data=uniform_keys, data_note="uniform i64 keys over [0, 1e12), new keys per trial",
        value=hll_rel, metric="estimate / truth − 1", signed=True,
        theory=two_sided(kmv_eps(KMV_K, KMV_DELTA), f"δ = {KMV_DELTA}"), cover=1 - KMV_DELTA,
        theory_note=f"Chernoff ε at δ = {KMV_DELTA}, k = {KMV_K}; exact below k distinct",
    ),
    Sketch(
        id="space-saving", title="Space-Saving", variant="space-saving",
        config=f"capacity={SS_CAPACITY}", comparator="frequency",
        data=zipf_shifted,
        data_note=f"Zipf(s = {ZIPF_SKEW}) over {ZIPF_KEYS} keys, key set shifted per trial",
        value=lambda acc, n: acc["aae_top1"] / n, metric="error of the top key / N", signed=False,
        theory=[Theory("ε = 1/m (hard bound)", 1 / SS_CAPACITY)], cover=1.0,
        theory_note=f"ε = 1/m, δ = 0, m = {SS_CAPACITY}",
    ),
    *[Sketch(
        id=sid, title=title, variant=variant, config=config, comparator="topk",
        data=zipf_shifted, data_note=TOPK_NOTE,
        value=lambda acc, n: 1 - acc["recall_at_k"], metric=f"1 − recall@{TOPK}",
        signed=False, theory_note="none: sketch_analytics.md bounds each reported count, not recall",
    ) for sid, title, variant, config in (
        ("cms-heap-topk", "Count-Min + heap, top-k", "cms-heap-topk-fastpath-vector2d",
         f"rows={ROWS} cols={COLS} heap={TOPK}"),
        ("cs-heap-topk", "Count Sketch + heap, top-k", "countsketch-heap-topk-fastpath-vector2d",
         f"rows={ROWS} cols={COLS} heap={TOPK}"),
        ("univmon-topk", "UnivMon, top-k", "univmon-topk",
         f"heap_size={TOPK} sketch_row={ROWS} sketch_col={COLS} layer_size=8"),
    )],
    *[Sketch(
        id=f"univmon-{stat}", title=f"UnivMon, {title}", variant=f"univmon-{stat}",
        config=f"heap_size={UM_HEAP} sketch_row={ROWS} sketch_col={COLS} layer_size={UM_LAYERS}",
        comparator=f"keyed-{stat}", data=keyed_weights, data_note=UM_NOTE,
        value=hll_rel, metric="estimate / truth − 1", signed=True,
        theory=theory, theory_note=note, cover=cover,
    ) for stat, title, theory, note, cover in (
        ("cardinality", "cardinality", rse_lines(math.sqrt(1.35), UM_HEAP, "SD"),
         f"SD ≤ √(1.35/k), k = {UM_HEAP}; L = {UM_LAYERS} keeps ψ ≈ 0", TWO_SIGMA),
        ("l1-norm", "L1", [], "exact (contract univmon_unit_update_total)", 0.95),
        ("l2-norm", "L2", two_sided(univmon_l2_eps(COLS), f"δ = {median_failure(ROWS, 0.1):.3f}"),
         f"ε = 1 − √(1 − √(20/w)), w = {COLS}, δ = P_med(d, 0.1)", 1 - median_failure(ROWS, 0.1)),
        ("entropy", "entropy", [], "none in sketch_analytics.md", 0.95),
    )],
    *[Sketch(
        id=variant, title=title, variant=variant, config=config, comparator=comparator,
        data=hydra_records(vtype), data_note=HYDRA_DATA_NOTE,
        value=lambda acc, n: acc["err_mean"], metric=f"mean over subpopulations of {what}",
        signed=False, seeded=variant.startswith("hydra-kll"),
        theory_note="none drawn: the bound depends on each subpopulation's N_Q, D_Q or ‖f_Q‖₂",
    ) for variant, title, config, comparator, vtype, what in (
        ("hydra-cms", "Hydra over Count-Min", f"{HYDRA_GRID} cell_rows=3 cell_cols=1024",
         "subpop-frequency", "i64", "relative frequency error"),
        ("hydra-cs", "Hydra over Count Sketch", f"{HYDRA_GRID} cell_rows=3 cell_cols=1024",
         "subpop-frequency", "i64", "relative frequency error"),
        ("hydra-hll", "Hydra over HyperLogLog", HYDRA_GRID,
         "subpop-cardinality", "i64", "relative cardinality error"),
        ("hydra-kll", "Hydra over KLL", f"{HYDRA_GRID} cell_k={KLL_K}",
         "subpop-rank-error", "f64", "max rank error"),
        ("hydra-kll-cdf", "Hydra over KLL (CDF)", f"{HYDRA_GRID} cell_k={KLL_K}",
         "subpop-cdf-error", "f64", "CDF error"),
        *[(f"hydra-univmon-{stat}", f"Hydra over UnivMon, {stat}",
           f"{HYDRA_GRID} cell_heap_size=32 cell_sketch_row=3 cell_sketch_col=256 cell_layer_size=8",
           f"subpop-{stat}", "i64", f"relative {stat} error")
          for stat in ("cardinality", "l1-norm", "l2-norm", "entropy", "sum")],
    )],
]

BY_ID = {s.id: s for s in SKETCHES}
