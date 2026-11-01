#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个体户年报与经营所得汇算 —— 提交前填报自检脚本。

用法::

    python scripts/annual_return_check.py --input filing.json
    python scripts/annual_return_check.py --input filing.json --json

设计原则
--------
1. 只做客观算术与规则判定：恒等式校验、差额计算、比值计算、同比波动、
   布尔一致性核对。不做税务认定，不给税务结论，不预测抽查结果。
2. 每条 finding 都写明"需要你自己确认"，而不是"你错了"。
3. 输出为填报前的自查辅助：总体风险等级 + 逐条 findings + 填报建议清单
   + 需要向税务机关确认的问题。
4. 仅依赖 Python 标准库，零第三方依赖。
5. 绝不输出 emoji；所有中文提示均为纯文本。
6. 政策数字以主管税务机关当期公告为准，本脚本不内置政策判断。

输入 JSON 格式示例
------------------
{
  "entity": {"type": "个体工商户", "name": "示例商户", "tax_no": "示例",
              "employees": 3, "has_own_staff": false, "opened_year": 2023},
  "period": {"year": 2026},
  "figures": {
    "assets_total": 500000,
    "revenue": 180000,
    "revenue_tax_inclusive": true,
    "operating_cost": 90000,
    "tax_paid": 0,
    "profit": 90000,
    "liabilities": 120000,
    "owner_equity": 380000,
    "year_end_inventory": 60000,
    "fixed_assets": 30000
  },
  "consistency": {
    "staff_included_self": true,
    "revenue_matches_bank": true,
    "revenue_matches_platform": true,
    "cost_has_invoices": true,
    "has_revenue_zero_months": false,
    "previous_year_reported": true,
    "license_valid": true,
    "bank_account_normal": true,
    "invoice_usage_normal": true,
    "tax_credit_normal": true
  },
  "last_year": {"reported": true, "assets_total": 480000, "revenue": 150000}
}

字段说明（缺失项将被跳过，不会报错）
--------------------------------
entity.type / name / tax_no：主体信息，仅用于输出展示。
entity.employees：填报的从业人数（整数）。
entity.has_own_staff：是否雇有员工（布尔）。与 employees 一起用于口径提示。
entity.opened_year：开业年份（整数），用于提示经营年限短时的波动解释力有限。

figures.assets_total：资产总额。
figures.revenue：营业额 / 营业收入。
figures.revenue_tax_inclusive：营业额是否含税（布尔），仅用于提示口径。
figures.operating_cost：营业支出 / 成本费用。
figures.tax_paid：实缴税额合计。
figures.profit：填报的利润。
figures.liabilities：负债合计。
figures.owner_equity：所有者权益。
figures.year_end_inventory：年末存货（可选，用于资产构成提示）。
figures.fixed_assets：固定资产（可选，用于资产构成提示）。

consistency 下十项布尔：staff_included_self、revenue_matches_bank、
revenue_matches_platform、cost_has_invoices、has_revenue_zero_months、
previous_year_reported、license_valid、bank_account_normal、
invoice_usage_normal、tax_credit_normal。

这十项统一按"确认状态"理解：**填 false 即产生一条风险提示**（该项尚未被
确认通过），填 true 即视为已确认。其中 has_revenue_zero_months 表示"全年
是否存在零收入月份已核实并已写明说明"，true 表示存在零收入月份且已完成
说明，false 表示尚未核实。无论取值如何，脚本都会提示逐月比对银行入账。

last_year.reported：上一年度是否已按期报送（布尔）。
last_year.assets_total / last_year.revenue：上一年度已报数，用于同比比对。

