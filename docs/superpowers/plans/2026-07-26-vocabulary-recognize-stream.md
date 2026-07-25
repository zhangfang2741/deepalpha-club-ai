# Vocabulary Recognition Streaming Heartbeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为拍照识词增加 NDJSON 心跳流，防止长时间无响应引发 `-1005` 连接中断。

**Architecture:** 保留旧同步接口并新增流式接口。后端用异步生成器定期输出心跳，iOS 上传完成后解析 NDJSON 最终事件，同时兼容普通 JSON 响应。

**Tech Stack:** FastAPI `StreamingResponse`、Python `asyncio`、Swift `URLSessionUploadTask`、Codable。

## Global Constraints

- 所有 Python import 位于文件顶部。
- 后端日志使用 structlog 的 lowercase_with_underscores 事件名。
- 不改变旧 `/recognize` 接口响应格式。
- 不引入第三方依赖。

---

### Task 1: 后端流协议

**Files:**
- Modify: `app/schemas/vocabulary.py`
- Modify: `app/api/v1/vocabulary/words.py`
- Test: `tests/services/vocabulary/test_recognize_stream.py`

**Interfaces:**
- Produces: `POST /recognize/stream`，返回 NDJSON 的 `heartbeat`、`result` 或 `error` 事件。

- [ ] 写失败测试，验证慢任务在完成前输出至少一条心跳。
- [ ] 运行测试并确认因流生成器不存在而失败。
- [ ] 实现事件模型、异步生成器和新路由。
- [ ] 运行测试并确认心跳、结果、错误场景通过。

### Task 2: iOS NDJSON 解析

**Files:**
- Modify: `ios/WordLens/Networking/APIClient.swift`
- Modify: `ios/WordLens/Networking/WordService.swift`

**Interfaces:**
- Consumes: `/recognize/stream` NDJSON 响应。
- Produces: 现有 `RecognizeResponse`，调用方无需变化。

- [ ] 增加私有 NDJSON 事件解码模型和解析函数。
- [ ] 将识别请求切换到 `/recognize/stream`。
- [ ] 保留普通 JSON 响应兼容路径。
- [ ] 构建 WordLens 并确认编译通过。

### Task 3: 综合验证

**Files:**
- Verify: `app/api/v1/vocabulary/words.py`
- Verify: `ios/WordLens/Networking/APIClient.swift`

- [ ] 运行后端相关测试。
- [ ] 运行 `git diff --check`。
- [ ] 运行 iPhone 17 模拟器完整构建。
