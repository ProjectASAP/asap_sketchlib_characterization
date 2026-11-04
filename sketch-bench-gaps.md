# What sketch-bench is missing for characterization

`asap_sketchlib_characterization` draws per-N error distributions over many independent trials, against the library's theoretical error.
It calls `approxbench sketchbench` and should only configure, call, aggregate, plot and publish.
Everything below is a sketch-bench feature that would let it do that.
Each item names what characterization does by hand today.

Base: sketch-bench main `68f6514` (asap_sketchlib `a05b35c`).

## Done

| Item | PR | What characterization uses it for |
|---|---|---|
| G-1 pin the new sketchlib | #234 | measures `a05b35c` |
| G-2 a trials axis for accuracy | #236 | not used yet: `--trials` with `--trial-mode fresh\|relabel\|reseed` |
| G-3 `--quantiles`, stream statistics | #235 | KLL rank error of one query, against the one-query ε; Count Sketch error over the stream's own ‖f‖₂ |
| G-6 seeded KLL | #235 | `seed = trial + 1`, so a rerun gives the same KLL errors |
| G-7 top-k count error | #235 | not drawn yet: the per-count bound over `k` reported keys gives no useful line at δ = e^−3 |
| G-8 wrapper coverage | #235 | HLL Ertl, KMV, Space-Saving and KllDynamic are in the grid; the other new rows have no bound with a fixed line |

## G-4 The theoretical bound in the record

Characterization copies each formula from asap_sketchlib `docs/sketch_analytics.md` into `grid.py`.
For Hydra it draws no line at all, because the bound depends on each subpopulation's `N_Q`, `D_Q` or `‖f_Q‖₂`.

Proposal: when the library is sketchlib, the record carries `SketchAnalytics::theoretical_error` for the run's config (`epsilon`, `delta`, `metric`, `contract`).
Readouts that need data inputs get them from the comparator, which already holds the exact answer:
- `D_max` for UnivMon cardinality;
- `D` for heap top-k and Bloom;
- `N`, and per subpopulation `N_Q`, `D_Q` and `‖f_Q‖₂`, for Hydra (`--per-group-out` already writes them).

## G-5 Checkpoints (optional)

Every N is a separate stream today.
DataSketches scores one stream at several prefix lengths.
Proposal: `--checkpoints`, which needs a `GroundTruth` that answers over a prefix.
Decide after G-2, by how long a full grid takes.

## G-9 Per-key estimates from the frequency comparator

DataSketches' Count-Min characterization queries every key in every trial and plots each key's estimate against its true count.
The frequency comparator reports means over the top 1, 10, 100 and 1000 keys and over all keys, so characterization can only follow one key, the most frequent.
Proposal: `--per-key-out`, writing `key,true_count,estimate` per probe, like `--per-group-out` does for Hydra.

## G-10 Accuracy-only runs still repeat the query for timing

The cardinality comparator asks the same question 4096 times and the top-k comparator 1024 times, so that the query time is readable.
With `--metrics accuracy` alone only the first answer is scored.
For HLL at `lg_k = 14` the repeats are about 200 ms of each trial, so one process over 1024 trials is no faster than 1024 processes.
Proposal: ask once when accuracy is the only metric.

## G-11 Rows that do not reproduce

hydra-cms, hydra-cs, hydra-univmon-entropy (lib and polars), univmon-cardinality, univmon-entropy (lib and oxide), univmon-two-tier-cardinality and univmon-two-tier-entropy give different numbers on two runs over the same input.
For these rows trial `t` cannot be rerun from its record.
UnivMonQ has `seed_index` and no `seed`, so it takes no `--trial-mode reseed`.

## Order

G-10 removes most of the run time of the cardinality and top-k rows.
G-4 and G-9 let characterization draw the rows it leaves without a line today.
G-5 widens and speeds up the grid.
