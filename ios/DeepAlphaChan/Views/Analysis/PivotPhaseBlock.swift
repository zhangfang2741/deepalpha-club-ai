import SwiftUI

/// 结构位置：全局判定图（全部可能结果的地图）+ 当前状态详情。
/// 不是必然依次完成的进度条——图上五个框是全部可能结果，点哪个看哪个的规则。
///
/// 不用 SectionCard：这张图紧跟在上面的内容下面，不需要再有一个
/// 「01·结构位置」大标题分隔。
struct PivotPhaseBlock: View {
    let phase: PivotPhase
    /// 页面可用内容宽度（`ResultDetailView` 顶层测量一次后逐层传下来），
    /// 用于让内部判定图按真实卡片宽度绘制，而不是自己现测现算（那样每次
    /// 切换「当前状态」tab 都会先用设计稿宽度渲染一帧，宽于绝大多数机型的
    /// 卡片可用宽度，导致横向溢出）。这里的水平内边距是 16*2=32。
    var contentWidth: CGFloat?

    private let horizontalPadding: CGFloat = 16

    var body: some View {
        Group {
            if let contentWidth {
                // 量到了页面宽度：用硬性的 `.frame(width:)` 把这张卡片钉死在这个
                // 宽度上，不是 `.frame(maxWidth: .infinity)`——后者只是「愿意占用
                // 到这么宽」，如果内部判定图算出来的宽度有误差比这个值更宽，
                // maxWidth 不会拦，卡片会跟着变宽，进而把整个详情页撑宽（这正是
                // 之前那版「修复」翻车的地方）。硬宽度 + 下面的 `.clipShape` 才能
                // 保证卡片对外汇报的宽度永远等于页面真实宽度，判定图内部哪怕算错，
                // 最多是卡片内部被裁掉一角，绝不会向外溢出。
                PivotPhaseDiagram(phase: phase, availableWidth: max(contentWidth - horizontalPadding * 2, 0))
                    .padding(horizontalPadding)
                    .frame(width: contentWidth, alignment: .leading)
            } else {
                // 极端情况：还没测到页面宽度（例如离屏渲染分享长图时跳过了
                // ResultDetailView 的测量链路）。退回原来的弹性宽度，判定图自己
                // 也会退回 designWidth 兜底，不会崩，只是没法保证不溢出。
                PivotPhaseDiagram(phase: phase, availableWidth: nil)
                    .padding(horizontalPadding)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}
