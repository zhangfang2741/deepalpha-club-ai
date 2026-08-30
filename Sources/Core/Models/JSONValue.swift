import Foundation

/// 轻量 JSON 值树。事件 data 载荷是弱类型字典（形状由事件 type 决定），
/// 解成强类型 struct 太早——reducer 按需取值，与 web 版 Record<string,unknown> 对等。
public enum JSONValue: Codable, Sendable, Equatable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([JSONValue])
    case object([String: JSONValue])

    public func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let v): try c.encode(v)
        case .int(let v): try c.encode(v)
        case .double(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        }
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Int.self) { self = .int(v) }
        else if let v = try? c.decode(Double.self) { self = .double(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else if let v = try? c.decode([String: JSONValue].self) { self = .object(v) }
        else {
            throw DecodingError.dataCorruptedError(
                in: c, debugDescription: "不支持的 JSON 值")
        }
    }

    // ── 便捷访问 ─────────────────────────────────────────────
    public var string: String? { if case .string(let v) = self { v } else { nil } }
    public var int: Int? {
        switch self {
        case .int(let v): v
        case .double(let v): Int(exactly: v)
        default: nil
        }
    }
    public var double: Double? {
        switch self {
        case .int(let v): Double(v)
        case .double(let v): v
        default: nil
        }
    }
    public var bool: Bool? { if case .bool(let v) = self { v } else { nil } }
    public var array: [JSONValue]? { if case .array(let v) = self { v } else { nil } }
    public subscript(key: String) -> JSONValue? {
        if case .object(let o) = self { o[key] } else { nil }
    }

    /// 从弱类型树解码为强类型 struct（如 RunStartedData）。
    public func decode<T: Decodable>(as type: T.Type) -> T? {
        guard let data = try? JSONEncoder().encode(self) else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }
}

// ── 字面量构造（测试与默认值书写方便）─────────────────────────
extension JSONValue: ExpressibleByStringLiteral, ExpressibleByIntegerLiteral,
    ExpressibleByFloatLiteral, ExpressibleByBooleanLiteral, ExpressibleByNilLiteral,
    ExpressibleByArrayLiteral, ExpressibleByDictionaryLiteral {
    public init(stringLiteral v: String) { self = .string(v) }
    public init(integerLiteral v: Int) { self = .int(v) }
    public init(floatLiteral v: Double) { self = .double(v) }
    public init(booleanLiteral v: Bool) { self = .bool(v) }
    public init(nilLiteral: ()) { self = .null }
    public init(arrayLiteral elements: JSONValue...) { self = .array(elements) }
    public init(dictionaryLiteral elements: (String, JSONValue)...) {
        self = .object(Dictionary(elements, uniquingKeysWith: { a, _ in a }))
    }
}
