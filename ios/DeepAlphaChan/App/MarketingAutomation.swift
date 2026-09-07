#if DEBUG && targetEnvironment(simulator)
import Foundation

/// 仅模拟器 Debug 包启用的运营接口桥接；凭证始终留在 App Keychain 中。
@MainActor
enum MarketingAutomation {
    static let directory = URL.documentsDirectory.appending(path: "marketing")

    static func runRequest() async {
        guard ProcessInfo.processInfo.arguments.contains("-marketingRequest") else { return }
        do {
            let input = try Data(contentsOf: directory.appending(path: "request.json"))
            let object = try JSONSerialization.jsonObject(with: input) as? [String: String]
            guard let object, let operation = object["operation"],
                  let token = await APIClient.shared.marketingToken() else {
                throw APIError(message: "运营请求无效或模拟器尚未登录", statusCode: nil)
            }
            var request: URLRequest
            if operation == "analysis" {
                var url = URLComponents(url: AppConfig.baseURL.appending(path: "/api/v1/chan/analysis"),
                                        resolvingAgainstBaseURL: false)!
                url.queryItems = ["symbol", "start_date", "end_date", "freq", "lang"].compactMap { key in
                    object[key].map { URLQueryItem(name: key, value: $0) }
                }
                request = URLRequest(url: url.url!)
            } else if operation == "upload" {
                let video = try Data(contentsOf: directory.appending(path: "upload.mp4"))
                let boundary = UUID().uuidString
                request = URLRequest(url: AppConfig.baseURL.appending(path: "/api/v1/media/upload"))
                request.httpMethod = "POST"
                request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
                var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"teaching.mp4\"\r\nContent-Type: video/mp4\r\n\r\n".utf8)
                body.append(video)
                body.append(Data("\r\n--\(boundary)--\r\n".utf8))
                request.httpBody = body
            } else {
                throw APIError(message: "不支持的运营操作", statusCode: nil)
            }
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            request.timeoutInterval = 90
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                throw APIError(message: "运营接口失败：\((response as? HTTPURLResponse)?.statusCode ?? 0)", statusCode: nil)
            }
            try data.write(to: directory.appending(path: "response.json"), options: .atomic)
        } catch {
            try? Data(error.localizedDescription.utf8).write(to: directory.appending(path: "error.txt"), options: .atomic)
        }
    }

    /// 读取同一份脚本，在真实结果页切换图层；由主机开始录屏后写入开始信号。
    static func playback(vm: ChanViewModel) async {
        guard ProcessInfo.processInfo.arguments.contains("-marketingPlayback") else { return }
        do {
            let data = try Data(contentsOf: directory.appending(path: "playback.json"))
            let steps = try JSONDecoder().decode([MarketingStep].self, from: data)
            guard !steps.isEmpty else { throw APIError(message: "录制脚本为空", statusCode: nil) }
            vm.showFractals = false
            vm.showStrokes = false
            vm.showSegments = false
            vm.showPivots = false
            vm.showSignals = false
            try await Task.sleep(for: .seconds(1))
            try Data("ready".utf8).write(to: directory.appending(path: "ready"), options: .atomic)
            let deadline = Date.now.addingTimeInterval(60)
            while !FileManager.default.fileExists(atPath: directory.appending(path: "start").path) {
                guard Date.now < deadline else { throw APIError(message: "未收到录屏开始信号", statusCode: nil) }
                try await Task.sleep(for: .milliseconds(100))
            }
            let start = Date.now
            var events: [[String: Any]] = []
            for step in steps {
                let remaining = step.time_sec - Date.now.timeIntervalSince(start)
                if remaining > 0 { try await Task.sleep(for: .seconds(remaining)) }
                vm.showFractals = step.layers.contains("fractals")
                vm.showStrokes = step.layers.contains("strokes")
                vm.showPivots = step.layers.contains("pivots")
                vm.showSegments = step.layers.contains("segments")
                vm.showSignals = step.layers.contains("signals")
                events.append(["step_id": step.step_id, "actual_time_sec": Date.now.timeIntervalSince(start), "layers": step.layers])
                let eventData = try JSONSerialization.data(withJSONObject: events, options: .prettyPrinted)
                try eventData.write(to: directory.appending(path: "events.json"), options: .atomic)
            }
        } catch {
            try? Data(error.localizedDescription.utf8).write(to: directory.appending(path: "error.txt"), options: .atomic)
        }
    }
}
#endif
