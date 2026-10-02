// DeepAlpha：严格 / 宽松口径的逐根扫描整段搬进 Rust。
//
// 原先 Python 侧每根 K 线调一次 `update_signals`、再读信号字典、拆字符串、必要时拷贝整份笔列表，
// 2000 根日线要跨 Python / Rust 边界上万次，且时间解析走 pandas。这里一次调用做完：
// 建 K 线（直接解析时间字符串）→ 逐根推进 → 提取买卖点事件 → 记录笔完成 / 成笔时刻，
// 只把「事件列表 + 两张笔时间表」交回 Python；计算期间释放 GIL，雷达可多线程并行扫描多只股票。
use super::trader::czsc_signals::parse_signals_config;
use chrono::{DateTime, NaiveDate, NaiveDateTime, Utc};
use czsc_core::objects::bar::{RawBar, RawBarBuilder};
use czsc_core::objects::freq::Freq;
use czsc_core::objects::market::Market;
use czsc_trader::czsc_signals::CzscSignals;
use czsc_trader::sig_parse::SignalConfig;
use czsc_utils::bar_generator::BarGenerator;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyList;
use std::collections::{HashMap, HashSet};
use std::str::FromStr;

/// 事件：（类型, 亮起 K 线时间, 所属笔终点时间, 所属笔终点价, 一类命中的笔数 span, dp_trend_legs 原始信号值）
type ScanEvent = (String, String, String, f64, String, Option<String>);

/// 项目时间字符串 → UTC（朴素时间按 UTC 解释，与 Python 侧 `pd.Timestamp(time)` 喂给 czsc 的口径一致）
fn parse_dt(s: &str) -> Result<DateTime<Utc>, String> {
    let t = s.trim();
    for f in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"] {
        if let Ok(n) = NaiveDateTime::parse_from_str(t, f) {
            return Ok(n.and_utc());
        }
    }
    NaiveDate::parse_from_str(t, "%Y-%m-%d")
        .map(|d| d.and_hms_opt(0, 0, 0).unwrap().and_utc())
        .map_err(|_| format!("无法解析时间: {s}"))
}

/// 与 Python `ts_date` 同口径：零点输出 YYYY-MM-DD，否则 YYYY-MM-DD HH:MM
fn fmt_ts(dt: DateTime<Utc>) -> String {
    let n = dt.naive_utc();
    if n.format("%H:%M").to_string() == "00:00" {
        n.format("%Y-%m-%d").to_string()
    } else {
        n.format("%Y-%m-%d %H:%M").to_string()
    }
}

fn sig_type(v1: &str) -> Option<&'static str> {
    Some(match v1 {
        "一买" => "buy1",
        "一卖" => "sell1",
        "二买" => "buy2",
        "二卖" => "sell2",
        "三买" => "buy3",
        "三卖" => "sell3",
        _ => return None,
    })
}

