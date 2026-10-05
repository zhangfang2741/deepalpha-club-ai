import SwiftUI

/// 雷达「基本面研究」tab 的外框：概览行 + 雷达画布（由 SignalRadarView 传入，与缠论雷达同一块画布：多环、浮动动画、摆位）
/// + 图例 + 日期轨。画布里每个气泡 = 选中日在场的一只评级升降股票：代码 + 名称 + ▲/▼ 变档数；
/// 升档红、降档绿（同缠论买卖点色）；环 = 新等级（A / B / C 及以下，越靠中心评级越高）；颜色越深、气泡越大变档越多。
struct GradeEventsView<Field: View>: View {
    @ObservedObject var vm: GradeEventsViewModel
    let universeName: String
    let sectorName: (String) -> String
    /// 「查看全部」半屏是否打开（按钮在画布里，状态放在外面）。
    @Binding var showAll: Bool
    /// 点某只股票：去看这只股票（与雷达气泡同一入口）。
    let onOpen: (String, String) -> Void
    @ViewBuilder let field: () -> Field

    /// 在「查看全部」里点了某一行：等面板收起后再打开个股。
    @State private var pending: GradeEvent?

    var body: some View {
        VStack(spacing: 10) {
            if vm.isLoading && vm.response == nil {
                Spacer()
                ProgressView()
                Spacer()
            } else if vm.hasError {
                message(L("评级数据暂时读取失败，稍后再试"))
            } else if vm.days.isEmpty {
                message(L("这个范围最近没有评级升降"))
            } else {
                summaryRow
                field()
                legend
                dayRail
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

    // MARK: - 概览 / 图例 / 日期轨

    /// 与缠论雷达的 metaRow 同一位置：指数名 + 在场的升降只数。
    private var summaryRow: some View {
        let all = vm.dayEvents
        return HStack(spacing: 8) {
            Text(L("%@ · 综合评级升降", universeName))
                .font(.footnote).foregroundColor(Theme.textSecondary)
            Spacer()
            Text(L("%lld 升档", all.filter(\.isUp).count)).foregroundColor(Theme.up)
            Text(L("%lld 降档", all.filter { !$0.isUp }.count)).foregroundColor(Theme.down)
        }
        .font(.footnote)
    }

    private func message(_ text: String) -> some View {
        VStack {
            Spacer()
            Text(text).font(.footnote).foregroundColor(Theme.textSecondary).multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private var legend: some View {
        HStack(spacing: 14) {
            legendDot(Theme.up, L("升档"))
            legendDot(Theme.down, L("降档"))
            Text(L("越靠中心评级越高 · 颜色越深、气泡越大变档越多"))
                .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
                .lineLimit(1).minimumScaleFactor(0.8)
            Spacer()
        }
    }

    private func legendDot(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 4) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(text).font(.system(size: 11)).foregroundColor(Theme.textSecondary)
        }
    }

    /// 日期轨：与缠论雷达同一套格子（上面星期 / 今日，下面月-日）。
    private var dayRail: some View {
        VStack(spacing: 6) {
            HStack {
                Text(L("选择日期")).font(.caption).foregroundColor(Theme.textSecondary)
                Spacer()
                Text(L("← 左右滑动 →")).font(.caption2).foregroundColor(Theme.textSecondary)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(Array(vm.days.enumerated()), id: \.element.id) { i, day in
                        dayChip(day, active: i == vm.selectedIndex) { vm.selectedIndex = i }
                    }
                }
                .padding(.horizontal, 2)
            }
        }
    }

    private func dayChip(_ day: GradeDay, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 3) {
                Text(SignalRadarView.dayLabel(day.date))
                    .font(.system(size: 9))
                    .foregroundColor(active ? .white.opacity(0.85) : Theme.textSecondary)
                Text(SignalRadarView.monthDay(day.date))
                    .font(.system(size: 13, weight: .bold, design: .monospaced))
                    .foregroundColor(active ? .white : Theme.textPrimary)
            }
            .frame(width: 56)
            .padding(.vertical, 8)
            .background(active ? Theme.accent : Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(active ? Theme.accent : Theme.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // MARK: - 查看全部

    private var allSheet: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(vm.dayEvents) { e in
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
            .navigationTitle(L("%@ 综合评级升降", vm.selectedDay.map { SignalRadarView.monthDay($0.date) } ?? ""))
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }

    private func row(_ e: GradeEvent) -> some View {
        let tint = e.isUp ? Theme.up : Theme.down
        return HStack(spacing: 10) {
            Image(systemName: e.isUp ? "arrow.up.right" : "arrow.down.right")
                .font(.system(size: 14, weight: .bold)).foregroundColor(tint).frame(width: 22)
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
                Text(e.isUp ? L("升 %lld 档", e.steps) : L("降 %lld 档", e.steps))
                    .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
    }
}
