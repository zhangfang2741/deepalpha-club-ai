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
            precondition(r.dimensions.last?.status == "accumulating")
            precondition(r.dimensions.filter(\.isHighest).count == 1, "\(sym) 最高维度只能有一个")
            precondition(!r.dimensions[0].allMetrics.isEmpty)
        }
        let nvda = try JSONDecoder().decode(QuantResearch.self, from: Data(contentsOf: URL(
            fileURLWithPath: "\(root)/tests/fixtures/quant_research/golden_NVDA.json")))
        let pe = nvda.dimensions[0].allMetrics.first { $0.key == "pe_fwd" }!
        precondition(pe.formula?.expression.hasPrefix("股价 ") == true)
        precondition(pe.distribution?["p50"] != nil && pe.lowerBetter)
        precondition(nvda.stage?.name == "成熟期")
        precondition(nvda.peerGroup?.inUniverse == true)
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
