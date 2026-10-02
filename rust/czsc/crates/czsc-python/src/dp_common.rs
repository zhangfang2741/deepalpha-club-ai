// DeepAlpha：dp_scan / dp_structures 共用的小工具（时间解析 / 格式化、按列构造 K 线、MACD）。
use chrono::{DateTime, NaiveDate, NaiveDateTime, Utc};
use czsc_core::objects::bar::{RawBar, RawBarBuilder};
use czsc_core::objects::freq::Freq;

/// 项目时间字符串 → UTC（朴素时间按 UTC 解释，与 Python 侧 `pd.Timestamp(time)` 喂给 czsc 的口径一致）
pub fn parse_dt(s: &str) -> Result<DateTime<Utc>, String> {
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
pub fn fmt_ts(dt: DateTime<Utc>) -> String {
    let n = dt.naive_utc();
    if n.format("%H:%M").to_string() == "00:00" {
        n.format("%Y-%m-%d").to_string()
    } else {
        n.format("%Y-%m-%d %H:%M").to_string()
    }
}

/// 按列构造 RawBar（id = 序号，amount = close * volume，与 Python `bars_to_raw_bars` 一致）
#[allow(clippy::too_many_arguments)]
pub fn build_raw(
    symbol: &str,
    freq: Freq,
    times: &[String],
    opens: &[f64],
    highs: &[f64],
    lows: &[f64],
    closes: &[f64],
    vols: &[f64],
) -> Result<Vec<RawBar>, String> {
    let mut raw = Vec::with_capacity(times.len());
    for i in 0..times.len() {
        raw.push(
            RawBarBuilder::default()
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
                .map_err(|e| format!("构造 RawBar 失败: {e}"))?,
        );
    }
    Ok(raw)
}

/// EMA：以首值起算，`v * k + prev * (1 - k)`，运算顺序与 Python `calc_ema` 完全一致（逐位相同）
fn ema(values: &[f64], period: usize) -> Vec<f64> {
    let k = 2.0 / (period as f64 + 1.0);
    let mut out: Vec<f64> = Vec::with_capacity(values.len());
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

/// MACD（12 / 26 / 9）：返回 (DIF, DEA, 柱)；不足慢线周期（26 根）时全 0，与 Python `calc_macd` 一致
pub fn macd_series(closes: &[f64]) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let n = closes.len();
    if n < 26 {
        return (vec![0.0; n], vec![0.0; n], vec![0.0; n]);
    }
    let (fast, slow) = (ema(closes, 12), ema(closes, 26));
    let dif: Vec<f64> = fast.iter().zip(slow.iter()).map(|(f, s)| f - s).collect();
    let dea = ema(&dif, 9);
    let bar: Vec<f64> = dif.iter().zip(dea.iter()).map(|(d, e)| 2.0 * (d - e)).collect();
    (dif, dea, bar)
}
