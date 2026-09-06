import Foundation

/// 生辰表单用的日期/时间 <-> 字符串转换，纯函数，方便测试。
/// 后端 Pydantic 的 date/time 字段接受 "yyyy-MM-dd" / "HH:mm:ss"（本地时间，不带时区）。
public enum BaziFormatting {
    public static func birthDateString(from date: Date, timeZone: TimeZone = .current) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let formatter = DateFormatter()
        formatter.calendar = calendar
        formatter.timeZone = timeZone
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    public static func birthTimeString(from date: Date, timeZone: TimeZone = .current) -> String {
        let formatter = DateFormatter()
        formatter.timeZone = timeZone
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: date)
    }

    /// 内置城市经度表覆盖的 38 个城市（与后端 app/services/bazi/data/cn_city_longitude.json 一一对应）。
    /// 表单只能从这里选，不开放自由输入——避免用户输入的城市名和后端表匹配不上，
    /// 真太阳时校正静默不生效却毫无提示。
    public static let supportedCities: [String] = [
        "北京", "上海", "广州", "深圳", "成都", "杭州", "南京", "武汉", "西安", "重庆",
        "天津", "苏州", "长沙", "郑州", "青岛", "大连", "厦门", "昆明", "哈尔滨", "沈阳",
        "济南", "合肥", "福州", "南昌", "太原", "石家庄", "兰州", "贵阳", "南宁", "海口",
        "乌鲁木齐", "拉萨", "呼和浩特", "银川", "西宁", "香港", "澳门", "台北",
    ]

    /// 出生日期选择范围下限：早于这个日期后端会拒绝(422)，UI 层直接不给选，
    /// 不依赖解析后端错误消息。
    public static let minBirthDate: Date = {
        var components = DateComponents()
        components.year = 1900
        components.month = 1
        components.day = 1
        return Calendar(identifier: .gregorian).date(from: components) ?? Date.distantPast
    }()
}