退出码
------
0：正常输出（含存在风险的正常检查结果）。
2：输入文件不存在、JSON 非法或参数错误。
"""

import argparse
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except AttributeError:  # pragma: no cover - 老版本 Python 兜底
    pass

# 判定阈值（均为通用规则阈值，非税务标准）
BALANCE_TOLERANCE_RATIO = 0.01     # 资产恒等式允许偏差 1%
PROFIT_DIFF_TOLERANCE_RATIO = 0.05  # 营收成本利润差额允许占营收 5%
YOY_VOLATILITY_LIMIT = 0.50         # 营业额同比波动 ±50%
ASSET_TO_REVENUE_HIGH = 5.0          # 资产总额超过年营收 5 倍
ASSET_TO_REVENUE_LOW = 0.2           # 资产总额低于年营收 0.2 倍

LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2}
LEVEL_LABEL = {"low": "低", "medium": "中", "high": "高"}

CONSISTENCY_ITEMS = [
    # (键, 标题, 说明, 建议, 取值为真时是否代表存在问题, 风险等级)
    ("staff_included_self", "从业人数是否包含经营者本人未明确",
     "填报为 false 表示未把经营者本人计入从业人数，这是一种可以成立的口径，但需要能说清依据。",
     "确认本人是否计入并保留依据；不确定就列入待确认问题问主管税务机关。", False, "low"),
    ("revenue_matches_bank", "营业额与银行流水未对上",
     "申报营业额与银行流水不一致，是抽查时最常被要求说明的差异之一。",
     "把银行入账按经营收入与非经营往来分两类重新加总核对。", False, "medium"),
    ("revenue_matches_platform", "营业额与平台后台数据未对上",
     "平台、电商等线上收入容易整年漏计或重复计入。",
     "按平台逐个导出全年结算数据并加总，与申报数比对。", False, "medium"),
    ("cost_has_invoices", "部分成本缺少凭证支撑",
     "无凭证成本在税前扣除时难以证明与经营相关。",
     "为大额成本补齐凭证，或准备成本明细与业务说明备查。", False, "medium"),
    ("has_revenue_zero_months", "零收入月份情况尚未逐月确认",
     "该项用于标注全年是否存在零收入月份已核实并已写明说明；整月零收入但银行仍有小额入账时，收入完整性容易被质疑。",
     "逐月比对银行入账，确认标为零收入的月份确实无经营流水；若有零收入月份且银行有入账，写明差异原因。", False, "low"),
    ("previous_year_reported", "上一年度是否已报尚未确认",
     "上年未按期报送会面临列入经营异常名录，并连带影响本年信用状况。",
     "在国家企业信用信息公示系统查询上年公示记录。", False, "high"),
    ("license_valid", "营业执照有效性未确认",
     "证照过期或状态异常会直接影响申报受理与后续事项。",
     "核对营业执照有效期与市场主体状态。", False, "medium"),
    ("bank_account_normal", "银行账户状态未确认",
     "账户异常（冻结、久悬、非正常）会影响收款与对账。",
     "到开户行确认账户状态正常。", False, "medium"),
    ("invoice_usage_normal", "发票使用情况未确认",
     "未按规定开具、取得或保管发票可能触发进项转出与处罚风险。",
     "核对全年开具与取得发票的品目、金额、备注是否合规。", False, "medium"),
    ("tax_credit_normal", "纳税信用状况未确认",
     "纳税信用评价结果影响部分经营事项，且与异常状态相互关联。",
     "在电子税务局查询本年度纳税信用评价结果。", False, "medium"),
]


def _num(value):
    """安全地把输入转成 float；无法转换时返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _get(container, key):
    """从字典中安全取值，缺失或类型不符时返回 None。"""
    if isinstance(container, dict):
        return container.get(key)
    return None


def _fmt_money(value):
    """把金额格式化为千分位整数，便于阅读。"""
    if value is None:
        return "缺失"
    return "{:,.0f}".format(value)


def _add(findings, level, code, wording, suggestion, reference):
    """追加一条 finding。level 取 low / medium / high。"""
    findings.append({
        "level": level,
        "code": code,
        "wording": wording,
        "suggestion": suggestion,
        "reference": reference,
    })


def check_balance_identity(figures, findings):
    """校验资产总额约等于负债加所有者权益，偏差超 1% 报错。"""
    assets = _num(_get(figures, "assets_total"))
    liabilities = _num(_get(figures, "liabilities"))
    equity = _num(_get(figures, "owner_equity"))
    if assets is None or liabilities is None or equity is None:
        return None
    expected = liabilities + equity
    diff = assets - expected
    if abs(expected) < 1e-9:
        if abs(diff) > 1e-9:
            _add(findings, "high", "balance_identity",
                 "资产总额与负债加所有者权益不相等：申报资产总额 %s，负债加权益合计 %s。"
                 % (_fmt_money(assets), _fmt_money(expected)),
                 "回查资产总额、负债、所有者权益三个字段的取数口径是否一致。",
                 "自检清单第 1 项：资产恒等式。")
        return diff
    ratio = abs(diff) / abs(expected)
    if ratio > BALANCE_TOLERANCE_RATIO:
        _add(findings, "high", "balance_identity",
             "资产总额与负债加所有者权益偏差 %.1f%%（超出 1%% 容忍线）：申报 %s，"
             "负债加权益 %s，差额 %s。"
             % (ratio * 100, _fmt_money(assets), _fmt_money(expected), _fmt_money(diff)),
             "至少一个字段的取数口径不一致，逐项回查资产、负债、权益的来源表。",
             "自检清单第 1 项：资产恒等式，偏差超 1% 需回查。")
    return diff


