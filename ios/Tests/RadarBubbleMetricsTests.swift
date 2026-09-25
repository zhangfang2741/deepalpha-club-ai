import CoreText
import Foundation

/// 用 swiftc 与 RadarBubbleMetrics.swift 一起编译运行，无需启动模拟器。
@main
struct RadarBubbleMetricsTests {
    static func width(_ s: String, _ f: CTFont) -> Double {
        CTLineGetTypographicBounds(CTLineCreateWithAttributedString(NSAttributedString(string: s, attributes: [
            NSAttributedString.Key(kCTFontAttributeName as String): f
        ])), nil, nil, nil)
    }

    static func main() {
        let cases = [("A", "安捷伦"), ("AAPL", "苹果"), ("0700.HK", "腾讯控股"), ("000001.SZ", "平安银行"),
                     ("2015.HK", "理想汽车-W"), ("WWWWWWWW", "Wide Name Co")]
        for (symbol, name) in cases {
            var previous = 0.0
            for base in [33.0, 42.0, 60.0, 76.0, 92.0] {
                let m = RadarBubbleMetrics(symbol: symbol, name: name, baseDiameter: base, maxDiameter: 250)
                precondition(m.showsName, "名称必须显示")
                precondition(m.diameter >= max(base, RadarBubbleMetrics.minDiameter), "不小于编码尺寸与可读下限")
                precondition(m.diameter >= previous, "编码越大气泡越大（单调）")
                previous = m.diameter
                // 代码与名称都完整放进圆内的文字宽度
                precondition(m.textWidth >= width(symbol, m.symbolFont) + 7, "代码完整落在圆内: \(symbol) \(base)")
                precondition(m.textWidth >= width(name, m.nameFont) + 8, "名称完整落在圆内: \(name) \(base)")
                let pad = RadarBubbleMetrics.textPadding(for: m.diameter)
                precondition(m.textWidth <= m.diameter - 2 * pad + 0.01, "文字不贴圆边")
            }
        }
        // 大气泡：原尺寸就放得下，不应膨胀
        let normal = RadarBubbleMetrics(symbol: "AAPL", name: "苹果", baseDiameter: 92, maxDiameter: 250)
        precondition(normal.diameter == 92, "足够大的气泡保持编码尺寸")
        // 小气泡：只在最小字号也放不下时才撑大，且明显小于旧版一律约 85pt
        let small = RadarBubbleMetrics(symbol: "AAPL", name: "苹果", baseDiameter: 44, maxDiameter: 250)
        precondition(small.diameter < 70, "小气泡只撑到刚好放下两行")
        let capped = RadarBubbleMetrics(symbol: "LONG-STOCK-SYMBOL", name: "Very Long Company Name",
                                        baseDiameter: 60, maxDiameter: 100)
        precondition(capped.diameter <= 100, "不能超出画布")
    }
}