#[allow(clippy::too_many_arguments)]
fn scan(
    symbol: &str,
    freq: Freq,
    label: &str,
    times: &[String],
    opens: &[f64],
    highs: &[f64],
    lows: &[f64],
    closes: &[f64],
    vols: &[f64],
    configs: &[SignalConfig],
    keys: &[String],
    track_bis: bool,
    legs_key: Option<&str>,
    init_n: usize,
) -> Result<(Vec<ScanEvent>, Vec<(String, String)>, Vec<(String, String)>), String> {
    let n = times.len();
    if n <= init_n {
        return Ok((vec![], vec![], vec![]));
    }
    let mut raw: Vec<RawBar> = Vec::with_capacity(n);
    for i in 0..n {
        let bar = RawBarBuilder::default()
            .symbol(symbol)
            .dt(parse_dt(&times[i])?)
            .freq(freq)
            .id(i as i32)
            .open(opens[i])
            .close(closes[i])
            .high(highs[i])
            .low(lows[i])
            .vol(vols[i])
            .amount(closes[i] * vols[i])
            .build()
            .map_err(|e| format!("构造 RawBar 失败: {e}"))?;
        raw.push(bar);
    }
    let mut bg = BarGenerator::new(freq, vec![], n + 1, Market::Default).map_err(|e| e.to_string())?;
    bg.init_freq_with_bars(freq, raw[..init_n].iter().cloned())
        .map_err(|e| e.to_string())?;
    let mut cs = CzscSignals::new(symbol.to_string(), bg);

    let mut prev: HashMap<&str, String> = keys.iter().map(|k| (k.as_str(), "其他".to_string())).collect();
    let mut seen: HashSet<(&'static str, String)> = HashSet::new();
    let mut events: Vec<ScanEvent> = Vec::new();
    let (mut done, mut started): (Vec<(String, String)>, Vec<(String, String)>) = (vec![], vec![]);
    let (mut done_seen, mut started_seen): (HashSet<String>, HashSet<String>) = (HashSet::new(), HashSet::new());

    for bar in &raw[init_n..] {
        cs.update_signals(bar, configs).map_err(|e| format!("update_signals 失败: {e}"))?;
        let day = fmt_ts(bar.dt);
        if track_bis {
            // 笔完成 / 成笔时刻：当根 K 线上末笔的终点、起点第一次出现的那根（setdefault 语义：只记首次）
            if let Some(last) = cs.kas.get(label).and_then(|ka| ka.bi_list.last()) {
                let (end, start) = (fmt_ts(last.fx_b.dt), fmt_ts(last.fx_a.dt));
                if done_seen.insert(end.clone()) {
                    done.push((end, day.clone()));
                }
                if started_seen.insert(start.clone()) {
                    started.push((start, day.clone()));
                }
            }
        }
        for key in keys {
            let val = cs.s.get(key).map(String::as_str).unwrap_or("其他");
            let mut parts = val.split('_');
            let v1 = parts.next().unwrap_or("其他");
            let span_part = parts.next().unwrap_or("");
            let Some(t) = sig_type(v1) else {
                prev.insert(key.as_str(), v1.to_string());
                continue;
            };
            if prev.get(key.as_str()).map(String::as_str) != Some(v1) {
                if let Some(bi) = cs.kas.get(label).and_then(|ka| ka.bi_list.last()) {
                    let bi_end = fmt_ts(bi.fx_b.dt);
                    if seen.insert((t, bi_end.clone())) {
                        let is_first = t == "buy1" || t == "sell1";
                        let span = if is_first && span_part.ends_with('笔') { span_part.to_string() } else { String::new() };
                        let legs = if is_first { legs_key.and_then(|k| cs.s.get(k).cloned()) } else { None };
                        events.push((t.to_string(), day.clone(), bi_end, bi.fx_b.fx, span, legs));
                    }
                }
            }
            prev.insert(key.as_str(), v1.to_string());
        }
    }
    Ok((events, done, started))
}

/// 逐根扫描：返回（事件列表, 笔完成时刻表, 成笔时刻表）。出错时由 Python 侧退回逐根循环实现。
#[pyfunction]
#[pyo3(signature = (symbol, freq, times, opens, highs, lows, closes, vols, signals_config, keys, track_bis, legs_key=None, init_n=20))]
#[allow(clippy::too_many_arguments, clippy::type_complexity)]
pub fn dp_scan_bs(
    py: Python<'_>,
    symbol: String,
    freq: String,
    times: Vec<String>,
    opens: Vec<f64>,
    highs: Vec<f64>,
    lows: Vec<f64>,
    closes: Vec<f64>,
    vols: Vec<f64>,
    signals_config: &Bound<PyList>,
    keys: Vec<String>,
    track_bis: bool,
    legs_key: Option<String>,
    init_n: usize,
) -> PyResult<(Vec<ScanEvent>, Vec<(String, String)>, Vec<(String, String)>)> {
    let n = times.len();
    if [opens.len(), highs.len(), lows.len(), closes.len(), vols.len()].iter().any(|l| *l != n) {
        return Err(PyValueError::new_err("K 线各列长度不一致"));
    }
    let f = Freq::from_str(&freq).map_err(|e| PyValueError::new_err(format!("解析 freq 失败: {e}")))?;
    let configs = parse_signals_config(signals_config)?;
    // 计算期间释放 GIL：多只股票可在 Python 线程里并行扫描
    py.detach(move || {
        scan(
            &symbol, f, &freq, &times, &opens, &highs, &lows, &closes, &vols, &configs, &keys, track_bis,
            legs_key.as_deref(), init_n,
        )
    })
    .map_err(PyValueError::new_err)
}
