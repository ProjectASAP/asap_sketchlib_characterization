# asap_sketchlib_characterization

Error distributions of `asap_sketchlib` sketches over many independent trials, drawn against the library's theoretical error, in the style of the DataSketches characterization plots.

Each figure draws one sketch at three configs that differ in one parameter, one color each, so the error is seen against both N and the sketch's size.
Each trial is one `approxbench sketchbench` run from [sketch-bench](../sketch-bench) at one stream length N.
Trials differ only in their data, so every trial sees a fresh key set.
Hydra rows get theirs from sketch-bench's `--trial-mode fresh`, which reseeds the data and prefixes the label strings per trial.
At each N the report shades the share of trials the theoretical bound covers (95% where there is no bound) and draws the median.
The shaded area should stay inside the dashed theory lines.
The theory lines are `asap_sketchlib`'s own `SketchAnalytics::theoretical_error`, asked through [`theory/`](theory) at each N with that N's data, so a bound that depends on the data (KMV is exact below k distinct keys) follows it.

## Run

Needs a built `approxbench` in `$SKETCH_BENCH_DIR/target/release` (default `../sketch-bench`). Python 3.10+, standard library only.
`report.py` also builds `theory/` with cargo; the `asap_sketchlib` rev in `theory/Cargo.toml` must be the measured one, which `report.py` checks against `meta.json`.

```bash
python3 characterize.py --trials 1024
python3 characterize.py --trials 1024 --merge-shards 2
python3 characterize.py --trials 1024 --merge-shards 8
python3 report.py results/<sha>
python3 cms_point_query.py
```

Each run directory is `results/<sha>`, the short commit of the `asap_sketchlib` that sketch-bench pins.
A crates.io release resolves to its tag's commit.
`meta.json` records the sketch-bench commit that ran each sketch, and under `runs` each invocation's machine, OS, rustc, `RUSTFLAGS` and command.

`characterize.py` appends to `raw.jsonl` and skips trials already there, so it resumes after an interruption.
Options: `--sketches` (sketch ids such as `cms-w1024`, or family names such as `cms` for all three configs), `--lg-min/--lg-max` (N from 2^lg-min to 2^lg-max), `--ppo` (points per octave), `--workers`.

`--merge-shards S` runs the same trials through sketch-bench's merge instead: each trial's stream is cut into S contiguous shards, one sketch is built per shard, the S sketches are merged, and the merged sketch is scored against the whole stream.
A family name then means its middle config, and the trials go to `merge.jsonl`.
The report draws `figures/<family>-merge.svg` for each family: the unmerged config and its merges from 2 and 8 shards, against the unmerged sketch's bound, with the share of trials whose merged error equals the unmerged one (always, for a sketch that merges exactly).
HyperLogLog HIP has no merge in sketch-bench, so it has no merge figure.
Hydra over UnivMon holds one grid per shard, about 0.27 GB per shard at N = 2^20, so its 8-shard runs need `--workers` low enough for memory.

## Run on GitHub

Actions → **Characterize** → **Run workflow**.
It builds sketch-bench at `sketch_bench_ref`, runs one job per sketch and one for `cms_point_query`, merges them with `merge.py`, draws the report and commits `results/<sha>/` to the branch it ran on.
The raw trials (`raw.jsonl`, `cms_point_query.jsonl`) are not committed; they stay 90 days as the run's `results-<sha>` artifact.
Inputs: `trials`, `cms_trials`, `sketches` (ids or family names; empty runs all; one job per config) and `publish` (off keeps the results as an artifact only).

## Files

| File | Contents |
| --- | --- |
| `grid.py` | the sketch families and their three configs, the data each trial sees, the per-trial error and the `asap_sketchlib` bound each is drawn against |
| `theory/` | a small Rust program that answers `asap_sketchlib`'s `theoretical_error` for the bounds `grid.py` names |
| `characterize.py` | runs the trials in parallel and writes `raw.jsonl` and `meta.json` |
| `merge.py` | merges run directories written by separate jobs |
| `report.py` | asks `theory/` for each bound, and writes `summary.json` (quantiles and bound per N), `index.html` and `figures/<family>.svg`, one standalone vector figure per family with its configs overlaid; with merge trials also `merge_summary.json` and `figures/<family>-merge.svg` |
| `cms_point_query.py` | Count-Min in DataSketches' setup (w = 272, d = 3, one stream, a new hash per trial), one row per implementation; writes `cms_point_query.jsonl` and `figures/cms_point_query.svg` |
| `reference_datasketches_cms_point_query.tsv` | DataSketches' published CMS point-query results, drawn as a reference row |
| `results/<sha>/` | the runs against one `asap_sketchlib` commit |
| `.github/workflows/characterize.yml` | the GitHub Actions run |

