import SwiftUI
import PDFKit
import WebKit

/// 研报原文：下载 PDF 到本地缓存（Caches/reports），之后离线可看；在 App 内阅读，不跳浏览器。
enum ReportCache {
    private static var dir: URL {
        let d = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("reports", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }

    private static func localURL(for remote: URL) -> URL {
        // 取路径最后两段当文件名：研报链接的文件名本身带编号；SEC 文档的上一级是披露编号，两段合起来不会重名
        dir.appendingPathComponent(remote.pathComponents.suffix(2).joined(separator: "-"))
    }

    static func isCached(_ remote: URL) -> Bool {
        FileManager.default.fileExists(atPath: localURL(for: remote).path)
    }

    /// 给分享 / 存到「文件」用的副本：缓存里的文件名是编号（H2_AN…_1.pdf），存到手机上不好认，换成「券商 标题.pdf」这样的名字。
    static func shareCopy(of local: URL, name: String) -> URL {
        let bad = CharacterSet(charactersIn: "/\\:*?\"<>|\n\r")
        let clean = name.components(separatedBy: bad).joined(separator: " ").trimmingCharacters(in: .whitespaces)
        let base = String(clean.prefix(80))
        let ext = local.pathExtension.isEmpty ? "html" : local.pathExtension
        let dest = FileManager.default.temporaryDirectory.appendingPathComponent("\(base.isEmpty ? "report" : base).\(ext)")
        try? FileManager.default.removeItem(at: dest)
        do { try FileManager.default.copyItem(at: local, to: dest); return dest } catch { return local }
    }

    /// 已缓存直接返回本地文件；否则下载、校验确实是 PDF 后落盘。
    static func load(_ remote: URL, isPDF: Bool = true, onProgress: (@Sendable (Double?) -> Void)? = nil) async throws -> URL {
        let local = localURL(for: remote)
        if FileManager.default.fileExists(atPath: local.path), !isPDF || PDFDocument(url: local) != nil { return local }
        var request = URLRequest(url: remote)
        if remote.host?.hasSuffix("sec.gov") == true {
            // SEC 要求声明身份的 User-Agent，否则可能被拒
            request.setValue("DeepAlpha research contact@deepalpha.club", forHTTPHeaderField: "User-Agent")
        }
        let (tmp, resp) = try await ReportDownloader(onProgress: onProgress).download(request)
        guard (resp as? HTTPURLResponse)?.statusCode == 200, !isPDF || PDFDocument(url: tmp) != nil else {
            throw URLError(.cannotParseResponse)
        }
        try? FileManager.default.removeItem(at: local)
        try FileManager.default.moveItem(at: tmp, to: local)
        return local
    }
}

/// PDF 目录里的一条。
struct PDFTocItem: Identifiable {
    let id = UUID()
    let title: String
    let level: Int
    let pageIndex: Int
}

extension ReportCache {
    /// 目录：优先用 PDF 自带的书签；没有书签时（A 股财报常见）按版式找「第X节 / 第X章」开头的页面凑一份。
    /// 页码与重排副本一一对应（重排只改页面大小、不增删页）。
    static func tableOfContents(of local: URL) async -> [PDFTocItem] {
        await Task.detached(priority: .utility) { () -> [PDFTocItem] in
            guard let doc = PDFDocument(url: local) else { return [] }
            if let root = doc.outlineRoot, root.numberOfChildren > 0 {
                var out: [PDFTocItem] = []
                func walk(_ node: PDFOutline, level: Int) {
                    for i in 0..<node.numberOfChildren {
                        guard let child = node.child(at: i) else { continue }
                        if let title = child.label, !title.trimmingCharacters(in: .whitespaces).isEmpty,
                           let page = child.destination?.page {
                            out.append(PDFTocItem(title: title, level: level, pageIndex: doc.index(for: page)))
                        }
                        walk(child, level: level + 1)
                    }
                }
                walk(root, level: 0)
                if !out.isEmpty { return out }
            }
            let headings = headingToc(doc)
            if headings.count >= 3 { return headings }
            // 既没有书签、也没有「第X节」（港股业绩公告、季报这类短文件）：取每页开头的短标题凑一份
            let generic = genericToc(doc)
            return generic.isEmpty ? headings : generic
        }.value
    }

