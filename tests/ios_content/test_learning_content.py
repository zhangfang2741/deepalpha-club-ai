"""iOS 学习内容守护：名词词典 / 新手入门的中英文条目一致，推导里引用的名词都能查到。

内容文件在 ios/DeepAlphaChan/Resources/{zh-Hans,en}.lproj/；推导文件里的 `terms: [...]` 引用词条的稳定中文键，
键必须在 glossary.json（key）或缠论词条索引（LessonModels.swift 的 GlossaryIndex.map）里能查到，否则界面上什么也不显示。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "ios" / "DeepAlphaChan"
RES = ROOT / "Resources"
CATEGORIES = {"market", "fundamental", "structure", "general"}


def _load(lang: str, name: str):
    return json.loads((RES / f"{lang}.lproj" / name).read_text())


def test_glossary_zh_en_have_same_keys_and_valid_fields():
    zh, en = _load("zh-Hans", "glossary.json"), _load("en", "glossary.json")
    assert [e["key"] for e in zh] == [e["key"] for e in en]
    for entry in zh + en:
        assert entry["category"] in CATEGORIES, entry["key"]
        assert entry["term"].strip() and entry["plain"].strip(), entry["key"]
    assert len({e["key"] for e in zh}) == len(zh), "词条键重复"


def test_guide_zh_en_same_ids_and_non_empty():
    zh, en = _load("zh-Hans", "guide.json"), _load("en", "guide.json")
    assert [a["id"] for a in zh] == [a["id"] for a in en]
    for a in zh + en:
        assert a["title"].strip() and a["summary"].strip() and len(a["body"]) > 200, a["id"]


def test_no_trade_words_in_plain_explanations():
    """名词解释不能写成买卖建议（「应该买入」之类）；「买点」「买入」作为术语出现的地方都是定义性的，这里只守最直白的几种。"""
    banned = ["建议买入", "建议卖出", "稳赚", "必涨", "保证收益"]
    for lang, name in (("zh-Hans", "glossary.json"), ("zh-Hans", "guide.json")):
        text = json.dumps(_load(lang, name), ensure_ascii=False)
        for w in banned:
            assert w not in text, f"{name} 出现 {w}"


def test_derivation_terms_resolve():
    keys = {e["key"] for e in _load("zh-Hans", "glossary.json")}
    index_src = (ROOT / "Models" / "LessonModels.swift").read_text()
    lesson_keys = set(re.findall(r'^\s*"([^"]+)":\s*"[a-z-]+",', index_src, re.M))
    known = keys | lesson_keys
    files = [ROOT / "Views" / "SignalRadar" / "MacroDerivations.swift", ROOT / "Views" / "SignalRadar" / "RadarDerivations.swift",
             ROOT / "Views" / "Analysis" / "SignalDerivation.swift"]
    seen = 0
    for f in files:
        for group in re.findall(r"terms:\s*\[([^\]]*)\]", f.read_text()):
            for term in re.findall(r'"([^"]+)"', group):
                seen += 1
                assert term in known, f"{f.name} 引用的名词「{term}」在词典和教程索引里都查不到"
    assert seen > 15


def test_guide_has_product_intro_and_relation():
    for lang in ("zh-Hans", "en"):
        ids = [a["id"] for a in _load(lang, "guide.json")]
        for need in ("guide-app-tour", "guide-app-radar", "guide-app-detail", "guide-relation"):
            assert need in ids, (lang, need)


SCREENSHOT = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)$")


def _screenshots(lang: str, name: str) -> list[tuple[str, str, str]]:
    """正文里单独成段的 `![说明](资源名)`，返回 (文章 id, 说明, 资源名)。"""
    out = []
    for a in _load(lang, name):
        for p in a["body"].split("\n\n"):
            m = SCREENSHOT.match(p.strip())
            if m:
                out.append((a["id"], m.group(1), m.group(2)))
    return out


def test_guide_screenshots_exist_and_match_between_languages():
    """新手入门里的 App 截图：引用的资源都在 Assets 里（中英各一份），中英文插在同样的位置、说明非空。"""
    assets = ROOT / "Resources" / "Assets.xcassets" / "Guide"
    zh, en = _screenshots("zh-Hans", "guide.json"), _screenshots("en", "guide.json")
    assert len(zh) >= 15
    assert [(i, n) for i, _, n in zh] == [(i, n) for i, _, n in en]
    for article, caption, name in zh + en:
        assert caption.strip(), (article, name)
        for asset in (name, f"{name}-en"):
            assert (assets / f"{asset}.imageset" / f"{asset}.jpg").is_file(), f"{article} 引用的截图 {asset} 不存在"
    used = {n for _, _, n in zh}
    unused = {p.name.removesuffix(".imageset").removesuffix("-en") for p in assets.glob("*.imageset")} - used
    assert not unused, f"没有被正文引用的截图：{sorted(unused)}"


def test_no_stale_five_dimension_claims():
    """基本面研究现在是六个维度、按公司阶段加权：界面与学习内容里不能再说「五个维度」「五项取平均」（后端 DIMENSIONS 为准）。"""
    from app.services.quant_research.metrics import DIMENSIONS

    assert len(DIMENSIONS) == 6
    stale = ["五个维度", "五项取平均", "五维成绩单", "五维雷达", "五项各自打分", "Five dimensions", "five dimensions",
             "five-factor", "Five-factor", "The five are averaged"]
    files = [p for p in (ROOT / "Views").rglob("*.swift") if "Moat" not in p.name]
    files += [RES / lang / name for lang in ("zh-Hans.lproj", "en.lproj")
              for name in ("glossary.json", "guide.json", "lessons.json", "Localizable.strings")]
    hits = []
    for f in files:
        text = f.read_text()
        for w in stale:
            if w in text:
                hits.append(f"{f.name}: {w}")
    assert hits == [], f"文案仍写着五维：{hits}"
