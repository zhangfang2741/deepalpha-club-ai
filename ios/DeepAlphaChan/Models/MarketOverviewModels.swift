import Foundation

/// 雷达页顶部「宏观 / 行业」两格及其弹层的数据（GET /macro/{market}…）。
/// A 股 / 港股数据未上线时 `available == false`，格子显示「数据建设中」。

/// 大盘市场状态：逐利 / 观望 / 避险。
struct MacroState: Decodable, Equatable {
    let label: String          // risk_on / neutral / risk_off
    let labelText: String
    let probability: Double
    let pRiskOn: Double
    let pNeutral: Double
    let pRiskOff: Double
    let daysInState: Int
    let asOf: String

    enum CodingKeys: String, CodingKey {
        case label, probability
        case labelText = "label_text"
        case pRiskOn = "p_risk_on"
        case pNeutral = "p_neutral"
        case pRiskOff = "p_risk_off"
        case daysInState = "days_in_state"
        case asOf = "as_of"
    }
}

struct MacroStatePoint: Decodable, Identifiable {
    let date: String
    let label: String?
    /// 尚未连续满确认天数（只出现在末尾几天），label 为当日原始判定；旧后端不带该字段。
    let pending: Bool?
    var id: String { date }
}

struct MacroDriver: Decodable, Identifiable {
    let key: String
    let name: String
    let value: Double?
    let unit: String           // percent / point / change
    let change: Double?        // percent=基点，point=点，change=%
    let direction: String?     // up / down / flat
    let impact: String         // positive / negative / neutral
    let text: String
    let asOf: String?
    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, name, value, unit, change, direction, impact, text
        case asOf = "as_of"
    }
}

struct MacroEvent: Decodable, Identifiable, Equatable {
    let date: String
    let time: String
    let country: String
    let name: String
    let importance: Int
    var id: String { "\(date)-\(time)-\(name)" }
}

struct MacroResponse: Decodable {
    let market: String
    let available: Bool
    let state: MacroState?
    let history: [MacroStatePoint]
    let drivers: [MacroDriver]
    let events: [MacroEvent]
}

struct SectorBrief: Decodable, Equatable {
    let key: String
    let name: String
    let rsVsMarket: Double?
    let label: String?

    enum CodingKeys: String, CodingKey {
        case key, name, label
        case rsVsMarket = "rs_vs_market"
    }
}

struct MarketOverview: Decodable {
    let market: String
    let available: Bool
    let macroState: MacroState?
    let nextEvent: MacroEvent?
    let strongest: SectorBrief?
    let weakest: SectorBrief?
    let sectorsAsOf: String?

    enum CodingKeys: String, CodingKey {
        case market, available, strongest, weakest
        case macroState = "macro_state"
        case nextEvent = "next_event"
        case sectorsAsOf = "sectors_as_of"
    }
}

struct SectorRow: Decodable, Identifiable {
    let key: String
    let name: String
    let rsVsMarket: Double?
    let label: String?
    let pRiskOn: Double?
    let hasChildren: Bool
    let buyCount: Int
    let sellCount: Int
    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, name, label
        case rsVsMarket = "rs_vs_market"
        case pRiskOn = "p_risk_on"
        case hasChildren = "has_children"
        case buyCount = "buy_count"
        case sellCount = "sell_count"
    }
}

struct SectorBoard: Decodable {
    let market: String
    let available: Bool
    let asOf: String?
    let radarUniverse: String?
    let radarUniverseName: String?
    let radarDate: String?
    let sectors: [SectorRow]
    let childrenOf: String?

    enum CodingKeys: String, CodingKey {
        case market, available, sectors
        case asOf = "as_of"
        case radarUniverse = "radar_universe"
        case radarUniverseName = "radar_universe_name"
        case radarDate = "radar_date"
        case childrenOf = "children_of"
    }
}

/// 美股行业 key（GICS 11 个一级行业，与后端 regime 行业一致）→ 展示名；顺序即数量相同时的排序。
enum RadarSectorCatalog {
    static let keys: [String] = [
        "technology", "communication", "discretionary", "healthcare", "financials",
        "industrials", "energy", "materials", "staples", "utilities", "realestate",
    ]

    static func name(_ key: String) -> String {
        switch key {
        case "technology": return L("科技")
        case "communication": return L("通讯服务")
        case "discretionary": return L("可选消费")
        case "healthcare": return L("医疗")
        case "financials": return L("金融")
        case "industrials": return L("工业")
        case "energy": return L("能源")
        case "materials": return L("材料")
        case "staples": return L("必需消费")
        case "utilities": return L("公用事业")
        case "realestate": return L("房地产")
        // A 股申万 / 港股恒生行业：key 就是中文名，走本地化表（中文界面原样，英文界面显示英文名）
        default: return L(key)
        }
    }

    static func order(_ key: String) -> Int { keys.firstIndex(of: key) ?? keys.count }
}
