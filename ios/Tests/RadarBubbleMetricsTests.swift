import CoreText
import Foundation

/// 用 swiftc 与 RadarBubbleMetrics.swift 一起编译运行，无需启动模拟器。
@main
struct RadarBubbleMetricsTests {
    static func main() {
        for symbol in ["A", "AAPL", "BRK.B", "0700.HK", "000001.SZ", "WWWWWWWW"] {
            var previous = 0.0
            for base in [33.0, 42.0, 60.0, 76.0, 92.0] {
                let m = RadarBubbleMetrics(symbol: symbol, baseDiameter: base, maxDiameter: 250)
                // 大小严格按编码：不因文字宽度撑大，只保留可读性下限
                precondition(m.diameter == max(base, RadarBubbleMetrics.minDiameter), "直径由编码决定，不被文字撑大")
                precondition(m.diameter >= previous, "编码越大气泡越大（单调）")
                previous = m.diameter
                precondition(m.textWidth <= m.diameter - 20, "文字左右至少各留 10 点，不贴圆边")
                let line = CTLineCreateWithAttributedString(NSAttributedString(string: symbol, attributes: [
                    NSAttributedString.Key(kCTFontAttributeName as String): m.symbolFont
                ]))
                let width = CTLineGetTypographicBounds(line, nil, nil, nil)
                let atMinSize = CTFontGetSize(m.symbolFont) <= RadarBubbleMetrics.minSymbolSize + 0.01
                precondition(m.textWidth >= width + 7 || atMinSize,
                             "字号缩到放得进圆内；最小字号仍放不下时由单行缩放兜底")
            }
        }
        let normal = RadarBubbleMetrics(symbol: "AAPL", baseDiameter: 92, maxDiameter: 250)
        precondition(normal.diameter == 92 && normal.showsName, "大气泡两行都显示")
        let tiny = RadarBubbleMetrics(symbol: "000001.SZ", baseDiameter: 33, maxDiameter: 250)
        precondition(!tiny.showsName, "小气泡放不下两行时只显示代码")
        let capped = RadarBubbleMetrics(symbol: "LONG-STOCK-SYMBOL", baseDiameter: 300, maxDiameter: 100)
        precondition(capped.diameter == 100, "不能超出画布")
        precondition(capped.textWidth > 0 && capped.textWidth <= capped.diameter - 20)
    }
}
