import SwiftUI

/// 全局配色，与 DeepAlpha 缠论 App（`ios/DeepAlphaChan/App/Theme.swift`）同一套
/// 深色投研风格，两个 App 观感统一。
enum Theme {
    static let accent = Color(hex: 0x3B82F6)       // 主题蓝
    static let background = Color(hex: 0x0B0E14)   // 页面底色
    static let surface = Color(hex: 0x141A24)      // 卡片底色
    static let surfaceAlt = Color(hex: 0x1C2431)   // 次级卡片 / 输入框
    static let border = Color(hex: 0x263041)

    static let textPrimary = Color(hex: 0xE6EDF3)
    static let textSecondary = Color(hex: 0x8B98A9)
    /// 第三级文字（占位、脚注）。缠论只有两级，这里补一级更暗的，
    /// 免得大量说明文字都压到 textSecondary 一个层次上。
    static let textTertiary = Color(hex: 0x5B6675)

    // MARK: - 信号色

    // 注意与缠论的区别：缠论按 A 股惯例「红涨绿跌」，交易台是美股多智能体场景，
    // 且 web 版 trading-desk 一直是「绿=看多、红=看空」。这里沿用后者——
    // 色值取自同一套调色板保证观感一致，但语义不跟着翻转，
    // 否则同一个 agent 的看多结论在网页是绿的、在 App 是红的，必然误读。
    static let bull = Color(hex: 0x2EBD85)    // 看多 = 绿
    static let bear = Color(hex: 0xF6465D)    // 看空 = 红
    static let neutral = Color(hex: 0xF59E0B) // 中性 = 琥珀
    static let human = Color(hex: 0x3B82F6)   // 人工意见 = 蓝

    static let warning = Color(hex: 0xF59E0B)
    static let danger = Color(hex: 0xF6465D)
    static let success = Color(hex: 0x2EBD85)
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

extension View {
    /// 铺满深色底：每个顶层页面都要有，否则会露出系统底色。
    func themedBackground() -> some View {
        background(Theme.background.ignoresSafeArea())
    }
}
