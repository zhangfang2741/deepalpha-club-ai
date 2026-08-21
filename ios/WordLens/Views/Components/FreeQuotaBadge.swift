// Views/Components/FreeQuotaBadge.swift
import SwiftUI

/// 免费额度提示胶囊：在用户被拦住**之前**就告诉他今天还剩多少。
///
/// 此前额度只在设置页显示，用户拍第 3 张照片时并不知道那是当天最后一次，
/// 直到第 4 次才被订阅墙挡下——「用着用着被打断」是差评的常见来源。把数字
/// 放在动作发生的地方，一是让人有预期，二是让付费理由变具体（"我确实每天
/// 都不够用"），比突然弹墙更容易转化。
///
/// 订阅用户整个视图消失，不占布局空间。
struct FreeQuotaBadge: View {
    enum Kind {
        case photo
        case word

        var icon: String {
            switch self {
            case .photo: return "camera.fill"
            case .word: return "sparkles"
            }
        }
    }

    /// 文案繁简两档。学习页要和队列进度并排，必须用 `.compact`——
    /// 完整文案（「今日新词 20/20 · 升级 Pro」≈180pt）加上进度胶囊，
    /// 在 iPhone SE 这类 375pt 宽的机器上会挤出屏幕。
    enum Style {
        case full
        case compact
    }

    let kind: Kind
    var style: Style = .full
    /// 点击回调，通常用来弹订阅墙。传 nil 则整个胶囊不可点。
    var onTap: (() -> Void)?

    @EnvironmentObject private var store: StoreManager
    @EnvironmentObject private var usage: UsageTracker

    @ViewBuilder
    var body: some View {
        if !store.isSubscribed {
            Group {
                if let onTap {
                    Button(action: onTap) { badge }
                        .buttonStyle(.plain)
                } else {
                    badge
                }
            }
            // App 跨过午夜仍停在前台时，@Published 的计数不会自己归零——
            // 额度判定本身在 canTakePhoto()/canLearn() 里会 rollover，但那要等
            // 用户先动手。这里主动对一次日期，避免显示昨天的数字。
            .onAppear { usage.refresh() }
        }
    }

    private var badge: some View {
        HStack(spacing: 6) {
            Image(systemName: isExhausted ? "crown.fill" : kind.icon)
                .font(.caption2)
            Text(text)
                .font(.caption.weight(.medium))
                .monospacedDigit()
        }
        .foregroundStyle(tint)
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Theme.surface)
        .clipShape(.capsule)
        .overlay {
            Capsule().strokeBorder(
                isExhausted ? Theme.fuzzy.opacity(0.5) : Theme.border,
                lineWidth: 1
            )
        }
        .contentShape(.capsule)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
        .accessibilityAddTraits(onTap == nil ? [] : .isButton)
    }

    // MARK: - 文案与配色

    private var used: Int {
        switch kind {
        case .photo: return usage.photosUsedToday
        case .word: return usage.wordsLearnedToday
        }
    }

    private var limit: Int {
        switch kind {
        case .photo: return usage.photoLimit
        case .word: return usage.wordLimit
        }
    }

    private var isExhausted: Bool { used >= limit }

    /// 只剩最后一次时也变色——那是最需要提前预警的时刻。
    private var isRunningLow: Bool { limit - used <= 1 }

    private var tint: Color {
        isRunningLow ? Theme.fuzzy : Theme.textSecondary
    }

    private var text: String {
        let counter: String
        switch (kind, style) {
        case (.photo, .full): counter = L("今日拍照 %lld/%lld", used, limit)
        case (.photo, .compact): counter = L("拍照 %lld/%lld", used, limit)
        case (.word, .full): counter = L("今日新词 %lld/%lld", used, limit)
        case (.word, .compact): counter = L("新词 %lld/%lld", used, limit)
        }
        // 用尽后光有数字不够，得给出下一步动作。紧凑模式放不下这句，
        // 靠皇冠图标和整体变色传达同样的意思。
        guard isExhausted, style == .full else { return counter }
        return "\(counter) · \(L("升级 Pro"))"
    }

    private var accessibilityLabel: String {
        switch kind {
        case .photo:
            return isExhausted
                ? L("今日免费拍照额度已用完，共 %lld 次。轻点升级 Pro", limit)
                : L("今日已用拍照 %lld 次，共 %lld 次", used, limit)
        case .word:
            return isExhausted
                ? L("今日免费学习额度已用完，共 %lld 个新词。轻点升级 Pro", limit)
                : L("今日已学 %lld 个新词，共 %lld 个", used, limit)
        }
    }
}
