// DeepAlpha：「建结构 + 提取分型 / 笔 / 笔级中枢 / 合并 K 线 + MACD」整段搬进 Rust。
//
// 原先 Python 侧先把每根 K 线转成 czsc 对象（pandas 时间）、批量建 CZSC，再逐个读取笔 / 分型 / 合并 K 线 /
// 中枢的属性（每次属性访问都是一份副本，时间还要逐个转 pandas Timestamp）转回项目的数据类。
// 这里一次调用做完，只返回纯数据（元组列表），Python 只负责把它们实例化成数据类。
// 逻辑逐条对应 czsc_adapter.extract_structures，并有逐项相等的对照测试守护。
use super::dp_common::{build_raw, fmt_ts, macd_series};
use chrono::{DateTime, Utc};
use czsc_core::analyze::utils::get_zs_seq;
use czsc_core::analyze::{resolve_max_bi_num, resolve_min_bi_len, CZSC};
use czsc_core::objects::bar::NewBar;
use czsc_core::objects::direction::Direction;
use czsc_core::objects::freq::Freq;
use czsc_core::objects::fx::FX;
use czsc_core::objects::mark::Mark;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::collections::{BTreeMap, HashMap};
use std::str::FromStr;

/// 合并 K 线：(idx, time, open, high, low, close, raw_start, raw_end, volume, end_time)
type Candle = (usize, String, f64, f64, f64, f64, i32, i32, f64, String);
/// 分型：(是否顶分型, 左, 中, 右)
type Fractal = (bool, Candle, Candle, Candle);
/// 笔：(是否上升, 起点分型下标, 终点分型下标, 价差力度, 量能力度, 时长)
type StrokeT = (bool, usize, usize, f64, f64, usize);
/// 笔级中枢：(zg, zd, gg, dd, 起, 止, 构成笔的下标)
type PivotT = (f64, f64, f64, f64, String, String, Vec<usize>);
/// MACD：(时间, DIF, DEA, 柱)，按 czsc 实际持有的 K 线（bars_raw）计算
type MacdT = (Vec<String>, Vec<f64>, Vec<f64>, Vec<f64>);
type Out = (Vec<Candle>, Vec<Fractal>, Vec<StrokeT>, Vec<PivotT>, MacdT);

fn candle(nb: &NewBar, pos: &HashMap<DateTime<Utc>, usize>) -> Result<Candle, String> {
    let idx = *pos.get(&nb.dt).ok_or_else(|| format!("NewBar {} 不在重建序列里", nb.dt))?;
    let (Some(first), Some(last)) = (nb.elements.first(), nb.elements.last()) else {
        return Err("NewBar 没有原始K线元素".to_string());
    };
    let volume = nb.elements.iter().fold(0.0_f64, |a, r| a + r.vol);
    Ok((idx, fmt_ts(nb.dt), first.open, nb.high, nb.low, last.close, first.id, last.id, volume, fmt_ts(last.dt)))
}

