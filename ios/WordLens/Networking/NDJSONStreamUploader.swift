// Networking/NDJSONStreamUploader.swift
import Foundation

/// 拍照识别专用的流式上传器：跟 `APIClient.postMultipartImage` 一样用
/// `uploadTask(fromFile:)`（保留"临时文件流式写入避免 idle reset"那套防线），
/// 但用 `URLSessionDataDelegate` 边收边读响应体，而不是等 `session.upload(for:fromFile:)`
/// 把整条 NDJSON 流攒完才返回——这样后端每推一条 `partial` 事件，就能在识别还没
/// 全部跑完时立刻回调给上层，替代之前"提交后干等 5~15 秒才看到结果"的体验。
///
/// 最终仍然把完整响应体一起吐出来（`Data`），交给 `NDJSONStreamDecoder.decode`
/// 做和以前完全一样的最终 result/error 解析——这里只负责"边下边看"这一层，
/// 不重复实现流协议本身的语义。
final class NDJSONStreamUploader: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let onPartial: (RecognizeResponse) -> Void
    private var continuation: CheckedContinuation<(Data, URLResponse), Error>?
    private var lineBuffer = Data()
    private var receivedData = Data()
    private var httpResponse: URLResponse?
    private let decoder = JSONDecoder()

    init(onPartial: @escaping (RecognizeResponse) -> Void) {
        self.onPartial = onPartial
    }

    func upload(request: URLRequest, fromFile fileURL: URL, configuration: URLSessionConfiguration) async throws -> (Data, URLResponse) {
        try await withCheckedThrowingContinuation { continuation in
            self.continuation = continuation
            // delegateQueue: nil 让系统给这个 session 分配一个串行后台队列，delegate
            // 回调不会跟主线程抢，也不需要我们自己再包一层线程安全。
            let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
            let task = session.uploadTask(with: request, fromFile: fileURL)
            task.resume()
        }
    }

    func urlSession(
        _ session: URLSession,
        dataTask: URLSessionDataTask,
        didReceive response: URLResponse,
        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
    ) {
        httpResponse = response
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        receivedData.append(data)
        lineBuffer.append(data)

        // NDJSON：按 \n 切行，逐行尝试解析。非 partial 事件（heartbeat/result/error）
        // 留给外层 NDJSONStreamDecoder 在拿到完整 receivedData 后统一处理，这里只挑
        // partial 出来早报。
        while let newlineIndex = lineBuffer.firstIndex(of: 0x0A) {
            let lineData = lineBuffer.subdata(in: lineBuffer.startIndex..<newlineIndex)
            lineBuffer.removeSubrange(lineBuffer.startIndex...newlineIndex)
            guard !lineData.isEmpty,
                  let event = try? decoder.decode(NDJSONStreamEvent<RecognizeResponse>.self, from: lineData),
                  event.type == "partial",
                  let partialData = event.data
            else { continue }
            onPartial(partialData)
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        defer { session.finishTasksAndInvalidate() }
        if let error {
            continuation?.resume(throwing: error)
        } else if let httpResponse {
            continuation?.resume(returning: (receivedData, httpResponse))
        } else {
            continuation?.resume(throwing: URLError(.badServerResponse))
        }
        continuation = nil
    }
}
