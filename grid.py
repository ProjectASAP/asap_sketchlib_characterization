"""The sketches characterized, the data each trial sees, and the bound each is drawn against.

One trial is one approxbench run at one stream length N; trials differ in their
data, so each sees a fresh key set, and seeded sketches take seed = trial + 1.
The bounds come from asap_sketchlib's own analytics through theory/ (see report.py).
"""

from dataclasses import dataclass, field
from typing import Callable

# Ranks of the Gaussian -3..+3 sigma points, as in the DataSketches pitchfork plots.
GAUSS_RANKS = [0.00135, 0.02275, 0.15866, 0.5, 0.84134, 0.97725, 0.99865]

ZIPF_SKEW = 1.1
ZIPF_KEYS = 10_000
# Keeps every trial's Zipf keys disjoint from every other trial's.
ZIPF_SHIFT = 1 << 24


@dataclass(frozen=True)
class Bound:
    """The asap_sketchlib `SketchAnalytics::theoretical_error` call a figure draws.

    `algorithm` and `statistic` name asap_sketchlib's `SketchAlgorithm` and
    `StatisticKind`; `impl` picks the type where one algorithm covers several
    (theory/src/main.rs). `params` are the analytics `Params` fields. `metric` is the
    `ErrorMetric` the per-trial value is stated in, which report.py checks the
    library's answer against. `data` fills an analytics `Data` field from one N's
    trials, as (accuracy field, "max" or "median"); `fixed` fills the rest.
    """
    algorithm: str
    statistic: str
    params: dict
    metric: str
    delta: float | None = None
    impl: str | None = None
    data: dict = field(default_factory=dict)
    fixed: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Sketch:
    """One (variant, config): one id in raw.jsonl and summary.json."""
    id: str
    # The figure it is drawn on, and its name there (the parameter its family varies).
    family: str
    label: str
    title: str
    variant: str
    config: str
    comparator: str
    data: Callable[[int, int], tuple[list[str], str | None]]
    data_note: str
    value: Callable[[dict, int], float]
    metric: str
    signed: bool
    bound: Bound | None = None
    # Why there is no bound, for a sketch without one.
    theory_note: str = ""
    # Adds seed=<trial + 1> to the config.
    seeded: bool = False
    # sketch-bench --trial-mode for trial t; data() then gives trial 0's spec.
    trial_mode: str | None = None
    extra: tuple[str, ...] = ()


@dataclass(frozen=True)
class Family:
    """One figure: the same sketch at three configs that differ in one parameter, in its order."""
    id: str
    configs: tuple[Sketch, ...]

    @property
    def title(self) -> str:
        return self.configs[0].title

    @property
    def lead(self) -> Sketch:
        """The config whose metric, data and sign the whole figure shares."""
        return self.configs[0]

    @property
    def merged(self) -> Sketch | None:
        """The config the merge figure splits into shards: the middle one, if the sketch merges."""
        return None if self.id in UNMERGEABLE else self.configs[1]


# Shard counts of the merge figures: sketch-bench --operations merge splits each trial's stream
# into this many contiguous stretches, builds one sketch per stretch, merges them and scores the
# result against the whole stream. sketch-bench's HLL HIP has no merge (its running estimate
# cannot be combined).
MERGE_SHARDS = (2, 8)
UNMERGEABLE = {"hll-hip"}


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
    """Hydra's records: label key1 uniform over 200, label key2 Zipf over 50, a Zipf value.

    Trial 0's spec; --trial-mode fresh reseeds it and prefixes the labels per trial.
    """
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
            "      seed: 1\n"
            "  - data_type: string\n"
            "    distribution:\n"
            "      kind: zipf\n"
            "      skewness: 1.1\n"
            "      population_size: 50\n"
            "      seed: 2\n"
            f"  - data_type: {value_type}\n"
            "    distribution:\n"
            "      kind: zipf\n"
            "      skewness: 1.2\n"
            "      population_size: 1000\n"
            "      seed: 3\n"
        )
        return ["--dtype", value_type], spec
    return data


def hll_rel(acc: dict, n: int) -> float:
    return acc["estimate"] / acc["truth"] - 1


