import SwiftUI

/// 保持筛选说明轻量，同时区分低评级、数据缺失和查询故障。
struct RadarQuantFilterSummary: View {
    let filter: RadarQuantFilter

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            if filter.status == "unavailable" {
                Text(L("量化评级暂不可用，请稍后刷新"))
            } else {
                Text(L("量化 ≥ %@ · 符合 %lld 只 · 低于门槛 %lld 只", filter.minGrade, filter.eligible, filter.belowThreshold))
                if filter.missing + filter.stale > 0 {
                    Text(L("评级缺失 %lld 只 · 已过期 %lld 只", filter.missing, filter.stale))
                }
            }
            if filter.preserveSells { Text(L("自选股卖出提醒保留")) }
        }
        .font(.caption2)
        .foregroundStyle(Theme.textSecondary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
    }
}
