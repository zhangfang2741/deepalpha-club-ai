"""Supplier alias normalization."""

import re

ALIASES = {
    "foxconn": "Hon Hai Precision Industry",
    "富士康": "Hon Hai Precision Industry",
    "hon hai": "Hon Hai Precision Industry",
    "tsmc": "Taiwan Semiconductor Manufacturing",
    "台积电": "Taiwan Semiconductor Manufacturing",
    "aws": "Amazon Web Services",
}


def normalize_alias(name: str) -> str:
    """Map common aliases to a stable canonical name."""
    cleaned = re.sub(r"\s+", " ", name.strip())
    key = cleaned.lower().removesuffix(" inc.").removesuffix(" inc").removesuffix(" corp.")
    return ALIASES.get(key, cleaned)
