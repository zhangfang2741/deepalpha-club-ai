import SwiftUI
import DeepAlphaCore

/// 历史列表：ticker 过滤 + 状态/裁决徽标，点击进回放。
struct HistoryListView: View {
    @Environment(HistoryListViewModel.self) private var vm
    @State private var tickerFilter = ""

    /// 空字符串当「无过滤」传给后端，避免 ticker= 空串查不到东西。
    private var filter: String? {
        let t = tickerFilter.trimmingCharacters(in: .whitespaces)
        return t.isEmpty ? nil : t
    }

    var body: some View {
        NavigationStack {
            List {
                if let err = vm.error {
                    ErrorBanner(message: err) { vm.error = nil }
                        .listRowSeparator(.hidden)
                }
                if vm.loading && vm.runs.isEmpty {
                    HStack(spacing: 8) {
                        ProgressView()
                        Text("正在拉取").foregroundStyle(.secondary)
                    }
                }
                if vm.runs.isEmpty && !vm.loading {
                    Text("暂无历史运行 —— 到交易台跑一次吧。")
                        .foregroundStyle(.tertiary)
                }
                ForEach(vm.runs) { run in
                    NavigationLink(value: run.runId) {
                        RunRow(run: run)
                    }
                }
            }
            .navigationTitle("历史运行")
            .navigationDestination(for: String.self) { runId in
                RunReplayView(runId: runId)
            }
            .searchable(text: $tickerFilter, prompt: "按标的过滤（如 NVDA）")
            .onSubmit(of: .search) {
                Task { await vm.refresh(ticker: filter) }
            }
            .refreshable {
                await vm.refresh(ticker: filter)
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await vm.refresh(ticker: filter) }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(vm.loading)
                }
            }
            .task {
                await vm.refresh(ticker: nil)
            }
        }
    }
}

/// 一行历史：ticker + 裁决徽标 + 状态 + 时长/计数 + 时间。
struct RunRow: View {
    let run: RunSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(run.ticker)
                    .font(.headline.monospaced())
                if let signal = run.verdictSignal {
                    VerdictBadge(signal: signal, confidence: run.verdictConfidence)
                } else {
                    Text("未出裁决").font(.caption2).foregroundStyle(.tertiary)
                }
                StatusBadge(status: run.status)
                Spacer(minLength: 4)
                VStack(alignment: .trailing, spacing: 2) {
                    Text(Self.timestamp(run.finishedAt ?? run.createdAt))
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Text(run.tradeDate)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.tertiary)
                }
            }
            HStack(spacing: 12) {
                Label(run.status == .running ? "—" : Self.duration(run.durationMs),
                      systemImage: "clock")
                Text("\(run.signalsCount) 信号")
                Text("\(run.turnsCount) 卡片")
                Text(run.engine).font(.caption2.monospaced())
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }

    static func duration(_ ms: Int) -> String {
        if ms < 1000 { return "\(ms)ms" }
        if ms < 60_000 { return String(format: "%.1fs", Double(ms) / 1000) }
        let m = ms / 60_000, s = (ms % 60_000) / 1000
        return "\(m)m\(s)s"
    }

    /// 后端 created_at 可能带/不带小数秒，两种 formatter 都试一次。
    static func timestamp(_ iso: String) -> String {
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let d = withFraction.date(from: iso) ?? ISO8601DateFormatter().date(from: iso)
        else { return iso }
        return d.formatted(date: .abbreviated, time: .shortened)
    }
}

struct VerdictBadge: View {
    let signal: VerdictSignal
    let confidence: Double?

    var body: some View {
        HStack(spacing: 4) {
            Text(signal.label)
            if let c = confidence {
                Text("\(Int((c * 100).rounded()))%")
                    .monospacedDigit()
                    .opacity(0.7)
            }
        }
        .font(.caption.weight(.medium))
        .foregroundStyle(signal.tint)
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
        .background(signal.tint.opacity(0.1), in: RoundedRectangle(cornerRadius: 5))
    }
}

struct StatusBadge: View {
    let status: RunRecordStatus

    private var style: (text: String, color: Color) {
        switch status {
        case .running: ("运行中", .blue)
        case .completed: ("已完成", .green)
        case .cancelled: ("已取消", .gray)
        case .failed: ("失败", .red)
        case .interrupted: ("中断", .orange)
        }
    }

    var body: some View {
        Text(style.text)
            .font(.caption2)
            .foregroundStyle(style.color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(style.color.opacity(0.1), in: RoundedRectangle(cornerRadius: 5))
    }
}
