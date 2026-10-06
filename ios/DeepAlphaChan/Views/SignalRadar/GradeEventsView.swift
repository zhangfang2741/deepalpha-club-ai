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
    @State private var showInfo = false

    var body: some View {
        // 行间距、行高、底部免责声明都与缠论雷达（SignalRadarView.radarContent）保持一致，两个 tab 的画布高度才一样
        VStack(spacing: 12) {
            if vm.hasError {
                message(L("评级数据暂时读取失败，稍后再试"))
            } else if vm.isUnsupported {
                message(vm.kind.unsupportedMessage)
            } else if vm.days.isEmpty {
                message(vm.pendingSymbols > 0
                        ? L("正在汇总券商评级，还剩 %lld 只，稍候会自动出现", vm.pendingSymbols)
                        : vm.kind.emptyMessage)
            } else {
                summaryRow
                field()
                legend
                dayRail
                Spacer(minLength: 0)
                disclaimer
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
            Text(String(format: vm.kind.summaryTitle, universeName))
                .font(.footnote).foregroundColor(Theme.textSecondary)
            Spacer()
            Text("\(all.filter(\.isUp).count) \(vm.kind.upWord)").foregroundColor(Theme.up)
            Text("\(all.filter { !$0.isUp }.count) \(vm.kind.downWord)").foregroundColor(Theme.down)
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
            legendDot(Theme.up, vm.kind.upWord)
            legendDot(Theme.down, vm.kind.downWord)
            Text(vm.kind.legendHint)
                .font(.system(size: 10)).foregroundColor(Theme.textSecondary)
                .lineLimit(1).minimumScaleFactor(0.8)
            Spacer(minLength: 4)
            Button { showInfo = true } label: {
                Image(systemName: "questionmark.circle")
                    .font(.system(size: 15))
                    .foregroundColor(Theme.textSecondary)
            }
            .accessibilityLabel(L("算法说明"))
            .sheet(isPresented: $showInfo) { infoSheet }
        }
    }

    /// 与缠论雷达底部同一位置、同一字号的一行说明。
    private var disclaimer: some View {
        Text(vm.kind.disclaimer)
            .font(.caption2)
            .foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.top, 4)
    }

    /// 图例旁问号：这张雷达怎么看。
    private var infoSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(vm.kind.infoLines, id: \.self) { line in
                        Text(line).font(.subheadline).foregroundColor(Theme.textPrimary)
                    }
                }
                .padding(16)
            }
            .background(Theme.background)
            .navigationTitle(L("算法说明"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("完成")) { showInfo = false } } }
        }
        .presentationDetents([.medium, .large])
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
            .navigationTitle(String(format: vm.kind.allTitle, vm.selectedDay.map { SignalRadarView.monthDay($0.date) } ?? ""))
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
                if vm.kind == .grade {
                    Text("\(e.fromGrade) → \(e.toGrade)")
                        .font(.system(size: 15, weight: .semibold)).foregroundColor(Theme.textPrimary)
                    Text(e.isUp ? L("升 %lld 档", e.steps) : L("降 %lld 档", e.steps))
                        .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
                } else {
                    Text(e.isUp ? L("净上调 %lld 家", e.steps) : L("净下调 %lld 家", e.steps))
                        .font(.system(size: 15, weight: .semibold)).foregroundColor(Theme.textPrimary)
                    Text(L("上调 %lld · 下调 %lld", e.upgrades, e.downgrades))
                        .font(.system(size: 11)).foregroundColor(Theme.textSecondary)
                }
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12))
    }
}
