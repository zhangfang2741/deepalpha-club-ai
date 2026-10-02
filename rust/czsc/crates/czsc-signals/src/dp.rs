// DeepAlpha 自有信号：沿用 czsc 的 `#[signal]` 架构，在 Rust 内核里直接读 `&CZSC`，
// 避免 Python 侧每根 K 线取整份结构副本（`cs.kas[...].bi_list` 是 O(n) 拷贝）。
use crate::params::ParamView;
use crate::types::TaCache;
use crate::utils::sig::{get_usize_param, make_kline_signal_v1, make_kline_signal_v3};
use czsc_core::analyze::CZSC;
use czsc_core::objects::bi::BI;
use czsc_core::objects::direction::Direction;
use czsc_core::objects::signal::Signal;
use czsc_signal_macros::signal;

/// dp_bi_track_V261001：笔轨迹（已完成笔数 + 末笔终点 / 起点时间）
///
/// 参数模板：`"{freq}_D{di}笔轨迹_DP辅助V261001"`
///
/// 信号逻辑：取倒数第 `di` 笔，输出 `{笔数}笔 _ 终点时间 _ 起点时间`；没有笔时返回 `其他`。
/// Python 侧用它判断「哪一根 K 线上新出现了一笔」，不必再拷贝整份笔列表。
///
/// 信号列表示例：
/// - `Signal('日线_D1笔轨迹_DP辅助V261001_12笔_202501100000_202501010000_0')`
#[signal(
    category = "kline",
    name = "dp_bi_track_V261001",
    template = "{freq}_D{di}笔轨迹_DP辅助V261001",
    opcode = "DpBiTrackV261001",
    param_kind = "DpBiTrackV261001"
)]
pub fn dp_bi_track_v261001(c: &CZSC, params: &ParamView, _cache: &mut TaCache) -> Vec<Signal> {
    let di = get_usize_param(params, "di", 1);
    let k1 = c.freq.to_string();
    let k2 = format!("D{}笔轨迹", di);
    let k3 = "DP辅助V261001";
    let n = c.bi_list.len();
    if di == 0 || n < di {
        return make_kline_signal_v1(&k1, &k2, k3, "其他");
    }
    let bi = &c.bi_list[n - di];
    let fmt = "%Y%m%d%H%M";
    make_kline_signal_v3(
        &k1,
        &k2,
        k3,
        &format!("{}笔", n),
        &bi.fx_b.dt.format(fmt).to_string(),
        &bi.fx_a.dt.format(fmt).to_string(),
    )
}

// ---------------------------------------------------------------------------
// dp_trend_legs：趋势前提 + b / c 两段的原始力度
// ---------------------------------------------------------------------------

/// 中枢分组（复刻 czsc `get_zs_seq`，但不拷贝笔）：新一笔完全落在当前组 [zd, zg] 之外才另起一组；
/// 组的 zg / zd 取组内前三笔（缠论：上下沿由最初三笔决定，之后不变）。
struct DpPivot {
    s: usize, // 组内第一笔下标
    zg: f64,
    zd: f64,
}

fn dp_zg_zd(bis: &[BI]) -> (f64, f64) {
    let zg = bis.iter().take(3).map(|x| x.get_high()).fold(f64::INFINITY, f64::min);
    let zd = bis.iter().take(3).map(|x| x.get_low()).fold(f64::NEG_INFINITY, f64::max);
    (zg, zd)
}

/// 已形成的有效中枢（>= 3 笔、上下沿有效、每笔都与区间有交集），与 Python 适配层 extract_structures 同口径。
fn dp_pivots(bis: &[BI]) -> Vec<DpPivot> {
    let mut groups: Vec<(usize, usize)> = Vec::new();
    for (i, bi) in bis.iter().enumerate() {
        match groups.last().copied() {
            None => groups.push((i, i + 1)),
            Some((s, _)) => {
                let (zg, zd) = dp_zg_zd(&bis[s..i]);
                let outside = (bi.direction == Direction::Up && bi.get_high() < zd)
                    || (bi.direction == Direction::Down && bi.get_low() > zg);
                if outside {
                    groups.push((i, i + 1));
                } else {
                    groups.last_mut().unwrap().1 = i + 1;
                }
            }
        }
    }
    groups
        .into_iter()
        .filter_map(|(s, e)| {
            if e - s < 3 {
                return None;
            }
            let (zg, zd) = dp_zg_zd(&bis[s..e]);
            if zg <= zd {
                return None;
            }
            let ok = bis[s..e].iter().all(|bi| {
                let (h, l) = (bi.get_high(), bi.get_low());
                (h <= zg && h >= zd) || (l <= zg && l >= zd) || (h >= zg && l <= zd)
            });
            ok.then_some(DpPivot { s, zg, zd })
        })
        .collect()
}

