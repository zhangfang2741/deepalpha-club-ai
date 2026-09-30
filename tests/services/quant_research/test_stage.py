import pytest

from app.services.quant_research.stage import classify_stage, stage_of
from tests.services.quant_research.fixtures import load_inputs


@pytest.mark.parametrize(
    ("cfo", "cfi", "cff", "expected"),
    [
        (-1, -1, 1, "intro"),
        (1, -1, 1, "growth"),
        (1, -1, -1, "mature"),
        (-1, 1, 1, "decline"),
        (-1, 1, -1, "decline"),
        (-1, -1, -1, "shakeout"),
        (1, 1, 1, "shakeout"),
        (1, 1, -1, "shakeout"),
    ],
)
def test_classify(cfo, cfi, cff, expected):
    assert classify_stage(cfo, cfi, cff) == expected


def test_missing_returns_none():
    assert classify_stage(None, -1, 1) is None


def test_fixtures_have_stage():
    info = stage_of(load_inputs("NVDA"))
    assert info is not None
    assert info.operating > 0
    assert info.unprofitable is False
    for s in ("O", "XOM"):
        assert stage_of(load_inputs(s)) is not None


def test_financials_have_no_stage():
    assert stage_of(load_inputs("JPM")) is None
