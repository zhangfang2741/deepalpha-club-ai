import SwiftUI
import DeepAlphaCore

/// 顶栏：标题/状态 + 市场 segment + ticker 输入 + 动作按钮。
struct Topbar: View {
    @Binding var ticker: String
    @Binding var market: Market
    let state: TradingDeskState
    let busy: Bool
    let onStart: () -> Void
    let onControl: (ControlAction, String?) -> Void
    @State private var showInject = false

    private var live: Bool { state.status == .running || state.status == .paused }
    private var canStart: Bool {
        !live && !busy && !ticker.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("交易台").font(.headline)
                    Text("多智能体分析")
                        .font(.caption2.monospaced())
                        .foregroundStyle(.tertiary)
                }
                Spacer()
                StatusDot(status: state.status)
            }

            Picker("市场", selection: $market) {
                ForEach(Market.allCases) { m in
                    Text(m.label).tag(m)
                }
            }
            .pickerStyle(.segmented)
            .disabled(live)

            HStack(spacing: 8) {
                HStack(spacing: 2) {
                    Text("$").font(.caption.monospaced()).foregroundStyle(.tertiary)
                    TextField(market.placeholder, text: $ticker)
                        .font(.subheadline.monospaced().weight(.semibold))
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .submitLabel(.go)
                        .onSubmit { if canStart { onStart() } }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Color(.secondarySystemBackground),
                            in: RoundedRectangle(cornerRadius: 8))
                .disabled(live)

                Button(live ? "分析中" : (state.status == .idle ? "开始分析" : "重新分析"),
                       action: onStart)
                    .buttonStyle(.borderedProminent)
                    .disabled(!canStart)
            }

            controls
        }
        .sheet(isPresented: $showInject) {
            InjectSheet { text in
                onControl(.inject, text)
            }
        }
    }

    @ViewBuilder
    private var controls: some View {
        HStack(spacing: 8) {
            if state.capabilities.supportsPause {
                Button {
                    onControl(state.status == .paused ? .resume : .pause, nil)
                } label: {
                    Label(state.status == .paused ? "继续" : "暂停",
                          systemImage: state.status == .paused ? "play.fill" : "pause.fill")
                }
                .buttonStyle(.bordered)
                .disabled(!live || busy)
            }
            if state.capabilities.supportsInject {
                Button {
                    showInject = true
                } label: {
                    Label("注入意见", systemImage: "plus.bubble")
                }
                .buttonStyle(.bordered)
                .disabled(!live || busy)
            }
            if live {
                Button(role: .destructive) {
                    onControl(.cancel, nil)
                } label: {
                    Label("停止", systemImage: "stop.fill")
                }
                .buttonStyle(.bordered)
                .disabled(busy)
            }
            Spacer(minLength: 0)
        }
        .font(.footnote)
    }
}

/// 状态点 + 中文文案（对齐 web STATUS_TEXT）。静态圆点：
/// `.symbolEffect(.pulse)` 只作用于 SF Symbol，Circle 用不了。
struct StatusDot: View {
    let status: RunStatus

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(status.tint)
                .frame(width: 6, height: 6)
            Text(status.label)
                .font(.caption2.monospaced())
                .foregroundStyle(.secondary)
        }
    }
}
