#!/bin/bash
# 图表点按命中几何的回归测试（徽标位置与点击判定同源、多候选取最近）。
# 必须 -Onone：-O 会把 assert 优化掉，测试形同虚设。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT=$(mktemp -d)/charthittest
swiftc -Onone -parse-as-library \
  "$ROOT/ios/DeepAlphaChan/Views/Chart/ChartHitResolver.swift" \
  "$ROOT/ios/Tests/ChartHitResolverTests.swift" \
  -o "$OUT"
"$OUT"
