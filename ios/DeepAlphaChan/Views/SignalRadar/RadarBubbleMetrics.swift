import CoreText
import Foundation

/// 气泡尺寸与文字排版：直径严格只由编码（一二三类 × 时间远近）决定，代码和名称两行都必须显示。
///
/// 只靠缩字号让两行放进编码尺寸的圆内，绝不为了放下文字而撑大气泡——A股/港股「代码+
/// 中文名」两行天然比美股「只有代码」更宽，若允许因放不下文字而撑大，会让同样类型/新鲜度
/// 的信号在不同市场画出大小不一致的气泡，大小编码就失去了跨市场可比性。缩到最小字号仍放
/// 不下时，直径依旧保持编码尺寸不变，交给渲染层的 `minimumScaleFactor` 继续压缩字号兜底。
/// 代码字号不受名称长度影响：长名称只压名称自己，放不下由渲染层截断。
struct RadarBubbleMetrics {
    static let edgePadding = 12.0
    /// 可读性下限：再小点不到。
    static let minDiameter = 44.0
    /// 内边距、字号都按直径同比例缩放，大小气泡里文字与留白的比例一致、看起来协调。
    /// 直径不再为放不下的文字撑大后（见下方 init 注释），最小的气泡（时间远 × 强度弱，
    /// 卡在 minDiameter floor）留给文字的空间最紧张，9% 的内边距在这些气泡上占比明显
    /// 偏大、看起来跟文字本身差不多宽，收窄到 5% 更协调。
    static let paddingRatio = 0.05
    static let symbolRatio = 0.19
    static let nameToSymbol = 0.74
    static let minSymbolSize = 7.0
    static let minNameSize = 6.0

    let diameter: Double
    let symbolFont: CTFont
    let nameFont: CTFont
    let textWidth: Double
    /// 有名称就显示（名称为空时只显示代码）。
    let showsName: Bool

    static func textPadding(for diameter: Double) -> Double {
        max(2, diameter * paddingRatio)
    }

    init(symbol: String, name: String = "", baseDiameter: Double, maxDiameter: Double) {
        showsName = !name.isEmpty
        let cap = max(1, maxDiameter)
        let base = min(max(baseDiameter, Self.minDiameter), cap)
        let start = max(Self.minSymbolSize, min(17, base * Self.symbolRatio))

        func makeSymbolFont(_ size: Double) -> CTFont {
            let system = CTFontCreateUIFontForLanguage(.system, size, nil)
                ?? CTFontCreateWithName("Helvetica" as CFString, size, nil)
            let traits = [kCTFontWeightTrait: 0.56] as CFDictionary
            let descriptor = CTFontDescriptorCreateWithAttributes([kCTFontTraitsAttribute: traits] as CFDictionary)
            return CTFontCreateCopyWithAttributes(system, size, nil, descriptor)
        }
        func makeNameFont(_ size: Double) -> CTFont {
            CTFontCreateUIFontForLanguage(.system, size, nil)
                ?? CTFontCreateWithName("Helvetica" as CFString, size, nil)
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
        /// `nameWidth: false` 只按代码宽度算（名称行只占高度），用来定代码字号。
        func required(_ sf: CTFont, _ nf: CTFont, nameWidth: Bool = true) -> (diameter: Double, height: Double) {
            // 内边距已按直径比例预留，这里只留很小的字边余量，避免留白算两遍把字压得过小
            let nw = (name.isEmpty || !nameWidth) ? 0 : width(name, nf) + 2
            let w = max(width(symbol, sf), nw)
            // 名称为空（美股无中文名）时只排代码一行
            let h = ceil(lineHeight(sf) + (name.isEmpty ? 0 : lineHeight(nf) + 1)) + 2
            let inner = hypot(w + 4, h)
            // 内边距与直径相关：先按无边距求，再加上该直径对应的边距（迭代一次足够）
            let d0 = inner + 2 * Self.textPadding(for: inner)
            return (inner + 2 * Self.textPadding(for: d0), h)
        }

        // 代码优先：代码字号只看代码自己（名称行只占高度）放不放得下，名称宽度绝不拖小代码——
        // 代码通常只有 1~5 个字符，是气泡里最重要的信息；名称（如「Citizens Financial
        // Group Inc」「美国电话电报」）再长也只压名称自己，缩到最小号仍放不下就交给
        // RadarBubble 渲染层截断。代码本身都放不下时才缩代码，最小字号兜底且不撑大气泡
        // （那会让气泡大小随文字长度而非类型/时间变化，跨市场就不可比了）。
        let minName = makeNameFont(Self.minNameSize)
        var symbolSize = start
        while symbolSize > Self.minSymbolSize,
              required(makeSymbolFont(symbolSize), minName, nameWidth: false).diameter > base {
            symbolSize -= 0.5
        }
        let sf = makeSymbolFont(max(Self.minSymbolSize, symbolSize))

        var nf = minName
        if !name.isEmpty {
            var nameSize = max(Self.minNameSize, CTFontGetSize(sf) * Self.nameToSymbol)
            while nameSize > Self.minNameSize, required(sf, makeNameFont(nameSize)).diameter > base {
                nameSize -= 0.5
            }
            nf = makeNameFont(max(Self.minNameSize, nameSize))
        }
        let h = required(sf, nf, nameWidth: false).height
        let d = base
        symbolFont = sf
        nameFont = nf
        diameter = d
        let inner = max(1, d - 2 * Self.textPadding(for: d))
        textWidth = max(1, sqrt(max(0, inner * inner - h * h)))
    }
}
