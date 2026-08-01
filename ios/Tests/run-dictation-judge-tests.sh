#!/bin/bash
# 听写判定的回归测试。
#
# 项目用 PBXFileSystemSynchronizedRootGroup 组织，手工往 project.pbxproj 里加
# XCTest target 风险大于收益，所以直接用 swiftc 编译**真实源文件** + 断言脚本。
# 测的是线上跑的那份 DictationJudge.swift，不是副本。
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT=$(mktemp -d)/judgetest
swiftc -O \
  "$ROOT/ios/WordLens/Services/DictationJudge.swift" \
  "$ROOT/ios/WordLens/Models/WordModels.swift" \
  "$ROOT/ios/Tests/main.swift" \
  -o "$OUT"
"$OUT"
