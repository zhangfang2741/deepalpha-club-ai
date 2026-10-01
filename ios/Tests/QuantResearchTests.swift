import Foundation
import SwiftUI

// 量化研究：后端 golden JSON 解码（守护前后端契约）、五维图标签不越界、等级配色。
func L(_ key: String, _ arguments: CVarArg...) -> String {
    String(format: key, arguments: arguments)
}

@main
struct QuantResearchTests {
    static func main() throws {
        let root = CommandLine.arguments[1]
        try decodesGoldenPayloads(root: root)
        try decodesEducationCompatibility(root: root)
        try decodesMoat()
        lifecycleStageBoundaries()
        try decodesAnalystOverview()
        layoutKeepsLabelsInside()
        gradeColors()
        print("QuantResearchTests passed")
    }

    static func decodesGoldenPayloads(root: String) throws {
        for sym in ["NVDA", "JPM", "O", "XOM"] {
            let url = URL(fileURLWithPath: "\(root)/tests/fixtures/quant_research/golden_\(sym).json")
            let r = try JSONDecoder().decode(QuantResearch.self, from: Data(contentsOf: url))
            precondition(r.isOK && r.symbol == sym)
            precondition(r.dimensions.map(\.key) == ["valuation", "growth", "profitability", "momentum", "revisions"])
            precondition(r.scoredDimensions.count == 5, "护城河已移出维度，五维全部计入综合")
            precondition(r.dimensions[4].status == "accumulating")
            precondition(r.dimensions.filter(\.isHighest).count == 1, "\(sym) 最高维度只能有一个")
            precondition(!r.dimensions[0].allMetrics.isEmpty)
            if let stage = r.stage {
                precondition(QuantLifecycleStage(rawValue: stage.key) != nil, "后端阶段必须对应可高亮的节点")
            }
            if sym == "JPM" { precondition(r.stage == nil, "金融公司不应高亮阶段") }
        }
        let nvda = try JSONDecoder().decode(QuantResearch.self, from: Data(contentsOf: URL(
            fileURLWithPath: "\(root)/tests/fixtures/quant_research/golden_NVDA.json")))
        let pe = nvda.dimensions[0].allMetrics.first { $0.key == "pe_fwd" }!
        precondition(pe.formula?.expression.hasPrefix("股价 ") == true)
        precondition(pe.distribution?["p50"] != nil && pe.lowerBetter)
        precondition(nvda.stage?.name == "成长期")
        precondition(nvda.stage?.revenueGrowthPct != nil)
        precondition(nvda.peerGroup?.inUniverse == true)
    }

