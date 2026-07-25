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
                        ProgressView("正在识别单词…")
                            .tint(Theme.accent)
                            .foregroundColor(Theme.textPrimary)
                    } else {
                        Image(systemName: "camera.viewfinder")
                            .font(.system(size: 64))
                            .foregroundColor(Theme.textSecondary)
                        Text("拍摄或选择含英语单词的图片")
                            .foregroundColor(Theme.textSecondary)
                    }

                    if let errorMessage = viewModel.errorMessage {
                        Text(errorMessage)
                            .font(.footnote)
                            .foregroundColor(Theme.unknown)
                    }

                    VStack(spacing: 12) {
                        Button {
                            showCameraSheet = true
                        } label: {
                            Label("拍照", systemImage: "camera.fill")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .background(Theme.accent)
                                .foregroundColor(.white)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(viewModel.isRecognizing)

                        PhotosPicker(selection: $photoPickerItem, matching: .images) {
                            Label("从相册选择", systemImage: "photo.on.rectangle")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                                .background(Theme.surface)
                                .foregroundColor(Theme.textPrimary)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                        }
                        .disabled(viewModel.isRecognizing)
                    }
                    .padding(.horizontal)

                    Spacer()
                    Spacer()
                }
            }
            .navigationTitle("拍照识词")
            .sheet(isPresented: $showCameraSheet) {
                CameraPicker { image in
                    Task {
                        // 缩放+压缩是 CPU 密集操作，放主线程做会在点「使用照片」的瞬间卡一下
                        // （尤其真机原图有几千万像素）。先立刻显示识别中状态，压缩本身丢到
                        // Task.detached 的后台线程池执行，避免阻塞 UI。
                        viewModel.isRecognizing = true
                        let data = await Task.detached(priority: .userInitiated) {
                            Self.compressedJPEGData(from: image)
                        }.value
                        guard let data else {
                            viewModel.isRecognizing = false
                            return
                        }
                        await viewModel.recognize(imageData: data)
                    }
                }
                .ignoresSafeArea()
            }
            .onChange(of: photoPickerItem) { _, newItem in
                guard let newItem else { return }
                Task {
                    viewModel.isRecognizing = true
                    guard let rawData = try? await newItem.loadTransferable(type: Data.self) else {
                        viewModel.isRecognizing = false
                        return
                    }
                    photoPickerItem = nil
                    let data = await Task.detached(priority: .userInitiated) {
                        UIImage(data: rawData).flatMap { Self.compressedJPEGData(from: $0) }
                    }.value
                    guard let data else {
                        viewModel.isRecognizing = false
                        return
                    }
                    await viewModel.recognize(imageData: data)
                }
            }
            .sheet(isPresented: $viewModel.showResult) {
                RecognizeResultView(viewModel: viewModel)
            }
        }
    }

    /// 把图片压缩到安全体积以内。
    ///
    /// 真机拍照原图常有 2-8MB，而 Railway 的边缘代理对请求体有约 1MB 的硬限制——
    /// 超过会在到达后端代码之前就被拒绝，返回一个无法被我们的错误处理捕获的裸
    /// 500（这是实测出来的：700KB 能过，900KB 必定 500）。这里先把最长边缩到
    /// 1600px（对识别文档里的英语单词完全够用），再用递减的 JPEG 质量压到
    /// 700KB 以内，留出安全余量。
    /// 显式标 nonisolated：`CameraCaptureView` 遵循 `View`，成员默认可能被隐式
    /// 归到 MainActor，如果这个函数被隐式 MainActor 隔离，Task.detached 里
    /// `await` 调用它反而会跳回主线程执行，压缩计算还是卡主线程，等于白改。
    private nonisolated static func compressedJPEGData(
        from image: UIImage, maxDimension: CGFloat = 1600, maxBytes: Int = 700_000
    ) -> Data? {
        let size = image.size
        let longestSide = max(size.width, size.height)
        let scale = longestSide > maxDimension ? maxDimension / longestSide : 1.0
        let targetSize = CGSize(width: size.width * scale, height: size.height * scale)

        let resized: UIImage
        if scale < 1.0 {
            let renderer = UIGraphicsImageRenderer(size: targetSize)
            resized = renderer.image { _ in image.draw(in: CGRect(origin: .zero, size: targetSize)) }
        } else {
            resized = image
        }

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
