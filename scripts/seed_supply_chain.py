"""为产业因果图谱注入 NVIDIA AI 产业链种子数据（命令行入口）。

数据与注入逻辑统一定义在 app.services.graph.seed，应用启动时也会自动调用。
本脚本仅供手动执行 / 演练。

用法::

    uv run python scripts/seed_supply_chain.py --dry-run    # 只打印，不写库
    uv run python scripts/seed_supply_chain.py --with-data  # 写入数据库（图谱已有数据时跳过）
    uv run python scripts/seed_supply_chain.py --force      # 强制补齐缺失的种子实体与事实
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def main() -> None:
    """解析参数并幂等写入种子数据。"""
    from sqlmodel import Session

    from app.db.session import sync_engine
    from app.services.graph.seed import ENTITIES, FACTS, seed_supply_chain_graph

    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    with_data = "--with-data" in sys.argv or force

    if not dry_run and not with_data:
        print("用法: --dry-run | --with-data | --force")
        sys.exit(1)

    print(f"准备写入 {len(ENTITIES)} 个实体、{len(FACTS)} 条事实")
    if dry_run:
        for name, etype, ticker, _desc in ENTITIES:
            print(f"  [实体] {etype:10s} {name}" + (f" ({ticker})" if ticker else ""))
        for src, rel, tgt, _ev, conf, _t in FACTS:
            print(f"  [事实] {src} --{rel}--> {tgt}  (conf={conf})")
        print("[dry-run] 未写入数据库。")
        return

    with Session(sync_engine) as session:
        created_entities, created_facts = seed_supply_chain_graph(session, force=force)

    if created_entities == 0 and created_facts == 0:
        print("图谱已有数据（或种子已存在），未新增。可加 --force 强制补齐。")
    else:
        print(f"完成：新增 {created_entities} 个实体、{created_facts} 条事实。")


if __name__ == "__main__":
    main()
