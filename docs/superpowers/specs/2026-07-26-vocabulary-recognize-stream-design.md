# 生词识别流式心跳设计

## 目标

解决拍照识词接口在视觉识别和释义补全期间长时间没有响应数据，导致 Railway 或移动网络中间层中断连接并产生 `NSURLErrorDomain -1005` 的问题。

## 接口设计

- 保留现有 `POST /api/v1/vocabulary/recognize`，确保旧版 App 继续可用。
- 新增 `POST /api/v1/vocabulary/recognize/stream`，请求体与旧接口一致。
- 新接口返回 `application/x-ndjson`。
- 流开始后立即发送心跳，识别未完成时每 5 秒发送一次。
- 成功时发送一条 `result` 事件，内容为原有 `RecognizeResponse`。
- 失败时发送一条 `error` 事件并结束流。

事件示例：

```json
{"type":"heartbeat","stage":"recognizing"}
{"type":"result","data":{"request_id":"...","candidates":[]}}
```

## 客户端设计

- WordLens 改为调用 `/recognize/stream`。
- `URLSessionUploadTask` 持续接收心跳字节，避免连接被判定为空闲。
- 请求完成后按行解析 NDJSON，忽略心跳并返回最终 `result.data`。
- 流中的 `error` 转换为现有 `APIError`，界面错误处理不变。
- 若服务端返回普通 JSON，则沿用原解析逻辑，支持发布期间的版本切换。

## 取消与异常

- 客户端取消请求时，服务端取消仍在运行的识别任务，避免继续消耗模型资源。
- 流开始前的认证、图片为空、图片过大等错误继续使用正常 HTTP 状态码。
- 流开始后的模型异常通过 `error` 事件传递。

## 验证

- 后端单测验证心跳、成功结果和失败事件。
- iOS 完整构建验证 NDJSON 解析和接口调用类型正确。
- 使用支持 NDJSON 的客户端确认响应头和首个心跳能够立即到达。
