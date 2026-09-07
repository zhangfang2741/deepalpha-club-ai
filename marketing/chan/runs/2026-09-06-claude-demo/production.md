# 生产回执（演示运行）

{
  "run_id": "2026-09-06-claude-demo",
  "status": "awaiting_review",
  "stage": "review",
  "symbol": "NVDA",
  "video": "/sessions/rcw-01v9mtmazxyc4zejendnacgj/mnt/deepalpha-club-ai/marketing/chan/runs/2026-09-06-claude-demo/teaching.mp4",
  "sha256": "42d3e6a01000d52903a09ee7aebc63f3c836dc030032a764819452136581a12f",
  "duration_sec": 38.834,
  "steps": [
    {
      "step_id": "01",
      "time_sec": 0.0,
      "duration_sec": 7.889,
      "app_action": "真实截图开场，镜头缓慢推近",
      "on_screen_text": "NVDA · 日线",
      "narration_text": "打开缠论分析，当前是英伟达日线图，最新收盘二百三十点三六。",
      "expected_visual": "真实App截图：NVDA日线K线图与MACD"
    },
    {
      "step_id": "02",
      "time_sec": 8.489,
      "duration_sec": 9.509,
      "app_action": "镜头停留于分型标注区域",
      "on_screen_text": "分型",
      "narration_text": "红点和绿点是分型。红色是顶分型，绿色是底分型，标记出局部高低点。",
      "expected_visual": "红/绿分型点清晰可见"
    },
    {
      "step_id": "03",
      "time_sec": 18.598,
      "duration_sec": 11.546,
      "app_action": "镜头移向线段/中枢/买卖点标注",
      "on_screen_text": "线段 · 中枢 · 买卖点",
      "narration_text": "蓝色的线是笔，把相邻分型连起来；橙色线段和紫色中枢框标出更大级别的结构，图上还标了一买、一卖两个点。",
      "expected_visual": "蓝色笔、橙色线段、紫色中枢虚线框、一买/一卖气泡"
    },
    {
      "step_id": "04",
      "time_sec": 30.744,
      "duration_sec": 8.098,
      "app_action": "镜头停留，画面不再变化",
      "on_screen_text": "仅供学习",
      "narration_text": "这些都是历史结构标注，不是买卖建议，看不懂图上的线，先去学习页读两分钟。",
      "expected_visual": "保持同一真实截图供观众对照"
    }
  ],
  "asset_source": "真实模拟器截图（非连续录屏）：由 Claude 通过 computer-use 直接操作 Xcode Simulator 打开 App 并截取，非历史素材、非伪造；简历器录屏功能本身仍不可用",
  "checks": {
    "codecs": {
      "video": "h264",
      "audio": "aac"
    },
    "decode": "passed",
    "duration_range_20_45s": "passed",
    "visual_review": "passed（人工核对 frame-1/13/24/34.jpg 与文案对应，镜头持续缓慢推近）",
    "audio_review": "passed（MiniMax 真实合成，4 段时长 7.89/9.51/11.55/8.10 秒，无静音/截断）",
    "layer_toggle_alignment": "not_applicable（静态截图+运镜方案，无模拟器分层切换事件可比对，以人工画面核对代替）"
  },
  "method_change": "选题阶段改为直接调用 /api/v1/auth/login + /api/v1/chan/analysis（不经模拟器桥接）；制作阶段改为 Xcode Simulator 真实截图（computer-use 采集）+ ffmpeg 运镜与混音，不使用模拟器连续录屏"
}
