import SwiftUI

struct QuantStageSheet: View {
    let selected: QuantLifecycleStage
    let research: QuantResearch
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                QuantStageDetailContent(selected: selected, research: research)
            }
            .background(Theme.background)
            .navigationTitle(L("企业阶段"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("完成")) { dismiss() }
                }
            }
        }
    }
}
