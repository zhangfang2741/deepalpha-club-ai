# 生产与上传回执

{
  "run_id": "2026-09-12-0910",
  "status": "ready_for_buffer",
  "stage": "uploaded",
  "symbol": "PLTR",
  "video": "/Users/zhangfang/deepalpha-club-ai/marketing/chan/runs/2026-09-12-0910/teaching.mp4",
  "sha256": "1106d8c0898c73ec73b191242861efd4db131e2ba3c5ca71220e1df35f90e435",
  "duration_sec": 36.289525,
  "steps": [
    {
      "step_id": "01",
      "time_sec": 0.0,
      "layers": [],
      "app_action": "展示 PLTR 原始日线",
      "on_screen_text": "PLTR · 事件 K 线就是信号？",
      "narration_text": "Palantir刚办完AIPCon。PLTR一根事件K线，就算结构信号吗？",
      "expected_visual": "真实 PLTR 日线结果页，结构图层全部关闭",
      "overlay_text": "AIPCon 刚结束\n一根 K 线就是信号？",
      "duration_sec": 7.372336
    },
    {
      "step_id": "02",
      "time_sec": 7.972335999999999,
      "layers": [
        "fractals"
      ],
      "app_action": "打开分型核对局部拐点",
      "on_screen_text": "先看局部拐点是否确认",
      "narration_text": "不是。先打开分型，看局部拐点有没有经过后续K线确认。单根波动不能替代结构确认。",
      "expected_visual": "红绿分型标记出现，其他结构图层关闭",
      "overlay_text": "第一步：分型确认了吗？",
      "duration_sec": 9.206712
    },
    {
      "step_id": "03",
      "time_sec": 17.779048,
      "layers": [
        "fractals",
        "strokes"
      ],
      "app_action": "叠加笔核对结构连接",
      "on_screen_text": "再看拐点能否连接成笔",
      "narration_text": "再叠加笔，确认这些拐点能不能连接成完整结构。虚线末端仍可能变化。",
      "expected_visual": "分型标记与蓝色笔同时显示",
      "overlay_text": "第二步：能连成确认的笔吗？",
      "duration_sec": 7.372336
    },
    {
      "step_id": "04",
      "time_sec": 25.751383999999998,
      "layers": [
        "strokes"
      ],
      "app_action": "关闭分型只保留笔并停留",
      "on_screen_text": "App Store 搜索 DeepAlpha 缠论",
      "narration_text": "关掉分型，只保留笔再核对一次。想自己拆解事件K线，App Store搜索DeepAlpha缠论。",
      "expected_visual": "分型消失、蓝色笔保留，DeepAlpha 缠论下载引导清晰显示",
      "overlay_text": "App Store 搜索\nDeepAlpha 缠论",
      "duration_sec": 9.938141
    }
  ],
  "checks": {
    "codecs": {
      "video": "h264",
      "audio": "aac"
    },
    "decode": "passed",
    "timeline": "passed",
    "platform_safe_zone": {
      "canvas": "720x1280",
      "content_rect": {
        "x": 36,
        "y": 96,
        "width": 564,
        "height": 924
      },
      "reserved": {
        "right": 120,
        "bottom": 260
      },
      "status": "awaiting_visual_review"
    },
    "visual_review": "passed",
    "audio_review": "passed",
    "anonymous_head": "passed",
    "anonymous_get_sha256": "passed"
  }
}
