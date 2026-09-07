# 选题回执（演示）

{
  "run_id": "2026-09-06-claude-demo",
  "mode": "demo_test",
  "date": "2026-09-06",
  "data_time": "分析接口拉取截止 2026-09-04 收盘（周五，最新交易日；09-05/09-06 休市）",
  "auth_method": "CHAN_DEMO_ACCOUNT 通过 /api/v1/auth/login 直接登录取 token，未使用模拟器桥接",
  "signal_basis": {
    "NVDA": {
      "confirmed_fractals_recent": 8,
      "strokes": 25,
      "eligible": true,
      "source": "https://api.deepalpha.club/api/v1/chan/analysis"
    },
    "AAPL": {
      "confirmed_fractals_recent": 8,
      "strokes": 17,
      "eligible": true,
      "source": "https://api.deepalpha.club/api/v1/chan/analysis"
    },
    "TSLA": {
      "confirmed_fractals_recent": 8,
      "strokes": 19,
      "eligible": true,
      "source": "https://api.deepalpha.club/api/v1/chan/analysis"
    }
  },
  "selected": "NVDA",
  "selection_rule": "候选顺序 NVDA/AAPL/TSLA 中第一个满足 >=3 已确认分型且 >=3 笔 的标的",
  "status": "success",
  "note": "本次为演示性质的功能验证运行（用户要求先跑通流程看效果），不是当日 09:00 正式档期；今日两频道此前已各发布 3 次，未触及重复发布。"
}
