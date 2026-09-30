import SwiftUI

/// 展示评级排序权重与覆盖情况，缺失评级不影响信号入选。
struct RadarQuantFilterSummary: View {
    let filter: RadarQuantFilter

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            if filter.status == "unavailable" {
                Text(L("评级暂不可用，按技术信号排序"))
            } else {
                // weight 为 0（当前口径）时评级只展示不参与排序，不显示权重行
                if let weight = filter.weight, weight > 0 {
                    Text(L("评级权重 %lld%% · 已评级 %lld 只", Int(weight * 100), filter.eligible))
                } else {
                    Text(L("已评级 %lld 只", filter.eligible))
                }
                if filter.missing + filter.stale > 0 {
                    Text(L("评级缺失 %lld 只 · 已过期 %lld 只", filter.missing, filter.stale))
                }
            }

        }
        .font(.caption2)
        .foregroundStyle(Theme.textSecondary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
    }
}
