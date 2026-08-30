import Foundation

/// 四个市场。label/placeholder 供 UI，suffix 是 yfinance 约定。
public enum Market: String, CaseIterable, Identifiable, Sendable, Equatable {
    case US, HK, SH, SZ
    public var id: String { rawValue }
    public var label: String {
        switch self {
        case .US: "美股"
        case .HK: "港股"
        case .SH: "沪 A"
        case .SZ: "深 A"
        }
    }
    public var placeholder: String {
        switch self {
        case .US: "NVDA"
        case .HK: "0700"
        case .SH: "600519"
        case .SZ: "000001"
        }
    }
    var suffix: String {
        switch self {
        case .US: ""
        case .HK: ".HK"
        case .SH: ".SS"
        case .SZ: ".SZ"
        }
    }
}

public enum TickerResolver {
    /// 市场后缀规则（移植 web frontend/app/trading-desk/page.tsx:31）：
    /// - 已带 `.` 视为完整代码，保留（防重复拼）
    /// - HK 前导零是 padding，yfinance 不认 03887.HK，strip 后再拼
    /// - A 股前导零是有效位（002415 海康），不动
    public static func resolve(raw: String, market: Market) -> String {
        let cleaned = raw.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard !cleaned.isEmpty else { return cleaned }
        if cleaned.contains(".") { return cleaned }

        var code = cleaned
        if market == .HK {
            let stripped = code.replacingOccurrences(
                of: "^0+", with: "", options: .regularExpression)
            if !stripped.isEmpty { code = stripped }
        }
        return code + market.suffix
    }
}