## Sketches

| Sketch | Configs | Per-trial error | `asap_sketchlib` bound |
| --- | --- | --- | --- |
| HyperLogLog Classic, Ertl, HIP | `lg_k` 12, 14, 16 (the ones sketch-bench builds) | `estimate / truth − 1` | `Distinct`, a standard error with no δ, drawn at ±2 SE |
| KMV | `k` 1024, 4096, 16384 | `estimate / truth − 1` | `Distinct` at `δ = 0.05`; exact below k distinct keys |
| KLL, KLL CDF, KllDynamic | `k` 100, 200, 400 | rank error of the median query, compaction seed = trial + 1 | `Quantile`, `δ = 0.01` |
| DDSketch | `α` 0.005, 0.01, 0.02 | max relative value error over 101 quantiles | `Quantile`, `ε = α`, `δ = 0` |
| Count-Min | `w` 512, 1024, 2048; `d = 3` | error of the top key / N | `ItemFrequency`, `ε = e/w`, `δ = e^−d` |
| Count Sketch | `w` 256, 1024, 4096; `d = 3` | \|error\| of the top key / ‖f‖₂ | `ItemFrequency` at `δ = 0.01` |
| Space-Saving | `m` 512, 1024, 2048 | error of the top key / N | `ItemFrequency`, `ε = 1/m`, `δ = 0` |
| Count-Min, Count Sketch, UnivMon top-k | `w` 256, 1024, 4096; heap 32 | `1 − recall@k` | none: the `TopK` bound covers each reported count, not recall |
| UnivMon cardinality | heap `k` 16, 64, 256 | `estimate / truth − 1` | `Distinct` at `δ = 0.05` |
| UnivMon L1, L2, entropy | `w` 256, 1024, 4096 | `estimate / truth − 1` | `Total`, exact; `FrequencyL2`; none for `FrequencyEntropy` |
| Hydra over Count-Min, Count Sketch | cell `w` 256, 1024, 4096; grid 3 × 1024 | mean over subpopulations, as named on each figure | none: the bounds are per subpopulation, given its `N_Q`, `D_Q` or `‖f_Q‖₂` |
| Hydra over HyperLogLog | grid `w` 256, 1024, 4096 (sketch-bench has no cell precision) | as above | as above |
| Hydra over KLL, KLL CDF | cell `k` 100, 200, 400 | as above | as above |
| Hydra over UnivMon | cell `w` 64, 256, 1024 | as above | as above |

Each figure's legend names the contract `asap_sketchlib` returned, with its ε and δ.

## Known Limitations

This repo serves as a human-readable observer of `asap_sketchlib` error distributions.
Relying on `sketch-bench` as the benchmark component, this repo cannot guarantee that its results are always up to date.

### API change in `asap_sketchlib`

When there is a version bump, or another reason that causes the API to change in `asap_sketchlib`, `sketch-bench` needs time to change accordingly.
The lag between a source library and its benchmark also exists in other projects, like [DataSketches characterization](https://github.com/apache/datasketches-characterization), whose newest module pins datasketches-java 8.0.0 although 9.0.0 came out in December 2025, and [ann-benchmarks](https://github.com/erikbern/ann-benchmarks), whose hnswlib entry still builds a 2018 branch of `nmslib/hnsw`.

### Update in `asap_sketchlib`

When a new commit or another form of update appears in `asap_sketchlib`, human effort is necessary to rerun the characterization.
There is no guarantee that a new commit will work with `sketch-bench` (as an API change is possible).
Passing a new commit as a parameter to `sketch-bench` still faces the fundamental problem in the previous section.
Thus, having every new commit trigger a rerun of the characterization provides no extra benefit compared to a manual rerun.

### Conclusion

With the two limitations mentioned above, this repo is not guaranteed to be exactly up to date with `asap_sketchlib`.
A manual rerun when necessary is still expected at the moment.
If there is a good way to rerun automatically on updates in `asap_sketchlib`, adopting it would be good practice.
