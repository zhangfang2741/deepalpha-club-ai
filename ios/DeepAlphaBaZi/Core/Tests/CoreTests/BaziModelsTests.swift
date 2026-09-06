import Foundation
import Testing
@testable import DeepAlphaBaZiCore

@Suite("BaziModels")
struct BaziModelsTests {
    @Test("BaziChartRequest 编码：字段名走 snake_case")
    func encodeChartRequest() throws {
        let request = BaziChartRequest(
            birthDate: "1990-05-15", birthTime: "14:30:00",
            birthCity: "北京", gender: "male")
        let data = try JSONEncoder().encode(request)
        let json = try #require(try JSONSerialization.jsonObject(with: data) as? [String: String])
        #expect(json["birth_date"] == "1990-05-15")
        #expect(json["birth_time"] == "14:30:00")
        #expect(json["birth_city"] == "北京")
        #expect(json["gender"] == "male")
    }

    @Test("BaziChartRequest 编码：birth_time 为 nil 时序列化成 null")
    func encodeChartRequestNilTime() throws {
        let request = BaziChartRequest(
            birthDate: "1990-05-15", birthTime: nil, birthCity: "北京", gender: "female")
        let data = try JSONEncoder().encode(request)
        let json = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any?])
        #expect(json["birth_time"] as? String == nil)
    }

    @Test("BaziChartResponse 解码：时辰已知，四柱+五行+大运完整映射")
    func decodeChartResponseHourKnown() throws {
        let json = """
        {
          "request_id": "11111111-1111-1111-1111-111111111111",
          "hour_known": true,
          "solar_date": "1990-05-15",
          "lunar_date": "一九九〇年四月廿一",
          "true_solar_time": "1990-05-15T14:16:00",
          "true_solar_time_applied": true,
          "year_pillar": {"gan": "庚", "zhi": "午", "na_yin": "路旁土", "shi_shen_gan": "比肩", "shi_shen_zhi": ["正官", "正印"]},
          "month_pillar": {"gan": "辛", "zhi": "巳", "na_yin": "白蜡金", "shi_shen_gan": "劫财", "shi_shen_zhi": ["七杀"]},
          "day_pillar": {"gan": "庚", "zhi": "辰", "na_yin": "白蜡金", "shi_shen_gan": "元男", "shi_shen_zhi": ["偏印"]},
          "time_pillar": {"gan": "癸", "zhi": "未", "na_yin": "杨柳木", "shi_shen_gan": "伤官", "shi_shen_zhi": ["正印"]},
          "wu_xing_distribution": {"jin": 3, "mu": 0, "shui": 1, "huo": 2, "tu": 2},
          "da_yun": [{"gan_zhi": "壬午", "start_age": 8, "end_age": 17}, {"gan_zhi": "癸未", "start_age": 18, "end_age": 27}],
          "liu_nian_gan_zhi": "甲辰"
        }
        """
        let response = try JSONDecoder().decode(BaziChartResponse.self, from: Data(json.utf8))
        #expect(response.hourKnown == true)
        #expect(response.trueSolarTimeApplied == true)
        #expect(response.yearPillar.gan == "庚")
        #expect(response.yearPillar.shiShenZhi == ["正官", "正印"])
        #expect(response.timePillar?.zhi == "未")
        #expect(response.wuXingDistribution["jin"] == 3)
        #expect(response.daYun.count == 2)
        #expect(response.daYun[0].startAge == 8)
        #expect(response.liuNianGanZhi == "甲辰")
    }

    @Test("BaziChartResponse 解码：时辰未知时 time_pillar 为 nil")
    func decodeChartResponseHourUnknown() throws {
        let json = """
        {
          "request_id": "11111111-1111-1111-1111-111111111111",
          "hour_known": false,
          "solar_date": "1990-05-15",
          "lunar_date": "一九九〇年四月廿一",
          "true_solar_time": null,
          "true_solar_time_applied": false,
          "year_pillar": {"gan": "庚", "zhi": "午", "na_yin": "路旁土", "shi_shen_gan": "比肩", "shi_shen_zhi": ["正官"]},
          "month_pillar": {"gan": "辛", "zhi": "巳", "na_yin": "白蜡金", "shi_shen_gan": "劫财", "shi_shen_zhi": ["七杀"]},
          "day_pillar": {"gan": "庚", "zhi": "辰", "na_yin": "白蜡金", "shi_shen_gan": "元女", "shi_shen_zhi": ["偏印"]},
          "time_pillar": null,
          "wu_xing_distribution": {"jin": 3, "mu": 0, "shui": 0, "huo": 2, "tu": 1},
          "da_yun": [],
          "liu_nian_gan_zhi": "甲辰"
        }
        """
        let response = try JSONDecoder().decode(BaziChartResponse.self, from: Data(json.utf8))
        #expect(response.hourKnown == false)
        #expect(response.timePillar == nil)
        #expect(response.trueSolarTime == nil)
    }

    @Test("InterpretationRequest 编码：section 走 daily/deep 字符串")
    func encodeInterpretationRequest() throws {
        let request = InterpretationRequest(
            birthDate: "1990-05-15", birthTime: nil, birthCity: "北京",
            gender: "male", section: .deep)
        let data = try JSONEncoder().encode(request)
        let json = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(json["section"] as? String == "deep")
    }

    @Test("InterpretationResponse 解码")
    func decodeInterpretationResponse() throws {
        let json = #"{"request_id": "x", "text": "今天适合签约 | 宜：签约 忌：争执"}"#
        let response = try JSONDecoder().decode(InterpretationResponse.self, from: Data(json.utf8))
        #expect(response.text == "今天适合签约 | 宜：签约 忌：争执")
    }
}
