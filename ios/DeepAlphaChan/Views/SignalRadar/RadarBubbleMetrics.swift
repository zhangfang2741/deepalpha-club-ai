import CoreText
import Foundation

/// 气泡尺寸与文字排版：直径严格只由编码（一二三类 × 时间远近）决定，代码和名称两行都必须显示。
///
/// 只靠缩字号让两行放进编码尺寸的圆内，绝不为了放下文字而撑大气泡——A股/港股「代码+
/// 中文名」两行天然比美股「只有代码」更宽，若允许因放不下文字而撑大，会让同样类型/新鲜度
/// 的信号在不同市场画出大小不一致的气泡，大小编码就失去了跨市场可比性。缩到最小字号仍放
/// 不下时，直径依旧保持编码尺寸不变，交给渲染层的 `minimumScaleFactor` 继续压缩字号兜底。
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
        func required(_ sf: CTFont, _ nf: CTFont) -> (diameter: Double, height: Double) {
            // 内边距已按直径比例预留，这里只留很小的字边余量，避免留白算两遍把字压得过小
            let w = max(width(symbol, sf), name.isEmpty ? 0 : width(name, nf) + 2)
            // 名称为空（美股无中文名）时只排代码一行
            let h = ceil(lineHeight(sf) + (name.isEmpty ? 0 : lineHeight(nf) + 1)) + 2
            let inner = hypot(w + 4, h)
            // 内边距与直径相关：先按无边距求，再加上该直径对应的边距（迭代一次足够）
            let d0 = inner + 2 * Self.textPadding(for: inner)
            return (inner + 2 * Self.textPadding(for: d0), h)
        }

        var picked: (CTFont, CTFont, Double, Double)?

        // 代码字号与名称字号分开求：名称（尤其是长中文名，如「美国电话电报」）比代码
        // 天然更容易放不下，若两者绑成同一个 size 一起退让，代码会被名称拖着一起缩得
        // 很小——代码通常只有 1~5 个字符，本不该被拖累。先把代码固定在它的自然字号
        // （`start`），只压名称去凑空间；只有代码在自然字号下配最小号名称仍放不下时，
        // 才退回两者一起缩的兜底（与最初实现一致）。
        if !name.isEmpty {
            let sf = makeSymbolFont(start)
            var nameSize = start * Self.nameToSymbol
            while nameSize >= Self.minNameSize {
                let nf = makeNameFont(nameSize)
                let need = required(sf, nf)
                if need.diameter <= base { picked = (sf, nf, base, need.height); break }
                nameSize -= 0.5
            }
        }

        if picked == nil {
            // 名称已经缩到最小仍放不下（多半是代码本身也偏长），退回两者同步缩放。
            var size = start
            while size >= Self.minSymbolSize {
                let sf = makeSymbolFont(size)
                let nf = makeNameFont(max(Self.minNameSize, size * Self.nameToSymbol))
                let need = required(sf, nf)
                if need.diameter <= base { picked = (sf, nf, base, need.height); break }
                size -= 0.5
            }
        }
        if picked == nil {
            // 最小字号仍放不下：不撑大气泡（那会让气泡大小随文字长度而非类型/时间变化，
            // 跨市场就不可比了）——直径继续保持编码尺寸，字号定在最小值，剩下交给
            // RadarBubble 渲染时的 minimumScaleFactor 兜底再压一压。
            let sf = makeSymbolFont(Self.minSymbolSize)
            let nf = makeNameFont(Self.minNameSize)
            let need = required(sf, nf)
            picked = (sf, nf, base, need.height)
        }
        let (sf, nf, d, h) = picked!
        symbolFont = sf
        nameFont = nf
        diameter = d
        let inner = max(1, d - 2 * Self.textPadding(for: d))
        textWidth = max(1, sqrt(max(0, inner * inner - h * h)))
    }
}
