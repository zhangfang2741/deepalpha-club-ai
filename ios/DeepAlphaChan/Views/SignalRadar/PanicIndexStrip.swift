import Charts
import SwiftUI

/// 三地恐慌指数小卡片 + 市场选择合二为一：点哪张卡就切到哪个市场（驱动下面的信号雷达），
/// 三张卡本身永远同时可见，方便一眼对比三地情绪；选中的那张卡右上角多一个展开按钮，
/// 点开看近一年完整曲线。
struct PanicIndexStrip: View {
    @ObservedObject var radarVM: SignalRadarViewModel
    @ObservedObject var panicVM: PanicIndexViewModel

    @State private var expanded: StockMarket?

    var body: some View {
        HStack(spacing: 8) {
            ForEach(StockMarket.allCases) { market in
                tile(market)
            }
        }
        .task { panicVM.onAppear() }
        .sheet(item: $expanded) { market in
            if let resp = panicVM.responses[market] {
                PanicIndexDetailSheet(market: market, response: resp)
            }
        }
    }

    private func tile(_ market: StockMarket) -> some View {
        let isSelected = radarVM.market == market
        let resp = panicVM.responses[market]

        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(market.title)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(isSelected ? Theme.textPrimary : Theme.textSecondary)
                Spacer()
                if isSelected && resp != nil {
                    Button { expanded = market } label: {
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(Theme.textSecondary)
                    }
                    .accessibilityLabel(L("查看完整曲线"))
                }
            }

            if let resp {
                HStack(alignment: .firstTextBaseline, spacing: 3) {
                    Text("\(Int(resp.current.score.rounded()))")
                        .font(.system(size: 20, weight: .bold, design: .rounded))
                        .foregroundColor(PanicIndexStrip.ratingColor(resp.current.score))
                    Text(PanicIndexStrip.ratingLabel(resp.current.rating))
                        .font(.system(size: 10))
                        .foregroundColor(Theme.textSecondary)
                        .lineLimit(1)
                }
                sparkline(resp)
            } else if panicVM.failedMarkets.contains(market) {
                Button { panicVM.retry(market) } label: {
                    HStack(spacing: 3) {
                        Image(systemName: "arrow.clockwise").font(.system(size: 10))
                        Text(L("重试")).font(.system(size: 11))
                    }
                    .foregroundColor(Theme.textSecondary)
                }
                .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
            } else {
                ProgressView().controlSize(.mini)
                    .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(isSelected ? Theme.accent.opacity(0.12) : Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(isSelected ? Theme.accent : Theme.border, lineWidth: isSelected ? 1.5 : 1)
        )
        .contentShape(Rectangle())
        .onTapGesture { radarVM.switchMarket(market) }
    }

    /// 迷你走势图：只取近 60 个交易日（约 3 个月），隐藏坐标轴，纯粹给个「形状」。
    private func sparkline(_ resp: PanicIndexResponse) -> some View {
        let points = Array(resp.history.suffix(60))
        return Chart(points) { p in
            LineMark(x: .value("date", p.date), y: .value("score", p.score))
                .foregroundStyle(PanicIndexStrip.ratingColor(resp.current.score))
                .lineStyle(StrokeStyle(lineWidth: 1.5))
                .interpolationMethod(.catmullRom)
        }
        .chartYScale(domain: 0...100)
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .frame(height: 24)
    }

    /// 分数 → 颜色，三档：恐慌偏绿（本 App「跌=绿」的语义延伸）、贪婪偏红、中性琥珀色。
    static func ratingColor(_ score: Double) -> Color {
        if score < 45 { return Theme.down }
        if score > 56 { return Theme.up }
        return Theme.segment
    }

    static func ratingLabel(_ rating: String) -> String {
        switch rating {
        case "Extreme Fear": return L("极度恐慌")
        case "Fear": return L("恐慌")
        case "Neutral": return L("中性")
        case "Greed": return L("贪婪")
        case "Extreme Greed": return L("极度贪婪")
        default: return rating
        }
    }
}

/// 展开态：近一年完整曲线 + 当前/一周前/一月前快照。
private struct PanicIndexDetailSheet: View {
    let market: StockMarket
    let response: PanicIndexResponse

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    snapshotRow
                    chart
                    Text(L("分数 0~100，越低越恐慌、越高越贪婪；按近一年区间分位数折算，三地口径统一可比。"))
                        .font(.caption2)
                        .foregroundColor(Theme.textSecondary)
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(response.label)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(L("关闭")) { dismiss() }
                }
            }
        }
    }

    private var snapshotRow: some View {
        HStack(spacing: 20) {
            snapshotItem(L("当前"), response.current)
            snapshotItem(L("一周前"), response.previousWeek)
            snapshotItem(L("一月前"), response.previousMonth)
        }
    }

    private func snapshotItem(_ title: String, _ snap: PanicIndexSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.caption2).foregroundColor(Theme.textSecondary)
            Text("\(Int(snap.score.rounded()))")
                .font(.title3.bold())
                .foregroundColor(PanicIndexStrip.ratingColor(snap.score))
            Text(PanicIndexStrip.ratingLabel(snap.rating))
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)
        }
    }

    private var chart: some View {
        Chart(response.history) { p in
            LineMark(x: .value("date", p.date), y: .value("score", p.score))
                .foregroundStyle(Theme.accent)
                .lineStyle(StrokeStyle(lineWidth: 1.5))
            AreaMark(x: .value("date", p.date), y: .value("score", p.score))
                .foregroundStyle(Theme.accent.opacity(0.12))
        }
        .chartYScale(domain: 0...100)
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 4))
        }
        .frame(height: 220)
        .padding(.vertical, 8)
        .background(Theme.surface.opacity(0.4))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
