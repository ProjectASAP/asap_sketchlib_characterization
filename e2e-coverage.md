# E2E accuracy checks mapped onto characterization figures

Rule: every E2E accuracy setting has a characterization figure with the same sketch, the same parameters and the same data shape. The figure shows the error distribution over many trials and draws the E2E threshold on it. The characterization may draw more than E2E, never less.

Source: the three inventories of `tests/e2e/*.rs` at `a05b35c` (727 accuracy rows, plus 4 borderline Octo rows not counted). sketch-bench state: `approxbench sketchbench --list-impls`, `sketch-bench/src/params.rs` and `aqpbm-core/src/accuracy/`.

## 1. Summary

| | settings |
|---|---|
| Distinct E2E accuracy settings | **149** |
| sketch-bench runs them today as-is | **33** |
| need a sketch-bench change | **111** |
| cannot be characterized (fixed fixture, nothing to resample) | **5** |

The 111 rows need these kinds of change (a row can need more than one):

| kind | rows that need it | rows it unblocks alone |
|---|---|---|
| A. per-key output from frequency comparators (and per group × value for Hydra) | 55 | 4 (15 more with B) |
| D. datagen stream shapes (order, planted keys, exponential, log-uniform, decrements, joint labels, …) | 28 | 11 |
| G. quantities the comparators do not report (F2, CDF sup distance, `count()`, estimated FPP, …) | 22 | 4 |
| B. counter type (i64/i128/f64) and FixedMatrix on RegularPath | 19 | 1 |
| E1. Octo plans and `run_octo` | 15 | 0 |
| E2. window frameworks (ExponentialHistogram, TumblingWindow, MicroCm, EH-UnivMon) | 14 | 6 |
| E4. small missing variants or insert modes (Bloom FastPath, CS-heap RegularPath top-k, row-level Nitro, …) | 14 | 3 |
| F. knobs not exposed (per-shard merge seed, KLL `m`, CSL2 `seed_index`) | 9 | 2 |
| C. HLL `lg_k` outside {12, 14, 16} | 4 | 4 |
| D-num. value dtypes beyond i64/u64/f64/string | 4 | 3 |
| E3. HashSketchEnsemble | 3 | 0 |
| H. weight column for Hydra cells | 3 | 2 |

The 5 that cannot be characterized: DDSketch rank-convention fixtures (Q6), DDSketch bucket-boundary probes (Q8), Hydra over 100 fixed records (F1), the deterministic EH sliding-window count (F18), and the 17-variant `DataInput` digest check (D1).

Structural or exact-by-construction tests (not rows): 231 in total, listed per family below.

## Conventions

- **Trials.** One trial is one sketch-bench run. Trials vary the data seed, and the sketch seed where the wrapper takes one (`seed=`). Every figure runs at least 100 trials per x point. Most E2E checks run one fixed hash on one realization. A fixed hash on freshly drawn keys samples the same randomness.
- **Documented inputs.** D1/D2: uniform i64 over [0, 1e7), N = 100K / 1M. D3/D4: Zipf(1.1) over 4096 keys. D5/D6: Zipf(1.1) over 20,000 keys. D7–D12: the same six shapes as f64 (own draws). D13: 100K uniform 3-char words. D14: 100K Zipf(1.1) over 4096 words. D15/D16: Normal(1000, 250), 100K / 1M. D17: Exponential(1e-3), 100K. D18: log-uniform on DDSketch bucket edges. All are datagen YAML specs except D17 and D18.
- **Stand-ins accepted as the same data shape.** Distinct identities = uniform i64 over [0, 1e12). Cyclic weights `1 + (i mod c)` = i.i.d. uniform integer weight in [1, c]. Round-robin labels `i mod 4` = uniform label over 4. Both keep weight and label independent of the key, which is what the sketch sees.
- **Counter type is part of the setting.** sketch-bench's CM, CS and heap wrappers build `i32` counters. An E2E sketch on `Vector2D<i64>` needs change B.
- **Symbols.** N stream mass, D distinct keys, f a key's count, F2 = Σf², d rows, w cols, P probed keys, m HLL registers.

## Figure templates

Each row's figure column names a template and its x axis.

- **F-card.** y = est/truth − 1 per trial. Theory ±2·RSE (RSE = 1.04/√m Classic/Ertl, √(ln 2/m) HIP). E2E line ±4·RSE, or the E2E's flat band.
- **F-cm.** Two panels per (d, w). Top: y = max over probed keys of (est − f)·w/(N − f). E2E line b = (P/1e-3)^(1/d). Theory line e. Bottom: y = share of probed keys with est − f > e(N − f)/w. E2E and theory line e^−d.
- **F-cs.** Two panels per (d, w). Top: y = max over probed keys of |est − f|·√w/√(F2 − f²). E2E line √κ, κ smallest with P[Bin(d, 1/κ) ≥ ⌈d/2⌉] ≤ 1e-3/P. Theory line √3. Bottom: share of keys above √(3/w)·√(F2 − f²). Line P[Bin(d, 1/3) ≥ ⌈d/2⌉] (0.259, 0.407, 0.210, 0.173, 0.145 at d = 3, 4, 5, 7, 9).
- **F-rank.** y = max rank error over the E2E's q set per trial. E2E line eps(k) = 2.446/k^0.9433. The share of trials above the line is printed next to the E2E's allowed share.
- **F-dd.** y = max relative value error over the 101-point grid (it contains every E2E q set). E2E line α (+ 8·ε_f64·(1 + |ln v|)).
- **F-recall.** y = 1 − recall@k. E2E line 1/k (E2E needs recall ≥ k − 1).
- **F-ratio.** y = est/truth. E2E band drawn as two lines.

## 2. Families

### 2.1 Cardinality (HLL, KMV, UnivMon cardinality)

