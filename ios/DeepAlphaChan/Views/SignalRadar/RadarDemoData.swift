import Foundation

/// 未订阅高级版时展示的示例雷达数据：钉死某一天，不随"今天"变化，也不发网络请求。
///
/// 目的是让用户在真正订阅前就看到"这功能长什么样、信号有多真实"——比空白锁定页
/// 更有说服力，又不会像展示真实今日数据那样把当下可操作的信号免费泄露出去（挑一批
/// 有代表性的信号组合，不是某天扫描出的真实结果，价格/强弱仅作展示用）。
///
/// 三个市场各配一组，跟着顶部恐慌指数卡片切市场联动——免费用户切市场时雷达内容
/// 也跟着变，不会显得和上面的市场选择脱节。
enum RadarDemoData {
    /// 演示日期，长期固定；不是"最近"，往后运行多久都显示这一天。
    static let dayDate = "2026-08-01"

    static func day(for market: StockMarket) -> RadarDay {
        let items = signals(for: market)
        return RadarDay(
            date: dayDate,
            buyCount: items.filter(\.isBuy).count,
            sellCount: items.filter { !$0.isBuy }.count,
            signals: items
        )
    }

    private static func signals(for market: StockMarket) -> [RadarSignal] {
        switch market {
        case .us:
            return [
                signal(symbol: "AAPL", name: "", side: "buy", label: L("三买"), signalType: "buy3",
                       price: 254.32, strength: 0.82, signalStrength: "strong", bias: "bullish",
                       confirmed: true, subLevelVerdict: "resonance_buy"),
                signal(symbol: "NVDA", name: "", side: "sell", label: L("二卖"), signalType: "sell2",
                       price: 187.60, strength: 0.55, signalStrength: "medium", bias: "bearish", confirmed: true),
                signal(symbol: "TSLA", name: "", side: "buy", label: L("一买"), signalType: "buy1",
                       price: 412.08, strength: 0.38, signalStrength: "weak", bias: "bullish", confirmed: false),
            ]
        case .cn:
            return [
                signal(symbol: "688981", name: "中芯国际", side: "buy", label: L("三买"), signalType: "buy3",
                       price: 92.15, strength: 0.79, signalStrength: "strong", bias: "bullish",
                       confirmed: true, subLevelVerdict: "resonance_buy"),
                signal(symbol: "600519", name: "贵州茅台", side: "sell", label: L("二卖"), signalType: "sell2",
                       price: 1489.00, strength: 0.52, signalStrength: "medium", bias: "bearish", confirmed: true),
                signal(symbol: "300750", name: "宁德时代", side: "buy", label: L("二买"), signalType: "buy2",
                       price: 268.40, strength: 0.61, signalStrength: "medium", bias: "bullish", confirmed: true),
            ]
        case .hk:
            return [
                signal(symbol: "2015", name: "理想汽车-W", side: "buy", label: L("三买"), signalType: "buy3",
                       price: 98.65, strength: 0.77, signalStrength: "strong", bias: "bullish", confirmed: true),
                signal(symbol: "0700", name: "腾讯控股", side: "sell", label: L("一卖"), signalType: "sell1",
                       price: 412.40, strength: 0.44, signalStrength: "weak", bias: "bearish", confirmed: false),
                signal(symbol: "9988", name: "阿里巴巴-SW", side: "buy", label: L("二买"), signalType: "buy2",
                       price: 88.90, strength: 0.58, signalStrength: "medium", bias: "bullish",
                       confirmed: true, subLevelVerdict: "resonance_buy"),
            ]
        }
    }

    private static func signal(
        symbol: String, name: String, side: String, label: String, signalType: String,
        price: Double, strength: Double, signalStrength: String, bias: String, confirmed: Bool,
        subLevelVerdict: String? = nil
    ) -> RadarSignal {
        RadarSignal(
            symbol: symbol, name: name, side: side, label: label, signalType: signalType,
            date: dayDate, price: price, strength: strength, bias: bias,
            signalStrength: signalStrength, confirmed: confirmed, pivotStageDepth: 0.6,
            subLevelVerdict: subLevelVerdict, subLevelLabel: nil, ageDays: 0
        )
    }
}
