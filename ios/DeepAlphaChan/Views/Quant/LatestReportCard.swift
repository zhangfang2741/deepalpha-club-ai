import SwiftUI

/// 基本面研究页的「最新财报」：点开在 App 内阅读（首次下载、之后缓存在本机），阅读页里可存到手机。
struct LatestReportCard: View {
    let market: StockMarket
    let symbol: String

    private enum LoadState { case loading, loaded(LatestReport), none }
    @State private var state: LoadState = .loading
    @State private var opened: OpenedReport?

    var body: some View {
        Group {
            if case .loaded(let r) = state, r.isOK { card(r).transition(.opacity) }
        }
        .animation(.easeOut(duration: 0.2), value: isLoaded)
        .task(id: symbol) { await load() }
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

    /// 存到手机时的文件名：「代码 报告类型 披露日」
    private func shareName(_ r: LatestReport) -> String {
        [symbol.uppercased(), r.reportType, r.filedDate].compactMap { $0 }.joined(separator: " ")
    }

    private struct OpenedReport: Identifiable {
        let report: LatestReport
        var id: String { report.url ?? "" }
    }

    private var isLoaded: Bool {
        if case .loaded = state { return true }
        return false
    }

    private func card(_ r: LatestReport) -> some View {
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
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(Theme.textSecondary)
            }
            .padding(14)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 16))
        }
        .buttonStyle(.plain)
    }

    private func load() async {
        state = .loading
        do { state = .loaded(try await QuantResearchService.latestReport(market: market, symbol: symbol)) }
        catch { state = .none }
    }
}
