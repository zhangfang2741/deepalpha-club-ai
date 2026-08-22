import SwiftUI

/// 全屏图表。竖屏横屏都能看，横过来能显示更多 K 线。
struct ChartFullscreenView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel

    @EnvironmentObject private var orientation: AppOrientation
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack(alignment: .top) {
            Theme.background.ignoresSafeArea()

            VStack(spacing: 8) {
                header
                LayerToggles(vm: vm)
                    .padding(.horizontal, 12)
                ChanChartView(analysis: analysis, vm: vm)
                ChartLegend()
                    .padding(.bottom, 4)
            }
            .padding(.top, 8)
        }
        .onAppear { orientation.allowLandscape() }
        // 无条件还原。漏了这一步，用户退出后整个 App 会卡在横屏。
        .onDisappear { orientation.lockPortrait() }
    }

    private var header: some View {
        HStack {
            Text(vm.symbol.uppercased())
                .font(.subheadline.bold())
                .foregroundColor(Theme.textPrimary)
            Text(vm.freq == "weekly" ? "周线" : "日线")
                .font(.caption)
                .foregroundColor(Theme.accent)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(Theme.accent.opacity(0.14))
                .clipShape(Capsule())

            Spacer()

            Text("横屏可看更多 K 线")
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)

            Button {
                dismiss()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.title3)
                    .foregroundColor(Theme.textSecondary)
            }
        }
        .padding(.horizontal, 14)
    }
}
