import CoreText
import Foundation

@main
struct RadarBubbleMetricsTests {
    static func main() {
        for symbol in ["A", "AAPL", "BRK.B", "0700.HK", "000001.SZ", "WWWWWWWW"] {
            for base in [33.0, 42.0, 60.0, 76.0, 92.0] {
                let metrics = RadarBubbleMetrics(symbol: symbol, baseDiameter: base, maxDiameter: 250)
                let line = CTLineCreateWithAttributedString(NSAttributedString(string: symbol, attributes: [
                    NSAttributedString.Key(kCTFontAttributeName as String): metrics.symbolFont
                ]))
                let width = CTLineGetTypographicBounds(line, nil, nil, nil)
                precondition(metrics.textWidth >= width + 7, "代码必须完整落在圆内，并保留左右余量")
                precondition(metrics.diameter >= base, "正常画布只允许撑大，不缩小原有气泡")
                precondition(metrics.diameter <= 250)
                precondition(metrics.textWidth <= metrics.diameter - 20, "文字左右至少各留 10 点，不贴圆边")
            }
        }
        let wide = RadarBubbleMetrics(symbol: "WWWWWW", baseDiameter: 33, maxDiameter: 250)
        let narrow = RadarBubbleMetrics(symbol: "IIIIII", baseDiameter: 33, maxDiameter: 250)
        precondition(wide.diameter > narrow.diameter, "相同字符数应按真实字宽分别测量")
        let normal = RadarBubbleMetrics(symbol: "AAPL", baseDiameter: 92, maxDiameter: 250)
        precondition(normal.diameter == 92, "足够大的原始气泡不应无故膨胀")
        let capped = RadarBubbleMetrics(symbol: "LONG-STOCK-SYMBOL", baseDiameter: 60, maxDiameter: 100)
        precondition(capped.diameter == 100, "极长代码的气泡不能撑出画布，改由单行文字缩放兜底")
        precondition(capped.textWidth > 0 && capped.textWidth < capped.diameter)
        precondition(capped.textWidth <= capped.diameter - 20, "达到尺寸上限时也必须保留内边距")
    }
}
