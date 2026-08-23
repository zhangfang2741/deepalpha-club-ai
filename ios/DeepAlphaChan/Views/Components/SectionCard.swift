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

/// 可折叠卡片：标题行可点开/收起，默认收起。
///
/// 结论页子章节多（形态解读 / 当前结构 / 操作倾向 / 待确认结构），全展开要长距离
/// 滚动。折叠后一屏能看到全部标题，按需展开自己关心的那块。
/// 收起态可在标题右侧带一个摘要 chip（如形态阶段、操作偏向），不展开也能瞄一眼结论。
struct CollapsibleCard<Content: View>: View {
    let title: String
    var systemImage: String? = nil
    var accessoryChip: (text: String, color: Color)? = nil
    var defaultExpanded: Bool = false
    @ViewBuilder let content: () -> Content

    @State private var expanded: Bool

    init(title: String,
         systemImage: String? = nil,
         accessoryChip: (text: String, color: Color)? = nil,
         defaultExpanded: Bool = false,
         @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.systemImage = systemImage
        self.accessoryChip = accessoryChip
        self.defaultExpanded = defaultExpanded
        self.content = content
        _expanded = State(initialValue: defaultExpanded)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
            } label: {
                HStack(spacing: 6) {
                    if let systemImage {
                        Image(systemName: systemImage).foregroundColor(Theme.accent)
                    }
                    Text(title).font(.headline).foregroundColor(Theme.textPrimary)
                    if let chip = accessoryChip {
                        Chip(text: chip.text, color: chip.color)
                    }
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.down")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(Theme.textSecondary)
                        .rotationEffect(.degrees(expanded ? 0 : -90))
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            if expanded { content() }
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
            Text(L("以下缠论结构、买卖点及建议均由算法自动生成，仅供技术研究参考，不构成投资建议。投资有风险，决策需自主判断。"))
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
