import CoreText
import Foundation

/// 用 swiftc 与 RadarBubbleMetrics.swift 一起编译运行，无需启动模拟器。
@main
struct RadarBubbleMetricsTests {
    static func main() {
        let cases = [("A", "安捷伦"), ("AAPL", "苹果"), ("0700.HK", "腾讯控股"), ("000001.SZ", "平安银行"),
                     ("2015.HK", "理想汽车-W"), ("WWWWWWWW", "Wide Name Co")]
        for (symbol, name) in cases {
            for base in [33.0, 42.0, 60.0, 76.0, 92.0] {
                let m = RadarBubbleMetrics(symbol: symbol, name: name, baseDiameter: base, maxDiameter: 250)
                precondition(m.showsName, "有名称就必须显示")
                // 直径只由 base（强弱×时间衰减）与可读下限决定，与代码/名称长度无关——
                // 否则同样强弱的信号会因为 A股/港股多一行中文名而比美股画得更大，
                // 气泡大小就不能跨市场直接比较了。
                precondition(m.diameter == max(base, RadarBubbleMetrics.minDiameter),
                            "直径严格等于编码尺寸，不因文字长度膨胀: \(symbol) \(base)")
            }
        }
        // 大气泡：原尺寸就放得下
        let normal = RadarBubbleMetrics(symbol: "AAPL", name: "苹果", baseDiameter: 92, maxDiameter: 250)
        precondition(normal.diameter == 92, "足够大的气泡保持编码尺寸")
        // 小气泡 + 很长的代码/名称：即便最小字号也放不下两行，直径依然不膨胀，只压缩字号
        let small = RadarBubbleMetrics(symbol: "LONG-STOCK-SYMBOL", name: "Very Long Company Name",
                                       baseDiameter: 44, maxDiameter: 250)
        precondition(small.diameter == RadarBubbleMetrics.minDiameter, "文字放不下也不撑大气泡")
        precondition(CTFontGetSize(small.symbolFont) == RadarBubbleMetrics.minSymbolSize, "放不下时字号落到最小值")
        // 协调：小气泡的内边距都随直径变小
        let big = RadarBubbleMetrics(symbol: "AAPL", name: "苹果", baseDiameter: 92, maxDiameter: 250)
        let tiny = RadarBubbleMetrics(symbol: "AAPL", name: "苹果", baseDiameter: 44, maxDiameter: 250)
        precondition(RadarBubbleMetrics.textPadding(for: tiny.diameter) < RadarBubbleMetrics.textPadding(for: big.diameter))
        let rBig = CTFontGetSize(big.symbolFont) / big.diameter
        let rTiny = CTFontGetSize(tiny.symbolFont) / tiny.diameter
        precondition(abs(rBig - rTiny) < 0.04, "大小气泡的字号占比一致（放得下文字时）: \(rBig) \(rTiny)")
        // 美股无中文名：名称为空只排代码一行，字号可以比两行时更大；直径不受影响
        let codeOnly = RadarBubbleMetrics(symbol: "AEP", name: "", baseDiameter: 60, maxDiameter: 250)
        let twoLines = RadarBubbleMetrics(symbol: "AEP", name: "美国电力", baseDiameter: 60, maxDiameter: 250)
        precondition(!codeOnly.showsName && twoLines.showsName)
        precondition(codeOnly.diameter == twoLines.diameter, "有无中文名不改变直径，只改变字号")
        precondition(CTFontGetSize(codeOnly.symbolFont) >= CTFontGetSize(twoLines.symbolFont))
        // 画布很小时：编码尺寸本身超出画布才需要按 maxDiameter 收窄（与文字无关）
        let capped = RadarBubbleMetrics(symbol: "LONG-STOCK-SYMBOL", name: "Very Long Company Name",
                                        baseDiameter: 120, maxDiameter: 100)
        precondition(capped.diameter == 100, "编码尺寸超出画布时才收窄到画布上限")
    }
}
