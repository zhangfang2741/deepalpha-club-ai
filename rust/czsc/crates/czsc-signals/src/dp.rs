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

/// 一段走势（若干连续笔，只读切片）的结构量：价差 # 量能 # 时长 # 起点时间 # 终点时间。
/// MACD 面积不在这里算：整条 MACD 只由 czsc 的 TA-Lib 兼容实现算一次，Python 按起止时间取面积
/// （EMA 是因果的，过去的柱不会随新 K 线改变，事后一次算完与当时逐根算数值完全一致）。
fn dp_leg_text(legs: &[BI]) -> String {
    let first = &legs[0];
    let last = &legs[legs.len() - 1];
    let price = (first.fx_a.fx - last.fx_b.fx).abs();
    let volume: f64 = legs.iter().map(|b| b.get_power_volume()).sum();
    let length: usize = legs.iter().map(|b| b.get_length()).sum();
    let fmt = "%Y%m%d%H%M";
    format!(
        "{}#{}#{}#{}#{}",
        price,
        volume,
        length,
        first.fx_a.dt.format(fmt),
        last.fx_b.dt.format(fmt)
    )
}

/// 连续笔的下标区间：起点不早于 start、终点不晚于 end 的笔（笔按时间严格递增，满足条件的必连续）
fn dp_leg_range(bis: &[BI], start: chrono::DateTime<chrono::Utc>, end: chrono::DateTime<chrono::Utc>) -> Option<(usize, usize)> {
    let lo = bis.iter().position(|x| x.fx_a.dt >= start)?;
    let hi = bis.iter().rposition(|x| x.fx_b.dt <= end)?;
    (lo <= hi).then_some((lo, hi + 1))
}

/// dp_trend_legs_V261001：趋势前提 + b / c 两段原始力度（缠论一类买卖点的结构依据）
///
/// 参数模板：`"{freq}_D{di}趋势腿_DP辅助V261001"`
///
/// 信号逻辑（对最后一笔）：
/// 1. 最后一笔向下 → 看买点，向上 → 看卖点；
/// 2. 趋势前提：已形成的最后两个中枢 A、B 依次下移（买）/ 上移（卖），且该笔终点已离开 B；
/// 3. b 段 = 离开 A 的那一笔起到进入 B；c 段 = B 最后一个中枢内笔的终点起到该笔终点；
/// 4. 输出两段的结构量（价差 / 量能 / 时长 / 起止时间），MACD 面积和是否背驰由 Python 侧按起止时间取面积、
///    再由背驰度量（可插拔）判定。
///
/// 信号列表示例：
/// - `Signal('日线_D1趋势腿_DP辅助V261001_买趋势_28#600#12#202501010000#202502010000_15#350#9#202502010000#202503010000_0')`
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
    let Some((b_lo, b_hi)) = dp_leg_range(bis, bis[k_b].fx_a.dt, entry) else {
        return none();
    };
    let Some((c_lo, c_hi)) = dp_leg_range(bis, bis[k_c].fx_a.dt, end) else {
        return none();
    };
    let (b_leg, c_leg) = (&bis[b_lo..b_hi], &bis[c_lo..c_hi]);
    if (b_leg[b_leg.len() - 1].fx_b.fx < b_leg[0].fx_a.fx) != is_buy {
        return none();
    }
    // 背驰的前提是价格创新极值：信号价要越过 b 段终点（买：更低，卖：更高），否则不是一类
    let b_end = b_leg[b_leg.len() - 1].fx_b.fx;
    if (is_buy && price >= b_end) || (!is_buy && price <= b_end) {
        return other();
    }
    make_kline_signal_v3(&k1, k2, k3, tag, &dp_leg_text(b_leg), &dp_leg_text(c_leg))
}
