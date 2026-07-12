import SwiftUI

/// 统一的卡片容器：标题 + 内容。
struct SectionCard<Content: View>: View {
    let title: String
    var systemImage: String? = nil
    @ViewBuilder let content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                if let systemImage { Image(systemName: systemImage).foregroundColor(Theme.accent) }
                Text(title).font(.headline).foregroundColor(Theme.textPrimary)
            }
            content()
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}

/// 免责声明横幅（金融类 App 过审必备）。
struct DisclaimerBanner: View {
    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(Theme.segment)
                .font(.caption)
            Text("以下缠论结构、买卖点及建议均由算法自动生成，仅供技术研究参考，不构成投资建议。投资有风险，决策需自主判断。")
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)
        }
        .padding(10)
        .background(Theme.segment.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

/// 小标签 chip。
struct Chip: View {
    let text: String
    var color: Color = Theme.accent
    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .medium))
            .padding(.horizontal, 8).padding(.vertical, 3)
            .background(color.opacity(0.15))
            .foregroundColor(color)
            .clipShape(Capsule())
    }
}
