# 生产与上传回执

{
  "run_id": "2026-09-08-2327",
  "status": "ready_for_buffer",
  "stage": "uploaded",
  "symbol": "NVDA",
  "video": "/Users/zhangfang/deepalpha-club-ai/marketing/chan/runs/2026-09-08-2327/teaching.mp4",
  "sha256": "69c04270ffdbb12d2741bf1b5b473c987ef2d6c0d2c6a72e18affc923e085088",
  "duration_sec": 24.644717,
  "steps": [
    {
      "step_id": "01",
      "time_sec": 0.0,
      "layers": [],
      "app_action": "关闭所有结构图层",
      "on_screen_text": "NVDA",
      "narration_text": "看NVDA的日线，先关掉图层，只看原始K线。",
      "expected_visual": "真实结果页，图上只有K线和MACD",
      "duration_sec": 5.15483
    },
    {
      "step_id": "02",
      "time_sec": 5.754829999999999,
      "layers": [
        "fractals"
      ],
      "app_action": "打开分型",
      "on_screen_text": "分型",
      "narration_text": "打开分型。红点标记顶分型，绿点标记底分型。",
      "expected_visual": "红绿分型点出现",
      "duration_sec": 5.537959
    },
    {
      "step_id": "03",
      "time_sec": 11.892788999999999,
      "layers": [
        "fractals",
        "strokes"
      ],
      "app_action": "打开笔",
      "on_screen_text": "笔",
      "narration_text": "再打开笔。蓝线连接结构，虚线表示还没有确认。",
      "expected_visual": "分型点保留，蓝色笔和未确认虚线出现",
      "duration_sec": 5.37542
    },
    {
      "step_id": "04",
      "time_sec": 17.868209,
      "layers": [
        "fractals",
        "strokes"
      ],
      "app_action": "停留展示",
      "on_screen_text": "NVDA · 日线",
      "narration_text": "这些是历史结构，不是收益预测。先看懂，再判断。",
      "expected_visual": "保持真实图表供观众对照",
      "duration_sec": 6.176508
    }
  ],
  "checks": {
    "codecs": {
      "video": "h264",
      "audio": "aac"
    },
    "decode": "passed",
    "timeline": "passed",
    "visual_review": "passed",
    "audio_review": "passed",
    "anonymous_head": "passed",
    "anonymous_get_sha256": "passed"
  }
}
