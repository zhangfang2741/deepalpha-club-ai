import SwiftUI

/// 分析结果详情页（第二页）。
///
/// 由「条件页」在分析成功后 push 进来。只负责呈现结果：图表 + 结论/买卖点/GAP。
/// 改条件请返回上一页——条件与结果分离，各自专注一件事。
struct ResultDetailView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel

    @EnvironmentObject private var orientation: AppOrientation

    @State private var showFullscreenChart = false

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                ChartSection(analysis: analysis, vm: vm, onFullscreen: openFullscreen)

                ResultSegments(analysis: analysis)

                compactDisclaimer
            }
            .padding(14)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(Theme.background)
        .navigationTitle(navTitle)
        .navigationBarTitleDisplayMode(.inline)
        .fullScreenCover(isPresented: $showFullscreenChart) {
            ChartFullscreenView(analysis: analysis, vm: vm)
                .environmentObject(orientation)
        }
    }

    private var navTitle: String {
        let freq = vm.freq == "weekly" ? "周线" : "日线"
        return "\(vm.symbol.uppercased()) · \(freq)"
    }

    /// 打开全屏图表（转屏 + 关呈现动画，逻辑同条件页原实现）。
    private func openFullscreen() {
        orientation.enterLandscape()
        var tx = Transaction()
        tx.disablesAnimations = true
        withTransaction(tx) { showFullscreenChart = true }
    }

    /// 压缩版免责声明。完整版在「我的」页——App Store 要求这个可见，不能删。
    private var compactDisclaimer: some View {
        Text("算法自动生成，仅供技术研究，不构成投资建议。")
            .font(.caption2)
            .foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.top, 4)
    }
}