Structural: 15 (cardinality.rs set aggregator and merge equalities), 0 in kmv.rs (its n < k exactness sub-checks are by construction).

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 1 | HLL Classic, Ertl, HIP × p ∈ {12, 14, 16}, DefaultXxHasher<br>`hll_{classic,ertl_mle,hip}_p{12,14,16}_*`, `*_custom_p{12,14,16}_*` (18 fns, 99 sketches) | distinct ids; core n ∈ {10, 1e2, …, 1e7}; custom lists p12 {400, 4K, 50K, 300K}, p14 {2K, 16K, 200K, 800K}, p16 {5K, 60K, 500K, 1.2M} | \|est−n\|/n ≤ 4·RSE: Classic/Ertl 0.065 / 0.0325 / 0.01625, HIP 0.0520 / 0.0260 / 0.0130 | `hll`, `hll-ertl`, `hll-hip`, `--config lg_k=12\|14\|16`, comparator `cardinality`, `--dataset uniform --cardinality 1000000000000 --dtype i64` | F-card, x = union of both n lists |
| 2 | same three estimators × p ∈ {10, 11, 13, 15, 17, 18}<br>`*_custom_p{10,11,13,15,17,18}_*` (18 fns, 69 sketches) | distinct ids; per-p lists, e.g. p10 {100, 1K, 20K, 200K}, p18 {10K, 100K, 1.5M} | 4·RSE: Classic/Ertl 0.13 … 0.0081, HIP 0.104 … 0.0065 | missing: `lg_k` outside {12, 14, 16} (C) | F-card, x = the E2E n list |
| 3 | HLL Classic p ∈ {12, 14, 16}<br>`hll_accuracy_improves_with_precision_*` (1 fn, 4 checks) | 6 blocks × 1M distinct ids | RMS rel. error ≤ 2·1.04/√m (0.0325 / 0.01625 / 0.008125); RSE(p12) ≥ 2·RSE(p16) | `hll --config lg_k=12\|14\|16`, N = 1M | F-card at N = 1M, x = p, RMS per p and line 2·1.04/√m; ratio printed |
| 4 | HLL Classic p ∈ {12, 14, 16}<br>`hll_classic_switchover_band_*` (1 fn, 3 checks) | 6 blocks × n = 2.5m distinct ids | RMS/(1.04/√m) ∈ [1.5, 10] | `hll --config lg_k=…`, N = 2.5m | x = n/m from 0.5 to 6, y = RMS/(1.04/√m), band [1.5, 10] at 2.5 |
| 5 | HLL Classic p ∈ {10, 13, 18}<br>`custom_precision_accuracy_improves_*` (1 fn, 1 check) | 200K distinct ids, same stream for all p | e18 ≤ e10 and e18 ≤ e13 | missing: `lg_k` 10, 13, 18 (C) | F-card at N = 200K, x = p |
| 6 | HLL ×3 × p ∈ {12, 14, 16}<br>`hll_*_zipf_p{12,14,16}_*` (9 fns, 18 sketches) | small: Zipf(1.05)/1500, 60K draws (D ≈ 1493); large: Zipf(0.6)/1.8M, 5M draws (D ≈ 1.49M) | \|est−D\|/D ≤ 4·RSE (as row 1) | `hll*` as row 1, zipf YAML spec (u64 ids, shift per trial) | F-card, x = {small, large} |
| 7 | HLL ×3 × p ∈ {10, 11, 13, 15, 17, 18}<br>`hll_*_zipf_p{10,…,18}_*` (18 fns, 36 sketches) | as row 6 | 4·RSE per p | missing: `lg_k` (C) | F-card, x = {small, large} |
| 8 | HLL ×3 × p ∈ {12, 14, 16}<br>`hll_p{12,14,16}_over_the_documented_inputs_*` (3 fns, 108 sketches) | D1–D12 | own 4·RSE and flat band (0.13 at p12, 0.046 at p14, 0.023 at p16) | `hll*` as row 1, D1–D12 specs | F-card, x = input, both lines |
| 9 | HLL ×3 × p ∈ {10, 11, 13, 15, 17, 18}<br>`hll_p{…}_over_the_documented_inputs_*` (6 fns, 216 sketches) | D1–D12 | own 4·RSE and flat band (0.13 / 0.046 / 0.023) | missing: `lg_k` (C) | F-card, x = input |
| 10 | UnivMon heap 128, rows 5, cols 2048, layers 16<br>`univmon_input_{1..12}_recovers_its_cardinality` (12 fns) | D1–D12, weight 1 | \|est−D\|/D ≤ 0.30 | `univmon-cardinality --config 'heap_size=128 sketch_row=5 sketch_col=2048 layer_size=16'`, comparator `keyed-cardinality`, weight column 1 | F-card, x = input; theory ±2·√(1.35/128); E2E ±0.30 |
| 11 | UnivMon heap 32, rows 5, cols 2048, layers 8<br>`a_pyramid_too_shallow_*` (1 fn) | D1 | est < 0.5·D (asserts failure) | `univmon-cardinality --config 'heap_size=32 sketch_row=5 sketch_col=2048 layer_size=8'` | F-ratio, x = N, line 0.5 |
| 12 | KMV k ∈ {64, 1024, 4096}<br>`kmv_estimates_stay_inside_*` (1 fn, 96 stochastic trials) | distinct ids, n ∈ {k, 2k, 8k, 32k} | \|est−n\|/n ≤ 4·√((n−k+1)/(n(k−2))); ≤ 2 failures of 144 | `kmv --config k=…`, uniform ids | F-card, x = n/k, E2E curve per k |
| 13 | KMV k = 512<br>`kmv_is_exact_below_k_and_estimates_at_k` (1 fn, 8 seeds) | n = k = 512 distinct ids | ≤ 0.007828 | `kmv --config k=512`, N = 512 | F-card at n = k |
| 14 | KMV k = 4096<br>`kmv_duplicates_are_inert_*` (1 fn) | 60K draws uniform over [0, 500K) (D = 56,507) | ≤ 0.06021 | `kmv --config k=4096`, `--dataset uniform --cardinality 500000 --size 60000` | F-card, x = N |
| 15 | KMV k ∈ {32, 128}<br>`kmv_k{32,128}_over_the_documented_inputs_*` (2 fns, 24 checks) | D1–D12 | own band (≈0.73 at k = 32, ≈0.356 at k = 128) and documented flat band | `kmv --config k=32\|128` | F-card, x = input |

### 2.2 Membership (Bloom)