#[allow(clippy::too_many_arguments)]
fn structures(
    symbol: &str,
    freq: Freq,
    times: &[String],
    opens: &[f64],
    highs: &[f64],
    lows: &[f64],
    closes: &[f64],
    vols: &[f64],
) -> Result<Out, String> {
    let raw = build_raw(symbol, freq, times, opens, highs, lows, closes, vols)?;
    let czsc = CZSC::new(raw, resolve_max_bi_num(0), resolve_min_bi_len(0));
    let bis = &czsc.bi_list;

    // 重建完整去包含 K 线序列：各笔的 bars ∪ bars_ubi，按 dt 去重（后写覆盖先写，与 Python 一致）、排序
    let mut by_dt: BTreeMap<DateTime<Utc>, &NewBar> = BTreeMap::new();
    for bi in bis {
        for nb in &bi.bars {
            by_dt.insert(nb.dt, nb);
        }
    }
    for nb in &czsc.bars_ubi {
        by_dt.insert(nb.dt, nb);
    }
    let pos: HashMap<DateTime<Utc>, usize> = by_dt.keys().enumerate().map(|(i, k)| (*k, i)).collect();
    let merged = by_dt.values().map(|nb| candle(nb, &pos)).collect::<Result<Vec<_>, _>>()?;

    // 分型只取笔的端点分型，按 (dt, mark) 去重保序（相邻笔共享端点）
    let mut fx_index: HashMap<(i64, bool), usize> = HashMap::new();
    let mut fractals: Vec<Fractal> = Vec::new();
    let mut fx_id = |fx: &FX| -> Result<usize, String> {
        let is_top = fx.mark == Mark::G;
        let key = (fx.dt.timestamp_millis(), is_top);
        if let Some(i) = fx_index.get(&key) {
            return Ok(*i);
        }
        if fx.elements.len() != 3 {
            return Err(format!("分型元素不是 3 根: {}", fx.elements.len()));
        }
        let (l, m, r) = (candle(&fx.elements[0], &pos)?, candle(&fx.elements[1], &pos)?, candle(&fx.elements[2], &pos)?);
        fractals.push((is_top, l, m, r));
        fx_index.insert(key, fractals.len() - 1);
        Ok(fractals.len() - 1)
    };
    let mut strokes: Vec<StrokeT> = Vec::with_capacity(bis.len());
    for bi in bis {
        let (a, b) = (fx_id(&bi.fx_a)?, fx_id(&bi.fx_b)?);
        strokes.push((bi.direction == Direction::Up, a, b, bi.get_power_price(), bi.get_power_volume(), bi.get_length()));
    }

    // 笔级中枢：czsc 只用已确认笔分组；至少 3 笔、区间有效才算（与 Python 适配层同口径）
    let mut stroke_by_start: HashMap<String, usize> = HashMap::new();
    for (i, bi) in bis.iter().enumerate() {
        stroke_by_start.entry(fmt_ts(bi.fx_a.dt)).or_insert(i);
    }
    let finished = czsc.get_finished_bis();
    let mut pivots: Vec<PivotT> = Vec::new();
    for zs in get_zs_seq(&finished) {
        if zs.bis.len() < 3 || !zs.is_valid() || zs.zg <= zs.zd {
            continue;
        }
        let elements = zs
            .bis
            .iter()
            .map(|bi| {
                stroke_by_start
                    .get(&fmt_ts(bi.fx_a.dt))
                    .copied()
                    .ok_or_else(|| "中枢里的笔不在笔列表中".to_string())
            })
            .collect::<Result<Vec<_>, _>>()?;
        pivots.push((
            zs.zg,
            zs.zd,
            zs.gg,
            zs.dd,
            fmt_ts(zs.bis[0].fx_a.dt),
            fmt_ts(zs.bis[zs.bis.len() - 1].fx_b.dt),
            elements,
        ));
    }

    let raw_closes: Vec<f64> = czsc.bars_raw.iter().map(|b| b.close).collect();
    let (dif, dea, bar) = macd_series(&raw_closes);
    let macd_times: Vec<String> = czsc.bars_raw.iter().map(|b| fmt_ts(b.dt)).collect();
    Ok((merged, fractals, strokes, pivots, (macd_times, dif, dea, bar)))
}

/// 建结构并提取：返回（合并 K 线, 分型, 笔, 笔级中枢, MACD）。出错由 Python 侧退回原实现。
#[pyfunction]
#[pyo3(signature = (symbol, freq, times, opens, highs, lows, closes, vols))]
#[allow(clippy::too_many_arguments)]
pub fn dp_structures(
    py: Python<'_>,
    symbol: String,
    freq: String,
    times: Vec<String>,
    opens: Vec<f64>,
    highs: Vec<f64>,
    lows: Vec<f64>,
    closes: Vec<f64>,
    vols: Vec<f64>,
) -> PyResult<Out> {
    let n = times.len();
    if [opens.len(), highs.len(), lows.len(), closes.len(), vols.len()].iter().any(|l| *l != n) {
        return Err(PyValueError::new_err("K 线各列长度不一致"));
    }
    let f = Freq::from_str(&freq).map_err(|e| PyValueError::new_err(format!("解析 freq 失败: {e}")))?;
    py.detach(move || structures(&symbol, f, &times, &opens, &highs, &lows, &closes, &vols))
        .map_err(PyValueError::new_err)
}

/// MACD（12 / 26 / 9）：返回 (DIF, DEA, 柱)，与 Python `calc_macd` 逐位一致
#[pyfunction]
pub fn dp_macd(closes: Vec<f64>) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    macd_series(&closes)
}
