import SwiftUI
import DeepAlphaCore

/// 中栏：实时推理流。贴底跟随规则（对齐 web StreamPanel）：
/// - 默认贴底，新 token / 新卡片自动跟随
/// - 用户上滑查看历史时停止跟随，滑回底部恢复
/// - 新 run 开始强制贴底
///
/// 实现用 iOS 17 的 `scrollPosition(id:)`：底部放一个哨兵 view，
/// 「当前滚动位置 == 哨兵」即视为贴底。比 GeometryReader 读全局坐标可靠，
/// 也不需要已弃用的 UIScreen.main。
struct StreamPanel: View {
    let turns: [Turn]
    let status: RunStatus
    let streamingTurnId: String?
    let runId: String?

    private static let bottomID = "stream-bottom"
    @State private var scrolledID: String?
    @State private var stickToBottom = true

    /// 流式追加时 turns.count 不变、最后一张卡的文本在变长，单独盯住它。
    private var lastTextLength: Int { turns.last?.text.count ?? 0 }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            panelHeader("实时推理")
            if turns.isEmpty {
                emptyState
            } else {
                stream
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(Color(.secondarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 14))
    }

    private var stream: some View {
        scrollBody
            .defaultScrollAnchor(.bottom)
            .scrollPosition(id: $scrolledID, anchor: .bottom)
            .onChange(of: scrolledID) { _, new in
                // 滚动落点在哨兵上才继续跟随（nil = 尚未产生位置信息）
                stickToBottom = (new == nil || new == Self.bottomID)
            }
            .onChange(of: turns.count) { followIfSticking() }
            .onChange(of: lastTextLength) { followIfSticking() }
            .onChange(of: runId) {
                stickToBottom = true          // 新 run 强制贴底
                scrollToBottom()
            }
    }

    private var scrollBody: some View {
        ScrollView {
            LazyVStack(spacing: 10) {
                ForEach(turns) { turn in
                    TurnCard(turn: turn, streaming: turn.turnId == streamingTurnId)
                        .id(turn.turnId)
                }
                // 底部哨兵：既是贴底判据，也是滚动目标
                Color.clear
                    .frame(height: 1)
                    .id(Self.bottomID)
            }
            .scrollTargetLayout()
            .padding(.vertical, 4)
        }
    }

    private func followIfSticking() {
        guard stickToBottom else { return }
        scrollToBottom()
    }

    private func scrollToBottom() {
        withAnimation(.easeOut(duration: 0.2)) {
            scrolledID = Self.bottomID
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Text("交易台还很安静。")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(.secondary)
            Text("输入标的、点「开始分析」。\n看每个 agent 实时推理、辩论、给出结论。")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
