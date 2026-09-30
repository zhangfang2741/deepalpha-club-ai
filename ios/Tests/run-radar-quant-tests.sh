#!/bin/bash
# 验证量化字段与旧雷达响应的解码兼容。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT
swiftc -parse-as-library \
  "$ROOT/ios/DeepAlphaChan/Models/SignalRadarModels.swift" \
  "$ROOT/ios/DeepAlphaChan/Models/RadarQuantFilter.swift" \
  "$ROOT/ios/Tests/RadarQuantDecodingTests.swift" \
  -o "$TEST_DIR/radar-quant-tests"
"$TEST_DIR/radar-quant-tests"
