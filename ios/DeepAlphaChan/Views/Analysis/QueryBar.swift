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

    /// 名称联想结果。输入的不是合法代码（比如打了「曙光」）时，边输边搜，点一条就填入代码。
    @State private var suggestions: [SymbolHit] = []
    @State private var searchTask: Task<Void, Never>?
    /// 点选联想把代码填进输入框会再触发一次 onChange；这个标记让那一次不要再搜、不要把列表又弹出来。
    @State private var skipNextSearch = false
    /// 输入行（市场 + 输入框）的实际高度，浮层按它往下偏移。用 offset 而不是 alignmentGuide：
    /// 上一版用 alignmentGuide 把浮层顶边对到输入行底边，实测没生效，列表反而底边对着输入行向上长，
    /// 盖住了输入框和状态栏。offset 只改显示位置、不参与布局，下面的内容纹丝不动。
    @State private var rowHeight: CGFloat = 44

    /// 收起键盘并触发分析。输入的是名称、还没点联想就回车 / 点分析时，取第一条联想。
    private func submit() {
        if !vm.market.isValidSymbol(vm.symbol), let first = suggestions.first {
            pick(first)
            return
        }
        symbolFocused = false
        suggestions = []
        Task { await onSubmit() }
    }

    /// 选中一条联想：填入代码并直接分析。
    private func pick(_ hit: SymbolHit) {
        searchTask?.cancel()
        // 填的值和输入框里已有的一样就不会触发 onChange，此时不能留着标记，否则会吞掉下一次真实输入
        skipNextSearch = vm.symbol != hit.symbol
        vm.symbol = hit.symbol
        // 联想自带名称：必须在改完代码之后设（代码一变会清掉旧名称）
        vm.displayName = hit.name.isEmpty ? nil : hit.name
        suggestions = []
        submit()
    }

    /// 输入变化后 0.25 秒再搜（防抖）。A 股 / 港股已经是合法代码就不搜（代码是定长的，输完就是了）；
    /// 美股代码长度不定，打到一半（如 APP）也可能想搜，所以美股一直搜。
    private func scheduleSearch(_ text: String) {
        searchTask?.cancel()
        if skipNextSearch { skipNextSearch = false; return }
        let query = text.trimmingCharacters(in: .whitespaces)
        let market = vm.market
        guard !query.isEmpty, market == .us || !market.isValidSymbol(query) else {
            suggestions = []
            return
        }
        searchTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard !Task.isCancelled else { return }
            let hits = (try? await ChanService.searchSymbols(query: query, market: market)) ?? []
            guard !Task.isCancelled, vm.market == market else { return }
            suggestions = hits
        }
    }

    /// 代码格式不对就不让点。按所选市场校验，规则与后端 market.py 一致。
    private var canSubmit: Bool {
        !vm.isLoading && (vm.market.isValidSymbol(vm.symbol) || !suggestions.isEmpty)
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
                        // 要能打中文名：A 股 / 港股也用默认键盘（原来是数字键盘，打不出汉字）
                        .keyboardType(.default)
                        .onChange(of: vm.symbol) { _, new in scheduleSearch(new) }
                        .foregroundColor(Theme.textPrimary)
                        .focused($symbolFocused)
                        .submitLabel(.search)
                        .onSubmit { submit() }
                }
                .padding(10).background(Theme.surfaceAlt)
                .clipShape(RoundedRectangle(cornerRadius: 10))
            }
            .background(GeometryReader { geo in
                Color.clear
                    .onAppear { rowHeight = geo.size.height }
                    .onChange(of: geo.size.height) { _, h in rowHeight = h }
            })
            // 联想是悬浮在输入行下方的浮层：顶边在输入行底边下 6pt，向下展开，不参与布局。
            .overlay(alignment: .topLeading) {
                if symbolFocused && !suggestions.isEmpty {
                    suggestionList
                        .offset(y: rowHeight + 6)
                }
            }
            .zIndex(2)

            Picker("", selection: $vm.freq) {
                Text(L("日线")).tag("daily")
                Text(L("周线")).tag("weekly")
                Text(L("30分钟")).tag("30min")
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
        // 不能再 clipShape：浮层要伸出卡片盖住下面的内容，裁掉就看不见了。背景自带圆角即可。
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 14))
    }

    /// 市场选择的绑定。清空代码这件事绑在**这个控件的交互**上，而不是绑在
    /// `vm.market` 的数据变化上。
    ///
    /// 原来写的是 `.onChange(of: vm.market) { vm.symbol = "" }`，它分不清
    /// 「用户手动切市场」和「程序恢复一条历史」，而且是在视图更新周期里才触发：
    /// 点历史里的 AAPL 时，先设 market 再设 symbol 都完成了，随后 onChange
    /// 才把 symbol 清成空串，runAnalysis 于是拿着空代码去请求，直接报错。
    private var marketBinding: Binding<StockMarket> {
        Binding(
            get: { vm.market },
            set: { newValue in
                guard newValue != vm.market else { return }
                vm.market = newValue
                // A 股代码留在港股框里没有意义，还会让人以为能直接分析
                vm.symbol = ""
                suggestions = []
            }
        )
    }

    /// 市场下拉框。
    private var marketPicker: some View {
        Menu {
            Picker("", selection: marketBinding) {
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
    }

    /// 联想列表：名称 + 代码，整行都是点击区域（≥ 44pt）。
    private var suggestionList: some View {
        VStack(spacing: 0) {
            ForEach(suggestions.prefix(5)) { hit in
                Button { pick(hit) } label: {
                    HStack {
                        // 单行 + 末尾截断：美股的英文全名很长（ETF 名字能到两行），不截断会把一行撑得很高
                        // 字号比输入框（默认 17pt）小一档：联想是辅助，不该比输入框还抢眼
                        Text(hit.name).font(.system(size: 14)).foregroundColor(Theme.textPrimary).lineLimit(1).truncationMode(.tail)
                        Spacer(minLength: 8)
                        Text(hit.symbol).font(.system(size: 12).monospacedDigit()).foregroundColor(Theme.textSecondary)
                            .lineLimit(1).fixedSize()
                    }
                    .padding(.horizontal, 10)
                    .frame(minHeight: 38)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                if hit.id != suggestions.prefix(5).last?.id { Divider().background(Theme.border) }
            }
        }
        .background(Theme.surfaceAlt)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
        .shadow(color: .black.opacity(0.45), radius: 14, x: 0, y: 8)
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
