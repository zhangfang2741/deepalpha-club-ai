import SwiftUI

/// 晨报 Tab —— 首页。
///
/// 市场三段切换（美股/A 股/港股）→ 拉当日晨报 → 卡片流展示。
/// 后端当日未就绪时自动回退最近一期并标 `stale`，顶部黄条提示；
/// 状态为 generating/pending 时展示生成中视图；失败走错误态 + 重试。
/// 「重点个股」整卡可点，经 `onOpenSymbol` 回调跳到分析 Tab 跑缠论。
struct MorningReportTabView: View {
    /// 个股跳转回调：(market, symbol)，由 MainTabView 转发给共享的 ChanViewModel。
    let onOpenSymbol: (String, String) -> Void
    /// 推送路由（Task 13 的 PushNotificationManager 发通知写入）：非 nil 时切到对应市场。
    @Binding var pendingMarket: String?

    @State private var market: String = "us"
    @State private var response: MorningReportResponse?
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var showHistory = false
    /// 从历史列表选中的日期；nil 表示「今日（自动回退最近一期）」。
    @State private var selectedDate: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    marketSwitch

                    if let errorMessage {
                        errorView(errorMessage)
                    } else if let response {
                        reportBody(response)
                    } else {
                        skeletonView
                    }
                }
                .padding(.horizontal, Theme.contentHInset)
                .padding(.vertical, Theme.contentVInset)
            }
            .scrollBounceBehavior(.basedOnSize)
            .background(Theme.background)
            .refreshable { await load(force: true) }
            .navigationTitle(L("每日晨报"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showHistory = true } label: {
                        Image(systemName: "clock.arrow.circlepath")
                    }
                    .tint(Theme.textSecondary)
                }
            }
            .sheet(isPresented: $showHistory) {
                HistoryDatesView(market: market) { date in
                    selectedDate = date
                    showHistory = false
                    Task { await load(force: true) }
                }
            }
            .task { await load() }
            .onChange(of: market) { _, _ in
                selectedDate = nil
                Task { await load(force: true) }
            }
            .onChange(of: pendingMarket) { _, _ in handlePendingMarket() }
            .onAppear { handlePendingMarket() }
        }
    }

    // MARK: - 市场切换

    private var marketSwitch: some View {
        Picker("", selection: $market) {
            ForEach(StockMarket.allCases) { m in
                Text(m.title).tag(m.rawValue)
            }
        }
        .pickerStyle(.segmented)
    }

    /// 当前市场的本地化名称，用于回退提示等文案。
    private var marketTitle: String {
        StockMarket(rawValue: market)?.title ?? market
    }

    // MARK: - 报告主体（状态机）

    @ViewBuilder
    private func reportBody(_ response: MorningReportResponse) -> some View {
        let status = response.meta.status
        if status == "generating" || status == "pending" {
            generatingView
        } else if let content = response.content {
            LazyVStack(spacing: 12) {
                if response.meta.stale {
                    staleBanner(response.meta)
                }
                if selectedDate != nil {
                    historyBar
                }

                HeadlineCard(headline: content.headline.resolved, metrics: content.metrics)

                ForEach(Array(content.sections.enumerated()), id: \.offset) { _, section in
                    ReportSectionCard(section: section)
                }

                if !content.stocks.isEmpty {
                    Text(L("重点个股"))
                        .font(.subheadline.bold())
                        .foregroundColor(Theme.textPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 4)
                    ForEach(Array(content.stocks.enumerated()), id: \.offset) { _, stock in
                        StockCard(stock: stock) { symbol in
                            onOpenSymbol(market, symbol)
                        }
                    }
                }

                if !content.catalysts.isEmpty {
                    CatalystsCard(catalysts: content.catalysts)
                }

                Text(L("内容由 AI 生成，仅供参考，不构成投资建议"))
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
                    .padding(.top, 2)
            }
        } else {
            errorView(L("暂无内容"))
        }
    }

    /// 回退提示：今日晨报未就绪，正文其实是最近一期。
    private func staleBanner(_ meta: MorningReportMeta) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "clock.badge.exclamationmark")
                .font(.subheadline)
            Text(L("今日晨报暂不可用，以下为 %@ 内容", meta.tradeDate ?? marketTitle))
                .font(.footnote)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .foregroundColor(Color(hex: 0xF5B94F))
        .padding(10)
        .background(Color(hex: 0xF5B94F).opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color(hex: 0xF5B94F).opacity(0.35), lineWidth: 1)
        )
    }

    /// 正在看历史日期时的提示条，提供「回到最新」出口——否则选过一天后没有明显的返回路径。
    private var historyBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "calendar")
                .font(.footnote)
            Text(L("正在查看 %@ 的晨报", selectedDate ?? ""))
                .font(.footnote)
            Spacer(minLength: 8)
            Button(L("回到最新")) {
                selectedDate = nil
                Task { await load(force: true) }
            }
            .font(.footnote.bold())
        }
        .foregroundColor(Theme.textSecondary)
        .padding(10)
        .background(Theme.surfaceAlt, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
    }

    private var generatingView: some View {
        VStack(spacing: 12) {
            ProgressView().tint(Theme.accent)
            Text(L("晨报生成中"))
                .font(.subheadline.bold())
                .foregroundColor(Theme.textPrimary)
            Text(L("通常 07:30 前就绪，稍后下拉刷新"))
                .font(.footnote)
                .foregroundColor(Theme.textSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: 240)
    }

    // MARK: - 骨架与错误

    /// 首次加载的占位骨架：三张与内容卡同构的 redacted 占位卡。
    private var skeletonView: some View {
        VStack(spacing: 12) {
            ForEach(0..<3, id: \.self) { _ in
                VStack(alignment: .leading, spacing: 8) {
                    Text("Section Title")
                        .font(.subheadline.bold())
                    Text("Fact line placeholder.\nInsight line placeholder.\nPrediction line placeholder.")
                        .font(.subheadline)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
                .redacted(reason: .placeholder)
            }
        }
    }

    private func errorView(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "wifi.exclamationmark")
                .font(.largeTitle)
                .foregroundColor(Theme.textSecondary)
            Text(message)
                .font(.subheadline)
                .foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            Button(L("重试")) {
                Task { await load(force: true) }
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.accent)
        }
        .frame(maxWidth: .infinity, minHeight: 240)
        .padding()
    }

    // MARK: - 数据加载

    /// 拉取晨报。`force` 为 false 且已有数据时跳过（.task 每次进 Tab 都会跑）；
    /// `date` 显式指定时优先于 `selectedDate`。
    private func load(force: Bool = false, date: String? = nil) async {
        guard !isLoading else { return }
        if !force && response != nil { return }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            response = try await MorningReportService.report(market: market, date: date ?? selectedDate)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("加载失败，请稍后再试")
        }
    }

    /// 消费推送路由带来的目标市场：切市场、清 pending，重载交给 market 的 onChange。
    private func handlePendingMarket() {
        guard let target = pendingMarket, !target.isEmpty else { return }
        pendingMarket = nil
        guard StockMarket(rawValue: target) != nil else { return }
        market = target
    }
}