def check_profit_consistency(figures, findings):
    """校验营业额减营业支出与填报利润的差额是否在可解释范围。"""
    revenue = _num(_get(figures, "revenue"))
    cost = _num(_get(figures, "operating_cost"))
    profit = _num(_get(figures, "profit"))
    if revenue is None or cost is None or profit is None:
        return None
    computed = revenue - cost
    diff = computed - profit
    if abs(revenue) < 1e-9:
        return diff
    ratio = abs(diff) / abs(revenue)
    if ratio > PROFIT_DIFF_TOLERANCE_RATIO:
        _add(findings, "medium", "profit_consistency",
             "营业额减营业支出与填报利润的差额为 %s，占营业额 %.1f%%（超过 5%% 参考线）："
             "按申报数算出 %s，填报利润 %s。"
             % (_fmt_money(diff), ratio * 100, _fmt_money(computed), _fmt_money(profit)),
             "差额需由存货变动、成本结转、待摊费用等客观因素解释并写明，否则利润口径存疑。",
             "自检清单第 2 项：营收成本利润一致性。")
    return diff


def check_yoy_volatility(figures, last_year, findings):
    """营业额同比波动超过正负 50% 时提示口径可能不一致。"""
    revenue = _num(_get(figures, "revenue"))
    prev_revenue = _num(_get(last_year, "revenue"))
    if revenue is None or prev_revenue is None:
        return None
    if abs(prev_revenue) < 1e-9:
        if abs(revenue) > 0:
            _add(findings, "low", "yoy_volatility",
                 "上一年度营业额为 0，本年度为 %s，同比幅度无法计算。"
                 % _fmt_money(revenue),
                 "确认是上年度真实无经营，还是本年才首次纳入此前未统计的收入渠道。",
                 "自检清单第 3 项：营业额同比波动。")
        return None
    change = (revenue - prev_revenue) / abs(prev_revenue)
    if abs(change) > YOY_VOLATILITY_LIMIT:
        direction = "增长" if change > 0 else "下降"
        _add(findings, "medium", "yoy_volatility",
             "营业额较上一年度%s %.1f%%（超过正负 50%% 参考线）：本年 %s，上年 %s。"
             % (direction, abs(change) * 100, _fmt_money(revenue), _fmt_money(prev_revenue)),
             "提示口径可能不一致（例如本年才纳入某平台收入、歇业期间恢复或缩减），"
             "请确认变动原因是否与账目一致；此处不作税务结论。",
             "自检清单第 3 项：营业额同比波动。")
    return change


def check_asset_to_revenue(figures, findings):
    """资产总额与年营收比例异常时提示口径可能填错。"""
    assets = _num(_get(figures, "assets_total"))
    revenue = _num(_get(figures, "revenue"))
    if assets is None or revenue is None:
        return None
    if abs(revenue) < 1e-9:
        if assets > 0:
            _add(findings, "low", "asset_to_revenue",
                 "本年营业额为 0 但资产总额为 %s，无法计算资产与营收比例。"
                 % _fmt_money(assets),
                 "确认资产栏是否误填了登记事项（如注册资金）而非账面数。",
                 "自检清单第 4 项：资产与营收比例。")
        return None
    ratio = assets / abs(revenue)
    if ratio > ASSET_TO_REVENUE_HIGH:
        _add(findings, "medium", "asset_to_revenue",
             "资产总额为年营收的 %.1f 倍（超过 5 倍参考线）：资产 %s，营收 %s。"
             % (ratio, _fmt_money(assets), _fmt_money(revenue)),
             "提示资产栏可能取了估值、家庭资产或累计数，而非经营账面数，请逐项回查。",
             "自检清单第 4 项：资产与营收比例。")
    elif ratio < ASSET_TO_REVENUE_LOW:
        _add(findings, "medium", "asset_to_revenue",
             "资产总额仅为年营收的 %.2f 倍（低于 0.2 倍参考线）：资产 %s，营收 %s。"
             % (ratio, _fmt_money(assets), _fmt_money(revenue)),
             "提示资产栏可能漏填存货、固定资产或往来资产，请与资产负债表核对。",
             "自检清单第 4 项：资产与营收比例。")
    return ratio


