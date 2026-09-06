import Foundation
import Testing
@testable import DeepAlphaBaZiCore

@Suite("BaziFormatting")
struct BaziFormattingTests {
    @Test("birthDateString：格式化成 yyyy-MM-dd")
    func birthDateFormat() {
        var components = DateComponents()
        components.year = 1990; components.month = 5; components.day = 15
        components.hour = 14; components.minute = 30
        let tz = TimeZone(identifier: "Asia/Shanghai")!
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = tz
        let date = calendar.date(from: components)!
        #expect(BaziFormatting.birthDateString(from: date, timeZone: tz) == "1990-05-15")
    }

    @Test("birthTimeString：格式化成 HH:mm:ss")
    func birthTimeFormat() {
        var components = DateComponents()
        components.year = 1990; components.month = 5; components.day = 15
        components.hour = 14; components.minute = 30; components.second = 0
        let tz = TimeZone(identifier: "Asia/Shanghai")!
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = tz
        let date = calendar.date(from: components)!
        #expect(BaziFormatting.birthTimeString(from: date, timeZone: tz) == "14:30:00")
    }

    @Test("supportedCities：包含38个后端支持的城市，覆盖北京和台北")
    func supportedCitiesCount() {
        #expect(BaziFormatting.supportedCities.count == 38)
        #expect(BaziFormatting.supportedCities.contains("北京"))
        #expect(BaziFormatting.supportedCities.contains("台北"))
    }
}
