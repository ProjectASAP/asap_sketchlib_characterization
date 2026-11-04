# asap_sketchlib_characterization

Error distributions of `asap_sketchlib` sketches over many independent trials, drawn against the library's theoretical error, in the style of the DataSketches characterization plots.

Each trial is one `approxbench sketchbench` run from [sketch-bench](../sketch-bench) at one stream length N.
Trials differ only in their data, so every trial sees a fresh key set.
At each N the report shades the share of trials the theoretical bound covers (95% where there is no bound) and draws the median.
The shaded area should stay inside the dashed theory lines.

## Run

Needs a built `approxbench` in `$SKETCH_BENCH_DIR/target/release` (default `../sketch-bench`). Python 3.10+, standard library only.

```bash
python3 characterize.py --trials 1024
python3 report.py results/<sha>
python3 cms_point_query.py
```

Each run directory is `results/<sha>`, the short commit of the `asap_sketchlib` that sketch-bench pins.
A crates.io release resolves to its tag's commit.
`meta.json` records the sketch-bench commit that ran each sketch.

`characterize.py` appends to `raw.jsonl` and skips trials already there, so it resumes after an interruption.
Options: `--sketches hll,kll`, `--lg-min/--lg-max` (N from 2^lg-min to 2^lg-max), `--ppo` (points per octave), `--workers`.

## Run on GitHub

Actions → **Characterize** → **Run workflow**.
It builds sketch-bench at `sketch_bench_ref`, runs one job per sketch and one for `cms_point_query`, merges them with `merge.py`, draws the report and commits `results/<sha>/` to the branch it ran on.
The raw trials (`raw.jsonl`, `cms_point_query.jsonl`) are not committed; they stay 90 days as the run's `results-<sha>` artifact.
Inputs: `trials`, `cms_trials`, `sketches` (empty runs all) and `publish` (off keeps the results as an artifact only).

## Files

| File | Contents |
| --- | --- |
| `grid.py` | the sketches, their configs, the data each trial sees, the per-trial error and the theory lines |
| `characterize.py` | runs the trials in parallel and writes `raw.jsonl` and `meta.json` |
| `merge.py` | merges run directories written by separate jobs |
| `report.py` | writes `summary.json` (quantiles per N), `index.html` and `figures/<sketch>_<config>.svg`, one standalone vector figure per sketch |
| `cms_point_query.py` | Count-Min in DataSketches' setup (w = 272, d = 3, one stream, a new hash per trial), one row per implementation; writes `cms_point_query.jsonl` and `figures/cms_point_query.svg` |
| `reference_datasketches_cms_point_query.tsv` | DataSketches' published CMS point-query results, drawn as a reference row |
| `results/<sha>/` | the runs against one `asap_sketchlib` commit |
| `.github/workflows/characterize.yml` | the GitHub Actions run |

## Sketches

| Sketch | Per-trial error | Theory |
| --- | --- | --- |
| HyperLogLog Classic, HIP, Ertl; KMV | `estimate / truth − 1` | ±2 RSE (`1.04/√m`, `√(ln 2)/√m`); KMV ±ε, Chernoff at `δ = 0.05` |
| KLL, KLL CDF, KllDynamic | rank error of the median query, compaction seed = trial + 1 | `2.296/k^0.9723`, 99% for one query |
| DDSketch | max relative value error over 101 quantiles | `α`, a hard bound |
| Count-Min | error of the top key / N | `e/w` with `δ = e^−d` |
| Count Sketch | \|error\| of the top key / ‖f‖₂ | `√(q/β)`, `q = 1/w`, `P_med(d, β) = 0.01` |
| Space-Saving | error of the top key / N | `1/m`, a hard bound |
| UnivMon cardinality, L2 | `estimate / truth − 1` | ±2 SD (`√(1.35/k)`); L2 ±ε at `δ = P_med(d, 0.1)` |
| UnivMon L1, entropy; heap top-k; Hydra | as named on each figure | none drawn |

The theory formulas are those in `asap_sketchlib` `docs/sketch_analytics.md`.

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
