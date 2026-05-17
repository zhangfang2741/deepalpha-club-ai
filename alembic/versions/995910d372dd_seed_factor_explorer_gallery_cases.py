# ruff: noqa
"""seed factor explorer gallery cases.

Revision ID: 995910d372dd
Revises: f8b40f61ef5b
Create Date: 2026-05-17 08:16:40.233577
"""

from __future__ import annotations

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "995910d372dd"
down_revision: Union[str, Sequence[str], None] = "f8b40f61ef5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIES = [
    ("momentum", "动量", "🚀", 0),
    ("reversal", "均值回归", "🔄", 1),
    ("volatility", "波动率", "📊", 2),
    ("volume", "量价", "📈", 3),
    ("sentiment", "情绪", "😱", 4),
    ("technical", "技术指标", "📉", 5),
]

CASES = [
    {
        "title": "英伟达 · AI 行情动量",
        "description": "取 60 日累计涨幅，量化 AI 主升浪中的强者恒强效应",
        "category": "momentum",
        "symbol": "NVDA",
        "start": "2024-01-01",
        "end": "2025-05-16",
        "pin_priority": 1,
        "code": """import pandas as pd\nimport numpy as np\n\nclass MomentumSkill(BaseSkill):\n    output_type = \"factor\"\n    def run(self, ctx):\n        prices = ctx.get_price()\n        closes = prices['close'].values\n        lookback = 60\n        factor = pd.Series([None] * len(closes), dtype=float)\n        for i in range(lookback + 5, len(closes)):\n            factor.iloc[i] = closes[i - 5] / closes[i - lookback - 5] - 1.0\n        mean, std = factor.dropna().mean(), factor.dropna().std() or 1.0\n        factor_z = (factor - mean) / std\n        return SkillResult(data=pd.DataFrame({'date': prices['date'], 'value': factor_z}))\n""",
    },
    {
        "title": "贵州茅台 · 均值回归",
        "description": "20 日均线偏离度，捕捉消费龙头的均值回归机会",
        "category": "reversal",
        "symbol": "600519",
        "start": "2023-01-01",
        "end": "2025-05-16",
        "pin_priority": 2,
        "code": """import pandas as pd\nimport numpy as np\n\nclass ReversalSkill(BaseSkill):\n    output_type = \"factor\"\n    def run(self, ctx):\n        prices = ctx.get_price()\n        closes = prices['close']\n        ma20 = closes.rolling(20).mean()\n        deviation = (closes - ma20) / ma20\n        mean, std = deviation.dropna().mean(), deviation.dropna().std() or 1.0\n        factor_z = (deviation - mean) / std\n        return SkillResult(data=pd.DataFrame({'date': prices['date'], 'value': factor_z}))\n""",
    },
    {
        "title": "沪深 300 ETF · 恐慌指数信号",
        "description": "ATR 恐慌指数：波动率突然放大时市场情绪极端",
        "category": "sentiment",
        "symbol": "510300",
        "start": "2023-01-01",
        "end": "2025-05-16",
        "pin_priority": 3,
        "code": """import pandas as pd\nimport numpy as np\n\nclass SentimentSkill(BaseSkill):\n    output_type = \"factor\"\n    def run(self, ctx):\n        prices = ctx.get_price()\n        high, low = prices['high'], prices['low']\n        atr = (high - low).rolling(14).mean()\n        mean, std = atr.dropna().mean(), atr.dropna().std() or 1.0\n        factor_z = (atr - mean) / std\n        return SkillResult(data=pd.DataFrame({'date': prices['date'], 'value': factor_z}))\n""",
    },
    {
        "title": "特斯拉 · 波动率突破",
        "description": "20 日历史波动率，识别波动率压缩后的突破行情",
        "category": "volatility",
        "symbol": "TSLA",
        "start": "2023-01-01",
        "end": "2025-05-16",
        "pin_priority": 4,
        "code": """import pandas as pd\nimport numpy as np\n\nclass VolatilitySkill(BaseSkill):\n    output_type = \"factor\"\n    def run(self, ctx):\n        prices = ctx.get_price()\n        returns = prices['close'].pct_change()\n        vol = returns.rolling(20).std() * (252 ** 0.5)\n        mean, std = vol.dropna().mean(), vol.dropna().std() or 1.0\n        factor_z = (vol - mean) / std\n        return SkillResult(data=pd.DataFrame({'date': prices['date'], 'value': factor_z}))\n""",
    },
    {
        "title": "中国平安 · RSI 极值",
        "description": "14 日 RSI 极端值（>70 超买 / <30 超卖），捕捉情绪拐点",
        "category": "technical",
        "symbol": "601318",
        "start": "2023-01-01",
        "end": "2025-05-16",
        "pin_priority": 5,
        "code": """import pandas as pd\nimport numpy as np\n\nclass RSISkill(BaseSkill):\n    output_type = \"factor\"\n    def run(self, ctx):\n        prices = ctx.get_price()\n        delta = prices['close'].diff()\n        gain = delta.clip(lower=0).rolling(14).mean()\n        loss = (-delta.clip(upper=0)).rolling(14).mean()\n        rs = gain / (loss + 1e-9)\n        rsi = 100 - 100 / (1 + rs)\n        mean, std = rsi.dropna().mean(), rsi.dropna().std() or 1.0\n        factor_z = (rsi - mean) / std\n        return SkillResult(data=pd.DataFrame({'date': prices['date'], 'value': factor_z}))\n""",
    },
    {
        "title": "宁德时代 · 量价背离",
        "description": "成交量与价格涨幅背离度，识别量价背离的主力出货信号",
        "category": "volume",
        "symbol": "300750",
        "start": "2023-01-01",
        "end": "2025-05-16",
        "pin_priority": 6,
        "code": """import pandas as pd\nimport numpy as np\n\nclass VolumeSkill(BaseSkill):\n    output_type = \"factor\"\n    def run(self, ctx):\n        prices = ctx.get_price()\n        price_chg = prices['close'].pct_change(5)\n        vol_chg = prices['volume'].pct_change(5)\n        divergence = price_chg - vol_chg\n        mean, std = divergence.dropna().mean(), divergence.dropna().std() or 1.0\n        factor_z = (divergence - mean) / std\n        return SkillResult(data=pd.DataFrame({'date': prices['date'], 'value': factor_z}))\n""",
    },
]


