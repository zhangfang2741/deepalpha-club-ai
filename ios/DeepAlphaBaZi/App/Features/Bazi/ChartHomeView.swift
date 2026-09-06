import SwiftUI
import DeepAlphaBaZiCore

/// 已排盘首页：四柱 + 五行(免费，纯本地数据) + 今日运势(免费，按日缓存) +
/// 概览/大运流年🔒/深度解读🔒 分段(后两段的付费墙 UI 在这个 Plan 里只是锁定态展示，
/// 真实 StoreKit 购买接入是下一个 Plan 的工作)。
struct ChartHomeView: View {
    @Environment(BaziViewModel.self) private var baziVM

    enum ChartSection: String, CaseIterable, Identifiable {
        case overview = "概览"
        case daYun = "大运流年"
        case deep = "深度解读"
        var id: String { rawValue }
    }
    @State private var selectedSection: ChartSection = .overview

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let chart = baziVM.profile?.chart {
                    PillarsCardView(chart: chart)
                    WuXingCardView(distribution: chart.wuXingDistribution)
                }

                DailyFortuneCardView()

                Picker("分段", selection: $selectedSection) {
                    ForEach(ChartSection.allCases) { section in
                        Text(section.rawValue).tag(section)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()

                switch selectedSection {
                case .overview:
                    EmptyView()
                case .daYun:
                    DaYunSectionView()
                case .deep:
                    DeepInterpretationView()
                }
            }
            .padding()
        }
        .navigationTitle("我的八字")
        .task {
            await baziVM.loadDailyFortuneIfNeeded()
        }
    }
}

private struct PillarsCardView: View {
    let chart: BaziChartResponse

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("四柱").font(.headline)
            HStack {
                pillarColumn("年柱", chart.yearPillar)
                pillarColumn("月柱", chart.monthPillar)
                pillarColumn("日柱", chart.dayPillar)
                if let time = chart.timePillar {
                    pillarColumn("时柱", time)
                } else {
                    VStack {
                        Text("时柱").font(.caption).foregroundStyle(.secondary)
                        Text("未知").foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }

    private func pillarColumn(_ title: String, _ pillar: Pillar) -> some View {
        VStack {
            Text(title).font(.caption).foregroundStyle(.secondary)
            Text("\(pillar.gan)\(pillar.zhi)").font(.title3.bold())
        }
        .frame(maxWidth: .infinity)
    }
}

private struct WuXingCardView: View {
    let distribution: [String: Int]
    private let order = ["jin", "mu", "shui", "huo", "tu"]
    private let labels: [String: String] = ["jin": "金", "mu": "木", "shui": "水", "huo": "火", "tu": "土"]

    var body: some View {
        HStack {
            ForEach(order, id: \.self) { key in
                VStack {
                    Text(labels[key] ?? key)
                    Text("\(distribution[key] ?? 0)").font(.headline)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}

private struct DailyFortuneCardView: View {
    @Environment(BaziViewModel.self) private var baziVM

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("今日运势").font(.headline)
            if baziVM.isLoadingFortune {
                ProgressView()
            } else if let text = baziVM.dailyFortuneText {
                Text(text)
            } else if let error = baziVM.fortuneError {
                // 加载失败：展示错误 + 重试按钮，不能让卡片停在一个死态什么都不能做
                VStack(alignment: .leading, spacing: 4) {
                    Text(error).foregroundStyle(.red)
                    Button("点击重试") {
                        Task { await baziVM.loadDailyFortuneIfNeeded() }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
    }
}