def check_staff_basis(entity, figures, findings):
    """从业人数口径自洽性检查。"""
    employees = _get(entity, "employees")
    has_own_staff = _get(entity, "has_own_staff")
    if employees is None or has_own_staff is None:
        return None
    try:
        headcount = int(employees)
    except (TypeError, ValueError):
        return None
    if headcount < 0:
        _add(findings, "medium", "staff_basis",
             "填报的从业人数为负数（%s），该数字不可能成立。"
             % _fmt_money(headcount),
             "回查从业人数的取数来源与统计时点。",
             "自检清单第 5 项：从业人数口径。")
        return headcount
    if headcount > 0 and not has_own_staff:
        _add(findings, "medium", "staff_basis",
             "填报从业人数为 %d 人，但未标记有雇员，两者口径不一致。"
             % headcount,
             "核对这 %d 人是雇员、劳务派遣人员，还是把经营者本人计入了。" % headcount,
             "自检清单第 5 项：从业人数口径。")
    if headcount == 0 and has_own_staff:
        _add(findings, "low", "staff_basis",
             "标记为有雇员但填报从业人数为 0，两者口径不一致。",
             "核对年末在册人数与是否含劳务派遣人员。",
             "自检清单第 5 项：从业人数口径。")
    return headcount


def check_zero_tax_with_revenue(figures, findings):
    """有营收但实缴税额为 0 时，提示需确认是否适用优惠。"""
    revenue = _num(_get(figures, "revenue"))
    tax_paid = _num(_get(figures, "tax_paid"))
    if revenue is None or tax_paid is None:
        return None
    if revenue > 0 and abs(tax_paid) < 1e-9:
        _add(findings, "low", "zero_tax_with_revenue",
             "本年有营业收入 %s，但实缴税额为 0。"
             % _fmt_money(revenue),
             "需自行确认是否适用小规模纳税人免税或个体工商户所得税优惠等政策；"
             "此处只提示需要确认，不作适用与否的认定。请把所依据的政策写进说明。",
             "自检清单第 6 项：零税额但有营收。")
    return tax_paid


def check_consistency_flags(consistency, findings):
    """逐项核对 consistency 中的十个布尔项。

    规则：填 false 即报风险（该项未被确认通过），填 true 即通过；
    取值不是布尔时一律提示补齐。
    """
    checked = []
    for key, title, wording, suggestion, risk_when_true, level in CONSISTENCY_ITEMS:
        value = _get(consistency, key)
        if value is None:
            continue
        checked.append(key)
        if value is True:
            if risk_when_true:
                _add(findings, level, "consistency_" + key,
                     "一致性项提示：%s。%s" % (title, wording),
                     suggestion,
                     "自检清单第 7 项：十项一致性核对。")
        elif value is False:
            if not risk_when_true:
                _add(findings, level, "consistency_" + key,
                     "一致性项未通过：%s。%s" % (title, wording),
                     suggestion,
                     "自检清单第 7 项：十项一致性核对。")
        else:
            _add(findings, "low", "consistency_" + key,
                 "一致性项取值不是 true/false：%s，请补齐后再提交。" % title,
                 "把该布尔项改为明确的 true 或 false。",
                 "自检清单第 7 项：十项一致性核对。")
    return checked


def check_last_year_filing(last_year, findings):
    """上年未按期报送时提示可能被列入经营异常名录。"""
    reported = _get(last_year, "reported")
    if reported is None:
        return None
    if not reported:
        _add(findings, "high", "last_year_not_reported",
             "上一年度未按期报送年度报告。",
             "未按期报送会被登记机关列入经营异常名录，建议先处理移出异常名录，"
             "再报本年；顺序反了可能两边都办不成。",
             "《市场主体登记管理条例实施细则》第六十三条、第七十条；"
             "自检清单第 8 项。")
    return reported


