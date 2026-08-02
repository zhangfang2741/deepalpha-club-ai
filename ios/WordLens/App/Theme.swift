// App/Theme.swift
import SwiftUI

/// 全局配色，深色系，风格与 DeepAlphaChan 保持一致但换成背单词场景色。
enum Theme {
    static let accent = Color(hex: 0x3B82F6)
    static let background = Color(hex: 0x0B0E14)
    static let surface = Color(hex: 0x141A24)
    static let surfaceAlt = Color(hex: 0x1C2431)
    static let border = Color(hex: 0x263041)
    static let textPrimary = Color(hex: 0xE6EDF3)
    static let textSecondary = Color(hex: 0x8B98A9)

    /// 三档标记状态色：不认识/模糊/认识
    static let unknown = Color(hex: 0xEF4444)
    static let fuzzy = Color(hex: 0xF59E0B)
    static let known = Color(hex: 0x22C55E)

    /// 听写结果滑动操作使用实色底板，避免用低透明度状态色叠加出“蒙层感”。
    static let dictationKnownSurface = Color(hex: 0x14532D)
    static let dictationFuzzySurface = Color(hex: 0x78350F)
    static let dictationUnknownSurface = Color(hex: 0x7F1D1D)
    static let dictationRetrySurface = Color(hex: 0x1E3A5F)
}

extension Color {
    init(hex: UInt32, alpha: Double = 1.0) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >> 8) & 0xFF) / 255.0
        let b = Double(hex & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}
