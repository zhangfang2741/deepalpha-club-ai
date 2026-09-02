import Foundation

/// 注册/登录支持的国家/地区区号。
///
/// 这是一份**精选**列表而非全球所有国家：手机号注册最终要落到阿里云国际短信，
/// 每个国家都涉及资费和合规开通，能发的国家由运营侧决定，前端只暴露这些。
/// 需要新增时在这里加一行，并确认后端阿里云侧已开通对应国家的国际短信。
///
/// 号码的权威校验在后端（phonenumbers）。这里的 `nationalDigits` 只做「位数明显
/// 不对就别发请求」这一层预校验，省掉一次注定失败的网络往返。
struct PhoneCountry: Identifiable, Hashable {
    /// 国家码（不含 +），如中国 "86"、美国 "1"。
    let dialCode: String
    /// 展示名（本地化）。
    let name: String
    /// 旗帜 emoji，让下拉里一眼能认出。
    let flag: String
    /// 国内号（不含国家码）的合法位数区间，用于本地预校验。
    let nationalDigits: ClosedRange<Int>

    var id: String { dialCode + name }

    /// 下拉里显示的一行：🇨🇳 中国大陆 +86
    var label: String { "\(flag) \(name) +\(dialCode)" }

    /// 当前是否支持短信验证码。国际短信暂未开通，只支持中国大陆；选到其它地区时
    /// UI 会提示改用邮箱/Apple 登录（后端也会拦截，见 codes.send_sms_code 的 CN-only 闸）。
    var isSupported: Bool { dialCode == "86" }

    /// 本地预校验：国内号位数落在区间内即可。
    func isValidNational(_ raw: String) -> Bool {
        let digits = raw.filter(\.isNumber)
        // 中国大陆再严一档：号段固定（1 开头，第二位 3-9）。复用 AccountInput 里
        // 已有的号段规则，避免两处各写一份正则走偏。
        if dialCode == "86" {
            return AccountInput.isValidCNMobile(digits)
        }
        return nationalDigits.contains(digits.count)
    }

    /// 拼成 E.164：+国家码+国内号（去掉分隔符和用户可能多打的前导 0）。
    func e164(national raw: String) -> String {
        var digits = raw.filter(\.isNumber)
        // 很多国家的本地写法带一个国内长途前缀 0（如英国 020…），E.164 里不要。
        // 中国大陆手机号本身不以 0 开头，不受影响。
        if dialCode != "86" {
            while digits.hasPrefix("0") { digits.removeFirst() }
        }
        return "+\(dialCode)\(digits)"
    }
}

extension PhoneCountry {
    /// 精选支持列表。默认第一个（中国大陆）。
    static let all: [PhoneCountry] = [
        PhoneCountry(dialCode: "86", name: L("中国大陆"), flag: "🇨🇳", nationalDigits: 11...11),
        PhoneCountry(dialCode: "852", name: L("中国香港"), flag: "🇭🇰", nationalDigits: 8...8),
        PhoneCountry(dialCode: "853", name: L("中国澳门"), flag: "🇲🇴", nationalDigits: 8...8),
        PhoneCountry(dialCode: "886", name: L("中国台湾"), flag: "🇹🇼", nationalDigits: 9...9),
        PhoneCountry(dialCode: "1", name: L("美国/加拿大"), flag: "🇺🇸", nationalDigits: 10...10),
        PhoneCountry(dialCode: "65", name: L("新加坡"), flag: "🇸🇬", nationalDigits: 8...8),
        PhoneCountry(dialCode: "44", name: L("英国"), flag: "🇬🇧", nationalDigits: 9...10),
        PhoneCountry(dialCode: "61", name: L("澳大利亚"), flag: "🇦🇺", nationalDigits: 9...9),
        PhoneCountry(dialCode: "81", name: L("日本"), flag: "🇯🇵", nationalDigits: 10...11),
        PhoneCountry(dialCode: "82", name: L("韩国"), flag: "🇰🇷", nationalDigits: 9...10),
    ]

    static let `default` = all[0]
}