Structural: 25 (membership.rs).

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 16 | Bloom RegularPath, k × w = 3 × 32768, 7 × 32768, 10 × 32768 (from `with_capacity(20000, 0.1 / 0.01 / 0.001)`)<br>`the_measured_false_positive_rate_matches_*` (1 fn, 3 checks) | 20,000 member keys; 200K absent probes | \|fpr − pred\| ≤ 5·√(p(1−p)/200000); pred 0.0954 / 0.00415 / 0.000396 | `bloom --config 'rows=3\|7\|10 cols=32768'`, comparator `membership` (100K non-member probes), 20K uniform ids | x = k, y = fpr − pred, E2E ±5σ (at the bench's probe count) |
| 17 | Bloom RegularPath 7 × 32768<br>`the_fill_based_estimate_tracks_*` (1 fn) | 20,000 members inserted 3× | 0.75 ≤ fpr/estimated_fpp ≤ 1.25 | missing: `estimated_fpp()` not reported (G) | F-ratio, y = fpr/estimated_fpp, band [0.75, 1.25] |
| 18 | Bloom FastPath, Packed64, 5 × 1024<br>`a_packed_64_geometry_*` (1 fn) | 300 members; 200K absent probes | \|fpr − 0.001059\| ≤ 3.6e-4; fpr ≤ 0.01 | missing: Bloom FastPath variant (E4) | x = members, y = fpr − pred, E2E ±5σ |

### 2.3 Frequency matrices (Count-Min, Count Sketch, CSL2, folds)

Structural: 1 (frequency.rs collision-free fold counts), 12 (matrix_instances.rs).

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 19 | CM FastPath `Vector2D<i64>` 4 × 4096; single pass and 3-way merge<br>`countmin_fast_path_zipf_conforms_*` (1 fn) | Zipf(1.1)/8192, N = 100K (D = 6508) | CountMinSpec: est ≥ f; est − f ≤ b(N−f)/w, b = 50.5; rate pin e^−4 | `cms-fastpath-vector2d --config 'rows=4 cols=4096'`, `--merge-shards 3 --merge-split interleaved`; missing: per-key output (A), i64 counters (B) | F-cm, x = N, single and merged |
| 20 | CM {Regular, Fast} × {`Vector2D<i64>`, FixMat i64}, d ∈ {3, 5, 7} × w ∈ {2048, 4096, 8192, 16384, 32768}<br>`countmin_{vec,mat}based_error_bound` (2 fns, 60 sketches) | Zipf(1.2)/512, N = 20K (D = 505) | CountMinSpec, P = 505: b = 79.6 / 13.8 / … at d = 3 / 5 / 7; rate e^−d | `cms-{fast,regular}path-vector2d`, `cms-fastpath-fixedmatrix --config 'rows=d cols=w'`; missing: A, B (i64, FixedMatrix on RegularPath) | F-cm, one panel per d, x = w |
| 21 | CS, same 4 storage × path and same 15-cell grid<br>`count_{vec,mat}based_error_bound` (2 fns, 60 sketches) | as row 20 | CountSketchSpec, P = 505: κ = 1231 / 171 / … at d = 3 / 5 / 7 | `countsketch-{fast,regular}path-vector2d`, `countsketch-fastpath-fixedmatrix`; missing: A, B | F-cs, one panel per d, x = w |
| 22 | CM `Vector2D<i32>` 3 × 4096, Regular and Fast<br>`countmin_regular_path_satisfies_*`, `countmin_fast_path_conforms_*` (2 fns, 12 sketches) | zipf/u64: Zipf(1.1)/8192, N = 120K (D ≈ 6930); uniform/f64: 4096 values, N = 120K | CountMinSpec, b = 190.7 (zipf) / 160 (uniform); rate e^−3 | `cms-{regular,fast}path-vector2d --config 'rows=3 cols=4096'`, u64 and f64 specs; missing: A | F-cm, x = N, one curve per stream |
| 23 | CS `Vector2D<i32>` 3 × 4096, Regular and Fast<br>`countsketch_both_paths_meet_the_l2_median_bound` (1 fn, 4 rows) | as row 22 | CountSketchSpec, κ ≈ 4560 (zipf) / 3505 (uniform); rate 0.259 | `countsketch-{regular,fast}path-vector2d --config 'rows=3 cols=4096'`; missing: A | F-cs, x = N |
| 24 | CS Regular `Vector2D<i64>` 5 × 4096<br>`countsketch_error_stays_rank_independent_*` (1 fn) | Zipf(1.1)/8192, N = 200K | max decile mean \|est−f\| ≤ 3 × min decile mean | `countsketch-regularpath-vector2d --config 'rows=5 cols=4096'`; missing: A, B | x = frequency decile, y = mean \|est−f\|, ratio line 3 |
| 25 | CSL2 4 × 2048, seed_index 11<br>`count_sketch_with_l2_norm_weighted_turnstile_*` (1 fn, 2 checks) | Zipf(1.3)/512, 30K arrivals, weight 1 + (i mod 5), then −10 on the hottest key | per-key CountSketchSpec (κ = 1749); \|F2̂ − F2\|/F2 ≤ √(6/2048) = 0.0541 | `count-sketch-l2-norm --config 'rows=4 cols=2048'`; missing: A, negative update (D), `seed_index` (F) | F-cs; second panel y = F2̂/F2 − 1, line ±0.0541 |
| 26 | CSL2 4 × 2048, seed_index 11<br>`countl2hh_input_{3..6,9..12}_*` (8 fns, 24 checks) | D3–D6, D9–D12, weight 1 + (i mod 5), hottest key decremented by 10% | per-key CountSketchSpec; hot key \|est−f\|/f ≤ 0.02; F2 rel. error ≤ 0.10 and ≤ 0.0541 | as row 25; missing: A, D, F | F-cs; hot-key panel (line 0.02); F2 panel (lines 0.0541, 0.10) |
| 27 | CM Fold rows 3, full_cols 4096, fold_level 4, top_k 20; 16 windows merged hierarchically (w = 256)<br>`folded_sketches_keep_their_own_bounds_*` (CM half) | Zipf(1.1)/10000, N = 240K in 16 windows of 15K | CountMinSpec at w = 256, b = 210 | `count-min-fold --config 'rows=3 full_cols=4096 fold_level=4 heap_size=20'`, `--merge-shards 16`; missing: A, hierarchical merge mode (E4) | F-cm at w = 256, x = N |
| 28 | CS Fold, same<br>(CS half of row 27's fn) | as row 27 | CountSketchSpec at w = 256, κ = 5270 | `count-sketch-fold`, same config; missing: A, E4 | F-cs at w = 256 |
| 29 | CM {Regular, Fast} × {`Vector2D<i64>`, FixMat i64}, 15-cell grid as row 20<br>`countmin_input_{1..12}_grid_*` (12 fns, 720 sketches) | D1–D12 | CountMinSpec, P = D (b = 463 at d = 3 on D1, 984 on D2) | as row 20; missing: A, B | F-cm, panels per d, x = w, one figure per input |
| 30 | CS, same grid<br>`countsketch_input_{1..12}_grid_*` (12 fns, 720 sketches) | D1–D12 | CountSketchSpec, P = D | as row 21; missing: A, B | F-cs, as row 29 |
| 31 | CM {Regular, Fast} × 10 storages: `Vector2D` i32/i64/i128/f64, FixedMatrix i32, DefaultMatrix i32/i64/i128 (3 × 4096), QuickMatrix i64/i128 (5 × 2048); single and 2-way merge<br>`countmin_{regular,fast}_path_instances_*` (2 fns, 20 sketches) | Zipf(1.1)/4096, N = 40K (D = 3138) | CountMinSpec, b = 146 (d = 3); rate e^−d | `cms-*-vector2d`, `cms-fastpath-fixedmatrix` cover i32 only; missing: A, B (counter types, named storages, FixedMatrix on RegularPath) | F-cm, x = storage type |
| 32 | CS {Regular, Fast} × 9 storages (row 31 minus f64)<br>`countsketch_{regular,fast}_path_instances_*` (2 fns, 18 sketches) | as row 31 | CountSketchSpec, κ = 3068 (d = 3) / 315 (d = 5) | as row 31 for CS; missing: A, B | F-cs, x = storage type |
| 33 | CM `Vector2D<i64>` {Regular, Fast}, d ∈ {1, 2, 3, 9} × w ∈ {64, 512, 4096, 8192}<br>`countmin_holds_its_contract_across_*` (1 fn, 32 sketches) | as row 31 | CountMinSpec; b = 3.1e6 / 1771 / 146 / 5.27 | `cms-{regular,fast}path-vector2d --config 'rows=d cols=w'`; missing: A, B | F-cm, panels per d, x = w |
| 34 | CM FastPath `Vector2D<i64>`, d ∈ {1, 2, 3, 9} × w ∈ {64, 512, 4096}<br>`countmin_mean_excess_falls_*` (1 fn, 8 pairs) | as row 31 | 2·mean excess(8w) ≤ mean excess(w) | `cms-fastpath-vector2d`, `aae_all`; missing: i64 counters (B) | x = w, y = mean excess (`aae_all`), line at half the previous point |
| 35 | CS `Vector2D<i64>` {Regular, Fast}, d ∈ {3, 5, 9} × w ∈ {64, 512, 4096, 8192}<br>`countsketch_holds_its_l2_contract_*` (1 fn, 24 sketches) | as row 31 | CountSketchSpec; κ = 3068 / 315 / 51.7 | `countsketch-{regular,fast}path-vector2d`; missing: A, B | F-cs, panels per d, x = w |
| 36 | CM `Vector2D<i64>` {Regular, Fast}, d = 3, w ∈ {3, 100, 1000, 4095}<br>`countmin_answers_a_non_power_of_two_width_*` (1 fn, 8 sketches) | as row 31 | CountMinSpec, b = 146 | `cms-*-vector2d --config 'rows=3 cols=w'`; missing: A, B | F-cm, x = w |
| 37 | CS `Vector2D<i64>` {Regular, Fast}, d = 5, w ∈ {3, 100, 1000, 4095}<br>`countsketch_answers_a_non_power_of_two_width_*` (1 fn, 8 sketches) | as row 31 | CountSketchSpec, κ = 315 | `countsketch-*-vector2d --config 'rows=5 cols=w'`; missing: A, B | F-cs, x = w |

### 2.4 Heavy hitters and top-k (heaps, Space-Saving, Elastic, Coco)

Structural: 31 (heavy_hitters.rs, 18 Space-Saving among them), 0 (topk.rs).

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 38 | CM + heap 32, {Regular, Fast} × 6 storages (`Vector2D` i32/i64, FixedMatrix i32, DefaultMatrix i32/i64 3 × 4096, QuickMatrix i64 5 × 2048)<br>`cmsheap_{regular,fast}_path_instances_*` (2 fns, 24 rows) | Zipf(1.1)/4096, N = 40K | per-key CountMinSpec; heap recall vs true top-32 ≥ 31 | recall: `cms-heap-topk-{regular,fast}path-vector2d --config 'rows=3 cols=4096 heap=32 topk_k=32'` (i32 only); missing: A, B | F-cm, x = storage; F-recall, x = storage |
| 39 | CS + heap 32, {Regular, Fast} × 9 storages (adds `Vector2D` i128, QuickMatrix i128, DefaultMatrix i128)<br>`csheap_{regular,fast}_path_instances_*` (2 fns, 36 rows) | as row 38 | per-key CountSketchSpec; recall ≥ 31 of 32 | recall: `countsketch-heap-topk-fastpath-vector2d` (i32 only); missing: A, B, CS-heap RegularPath top-k (E4) | F-cs and F-recall, x = storage |
| 40 | CM + heap Regular `Vector2D<i64>` 3 × 4096 top 16; CS + heap Regular 5 × 4096 top 16<br>`heaps_satisfy_their_own_bounds_*` (1 fn, 4 rows) | Zipf(1.1)/1024, N = 20K | per-key spec; recall ≥ 15 of 16 | `cms-heap-topk-regularpath-vector2d --config 'rows=3 cols=4096 heap=16 topk_k=16'`; missing: A, B, CS-heap RegularPath top-k (E4) | F-cm / F-cs; F-recall, x = N |
| 41 | CM + heap and CS + heap, Regular `Vector2D<i64>` 5 × 32768, top_k ∈ {32, 64, 128}<br>`heaps_on_input_{3..6,9..12}_hold_their_bounds` (8 fns, 48 rows) | D3–D6, D9–D12 | each heap count \|c−f\|/f ≤ 0.02; spec bound at heap keys (P = top_k); recall ≥ top_k − 1 | recall for CM: `cms-heap-topk-regularpath-vector2d --config 'rows=5 cols=32768 heap=k topk_k=k'`; missing: A, B, relative heap-count error (G), CS-heap RegularPath top-k (E4) | F-recall, x = top_k; y = max \|c−f\|/f, line 0.02 |
| 42 | Space-Saving capacity 256<br>`the_true_heavy_hitters_are_reported_exactly_*` (1 fn) | Zipf(1.1)/2048, N = 60K | top-20 keys and counts exact | `space-saving-topk --config 'capacity=256 topk_k=20'`, comparator `topk` (`recall_at_k`, `max_count_err`) | F-recall at k = 20 and y = `max_count_err`, E2E line 0 |
| 43 | Space-Saving capacity m ∈ {2, 8, 64, 1024, 2048}<br>`space_saving_input_{1..12}_holds_its_capacity_ceiling` (12 fns, 60 summaries) | D1–D12 | min_count ≤ N/m; every monitored key f ≤ est ≤ f + N/m | `space-saving --config capacity=m`; missing: A (monitored keys), `min_count` (G) | x = m, y = max (est − f)·m/N and min_count·m/N, E2E line 1 |
| 44 | CM, 4 storage × path, 15-cell grid as row 20, probed set = true top 1%<br>`countmin_input_{1..12}_heavy_hitters_*` (12 fns, 48 rows) | D1–D12 | CountMinSpec over top-1% keys | same runs as row 29; missing: A, B | F-cm restricted to top 1% |
| 45 | CS, same<br>`countsketch_input_{1..12}_heavy_hitters_*` (12 fns, 48 rows) | D1–D12 | CountSketchSpec over top-1% keys | same runs as row 30; missing: A, B | F-cs restricted to top 1% |
| 46 | Elastic heavy 256, light CM 3 × 4096<br>`elastic_passes_frequency_and_merge_conformance` (1 fn) | Zipf(1.1)/2048, N = 60K, string keys | absent key \|est\| ≤ eN/4096 = 39.8; dense keys (f ≥ 25) f ≤ est ≤ f + 39.8 | `elastic --config 'heavy_buckets=256 light_rows=3 light_cols=4096'`, `--dtype string`; missing: A, absent-key probe (G) | x = N, y = max (est − f) over dense keys, line eN/w |
| 47 | Elastic heavy 64, light 3 × 4096<br>`elastic_tracks_hot_flows` (1 fn) | 12K arrivals: 3 hot flows × 1200, rest over 977 bg keys | each hot flow within ±20% | `elastic --config 'heavy_buckets=64 light_rows=3 light_cols=4096'`; missing: planted flows (D), A | F-ratio per hot flow, band [0.8, 1.2] |
| 48 | Elastic `with_heavy_and_light(8, 1, 64)` and `(8, 3, 4096)`<br>`elastic_light_dimensions_set_the_error_*` (1 fn, 2 checks) | target × 50, then 20K distinct bg keys | wide: 50 ≤ est ≤ 100; narrow ≥ 4 × wide | `elastic --config 'heavy_buckets=8 light_rows=1\|3 light_cols=64\|4096'`; missing: planted target (D), A | y = target est, x = light geometry, lines 50 and 100 |
| 49 | Elastic heavy 16, light 3 × 4096<br>`elastic_never_underestimates_*` (1 fn) | Zipf(1.1)/4000, 60K draws, every 500th arrival an elephant | every flow est ≥ f; elephant ≤ f + e(N−f)/4096 | `elastic --config 'heavy_buckets=16 light_rows=3 light_cols=4096'`; missing: planted elephant (D), A | y = min (est − f) and elephant excess, lines 0 and e(N−f)/w |
| 50 | Elastic heavy 64, light 3 × 4096<br>`elastic_input_{3..6,9..12}_hot_flows_*` (8 fns) | D3–D6, D9–D12 with 3 hot flows injected (≈11% each) | each hot flow within ±20% | as row 47; missing: D, A | F-ratio, x = input, band [0.8, 1.2] |
| 51 | Coco d = 2, w = 128, seed per trial; single and merged<br>`coco_dense_key_mass_is_unbiased_*` (1 fn, 2 checks) | Zipf(1.1)/2048, N = 60K, string keys | mean over 48 seeds of summed estimate over 243 dense keys within 6.5·SE, 6.5·SE < 2% | `coco --config 'rows=2 cols=128 seed=t'`, `--merge-shards 2`; missing: A | y = summed dense estimate / truth − 1 per seed, E2E ±6.5·SE |
| 52 | Coco 2 × 32, seed per trial<br>`coco_point_estimates_are_unbiased_under_heavy_eviction` (1 fn) | 200 bg keys × 10 + target × 20 interleaved | mean target estimate over 800 seeds in [17, 23] | `coco --config 'rows=2 cols=32 seed=t'`; missing: planted target (D), A | y = target est per seed, mean marked, band [17, 23] |
| 53 | Coco 2 × 900, seed per trial<br>`coco_recall_meets_the_papers_*` (1 fn) | 5000 bg keys × 1 + heavy × 51 interleaved | share of 200 seeds recording the heavy flow ≥ 0.99 | `coco --config 'rows=2 cols=900 seed=t'`; missing: planted heavy (D), "is key recorded" (G) | y = recorded indicator per seed, share vs 0.99 and Theorem-4 0.99035 |

### 2.5 Quantiles (KLL, KllDynamic, DDSketch, UnivMonQ, numeric types)

Structural: 11 (quantiles.rs), 0 (numeric_types.rs). RANK_QS = {0, 0.01, 0.1, 0.5, 0.9, 0.99, 1}. "rank_streams": uniform, Normal(1000, 250), Zipf(1.1)/8192, 50-value discrete, monotonic, outside-in Normal. "dds_streams": log-uniform adversarial, Normal, Exponential(1e-3), uniform 1e6 + [0, 9e6), Zipf value grid, wide dynamic range.

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 54 | Kll and KllDynamic `<f64>`, k ∈ {64, 200, 800}, m = 8, single pass (update loop and `update_batch`, byte-identical)<br>Q1, Q2 SinglePass and BulkUpdate (72 trials per feed) | rank_streams, N = 30K | max rank error over RANK_QS ≤ eps(k) (0.0484 / 0.0165 / 0.00447); ≤ 7 of 72 | `kll-percall`, `kll-dynamic --config 'k=… seed=t'`, comparator `rank-error --quantiles 0,0.01,0.1,0.5,0.9,0.99,1`; as-is for uniform, Normal, Zipf; missing: monotonic, outside-in, 50-value f64 (D) | F-rank, x = shape, one panel per k |
| 55 | Kll and KllDynamic, k ∈ {64, 200, 800}, 4-shard merge (shard seeds differ)<br>Q1, Q2 ShardMerge | rank_streams, N = 30K, round-robin shards | as row 54 | `--operations merge --merge-shards 4 --merge-split interleaved`; missing: per-shard seed (F), shapes (D) | F-rank on `merge_accuracy` |
| 56 | Kll k ∈ {64, 256, 1024}<br>`kll_rank_error_shrinks_with_k_*` Q3, Q4 | uniform, N = 100K | worst over 4 seeds of max rank error at q ∈ {0.05, …, 0.95} ≤ eps(k); worst(64) ≥ 4·worst(1024) | `kll-percall --config 'k=… seed=t'`, `--quantiles 0.05,0.1,…,0.95` | F-rank, x = k, eps(k) curve; ratio printed |
| 57 | DDSketch α ∈ {0.001, 0.01, 0.05, 0.1}<br>`ddsketch_satisfies_the_relative_value_error_contract` Q5 (126 checks per α) | dds_streams, N ∈ {1K, 20K, 100K} | rel. value error ≤ α + slack | `dd --config alpha=…`, comparator `relative-value-error`; as-is for Normal and uniform; missing: log-uniform, exponential, Zipf value grid, wide-range (D) | F-dd, x = N, panel per α and shape |
| 58 | DDSketch α = 0.01 rank-convention fixtures<br>Q6 | 8 fixed (n, q) fixtures | ≤ 0.01 + slack | not characterizable (fixed fixture) | none |
| 59 | DDSketch α ∈ {0.001, 0.01, 0.05, 0.1}, endpoints<br>Q7 | 5000 log-uniform | q = 0 and q = 1 within α of exact min/max | `dd`; missing: log-uniform (D) | F-dd at q ∈ {0, 1} |
| 60 | DDSketch bucket-boundary probes<br>Q8 | one-sample sketches at γ^k edges | ≤ α + slack | not characterizable (fixed fixture) | none |
| 61 | DDSketch α ∈ {0.001, 0.01, 0.05, 0.1}, 4-shard merge and delta replay<br>Q9, Q10 | Zipf value grid [1e3, 1e7], N = 40K | ≤ α + slack | `dd`, `--merge-shards 4 --merge-split interleaved`; missing: Zipf value grid (D), delta replay mode (E4) | F-dd, single vs merged |
| 62 | UnivMonQ default (layers 10, top cols 4096, rows 5, heap 1024, ordered 1024, seed_index 5)<br>Q11, Q12 | keys 0..39 planted (i+1)·60 times + 20K uniform over 800 keys (N = 69,200) | per-key CountSketchSpec (5, 4096), κ = 202.8; F2 rel. error ≤ 0.0383 | `univmon-q-frequency` (default config); missing: planted keys (D), A, F2 (G) | F-cs; F2 panel, line 0.0383 |
| 63 | UnivMonQ default, seed_index 3 + t<br>Q13–Q15 (12 trials per regime) | 200K each: diffuse uniform; Zipf(1.4)/4096; mixture of Zipf(1.6)/60K and uniform | CDF sup distance ≤ η; quantile rank within ±η; ≤ 4 of 12 | `univmon-q-quantile --config 'seed_index=…'` (rank error only); missing: CDF sup distance and η (G), mixture (D) | y = sup distance / η per trial, line 1 |
| 64 | UnivMonQ default<br>Q16–Q18 | as row 62 | cardinality and entropy within ±10%; heavy_hitters(10) ≥ 8 of 10 | `univmon-q-cardinality`, `univmon-q-topk`; missing: entropy (G), planted keys (D) | F-ratio (band ±10%); F-recall at k = 10 |
| 65 | Kll k = 200, m ∈ {2, 4, 8, 16, 64}; k = 4 → (64, 64); k ∈ {8, 16, 32}<br>Q21, Q22, Q26 | uniform, N = 20K / 5K / 20K | `count()` within ±5% / ±15% | missing: `m` knob (F), `count()` (G) | F-ratio, y = count/n, x = m or k |
| 66 | Kll k = 200, m ∈ {8, 16, 64}<br>Q23 (18 trials) | rank_streams, N = 30K | max rank error ≤ 0.0165; ≤ 4 of 18 | `kll-percall --config 'k=200 seed=t'` is m = 8 only; missing: `m` (F), shapes (D) | F-rank, x = m |
| 67 | Kll k = 200, m ∈ {2, 4}<br>Q24 (12 trials) | rank_streams, N = 30K | max rank error ≤ 3·eps(200) = 0.0495 | missing: `m` (F) | F-rank, x = m, line 0.0495 |
| 68 | Kll k ∈ {8, 16, 32}, m = 8<br>Q25 (18 trials) | rank_streams, N = 20K | ≤ eps(k) = 0.344 / 0.179 / 0.0930; ≤ 4 of 18 | `kll-percall --config 'k=8\|16\|32 seed=t'`; as-is for uniform, Normal, Zipf; missing: other shapes (D) | F-rank, x = k |
| 69 | DDSketch α ∈ {1e-5, 1e-4, 0.3, 0.5, 0.9}<br>Q27 | dds_streams, N = 20K, indexable values only | ≤ α + slack | `dd --config alpha=…`; as-is for Normal and uniform; missing: other shapes (D) | F-dd, x = α |
| 70 | UnivMonQ default, entropy from g_sum<br>Q28 | uniform over 50K, N = 200K | within ±20% | missing: `estimate_entropy_from_g_sum` (G) | F-ratio, band [0.8, 1.2] |
| 71 | UnivMonQ default, rank from g_sum<br>Q29 | Zipf(1.2)/2048 values, N = 120K | \|rank err\| ≤ 0.25 at q ∈ {0.25, 0.5, 0.75} | missing: `estimate_rank_from_g_sum` (G) | y = rank error, line 0.25 |
| 72 | Kll `<f64>`, k ∈ {50, 200, 800}<br>Q30, Q31 | D15, D16 (Normal) | max rank error over {0, 0.1, …, 1} ≤ eps(k) | `kll-percall --config 'k=… seed=t' --quantiles 0,0.1,…,1`, normal spec | F-rank, x = N ∈ {100K, 1M} |
| 73 | Kll k ∈ {50, 200, 800}<br>Q32 | D17 (Exponential) | as row 72 | missing: exponential (D) | F-rank |
| 74 | DDSketch α ∈ {0.1, 0.01, 0.001}<br>Q33, Q34 | D15, D16 | ≤ α + slack | `dd --config alpha=…`, normal spec | F-dd, x = N |
| 75 | DDSketch α ∈ {0.1, 0.01, 0.001}<br>Q35, Q36 | D17; D18 (log-uniform on bucket edges) | ≤ α + slack | missing: exponential, log-uniform (D) | F-dd |
| 76 | Kll and KllDynamic, k ∈ {50, 200, 800}, single pass<br>`kll_family_on_input_{1..12}_*` Q37–Q48 (single-pass half) | D1–D12 | max rank error over {0, 0.1, …, 1} ≤ eps(k), 0 failures | `kll-percall`, `kll-dynamic --config 'k=… seed=t'` | F-rank, x = input |
| 77 | Kll and KllDynamic, k ∈ {50, 200, 800}, 4-shard merge<br>Q37–Q48 (merge half) | D1–D12 | as row 76 | `--merge-shards 4 --merge-split interleaved`; missing: per-shard seed (F) | F-rank on `merge_accuracy` |
| 78 | DDSketch α ∈ {0.1, 0.01, 0.001}, single and 4-shard merge<br>`ddsketch_on_input_{1..12}_*` Q49–Q60 | D1–D12, positive values | ≤ α + slack | `dd --config alpha=…`, `--merge-shards 4`; comparator drops exact zeros as E2E does | F-dd, x = input, single vs merged |
| 79 | Kll and KllDynamic `<T>`, k = 200, single, 2-shard merge, batch; 14 types (i8 … u128, isize, usize, f32, f64)<br>N1 (252 trials) | uniform over a per-type span, N = 20K | ≤ 0.0165; ≤ 13 of 252 | `kll-percall --dtype i64\|u64\|f64` covers 3 types; missing: other dtypes (D-num), per-shard seed (F) | F-rank, x = type |
| 80 | Kll and KllDynamic, k = 200, signed types (i8 … i128, isize, f32, f64)<br>N2, N3 (48 trials) | uniform over [−s, s) | ≤ 0.0165; ≤ 6 of 48; \|median\| ≤ 0.1·s | `--dtype i64\|f64` covers 2 types; missing: D-num | F-rank, x = type |
| 81 | DDSketch α ∈ {0.001, 0.01, 0.05} over 14 types<br>N4 | as row 79 | ≤ α + slack | `dd --dtype i64\|u64\|f64` covers 3 types; missing: D-num | F-dd, x = type |
| 82 | DDSketch α = 0.01 and Kll k = 200 on u128<br>N5, N6 (16 KLL trials) | 5000 values (v+1)·2^70 | DD ≤ 0.01 + slack; KLL ≤ 0.0165, ≤ 4 of 16 | missing: u128 dtype (D-num) | F-dd and F-rank |

### 2.6 Windows (ExponentialHistogram, TumblingWindow, MicroCm)

Structural: 13 (windows.rs). Every row needs the window-framework wrappers (E2).

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 83 | EH k = 8, window 1e6, over CM FastPath `Vector2D<i32>` 3 × 512; full-span query<br>W1 | Zipf(1.1)/2048, N = 10K | CountMinSpec (3, 512), b ≤ 127 | missing: EH wrapper (E2), A | F-cm, x = N |
| 84 | EH over CS FastPath 3 × 512<br>W2 | as row 83 | CountSketchSpec (3, 512), κ ≤ 2478 | missing: E2, A | F-cs, x = N |
| 85 | EH over CSL2 3 × 512 (seed_index 0)<br>W3 | as row 83 | as row 84 | missing: E2, A | F-cs |
| 86 | EH over HLL Ertl P14<br>W4 | uniform over 200K, N = 10K | ≤ 0.0325 | missing: E2 | F-card |
| 87 | EH over Kll k = 200 (12 trials)<br>W5 | uniform over 1e6, N = 10K | ≤ 0.0165 over 5 q; ≤ 4 of 12 | missing: E2 | F-rank |
| 88 | EH over DDSketch 0.01<br>W6 | 1e6 + uniform over 9e6, N = 10K | ≤ 0.01 + slack | missing: E2 | F-dd |
| 89 | EH over UnivMon (32, 5, 2048, 8)<br>W7 | Zipf(1.1)/2048, N = 10K | L2 in [0.9726, 1.0267]·L2 | missing: E2 | F-ratio |
| 90 | Tumbling CountSketchFold (3, 4096, fold 2, heap 32), window 500, 16 windows; views active / all / recent(2)<br>W8–W10 | Zipf(1.1)/512, N = 3000 | CountSketchSpec (3, 1024), κ ≤ 1239 | missing: E2, A | F-cs per view |
| 91 | Tumbling CountMinSketchFold (3, 4096, fold 2, heap 32), hierarchical query_all<br>W11 | as row 90 | CountMinSpec (3, fold_cols), b ≤ 80 | missing: E2, A | F-cm |
| 92 | EH k = 8, window 100, over CM `Vector2D<i32>` 3 × 2048<br>`eh_input_{3,4,5,6,14}_*` W12–W21 (5 fns, 10 checks) | D3–D6, D14 (100 or 1000 items per time unit) | est − f ≤ b(M − f)/2048 on the retained superset; heaviest key in the last 3/4 within 21% | missing: E2, A | F-cm; y = heavy-key rel. error, line 0.21 |
| 93 | MicroCm (4, 1024, t = 8, c = 2), count-based sub-windows of 1000<br>W22 | Zipf(1.1)/4096, N = 40K, last 8000 scored | CountMinSpec (4, 1024), b ≤ 45 | missing: E2, A | F-cm |
| 94 | Tumbling Kll (window 400, 16 windows, k = 200, pool 4); views all / recent(1) / active (16 trials) and retained mass<br>Q19, Q20 | uniform over 1e6, N = 4000 | ≤ 0.0165 over 5 q; ≤ 4 of 16; \|count − 4000\|/4000 ≤ 0.0165 | missing: E2 | F-rank per view; F-ratio of count |
| 95 | Tumbling Kll (window n/8, 32 windows), k ∈ {64, 200, 800}, `query_all`<br>Q1 TumblingMerge feed | rank_streams, N = 30K | as row 54 | missing: E2 (and D for 3 shapes) | F-rank |

### 2.7 Nitro

Structural: 9 (nitro.rs). RATES = {1, 0.5, 0.3, 0.1, 0.07, 0.01}, f(p) = round(1000/p), σ(f) = √(f((1−p)/p + p·r(1−r))), r = frac(1/p).

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 96 | NitroBatch over CM FastPath `Vector2D<i32>` 3 × 4096, live `update_batch`<br>P5, P6 (12 seeds per p) | one key × f(p) | `estimate_median` within f ± 4σ(f) (≤ 1 of 12); seed mean within 4σ/√12 | `nitro-count-min --config 'sample_rate=p rows=3 cols=4096 seed=t'`, comparator `frequency` (`aae_top1`), one-key spec (uniform over [0, 1)) | x = p, y = (est − f)/f, theory ±2σ/f, E2E ±4σ/f; seed mean marked |
| 97 | as row 96, `update_batch_cached_step`<br>P7, P8 | as row 96 | as row 96 | missing: cached-step insert mode (E4) | as row 96 |
| 98 | bare `NitroBatch<Vector2D<u32>>` 5 × 2048, row mass<br>P9, P10 | as row 96 | each row's mass within f ± 4σ(f) | missing: wrapper (E4), row mass (G) | as row 96, y per row |
| 99 | row-level Nitro (`enable_nitro_with_seed`) on CM FastPath 3 × 4096 and CS FastPath 3 × 4096, row mass<br>P1–P4 | as row 96 | as row 98 | missing: row-level wrapper (E4), row mass (G) | as row 98 |
| 100 | two seeded Nitro sketches merged: row-level CM and NitroBatch CM, 3 × 4096<br>M1, M2 (6 pairs per p) | one key × f(p) per shard | merged est within 2f ± 4σ(2f); ≤ 1 of 6 | `nitro-count-min --merge-shards 2`; missing: per-shard seed (F), row-level wrapper (E4) | x = p, y = (est − 2f)/2f, E2E ±4σ(2f)/2f |
| 101 | row-level CM Nitro 3 × 4096, p ∈ {1, 0.3, 0.1, 0.07}<br>Z1, Z2 | Zipf(1.1)/512, N = 200K | per key est ≥ f − 4σ(f); est ≤ f + b(N − f)/4096 + 4σ(N), b = 80 | missing: E4, A | x = p, top: max (f − est)/4σ(f), bottom: max (est − f)/(b(N−f)/w + 4σ(N)), E2E line 1 |
| 102 | row-level CM Nitro 3 × 4096, p ∈ {1, 0.5, 0.3, 0.1}<br>K1 | 16 keys round-robin, 20K each | each est in [20000 − 4σ, 20000 + 1845.6 + 4σ(N)] | missing: E4, A | as row 101 |

### 2.8 Frameworks: Hydra, UnivMon, ensembles, Octo

Structural: 14 (frameworks.rs), 4 (composition.rs, UnivMonQ config and exact aggregates), 55 (octo.rs). Hydra rows use `--group-columns` for the mask and `--per-group-out` for per-group errors.

**Hydra**

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 103 | Hydra 4 × 4096, cells CM 4 × 4096, labels (region, user)<br>F1 | 100 fixed records | full keys ±2, wildcards [50, 61], unseen ≤ 1 | not characterizable (fixed fixture) | none |
| 104 | Hydra 4 × 512, cells Kll k = 200, one label<br>F2, F19 | uniform over 1e6, N = 20K, one subpopulation | median in rank ±0.03; \|CDF − F\| ≤ 0.0165 at 5e5 and at 5 points | `hydra-kll --config 'rows=4 cols=512 cell_k=200 seed=t' --quantiles 0.5`; `hydra-kll-cdf` (its own x grid) | F-rank with lines 0.03 and 0.0165 |
| 105 | Hydra 4 × 512, cells HLL Ertl P14, label tenant<br>F3 | 2 tenants × 500 ids | each in [450, 550] | `hydra-hll --config 'rows=4 cols=512'`, ≈500 distinct ids per tenant | F-card per group, band ±10% |
| 106 | Hydra 5 × 8192, cells CM FastPath 3 × 64, label = key<br>F4 | Zipf(1.1)/256, N = 40K, constant value | absent ≤ 4; keys with c ≥ 25: c ≤ est ≤ 1.01c + 4 | `hydra-cms --config 'rows=5 cols=8192 cell_rows=3 cell_cols=64'`, comparator `subpop-frequency`, `--per-group-out` | x = N, y = max over groups (est − c − 4)/(0.01c), line 0 |
| 107 | Hydra 5 × 8192, cells CS FastPath 3 × 64<br>F5 | as row 106 | 0.94c − 25 ≤ est ≤ 1.06c + 25 | `hydra-cs`, same config | as row 106 |
| 108 | Hydra 5 × 4096, cells CM / CS 3 × 64, labels (src, dst, status), value = endpoint<br>F6, F7, F8, F13 | `labelled_stream`, N = 12K / 30K; F7, F8 weighted 1 + (i mod 7) | per (subpop × endpoint) with c ≥ 25: CM exact; CS \|est − c\| ≤ 0.06c + 25 | `hydra-cms`, `hydra-cs --group-columns …`; missing: per (group, value) output (A), Hydra weights (H) | y = max over pairs of \|est − c\| (CM) or excess over 0.06c + 25 (CS), line 0 |
| 109 | Hydra 5 × 128, cells Kll k = 200, labels (region, service), 8 subpops<br>F11 | Normal(500, 80), N = 40K | per (subpop, q) within quantile_band(q, 0.0165) | `hydra-kll --config 'rows=5 cols=128 cell_k=200 seed=t' --group-columns 0,1 --quantiles 0.1,0.25,0.5,0.75,0.9` | F-rank per group |
| 110 | as row 109, weighted 1 + (i mod 4)<br>F9 | Normal(500, 80), N = 20K | as row 109 on the weighted truth | missing: Hydra weights (H) | F-rank per group |
| 111 | Hydra 5 × 128, cells HLL Ertl P14, 8 subpops<br>F10 | ids Zipf(0.2)/20K, N = 40K | each within ±3% | `hydra-hll --config 'rows=5 cols=128' --group-columns 0,1` | F-card per group, band ±3% |
| 112 | Hydra 5 × 4096 and 5 × 256, cells CM 3 × 64, labels (region, device, os), 7 masks<br>F12a, F12b | combo Zipf(1.1)/192 decoded to 8 × 6 × 4, N = 120K | share of subpops with est − G ≤ (4/cols)·G_s above 0.8965 | `hydra-cms`, one run per mask; missing: joint label distribution (D) | y = share in bound, line 0.8965, x = cols |
| 113 | Hydra 5 × 128, cells UnivMon (32, 5, 256, 8)<br>F14 | items Zipf(1.2)/1000, N = 40K, weight 1 + (i mod 7) | L2 ±5%, entropy ±12% per subpop | `hydra-univmon-l2-norm`, `hydra-univmon-entropy`; missing: Hydra weights (H) | F-ratio per group |
| 114 | Hydra shard merge: cells Kll k = 200 and UnivMon (32, 5, 256, 8), 5 × 256<br>F15a, F15b | shard-dependent values: Normal(300, 20) vs Normal(700, 20); items Zipf(1.2)/800 | KLL q in band 0.0165; L2 in [0.9203, 1.0738] | `--merge-shards 2`; missing: shard-conditional mixture (D) | F-rank and F-ratio on `merge_accuracy` |
| 115 | Hydra 4 × 4096, cells CM 4 × 4096, labels (region, word)<br>F33, F34 | D13, D14 words, region uniform over 4 | full key \|est − c\| ≤ 1000, est ≥ c; in-bound share > 0.9492; region c ≤ est ≤ 1.2c + 1; unseen ≤ 100 | `hydra-cms --dtype string --key-len 3 3`; missing: per (group, value) output (A) | y = in-bound share, line 0.9492; y = max error, line 1000 |
| 116 | Hydra 4 × 512, cells Kll k = 200, shard uniform over 4<br>F35, F36 | D7, D8 | median rank ±0.03; CDF at 9 deciles within 0.03 | `hydra-kll --config 'rows=4 cols=512 cell_k=200 seed=t'`, `hydra-kll-cdf` | F-rank per shard, line 0.03 |
| 117 | Hydra 4 × 512, cells HLL Ertl P14, tenant uniform over 4<br>F37, F38 | D1, D2 | rel. error ≤ 0.0325 and ≤ 0.10 | `hydra-hll --config 'rows=4 cols=512'` | F-card per tenant |

**UnivMon**

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 118 | UnivMon (32, 5, 2048, 8), `update_weighted`<br>F16 | Zipf(1.2)/1000, N = 20K, weights 1..7 | L2 in [0.9726, 1.0267]; entropy ±12%; cardinality ±6% | `univmon-{l2-norm,entropy,cardinality} --config 'heap_size=32 sketch_row=5 sketch_col=2048 layer_size=8'`, keyed comparators | F-ratio per quantity |
| 119 | UnivMon `update_weighted_terminal` path, (32, 5, 2048, 8) and (32, 5, 2048, 16)<br>F16, F21–F32 terminal L2 | F16 stream; D1–D12 weights 1..7 | L2 ±15% (F16), ±18% (inputs) | missing: terminal insert path (E4) | F-ratio |
| 120 | UnivMon (32, 5, 2048, 8) g-sum<br>F20 | as row 118 | √g_sum(x²) within ±15% of √F2; g_sum(x) within ±50% of L1 | missing: `g_sum` (G) | F-ratio |
| 121 | UnivMonTwoTier (128, 8, 3, 2048, 3, 512, 16)<br>F17 | Zipf(1.3)/800, N = 15K, weights 1..3 | L2 ±15%; cardinality ±20% | `univmon-two-tier-{l2-norm,cardinality}` with that config | F-ratio |
| 122 | UnivMon (32, 5, 2048, 16) and TwoTier defaults (32, 8, 3, 2048, 3, 512, 16)<br>`univmon_family_on_input_{1..12}_*` F21–F32 | D1–D12, weights 1..7 | entropy [0.88, 1.15]; L2 ±11% (UnivMon), ±15% (TwoTier); cardinality ±30% | `univmon-{entropy,l2-norm,cardinality}`, `univmon-two-tier-{l2-norm,cardinality}` | F-ratio, x = input |
| 123 | EH k = 8, window 100, over CM 3 × 2048<br>F18 | `"req"` at every t ≡ 0 mod 3 | interval count in [26, 40] | not characterizable (deterministic stream) | none |

**HashSketchEnsemble**

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 124 | Ensemble [CM 3 × 4096, CS 3 × 4096, HLL Ertl / Classic / HIP P14], FastPath `Vector2D<i32>`<br>C1, C2 | Zipf(1.1)/2048, N = 40K | HLL ≤ 0.0325 / 0.0325 / 0.0260 on the ensemble hash; CM and CS specs | missing: ensemble wrapper (E3), A | F-card per HLL; F-cm; F-cs |
| 125 | Ensemble [CM i32 3 × 4096, CM i64 3 × 2048, CS 3 × 4096]<br>C3 | as row 124 | CountMinSpec (3, 4096) and (3, 2048); CountSketchSpec (3, 4096) | missing: E3, A | F-cm, F-cs |
| 126 | Ensemble [CM 3 × 4096, HLL Ertl P14]<br>`ensemble_input_{1..12}_*` C4–C15 | D1–D12 | CountMinSpec (3, 4096); HLL ≤ 0.0325 | missing: E3, A | F-cm and F-card, x = input |

**Octo**

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 127 | Octo HLL Classic P14 (delta round trip, `run_octo`, both routes); registers equal the single-pass sketch<br>O1, O3, O19a, O19b | 100K / 200K distinct; Zipf(1.1)/1024, N = 60K | < 0.025 (O1, O3); ≤ 0.0325 (O19) | `hll --config lg_k=14` (register-equal by construction) | F-card, x = N, lines 0.025 and 0.0325 |
| 128 | Octo DD α = 0.01 after flush, both routes; buckets equal the single-pass sketch<br>O20a, O20b | 1 + key, Zipf(1.1)/1024, N = 60K | ≤ 0.01 + slack at RANK_QS | `dd --config alpha=0.01`, zipf spec shifted by 1 | F-dd |
| 129 | single-pass UnivMon (64, 5, 4096, 8)<br>O21 | Zipf(1.1)/1024, N = 60K | F2 rel. error ≤ √(6/4096) = 0.0383 | `univmon-l2-norm --config 'heap_size=64 sketch_row=5 sketch_col=4096 layer_size=8'`, F2 = L2² | F-ratio of F2, band ±0.0383 |
| 130 | `run_octo` CM 5 × 4096, 4 workers, HashByKey, flushed<br>O2 | Zipf(1.1)/4096, N = 200K | est ≤ f + eN/4096 for all 4096 keys | missing: Octo (E1), A | F-cm (bottom panel at share 0) |
| 131 | `run_octo` CS 5 × 4096, flushed<br>O4 | Zipf(1.1)/2048, N = 200K | top-64 \|est − f\| ≤ 3‖f‖₂/64 | missing: E1, A | F-cs over top-64 |
| 132 | OctoCm 5 × 4096, τ = 31, unflushed, both routes<br>O5a, O5b | Zipf(1.1)/8192, N = 400K | share with \|est − f\| > (2/4096)·L1 < 2^−5; worst under-estimate < 124 | missing: E1, A | y = share, line 0.03125; y = worst deficit, line 124 |
| 133 | OctoCs 5 × 4096, τ = 31, both routes<br>O6a, O6b | Zipf(1.1)/8192, N = 400K | share above √(8/4096)·L2 < 0.03125; gap to single core < 124 | missing: E1, A | as row 132 |
| 134 | OctoCm 3 × 1024, 4 workers vs MergeCm (1×, 10×, periods 500–4000)<br>O7, O8 | Zipf(1.1)/4096, N = 60K; Zipf(1.1)/2048, N = 40K | merge MAE > 2·octo MAE; octo mean deficit ≤ 31 | missing: E1, mid-stream query points (G) | x = query point, y = MAE per system, E2E ratio lines |
| 135 | OctoCs 5 × 1024 vs MergeCs<br>O9 | Zipf(1.1)/4096, N = 60K | octo < parity/2; octo < 10× | missing: E1, G | as row 134 |
| 136 | OctoHll P14 vs MergeHll<br>O10 | 200K distinct | octo < parity, octo < 10× | missing: E1, G | as row 134 |
| 137 | OctoDd 0.01, τ ∈ {1, 2, 4, 8}<br>O11 | Exponential(0.05), N = 200K | error at τ = 1 equals ideal; non-decreasing in τ | missing: E1, G, exponential (D) | x = τ, y = mean rel. value error |
| 138 | OctoUniv (5, 1024, 12), τ = 31 vs MergeUniv<br>O12 | Zipf(1.1)/4096, N = 60K | mean top-16 recall > 0.9 and ≥ merge | missing: E1, G | F-recall per query point |
| 139 | OctoCoco 2 × 64, 1 worker, flushed (120 seeds)<br>O13 | Zipf(1.1)/1000, N = 20K, string keys | summed top-32 estimate within 5·SE, 5·SE < 2% | missing: E1, A | y = sum/truth − 1 per seed, ±5·SE |
| 140 | OctoCoco 2 × 512, 4 workers vs MergeCoco<br>O14 | Zipf(1.1)/5000, N = 200K, 3 streams | octo ARE < merge/2; octo ARE < 0.10; F1 > merge | missing: E1, G | as row 134 |
| 141 | OctoElastic 1024 / 3 × 4096 vs MergeElastic<br>O15 | Zipf(1.1)/5000, N = 300K | octo ARE < merge/2, < 0.06; F1 > 1.2·merge | missing: E1, G | as row 134 |
| 142 | Octo top-k plan CM + heap 5 × 2048, heap 32, both routes<br>O16a, O16b, O18a, O18b | Zipf(1.1)/8192, N = 200K | est ≥ f − 124; CountMinSpec (5, 2048); recall of top-32 above 124 = 100% | missing: E1, A | F-cm widened by 124; F-recall |
| 143 | Octo top-k plan CS + heap 5 × 2048, both routes<br>O17a, O17b, O18c, O18d | as row 142 | CountSketchSpec (5, 2048) + 124; recall 100% | missing: E1, A | F-cs widened by 124; F-recall |
| 144 | OctoCoco 2 × 128, 4 workers, both routes (32 seeds)<br>O22a, O22b | Zipf(1.1)/1024, N = 60K | summed top-32 within 6.5·SE, 6.5·SE < 2% | missing: E1, A | as row 139 |

### 2.9 Experimental and other

Structural: 13 (experimental.rs), 13 (data_input.rs), 15 (wire.rs, no accuracy checks).

| # | setting | stream | E2E quantity and threshold | sketch-bench | proposed figure |
|---|---|---|---|---|---|
| 145 | UniformSampling rate ∈ {0.5, 0.1, 0.01} (24 seeds)<br>E1 | values i^1.7, i < 20K | \|sample mean − μ\| ≤ 4σ_mean (2.3% / 6.9% / 22.8% of μ); ≤ 2 of 24 | `uniform-sampling --config 'sample_rate=… seed=t'`; missing: i^1.7 values (D), sample mean (G) | x = rate, y = (mean − μ)/σ_mean, E2E ±4 |
| 146 | ExponentialHistogramUnivMon (k = 2, window 1e8, 32, 3, 512, 2)<br>E2–E4 | Zipf(1.1)/30000, N = 80K | L2 ±10%; entropy [0.90, 1.40]; cardinality < 0.1·D (documented failure) | missing: E2 | F-ratio per quantity |
| 147 | CountMinHll 4 × 512, precision 10<br>E5 | 120 keys, key k has 40 + 37k distinct values | collision-free keys ≤ 0.13 | `count-min-hll --config 'rows=4 cols=512 precision=10'`; missing: per-key distinct schedule (D) | F-card per key, ±0.13 |
| 148 | CountMinHll 4 × 32, precision 10<br>E6 | 200 keys, 40 + 37k distinct values | est ≥ 0.87·n per key | as row 147, `cols=32`; missing: D | y = min est/n, line 0.87 |
| 149 | CountSketch Regular `Vector2D<i64>` 5 × 4096 over 17 `DataInput` variants<br>D1 | 200 inserts per variant | \|est − 200\| ≤ 60 | not characterizable (fixed fixture) | none |

## 3. sketch-bench changes, ordered by rows unlocked

"Needs" counts the rows that require the change. "Alone" counts the rows that become runnable with this change only.

| # | change | needs | alone | rows |
|---|---|---|---|---|
| 1 | **A. Per-key output.** A `--per-key-out` CSV (key, true count, estimate) for the `frequency` comparator, the heap and Space-Saving per-key rows, and per (group, value) for `subpop-frequency`. The figure scripts then compute max normalized error, exceedance shares, top-1% and dense-key subsets, deciles and absent keys. | 55 | 4 | 19–33, 35–41, 43–52, 62, 83–85, 90–93, 101, 102, 108, 115, 124–126, 130–133, 139, 142–144 |
| 2 | **D. Datagen stream shapes.** Stream order (monotonic, outside-in); 50-value discrete f64; Exponential; log-uniform on DDSketch edges; Zipf rank → value-grid map; wide dynamic range; planted keys and flows (hot flows, single target, interleaved heavy, keys with planted counts); a final negative update; per-key distinct-value schedule; joint label distribution; shard-conditional mixture; mixture of two distributions; values i^1.7. | 28 | 11 | 25, 26, 47–50, 52–55, 57, 59, 61–64, 66, 68, 69, 73, 75, 95, 112, 114, 137, 145, 147, 148 |
| 3 | **G. Reported quantities.** F2 for UnivMonQ; relative heap-count error; Bloom `estimated_fpp`; KLL `count()`; UnivMonQ CDF sup distance and η; UnivMonQ entropy; `g_sum` estimators (UnivMon, UnivMonQ entropy and rank); Space-Saving `min_count`; absent-key probe; Coco "key recorded"; Nitro row mass; sample mean; mid-stream query points for the Octo online comparisons. | 22 | 4 | 17, 41, 43, 46, 53, 62–65, 70, 71, 98, 99, 120, 134–138, 140, 141, 145 |
| 4 | **B. Counter type and storage.** A `counter=i32\|i64\|i128\|f64` knob on CM, CS and heap wrappers; FixedMatrix on RegularPath; DefaultMatrix and QuickMatrix storages. With A it unlocks 15 rows. | 19 | 1 | 19–21, 24, 29–41, 44, 45 |
| 5 | **E1. Octo.** Plans for CM, CS, HLL, DD, UnivMon, Coco, Elastic, CM + heap and CS + heap; `run_octo` with workers, route (HashByKey, RoundRobin), τ and flush; merge-baseline runners. | 15 | 0 | 130–144 |
| 6 | **E2. Window frameworks.** ExponentialHistogram over CM, CS, CSL2, HLL, KLL, DD and UnivMon; TumblingWindow over KLL, CountSketchFold and CountMinSketchFold with view selection; MicroCm; ExponentialHistogramUnivMon. | 14 | 6 | 83–95, 146 |
| 7 | **E4. Small variants and insert modes.** Bloom FastPath (Packed64); CS + heap RegularPath top-k; fold hierarchical merge; DD delta replay; Nitro cached-step mode, bare NitroBatch and row-level Nitro; UnivMon terminal insert path. | 14 | 3 | 18, 27, 28, 39–41, 61, 97–102, 119 |
| 8 | **F. Knobs.** Per-shard seed derivation for merge (KLL, KllDynamic, Nitro); KLL minimum compactor capacity `m`; CSL2 `seed_index`. | 9 | 2 | 25, 26, 55, 65–67, 77, 79, 100 |
| 9 | **C. HLL precision.** Compile HLL storages for `lg_k` 10, 11, 13, 15, 17, 18. | 4 | 4 | 2, 5, 7, 9 |
| 10 | **D-num. Value dtypes.** i8, i16, i32, i128, isize, u8, u16, u32, u128, usize, f32 for KLL, KllDynamic and DDSketch. | 4 | 3 | 79–82 |
| 11 | **E3. HashSketchEnsemble wrapper.** | 3 | 0 | 124–126 |
| 12 | **H. Hydra weights.** A weight column for `hydra-cms`, `hydra-cs`, `hydra-kll` and `hydra-univmon-*`. | 3 | 2 | 108, 110, 113 |

The rows that today run as-is (33): 1, 3, 4, 6, 8, 10–16, 42, 56, 72, 74, 76, 78, 96, 104–107, 109, 111, 116–118, 121, 122, 127–129.