    /// 通用兜底：每页取开头第一行「像标题的短行」（跳过纯页码、每页都出现的页眉），去掉「（续）」，同名只留第一次。只用于 80 页以内的短文件。
    private static func genericToc(_ doc: PDFDocument) -> [PDFTocItem] {
        guard doc.pageCount >= 3, doc.pageCount <= 80 else { return [] }
        let pageLines: [[String]] = (0..<doc.pageCount).map { i in
            (doc.page(at: i)?.string ?? "").components(separatedBy: .newlines)
                .map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        }
        var frequency: [String: Int] = [:]
        for lines in pageLines { for l in Set(lines.prefix(3)) { frequency[l, default: 0] += 1 } }
        let runningHeaders = Set(frequency.filter { $0.value >= 3 }.keys)

        func candidate(_ raw: String) -> String? {
            var t = raw
            for suffix in ["（續）", "（续）", "(續)", "(续)", "－續", "-續", "-续"] where t.hasSuffix(suffix) {
                t = String(t.dropLast(suffix.count)).trimmingCharacters(in: .whitespaces)
            }
            guard (2...28).contains(t.count), !t.hasPrefix("•"), !t.hasPrefix("·"), !t.hasPrefix("-"),
                  !t.lowercased().contains("http"), t.rangeOfCharacter(from: CharacterSet(charactersIn: "。，；：,;")) == nil else { return nil }
            // 提取成乱码的行（字体没有字符映射）不能当标题
            let readable = t.unicodeScalars.filter {
                CharacterSet.alphanumerics.contains($0) || CharacterSet.whitespaces.contains($0) || ("\u{4E00}"..."\u{9FFF}").contains($0)
            }.count
            guard Double(readable) / Double(t.unicodeScalars.count) >= 0.8 else { return nil }
            return t
        }

        var seen = Set<String>()
        var out: [PDFTocItem] = []
        for (i, lines) in pageLines.enumerated() {
            for l in lines.prefix(4) {
                if l.allSatisfy({ $0.isNumber }) || runningHeaders.contains(l) { continue }
                if let t = candidate(l), seen.insert(t).inserted { out.append(PDFTocItem(title: t, level: 0, pageIndex: i)) }
                break  // 只看第一条既不是页码、也不是页眉的行
            }
        }
        return out.count >= 3 ? Array(out.prefix(40)) : []
    }

    private static func headingToc(_ doc: PDFDocument) -> [PDFTocItem] {
        let pattern = try? NSRegularExpression(pattern: "^\\s*第[一二三四五六七八九十百]+[节章]\\s*\\S.{0,30}$")
        guard let pattern else { return [] }
        func isHeading(_ line: String) -> Bool {
            pattern.firstMatch(in: line, range: NSRange(line.startIndex..., in: line)) != nil
        }
        var out: [PDFTocItem] = []
        var seen = Set<String>()
        for i in 0..<doc.pageCount {
            guard let text = doc.page(at: i)?.string else { continue }
            let lines = text.components(separatedBy: .newlines)
                .map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
            // 目录页会一口气列出好几个「第X节」，不当作章节起点
            if lines.filter(isHeading).count >= 3 { continue }
            if let head = lines.prefix(4).first(where: isHeading), seen.insert(head).inserted {
                out.append(PDFTocItem(title: head, level: 0, pageIndex: i))
            }
        }
        return out
    }