/// 离开中枢 [lo, hi] 的那一笔：[start, end] 内最后一笔「与区间有重叠、沿趋势方向、终点越过区间边界」的笔
/// （买：向下且终点 < lo；卖：向上且终点 > hi）。czsc 会把离开笔吸收进中枢，所以不能拿中枢最后一个元素当离开点。
/// 高低点用两端分型价（与 Python Stroke.high / low 同口径）。
fn dp_exit_stroke(
    bis: &[BI],
    lo: f64,
    hi: f64,
    is_buy: bool,
    start: chrono::DateTime<chrono::Utc>,
    end: chrono::DateTime<chrono::Utc>,
) -> Option<usize> {
    bis.iter()
        .enumerate()
        .filter(|(_, x)| {
            let (h, l) = (x.fx_a.fx.max(x.fx_b.fx), x.fx_a.fx.min(x.fx_b.fx));
            x.fx_a.dt >= start
                && x.fx_b.dt <= end
                && l <= hi
                && h >= lo
                && (x.direction == Direction::Down) == is_buy
                && if is_buy { x.fx_b.fx < lo } else { x.fx_b.fx > hi }
        })
        .map(|(k, _)| k)
        .next_back()
}

fn dp_ema(values: &[f64], period: usize) -> Vec<f64> {
    let mut out = Vec::with_capacity(values.len());
    let k = 2.0 / (period as f64 + 1.0);
    for (i, v) in values.iter().enumerate() {
        if i == 0 {
            out.push(*v);
        } else {
            let prev = out[i - 1];
            out.push(v * k + prev * (1.0 - k));
        }
    }
    out
}

/// MACD 柱（与 Python calc_macd 同公式 / 同运算顺序：EMA 以首值起算，柱 = 2 * (DIF - DEA)）；不足慢线周期时全 0。
fn dp_macd_bar(closes: &[f64]) -> Vec<f64> {
    if closes.len() < 26 {
        return vec![0.0; closes.len()];
    }
    let fast = dp_ema(closes, 12);
    let slow = dp_ema(closes, 26);
    let dif: Vec<f64> = fast.iter().zip(slow.iter()).map(|(f, s)| f - s).collect();
    let dea = dp_ema(&dif, 9);
    dif.iter().zip(dea.iter()).map(|(d, e)| 2.0 * (d - e)).collect()
}

/// 一段走势（若干连续笔）的原始力度：价差 # 量能 # 时长 # MACD 面积（与走势同向的柱绝对值之和）。
fn dp_leg_text(c: &CZSC, legs: &[BI], bar: &[f64]) -> String {
    let first = &legs[0];
    let last = &legs[legs.len() - 1];
    let price = (first.fx_a.fx - last.fx_b.fx).abs();
    let volume: f64 = legs.iter().map(|b| b.get_power_volume()).sum();
    let length: usize = legs.iter().map(|b| b.get_length()).sum();
    let is_down = last.fx_b.fx < first.fx_a.fx;
    let (start, end) = (first.fx_a.dt, last.fx_b.dt);
    let mut area = 0.0_f64;
    for (rb, v) in c.bars_raw.iter().zip(bar.iter()) {
        if rb.dt >= start && rb.dt <= end && ((is_down && *v < 0.0) || (!is_down && *v > 0.0)) {
            area += v.abs();
        }
    }
    format!("{}#{}#{}#{}", price, volume, length, area)
}

