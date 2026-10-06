import SwiftUI

/// 基本面研究页的「最新财报」「最新年报」：点开在 App 内阅读（首次下载、之后缓存在本机），阅读页里可存到手机、右下角有「AI 总结」。
struct LatestReportCard: View {
    let market: StockMarket
    let symbol: String

    /// 由上层加载好再传进来：卡片本身在没数据时是空视图，空视图上挂的 .task 不会执行，所以加载不能放在这里。
    let report: LatestReport
    /// 最新年报；和最新财报是同一份（刚出完年报时）或取不到就不单列
    var annual: LatestReport? = nil
    @State private var opened: OpenedReport?

    private var annualRow: LatestReport? {
        guard let annual, annual.isOK, annual.url != report.url else { return nil }
        return annual
    }

    var body: some View {
        card
            .sheet(item: $opened) { item in
                if let url = URL(string: item.report.url ?? "") {
                    let context = ReportSummaryContext(market: market, symbol: symbol, kind: item.kind, report: item.report)
                    if item.report.fileType == "html" {
                        FilingWebView(title: item.report.title ?? item.heading, remote: url,
                                      shareName: shareName(item.report), summary: context)
                    } else {
                        ReportPDFView(title: item.report.reportType ?? item.heading, remote: url,
                                      shareName: shareName(item.report), summary: context)
                    }
                }
            }
    }

    /// 存到手机时的文件名：「代码 报告类型 披露日」
    private func shareName(_ r: LatestReport) -> String {
        [symbol.uppercased(), r.reportType, r.filedDate].compactMap { $0 }.joined(separator: " ")
    }

    private struct OpenedReport: Identifiable {
        let report: LatestReport
        let kind: String
        let heading: String
        var id: String { kind + (report.url ?? "") }
    }

    private var card: some View {
        VStack(spacing: 0) {
            row(report, heading: L("最新财报"), kind: "latest")
            if let annualRow {
                Divider().overlay(Theme.border).padding(.horizontal, 14)
                row(annualRow, heading: L("最新年报"), kind: "annual")
            }
        }
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
    }

    private func row(_ r: LatestReport, heading: String, kind: String) -> some View {
        Button { opened = OpenedReport(report: r, kind: kind, heading: heading) } label: {
            HStack(spacing: 12) {
                Image(systemName: "doc.text").font(.title3).foregroundStyle(Theme.accent)
                VStack(alignment: .leading, spacing: 3) {
                    Text(heading).font(QuantTypography.title).foregroundStyle(Theme.textPrimary)
                    Text([r.reportType, r.filedDate.map { L("披露于 %@", $0) }].compactMap { $0 }.joined(separator: " · "))
                        .font(QuantTypography.metadata).foregroundStyle(Theme.textSecondary)
                    if let t = r.title, market != .us {
                        Text(t).font(.caption2).foregroundStyle(Theme.textSecondary).lineLimit(2).multilineTextAlignment(.leading)
                    }
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
