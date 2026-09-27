import SwiftUI

/// 设置 → 买卖点模式：宽松（默认）/ 严格 / …（选项来自服务端，新增模式无需发版）。
/// 选完立刻生效：信号雷达与已打开的分析按新模式重算。
struct SignalModeSettingView: View {
    @ObservedObject private var manager = SignalModeManager.shared

    var body: some View {
        List {
            Section {
                ForEach(manager.options) { option in
                    Button {
                        manager.mode = option.key
                    } label: {
                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(spacing: 6) {
                                    Text(option.label)
                                        .font(.body.weight(.semibold))
                                        .foregroundColor(Theme.textPrimary)
                                    if option.isDefault {
                                        Text(L("默认"))
                                            .font(.caption2)
                                            .foregroundColor(Theme.textSecondary)
                                    }
                                }
                                Text(option.description)
                                    .font(.footnote)
                                    .foregroundColor(Theme.textSecondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            Spacer(minLength: 0)
                            if option.key == manager.mode {
                                Image(systemName: "checkmark")
                                    .font(.body.weight(.semibold))
                                    .foregroundColor(Theme.accent)
                            }
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            } footer: {
                Text(L("切换后信号雷达、分析详情与次级别确认都按所选模式重新计算。"))
            }
        }
        .navigationTitle(L("买卖点模式"))
        .navigationBarTitleDisplayMode(.inline)
        .task { await manager.loadOptions() }
    }
}
