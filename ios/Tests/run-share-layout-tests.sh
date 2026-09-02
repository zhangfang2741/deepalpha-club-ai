#!/bin/bash
# 分享图几何计算的回归测试。
#
# 同 run-dictation-judge-tests.sh：工程没有 XCTest target，直接用 swiftc 编译
# **真实源文件** + 断言脚本。ShareLayout 刻意不依赖 UIKit，就是为了能在这里跑。
set -e
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT=$(mktemp -d)/sharelayouttest
swiftc -O \
  "$ROOT/ios/DeepAlphaChan/Share/ShareLayout.swift" \
  "$ROOT/ios/Tests/ShareLayoutTests.swift" \
  -o "$OUT"
"$OUT"
