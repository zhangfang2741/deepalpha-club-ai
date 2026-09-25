import CoreText
import Foundation

/// 文字测量与显示共用字体，让气泡按代码的实际宽度撑开，而不是按字符数猜测。
struct RadarBubbleMetrics {
    static let edgePadding = 12.0
    /// 文字包围矩形到圆形边缘的最小留白；按半径预留，每侧各 10 点。
    static let textPadding = 10.0

    let diameter: Double
    let symbolFont: CTFont
    let nameFont: CTFont
    let textWidth: Double

    init(symbol: String, baseDiameter: Double, maxDiameter: Double) {
        // 字号取原始尺寸，撑大圆形时不再同步增大文字，避免尺寸相互追涨。
        let symbolSize = max(12, min(17, baseDiameter * 0.21))
        let nameSize = max(9, min(12, baseDiameter * 0.15))
        let systemFont = CTFontCreateUIFontForLanguage(.system, symbolSize, nil)
            ?? CTFontCreateWithName("Helvetica" as CFString, symbolSize, nil)
        let traits = [kCTFontWeightTrait: 0.56] as CFDictionary
        let descriptor = CTFontDescriptorCreateWithAttributes([kCTFontTraitsAttribute: traits] as CFDictionary)
        symbolFont = CTFontCreateCopyWithAttributes(systemFont, symbolSize, nil, descriptor)
        nameFont = CTFontCreateUIFontForLanguage(.system, nameSize, nil)
            ?? CTFontCreateWithName("Helvetica" as CFString, nameSize, nil)

        let text = NSAttributedString(string: symbol, attributes: [
            NSAttributedString.Key(kCTFontAttributeName as String): symbolFont
        ])
        let line = CTLineCreateWithAttributedString(text)
        let symbolWidth = ceil(CTLineGetTypographicBounds(line, nil, nil, nil))
        let textHeight = ceil(CTFontGetAscent(symbolFont) + CTFontGetDescent(symbolFont)
            + CTFontGetLeading(symbolFont) + CTFontGetAscent(nameFont)
            + CTFontGetDescent(nameFont) + CTFontGetLeading(nameFont)) + 3
        // 两行文字的包围矩形需要完整落在圆内，不能只比较字宽与直径。
        let requiredDiameter = hypot(symbolWidth + 8, textHeight) + 2 * Self.textPadding
        diameter = min(max(baseDiameter, ceil(requiredDiameter)), max(1, maxDiameter))
        let innerDiameter = max(1, diameter - 2 * Self.textPadding)
        textWidth = max(1, sqrt(max(0, innerDiameter * innerDiameter - textHeight * textHeight)))
    }
}
