#!/bin/bash
# 量化研究：后端 golden JSON 解码、五维图标签布局、等级配色。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT
swiftc -parse-as-library \
  "$ROOT/ios/DeepAlphaChan/Models/QuantResearchModels.swift" \
  "$ROOT/ios/DeepAlphaChan/App/Theme.swift" \
  "$ROOT/ios/DeepAlphaChan/Views/Quant/QuantGradeStyle.swift" \
  "$ROOT/ios/DeepAlphaChan/Views/Quant/FiveDimensionChart.swift" \
  "$ROOT/ios/Tests/QuantResearchTests.swift" \
  -o "$TEST_DIR/quant-tests"
"$TEST_DIR/quant-tests" "$ROOT"
