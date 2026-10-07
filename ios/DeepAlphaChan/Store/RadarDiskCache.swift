import Foundation

/// 雷达结果的磁盘缓存（Caches/radar）：App 重新打开时先显示上次的结果，再后台静默更新，
/// 不再每次冷启动都从「正在加载」开始。存的是接口原始 JSON；公开的行情数据，不含个人信息。
/// 放 Caches：系统空间紧张时会自己清，清了就退回正常加载。
enum RadarDiskCache {
    /// 超过这么久的磁盘缓存不用（雷达只有 30 天窗口，太旧的快照显示出来反而误导）。
    static let maxAge: TimeInterval = 3 * 24 * 3600

    private static var dir: URL? {
        guard let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first else { return nil }
        let d = base.appendingPathComponent("radar", isDirectory: true)
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        return d
    }

    private static func url(_ key: String) -> URL? {
        let safe = key.map { $0.isLetter || $0.isNumber || $0 == "_" || $0 == "-" ? String($0) : "_" }.joined()
        return dir?.appendingPathComponent(safe + ".json")
    }

    static func write(_ key: String, _ data: Data) {
        guard let u = url(key) else { return }
        try? data.write(to: u, options: .atomic)
    }

    /// 读到 (原始字节, 写入时间)；没有或太旧返回 nil。
    static func read(_ key: String) -> (Data, Date)? {
        guard let u = url(key),
              let attrs = try? FileManager.default.attributesOfItem(atPath: u.path),
              let at = attrs[.modificationDate] as? Date,
              Date().timeIntervalSince(at) < maxAge,
              let data = try? Data(contentsOf: u) else { return nil }
        return (data, at)
    }
}