    /// 页面宽度不一致（竖版 A4 夹着横版表格页）时，PDFKit 按最宽的页缩放，竖版页就缩在中间、两边留一大片空。
    /// 这种文件重新排一份「每页同宽」的副本（矢量内容原样画进去、文字保留），缓存在原文件旁边；页面本来就一致的直接用原文件。
    static func fitted(_ local: URL) async -> URL {
        await Task.detached(priority: .userInitiated) { () -> URL in
            let out = local.deletingPathExtension().appendingPathExtension("fit.pdf")
            if FileManager.default.fileExists(atPath: out.path) { return out }
            guard let doc = PDFDocument(url: local), doc.pageCount > 1 else { return local }
            let widths = (0..<doc.pageCount).compactMap { doc.page(at: $0)?.bounds(for: .cropBox).width }
            guard let lo = widths.min(), let hi = widths.max(), hi - lo > 8 else { return local }
            guard let cg = CGPDFDocument(local as CFURL) else { return local }

            let fixedWidth: CGFloat = 595
            let renderer = UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: fixedWidth, height: 842))
            let tmp = out.appendingPathExtension("part")
            do {
                try renderer.writePDF(to: tmp) { ctx in
                    for i in 1...cg.numberOfPages {
                        guard let page = cg.page(at: i) else { continue }
                        var box = page.getBoxRect(.cropBox)
                        if page.rotationAngle % 180 != 0 { box = CGRect(x: 0, y: 0, width: box.height, height: box.width) }
                        let h = box.width > 0 ? box.height * fixedWidth / box.width : 842
                        let rect = CGRect(x: 0, y: 0, width: fixedWidth, height: h)
                        ctx.beginPage(withBounds: rect, pageInfo: [:])
                        let c = ctx.cgContext
                        c.saveGState()
                        c.translateBy(x: 0, y: h)
                        c.scaleBy(x: 1, y: -1)
                        c.concatenate(page.getDrawingTransform(.cropBox, rect: rect, rotate: 0, preserveAspectRatio: true))
                        c.drawPDFPage(page)
                        c.restoreGState()
                    }
                }
                try? FileManager.default.removeItem(at: out)
                try FileManager.default.moveItem(at: tmp, to: out)
                return out
            } catch {
                try? FileManager.default.removeItem(at: tmp)
                return local
            }
        }.value
    }
}

/// 带进度回调的下载：URLSession 的 async download 拿不到进度，所以自己接一个下载代理。
/// 进度为 nil 表示服务器没给总大小（只能转圈）。
final class ReportDownloader: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    private let onProgress: (@Sendable (Double?) -> Void)?
    private let lock = NSLock()
    private var continuation: CheckedContinuation<(URL, URLResponse), Error>?
    private var task: URLSessionDownloadTask?
    private var session: URLSession?

    init(onProgress: (@Sendable (Double?) -> Void)?) { self.onProgress = onProgress }

    func download(_ request: URLRequest) async throws -> (URL, URLResponse) {
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (c: CheckedContinuation<(URL, URLResponse), Error>) in
                let s = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
                let t = s.downloadTask(with: request)
                lock.lock(); continuation = c; session = s; task = t; lock.unlock()
                t.resume()
            }
        } onCancel: {
            lock.lock(); let t = task; lock.unlock()
            t?.cancel()
        }
    }

    private func finish(_ result: Result<(URL, URLResponse), Error>) {
        lock.lock()
        let c = continuation; continuation = nil
        let s = session; session = nil
        lock.unlock()
        s?.finishTasksAndInvalidate()
        c?.resume(with: result)
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didWriteData bytesWritten: Int64,
                    totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        onProgress?(totalBytesExpectedToWrite > 0 ? Double(totalBytesWritten) / Double(totalBytesExpectedToWrite) : nil)
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        // 临时文件在这个回调返回后就会被系统删掉，必须在这里挪走
        let dest = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        do {
            try FileManager.default.moveItem(at: location, to: dest)
            guard let resp = downloadTask.response else { throw URLError(.badServerResponse) }
            finish(.success((dest, resp)))
        } catch {
            finish(.failure(error))
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error { finish(.failure(error)) }
    }
}