ROWS, KLL_K = 3, 200
KMV_DELTA = 0.05
# δ for the bounds whose δ the caller chooses (Count Sketch takes asap_sketchlib's default, 0.01).
CS_DELTA, UM_DELTA = 0.01, 0.05
TOPK = 32
UM_KEYS, UM_HEAP, UM_COLS, UM_LAYERS = 100_000, 64, 1024, 14
HYDRA_ROWS, HYDRA_COLS = 3, 1024
HYDRA_GRID = f"rows={HYDRA_ROWS} cols={HYDRA_COLS}"
# Each trial's exact distinct count, as approxbench reports it.
TRUE_DISTINCT = ("truth", "median")
UNIFORM_NOTE = "uniform i64 keys over [0, 1e12), new keys per trial"
ZIPF_NOTE = f"Zipf(s = {ZIPF_SKEW}) over {ZIPF_KEYS} keys, key set shifted per trial"
KLL_NOTE = "uniform i64 values, new values per trial; compaction seed = trial + 1"
HYDRA_DATA_NOTE = ("label key1 uniform over 200 values, key2 Zipf(1.1) over 50, value Zipf(1.2) over 1000; "
                   "grouped by key1, new draws and new label strings per trial (--trial-mode fresh)")
UM_NOTE = (f"Zipf(s = {ZIPF_SKEW}) u64 keys over {UM_KEYS:,}, each weighted uniform in [1, 100], "
           "key set shifted per trial")
TOPK_THEORY = "none: asap_sketchlib's TopK bound covers each reported count, not recall"
HYDRA_THEORY = ("none drawn: asap_sketchlib bounds one subpopulation's estimate given its N_Q, D_Q "
                "or ‖f_Q‖₂, not this mean over subpopulations")


def family(fid: str, values, make) -> "Family":
    return Family(fid, tuple(make(v) for v in values))


def hll(fid: str, title: str, algorithm: str, impl: str | None) -> Family:
    # sketch-bench builds asap_sketchlib's HLL at lg_k 12, 14 and 16 only (fixed register types).
    def make(lg_k):
        data = {"max_distinct": ("truth", "max")} if impl == "classic" else {}
        return Sketch(
            id=f"{fid}-lgk{lg_k}", family=fid, label=f"lg_k = {lg_k}", title=title, variant=fid,
            config=f"lg_k={lg_k}", comparator="cardinality",
            data=uniform_keys, data_note=UNIFORM_NOTE,
            value=hll_rel, metric="estimate / truth − 1", signed=True,
            bound=Bound(algorithm, "Distinct", {"precision": lg_k}, "Relative", impl=impl, data=data),
        )
    return family(fid, (12, 14, 16), make)


def kll(fid: str, title: str, variant: str, algorithm: str, how: str) -> Family:
    return family(fid, (100, 200, 400), lambda k: Sketch(
        id=f"{fid}-k{k}", family=fid, label=f"k = {k}", title=title, variant=variant,
        config=f"k={k}", comparator="rank-error", seeded=True, extra=("--quantiles", "0.5"),
        data=uniform_keys, data_note=KLL_NOTE,
        value=lambda acc, n: acc["rank_err_q0.5"], metric=f"rank error of the median query{how}",
        signed=False,
        # A median query, answered per call or from the cdf() table: a Quantile readout.
        bound=Bound(algorithm, "Quantile", {"k": k}, "Rank"),
    ))


def dd() -> Family:
    return family("dd", (0.005, 0.01, 0.02), lambda alpha: Sketch(
        id=f"dd-a{alpha}", family="dd", label=f"α = {alpha}", title="DDSketch", variant="dd",
        config=f"alpha={alpha}", comparator="relative-value-error",
        data=pareto_values, data_note="Pareto(α = 2, scale 1000) f64 values, new values per trial",
        value=lambda acc, n: acc["max_relative_value_error"],
        metric="max relative value error over 101 quantiles", signed=False,
        bound=Bound("DDSketch", "Quantile", {"alpha": alpha}, "Relative"),
    ))


