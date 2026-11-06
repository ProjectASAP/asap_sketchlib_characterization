//! Reads a JSON array of queries on stdin and prints one `ErrorBound` (or
//! null) per query, from asap_sketchlib's `SketchAnalytics::theoretical_error`.
//!
//! A query: `{"algorithm": <SketchAlgorithm>, "statistic": <StatisticKind>,
//! "params": {..}, "data": {..}, "delta": <f64 or null>, "impl": <str>}`.
//! `impl` picks the type where one `SketchAlgorithm` covers several:
//! `classic` or `ertl` for HLL, `fast` or `regular` for the count matrices.

use std::io::Read;

use asap_sketchlib::analytics::*;
use asap_sketchlib::{
    Classic, CountMinSketch, CountSketch, DdSketch, ErrorBound, ErrorMetric, Ertl, FastPath,
    HyperLogLog, HyperLogLogHip, Kll, KllDynamic, Kmv, NormScale, RegularPath, SketchAlgorithm,
    SketchAnalytics, SpaceSaving, UnivMon, Vector2D,
};
use serde_json::{Value, json};

fn get<T: serde::de::DeserializeOwned>(v: &Value, key: &str) -> Result<T, String> {
    serde_json::from_value(v.get(key).cloned().ok_or(format!("missing {key}"))?)
        .map_err(|e| format!("{key}: {e}"))
}

fn opt<T: serde::de::DeserializeOwned>(v: &Value, key: &str) -> Result<Option<T>, String> {
    match v.get(key) {
        None | Some(Value::Null) => Ok(None),
        Some(x) => serde_json::from_value(x.clone()).map(Some).map_err(|e| format!("{key}: {e}")),
    }
}

fn error<S: SketchAnalytics>(
    q: &Value,
    params: S::Params,
    data: S::Data,
) -> Result<Option<ErrorBound>, String> {
    Ok(S::theoretical_error(get(q, "statistic")?, &params, &data, opt(q, "delta")?))
}

fn matrix(p: &Value) -> Result<MatrixParams, String> {
    Ok(MatrixParams { rows: get(p, "rows")?, cols: get(p, "cols")? })
}

fn bound(q: &Value) -> Result<Option<ErrorBound>, String> {
    let algorithm: SketchAlgorithm = get(q, "algorithm")?;
    let p = q.get("params").cloned().unwrap_or(json!({}));
    let d = q.get("data").cloned().unwrap_or(json!({}));
    let imp: Option<String> = opt(q, "impl")?;
    type Cm<M> = CountMinSketch<Vector2D<i32>, M>;
    type Cs<M> = CountSketch<Vector2D<i32>, M>;
    match (algorithm, imp.as_deref()) {
        (SketchAlgorithm::CountMinSketch, Some("fast")) => error::<Cm<FastPath>>(q, matrix(&p)?, ()),
        (SketchAlgorithm::CountMinSketch, Some("regular")) => error::<Cm<RegularPath>>(q, matrix(&p)?, ()),
        (SketchAlgorithm::CountSketch, Some("fast")) => error::<Cs<FastPath>>(q, matrix(&p)?, ()),
        (SketchAlgorithm::CountSketch, Some("regular")) => error::<Cs<RegularPath>>(q, matrix(&p)?, ()),
        (SketchAlgorithm::HLL, Some(estimator @ ("classic" | "ertl"))) => {
            let params = HllParams { precision: get(&p, "precision")? };
            let mut data = HllData::default();
            data.max_distinct = opt(&d, "max_distinct")?;
            if estimator == "classic" {
                error::<HyperLogLog<Classic>>(q, params, data)
            } else {
                error::<HyperLogLog<Ertl>>(q, params, data)
            }
        }
        (SketchAlgorithm::HLLHip, None) => {
            error::<HyperLogLogHip>(q, HllParams { precision: get(&p, "precision")? }, ())
        }
        (SketchAlgorithm::KMV, None) => {
            let mut data = DistinctData::default();
            data.distinct = opt(&d, "distinct")?;
            error::<Kmv>(q, KmvParams { k: get(&p, "k")? }, data)
        }
        (SketchAlgorithm::KLL | SketchAlgorithm::KLLDynamic, None) => {
            let params = KllParams { k: get(&p, "k")?, ..KllParams::default() };
            let mut data = StreamData::default();
            data.n = opt(&d, "n")?;
            if algorithm == SketchAlgorithm::KLL {
                error::<Kll<f64>>(q, params, data)
            } else {
                error::<KllDynamic<f64>>(q, params, data)
            }
        }
        (SketchAlgorithm::DDSketch, None) => error::<DdSketch>(q, DdParams { alpha: get(&p, "alpha")? }, Default::default()),
        (SketchAlgorithm::SpaceSaving, None) => {
            let mut data = SpaceSavingData::default();
            data.merged = opt(&d, "merged")?;
            error::<SpaceSaving>(q, SpaceSavingParams { capacity: get(&p, "capacity")? }, data)
        }
        (SketchAlgorithm::UnivMon, None) => {
            let params = UnivMonParams {
                heap_size: get(&p, "heap_size")?,
                rows: get(&p, "rows")?,
                cols: get(&p, "cols")?,
                layers: get(&p, "layers")?,
            };
            let mut data = FlowData::default();
            data.distinct = opt(&d, "distinct")?;
            error::<UnivMon>(q, params, data)
        }
        (a, i) => Err(format!("unsupported algorithm {a:?} with impl {i:?}")),
    }
}

fn metric(m: ErrorMetric) -> &'static str {
    match m {
        ErrorMetric::Absolute { scale: None } => "Absolute",
        ErrorMetric::Absolute { scale: Some(NormScale::StreamL1) } => "L1",
        ErrorMetric::Absolute { scale: Some(NormScale::StreamL2) } => "L2",
        ErrorMetric::Relative => "Relative",
        ErrorMetric::Rank => "Rank",
    }
}

fn main() {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).expect("read stdin");
    let queries: Vec<Value> = serde_json::from_str(&input).expect("stdin is a JSON array");
    let mut out = Vec::with_capacity(queries.len());
    for (i, q) in queries.iter().enumerate() {
        match bound(q) {
            Ok(b) => out.push(b.map_or(Value::Null, |b| {
                json!({"epsilon": b.epsilon, "delta": b.delta, "metric": metric(b.metric), "contract": b.contract})
            })),
            Err(e) => {
                eprintln!("query {i} {q}: {e}");
                std::process::exit(2);
            }
        }
    }
    println!("{}", Value::Array(out));
}
