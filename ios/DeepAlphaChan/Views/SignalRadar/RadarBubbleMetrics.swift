import CoreText
import Foundation

/// 气泡尺寸与文字排版：直径按编码（强弱 × 时间远近），代码和名称两行都必须显示。
///
/// 先缩字号让两行放进编码尺寸的圆内；缩到最小字号仍放不下，才把气泡撑大到刚好放下——
/// 大小编码只在迫不得已时让步，且幅度最小（以前一律按字宽撑到约 85pt，大小失去意义）。
struct RadarBubbleMetrics {
    static let edgePadding = 12.0
    /// 可读性下限：再小点不到。
    static let minDiameter = 44.0
    /// 内边距、字号都按直径同比例缩放，大小气泡里文字与留白的比例一致、看起来协调。
    static let paddingRatio = 0.09
    static let symbolRatio = 0.19
    static let nameToSymbol = 0.74
    static let minSymbolSize = 7.0
    static let minNameSize = 6.0

    let diameter: Double
    let symbolFont: CTFont
    let nameFont: CTFont
    let textWidth: Double
    /// 名称始终显示（保留字段供视图判断）。
    let showsName = true

    static func textPadding(for diameter: Double) -> Double {
        max(3, diameter * paddingRatio)
    }

    init(symbol: String, name: String = "", baseDiameter: Double, maxDiameter: Double) {
        let cap = max(1, maxDiameter)
        let base = min(max(baseDiameter, Self.minDiameter), cap)
        let start = max(Self.minSymbolSize, min(17, base * Self.symbolRatio))

        func fonts(_ size: Double) -> (CTFont, CTFont) {
            let system = CTFontCreateUIFontForLanguage(.system, size, nil)
                ?? CTFontCreateWithName("Helvetica" as CFString, size, nil)
            let traits = [kCTFontWeightTrait: 0.56] as CFDictionary
            let descriptor = CTFontDescriptorCreateWithAttributes([kCTFontTraitsAttribute: traits] as CFDictionary)
            let symbolFont = CTFontCreateCopyWithAttributes(system, size, nil, descriptor)
            let nameSize = max(Self.minNameSize, size * Self.nameToSymbol)
            let nameFont = CTFontCreateUIFontForLanguage(.system, nameSize, nil)
                ?? CTFontCreateWithName("Helvetica" as CFString, nameSize, nil)
            return (symbolFont, nameFont)
        }
        func lineHeight(_ f: CTFont) -> Double {
            CTFontGetAscent(f) + CTFontGetDescent(f) + CTFontGetLeading(f)
        }
        func width(_ s: String, _ f: CTFont) -> Double {
            guard !s.isEmpty else { return 0 }
            let text = NSAttributedString(string: s, attributes: [NSAttributedString.Key(kCTFontAttributeName as String): f])
            return ceil(CTLineGetTypographicBounds(CTLineCreateWithAttributedString(text), nil, nil, nil))
        }
        /// 两行文字的包围矩形（较宽一行 + 左右余量 × 两行高）放进内圆所需的直径。
        func required(_ sf: CTFont, _ nf: CTFont) -> (diameter: Double, height: Double) {
            // 内边距已按直径比例预留，这里只留很小的字边余量，避免留白算两遍把字压得过小
            let w = max(width(symbol, sf), width(name, nf) + 2)
            let h = ceil(lineHeight(sf) + lineHeight(nf) + 1) + 2
            let inner = hypot(w + 4, h)
            // 内边距与直径相关：先按无边距求，再加上该直径对应的边距（迭代一次足够）
            let d0 = inner + 2 * Self.textPadding(for: inner)
            return (inner + 2 * Self.textPadding(for: d0), h)
        }

        var size = start
        var picked: (CTFont, CTFont, Double, Double)?
        while size >= Self.minSymbolSize {
            let (sf, nf) = fonts(size)
            let need = required(sf, nf)
            if need.diameter <= base { picked = (sf, nf, base, need.height); break }
            size -= 0.5
        }
        if picked == nil {
            // 最小字号仍放不下：撑大到刚好放下两行（不超过画布）
            let (sf, nf) = fonts(Self.minSymbolSize)
            let need = required(sf, nf)
            picked = (sf, nf, min(cap, ceil(need.diameter)), need.height)
        }
        let (sf, nf, d, h) = picked!
        symbolFont = sf
        nameFont = nf
        diameter = d
        let inner = max(1, d - 2 * Self.textPadding(for: d))
        textWidth = max(1, sqrt(max(0, inner * inner - h * h)))
    }
}
