#!/bin/bash
# 扇区雷达布局（行业角度 / 时间半径 / 每行业名额）的纯逻辑测试。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT
swiftc -parse-as-library \
  "$ROOT/ios/DeepAlphaChan/Views/SignalRadar/SectorRadarLayout.swift" \
  "$ROOT/ios/Tests/SectorRadarLayoutTests.swift" \
  -o "$TEST_DIR/sector-radar-tests"
"$TEST_DIR/sector-radar-tests"
