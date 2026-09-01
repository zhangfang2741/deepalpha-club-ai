import SwiftUI

/// 分析结果详情页（第二页）。
///
/// 由「条件页」在分析成功后 push 进来。只负责呈现结果：图表 + 形态分析/买卖点。
/// 改条件请返回上一页——条件与结果分离，各自专注一件事。
struct ResultDetailView: View {
    let analysis: ChanAnalysis
    @ObservedObject var vm: ChanViewModel

    @EnvironmentObject private var orientation: AppOrientation

    @State private var showFullscreenChart = false

    /// 用户当前拖到/缩放到的图表窗口，分享时原样交给离屏渲染。
    @State private var chartWindow: ChartWindow?
    @State private var shareItem: ShareItem?
    @State private var isRendering = false
    @State private var showShareError = false

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                ChartSection(analysis: analysis, vm: vm,
                             onFullscreen: openFullscreen,
                             onWindowChange: { chartWindow = $0 })

                ResultSegments(analysis: analysis)

                compactDisclaimer
            }
            .padding(.horizontal, Theme.contentHInset)
            .padding(.vertical, Theme.contentVInset)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(Theme.background)
        .navigationTitle(navTitle)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) { shareButton }
        }
        .sheet(item: $shareItem) { item in
            ShareSheet(items: [item.image, item.text])
        }
        .alert(L("生成分享图失败"), isPresented: $showShareError) {
            Button(L("好"), role: .cancel) {}
        } message: {
            Text(L("请稍后重试。"))
        }
        .fullScreenCover(isPresented: $showFullscreenChart) {
            ChartFullscreenView(analysis: analysis, vm: vm)
                .environmentObject(orientation)
        }
    }

    private var navTitle: String {
        let freq = vm.freq == "weekly" ? L("周线") : L("日线")
        return "\(vm.symbol.uppercased()) · \(freq)"
    }

    /// 打开全屏图表（转屏 + 关呈现动画，逻辑同条件页原实现）。
    private func openFullscreen() {
        orientation.enterLandscape()
        var tx = Transaction()
        tx.disablesAnimations = true
        withTransaction(tx) { showFullscreenChart = true }
    }

    // MARK: - 分享

    private var shareButton: some View {
        Button(action: share) {
            if isRendering {
                ProgressView()
            } else {
                Image(systemName: "square.and.arrow.up")
            }
        }
        // 渲染期间禁用，防连点弹出两个分享面板
        .disabled(isRendering)
        .accessibilityLabel(L("分享分析图"))
        .accessibilityHint(L("生成一张带二维码的分析图并打开分享面板"))
    }

    /// 点按才渲染：进页面就预渲染的话，绝大多数不分享的用户白付这份开销。
    private func share() {
        isRendering = true
        // 让按钮先切到 loading 再开渲染，否则同步渲染会把这一帧吃掉，看着像没反应
        DispatchQueue.main.async {
            let image = ShareCardRenderer.render(analysis: analysis, vm: vm, window: chartWindow)
            isRendering = false
            guard let image else {
                showShareError = true
                return
            }
            shareItem = ShareItem(image: image,
                                  text: ShareCardRenderer.shareText(analysis: analysis, vm: vm))
        }
    }

    /// 压缩版免责声明。完整版在「我的」页——App Store 要求这个可见，不能删。
    private var compactDisclaimer: some View {
        Text(L("算法自动生成，仅供技术研究，不构成投资建议。"))
            .font(.caption2)
            .foregroundColor(Theme.textSecondary)
            .frame(maxWidth: .infinity)
            .padding(.top, 4)
    }
}

/// 分享内容。`sheet(item:)` 要求 Identifiable，UIImage 不是，故包一层。
struct ShareItem: Identifiable {
    let id = UUID()
    let image: UIImage
    let text: String
}
