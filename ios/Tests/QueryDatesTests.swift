import Foundation

/// 用 swiftc 与 DeepAlphaChan/Models/QueryDates.swift 一起编译运行，无需模拟器：
///   swiftc -Onone Tests/QueryDatesTests.swift DeepAlphaChan/Models/QueryDates.swift -o /tmp/qd && /tmp/qd
@main
struct QueryDatesTests {
    static func utc(_ s: String) -> Date {
        let f = ISO8601DateFormatter()
        return f.date(from: s)!
    }

    static func main() {
        for tz in ["Asia/Shanghai", "America/Los_Angeles", "America/New_York", "UTC"] {
            NSTimeZone.default = TimeZone(identifier: tz)!  // 模拟手机所在时区
            // 北京时间 26 号 10:00（A 股/港股盘中）= 纽约 25 号 22:00
            let t = utc("2026-09-26T02:00:00Z")
            assert(QueryDates.string(from: t, market: "cn") == "2026-09-26", "\(tz): A 股按上海日期，盘中能取到当天")
            assert(QueryDates.string(from: t, market: "hk") == "2026-09-26", "\(tz): 港股按香港日期")
            assert(QueryDates.string(from: t, market: "us") == "2026-09-25", "\(tz): 美股按纽约日期")
            // 纽约 25 号 11:00（美股盘中）= 北京 25 号 23:00
            let u = utc("2026-09-25T15:00:00Z")
            assert(QueryDates.string(from: u, market: "us") == "2026-09-25", "\(tz): 美股盘中当天")
            // 后端给的 as_of 解析再格式化必须原样回来（回归：东八区解析后按纽约格式化退一天）
            for m in ["us", "cn", "hk"] {
                let d = QueryDates.date(from: "2026-09-25", market: m)!
                assert(QueryDates.string(from: d, market: m) == "2026-09-25", "\(tz) \(m): as_of 往返不变")
                let start = QueryDates.adding(days: -270, to: d, market: m)
                assert(QueryDates.string(from: start, market: m) == "2025-12-29", "\(tz) \(m): 往前推 270 天")
            }
        }
        print("QueryDates 测试通过")
    }
}
