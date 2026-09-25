import Foundation

/// 分析查询日期（"yyyy-MM-dd"）与 Date 的互转，按各市场交易所所在时区换算。
///
/// 为什么不能用手机本地时区或统一用纽约时区：
/// - 统一纽约：北京时间 26 号上午 A 股盘中，纽约还是 25 号晚上，截止日成了 25 号，
///   A 股/港股盘中当天的K线从任何入口都拿不到。
/// - 本地时区解析 + 纽约格式化（雷达 as_of 的旧写法）：东八区解析出的「25 号 0 点」
///   在纽约是 24 号中午，截止日退成 24 号，从雷达点进详情只有前一天数据。
/// 市场用 rawValue（us / cn / hk）传入，不依赖 StockMarket，方便单独编译测试。
enum QueryDates {
    static func timeZone(market: String) -> TimeZone {
        switch market {
        case "cn": return TimeZone(identifier: "Asia/Shanghai")!
        case "hk": return TimeZone(identifier: "Asia/Hong_Kong")!
        default: return TimeZone(identifier: "America/New_York")!
        }
    }

    private static let formatters: [String: DateFormatter] = {
        var out: [String: DateFormatter] = [:]
        for m in ["us", "cn", "hk"] {
            let f = DateFormatter()
            f.dateFormat = "yyyy-MM-dd"
            f.locale = Locale(identifier: "en_US_POSIX")
            f.timeZone = timeZone(market: m)
            out[m] = f
        }
        return out
    }()

    private static func formatter(market: String) -> DateFormatter {
        formatters[market] ?? formatters["us"]!
    }

    /// 某一时刻在该市场交易所当地是哪一天。
    static func string(from date: Date, market: String) -> String {
        formatter(market: market).string(from: date)
    }

    /// 后端给的 "yyyy-MM-dd"（如雷达 as_of）→ 该市场当地那天的 0 点。
    static func date(from string: String, market: String) -> Date? {
        formatter(market: market).date(from: string)
    }

    /// 在该市场当地日历上加减天数（不受手机时区与夏令时影响）。
    static func adding(days: Int, to date: Date, market: String) -> Date {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = timeZone(market: market)
        return cal.date(byAdding: .day, value: days, to: date) ?? date
    }
}