    static func decodesEducationCompatibility(root: String) throws {
        let url = URL(fileURLWithPath: "\(root)/tests/fixtures/quant_research/golden_NVDA.json")
        let research = try JSONDecoder().decode(QuantResearch.self, from: Data(contentsOf: url))
        precondition(research.dimensions.flatMap(\.allMetrics).allSatisfy {
            !($0.interpretation?.calculation ?? "").isEmpty
        }, "全部指标都应有不依赖数据的通用公式")
        let legacy = Data(#"{"what":"指标定义","role":"投资含义","threshold":"适用边界"}"#.utf8)
        let interpretation = try JSONDecoder().decode(QuantMetricInterpretation.self, from: legacy)
        precondition(interpretation.calculation == nil, "旧响应缺少通用公式时仍应正常解码")
        precondition(interpretation.plain == nil && interpretation.fullName == nil, "旧响应缺少大白话时仍应正常解码")
        let roe = research.dimensions.flatMap(\.allMetrics).first { $0.key == "roe" }!
        precondition(roe.interpretation?.fullName?.contains("净资产收益率") == true)
        precondition(roe.interpretation?.plain?.isEmpty == false && roe.interpretation?.reading?.isEmpty == false)
        precondition(roe.interpretation?.why?.isEmpty == false && roe.interpretation?.purpose?.isEmpty == false,
                     "每项指标都要讲清为什么重要、为什么选它")
        precondition(interpretation.why == nil && interpretation.purpose == nil, "旧响应缺少时仍应正常解码")
        let byKey = Dictionary(uniqueKeysWithValues: research.dimensions.flatMap(\.allMetrics).map { ($0.key, $0) })
        precondition(byKey["roe"]?.fullNameSubtitle?.contains("净资产收益率") == true, "缩写指标要显示全称")
        precondition(byKey["gross_m"]?.fullNameSubtitle == nil, "名称已是全称时不重复")
        precondition(byKey["pe_fwd"]?.fullNameSubtitle == nil, "去掉期间修饰后重复的也不显示")
    }

    static func decodesMoat() throws {
        let json = """
        {"status":"ok","status_note":null,"rating":"wide","rating_name":"宽护城河","trend":"widening",
         "trend_name":"超额回报在扩大","summary":"主要来源：转换成本",
         "evidence":{"metric":"roic","metric_name":"投入资本回报率 ROIC","years":[{"year":2025,"value":0.6}],
                     "cost_of_capital":0.1,"years_above":1,"n_years":1,"avg_spread":0.5,"level":"strong",
                     "level_name":"财务证据强","text":"过去 1 年里 1 年 ROIC 高于资金成本"},
         "sources":[{"key":"switching_costs","name":"转换成本","strength":"strong","strength_name":"强",
                     "reason":"r","quotes":["q"]}],
         "threats":"t","filed_date":"2026-02-25","tenk_url":"u","method_note":"m"}
        """
        let m = try JSONDecoder().decode(QuantMoat.self, from: Data(json.utf8))
        precondition(m.isOK && m.sources.first?.dots == 3 && m.evidence?.yearsAbove == 1)
        let pending = try JSONDecoder().decode(QuantMoat.self, from: Data(#"{"status":"pending","status_note":"评估中","sources":[],"method_note":"m"}"#.utf8))
        precondition(!pending.isOK && pending.rating == nil)
    }

    static func lifecycleStageBoundaries() {
        precondition(QuantLifecycleStage.allCases.map(\.rawValue) == ["intro", "growth", "mature", "shakeout", "decline"])
        precondition(QuantLifecycleStage(rawValue: "unknown") == nil, "未知阶段不能错误地高亮成熟期")
        precondition(QuantLifecycleStage.signLabel(0) == "零值 · 按非正值处理")
        precondition(QuantLifecycleStage.signLabel(-1) == "负值 · 流出")
        precondition(QuantLifecycleStage.signLabel(1) == "正值 · 流入")
    }

    static func decodesAnalystOverview() throws {
        let json = """
        {"symbol":"NVDA","status":"ok","status_note":null,
         "ratings":{"current":{"date":"2026-09-01","strong_buy":11,"buy":49,"hold":2,"sell":1,"strong_sell":0,"total":63},
                    "history":[],"change_text":"近 3 个月"},
         "price_target":{"price":227.21,"high":515,"low":270,"median":322.5,"consensus":345.21,"vs_price_pct":41.9,
                         "vs_price_text":"x","last_month_count":1,"last_quarter_count":23,"last_year_count":94},
         "earnings":{"quarters":[{"date":"2026-08-26","eps_actual":2.22,"eps_estimated":2.09,"surprise_pct":6.2}],
                     "next":{"date":"2026-11-18","eps_estimated":2.47,"revenue_estimated":1.087e11}},
         "recent_grades":[{"date":"2026-09-29","firm":"Rosenblatt","action":"maintain","action_label":"维持",
                           "previous_grade":"Buy","previous_grade_label":"买入","new_grade":"Buy","new_grade_label":"买入"}],
         "note":"n"}
        """
        let o = try JSONDecoder().decode(AnalystOverview.self, from: Data(json.utf8))
        precondition(o.isOK && o.ratings?.current?.total == 63 && o.recentGrades.count == 1)
        precondition(o.earnings?.next?.date == "2026-11-18")
    }

    static func layoutKeepsLabelsInside() {
        let names = [("估值", "C-"), ("成长", "B+"), ("盈利能力", "A+"), ("动量", "C+"), ("EPS 修正", "暂无")]
        let longNames = [("Valuation", "C-"), ("Growth", "B+"), ("Profitability", "A+"),
                         ("Momentum", "C+"), ("EPS Revisions", "A")]
        for width in [300.0, 342.0, 390.0] {
            for titles in [names, longNames] {
                let size = CGSize(width: width, height: 280)
                let layout = FiveDimensionLayout(size: size, titles: titles.map { (name: $0.0, grade: $0.1) })
                let bounds = CGRect(origin: .zero, size: size)
                for l in layout.labels {
                    precondition(bounds.contains(l.rect), "标签越界 width=\(width) \(l.rect)")
                }
                precondition(layout.radius >= FiveDimensionLayout.minRadius, "半径过小 \(layout.radius)")
                let top = layout.point(index: 0, count: 5, percentile: 100)
                precondition(abs(top.x - layout.center.x) < 0.001 && top.y < layout.center.y, "第一根轴朝上")
            }
        }
    }

    static func gradeColors() {
        precondition(QuantGradeStyle.color("A+") == Theme.up)
        precondition(QuantGradeStyle.color("F") == Theme.down)
        precondition(QuantGradeStyle.color("C") == Theme.textSecondary)
        precondition(QuantGradeStyle.color(nil) == Theme.textSecondary)
    }
}