def check_inventory_and_fixed_assets(figures, findings):
    """存货与固定资产之和超过资产总额时给出提示（客观算术比较）。"""
    assets = _num(_get(figures, "assets_total"))
    inventory = _num(_get(figures, "year_end_inventory"))
    fixed = _num(_get(figures, "fixed_assets"))
    if assets is None:
        return None
    parts = [v for v in (inventory, fixed) if v is not None]
    if not parts:
        return None
    total = sum(parts)
    if total > assets * 1.01:
        _add(findings, "medium", "asset_components",
             "年末存货与固定资产合计 %s，已超过申报资产总额 %s。"
             % (_fmt_money(total), _fmt_money(assets)),
             "提示资产总额与资产明细口径不一致，请核对是否把负债项或累计数计入了资产栏。",
             "自检清单第 1、4 项：资产恒等式与资产构成。")
    return total


def build_questions(figures, entity, findings):
    """根据已发现的问题生成需要向税务机关确认的问题清单。"""
    questions = []
    codes = set(item["code"] for item in findings)
    if "revenue_tax_inclusive" in codes:
        questions.append(
            "年报营业额栏应填含税还是不含税的全年金额，与我的发票系统口径如何对应？")
    if "balance_identity" in codes:
        questions.append(
            "资产总额与负债加所有者权益对不上时，登记机关要求的取数口径以哪份表为准？")
    if "staff_basis" in codes:
        questions.append(
            "本省个体工商户年报的从业人数是否包含经营者本人？劳务派遣人员如何计入？")
    if "zero_tax_with_revenue" in codes:
        questions.append(
            "我的经营情况是否适用小规模纳税人免税或个体工商户所得税优惠？"
            "如适用，需在哪个环节说明依据？")
    if "last_year_not_reported" in codes:
        questions.append(
            "上年未按期报送年报且已被列入经营异常名录，应先移出异常名录还是先报本年？")
    if "consistency_revenue_matches_bank" in codes:
        questions.append(
            "年报营业额与增值税申报销售额口径不一致时，应以哪个为准、在哪个系统调整？")
    if "consistency_cost_has_invoices" in codes:
        questions.append(
            "部分成本缺少凭证时，税前扣除需保留哪些证据、达到什么留存标准？")
    if not questions:
        questions.append(
            "以上十项自检均通过。请向主管税务机关确认：本省个体工商户年报表单中"
            "资产总额、负债、所有者权益三项是否需要填报，以及是否可选择不公示营业额与纳税总额。")
    return questions


def run_checks(data):
    """执行全部检查并返回结果字典。"""
    entity = _get(data, "entity") or {}
    figures = _get(data, "figures") or {}
    consistency = _get(data, "consistency") or {}
    last_year = _get(data, "last_year") or {}

    findings = []

    check_balance_identity(figures, findings)
    check_profit_consistency(figures, findings)
    check_yoy_volatility(figures, last_year, findings)
    check_asset_to_revenue(figures, findings)
    check_staff_basis(entity, figures, findings)
    check_zero_tax_with_revenue(figures, findings)
    check_consistency_flags(consistency, findings)
    check_last_year_filing(last_year, findings)
    check_inventory_and_fixed_assets(figures, findings)

    tax_inclusive = _get(figures, "revenue_tax_inclusive")
    if tax_inclusive is not None:
        if tax_inclusive is True:
            _add(findings, "low", "revenue_tax_inclusive",
                 "本表营业额按含税口径填写。",
                 "确认与发票系统、平台后台、增值税申报的口径一致，并在口径说明中写明含税与否。",
                 "自检清单第 7 项：营收与银行流水、营收与平台后台的一致性。")
        elif tax_inclusive is not True:
            _add(findings, "low", "revenue_tax_inclusive",
                 "revenue_tax_inclusive 取值不是 true/false，请补齐含税口径标记。",
                 "把该字段改为明确的 true 或 false。",
                 "自检清单第 7 项。")

    counts = {"high": 0, "medium": 0, "low": 0}
    for item in findings:
        counts[item["level"]] = counts.get(item["level"], 0) + 1

    if counts["high"] > 0:
        overall = "high"
    elif counts["medium"] > 0:
        overall = "medium"
    else:
        overall = "low"

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda item: order[item["level"]])

    suggestions = []
    for item in findings:
        suggestions.append({
            "priority": LEVEL_LABEL[item["level"]],
            "code": item["code"],
            "action": item["suggestion"],
        })

    questions = build_questions(figures, entity, findings)

    return {
        "entity": {
            "type": _get(entity, "type") or "未填写",
            "name": _get(entity, "name") or "未填写",
            "tax_no": _get(entity, "tax_no") or "未填写",
            "period": (_get(_get(data, "period") or {}, "year")),
        },
        "overall_risk": overall,
        "overall_risk_label": LEVEL_LABEL[overall],
        "risk_count": len(findings),
        "risk_counts_by_level": counts,
        "findings": findings,
        "filing_suggestions": suggestions,
        "questions_for_tax_authority": questions,
        "disclaimer": "本结果为客观算术与规则判定，不构成税务意见、鉴证报告或申报承诺；"
                     "最终以税务机关认定为准。本工具不代办申报。",
    }


