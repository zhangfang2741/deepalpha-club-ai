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


# form type -> (中文名, 解释)。覆盖常见表格；未知表格返回空。
# 修订版（/A 后缀）自动追加「（修订）」，无需单列。
FORM_INFO: dict[str, tuple[str, str]] = {
    # 定期财报
    "10-K": ("年报", "美国公司年度报告，含经审计的完整财务报表、业务与风险披露，一年一份。"),
    "10-Q": ("季报", "美国公司季度报告，含未经审计的财务数据，前三个季度各一份。"),
    "20-F": ("外国公司年报", "外国私人发行人的年度报告，相当于外国公司版的 10-K。"),
    "40-F": ("加拿大公司年报", "符合 MJDS 的加拿大公司年度报告。"),
    "6-K": ("外国公司临时报告", "外国私人发行人提交的当期重大信息，相当于外国公司版的 8-K。"),
    "11-K": ("员工持股计划年报", "员工持股/401(k) 等福利计划的年度报告。"),
    "ARS": ("股东年度报告", "发给股东的年度报告（图文版），常与 10-K 同期。"),
    "NT 10-K": ("年报延迟通知", "无法按时提交 10-K 的通知（Form 12b-25）。"),
    "NT 10-Q": ("季报延迟通知", "无法按时提交 10-Q 的通知（Form 12b-25）。"),
    # 重大事件
    "8-K": ("重大事件报告", "发生重大事件时的临时报告（如财报发布、高管变动、并购），随时提交。"),
    # 内部人交易
    "3": ("内部人初始持股申报", "董事、高管或大股东首次申报其持股（Form 3）。"),
    "4": ("内部人持股变动", "内部人买卖公司股票后 2 个工作日内申报（Form 4），最常见的内部人交易信号。"),
    "5": ("内部人年度持股申报", "内部人年度汇总申报，补充未及时报告的交易（Form 5）。"),
    "144": ("受限股拟出售通知", "关联人拟出售受限证券的通知（Rule 144）。"),
    # 大股东与机构持仓
    "SC 13D": ("大股东持股申报(主动)", "持股超 5% 且有意影响公司控制权的投资者申报。"),
    "SC 13G": ("大股东持股申报(被动)", "持股超 5% 的被动投资者简式申报（无控制意图）。"),
    "SC 13E3": ("私有化交易申报", "关联方发起的私有化（going-private）交易披露。"),
    "13F-HR": ("机构持仓报告", "管理资产超 1 亿美元的机构每季度披露其美股持仓。"),
    "13F-NT": ("机构持仓通知", "持仓已由其他机构代为申报的通知。"),
    "SC TO-I": ("发行人要约收购", "公司回购自身股票的要约收购申报。"),
    "SC TO-T": ("第三方要约收购", "第三方对目标公司发起的要约收购申报。"),
    "SC 14D9": ("目标公司回应声明", "被收购公司对要约收购的立场声明。"),
    # 股东会与代理
    "DEF 14A": ("股东大会委托书", "正式的股东大会委托征集材料（代理声明），含董事选举、高管薪酬、股东提案等。"),
    "DEFA14A": ("补充委托材料", "对已发布委托书的补充或附加材料。"),
    "DEFM14A": ("并购股东委托书", "涉及并购等重大事项表决的委托书。"),
    "PRE 14A": ("委托书预备稿", "正式委托书发布前提交给 SEC 的初稿。"),
    "DEFR14A": ("委托书修订稿", "对已发布委托书的修订版本。"),
    "PX14A6G": ("股东提案函", "股东就投票议案对外发出的征集/说明函。"),
    "DEFC14A": ("争议性委托书", "存在代理权争夺时的委托征集材料。"),
    # 注册与发行
    "S-1": ("证券注册书(IPO)", "证券首次公开发行的注册登记书，常见于 IPO。"),
    "S-3": ("简式证券注册书", "符合条件公司的简化注册书，用于后续增发。"),
    "S-4": ("并购证券注册书", "并购或换股交易中发行证券的注册书。"),
    "S-8": ("员工股权注册书", "为员工股权激励计划注册发行的证券。"),
    "S-11": ("房地产证券注册书", "房地产公司/REIT 的证券注册书。"),
    "F-1": ("外国公司注册书", "外国私人发行人的证券注册书（相当于外国版 S-1）。"),
    "F-3": ("外国公司简式注册书", "符合条件外国发行人的简化注册书。"),
    "424B1": ("最终招股说明书", "证券发行的最终定价招股说明书。"),
    "424B2": ("招股说明书(定价)", "含发行定价信息的招股说明书补充。"),
    "424B3": ("招股说明书补充", "对已生效注册书的招股说明书补充。"),
    "424B4": ("最终招股说明书", "IPO/增发的最终招股说明书。"),
    "424B5": ("招股说明书(增发)", "后续发行的定价招股说明书补充。"),
    "FWP": ("自由书写宣传材料", "发行过程中使用的补充性宣传/说明材料（Free Writing Prospectus）。"),
    "8-A12B": ("证券上市登记", "证券在交易所上市登记（Section 12(b)）。"),
    "POS AM": ("生效后修订", "注册书生效后的修订（Post-Effective Amendment）。"),
    "EFFECT": ("注册生效通知", "SEC 宣布注册书生效的通知。"),
    # 其他常见
    "SD": ("冲突矿产披露", "关于冲突矿产来源的专项披露（Specialized Disclosure）。"),
    "NO ACT": ("无异议函", "SEC 就某事项出具的 no-action letter 往来。"),
    "CORRESP": ("与SEC往来函件", "公司与 SEC 审核人员之间的通信。"),
    "UPLOAD": ("SEC审核意见函", "SEC 上传的审核意见/问询函。"),
    "CERT": ("交易所上市证明", "交易所出具的证券上市认证。"),
    "25-NSE": ("退市通知", "证券从交易所退市的通知。"),
    "SC 13D/A": ("大股东持股变更(主动)", "SC 13D 的更新申报。"),
}

