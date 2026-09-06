import SwiftUI

/// 深度解读：付费墙锁定态 UI。真实调用 /interpretation?section=deep 和 StoreKit
/// 购买解锁都在下一个 Plan 里做，这里先把"未订阅时长什么样"做出来。
struct DeepInterpretationView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "lock.fill")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text("订阅解锁深度解读")
            Text("即将推出")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
    }
}
