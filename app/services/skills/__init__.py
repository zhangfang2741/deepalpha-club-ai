"""skills 服务包——公共 API。"""
from app.services.skills.errors import (
    SkillDataError,
    SkillError,
    SkillSandboxError,
    SkillSyntaxError,
    SkillTimeoutError,
)
from app.services.skills.generator import generate_skill_stream
from app.services.skills.kline import fetch_kline
from app.services.skills.narrator import generate_narrative
from app.services.skills.runner import compute_factor_snapshot

__all__ = [
    "SkillError",
    "SkillSyntaxError",
    "SkillSandboxError",
    "SkillDataError",
    "SkillTimeoutError",
    "generate_skill_stream",
    "fetch_kline",
    "generate_narrative",
    "compute_factor_snapshot",
]