# 仅前缀即可判定中文名的兜底（覆盖 424B* 等系列，未被精确命中时用）
_FORM_PREFIX_INFO: list[tuple[str, tuple[str, str]]] = [
    ("424B", ("招股说明书", "证券发行的招股说明书补充（含定价等信息）。")),
    ("424A", ("招股说明书(初步)", "发行前的初步招股说明书补充。")),
    ("13F", ("机构持仓报告", "机构投资者的季度美股持仓披露。")),
    ("NT 10-K", ("年报延迟通知", "无法按时提交年报的通知（Form 12b-25）。")),
    ("NT 10-Q", ("季报延迟通知", "无法按时提交季报的通知（Form 12b-25）。")),
    ("NT ", ("延迟提交通知", "无法按时提交定期报告的通知（Form 12b-25）。")),
    # 定期报告变体：10-K405 / 10-KSB / 10-QSB 等旧版或小企业版
    ("10-K", ("年报", "美国公司年度报告，含经审计的完整财务报表（含 10-K405 等历史变体）。")),
    ("10-Q", ("季报", "美国公司季度报告，含未经审计的财务数据（含 10-QSB 等历史变体）。")),
    ("8-K", ("重大事件报告", "发生重大事件时的临时报告，随时提交。")),
    ("SC 13D", ("大股东持股申报(主动)", "持股超 5% 且有意影响控制权的投资者申报。")),
    ("SC 13G", ("大股东持股申报(被动)", "持股超 5% 的被动投资者简式申报。")),
    ("SC TO", ("要约收购申报", "要约收购（tender offer）相关申报。")),
    ("DEF ", ("股东会委托材料", "股东大会的委托征集材料（代理声明）。")),
    ("PRE ", ("委托材料预备稿", "正式委托材料发布前的初稿。")),
    ("S-", ("证券注册书", "向 SEC 提交的证券发行注册登记文件。")),
    ("F-", ("外国公司注册书", "外国私人发行人的证券注册登记文件。")),
]