/// dp_trend_legs_V261001：趋势前提 + b / c 两段原始力度（缠论一类买卖点的结构依据）
///
/// 参数模板：`"{freq}_D{di}趋势腿_DP辅助V261001"`
///
/// 信号逻辑（对最后一笔）：
/// 1. 最后一笔向下 → 看买点，向上 → 看卖点；
/// 2. 趋势前提：已形成的最后两个中枢 A、B 依次下移（买）/ 上移（卖），且该笔终点已离开 B；
/// 3. b 段 = 离开 A 的那一笔起到进入 B；c 段 = B 最后一个中枢内笔的终点起到该笔终点；
/// 4. 输出两段的原始力度，是否背驰由 Python 侧的背驰度量（可插拔）判定。
///
/// 信号列表示例：
/// - `Signal('日线_D1趋势腿_DP辅助V261001_买趋势_28#600#12#3.4_15#350#9#1.1_0')`
/// - `Signal('日线_D1趋势腿_DP辅助V261001_卖趋势_无_无_0')`（趋势成立但 b / c 段取不到）
/// - `Signal('日线_D1趋势腿_DP辅助V261001_其他_任意_任意_0')`
#[signal(
    category = "kline",
    name = "dp_trend_legs_V261001",
    template = "{freq}_D{di}趋势腿_DP辅助V261001",
    opcode = "DpTrendLegsV261001",
    param_kind = "DpTrendLegsV261001"
)]
pub fn dp_trend_legs_v261001(c: &CZSC, _params: &ParamView, _cache: &mut TaCache) -> Vec<Signal> {
    let k1 = c.freq.to_string();
    let k2 = "D1趋势腿";
    let k3 = "DP辅助V261001";
    let other = || make_kline_signal_v1(&k1, k2, k3, "其他");
    let bis = &c.bi_list;
    let Some(last) = bis.last() else {
        return other();
    };
    let is_buy = last.direction == Direction::Down;
    // 中枢只用「已确认」的笔分组（与 czsc `zs_list` 同口径：未完成区域不足 5 根 K 线时，最后一笔尚未确认）
    let n_finished = if c.bars_ubi.len() < 5 { bis.len() - 1 } else { bis.len() };
    let piv = dp_pivots(&bis[..n_finished]);
    if piv.len() < 2 {
        return other();
    }
    let (a, b) = (&piv[piv.len() - 2], &piv[piv.len() - 1]);
    let price = last.fx_b.fx;
    let in_trend = if is_buy {
        b.zg < a.zd && price < b.zd
    } else {
        b.zd > a.zg && price > b.zg
    };
    if !in_trend {
        return other();
    }
    let tag = if is_buy { "买趋势" } else { "卖趋势" };
    let none = || make_kline_signal_v3(&k1, k2, k3, tag, "无", "无");

    // b 段：离开 A 的那一笔起，到进入 B；c 段：离开 B 的那一笔起，到信号笔终点（都含各自的离开笔）
    let entry = bis[b.s].fx_a.dt;
    let end = last.fx_b.dt;
    let Some(k_b) = dp_exit_stroke(bis, a.zd, a.zg, is_buy, bis[a.s].fx_a.dt, entry) else {
        return none();
    };
    let Some(k_c) = dp_exit_stroke(bis, b.zd, b.zg, is_buy, entry, end) else {
        return none();
    };
    let b_leg: Vec<BI> = bis
        .iter()
        .filter(|x| x.fx_a.dt >= bis[k_b].fx_a.dt && x.fx_b.dt <= entry)
        .cloned()
        .collect();
    let c_leg: Vec<BI> = bis
        .iter()
        .filter(|x| x.fx_a.dt >= bis[k_c].fx_a.dt && x.fx_b.dt <= end)
        .cloned()
        .collect();
    if b_leg.is_empty() || c_leg.is_empty() || (b_leg[b_leg.len() - 1].fx_b.fx < b_leg[0].fx_a.fx) != is_buy {
        return none();
    }
    // 背驰的前提是价格创新极值：信号价要越过 b 段终点（买：更低，卖：更高），否则不是一类
    let b_end = b_leg[b_leg.len() - 1].fx_b.fx;
    if (is_buy && price >= b_end) || (!is_buy && price <= b_end) {
        return other();
    }
    let closes: Vec<f64> = c.bars_raw.iter().map(|x| x.close).collect();
    let bar = dp_macd_bar(&closes);
    make_kline_signal_v3(&k1, k2, k3, tag, &dp_leg_text(c, &b_leg, &bar), &dp_leg_text(c, &c_leg, &bar))
}
