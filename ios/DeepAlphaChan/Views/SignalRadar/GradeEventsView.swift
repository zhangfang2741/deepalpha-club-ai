import SwiftUI

/// 雷达「基本面研究」tab：股票池里每天综合等级升 / 降的股票。
/// 只陈列事实（谁在哪天从几级到几级），不排序推荐；升降用箭头 + 中性色，红 / 绿只留给缠论已成立的买卖点。
struct GradeEventsView: View {
    @ObservedObject var vm: GradeEventsViewModel
    let universeName: String
    let sectorName: (String) -> String
    /// 点某一行：去看这只股票（与雷达气泡同一入口）。
    let onOpen: (String, String) -> Void

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
                eventList
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

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

    private var eventList: some View {
        ScrollView {
            LazyVStack(spacing: 8) {
                ForEach(vm.selectedDay?.events ?? []) { event in
                    Button { onOpen(event.symbol, event.name) } label: { row(event) }
                        .buttonStyle(.plain)
                }
            }
        }
    }

    private func row(_ e: GradeEvent) -> some View {
        HStack(spacing: 10) {
            Image(systemName: e.isUp ? "arrow.up.right" : "arrow.down.right")
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(e.isUp ? Theme.accent : Theme.textSecondary)
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