// MARK: - 历史日期选择

/// 历史晨报日期列表（倒序）。选中的日期回调给父视图后拉对应一期。
private struct HistoryDatesView: View {
    let market: String
    let onSelect: (String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var dates: [String] = []
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Group {
                if let errorMessage {
                    VStack(spacing: 10) {
                        Text(errorMessage)
                            .font(.subheadline)
                            .foregroundColor(Theme.textSecondary)
                        Button(L("重试")) { Task { await load() } }
                            .buttonStyle(.borderedProminent)
                            .tint(Theme.accent)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if dates.isEmpty {
                    VStack(spacing: 10) {
                        ProgressView().tint(Theme.accent)
                        Text(L("暂无历史晨报"))
                            .font(.footnote)
                            .foregroundColor(Theme.textSecondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List(dates, id: \.self) { date in
                        Button {
                            onSelect(date)
                        } label: {
                            HStack {
                                Text(date)
                                    .font(.subheadline.monospacedDigit())
                                    .foregroundColor(Theme.textPrimary)
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.caption)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                    .listStyle(.insetGrouped)
                    .scrollContentBackground(.hidden)
                    .background(Theme.background)
                }
            }
            .navigationTitle(L("历史晨报"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("关闭")) { dismiss() }
                        .tint(Theme.textSecondary)
                }
            }
        }
        .task { await load() }
    }

    private func load() async {
        do {
            let result = try await MorningReportService.dates(market: market)
            dates = result.dates
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = L("加载失败，请稍后再试")
        }
    }
}
