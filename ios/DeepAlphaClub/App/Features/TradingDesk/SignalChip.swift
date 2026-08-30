import SwiftUI
import DeepAlphaCore

/// 信号 pill：圆点 + 「看多 · 78」；extracted 追加「抽」标注（信号来自文本抽取，
/// 非 agent 原生输出，不标会误导置信度语义）。
struct SignalChip: View {
    let dir: Polarity
    let conf: Int
    var extracted = false

    var body: some View {
        HStack(spacing: 4) {
            Circle().fill(dir.tint).frame(width: 6, height: 6)
            Text("\(dir.label) · \(conf)")
            if extracted {
                Text("抽").opacity(0.6)
            }
        }
        .font(.system(size: 11, weight: .semibold, design: .monospaced))
        .foregroundStyle(dir.tint)
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(dir.tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 6))
        // 窄列下 chip 不撑破父级（对齐 web 的同款修复）
        .fixedSize(horizontal: false, vertical: true)
    }
}

/// 面板小标题（对齐 web 的 mono uppercase 风格）。
func panelHeader(_ text: String) -> some View {
    Text(text)
        .font(.caption2.monospaced().weight(.bold))
        .tracking(1.2)
        .foregroundStyle(Theme.textTertiary)
}
