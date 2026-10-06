import SwiftUI
import PDFKit

/// 研报原文：下载 PDF 到本地缓存（Caches/reports），之后离线可看；在 App 内阅读，不跳浏览器。
enum ReportCache {
    private static var dir: URL {
        let d = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("reports", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }

    private static func localURL(for remote: URL) -> URL {
        // 链接里的文件名本身就带研报编号，直接当缓存文件名
        dir.appendingPathComponent(remote.lastPathComponent)
    }

    static func isCached(_ remote: URL) -> Bool {
        FileManager.default.fileExists(atPath: localURL(for: remote).path)
    }

    /// 已缓存直接返回本地文件；否则下载、校验确实是 PDF 后落盘。
    static func load(_ remote: URL) async throws -> URL {
        let local = localURL(for: remote)
        if FileManager.default.fileExists(atPath: local.path), PDFDocument(url: local) != nil { return local }
        let (tmp, resp) = try await URLSession.shared.download(from: remote)
        guard (resp as? HTTPURLResponse)?.statusCode == 200, PDFDocument(url: tmp) != nil else {
            throw URLError(.cannotParseResponse)
        }
        try? FileManager.default.removeItem(at: local)
        try FileManager.default.moveItem(at: tmp, to: local)
        return local
    }
}

/// 点研报行弹出的阅读页。
struct ReportPDFView: View {
    let title: String
    let remote: URL
    @Environment(\.dismiss) private var dismiss
    @State private var localURL: URL?
    @State private var failed = false

    var body: some View {
        NavigationStack {
            Group {
                if let localURL {
                    PDFKitView(url: localURL)
                } else if failed {
                    VStack(spacing: 10) {
                        Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(Theme.textSecondary)
                        Text(L("研报原文加载失败")).font(.subheadline).foregroundStyle(Theme.textPrimary)
                        Button(L("重试")) { Task { await load() } }
                    }
                } else {
                    VStack(spacing: 10) {
                        ProgressView()
                        Text(L("正在下载研报…")).font(.caption).foregroundStyle(Theme.textSecondary)
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.background)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button(L("完成")) { dismiss() } }
                if let localURL {
                    // 存到「文件」App / 发给别人：系统分享面板里选「存储到文件」即下载到手机
                    ToolbarItem(placement: .cancellationAction) {
                        ShareLink(item: localURL) { Image(systemName: "square.and.arrow.down") }
                            .accessibilityLabel(L("保存到手机"))
                    }
                }
            }
        }
        .task { await load() }
    }

    private func load() async {
        failed = false
        do { localURL = try await ReportCache.load(remote) } catch { failed = true }
    }
}

private struct PDFKitView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.document = PDFDocument(url: url)
        return v
    }

    func updateUIView(_ uiView: PDFView, context: Context) {}
}