/// 阅读页：PDF（研报、A 股 / 港股财报）、SEC 网页文档（美股财报，先下载到本机）、普通网页（媒体报道）共用一套外壳——
/// 加载中 / 失败重试 / 左上角保存到手机 / 右上角完成。
/// 阅读页右下角「AI 总结」需要的上下文：哪只股票的哪一份财报（kind = latest / annual）。
struct ReportSummaryContext {
    let market: StockMarket
    let symbol: String
    let kind: String
    let report: LatestReport
}

struct ReportReaderView: View {
    enum Kind { case pdf, filing, page }

    let title: String
    let remote: URL
    let kind: Kind
    var shareName: String?
    var summary: ReportSummaryContext? = nil
    @Environment(\.dismiss) private var dismiss
    @State private var showSummary = false
    @State private var cachedSummary: ReportSummaryResponse?
    @State private var localURL: URL?
    @State private var shareURL: URL?
    @State private var failed = false
    @State private var downloaded = false
    @State private var displayURL: URL?
    @State private var preparing = false
    @State private var toc: [PDFTocItem] = []
    @State private var showToc = false
    @State private var jumpTo: Int?
    @State private var progress: Double?

    var body: some View {
        NavigationStack {
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Theme.background)
                .navigationTitle(title)
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) { Button(L("完成")) { dismiss() } }
                    ToolbarItemGroup(placement: .topBarLeading) {
                        if let shareURL {
                            // 系统分享面板里选「存储到文件」即下载到手机
                            ShareLink(item: shareURL) { Image(systemName: "square.and.arrow.down") }
                                .accessibilityLabel(L("保存到手机"))
                        }
                        if !toc.isEmpty {
                            Button { showToc = true } label: { Image(systemName: "list.bullet") }
                                .accessibilityLabel(L("目录"))
                        }
                    }
                }
        }
        .presentationDragIndicator(.visible)
        .overlay(alignment: .bottomTrailing) {
            if let summary, documentVisible { summaryButton(summary) }
        }
        .sheet(isPresented: $showSummary) {
            if let summary {
                ReportSummarySheet(market: summary.market, symbol: summary.symbol, report: summary.report,
                                   kind: summary.kind, initial: cachedSummary)
                    .presentationDetents([.large])
            }
        }
        .task {
            // 打开阅读页时静悄悄探一下有没有缓存好的总结（不触发生成）：有的话点「AI 总结」直接显示、按钮也会高亮
            guard let summary else { return }
            let r = try? await QuantResearchService.reportSummary(market: summary.market, symbol: summary.symbol,
                                                                  kind: summary.kind, peek: true)
            if r?.status == "ready" { cachedSummary = r }
        }
        .sheet(isPresented: $showToc) {
            PDFTocSheet(items: toc) { index in
                jumpTo = index
                showToc = false
            }
            .presentationDetents([.medium, .large])
        }
        .task { await load() }
    }

    /// 文档已经显示出来（加载 / 整理版面期间不放浮动按钮）
    private var documentVisible: Bool {
        switch kind {
        case .pdf: return displayURL != nil
        case .filing: return downloaded || failed
        case .page: return false
        }
    }

    private func summaryButton(_ s: ReportSummaryContext) -> some View {
        let cached = cachedSummary != nil
        return Button { showSummary = true } label: {
            Label(L("AI 总结"), systemImage: "sparkles")
                .font(.system(size: 14, weight: .semibold))
                .padding(.horizontal, 16)
                .frame(minHeight: 44)
                .foregroundStyle(cached ? Color.white : Theme.textPrimary)
                .background(cached ? AnyShapeStyle(Theme.accent) : AnyShapeStyle(.ultraThinMaterial), in: Capsule())
                .overlay(Capsule().stroke(Theme.border))
                .shadow(color: .black.opacity(0.25), radius: 8, y: 3)
        }
        .buttonStyle(.plain)
        .padding(.trailing, 16)
        .padding(.bottom, 28)
        .accessibilityLabel(L("AI 总结"))
    }

    @ViewBuilder private var content: some View {
        switch kind {
        case .page:
            InAppWebView(url: remote, local: nil, paper: false)
        case .pdf:
            if let displayURL { PDFKitView(url: displayURL, jumpTo: $jumpTo) } else { status }
        case .filing:
            // 下载失败时直接在线打开网页（不能保存），比报错有用
            if downloaded || failed { InAppWebView(url: remote, local: localURL, paper: true) } else { status }
        }
    }

    @ViewBuilder private var status: some View {
        if preparing {
            VStack(spacing: 10) {
                ProgressView()
                Text(L("正在整理版面…")).font(.subheadline).foregroundStyle(Theme.textPrimary)
            }
        } else if failed {
            VStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(Theme.textSecondary)
                Text(L("加载失败，请检查网络后重试")).font(.subheadline).foregroundStyle(Theme.textPrimary)
                Button(L("重试")) { Task { await load() } }
                    .buttonStyle(.bordered).frame(minHeight: 44)
            }
        } else {
            VStack(spacing: 10) {
                if let progress {
                    ProgressView(value: progress).frame(width: 180)
                    Text(L("正在下载… %lld%%", Int((progress * 100).rounded()))).font(.subheadline).foregroundStyle(Theme.textPrimary)
                        .monospacedDigit()
                } else {
                    ProgressView()
                    Text(L("正在下载…")).font(.subheadline).foregroundStyle(Theme.textPrimary)
                }
                Text(L("只需首次，之后缓存在本机")).font(.caption).foregroundStyle(Theme.textSecondary)
            }
        }
    }

    private func load() async {
        failed = false
        progress = nil
        guard kind != .page else { return }
        do {
            let local = try await ReportCache.load(remote, isPDF: kind == .pdf) { p in
                Task { @MainActor in progress = p }
            }
            localURL = local
            shareURL = ReportCache.shareCopy(of: local, name: shareName ?? title)
            if kind == .pdf {
                preparing = true
                displayURL = await ReportCache.fitted(local)
                preparing = false
                toc = await ReportCache.tableOfContents(of: local)
            }
            downloaded = true
        } catch {
            failed = true
        }
    }
}

