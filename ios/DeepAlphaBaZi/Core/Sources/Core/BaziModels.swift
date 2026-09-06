import Foundation

/// 请求：镜像后端 app/schemas/bazi.py 的 BaziChartRequest。
/// birthDate/birthTime 在调用方就格式化成字符串（"yyyy-MM-dd" / "HH:mm:ss"），
/// 不用 Date 的默认 JSON 编码——那和 Python 的 date/time 格式对不上。
public struct BaziChartRequest: Encodable, Sendable {
    public let birthDate: String
    public let birthTime: String?
    public let birthCity: String
    public let gender: String

    public init(birthDate: String, birthTime: String?, birthCity: String, gender: String) {
        self.birthDate = birthDate
        self.birthTime = birthTime
        self.birthCity = birthCity
        self.gender = gender
    }

    enum CodingKeys: String, CodingKey {
        case birthDate = "birth_date"
        case birthTime = "birth_time"
        case birthCity = "birth_city"
        case gender
    }
}

public struct Pillar: Codable, Sendable, Equatable {
    public let gan: String
    public let zhi: String
    public let naYin: String
    public let shiShenGan: String
    public let shiShenZhi: [String]

    public init(gan: String, zhi: String, naYin: String, shiShenGan: String, shiShenZhi: [String]) {
        self.gan = gan
        self.zhi = zhi
        self.naYin = naYin
        self.shiShenGan = shiShenGan
        self.shiShenZhi = shiShenZhi
    }

    enum CodingKeys: String, CodingKey {
        case gan, zhi
        case naYin = "na_yin"
        case shiShenGan = "shi_shen_gan"
        case shiShenZhi = "shi_shen_zhi"
    }
}

public struct DaYunStep: Codable, Sendable, Equatable, Identifiable {
    public var id: String { "\(ganZhi)-\(startAge)" }
    public let ganZhi: String
    public let startAge: Int
    public let endAge: Int

    public init(ganZhi: String, startAge: Int, endAge: Int) {
        self.ganZhi = ganZhi
        self.startAge = startAge
        self.endAge = endAge
    }

    enum CodingKeys: String, CodingKey {
        case ganZhi = "gan_zhi"
        case startAge = "start_age"
        case endAge = "end_age"
    }
}

public struct BaziChartResponse: Codable, Sendable, Equatable {
    public let requestId: String
    public let hourKnown: Bool
    public let solarDate: String
    public let lunarDate: String
    public let trueSolarTime: String?
    public let trueSolarTimeApplied: Bool
    public let yearPillar: Pillar
    public let monthPillar: Pillar
    public let dayPillar: Pillar
    public let timePillar: Pillar?
    public let wuXingDistribution: [String: Int]
    public let daYun: [DaYunStep]
    public let liuNianGanZhi: String

    public init(requestId: String, hourKnown: Bool, solarDate: String, lunarDate: String,
                trueSolarTime: String?, trueSolarTimeApplied: Bool, yearPillar: Pillar,
                monthPillar: Pillar, dayPillar: Pillar, timePillar: Pillar?,
                wuXingDistribution: [String: Int], daYun: [DaYunStep], liuNianGanZhi: String) {
        self.requestId = requestId
        self.hourKnown = hourKnown
        self.solarDate = solarDate
        self.lunarDate = lunarDate
        self.trueSolarTime = trueSolarTime
        self.trueSolarTimeApplied = trueSolarTimeApplied
        self.yearPillar = yearPillar
        self.monthPillar = monthPillar
        self.dayPillar = dayPillar
        self.timePillar = timePillar
        self.wuXingDistribution = wuXingDistribution
        self.daYun = daYun
        self.liuNianGanZhi = liuNianGanZhi
    }

    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case hourKnown = "hour_known"
        case solarDate = "solar_date"
        case lunarDate = "lunar_date"
        case trueSolarTime = "true_solar_time"
        case trueSolarTimeApplied = "true_solar_time_applied"
        case yearPillar = "year_pillar"
        case monthPillar = "month_pillar"
        case dayPillar = "day_pillar"
        case timePillar = "time_pillar"
        case wuXingDistribution = "wu_xing_distribution"
        case daYun = "da_yun"
        case liuNianGanZhi = "liu_nian_gan_zhi"
    }
}

/// section 固定两档：daily(免费今日运势) / deep(付费深度解读)。
public enum InterpretationSection: String, Codable, Sendable {
    case daily
    case deep
}

public struct InterpretationRequest: Encodable, Sendable {
    public let birthDate: String
    public let birthTime: String?
    public let birthCity: String
    public let gender: String
    public let section: InterpretationSection

    public init(birthDate: String, birthTime: String?, birthCity: String, gender: String,
                section: InterpretationSection) {
        self.birthDate = birthDate
        self.birthTime = birthTime
        self.birthCity = birthCity
        self.gender = gender
        self.section = section
    }

    enum CodingKeys: String, CodingKey {
        case birthDate = "birth_date"
        case birthTime = "birth_time"
        case birthCity = "birth_city"
        case gender, section
    }
}

public struct InterpretationResponse: Codable, Sendable, Equatable {
    public let requestId: String
    public let text: String

    public init(requestId: String, text: String) {
        self.requestId = requestId
        self.text = text
    }

    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case text
    }
}
