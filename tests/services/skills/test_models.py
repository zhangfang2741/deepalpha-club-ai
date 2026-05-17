"""FactorSkill 模型字段测试"""
import pytest
from app.models.factor_skill import FactorSkill
from app.models.factor_run import FactorRun
from app.models.factor_category import FactorCategory


def test_factor_skill_has_required_fields():
    fields = ["id", "title", "description", "category", "code",
              "default_symbol", "default_start_date", "default_end_date",
              "default_freq", "snapshot_factor_jsonb", "narrative_jsonb",
              "is_public", "pin_priority", "owner_id"]
    for f in fields:
        assert hasattr(FactorSkill, f)


def test_factor_run_has_required_fields():
    fields = ["skill_id", "user_id", "symbol", "start_date", "end_date",
              "freq", "factor_jsonb", "narrative_jsonb"]
    for f in fields:
        assert hasattr(FactorRun, f)


def test_factor_category_pk():
    assert hasattr(FactorCategory, "name")
    # name is primary key