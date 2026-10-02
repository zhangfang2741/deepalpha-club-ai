#!/bin/bash
# 市场状态 × 恐慌贪婪背离提示的纯逻辑测试。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT
swiftc -parse-as-library \
  "$ROOT/ios/DeepAlphaChan/Views/SignalRadar/MacroConsistency.swift" \
  "$ROOT/ios/Tests/MacroConsistencyTests.swift" \
  -o "$TEST_DIR/macro-consistency-tests"
"$TEST_DIR/macro-consistency-tests"