/// 兼容的薄封装：各处调用点不用改。
struct ReportPDFView: View {
    let title: String
    let remote: URL
    var shareName: String?
    var summary: ReportSummaryContext? = nil
    var body: some View { ReportReaderView(title: title, remote: remote, kind: .pdf, shareName: shareName, summary: summary) }
}

struct FilingWebView: View {
    let title: String
    let remote: URL
    var shareName: String?
    var summary: ReportSummaryContext? = nil
    var body: some View { ReportReaderView(title: title, remote: remote, kind: .filing, shareName: shareName, summary: summary) }
}

struct NewsWebView: View {
    let title: String
    let url: URL
    var body: some View { ReportReaderView(title: title, remote: url, kind: .page) }
}

private struct PDFKitView: UIViewRepresentable {
    let url: URL
    @Binding var jumpTo: Int?

    func makeUIView(context: Context) -> PDFView {
        let v = PDFView()
        v.autoScales = true
        v.displayMode = .singlePageContinuous
        v.displayDirection = .vertical
        v.pageBreakMargins = UIEdgeInsets(top: 8, left: 0, bottom: 8, right: 0)
        v.backgroundColor = UIColor(Theme.background)
        v.document = PDFDocument(url: url)
        return v
    }

    func updateUIView(_ uiView: PDFView, context: Context) {
        guard let index = jumpTo, let page = uiView.document?.page(at: index) else { return }
        // 跳到那一页的顶部
        uiView.go(to: PDFDestination(page: page, at: CGPoint(x: 0, y: page.bounds(for: .cropBox).maxY)))
        DispatchQueue.main.async { jumpTo = nil }
    }
}

