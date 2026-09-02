import SwiftUI
import UIKit
import Photos

/// 分享前的预览弹窗：完整看一遍拼好的分享图，再决定保存还是发出去。
///
/// 存在的理由见 Task 5 需求本身——系统分享面板顶部的缩略图只有几十像素，
/// 相当于盲发；这里把 `ShareComposer.compose` 的成品原样铺开滚动查看。
struct SharePreviewSheet: View {
    let image: UIImage
    let text: String

    @Environment(\.dismiss) private var dismiss
    @State private var showShareSheet = false
    @State private var saveResult: SaveResult?
    /// 保存进行中。双击会往相册写两张一模一样的图，还把状态提示搅乱。
    @State private var isSaving = false

    var body: some View {
        VStack(spacing: 16) {
            ScrollView {
                // 分享图是「品牌头+原图+免责条」竖向拼接，可能比一屏还长，
                // 必须能滚动看到底部——尤其免责条，那是唯一跟着图走的风险提示。
                Image(uiImage: image)
                    .resizable()
                    .scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                    .padding(.horizontal, 20)
                    .padding(.top, 16)
            }

            if let saveResult {
                saveResultBanner(saveResult)
            }

            HStack(spacing: 12) {
                Button(action: saveToAlbum) {
                    // 保存进行中转菊花并禁用，防止双击写两张重复图进相册
                    if isSaving { ProgressView() } else { Text(L("保存到相册")) }
                    Text(L("保存到相册"))
                        .font(.system(size: 16, weight: .medium))
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(Theme.surfaceAlt)
                        .foregroundColor(Theme.textPrimary)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
                .disabled(isSaving)
                Button { showShareSheet = true } label: {
                    Text(L("分享"))
                        .font(.system(size: 16, weight: .semibold))
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(Theme.accent)
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 8)
        }
        .background(Theme.background)
        .sheet(isPresented: $showShareSheet) {
            ShareSheet(items: [image, text])
        }
    }

    @ViewBuilder
    private func saveResultBanner(_ result: SaveResult) -> some View {
        switch result {
        case .success:
            Text(L("已保存到相册"))
                .font(.footnote)
                .foregroundColor(Theme.textSecondary)
        case .deniedPermission:
            // 权限被拒后再点按钮也不会重新弹系统授权框（系统只弹一次），
            // 所以只能靠这行文案 + 跳转入口把用户引导到设置里自己开。
            VStack(spacing: 4) {
                Text(L("相册权限未开启，无法保存"))
                    .font(.footnote)
                    .foregroundColor(Theme.textSecondary)
                Button(L("前往设置")) { openSystemSettings() }
                    .font(.footnote.bold())
                    .foregroundColor(Theme.accent)
            }
        case .failure:
            Text(L("保存失败，请重试"))
                .font(.footnote)
                .foregroundColor(Theme.textSecondary)
        }
    }

    private enum SaveResult {
        case success
        case deniedPermission
        case failure
    }

    /// 保存到相册。
    ///
    /// 用 `PHPhotoLibrary` 的 async/await API 而不是原版参考实现里的
    /// `UIImageWriteToSavedPhotosAlbum(_:nil:nil:nil)`：后者把 completion selector
    /// 传 nil 等于放弃了所有结果反馈，无论成功、权限被拒还是写入失败都会一律显示
    /// 「已保存到相册」——这是在骗用户，相册里其实什么都没有。
    ///
    /// 权限只申请 `.addOnly`（对应 Info.plist 里已有的
    /// `NSPhotoLibraryAddUsageDescription`），不用 `.readWrite`：分享图只需要「写进去」，
    /// 没有理由申请读取用户整个相册的权限，那是过度索权，也会被 App Store 审核质疑。
    private func saveToAlbum() {
        guard !isSaving else { return }
        isSaving = true
        Task {
            defer { isSaving = false }
            let status = await PHPhotoLibrary.requestAuthorization(for: .addOnly)
            switch status {
            case .authorized, .limited:
                await performSave()
            case .denied, .restricted:
                saveResult = .deniedPermission
            case .notDetermined:
                // 理论上 requestAuthorization 返回后不会还是 notDetermined，
                // 保底按失败处理，避免吞掉这个分支。
                saveResult = .failure
            @unknown default:
                saveResult = .failure
            }
        }
    }

    private func performSave() async {
        do {
            try await PHPhotoLibrary.shared().performChanges {
                PHAssetChangeRequest.creationRequestForAsset(from: image)
            }
            saveResult = .success
            // 成功后自动关掉：保存目的已达成，留着弹窗只会挡住下面的 App 内容。
            // 延迟半秒让用户看到「已保存到相册」的提示再落下去。
            try? await Task.sleep(nanoseconds: 500_000_000)
            dismiss()
        } catch {
            saveResult = .failure
        }
    }

    private func openSystemSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }
}
