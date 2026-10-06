import SwiftUI

/// 最新财报的中文要点（AI 整理）：同一份财报只生成一次、所有人共用；生成要一会儿时显示进度并自动轮询。
struct ReportSummarySheet: View {
    let market: StockMarket
    let symbol: String
    let report: LatestReport
    var kind: String = "latest"
    /// 阅读页里已经探到的缓存：有就直接显示，不等网络
    var initial: ReportSummaryResponse? = nil

    @Environment(\.dismiss) private var dismiss
    @State private var response: ReportSummaryResponse?
    @State private var failed = false

    init(market: StockMarket, symbol: String, report: LatestReport, kind: String = "latest", initial: ReportSummaryResponse? = nil) {
        self.market = market
        self.symbol = symbol
        self.report = report
        self.kind = kind
        self.initial = initial
        _response = State(initialValue: initial)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let summary = response?.summary {
                        content(summary)
                    } else {
                        status
                    }
                }
                .padding(.horizontal, Theme.contentHInset)
                .padding(.vertical, Theme.contentVInset)
            }
            .background(Theme.background)
            .navigationTitle(L("AI 总结"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("完成")) { dismiss() } } }
        }
        .presentationDragIndicator(.visible)
        .task { await poll() }
    }

    // MARK: 内容

    @ViewBuilder
    private func content(_ s: ReportSummaryResponse.Summary) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text([report.reportType, report.filedDate.map { L("披露于 %@", $0) }].compactMap { $0 }.joined(separator: " · "))
                .font(.caption).foregroundStyle(Theme.textSecondary)
            Text(s.headline).font(.system(size: 18, weight: .semibold)).foregroundStyle(Theme.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }

        if !s.keyNumbers.isEmpty {
            section(L("关键数字")) {
                VStack(spacing: 0) {
                    ForEach(Array(s.keyNumbers.enumerated()), id: \.element.id) { i, n in
                        if i > 0 { Divider().overlay(Theme.border) }
                        HStack(alignment: .firstTextBaseline) {
                            Text(n.label).font(.footnote).foregroundStyle(Theme.textSecondary)
                            Spacer(minLength: 12)
                            VStack(alignment: .trailing, spacing: 1) {
                                Text(n.value).font(.footnote.weight(.semibold)).monospacedDigit().foregroundStyle(Theme.textPrimary)
                                if let c = n.change, !c.isEmpty {
                                    Text(c).font(.caption2).monospacedDigit().foregroundStyle(Theme.textSecondary)
                                }
                            }
                        }
                        .padding(.vertical, 9)
                    }
                }
            }
        }
        if !s.highlights.isEmpty {
            section(L("这期发生了什么")) { bullets(s.highlights) }
        }
        if !s.watchPoints.isEmpty {
            section(L("原文提到的风险与变化")) { bullets(s.watchPoints) }
        }
        if !s.outlook.isEmpty {
            section(L("管理层的说法")) {
                Text(s.outlook).font(.footnote).foregroundStyle(Theme.textPrimary).fixedSize(horizontal: false, vertical: true)
            }
        }

        Text(response?.note ?? "").font(.caption2).foregroundStyle(Theme.textSecondary)
            .fixedSize(horizontal: false, vertical: true)

    }

    private func section<C: View>(_ title: String, @ViewBuilder _ body: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.textSecondary).padding(.horizontal, 4)
            body()
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
        }
    }

    private func bullets(_ items: [String]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, t in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("•").foregroundStyle(Theme.accent)
                    Text(t).font(.footnote).foregroundStyle(Theme.textPrimary).fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    // MARK: 状态

    @ViewBuilder private var status: some View {
        VStack(spacing: 12) {
            if failed {
                Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(Theme.textSecondary)
                Text(L("加载失败，请检查网络后重试")).font(.subheadline).foregroundStyle(Theme.textPrimary)
                Button(L("重试")) { Task { await poll() } }.buttonStyle(.bordered).frame(minHeight: 44)
            } else if let r = response, r.status != "generating" {
                Image(systemName: "text.badge.xmark").font(.largeTitle).foregroundStyle(Theme.textSecondary)
                Text(r.note ?? L("暂时没法整理这份财报的要点")).font(.subheadline).foregroundStyle(Theme.textPrimary)
                    .multilineTextAlignment(.center)
            } else {
                ProgressView()
                Text(L("正在整理要点…")).font(.subheadline).foregroundStyle(Theme.textPrimary)
                Text(L("第一次生成要一会儿，之后所有人秒开")).font(.caption).foregroundStyle(Theme.textSecondary)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 320)
    }

    /// 生成中就每 3 秒问一次，最多约 3 分钟。
    private func poll() async {
        failed = false
        if response?.summary != nil { return }  // 已有缓存，直接显示
        for _ in 0..<60 {
            do {
                let r = try await QuantResearchService.reportSummary(market: market, symbol: symbol, kind: kind)
                response = r
                if r.status != "generating" { return }
            } catch {
                failed = true
                return
            }
            try? await Task.sleep(for: .seconds(3))
            if Task.isCancelled { return }
        }
    }
}