/// 目录：一级是正文色、略粗，子级缩进且更淡；右侧小号页码。行紧凑（约 44pt）、分隔线很淡、背景和页面一致。
private struct PDFTocSheet: View {
    let items: [PDFTocItem]
    let onSelect: (Int) -> Void

    var body: some View {
        NavigationStack {
            List(items) { item in
                Button { onSelect(item.pageIndex) } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(item.title)
                            .font(.system(size: item.level == 0 ? 15 : 14, weight: item.level == 0 ? .medium : .regular))
                            .foregroundStyle(item.level == 0 ? Theme.textPrimary : Theme.textSecondary)
                            .multilineTextAlignment(.leading)
                            .lineLimit(2)
                            .padding(.leading, CGFloat(min(item.level, 4)) * 16)
                        Spacer(minLength: 8)
                        Text("\(item.pageIndex + 1)")
                            .font(.system(size: 13)).monospacedDigit()
                            .foregroundStyle(Theme.textSecondary.opacity(0.8))
                    }
                    .padding(.vertical, 11)
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .listRowInsets(EdgeInsets(top: 0, leading: 20, bottom: 0, trailing: 20))
                .listRowBackground(Color.clear)
                .listRowSeparatorTint(Theme.border.opacity(0.5))
            }
            .listStyle(.plain)
            .scrollContentBackground(.hidden)
            .background(Theme.background)
            .navigationTitle(L("目录"))
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

/// 网页（本地缓存文件或在线地址）：顶部有加载进度，加载失败给提示；支持左滑返回。
private struct InAppWebView: View {
    let url: URL
    let local: URL?
    /// 财报网页（SEC 文档）：整页白底、内容顶到屏幕两侧，读起来太满。加载后注入样式：深色底上放一张留边的「纸」。
    let paper: Bool
    @State private var loading = true
    @State private var failed = false

    var body: some View {
        ZStack {
            WebRepresentable(url: url, local: local, paper: paper, loading: $loading, failed: $failed)
            if loading && !failed {
                ProgressView().padding(14).background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
            if failed {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle").font(.largeTitle).foregroundStyle(Theme.textSecondary)
                    Text(L("页面打不开，可能是对方网站限制访问")).font(.subheadline).foregroundStyle(Theme.textPrimary)
                        .multilineTextAlignment(.center)
                }
                .padding().frame(maxWidth: .infinity, maxHeight: .infinity).background(Theme.background)
            }
        }
    }
}

private struct WebRepresentable: UIViewRepresentable {
    let url: URL
    let local: URL?
    let paper: Bool
    @Binding var loading: Bool
    @Binding var failed: Bool

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        if paper {
            let css = "html{background:#0b0e14 !important;} body{background:#fff !important;margin:10px auto !important;" +
                "padding:14px 16px !important;box-sizing:border-box !important;border-radius:10px;" +
                "max-width:calc(100vw - 20px) !important;overflow-x:auto;}"
            let js = "var s=document.createElement('style');s.textContent='\(css)';document.head.appendChild(s);"
            config.userContentController.addUserScript(WKUserScript(source: js, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
        }
        let v = WKWebView(frame: .zero, configuration: config)
        v.navigationDelegate = context.coordinator
        v.allowsBackForwardNavigationGestures = true
        if paper { v.isOpaque = false; v.backgroundColor = UIColor(red: 0.043, green: 0.055, blue: 0.078, alpha: 1) }
        if let local {
            v.loadFileURL(local, allowingReadAccessTo: local.deletingLastPathComponent())
        } else {
            v.load(URLRequest(url: url))
        }
        return v
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate {
        let parent: WebRepresentable
        init(_ parent: WebRepresentable) { self.parent = parent }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { parent.loading = false }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { finish(error) }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { finish(error) }

        private func finish(_ error: Error) {
            parent.loading = false
            // 用户自己取消 / 跳转中断（-999）不算失败
            if (error as NSError).code != NSURLErrorCancelled { parent.failed = true }
        }
    }
}
