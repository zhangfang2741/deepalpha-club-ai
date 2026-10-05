import SwiftUI

/// 雷达「基本面研究」tab：股票池里每天综合等级升 / 降的股票，用气泡陈列。
/// 气泡只显示当天变档最多的前 10 只（档数相同按代码排），更多的点「另有 N 个 · 查看全部」。
/// 颜色与变档挂钩，且与缠论雷达同一套：升档 = 红（同买点）、降档 = 绿（同卖点），档数越多越深；气泡大小随新等级（A+ 最大、F 最小）。
struct GradeEventsView: View {
    @ObservedObject var vm: GradeEventsViewModel
    let universeName: String
    let sectorName: (String) -> String
    /// 点某只股票：去看这只股票（与雷达气泡同一入口）。
    let onOpen: (String, String) -> Void

    /// 气泡最多画几个，其余折叠进「查看全部」。
    static let bubbleLimit = 10

    @State private var showAll = false
    /// 在「查看全部」里点了某一行：等面板收起后再打开个股。
    @State private var pending: GradeEvent?

    var body: some View {
        VStack(spacing: 10) {
            header
            if vm.isLoading && vm.response == nil {
                Spacer()
                ProgressView()
                Spacer()
            } else if vm.hasError {
                message(L("评级数据暂时读取失败，稍后再试"))
            } else if vm.days.isEmpty {
                message(L("这个范围最近没有评级升降"))
            } else {
                dayRail
                bubbleField
                legend
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .sheet(isPresented: $showAll, onDismiss: {
            guard let e = pending else { return }
            pending = nil
            onOpen(e.symbol, e.name)
        }) {
            allSheet
        }
    }

    // MARK: - 头部 / 日期轨

    private var header: some View {
        HStack {
            Text(L("%@ · 最近 10 天综合评级升降", universeName))
                .font(.footnote).foregroundColor(Theme.textSecondary)
            Spacer()
        }
    }

    private func message(_ text: String) -> some View {
        VStack {
            Spacer()
            Text(text).font(.footnote).foregroundColor(Theme.textSecondary).multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    /// 日期轨：每一天写「月-日」和升降只数。
    private var dayRail: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(Array(vm.days.enumerated()), id: \.element.id) { i, day in
                    let selected = i == vm.selectedIndex
                    Button { vm.selectedIndex = i } label: {
                        VStack(spacing: 2) {
                            Text(shortDate(day.date)).font(.system(size: 13, weight: .semibold))
                            Text("▲\(day.upCount) ▼\(day.downCount)")
                                .font(.system(size: 10)).foregroundColor(selected ? .white.opacity(0.85) : Theme.textSecondary)
                        }
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .background(selected ? Theme.accent : Theme.surface, in: RoundedRectangle(cornerRadius: 10))
                        .foregroundColor(selected ? .white : Theme.textPrimary)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    // MARK: - 气泡

    private var events: [GradeEvent] { vm.selectedDay?.events ?? [] }

    /// 前 10 只（后端已按变档数从多到少、同档数按代码排）。
    private var shown: [GradeEvent] { Array(events.prefix(Self.bubbleLimit)) }

    private var bubbleField: some View {
        VStack(spacing: 12) {
            BubbleFlow(spacing: 8) {
                ForEach(shown) { e in
                    Button { onOpen(e.symbol, e.name) } label: { bubble(e) }
                        .buttonStyle(.plain)
                }
            }
            .frame(maxWidth: .infinity)
            if events.count > shown.count {
                Button { showAll = true } label: {
                    Text(L("另有 %d 个 · 查看全部", events.count - shown.count))
                        .font(.system(size: 13, weight: .semibold))
                        .padding(.horizontal, 14).padding(.vertical, 7)
                        .background(Theme.surface, in: Capsule())
                        .foregroundColor(Theme.accent)
                }
                .buttonStyle(.plain)
            }
            Spacer(minLength: 0)
        }
        .padding(.top, 6)
    }

    /// 13 档字母等级，A+ 最高、F 最低（与后端 GRADE_ORDER 一致）。
    static let gradeOrder = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]

    /// 气泡大小随新等级：A+ 最大、F 最小；颜色深浅才随变档数。
    static func diameter(grade: String) -> CGFloat {
        let idx = gradeOrder.firstIndex(of: grade) ?? (gradeOrder.count - 1)
        return 92 - 3 * CGFloat(idx)
    }

    /// 与缠论雷达气泡同一套颜色：升档 = 红（同买点）、降档 = 绿（同卖点），深浅随变档数（1 档最浅，5 档及以上最深）。
    static func fill(isUp: Bool, steps: Int) -> Color {
        SignalFormatting.radarColor(side: isUp ? "buy" : "sell", depth: Double(min(max(steps, 1), 5) - 1) / 4)
    }

    static func tint(isUp: Bool) -> Color { isUp ? Theme.up : Theme.down }

    private func bubble(_ e: GradeEvent) -> some View {
        let d = Self.diameter(grade: e.toGrade)
        return VStack(spacing: 1) {
            Text(e.name).font(.system(size: 11, weight: .semibold)).lineLimit(1)
            Text("\(e.fromGrade)→\(e.toGrade)").font(.system(size: 12, weight: .bold))
            Text(e.isUp ? "▲\(e.steps)" : "▼\(e.steps)").font(.system(size: 10)).opacity(0.85)
        }
        .foregroundColor(.white)
        .padding(4)
        .frame(width: d, height: d)
        .background(Circle().fill(Self.fill(isUp: e.isUp, steps: e.steps)))
        .overlay(Circle().stroke(Self.tint(isUp: e.isUp).opacity(0.7), lineWidth: 1))
    }

    private var legend: some View {
        HStack(spacing: 14) {
            legendDot(Theme.up, L("升档"))
            legendDot(Theme.down, L("降档"))
            Text(L("颜色越深变档越多，气泡越大新等级越高")).font(.system(size: 11)).foregroundColor(Theme.textSecondary)
            Spacer()
        }
    }

    private func legendDot(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(text).font(.system(size: 11)).foregroundColor(Theme.textSecondary)
        }
    }

    // MARK: - 查看全部

    private var allSheet: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(events) { e in
                        Button {
                            pending = e
                            showAll = false
                        } label: { row(e) }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 12).padding(.vertical, 8)
            }
            .background(Theme.background)
            .navigationTitle(L("%@ 综合评级升降", vm.selectedDay.map { shortDate($0.date) } ?? ""))
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    private func row(_ e: GradeEvent) -> some View {
        HStack(spacing: 10) {
            Image(systemName: e.isUp ? "arrow.up.right" : "arrow.down.right")
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(Self.tint(isUp: e.isUp))
                .frame(width: 22)
            VStack(alignment: .leading, spacing: 2) {
                Text(e.name).font(.system(size: 15, weight: .semibold)).foregroundColor(Theme.textPrimary)
                HStack(spacing: 6) {
                    Text(e.symbol)
                    if let sector = e.sector { Text("· " + sectorName(sector)) }
                }
                .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text("\(e.fromGrade) → \(e.toGrade)")
                    .font(.system(size: 15, weight: .semibold)).foregroundColor(Theme.textPrimary)
                Text(e.isUp ? L("升 %d 档", e.steps) : L("降 %d 档", e.steps))
                    .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
    }

    private func shortDate(_ iso: String) -> String { String(iso.dropFirst(5)) }
}

/// 简单的气泡流式布局：按行从左到右排，每行居中，放不下换行。
private struct BubbleFlow: Layout {
    var spacing: CGFloat = 8

    private func rows(in width: CGFloat, subviews: Subviews) -> [[Int]] {
        var rows: [[Int]] = [[]]
        var x: CGFloat = 0
        for (i, s) in subviews.enumerated() {
            let w = s.sizeThatFits(.unspecified).width
            if x > 0, x + w > width { rows.append([]); x = 0 }
            rows[rows.count - 1].append(i)
            x += w + spacing
        }
        return rows
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 360
        var height: CGFloat = 0
        for row in rows(in: width, subviews: subviews) {
            height += (row.map { subviews[$0].sizeThatFits(.unspecified).height }.max() ?? 0) + spacing
        }
        return CGSize(width: width, height: max(0, height - spacing))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in rows(in: bounds.width, subviews: subviews) {
            let sizes = row.map { subviews[$0].sizeThatFits(.unspecified) }
            let rowWidth = sizes.map(\.width).reduce(0, +) + spacing * CGFloat(max(row.count - 1, 0))
            var x = bounds.minX + (bounds.width - rowWidth) / 2
            let rowHeight = sizes.map(\.height).max() ?? 0
            for (k, i) in row.enumerated() {
                subviews[i].place(at: CGPoint(x: x, y: y + (rowHeight - sizes[k].height) / 2),
                                  proposal: ProposedViewSize(sizes[k]))
                x += sizes[k].width + spacing
            }
            y += rowHeight + spacing
        }
    }
}
