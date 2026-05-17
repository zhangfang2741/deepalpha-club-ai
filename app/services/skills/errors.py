"""Skill 相关统一异常，所有 API 层 catch 后转结构化 JSON"""


class SkillError(Exception):
    code: str = "SKILL_ERROR"


class SkillSyntaxError(SkillError):
    code = "SKILL_SYNTAX_ERROR"


class SkillSandboxError(SkillError):
    code = "SKILL_SANDBOX_ERROR"


class SkillDataError(SkillError):
    code = "SKILL_DATA_ERROR"


class SkillTimeoutError(SkillError):
    code = "SKILL_TIMEOUT"
