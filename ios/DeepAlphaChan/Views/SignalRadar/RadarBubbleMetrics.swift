import CoreText
import Foundation

/// 气泡尺寸与文字排版：直径严格按编码（强弱 × 时间远近），文字去适应气泡。
///
/// 以前是「按代码字宽把气泡撑大」，结果几乎所有气泡都被撑到 85pt 上下，大小不再能表示
/// 强弱、越远越小也失效。现在反过来：直径 = 编码尺寸（只设一个可读性下限），字号从原始
/// 大小往下缩到放得进圆内；最小字号仍放不下时只显示代码、不显示名称，再放不下交给
/// 视图的单行缩放兜底。
struct RadarBubbleMetrics {
    static let edgePadding = 12.0
    /// 文字包围矩形到圆形边缘的最小留白；按半径预留，每侧各 10 点。
    static let textPadding = 10.0
    /// 可读性下限：再小点不到、字也看不清（30 天前的弱信号按编码只有约 33pt）。
    static let minDiameter = 44.0
    /// 代码字号下限。
    static let minSymbolSize = 8.0

    let diameter: Double
    let symbolFont: CTFont
    let nameFont: CTFont
    let textWidth: Double
    /// 放不下两行时只显示代码。
    let showsName: Bool

    init(symbol: String, baseDiameter: Double, maxDiameter: Double) {
        diameter = min(max(baseDiameter, Self.minDiameter), max(1, maxDiameter))
        let inner = max(1, diameter - 2 * Self.textPadding)
        let startSize = max(Self.minSymbolSize, min(17, baseDiameter * 0.21))

        func fonts(_ size: Double) -> (CTFont, CTFont) {
            let system = CTFontCreateUIFontForLanguage(.system, size, nil)
                ?? CTFontCreateWithName("Helvetica" as CFString, size, nil)
            let traits = [kCTFontWeightTrait: 0.56] as CFDictionary
            let descriptor = CTFontDescriptorCreateWithAttributes([kCTFontTraitsAttribute: traits] as CFDictionary)
            let symbolFont = CTFontCreateCopyWithAttributes(system, size, nil, descriptor)
            let nameSize = max(7, size * 0.72)
            let nameFont = CTFontCreateUIFontForLanguage(.system, nameSize, nil)
                ?? CTFontCreateWithName("Helvetica" as CFString, nameSize, nil)
            return (symbolFont, nameFont)
        }
        func lineHeight(_ f: CTFont) -> Double {
            CTFontGetAscent(f) + CTFontGetDescent(f) + CTFontGetLeading(f)
        }
        func symbolWidth(_ f: CTFont) -> Double {
            let text = NSAttributedString(string: symbol, attributes: [
                NSAttributedString.Key(kCTFontAttributeName as String): f
            ])
            return ceil(CTLineGetTypographicBounds(CTLineCreateWithAttributedString(text), nil, nil, nil))
        }
        /// 文字包围矩形（代码宽 + 左右余量 × 行高）的对角线放得进内圆即可。
        func fits(_ width: Double, _ height: Double) -> Bool {
            hypot(width + 8, height) <= inner
        }

        var chosen: (CTFont, CTFont, Double, Bool)?
        for withName in [true, false] {
            var size = startSize
            while size >= Self.minSymbolSize {
                let (sf, nf) = fonts(size)
                let height = ceil(lineHeight(sf) + (withName ? lineHeight(nf) + 1 : 0)) + 2
                if fits(symbolWidth(sf), height) {
                    chosen = (sf, nf, height, withName)
                    break
                }
                size -= 0.5
            }
            if chosen != nil { break }
        }
        let (sf, nf) = fonts(Self.minSymbolSize)
        let fallbackHeight = ceil(lineHeight(sf)) + 2
        let (symbolFont, nameFont, textHeight, showsName) = chosen ?? (sf, nf, fallbackHeight, false)
        self.symbolFont = symbolFont
        self.nameFont = nameFont
        self.showsName = showsName
        textWidth = max(1, sqrt(max(0, inner * inner - textHeight * textHeight)))
    }
}
