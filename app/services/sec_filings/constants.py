"""SEC filing 分类常量：表格类型 → 业务分类，以及 8-K item 代码中文释义。

分类策略（保证正确性优先）：按 form type 归入 7 大类，每类给中文标签。
匹配用「有序规则」——从上到下第一个命中的规则决定分类，避免歧义。
"""

# 7 大分类：key -> (中文标签, 展示顺序)
CATEGORIES: dict[str, dict] = {
    "financials": {"label": "财报", "label_en": "Financial Reports", "order": 1},
    "material_events": {"label": "重大事件 (8-K)", "label_en": "Material Events", "order": 2},
    "insider": {"label": "内部人交易", "label_en": "Insider Transactions", "order": 3},
    "ownership": {"label": "大股东与机构持仓", "label_en": "Ownership", "order": 4},
    "proxy": {"label": "股东会与代理", "label_en": "Proxy", "order": 5},
    "registration": {"label": "注册与发行", "label_en": "Registration & Offerings", "order": 6},
    "other": {"label": "其他", "label_en": "Other", "order": 7},
}

# 分类规则：(判定函数, 分类 key)。按顺序匹配，第一个命中即返回。
# 注意顺序——特殊类（13/14A/S-）要在通用兜底前。
def _norm(form: str) -> str:
    return form.strip().upper()


def classify_form(form: str) -> str:
    """将 SEC form type 归入 7 大分类之一。"""
    f = _norm(form)

    # 财报：定期报告（含修订 /A 与外国私人发行人表格）
    if f.startswith(("10-K", "10-Q", "20-F", "40-F", "11-K", "ARS")):
        return "financials"
    if f in ("6-K", "6-K/A"):
        return "financials"
    if f.startswith(("NT 10-K", "NT 10-Q", "NT 20-F")):  # 延迟提交通知
        return "financials"

    # 重大事件 8-K
    if f.startswith("8-K"):
        return "material_events"

    # 内部人交易：Form 3/4/5（及修订）与 Form 144
    if f in ("3", "4", "5", "3/A", "4/A", "5/A"):
        return "insider"
    if f.startswith("144"):
        return "insider"

    # 大股东与机构持仓：13D / 13G / 13F / SC TO / SC 13E
    if "13D" in f or "13G" in f or "13F" in f or f.startswith(("SC TO", "SC 13E", "SC14D", "SC 14D")):
        return "ownership"

    # 股东会与代理：所有 14A 系列
    if "14A" in f:
        return "proxy"

    # 注册与发行：S-*/F-* 招股、424 定价、FWP、8-A 上市登记、POS AM
    if f.startswith(("S-", "F-", "424", "FWP", "8-A", "POS AM", "N-", "SF-")):
        return "registration"

    return "other"


# 8-K item 代码 -> 中文释义（覆盖常见项，未知代码原样透传）
EIGHT_K_ITEMS: dict[str, str] = {
    "1.01": "订立重大协议",
    "1.02": "终止重大协议",
    "1.03": "破产或接管",
    "1.04": "矿山安全事故",
    "2.01": "完成资产收购或处置",
    "2.02": "业绩与经营成果（财报发布）",
    "2.03": "产生重大直接财务义务",
    "2.04": "触发财务义务加速到期",
    "2.05": "退出或处置成本承诺",
    "2.06": "重大资产减值",
    "3.01": "退市通知或不符合上市规则",
    "3.02": "未登记的股权发行",
    "3.03": "证券持有人权利变更",
    "4.01": "会计师事务所变更",
    "4.02": "已发布财报不可依赖",
    "5.01": "控制权变更",
    "5.02": "董事或高管变动",
    "5.03": "章程或细则修订",
    "5.04": "员工福利计划暂停交易",
    "5.05": "道德准则变更或豁免",
    "5.06": "空壳公司状态变更",
    "5.07": "股东投票结果",
    "5.08": "股东提名事项",
    "6.01": "ABS 信息披露",
    "7.01": "Regulation FD 披露",
    "8.01": "其他重大事件",
    "9.01": "财务报表与附件",
}


def describe_8k_items(items_raw: str) -> list[dict]:
    """将 8-K 的 items 字段（如 '2.02,9.01'）解析为 [{code, label}] 列表。"""
    if not items_raw:
        return []
    result = []
    for code in items_raw.split(","):
        code = code.strip()
        if not code:
            continue
        result.append({"code": code, "label": EIGHT_K_ITEMS.get(code, "")})
    return result