def render_text(result):
    """把结果渲染为纯文本报告（不使用任何 emoji）。"""
    lines = []
    entity = result["entity"]
    lines.append("个体户年报与经营所得汇算 · 提交前自检报告")
    lines.append("主体：%s（%s）  纳税人识别号：%s  报告年度：%s"
                 % (entity["name"], entity["type"], entity["tax_no"], entity["period"]))
    lines.append("总体风险等级：%s    风险条数：%d（高 %d / 中 %d / 低 %d）"
                 % (result["overall_risk_label"], result["risk_count"],
                    result["risk_counts_by_level"]["high"],
                    result["risk_counts_by_level"]["medium"],
                    result["risk_counts_by_level"]["low"]))
    lines.append("")

    if not result["findings"]:
        lines.append("自检结果：未发现口径差异提示。")
        lines.append("提示：这不代表填报一定正确，仍需人工复核原始凭据。")
    else:
        lines.append("自检发现（按紧急度排序）：")
        for index, item in enumerate(result["findings"], 1):
            lines.append("")
            lines.append("%d. [%s] %s" % (index, LEVEL_LABEL[item["level"]], item["wording"]))
            lines.append("   建议：%s" % item["suggestion"])
            lines.append("   依据：%s" % item["reference"])
        lines.append("")

    lines.append("填报建议清单（按紧急度排序）：")
    if result["filing_suggestions"]:
        for index, item in enumerate(result["filing_suggestions"], 1):
            lines.append("%d. [%s] %s" % (index, item["priority"], item["action"]))
    else:
        lines.append("无。按第十项保留期限缓冲即可。")
    lines.append("")

    lines.append("需要向税务机关确认的问题：")
    for index, question in enumerate(result["questions_for_tax_authority"], 1):
        lines.append("%d. %s" % (index, question))
    lines.append("")
    lines.append(result["disclaimer"])
    return "\n".join(lines)


def main(argv=None):
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="个体户年报与经营所得汇算填报自检脚本（仅做客观算术与规则判定）")
    parser.add_argument("--input", required=True, help="填好的申报数据 JSON 文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")
    args = parser.parse_args(argv)

    path = args.input
    if not os.path.isfile(path):
        sys.stderr.write("错误：找不到输入文件 %s\n" % path)
        sys.stderr.write("请用 --input 指定填好的 filing.json 路径。\n")
        return 2

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except UnicodeDecodeError:
        sys.stderr.write("错误：输入文件 %s 不是 UTF-8 编码的文本文件。\n" % path)
        return 2
    except json.JSONDecodeError as exc:
        sys.stderr.write("错误：输入文件 %s 不是合法的 JSON（第 %d 行第 %d 列：%s）。\n"
                         % (path, exc.lineno, exc.colno, exc.msg))
        return 2
    except OSError as exc:
        sys.stderr.write("错误：无法读取输入文件 %s（%s）。\n" % (path, exc.strerror))
        return 2

    if not isinstance(data, dict):
        sys.stderr.write("错误：输入 JSON 顶层必须是对象（{...}），当前为 %s。\n"
                         % type(data).__name__)
        return 2

    result = run_checks(data)

    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(result))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
