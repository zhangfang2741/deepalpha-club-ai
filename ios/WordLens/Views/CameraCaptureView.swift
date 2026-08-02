// Views/CameraCaptureView.swift
import SwiftUI
import PhotosUI
import UIKit

struct CameraCaptureView: View {
    @StateObject private var viewModel = CameraViewModel()
    @State private var photoPickerItem: PhotosPickerItem?
    @State private var showCameraSheet = false

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.background.ignoresSafeArea()
                VStack(spacing: 24) {
                    Spacer()

                    if viewModel.isRecognizing {
                        ScanningOverlay(
                            image: viewModel.capturedImage,
                            partialWordCount: viewModel.partialWordCount,
                            enrichedWordCount: viewModel.partialEnrichedCount
                        )
                    } else {
                        Image(systemName: "camera.viewfinder")
                            .font(.system(size: 64))
                            .foregroundStyle(Theme.textSecondary)
                        Text("拍摄或选择含英语单词的图片")
                            .foregroundStyle(Theme.textSecondary)
                    }

                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage)
                            .font(.footnote)
                            .foregroundStyle(Theme.unknown)
                    }

                    // 识别期间只保留扫描图和进度反馈。原来这里只禁用按钮，按钮仍会
                    // 占据布局空间，并在进度状态切换时插到两段状态文案之间。
                    if !viewModel.isRecognizing {
                        VStack(spacing: 12) {
                            Button {
                                showCameraSheet = true
                            } label: {
                                Label("拍照", systemImage: "camera.fill")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 14)
                                    .background(Theme.accent)
                                    .foregroundStyle(.white)
                                    .clipShape(.rect(cornerRadius: 12))
                            }
                            .buttonStyle(.pressable)

                            PhotosPicker(selection: $photoPickerItem, matching: .images) {
                                Label("从相册选择", systemImage: "photo.on.rectangle")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 14)
                                    .background(Theme.surface)
                                    .foregroundStyle(Theme.textPrimary)
                                    .clipShape(.rect(cornerRadius: 12))
                            }
                        }
                        .padding(.horizontal)
                    }

                    Spacer()
                    Spacer()
                }
            }
            .navigationTitle("拍照录入")
            .sheet(isPresented: $showCameraSheet) {
                CameraPicker { image in
                    Task { await process(image) }
                }
                .ignoresSafeArea()
            }
            .onChange(of: photoPickerItem) { _, newItem in
                guard let newItem else { return }
                Task {
                    viewModel.isRecognizing = true
                    guard let rawData = try? await newItem.loadTransferable(type: Data.self),
                          let image = UIImage(data: rawData)
                    else {
                        viewModel.isRecognizing = false
                        return
                    }
                    photoPickerItem = nil
                    await process(image)
                }
            }
            .sheet(isPresented: $viewModel.showResult) {
                RecognizeResultView(viewModel: viewModel)
                    // 用户在结果列表里向下滑动，本意非常可能就是想看下面的识别结果，
                    // 但 iOS 13+ 的 sheet 默认把整张页面的下滑手势接管成"下拉关闭"，
                    // 结果就是识别完一抬手什么都没了，整批识别结果丢掉。
                    // 取消按钮（左上）已经走 confirmationDialog 二次确认，关闭入口
                    // 不缺这一个，这里只禁掉手势关掉，让下拉真回到它该干的事（滚动）。
                    .interactiveDismissDisabled(true)
            }
        }
    }

    /// 拍照/选图共用的预处理 + 识别入口。
    ///
    /// 顺序是关键（解决"拍完要等几秒才出现扫描效果"）：扫描背景图 `capturedImage`
    /// 只需要一张 600px 缩略图，先把它算出来并**立刻**赋值，扫描效果连同用户照片
    /// 马上出现；较重的压缩 + 本地 OCR 再在后台跑，此时扫描动画已经在转，用户无感。
    /// 旧写法把缩略图、压缩、OCR 塞进同一个顺序元组一起等，最慢的 OCR（几秒）把
    /// 缩略图也一起拖住，照片+扫描线要等 OCR 跑完才显示。
    ///
    /// 内存：只对原图解码/重绘一次到 1600px（`uploadImage`），缩略图、压缩、OCR
    /// 都基于这张图派生，避免同一时刻内存里有多份大位图触发内存看门狗 SIGKILL。
    private func process(_ image: UIImage) async {
        viewModel.isRecognizing = true
        // 第一步：解码到 1600px 并派生缩略图，立刻显示——扫描效果秒出，不被压缩/OCR 拖住。
        let (uploadImage, thumbnail) = await Task.detached(priority: .userInitiated) {
            () -> (UIImage, UIImage) in
            let uploadImage = Self.resizedImage(from: image, maxDimension: 1600)
            return (uploadImage, Self.resizedImage(from: uploadImage, maxDimension: 600))
        }.value
        viewModel.capturedImage = thumbnail
        // 第二步：压缩 + 本地 OCR 放后台。OCR 也喂这张 1600px 图（跟后端视觉模型输入
        // 一致；印刷体在 1600px 下完全够认，喂原图只是白烧耗时/内存）。
        let (data, ocrWords) = await Task.detached(priority: .userInitiated) {
            () -> (Data?, [String]) in
            (
                Self.compressedJPEGData(from: uploadImage),
                await TextRecognizer.recognizeWords(from: uploadImage)
            )
        }.value
        guard let data else {
            viewModel.isRecognizing = false
            viewModel.errorMessage = "照片处理失败，请重新拍摄"
            return
        }
        await viewModel.recognize(imageData: data, ocrWords: ocrWords)
    }

    /// 等比缩放到最长边不超过 maxDimension。真机原图解码成 UIImage 后在内存里可能
    /// 有几十上百 MB（几千万像素 × 4 字节/像素），拍完照如果直接把这张原图存进
    /// @Published 属性给 SwiftUI 长期持有/渲染（比如扫描动画背景），加上其它状态
    /// 一起很容易把 App 撑到被系统内存看门狗直接 SIGKILL 杀掉（实测复现过）。
    /// 所以无论是给后端上传压缩，还是给 UI 当缩略图显示，都要先经过这一步缩小，
    /// 不能碰原图本体。
    /// 显式标 nonisolated：`CameraCaptureView` 遵循 `View`，成员默认可能被隐式
    /// 归到 MainActor，如果这个函数被隐式 MainActor 隔离，Task.detached 里
    /// `await` 调用它反而会跳回主线程执行，还是卡主线程，等于白改。
    private nonisolated static func resizedImage(from image: UIImage, maxDimension: CGFloat) -> UIImage {
        let size = image.size
        let longestSide = max(size.width, size.height)
        guard longestSide > maxDimension else { return image }
        let scale = maxDimension / longestSide
        let targetSize = CGSize(width: size.width * scale, height: size.height * scale)
        let renderer = UIGraphicsImageRenderer(size: targetSize)
        return renderer.image { _ in image.draw(in: CGRect(origin: .zero, size: targetSize)) }
    }

    /// 把图片压缩到安全体积以内。
    ///
    /// 真机拍照原图常有 2-8MB，而 Railway 的边缘代理对请求体有约 1MB 的硬限制——
    /// 超过会在到达后端代码之前就被拒绝，返回一个无法被我们的错误处理捕获的裸
    /// 500（这是实测出来的：700KB 能过，900KB 必定 500）。这里先把最长边缩到
    /// 1600px（对识别文档里的英语单词完全够用），再用递减的 JPEG 质量压到
    /// 700KB 以内，留出安全余量。
    private nonisolated static func compressedJPEGData(
        from image: UIImage, maxDimension: CGFloat = 1600, maxBytes: Int = 700_000
    ) -> Data? {
        let resized = resizedImage(from: image, maxDimension: maxDimension)
        var quality: CGFloat = 0.7
        var data = resized.jpegData(compressionQuality: quality)
        while let currentData = data, currentData.count > maxBytes, quality > 0.2 {
            quality -= 0.15
            data = resized.jpegData(compressionQuality: quality)
        }
        return data
    }
}

/// 桥接系统相机（PhotosPicker 只能选相册，拍照要用 UIImagePickerController）。
/// 用完成回调而不是 @Binding<UIImage?> + onChange：UIImage 不遵循 Equatable，
/// iOS 17 的 onChange(of:) 要求值类型可比较，绑定 UIImage? 会直接编译报错。
private struct CameraPicker: UIViewControllerRepresentable {
    let onCapture: (UIImage) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker
        init(_ parent: CameraPicker) { self.parent = parent }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage {
                parent.onCapture(image)
            }
            parent.dismiss()
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}
