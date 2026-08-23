import SwiftUI

/// 查询条件表单：市场 + 代码 + 周期 + 日期 + 分析按钮。
///
/// 拆成「条件页 / 详情页」两页后，这里只负责录入条件；原先为了和图表共处一屏
/// 而做的折叠/展开逻辑已不需要，删掉后表单始终完整展示。
struct QueryBar: View {
    @ObservedObject var vm: ChanViewModel
    let onSubmit: () async -> Void

    /// 代码输入框的焦点。点「分析」或回车前先收起键盘——港股/A 股用的是
    /// numberPad，没有回车键，不主动 resign 的话键盘会一直杵着挡住内容。
    @FocusState private var symbolFocused: Bool

    /// 收起键盘并触发分析。
    private func submit() {
        symbolFocused = false
        Task { await onSubmit() }
    }

    /// 代码格式不对就不让点。按所选市场校验，规则与后端 market.py 一致。
    private var canSubmit: Bool {
        !vm.isLoading && vm.market.isValidSymbol(vm.symbol)
    }

    var body: some View {
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
                }
                .padding(10).background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }

            Picker("", selection: $vm.freq) {
                Text(L("日线")).tag("daily")
                Text(L("周线")).tag("weekly")
            }
            .pickerStyle(.segmented)

            VStack(spacing: 8) {
                // DatePicker 自带的 label 在两列并排时宽度不够会被截断，
                // 改成 labelsHidden + 外置文字标签。
                HStack(spacing: 10) {
                    dateField(L("起始"), selection: $vm.startDate)
                    dateField(L("截止"), selection: $vm.endDate)
                }

                Button {
                    submit()
                } label: {
                    HStack(spacing: 6) {
                        if vm.isLoading { ProgressView().controlSize(.small).tint(.white) }
                        Text(vm.isLoading ? L("分析中") : L("分析")).fontWeight(.semibold)
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
}
