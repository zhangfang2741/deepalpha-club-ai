import Foundation

func L(_ value: String) -> String { value }

@main
struct RadarQuantDecodingTests {
    static func main() throws {
        let signal: [String: Any] = [
            "symbol": "TEST", "name": "测试", "side": "buy", "label": "二买",
            "signal_type": "buy2", "date": "2026-09-30", "price": 10,
            "strength": 0.8, "bias": "bullish", "signal_strength": "strong",
            "confirmed": true, "pivot_stage_depth": 0.5,
        ]
        var payload: [String: Any] = [
            "date": "2026-09-30", "buy_count": 1, "sell_count": 0, "signals": [signal],
        ]
        let decoder = JSONDecoder()
        let legacy = try decoder.decode(RadarDay.self, from: JSONSerialization.data(withJSONObject: payload))
        precondition(legacy.quantFilter == nil && legacy.signals[0].quantGrade == nil)
        precondition(legacy.candidates.isEmpty)
        var rated = signal
        rated["quant_grade"] = "A-"
        rated["quant_score"] = 67.7
        rated["quant_as_of"] = "2026-09-29"
        rated["quant_status"] = "eligible"
        payload["signals"] = [rated]
        payload["quant_filter"] = [
            "min_grade": "A-", "status": "ready", "eligible": 20, "below_threshold": 60,
            "missing": 15, "stale": 5, "max_age_days": 7, "preserve_sells": false,
        ]
        let current = try decoder.decode(RadarDay.self, from: JSONSerialization.data(withJSONObject: payload))
        precondition(current.quantFilter?.eligible == 20)
        precondition(current.quantFilter?.preserveSells == false)
        precondition(current.signals[0].quantGrade == "A-")
        precondition(current.signals[0].quantScore == 67.7)
        precondition(current.signals[0].quantAsOf == "2026-09-29")
        print("雷达量化评级解码测试通过")
    }
}
