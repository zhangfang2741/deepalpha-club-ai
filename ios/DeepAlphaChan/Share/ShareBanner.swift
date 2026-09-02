import SwiftUI

/// 分享图顶部的品牌头：图标 + 名称 + slogan + 下载二维码。
///
/// 高度固定为 `ShareLayout.bannerHeight`，宽度由外部按截图宽度给定 ——
/// 全屏图表页是横屏，截出来是横图，写死宽度会错位。
struct ShareBanner: View {
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
                Text("DeepAlpha \(L("缠论"))")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundColor(Theme.textPrimary)
                // 只陈述功能。分享图会脱离 App 语境传播，不能出现「先机」「收益」
                // 这类暗示性措辞。
                Text(L("缠论结构 自动标注"))
                    .font(.system(size: 12))
                    .foregroundColor(Theme.textSecondary)
            }

            Spacer(minLength: 0)

            qrCode
        }
        .padding(.horizontal, 16)
        .frame(width: width, height: ShareLayout.bannerHeight)
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

/// 分享图底部的免责条。
///
/// 这行字不可省。分享图会脱离 App 语境传播，被当成荐股截图转发时，它是唯一还跟着图走的
/// 风险说明。用户截屏时未必滚动到了结果页底部那行 compactDisclaimer，所以由品牌层无条件补上。
struct ShareDisclaimer: View {
    let width: CGFloat

    var body: some View {
        Text(L("算法自动生成，仅供技术研究，不构成投资建议。"))
            .font(.system(size: 10))
            .foregroundColor(Theme.textSecondary)
            .frame(width: width, height: ShareLayout.disclaimerHeight)
            .background(Theme.surface)
    }
}

#if DEBUG
#Preview("品牌头与免责条") {
    VStack(spacing: 0) {
        ShareBanner(width: 390)
        Rectangle().fill(Theme.background).frame(width: 390, height: 200)
            .overlay(Text("（此处为用户界面截图）").foregroundColor(Theme.textSecondary))
        ShareDisclaimer(width: 390)
    }
    .preferredColorScheme(.dark)
}
#endif
