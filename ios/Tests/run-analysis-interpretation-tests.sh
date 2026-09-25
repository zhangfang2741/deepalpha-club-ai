#!/bin/bash
# 使用真实源文件检查颜色语义、风险归并及观察条件的表述边界。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEST_DIR=$(mktemp -d)
trap 'rm -rf "$TEST_DIR"' EXIT
swiftc \
  "$ROOT/ios/DeepAlphaChan/Models/ChanModels.swift" \
  "$ROOT/ios/DeepAlphaChan/App/Theme.swift" \
  "$ROOT/ios/DeepAlphaChan/Views/Analysis/SignalFormatting.swift" \
  "$ROOT/ios/DeepAlphaChan/Views/Analysis/HeadlineHighlighter.swift" \
  "$ROOT/ios/DeepAlphaChan/Views/Analysis/AnalysisInterpretation.swift" \
  "$ROOT/ios/Tests/AnalysisInterpretationTests.swift" \
  -o "$TEST_DIR/analysis-tests"
"$TEST_DIR/analysis-tests"
