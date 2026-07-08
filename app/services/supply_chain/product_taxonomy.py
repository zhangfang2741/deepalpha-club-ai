"""Small deterministic supply-chain product taxonomy."""

import re

_TAXONOMY = {
    "hbm": ("hbm", "高带宽内存", "high bandwidth memory"),
    "wafer_foundry": ("晶圆代工", "芯片代工", "foundry", "wafer fabrication"),
    "lithography": ("光刻", "lithography", "euv"),
    "packaging_test": ("封装", "测试", "packaging", "assembly and test"),
    "cloud": ("cloud", "云计算", "云服务"),
    "rare_earth": ("稀土", "rare earth"),
    "chemicals": ("化学品", "chemical", "photoresist"),
    "airframe": ("机身", "airframe", "fuselage"),
    "storage": ("storage", "存储", "nand", "hard drive"),
}


def normalize_product(product_text: str) -> str:
    """Return a stable category ID for free-text products."""
    value = re.sub(r"\s+", " ", product_text.lower())
    for category, keywords in _TAXONOMY.items():
        if any(keyword in value for keyword in keywords):
            return category
    return "other"
