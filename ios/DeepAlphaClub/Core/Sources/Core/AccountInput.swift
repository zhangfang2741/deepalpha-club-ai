import Foundation

/// 注册/登录的账号通道。
public enum AccountChannel: String, CaseIterable, Identifiable, Sendable, Equatable {
    case phone
    case email

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .phone: "手机号"
        case .email: "邮箱"
        }
    }

    public var placeholder: String {
        switch self {
        case .phone: "手机号"
        case .email: "邮箱"
        }
    }

    public var icon: String {
        switch self {
        case .phone: "iphone"
        case .email: "envelope"
        }
    }
}

/// 账号输入的本地预校验。
///
/// 只做「明显不合法就别发请求」这一层，权威判断在服务端——手机号归一化规则
/// （全角转半角、去分隔符、086 前缀等）比这里复杂得多，两边各写一份必然走偏。
/// 这里存在的意义是省掉一次注定失败的网络往返，并且能在用户还没点按钮时就
/// 把「获取验证码」置灰。
public enum AccountInput {
    /// 中国大陆手机号：1 开头，第二位 3-9，共 11 位。与后端 utils/phone.py 的
    /// _CN_MOBILE 保持一致。
    public static func isValidCNMobile(_ raw: String) -> Bool {
        let digits = raw.filter(\.isNumber)
        return digits.range(of: "^1[3-9]\\d{9}$", options: .regularExpression) != nil
    }

    /// 邮箱格式的宽松校验，与后端 sanitize_email 的正则同源。
    public static func isValidEmail(_ raw: String) -> Bool {
        let text = raw.trimmingCharacters(in: .whitespaces)
        let pattern = "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
        return text.range(of: pattern, options: .regularExpression) != nil
    }

    public static func isValid(_ raw: String, channel: AccountChannel) -> Bool {
        switch channel {
        case .phone: isValidCNMobile(raw)
        case .email: isValidEmail(raw)
        }
    }

    /// 6 位数字验证码。
    public static func isValidCode(_ raw: String) -> Bool {
        raw.range(of: "^\\d{6}$", options: .regularExpression) != nil
    }
}

/// 密码强度规则。与后端 validate_password_strength 对齐：8–64 位，含字母和数字。
///
/// 前端比后端更严会让用户卡在一个后端本可接受的密码上，更松则是白跑一趟网络请求，
/// 所以这里必须跟后端一字不差。
public struct PasswordRules: Sendable {
    public let password: String
    public init(password: String) { self.password = password }

    public var hasLetter: Bool {
        password.range(of: "[A-Za-z]", options: .regularExpression) != nil
    }
    public var hasDigit: Bool {
        password.range(of: "[0-9]", options: .regularExpression) != nil
    }
    public var longEnough: Bool { password.count >= 8 && password.count <= 64 }

    public var allSatisfied: Bool { hasLetter && hasDigit && longEnough }
}