def upgrade() -> None:
    """插入 6 个精选案例到 factor_skills + factor_categories（owner_id=NULL）。"""
    conn = op.get_bind()
    # 插入 categories
    for name, label, icon, sort_order in CATEGORIES:
        conn.execute(
            sa.text(
                "INSERT INTO factor_categories (name, label, icon, sort_order) "
                "VALUES (:name, :label, :icon, :sort_order) ON CONFLICT DO NOTHING"
            ),
            {"name": name, "label": label, "icon": icon, "sort_order": sort_order},
        )
    # 插入 skills
    for case in CASES:
        conn.execute(
            sa.text(
                """INSERT INTO factor_skills
                   (id, created_at, updated_at, title, description, category, code,
                    default_symbol, default_start_date, default_end_date, default_freq,
                    snapshot_factor_jsonb, narrative_jsonb, is_public, pin_priority)
                   VALUES (:id, NOW(), NOW(), :title, :description, :category, :code,
                           :symbol, :start, :end, 'daily',
                           :snapshot, NULL, false, :pin)
                   ON CONFLICT DO NOTHING"""
            ),
            {
                "id": str(uuid.uuid4()),
                "title": case["title"],
                "description": case["description"],
                "category": case["category"],
                "code": case["code"],
                "symbol": case["symbol"],
                "start": case["start"],
                "end": case["end"],
                "snapshot": json.dumps({}),
                "pin": case["pin_priority"],
            },
        )


def downgrade() -> None:
    """删除 seed 数据。"""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM factor_skills WHERE owner_id IS NULL"))
    conn.execute(sa.text("DELETE FROM factor_categories"))
