import SwiftUI

/// 查询条。分析完成后折叠成一行摘要，把首屏空间让给图表。
///
/// 改造前这个表单固定占首屏约三分之一，分析完之后仍然杵在那儿——而那时用户
/// 想看的是图，不是刚填完的参数。
struct QueryBar: View {
    @ObservedObject var vm: ChanViewModel
    @Binding var isExpanded: Bool
    let onSubmit: () async -> Void

    var body: some View {
        if isExpanded {
            expandedForm
        } else {
            collapsedSummary
        }
    }

    // MARK: - 折叠态

    private var collapsedSummary: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.2)) { isExpanded = true }
        } label: {
            HStack(spacing: 8) {
                Text(vm.symbol.uppercased())
                    .font(.subheadline.bold())
                    .foregroundColor(Theme.textPrimary)
                Text(freqLabel)
                    .font(.caption)
                    .foregroundColor(Theme.accent)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Theme.accent.opacity(0.14))
                    .clipShape(Capsule())
                Text(dateRangeLabel)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
                Spacer()
                Image(systemName: "slider.horizontal.3")
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
            }
            .padding(.horizontal, 14).padding(.vertical, 11)
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
    }

    private var freqLabel: String { vm.freq == "weekly" ? "周线" : "日线" }

    /// 带两位年份。默认区间是整一年，只显示 MM-dd 的话两头都是同一天，
    /// 看起来像坏了。
    private var dateRangeLabel: String {
        let f = DateFormatter()
        f.dateFormat = "yy-MM-dd"
        return "\(f.string(from: vm.startDate)) ~ \(f.string(from: vm.endDate))"
    }

    // MARK: - 展开态

    private var expandedForm: some View {
        VStack(spacing: 10) {
            HStack {
                Image(systemName: "magnifyingglass").foregroundColor(Theme.textSecondary)
                TextField("股票代码，如 AAPL", text: $vm.symbol)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .foregroundColor(Theme.textPrimary)
                    .onSubmit { Task { await onSubmit() } }
                // 已有结果时给个收起入口，避免用户点开改参数后无路可退
                if vm.analysis != nil {
                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) { isExpanded = false }
                    } label: {
                        Image(systemName: "chevron.up")
                            .font(.caption).foregroundColor(Theme.textSecondary)
                    }
                }
            }
            .padding(10).background(Theme.surfaceAlt)
            .clipShape(RoundedRectangle(cornerRadius: 10))

            Picker("", selection: $vm.freq) {
                Text("日线").tag("daily")
                Text("周线").tag("weekly")
            }
            .pickerStyle(.segmented)

            VStack(spacing: 8) {
                HStack(spacing: 8) {
                    DatePicker("起", selection: $vm.startDate, displayedComponents: .date)
                    DatePicker("止", selection: $vm.endDate, displayedComponents: .date)
                }
                .font(.caption)

                Button {
                    Task { await onSubmit() }
                } label: {
                    HStack(spacing: 6) {
                        if vm.isLoading { ProgressView().controlSize(.small).tint(.white) }
                        Text(vm.isLoading ? "分析中" : "分析").fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(vm.isLoading ? Theme.surfaceAlt : Theme.accent)
                    .foregroundColor(vm.isLoading ? Theme.textSecondary : .white)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .disabled(vm.isLoading)
            }
        }
        .padding(14)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}
