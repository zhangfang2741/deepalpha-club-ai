import SwiftUI

/// 基本面研究页的「最新财报」：点开在 App 内阅读（首次下载、之后缓存在本机），阅读页里可存到手机。
struct LatestReportCard: View {
    let market: StockMarket
    let symbol: String

    /// 由上层加载好再传进来：卡片本身在没数据时是空视图，空视图上挂的 .task 不会执行，所以加载不能放在这里。
    let report: LatestReport
    @State private var opened: OpenedReport?
    @State private var showSummary = false

    var body: some View {
        card(report)
            .sheet(isPresented: $showSummary) { summarySheet }
            .sheet(item: $opened) { item in
                if let url = URL(string: item.report.url ?? "") {
                    if item.report.fileType == "html" {
                        FilingWebView(title: item.report.title ?? L("最新财报"), remote: url, shareName: shareName(item.report))
                    } else {
                        ReportPDFView(title: item.report.reportType ?? L("最新财报"), remote: url, shareName: shareName(item.report))
                    }
                }
            }
    }

    private var summarySheet: some View {
        ReportSummarySheet(market: market, symbol: symbol, report: report) {
            // 先让要点页收起，再开原文（同一时刻只能有一个 sheet）
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { opened = OpenedReport(report: report) }
        }
    }

    /// 存到手机时的文件名：「代码 报告类型 披露日」
    private func shareName(_ r: LatestReport) -> String {
        [symbol.uppercased(), r.reportType, r.filedDate].compactMap { $0 }.joined(separator: " ")
    }

    private struct OpenedReport: Identifiable {
        let report: LatestReport
        var id: String { report.url ?? "" }
    }

    private func card(_ r: LatestReport) -> some View {
        VStack(spacing: 0) {
            Button { opened = OpenedReport(report: r) } label: {
                HStack(spacing: 12) {
                    Image(systemName: "doc.text").font(.title3).foregroundStyle(Theme.accent)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(L("最新财报")).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                        Text([r.reportType, r.filedDate.map { L("披露于 %@", $0) }].compactMap { $0 }.joined(separator: " · "))
                            .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                        if let t = r.title, market != .us {
                            Text(t).font(.caption2).foregroundStyle(Theme.textSecondary).lineLimit(2).multilineTextAlignment(.leading)
                        }
                    }
                    Spacer()
                    Text(L("阅读原文")).font(.caption).foregroundStyle(Theme.textSecondary)
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(Theme.textSecondary)
                }
                .padding(14)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            Divider().overlay(Theme.border).padding(.horizontal, 14)

            Button { showSummary = true } label: {
                HStack(spacing: 12) {
                    Image(systemName: "sparkles").font(.title3).foregroundStyle(Theme.accent)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(L("中文要点")).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                        Text(L("AI 整理的重点：关键数字、变化与风险")).font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    }
                    Spacer()
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(Theme.textSecondary)
                }
                .padding(14)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
    }
}


/// 财报卡加载中的占位：和真实卡片同样的两行结构与高度，灰块缓慢明暗呼吸。
struct LatestReportSkeleton: View {
    @State private var dim = false

    var body: some View {
        VStack(spacing: 0) {
            row(titleWidth: 84, subtitleWidth: 150)
            Divider().overlay(Theme.border).padding(.horizontal, 14)
            row(titleWidth: 72, subtitleWidth: 190)
        }
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
        .opacity(dim ? 0.55 : 1)
        .animation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true), value: dim)
        .onAppear { dim = true }
        .accessibilityLabel(L("正在加载最新财报"))
    }

    private func row(titleWidth: CGFloat, subtitleWidth: CGFloat) -> some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 6).fill(Theme.surfaceAlt).frame(width: 24, height: 24)
            VStack(alignment: .leading, spacing: 6) {
                RoundedRectangle(cornerRadius: 4).fill(Theme.surfaceAlt).frame(width: titleWidth, height: 14)
                RoundedRectangle(cornerRadius: 4).fill(Theme.surfaceAlt).frame(width: subtitleWidth, height: 11)
            }
            Spacer()
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 60, alignment: .leading)
    }
}