def matrix(fid: str, title: str, variant: str, algorithm: str, widths, value, metric, metric_kind,
           delta=None) -> Family:
    return family(fid, widths, lambda w: Sketch(
        id=f"{fid}-w{w}", family=fid, label=f"w = {w}", title=title, variant=variant,
        config=f"rows={ROWS} cols={w}", comparator="frequency",
        data=zipf_shifted, data_note=ZIPF_NOTE,
        value=value, metric=metric, signed=False,
        bound=Bound(algorithm, "ItemFrequency", {"rows": ROWS, "cols": w}, metric_kind,
                    delta=delta, impl="fast"),
    ))


def kmv() -> Family:
    return family("kmv", (1024, 4096, 16384), lambda k: Sketch(
        id=f"kmv-k{k}", family="kmv", label=f"k = {k}", title="KMV", variant="kmv",
        config=f"k={k}", comparator="cardinality",
        data=uniform_keys, data_note=UNIFORM_NOTE,
        value=hll_rel, metric="estimate / truth − 1", signed=True,
        bound=Bound("KMV", "Distinct", {"k": k}, "Relative", delta=KMV_DELTA, data={"distinct": TRUE_DISTINCT}),
    ))


def space_saving() -> Family:
    return family("space-saving", (512, 1024, 2048), lambda m: Sketch(
        id=f"space-saving-m{m}", family="space-saving", label=f"m = {m}", title="Space-Saving",
        variant="space-saving", config=f"capacity={m}", comparator="frequency",
        data=zipf_shifted, data_note=ZIPF_NOTE,
        value=lambda acc, n: acc["aae_top1"] / n, metric="error of the top key / N", signed=False,
        bound=Bound("SpaceSaving", "ItemFrequency", {"capacity": m}, "L1", fixed={"merged": False}),
    ))


def topk(fid: str, title: str, variant: str, config) -> Family:
    return family(fid, (256, 1024, 4096), lambda w: Sketch(
        id=f"{fid}-w{w}", family=fid, label=f"w = {w}", title=title, variant=variant,
        config=config(w), comparator="topk",
        data=zipf_shifted, data_note=ZIPF_NOTE,
        value=lambda acc, n: 1 - acc["recall_at_k"], metric=f"1 − recall@{TOPK}",
        signed=False, theory_note=TOPK_THEORY,
    ))


def univmon(stat: str, title: str, statistic: str, values, param: str, delta=None, data=None) -> Family:
    fid = f"univmon-{stat}"
    def make(v):
        p = {"heap_size": UM_HEAP, "rows": ROWS, "cols": UM_COLS, "layers": UM_LAYERS, param: v}
        tag, label = {"heap_size": (f"k{v}", f"k = {v}"), "cols": (f"w{v}", f"w = {v}")}[param]
        return Sketch(
            id=f"{fid}-{tag}", family=fid, label=label, title=f"UnivMon, {title}", variant=fid,
            config=f"heap_size={p['heap_size']} sketch_row={ROWS} sketch_col={p['cols']} layer_size={UM_LAYERS}",
            comparator=f"keyed-{stat}", data=keyed_weights, data_note=UM_NOTE,
            value=hll_rel, metric="estimate / truth − 1", signed=True,
            bound=Bound("UnivMon", statistic, p, "Relative", delta=delta, data=data or {}),
        )
    return family(fid, values, make)


def hydra(variant: str, title: str, comparator: str, vtype: str, what: str, values, tag: str,
          label: str, config) -> Family:
    return family(variant, values, lambda v: Sketch(
        id=f"{variant}-{tag}{v}", family=variant, label=f"{label} = {v}", title=title, variant=variant,
        config=config(v), comparator=comparator,
        data=hydra_records(vtype), data_note=HYDRA_DATA_NOTE,
        value=lambda acc, n: acc["err_mean"], metric=f"mean over subpopulations of {what}",
        signed=False, seeded=variant.startswith("hydra-kll"), trial_mode="fresh",
        theory_note=HYDRA_THEORY,
    ))


