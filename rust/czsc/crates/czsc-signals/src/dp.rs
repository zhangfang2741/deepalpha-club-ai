// DeepAlpha 自有信号：沿用 czsc 的 `#[signal]` 架构，在 Rust 内核里直接读 `&CZSC`，
// 避免 Python 侧每根 K 线取整份结构副本（`cs.kas[...].bi_list` 是 O(n) 拷贝）。
use crate::params::ParamView;
use crate::types::TaCache;
use crate::utils::sig::{get_usize_param, make_kline_signal_v1, make_kline_signal_v3};
use czsc_core::analyze::CZSC;
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
