import SwiftUI

/// 查询条。分析完成后折叠成一行摘要，把首屏空间让给图表。
///
/// 改造前这个表单固定占首屏约三分之一，分析完之后仍然杵在那儿——而那时用户
/// 想看的是图，不是刚填完的参数。
struct QueryBar: View {
    @ObservedObject var vm: ChanViewModel
    @Binding var isExpanded: Bool
    let onSubmit: () async -> Void

    /// 代码输入框的焦点。点「分析」或回车前先收起键盘——港股/A 股用的是
    /// numberPad，没有回车键，不主动 resign 的话键盘会一直杵着挡住结果和「重试」。
    @FocusState private var symbolFocused: Bool

    /// 收起键盘并触发分析。
    private func submit() {
        symbolFocused = false
        Task { await onSubmit() }
    }

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
                Text(vm.market.title)
                    .font(.caption)
                    .foregroundColor(Theme.textSecondary)
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
                Spacer(minLength: 6)
                // 只放一个灰色小图标时没人知道这条能点开，改成带文字的实体按钮
                HStack(spacing: 3) {
                    Image(systemName: "slider.horizontal.3").font(.system(size: 11))
                    Text("修改").font(.caption)
                }
                .foregroundColor(Theme.accent)
                .padding(.horizontal, 9).padding(.vertical, 5)
                .background(Theme.accent.opacity(0.14))
                .clipShape(Capsule())
            }
            .padding(.horizontal, 14).padding(.vertical, 10)
            .background(Theme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Theme.accent.opacity(0.25), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }

    /// 代码格式不对就不让点。按所选市场校验，规则与后端 market.py 一致。
    private var canSubmit: Bool {
        !vm.isLoading && vm.market.isValidSymbol(vm.symbol)
    }

    private var freqLabel: String { vm.freq == "weekly" ? "周线" : "日线" }

    /// 市场下拉框。切换市场时清空代码——A 股代码留在港股框里没有意义，
    /// 而且会让人以为能直接分析。
    private var marketPicker: some View {
        Menu {
            Picker("", selection: $vm.market) {
                ForEach(StockMarket.allCases, id: \.self) { m in
                    Text(m.title).tag(m)
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text(vm.market.title)
                    .font(.subheadline.weight(.medium))
                Image(systemName: "chevron.down")
                    .font(.system(size: 10, weight: .semibold))
            }
            .foregroundColor(Theme.accent)
            .padding(.horizontal, 12).padding(.vertical, 12)
            .background(Theme.accent.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 10))
        }
        .onChange(of: vm.market) { _, _ in vm.symbol = "" }
    }

    private func dateField(_ title: String, selection: Binding<Date>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2)
                .foregroundColor(Theme.textSecondary)
            DatePicker("", selection: selection, displayedComponents: .date)
                .labelsHidden()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

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
            HStack(spacing: 8) {
                marketPicker

                HStack {
                    Image(systemName: "magnifyingglass").foregroundColor(Theme.textSecondary)
                    TextField(vm.market.placeholder, text: $vm.symbol)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .keyboardType(vm.market == .us ? .asciiCapable : .numberPad)
                        .foregroundColor(Theme.textPrimary)
                        .focused($symbolFocused)
                        .submitLabel(.search)
                        .onSubmit { submit() }
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
            }

            Picker("", selection: $vm.freq) {
                Text("日线").tag("daily")
                Text("周线").tag("weekly")
            }
            .pickerStyle(.segmented)

            VStack(spacing: 8) {
                // DatePicker 自带的 label 在两列并排时宽度不够会被截断，
                // 改成 labelsHidden + 外置文字标签。
                HStack(spacing: 10) {
                    dateField("起始", selection: $vm.startDate)
                    dateField("截止", selection: $vm.endDate)
                }

                Button {
                    submit()
                } label: {
                    HStack(spacing: 6) {
                        if vm.isLoading { ProgressView().controlSize(.small).tint(.white) }
                        Text(vm.isLoading ? "分析中" : "分析").fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background(canSubmit ? Theme.accent : Theme.surfaceAlt)
                    .foregroundColor(canSubmit ? .white : Theme.textSecondary)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .disabled(!canSubmit)
            }
        }
        .padding(14)
        .background(Theme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }
}