FAMILIES = [
    hll("hll", "HyperLogLog (Classic)", "HLL", "classic"),
    hll("hll-hip", "HyperLogLog (HIP)", "HLLHip", None),
    kll("kll", "KLL", "kll-percall", "KLL", ""),
    kll("kll-cdf", "KLL (CDF)", "kll-cdf", "KLL", ", read from one cdf()"),
    kll("kll-dynamic", "KLL (dynamic)", "kll-dynamic", "KLLDynamic", ""),
    dd(),
    matrix("cms", "Count-Min", "cms-fastpath-vector2d", "CountMinSketch", (512, 1024, 2048),
           lambda acc, n: acc["aae_top1"] / n, "error of the top key / N", "L1"),
    matrix("cs", "Count Sketch", "countsketch-fastpath-vector2d", "CountSketch", (256, 1024, 4096),
           lambda acc, n: acc["aae_top1"] / acc["stream_l2"], "|error| of the top key / ‖f‖₂", "L2",
           delta=CS_DELTA),
    hll("hll-ertl", "HyperLogLog (Ertl)", "HLL", "ertl"),
    kmv(),
    space_saving(),
    topk("cms-heap-topk", "Count-Min + heap, top-k", "cms-heap-topk-fastpath-vector2d",
         lambda w: f"rows={ROWS} cols={w} heap={TOPK}"),
    topk("cs-heap-topk", "Count Sketch + heap, top-k", "countsketch-heap-topk-fastpath-vector2d",
         lambda w: f"rows={ROWS} cols={w} heap={TOPK}"),
    topk("univmon-topk", "UnivMon, top-k", "univmon-topk",
         lambda w: f"heap_size={TOPK} sketch_row={ROWS} sketch_col={w} layer_size=8"),
    univmon("cardinality", "cardinality", "Distinct", (16, 64, 256), "heap_size",
            delta=UM_DELTA, data={"distinct": TRUE_DISTINCT}),
    # An exact Total bounds the relative error at 0 too.
    univmon("l1-norm", "L1", "Total", (256, 1024, 4096), "cols"),
    univmon("l2-norm", "L2", "FrequencyL2", (256, 1024, 4096), "cols"),
    univmon("entropy", "entropy", "FrequencyEntropy", (256, 1024, 4096), "cols"),
    *[hydra(v, t, c, vt, what, (256, 1024, 4096), "cw", "cell w",
            lambda w: f"{HYDRA_GRID} cell_rows=3 cell_cols={w}")
      for v, t, c, vt, what in (
          ("hydra-cms", "Hydra over Count-Min", "subpop-frequency", "i64", "relative frequency error"),
          ("hydra-cs", "Hydra over Count Sketch", "subpop-frequency", "i64", "relative frequency error"))],
    # Hydra's HLL cell has no precision in sketch-bench, so this one varies Hydra's own grid width.
    hydra("hydra-hll", "Hydra over HyperLogLog", "subpop-cardinality", "i64", "relative cardinality error",
          (256, 1024, 4096), "w", "w", lambda w: f"rows={HYDRA_ROWS} cols={w}"),
    *[hydra(v, t, c, "f64", what, (100, 200, 400), "ck", "cell k",
            lambda k: f"{HYDRA_GRID} cell_k={k}")
      for v, t, c, what in (
          ("hydra-kll", "Hydra over KLL", "subpop-rank-error", "max rank error"),
          ("hydra-kll-cdf", "Hydra over KLL (CDF)", "subpop-cdf-error", "CDF error"))],
    *[hydra(f"hydra-univmon-{stat}", f"Hydra over UnivMon, {stat}", f"subpop-{stat}", "i64",
            f"relative {stat} error", (64, 256, 1024), "cw", "cell w",
            lambda w: f"{HYDRA_GRID} cell_heap_size=32 cell_sketch_row=3 cell_sketch_col={w} cell_layer_size=8")
      for stat in ("cardinality", "l1-norm", "l2-norm", "entropy", "sum")],
]

SKETCHES = [s for f in FAMILIES for s in f.configs]
BY_ID = {s.id: s for s in SKETCHES}
BY_FAMILY = {f.id: f for f in FAMILIES}
assert len(BY_ID) == len(SKETCHES) and not set(BY_ID) & set(BY_FAMILY), "ids and family names must be unique"
assert UNMERGEABLE <= set(BY_FAMILY)