def describe_form(form: str) -> dict:
    """返回 {name, desc}：form 的中文名与解释；未知表格 name/desc 为空。"""
    f = form.strip().upper()

    # 修订版 /A：查基表格，名称追加「（修订）」
    suffix = ""
    base = f
    if f.endswith("/A"):
        base = f[:-2].strip()
        suffix = "（修订）"

    info = FORM_INFO.get(f) or FORM_INFO.get(base)
    if info:
        name, desc = info
        return {"name": name + suffix, "desc": desc}

    for prefix, (name, desc) in _FORM_PREFIX_INFO:
        if base.startswith(prefix):
            return {"name": name + suffix, "desc": desc}

    return {"name": "", "desc": ""}


# SEC exhibit 按「编号分组」映射中文（EX-<组号>.<子号>），按组号整数精确匹配。
_EXHIBIT_GROUP: dict[str, str] = {
    "1": "承销相关协议",
    "2": "并购/重组协议",
    "3": "公司章程 / 细则",
    "4": "证券持有人权利文件",
    "5": "法律意见书",
    "8": "税务意见书",
    "10": "重大合同",
    "21": "子公司列表",
    "22": "债务发行主体",
    "23": "会计师 / 专家同意书",
    "24": "授权委托书",
    "31": "SOX 302 认证（CEO/CFO 签署）",
    "32": "SOX 906 认证（CEO/CFO 签署）",
    "95": "矿山安全披露",
    "97": "高管薪酬追回政策",
    "99": "新闻稿 / 补充材料",
}
# EX-99 子号细分（99.1 通常是业绩新闻稿）
_EX99_SUB: dict[str, str] = {
    "99.1": "新闻稿 / 业绩公告（附件 99.1）",
    "99.2": "补充材料（附件 99.2，常为演示稿/讲评）",
}
# 无阅读价值，列表隐藏：XBRL 数据、图片、封面等
_EXHIBIT_SKIP_GROUPS = {"100", "101", "104"}


def describe_exhibit(ex_type: str, description: str, is_primary: bool) -> dict:
    """返回附件的 {label, highlight, skip}。

    - skip：XBRL/图片/完整提交文本等对用户无价值，前端隐藏
    - highlight：EX-99.x（新闻稿/业绩材料），前端重点标出
    - label：中文标签
    """
    t = (ex_type or "").strip().upper()

    if is_primary:
        return {"label": "主文件", "highlight": False, "skip": False}

    # 完整提交合并文本、图片等
    if "COMPLETE SUBMISSION" in (description or "").upper():
        return {"label": "", "highlight": False, "skip": True}
    if t.startswith("GRAPHIC") or t in ("ZIP", "XML", "JSON", "EXCEL", "GRAPHIC"):
        return {"label": "", "highlight": False, "skip": True}

    if t.startswith("EX-"):
        num = t[3:].strip()               # 如 "99.1" / "21" / "101.INS"
        group = num.split(".")[0].split(" ")[0]
        if group in _EXHIBIT_SKIP_GROUPS:
            return {"label": "", "highlight": False, "skip": True}
        if group == "99":
            label = _EX99_SUB.get(num, f"补充材料（附件 {num}）")
            return {"label": label, "highlight": True, "skip": False}
        if group in _EXHIBIT_GROUP:
            return {"label": f"{_EXHIBIT_GROUP[group]}（附件 {num}）", "highlight": False, "skip": False}
        return {"label": f"附件 {num}", "highlight": False, "skip": False}

    # 非 EX 类型：用原始描述兜底
    label = description.strip() if description and description.upper() != t else (t or "附件")
    return {"label": label, "highlight": False, "skip": False}
