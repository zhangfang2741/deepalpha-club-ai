import Foundation
import Testing
@testable import DeepAlphaBaZiCore

@Suite("BaziService")
struct BaziServiceTests {
    func makeService(_ mock: MockServer) -> BaziService {
        BaziService(api: APIClient(baseURL: URL(string: "https://api.example.com")!, session: mock.session))
    }

    @Test("getChart：POST /api/v1/bazi/chart，请求体/响应体正确映射")
    func getChart() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            let body = """
            {"request_id":"x","hour_known":true,"solar_date":"1990-05-15",
             "lunar_date":"一九九〇年四月廿一","true_solar_time":"1990-05-15T14:16:00",
             "true_solar_time_applied":true,
             "year_pillar":{"gan":"庚","zhi":"午","na_yin":"路旁土","shi_shen_gan":"比肩","shi_shen_zhi":["正官"]},
             "month_pillar":{"gan":"辛","zhi":"巳","na_yin":"白蜡金","shi_shen_gan":"劫财","shi_shen_zhi":["七杀"]},
             "day_pillar":{"gan":"庚","zhi":"辰","na_yin":"白蜡金","shi_shen_gan":"元男","shi_shen_zhi":["偏印"]},
             "time_pillar":{"gan":"癸","zhi":"未","na_yin":"杨柳木","shi_shen_gan":"伤官","shi_shen_zhi":["正印"]},
             "wu_xing_distribution":{"jin":3,"mu":0,"shui":1,"huo":2,"tu":2},
             "da_yun":[{"gan_zhi":"壬午","start_age":8,"end_age":17}],
             "liu_nian_gan_zhi":"甲辰"}
            """
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!,
                    Data(body.utf8))
        }
        let service = makeService(mock)
        let response = try await service.getChart(BaziChartRequest(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京", gender: "male"))

        let req = try #require(captured.get())
        #expect(req.httpMethod == "POST")
        #expect(req.url?.absoluteString == "https://api.example.com/api/v1/bazi/chart")
        #expect(response.yearPillar.gan == "庚")
        #expect(response.daYun.first?.ganZhi == "壬午")
    }

    @Test("getInterpretation：POST /api/v1/bazi/interpretation")
    func getInterpretation() async throws {
        let mock = MockServer()
        let captured = LockedRequestBox()
        mock.handler = { req in
            captured.set(req)
            let body = #"{"request_id":"x","text":"今天适合签约 | 宜：签约 忌：争执"}"#
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!,
                    Data(body.utf8))
        }
        let service = makeService(mock)
        let response = try await service.getInterpretation(InterpretationRequest(
            birthDate: "1990-05-15", birthTime: "14:30:00", birthCity: "北京",
            gender: "male", section: .daily))

        let req = try #require(captured.get())
        #expect(req.url?.absoluteString == "https://api.example.com/api/v1/bazi/interpretation")
        let bodyData = try #require(req.httpBody ?? req.httpBodyStreamData)
        let bodyJSON = try #require(try JSONSerialization.jsonObject(with: bodyData) as? [String: Any])
        #expect(bodyJSON["section"] as? String == "daily")
        #expect(response.text == "今天适合签约 | 宜：签约 忌：争执")
    }

    @Test("getChart：422 校验错误抛出 APIError")
    func getChartValidationError() async {
        let mock = MockServer()
        mock.handler = { req in
            // 这是后端 app/main.py 里 RequestValidationError 自定义处理器的真实返回形状
            // （不是 Pydantic 默认的 {"detail": [...]} 数组），已实测核对过
            let body = #"{"detail":"Validation error","errors":[{"field":"birth_date","message":"Value error, 出生日期不能晚于今天"}]}"#
            return (HTTPURLResponse(url: req.url!, statusCode: 422, httpVersion: nil, headerFields: nil)!,
                    Data(body.utf8))
        }
        let service = makeService(mock)
        await #expect(throws: (any Error).self) {
            _ = try await service.getChart(BaziChartRequest(
                birthDate: "2999-01-01", birthTime: nil, birthCity: "北京", gender: "male"))
        }
    }
}
