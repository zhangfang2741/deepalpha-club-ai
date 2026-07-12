import SwiftUI

/// 全局配色与样式常量，统一深色投研风格。
enum Theme {
    static let accent = Color(hex: 0x3B82F6)      // 主题蓝
    static let background = Color(hex: 0x0B0E14)   // 页面底色
    static let surface = Color(hex: 0x141A24)      // 卡片底色
    static let surfaceAlt = Color(hex: 0x1C2431)   // 次级卡片
    static let border = Color(hex: 0x263041)

    static let textPrimary = Color(hex: 0xE6EDF3)
    static let textSecondary = Color(hex: 0x8B98A9)

    // 涨跌色（美股惯例：绿涨红跌）
    static let up = Color(hex: 0x22C55E)
    static let down = Color(hex: 0xEF4444)

    // 缠论结构叠加色
    static let stroke = Color(hex: 0x60A5FA)       // 笔
    static let segment = Color(hex: 0xF59E0B)      // 线段
    static let pivotFill = Color(hex: 0x8B5CF6)    // 中枢
    static let topFractal = Color(hex: 0xEF4444)   // 顶分型
    static let bottomFractal = Color(hex: 0x22C55E)// 底分型
}

extension Color {
    /// 用 0xRRGGBB 十六进制初始化颜色。
    init(hex: UInt32, alpha: Double = 1.0) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >> 8) & 0xFF) / 255.0
        let b = Double(hex & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}
