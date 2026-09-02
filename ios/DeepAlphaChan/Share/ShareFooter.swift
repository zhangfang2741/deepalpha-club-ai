import SwiftUI

/// 分享图底部的品牌脚：图标 + 名称 + slogan + 下载二维码。
///
/// 放在截图下方而非上方（用户明确要求）：内容是主体、品牌是署名；长图场景下
/// 品牌在顶部会随滚动消失，在底部则始终收尾。高度固定为 `ShareLayout.footerHeight`，
/// 宽度由外部按截图宽度给定 —— 全屏图表页是横屏，截出来是横图，写死宽度会错位。
struct ShareFooter: View {
    let width: CGFloat

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            // 用 SF Symbol 而不是 App 图标：Assets 里只有 AppIcon.appiconset，
            // 那是 App 图标专用的，不能当普通 Image 引用。
            Image(systemName: "chart.xyaxis.line")
                .font(.system(size: 22, weight: .semibold))
                .foregroundColor(Theme.accent)
                .frame(width: 40, height: 40)
                .background(Theme.accent.opacity(0.14))
                .clipShape(RoundedRectangle(cornerRadius: 9))

            VStack(alignment: .leading, spacing: 3) {
                // 锁一行并允许适度缩字：本视图声明「宽度由外部给定」，就得能扛住窄宽度。
                // 换行会撑破下方固定的 footerHeight，离屏渲染时半行字被裁掉，
                // 而几何层的测试只覆盖 CoreGraphics 矩形，结构性地拦不住这类问题。
                Text("DeepAlpha \(L("缠论"))")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundColor(Theme.textPrimary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                // 只陈述功能。分享图会脱离 App 语境传播，不能出现「先机」「收益」
                // 这类暗示性措辞。
                Text(L("缠论结构 自动标注"))
                    .font(.system(size: 12))
                    .foregroundColor(Theme.textSecondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }

            Spacer(minLength: 0)

            qrCode
        }
        .padding(.horizontal, 16)
        .frame(width: width, height: ShareLayout.footerHeight)
        .background(Theme.surface)
    }

    @ViewBuilder
    private var qrCode: some View {
        if let qr = QRCode.image(for: AppConfig.downloadPageURL, side: 64) {
            Image(uiImage: qr)
                .resizable()
                .frame(width: 64, height: 64)
                // 白色内边距是二维码的「静默区」，紧贴深色底会明显掉识别率
                .padding(3)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 4))
        }
    }
}

/// 品牌脚之下的免责条，紧贴收边。
///
/// 这行字不可省。分享图会脱离 App 语境传播，被当成荐股截图转发时，它是唯一还跟着图走的
/// 风险说明。用户截屏时未必滚动到了结果页底部那行 compactDisclaimer，所以由品牌层无条件补上。
struct ShareDisclaimer: View {
    let width: CGFloat

    var body: some View {
        // 同样锁一行。这行是合规文案，宁可缩字也不能换行后被固定高度裁掉半句 ——
        // 截成「…仅供技术研」会让风险提示失去意义。
        Text(L("算法自动生成，仅供技术研究，不构成投资建议。"))
            .font(.system(size: 10))
            .foregroundColor(Theme.textSecondary)
            .lineLimit(1)
            .minimumScaleFactor(0.8)
            .frame(width: width, height: ShareLayout.disclaimerHeight)
            .background(Theme.surface)
    }
}

#if DEBUG
#Preview("截图卡片与品牌脚") {
    VStack(spacing: 0) {
        Rectangle().fill(Theme.background)
            .frame(width: 390 + ShareLayout.outerPadding * 2,
                   height: 200 + ShareLayout.outerPadding)
            .overlay(
                RoundedRectangle(cornerRadius: ShareLayout.screenshotCornerRadius)
                    .fill(Theme.surface)
                    .frame(width: 390, height: 200)
                    .overlay(Text("（此处为用户界面截图）").foregroundColor(Theme.textSecondary)),
                alignment: .bottom
            )
            .padding(.horizontal, -ShareLayout.outerPadding)
        ShareFooter(width: 390 + ShareLayout.outerPadding * 2)
            .padding(.top, ShareLayout.gap)
        ShareDisclaimer(width: 390 + ShareLayout.outerPadding * 2)
    }
    .preferredColorScheme(.dark)
}
#endif
