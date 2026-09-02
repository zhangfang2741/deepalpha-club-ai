#!/bin/bash
# 编译检查。命令行等价于 Xcode 的 Cmd+B，供自动化流程与 CI 使用。
#
# 只编译不运行：App 需要登录与网络，跑起来验证的部分在计划里单列为真机步骤。
#
# pipefail 不可省：默认情况下 pipeline 的退出码取自 tail，xcodebuild 编译失败会被
# 吞成 0，脚本反而「成功」。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

xcodebuild \
  -project "$ROOT/ios/DeepAlphaChan.xcodeproj" \
  -scheme DeepAlphaChan \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -configuration Debug \
  build 2>&1 | tail -40
