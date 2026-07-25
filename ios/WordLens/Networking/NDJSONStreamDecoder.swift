import Foundation

enum NDJSONStreamDecodeError: LocalizedError {
    case server(String)
    case invalidResponse
    case missingResult

    var errorDescription: String? {
        switch self {
        case .server(let message):
            message
        case .invalidResponse:
            "识别响应格式异常，请重试"
        case .missingResult:
            "识别连接提前结束，请重试"
        }
    }
}

enum NDJSONStreamDecoder {
    static func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        let decoder = JSONDecoder()

        for line in data.split(separator: 0x0A) {
            let event: NDJSONStreamEvent<T>
            do {
                event = try decoder.decode(NDJSONStreamEvent<T>.self, from: Data(line))
            } catch {
                throw NDJSONStreamDecodeError.invalidResponse
            }

            switch event.type {
            case "result":
                guard let result = event.data else {
                    throw NDJSONStreamDecodeError.invalidResponse
                }
                return result
            case "error":
                throw NDJSONStreamDecodeError.server(event.message ?? "识别失败，请重试")
            default:
                continue
            }
        }

        throw NDJSONStreamDecodeError.missingResult
    }
}

private struct NDJSONStreamEvent<T: Decodable>: Decodable {
    let type: String
    let data: T?
    let message: String?
}
