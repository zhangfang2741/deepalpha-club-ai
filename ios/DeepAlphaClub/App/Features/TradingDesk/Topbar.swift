import SwiftUI
import DeepAlphaCore

/// 顶栏：标题/状态 + 市场 segment + ticker 输入 + 动作按钮。
///
/// 分析进行中会收起输入区：那时市场选择和 ticker 输入都是禁用的，
/// 却在窄屏上白占近三分之一高度——而这段时间恰恰是最需要看内容的时候。
struct Topbar: View {
    @Binding var ticker: String
    @Binding var market: Market
    let state: TradingDeskState
    let connection: ConnectionState
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
            titleRow
            if live {
                controls           // 分析中：只留控制按钮
            } else {
                inputSection       // 空闲/结束：完整输入区
            }
        }
        .animation(.easeInOut(duration: 0.2), value: live)
        .sheet(isPresented: $showInject) {
            InjectSheet { text in
                onControl(.inject, text)
            }
        }
    }

    /// 标题行。分析中把标的提到这里，收起输入框也仍看得到在分析什么。
    private var titleRow: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text("交易台").font(.headline)
                    if live && !state.ticker.isEmpty {
                        Text(state.ticker)
                            .font(.subheadline.monospaced().weight(.bold))
                            .foregroundStyle(Theme.accent)
                    }
                }
                Text(live ? "\(state.stages.count) 位分析师参与" : "多智能体分析")
                    .font(.caption2.monospaced())
                    .foregroundStyle(Theme.textTertiary)
            }
            Spacer()
            StatusDot(status: state.status, connection: connection)
        }
    }

    private var inputSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker("市场", selection: $market) {
                ForEach(Market.allCases) { m in
                    Text(m.label).tag(m)
                }
            }
            .pickerStyle(.segmented)

            HStack(spacing: 8) {
                HStack(spacing: 2) {
                    Text("$").font(.caption.monospaced()).foregroundStyle(Theme.textTertiary)
                    TextField(market.placeholder, text: $ticker)
                        .font(.subheadline.monospaced().weight(.semibold))
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .submitLabel(.go)
                        .onSubmit { if canStart { onStart() } }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 8))

                Button(state.status == .idle ? "开始分析" : "重新分析", action: onStart)
                    .buttonStyle(.borderedProminent)
                    .disabled(!canStart)
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
                .disabled(busy)
            }
            if state.capabilities.supportsInject {
                Button {
                    showInject = true
                } label: {
                    Label("注入意见", systemImage: "plus.bubble")
                }
                .buttonStyle(.bordered)
                .disabled(busy)
            }
            Button(role: .destructive) {
                onControl(.cancel, nil)
            } label: {
                Label("停止", systemImage: "stop.fill")
            }
            .buttonStyle(.bordered)
            .tint(Theme.danger)     // 全局 tint 会盖掉 role: .destructive 的红
            .disabled(busy)
            Spacer(minLength: 0)
        }
        .font(.footnote)
    }
}

/// 状态点 + 中文文案。断线重连优先于运行状态显示——
/// 流停住时用户最需要知道的是「网断了在重连」还是「agent 在想」。
struct StatusDot: View {
    let status: RunStatus
    var connection: ConnectionState = .idle

    var body: some View {
        HStack(spacing: 5) {
            if connection.isReconnecting {
                ProgressView().controlSize(.mini)
                Text(reconnectText)
                    .font(.caption2.monospaced())
                    .foregroundStyle(Theme.warning)
            } else {
                Circle()
                    .fill(status.tint)
                    .frame(width: 6, height: 6)
                Text(status.label)
                    .font(.caption2.monospaced())
                    .foregroundStyle(Theme.textSecondary)
            }
        }
    }

    private var reconnectText: String {
        if case .reconnecting(let attempt) = connection, attempt > 1 {
            return "重连中 \(attempt)"
        }
        return "重连中"
    }
}
