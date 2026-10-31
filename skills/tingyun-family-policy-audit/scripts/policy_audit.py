#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""家庭保单年度体检助手 —— 保单盘点与客观数据核对脚本。

用法::

    python scripts/policy_audit.py --input policies.json
    python scripts/policy_audit.py --input policies.json --json
    python scripts/policy_audit.py --input policies.json --json --today 2026-10-31

设计原则
--------
1. 只做客观算术与规则判定：倍数换算、日期倒计时、区间对照、状态标记。
2. 不推荐保险产品、不推荐公司、不判断"能不能赔"、不预测理赔结果，
   不输出"你应该买什么保险"这类主观建议。
3. 输出中出现的"参考区间"（如重疾保额 3~5 倍年收入）一律标注为
   "常见做法参考，实际应结合自身情况"，仅供对照阅读。
4. 仅依赖 Python 标准库，零第三方依赖。
5. 所有日期基于真实当前日期计算（可用 --today 覆盖以便复现）。

输入 JSON 格式示例
------------------
{
  "family": {
    "members": 3,
    "member_names": ["父亲", "母亲", "孩子"],
    "annual_income": 600000,
    "annual_expense": 240000,
    "liabilities": 800000
  },
  "policies": [
    {
      "holder": "父亲",
      "insured": "父亲",
      "company": "示例保险",
      "product": "重疾险",
      "coverage": 300000,
      "pay_mode": "年缴",
      "annual_premium": 7200,
      "pay_day": 15,
      "pay_month": 9,
      "term_years": 20,
      "start_year": 2021,
      "type": "重疾",
      "beneficiary": "",
      "auto_pay": true,
      "active": true,
      "last_pay_year": 2025,
      "grace_days": 60,
      "card_verified_year": 2024
    },
    {
      "holder": "父亲",
      "insured": "孩子",
      "company": "示例保险",
      "product": "百万医疗",
      "coverage": 3000000,
      "pay_mode": "年缴",
      "annual_premium": 400,
      "pay_day": 15,
      "term_years": 1,
      "start_year": 2025,
      "type": "医疗",
      "beneficiary": "",
      "auto_pay": false,
      "active": true,
      "last_pay_year": 2025
    }
  ]
}

字段说明
--------
family.members          家庭成员数量（整数）
family.member_names     成员姓名或称谓列表（可选，用于保障成员覆盖检查）
family.annual_income    家庭年总收入（数字）
family.annual_expense   家庭年支出（数字，可选；缺失时寿险对照仅用负债）
family.liabilities      家庭负债总额，如房贷余额（数字）

policies[].holder            投保人
policies[].insured           被保险人
policies[].company           保险公司名称
policies[].product           产品名称
policies[].coverage           保额（数字）
policies[].pay_mode          缴费方式：年缴 / 趸缴 / 期缴
policies[].annual_premium    年缴保费（数字）
policies[].pay_day           缴费日（每月几号，1~31）
policies[].pay_month         缴费月份（1~12，可选；填写后倒计时为精确推算，
                             未填写则按日号估算并标注"估算值"）
policies[].term_years        保障年限（数字）
policies[].start_year        起保年度（数字）
policies[].type              险种类别：重疾 / 寿险 / 医疗 / 意外 / 年金 / 失能
policies[].beneficiary       受益人（留空表示未指定）
policies[].auto_pay          是否自动扣款（布尔）
policies[].active            保单是否有效（布尔）
policies[].last_pay_year     最后缴费年份（数字，可选）
policies[].grace_days        宽限期天数（数字，可选，默认 60）
policies[].card_verified_year 扣款账户最近核验年份（数字，可选）
policies[].auto_pay_card     扣款账户标识（字符串，可选）
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date, timedelta

try:  # 保证在 GBK 控制台环境下也能安全输出中文
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:  # pragma: no cover - 极端环境下静默跳过
    pass


DISCLAIMER = (
    "本脚本输出仅为对用户自行录入数据的客观整理与算术对照，不构成保险产品建议、"
    "投保建议或理赔结论，不能用于判断某份保单是否应当赔付。所有内容需以保险合同、"
    "承保公司正式通知与保险法及保险合同相关规定为准，重大决策请另行咨询持牌"
    "保险从业者或执业律师。"
)

# 参考区间常量：只作为"常见做法参考"用于对照，不构成配置建议。
CRITICAL_ILLNESS_LOW_MULTIPLE = 3
CRITICAL_ILLNESS_HIGH_MULTIPLE = 5
ACCIDENT_LOW_MULTIPLE = 5
ACCIDENT_HIGH_MULTIPLE = 10
LIFE_INSURANCE_EXPENSE_YEARS = 5
MILLION_MEDICAL_REFERENCE = 1000000
PREMIUM_INCOME_ALERT_RATIO = 0.20
LAPSED_REINSTATEMENT_YEARS = 2
DEFAULT_GRACE_DAYS = 60

# 险种类别归一化别名表
TYPE_ALIASES = {
    "重疾": "重疾",
    "重大疾病": "重疾",
    "critical": "重疾",
    "医疗": "医疗",
    "百万医疗": "医疗",
    "住院医疗": "医疗",
    "medical": "医疗",
    "寿险": "寿险",
    "定期寿险": "寿险",
    "终身寿险": "寿险",
    "身故": "寿险",
    "life": "寿险",
    "意外": "意外",
    "团体意外": "意外",
    "accident": "意外",
    "年金": "年金",
    "教育金": "年金",
    "储蓄": "年金",
    "失能": "失能",
    "收入保障": "失能",
    "护理": "失能",
}

SEVERITY_ORDER = {"高": 0, "中": 1, "低": 2}
URGENCY_BUCKETS = ("30天内", "90天内", "年度事项")


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def _num(value, default=0.0):
    """把任意输入安全转换为数字，无法转换时返回默认值。

    Args:
        value: 原始值，可能是数字、数字字符串、空值或 None。
        default: 无法解析时返回的默认值。

    Returns:
        float 或 int 类型的数值。
    """
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _opt_num(value):
    """把输入转换为数字，无法解析时返回 None（表示缺失）。

    Args:
        value: 原始值。

    Returns:
        float/int 或 None。
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _text(value):
    """安全地把输入转换为去除首尾空白的字符串。

    Args:
        value: 原始值。

    Returns:
        str，None 转为空字符串。
    """
    if value is None:
        return ""
    return str(value).strip()


def normalize_type(raw):
    """把保险公司或用户自由填写的险种名称归一化到内部类别。

    Args:
        raw: 原始类别字符串，例如"重疾险""百万医疗""定期寿险"。

    Returns:
        str，归一化类别；无法识别时返回"其他"。
    """
    text = _text(raw)
    if not text:
        return "其他"
    for alias, group in TYPE_ALIASES.items():
        if alias.lower() in text.lower():
            return group
    return "其他"


def _days_in_month(year: int, month: int) -> int:
    """返回指定年月的天数。

    Args:
        year: 年份。
        month: 月份（1~12）。

    Returns:
        int，该月天数。
    """
    return calendar.monthrange(year, month)[1]


def _next_payment_date(policy, today: date):
    """计算年缴保单下一次缴费日。

    若录入时提供了 pay_month（1~12），则按该年份的该月该日号推算；
    若未提供月份，则按"该日号在最近一个未来月份出现"估算，并置 estimated 标记，
    提示用户补充具体月份以获得精确倒计时。

    Args:
        policy: 保单字典，需含 pay_day，可选 pay_month。
        today: 当前日期。

    Returns:
        (date, int, bool) 分别为下一次缴费日期、剩余天数、是否为估算值；
        无有效缴费日时返回 (None, None, False)。
    """
    pay_day = int(_num(policy.get("pay_day"), 0))
    if pay_day < 1:
        return None, None, False
    if pay_day > 28:
        pay_day = 28
    pay_month = _opt_num(policy.get("pay_month"))

    if pay_month is not None and 1 <= int(pay_month) <= 12:
        month = int(pay_month)
        year = today.year
        candidate = date(year, month, min(pay_day, _days_in_month(year, month)))
        if candidate < today:
            year += 1
            candidate = date(year, month, min(pay_day, _days_in_month(year, month)))
        return candidate, (candidate - today).days, False

    year, month = today.year, today.month
    candidate = date(year, month, min(pay_day, _days_in_month(year, month)))
    if candidate < today:
        month += 1
        if month > 12:
            month = 1
            year += 1
        candidate = date(year, month, min(pay_day, _days_in_month(year, month)))
    return candidate, (candidate - today).days, True


def _is_annual(policy) -> bool:
    """判断保单是否为按年缴费（会持续产生年度扣款）。

    Args:
        policy: 保单字典。

    Returns:
        bool，True 表示年缴或其他年度持续缴费方式。
    """
    mode = _text(policy.get("pay_mode"))
    if not mode:
        return bool(_num(policy.get("annual_premium"), 0) > 0)
    if "趸" in mode:
        return False
    return ("年" in mode) or ("期" in mode)


def _policy_label(policy) -> str:
    """生成保单在报告中的可读标识。

    Args:
        policy: 保单字典。

    Returns:
        str，形如"父亲·示例保险某产品(重疾)"。
    """
    insured = _text(policy.get("insured")) or _text(policy.get("holder")) or "未标注被保险人"
    company = _text(policy.get("company"))
    product = _text(policy.get("product"))
    name = "".join(x for x in (company, product) if x) or "未命名保单"
    ptype = normalize_type(policy.get("type") or policy.get("product"))
    return "{0}·{1}({2})".format(insured, name, ptype)


def _coverage(policy) -> float:
    """提取保额。

    Args:
        policy: 保单字典。

    Returns:
        float，保额数值。
    """
    return _num(policy.get("coverage"), 0)


# --------------------------------------------------------------------------- #
# 1. 保障缺口测算（客观倍数对照）
# --------------------------------------------------------------------------- #
def analyze_coverage_gap(data):
    """按家庭结构做保额倍数的客观对照，输出对照结果而非配置建议。

    对照口径（均为"常见做法参考，实际应结合自身情况"）：
    - 重疾保额 vs 家庭年收入 3~5 倍
    - 寿险保额 vs 家庭负债 + 5 年家庭支出
    - 百万医疗类产品额度 vs 100 万元参考下限
    - 意外保额 vs 家庭年收入 5~10 倍

    Args:
        data: 顶层输入字典。

    Returns:
        dict，包含 totals / items / missing_types 三部分。
    """
    family = data.get("family") or {}
    policies = data.get("policies") or []
    active = [p for p in policies if p.get("active", True)]

    income = _opt_num(family.get("annual_income"))
    expense = _opt_num(family.get("annual_expense"))
    liabilities = _opt_num(family.get("liabilities"))

    totals = {"重疾": 0.0, "寿险": 0.0, "医疗": 0.0, "意外": 0.0, "年金": 0.0, "失能": 0.0}
    counts = {k: 0 for k in totals}
    for policy in active:
        group = normalize_type(policy.get("type") or policy.get("product"))
        if group in totals:
            totals[group] += _coverage(policy)
            counts[group] += 1

    items = []

    # 重疾：保额 / 年收入
    ci_total = totals["重疾"]
    if income and income > 0:
        multiple = ci_total / income
        low = CRITICAL_ILLNESS_LOW_MULTIPLE * income
        high = CRITICAL_ILLNESS_HIGH_MULTIPLE * income
        if ci_total < low:
            status = "低于参考区间"
        elif ci_total > high:
            status = "高于参考区间"
        else:
            status = "落在参考区间内"
        items.append({
            "risk": "重疾",
            "coverage_total": ci_total,
            "policy_count": counts["重疾"],
            "base_amount": income,
            "multiple": round(multiple, 2),
            "reference_low": low,
            "reference_high": high,
            "reference_text": "常见做法参考：家庭年收入的 3~5 倍（实际应结合自身情况与预算）",
            "status": status,
            "statement": "当前重疾保额合计 {0:,.0f} 元，为家庭年收入的 {1} 倍；参考区间为 {2:,.0f}~{3:,.0f} 元。".format(
                ci_total, round(multiple, 2), low, high),
        })
    else:
        items.append({
            "risk": "重疾",
            "coverage_total": ci_total,
            "policy_count": counts["重疾"],
            "base_amount": None,
            "multiple": None,
            "reference_low": None,
            "reference_high": None,
            "reference_text": "常见做法参考：家庭年收入的 3~5 倍（实际应结合自身情况与预算）",
            "status": "缺少家庭年收入数据，无法完成倍数对照",
            "statement": "当前重疾保额合计 {0:,.0f} 元；family.annual_income 未填写，无法做倍数对照。".format(ci_total),
        })

    # 寿险：保额 / （负债 + 5 年支出）
    life_total = totals["寿险"]
    if liabilities is None and expense is None:
        items.append({
            "risk": "寿险",
            "coverage_total": life_total,
            "policy_count": counts["寿险"],
            "base_amount": None,
            "multiple": None,
            "reference_low": None,
            "reference_high": None,
            "reference_text": "常见做法参考：覆盖家庭负债 + 5 年家庭支出（实际应结合自身情况）",
            "status": "缺少负债与支出数据，无法完成对照",
            "statement": "当前寿险保额合计 {0:,.0f} 元；未填写 family.liabilities 与 family.annual_expense，无法做对照。".format(life_total),
        })
    else:
        liabilities = liabilities or 0.0
        expense_base = (expense or 0.0) * LIFE_INSURANCE_EXPENSE_YEARS
        base = liabilities + expense_base
        note = ""
        if expense is None:
            note = "；family.annual_expense 未填写，对照基数仅含负债部分"
        multiple = (life_total / base) if base > 0 else None
        if base <= 0:
            status = "对照基数为 0，无法判定"
        elif life_total < base:
            status = "低于对照基数"
        else:
            status = "达到或高于对照基数"
        items.append({
            "risk": "寿险",
            "coverage_total": life_total,
            "policy_count": counts["寿险"],
            "base_amount": base,
            "multiple": round(multiple, 2) if multiple is not None else None,
            "reference_low": base,
            "reference_high": None,
            "reference_text": "常见做法参考：覆盖家庭负债 + 5 年家庭支出（实际应结合自身情况）",
            "status": status,
            "statement": "当前寿险保额合计 {0:,.0f} 元；对照基数（负债 {1:,.0f} + 5 年支出 {2:,.0f}）为 {3:,.0f} 元{4}。".format(
                life_total, liabilities, expense_base, base, note),
        })

    # 医疗：是否有医疗类记录 + 百万医疗额度参考下限
    medical_policies = [
        p for p in active
        if normalize_type(p.get("type") or p.get("product")) == "医疗"
    ]
    million_policies = [
        p for p in medical_policies
        if "百万" in _text(p.get("product")) or _coverage(p) >= MILLION_MEDICAL_REFERENCE
    ]
    below_million = [p for p in million_policies if _coverage(p) < MILLION_MEDICAL_REFERENCE]
    medical_item = {
        "risk": "医疗",
        "coverage_total": totals["医疗"],
        "policy_count": counts["医疗"],
        "has_medical": bool(medical_policies),
        "million_count": len(million_policies),
        "below_million": [_policy_label(p) for p in below_million],
        "reference_text": "常见做法参考：百万医疗类产品保额 100 万元起（仅作客观对照，实际以合同为准）",
        "status": "未发现医疗类保单记录" if not medical_policies else (
            "存在医疗类记录，未见百万医疗额度" if not million_policies else "已见百万医疗额度记录"),
        "statement": ("本次录入的保单中未发现医疗类保单记录。" if not medical_policies else
                      "医疗类保单 {0} 件，其中百万医疗类 {1} 件。".format(len(medical_policies), len(million_policies))),
    }
    if below_million:
        medical_item["statement"] += "有 {0} 件百万医疗类保单额度低于 100 万元参考下限。".format(len(below_million))
    items.append(medical_item)

    # 意外：保额 / 年收入
    acc_total = totals["意外"]
    if income and income > 0:
        multiple = acc_total / income
        low = ACCIDENT_LOW_MULTIPLE * income
        high = ACCIDENT_HIGH_MULTIPLE * income
        if acc_total < low:
            status = "低于参考区间"
        elif acc_total > high:
            status = "高于参考区间"
        else:
            status = "落在参考区间内"
        items.append({
            "risk": "意外",
            "coverage_total": acc_total,
            "policy_count": counts["意外"],
            "base_amount": income,
            "multiple": round(multiple, 2),
            "reference_low": low,
            "reference_high": high,
            "reference_text": "常见做法参考：家庭年收入的 5~10 倍（实际应结合自身情况与预算）",
            "status": status,
            "statement": "当前意外保额合计 {0:,.0f} 元，为家庭年收入的 {1} 倍；参考区间为 {2:,.0f}~{3:,.0f} 元。".format(
                acc_total, round(multiple, 2), low, high),
        })
    else:
        items.append({
            "risk": "意外",
            "coverage_total": acc_total,
            "policy_count": counts["意外"],
            "base_amount": None,
            "multiple": None,
            "reference_low": None,
            "reference_high": None,
            "reference_text": "常见做法参考：家庭年收入的 5~10 倍（实际应结合自身情况与预算）",
            "status": "缺少家庭年收入数据，无法完成倍数对照",
            "statement": "当前意外保额合计 {0:,.0f} 元；family.annual_income 未填写，无法做倍数对照。".format(acc_total),
        })

    missing_types = [name for name in ("重疾", "寿险", "医疗", "意外") if counts[name] == 0]

    return {
        "family_snapshot": {
            "members": family.get("members"),
            "annual_income": income,
            "annual_expense": expense,
            "liabilities": liabilities,
        },
        "totals": totals,
        "counts": counts,
        "items": items,
        "missing_types": missing_types,
    }


# --------------------------------------------------------------------------- #
# 2. 缴费日冲突检测
# --------------------------------------------------------------------------- #
def analyze_payment_conflicts(data):
    """检测同一缴费日、同一月份多笔扣款造成的现金流拥挤。

    Args:
        data: 顶层输入字典。

    Returns:
        dict，包含 same_day_groups / same_month_groups。
    """
    policies = [p for p in (data.get("policies") or []) if p.get("active", True)]
    annual = [p for p in policies if _is_annual(p)]

    by_day = {}
    for policy in annual:
        day = int(_num(policy.get("pay_day"), 0))
        if day < 1:
            continue
        by_day.setdefault(day, []).append(policy)

    same_day_groups = []
    for day in sorted(by_day):
        group = by_day[day]
        if len(group) >= 2:
            same_day_groups.append({
                "pay_day": day,
                "policy_count": len(group),
                "policies": [_policy_label(p) for p in group],
                "annual_premium_sum": sum(_num(p.get("annual_premium")) for p in group),
                "statement": "每月 {0} 日有 {1} 笔年缴扣款，合计 {2:,.0f} 元。".format(
                    day, len(group), sum(_num(p.get("annual_premium")) for p in group)),
            })

    # 缴费月缺省时按"每年固定月份"归入同一簇
    month_map = {}
    for policy in annual:
        day = int(_num(policy.get("pay_day"), 0))
        if day < 1:
            continue
        month = policy.get("pay_month") or "每年固定月份"
        month_map.setdefault(month, []).append(policy)

    same_month_groups = []
    for month in sorted(month_map.keys(), key=lambda x: str(x)):
        group = month_map[month]
        days = sorted({int(_num(p.get("pay_day"), 0)) for p in group})
        if len(group) >= 3 or (len(group) >= 2 and days and (days[-1] - days[0]) <= 3):
            same_month_groups.append({
                "pay_month": month,
                "policy_count": len(group),
                "pay_days": days,
                "policies": [_policy_label(p) for p in group],
                "annual_premium_sum": sum(_num(p.get("annual_premium")) for p in group),
                "statement": "{0} 附近有 {1} 笔年缴扣款（缴费日 {2}），合计 {3:,.0f} 元。".format(
                    month, len(group), "、".join(str(d) for d in days),
                    sum(_num(p.get("annual_premium")) for p in group)),
            })

    return {
        "annual_policy_count": len(annual),
        "same_day_groups": same_day_groups,
        "same_month_groups": same_month_groups,
        "statement": ("未发现同一缴费日多笔扣款。" if not same_day_groups
                      else "发现 {0} 个缴费日存在多笔扣款。".format(len(same_day_groups))),
    }


# --------------------------------------------------------------------------- #
# 3. 缴费能力占比
# --------------------------------------------------------------------------- #
def analyze_payment_capacity(data):
    """计算年缴保费合计占家庭年收入的比例。

    Args:
        data: 顶层输入字典。

    Returns:
        dict，包含 total_premium / ratio / status / statement。
    """
    family = data.get("family") or {}
    policies = [p for p in (data.get("policies") or []) if p.get("active", True)]
    total = sum(_num(p.get("annual_premium")) for p in policies)
    income = _opt_num(family.get("annual_income"))

    if not income or income <= 0:
        return {
            "total_premium": total,
            "annual_income": income,
            "ratio": None,
            "status": "缺少家庭年收入数据，无法计算占比",
            "statement": "在保保单年缴保费合计 {0:,.0f} 元；family.annual_income 未填写，无法计算占比。".format(total),
        }

    ratio = total / income
    if ratio > PREMIUM_INCOME_ALERT_RATIO:
        status = "占比超过 20%，需自行判断现金流是否可承受"
    elif ratio > 0.15:
        status = "占比处于 15%~20% 之间"
    else:
        status = "占比低于 15%"
    return {
        "total_premium": total,
        "annual_income": income,
        "ratio": round(ratio, 4),
        "ratio_percent": round(ratio * 100, 2),
        "status": status,
        "statement": "在保保单年缴保费合计 {0:,.0f} 元，占家庭年收入的 {1}%。".format(total, round(ratio * 100, 2)),
    }


# --------------------------------------------------------------------------- #
# 4. 保障成员覆盖（只报事实）
# --------------------------------------------------------------------------- #
def analyze_member_coverage(data):
    """检查每个家庭成员的保障结构缺口，仅陈述事实。

    Args:
        data: 顶层输入字典。

    Returns:
        dict，包含 members / uncovered_members / structure_gaps。
    """
    family = data.get("family") or {}
    policies = data.get("policies") or []
    liabilities = _opt_num(family.get("liabilities")) or 0.0

    names = [_text(n) for n in (family.get("member_names") or []) if _text(n)]
    if not names:
        collected = set()
        for policy in policies:
            for key in ("insured", "holder"):
                value = _text(policy.get(key))
                if value:
                    collected.add(value)
        names = sorted(collected)

    member_rows = []
    uncovered = []
    structure_gaps = []

    for name in names:
        own = [p for p in policies if _text(p.get("insured")) == name]
        active = [p for p in own if p.get("active", True)]
        groups = {normalize_type(p.get("type") or p.get("product")) for p in active}
        coverage_sum = sum(_coverage(p) for p in active)
        premiums = sum(_num(p.get("annual_premium")) for p in active)
        row = {
            "member": name,
            "policy_count": len(own),
            "active_count": len(active),
            "coverage_total": coverage_sum,
            "annual_premium_total": premiums,
            "covered_types": sorted(g for g in groups if g != "其他"),
        }
        member_rows.append(row)

        if not active:
            uncovered.append({
                "member": name,
                "statement": "{0} 在本次录入的有效保单中没有记录。".format(name),
            })
            continue

        if "医疗" in groups and "重疾" not in groups:
            structure_gaps.append({
                "member": name,
                "gap": "有医疗类记录，未见重疾类记录",
                "statement": "{0} 名下有医疗类保障 {1} 件，本次录入中未见重疾类保障记录。".format(
                    name, sum(1 for p in active if normalize_type(p.get("type") or p.get("product")) == "医疗")),
            })
        if "意外" not in groups:
            structure_gaps.append({
                "member": name,
                "gap": "未见意外类记录",
                "statement": "{0} 名下本次录入中未见意外类保障记录。".format(name),
            })
        if "寿险" not in groups and liabilities > 0:
            structure_gaps.append({
                "member": name,
                "gap": "有家庭负债但未见寿险类记录",
                "statement": "家庭负债记录为 {0:,.0f} 元，{1} 名下本次录入中未见寿险类保障记录。".format(liabilities, name),
            })

    return {
        "member_count": len(names),
        "members": member_rows,
        "uncovered_members": uncovered,
        "structure_gaps": structure_gaps,
    }


# --------------------------------------------------------------------------- #
# 5. 时间节点计算
# --------------------------------------------------------------------------- #
def analyze_timeline(data, today: date):
    """计算缴费倒计时、宽限期、满期日、失效复效风险等时间节点。

    Args:
        data: 顶层输入字典。
        today: 当前日期。

    Returns:
        dict，包含 upcoming / grace / maturity / lapsed / dormant。
    """
    policies = data.get("policies") or []
    current_year = today.year

    upcoming = []
    grace = []
    maturity = []
    lapsed = []
    dormant = []

    for policy in policies:
        label = _policy_label(policy)
        active = policy.get("active", True)
        premium = _num(policy.get("annual_premium"))
        grace_days = int(_num(policy.get("grace_days"), DEFAULT_GRACE_DAYS))

        if active and _is_annual(policy) and premium > 0:
            due_date, days_left, estimated = _next_payment_date(policy, today)
            if due_date is not None:
                upcoming.append({
                    "policy": label,
                    "pay_day": int(_num(policy.get("pay_day"), 0)),
                    "pay_month": policy.get("pay_month"),
                    "due_date": due_date.isoformat(),
                    "days_left": days_left,
                    "date_estimated": estimated,
                    "annual_premium": premium,
                    "auto_pay": bool(policy.get("auto_pay")),
                    "statement": "{0} 下一次缴费日为 {1}，距今 {2} 天，应缴 {3:,.0f} 元。{4}".format(
                        label, due_date.isoformat(), days_left, premium,
                        "（未录入缴费月份，日期为按日号估算值）" if estimated else ""),
                })
                grace_end = due_date + timedelta(days=grace_days)
                grace.append({
                    "policy": label,
                    "due_date": due_date.isoformat(),
                    "grace_days": grace_days,
                    "grace_end_date": grace_end.isoformat(),
                    "days_left": days_left,
                    "statement": "{0} 宽限期按 {1} 天计，如 {2} 之前未缴清，保障效力可能受影响。".format(
                        label, grace_days, grace_end.isoformat()),
                })

        start_year = _opt_num(policy.get("start_year"))
        term_years = _opt_num(policy.get("term_years"))
        end_year = _opt_num(policy.get("end_year"))
        if end_year is None and start_year is not None and term_years is not None:
            end_year = start_year + term_years
        if end_year is not None and active:
            end_year = int(end_year)
            if end_year < current_year:
                maturity.append({
                    "policy": label,
                    "end_year": end_year,
                    "status": "推算的保障年度已过",
                    "statement": ("{0} 按录入的起保年度与保障年限推算，保障年度截至 {1} 年已过，"
                                  "需与保单确认页核对是否已续保。".format(label, end_year)),
                })
            elif end_year == current_year:
                extra = "；录入的保障年限为 1 年，此类产品通常逐年续保，需确认下一年度是否已续" if term_years == 1 else ""
                maturity.append({
                    "policy": label,
                    "end_year": end_year,
                    "status": "推算的保障年度为本年度",
                    "statement": "{0} 按录入的起保年度与保障年限推算，当前处于 {1} 年度保障期内{2}。".format(
                        label, end_year, extra),
                })
            else:
                maturity.append({
                    "policy": label,
                    "end_year": end_year,
                    "status": "推算的保障年度在本年度之后",
                    "statement": "{0} 推算满期年度为 {1} 年。".format(label, end_year),
                })

        last_pay_year = _opt_num(policy.get("last_pay_year"))
        if not active:
            gap = None
            if last_pay_year is not None:
                gap = current_year - last_pay_year
            lapsed.append({
                "policy": label,
                "last_pay_year": int(last_pay_year) if last_pay_year is not None else None,
                "years_since_last_payment": int(gap) if gap is not None else None,
                "beyond_reinstatement_threshold": bool(gap is not None and gap >= LAPSED_REINSTATEMENT_YEARS),
                "statement": ("{0} 已标记为停缴或失效，最后缴费年份 {1}，距今 {2} 年。长期未缴可能导致合同效力终止；"
                              "如需恢复通常需办理复效并重新健康告知，可能涉及新的等待期（以合同约定与保险公司审核为准）。".format(
                                  label, int(last_pay_year) if last_pay_year is not None else "未填写", int(gap) if gap is not None else "未知")),
            })
        elif last_pay_year is not None and (current_year - last_pay_year) >= LAPSED_REINSTATEMENT_YEARS:
            dormant.append({
                "policy": label,
                "last_pay_year": int(last_pay_year),
                "years_since_last_payment": int(current_year - last_pay_year),
                "statement": ("{0} 标注为有效，但最后缴费年份为 {1}，距今 {2} 年，需核实扣款是否成功、保单当前是否仍在保障中。".format(
                    label, int(last_pay_year), int(current_year - last_pay_year))),
            })

    upcoming.sort(key=lambda x: x["days_left"])
    grace.sort(key=lambda x: x["days_left"])

    return {
        "today": today.isoformat(),
        "upcoming_payments": upcoming,
        "grace_periods": grace,
        "maturity": maturity,
        "lapsed_policies": lapsed,
        "dormant_policies": dormant,
    }


# --------------------------------------------------------------------------- #
# 6 & 7. 受益人与自动扣款风险
# --------------------------------------------------------------------------- #
def analyze_beneficiaries(data):
    """标记未指定受益人的保单。

    Args:
        data: 顶层输入字典。

    Returns:
        dict，包含 issues / statement。
    """
    policies = [p for p in (data.get("policies") or []) if p.get("active", True)]
    issues = []
    # 费用补偿型（医疗）通常无受益人概念，故只对含身故给付责任的类别做标记
    designated_relevant = ("寿险", "重疾", "意外", "年金")
    for policy in policies:
        group = normalize_type(policy.get("type") or policy.get("product"))
        if group not in designated_relevant:
            continue
        beneficiary = _text(policy.get("beneficiary"))
        if not beneficiary or beneficiary in ("法定", "法定继承", "未指定"):
            issues.append({
                "policy": _policy_label(policy),
                "risk_type": group,
                "statement": "{0} 未指定具体受益人（当前记录：{1}）。受益人缺位会影响给付对象确定的效率。".format(
                    _policy_label(policy), beneficiary or "空白"),
            })
    return {
        "issues": issues,
        "count": len(issues),
        "statement": ("全部在保保单均已记录受益人。" if not issues
                      else "{0} 件在保保单未指定具体受益人。".format(len(issues))),
    }


def analyze_auto_pay(data, today: date):
    """标记自动扣款与扣款账户相关风险。

    Args:
        data: 顶层输入字典。
        today: 当前日期。

    Returns:
        dict，包含 issues / statement。
    """
    policies = [p for p in (data.get("policies") or []) if p.get("active", True)]
    current_year = today.year
    issues = []
    for policy in policies:
        if not _is_annual(policy) or _num(policy.get("annual_premium")) <= 0:
            continue
        label = _policy_label(policy)
        auto_pay = policy.get("auto_pay")
        card = _text(policy.get("auto_pay_card"))
        verified = _opt_num(policy.get("card_verified_year"))
        if auto_pay is None:
            issues.append({
                "policy": label,
                "issue": "未确认扣款方式",
                "statement": "{0} 未录入自动扣款状态，需向承保公司确认当前扣款方式。".format(label),
            })
        elif auto_pay and not card:
            issues.append({
                "policy": label,
                "issue": "已开启自动扣款但未登记扣款账户",
                "statement": "{0} 已开启自动扣款但未登记账户信息，扣款失败时不易第一时间发现。".format(label),
            })
        elif not auto_pay:
            issues.append({
                "policy": label,
                "issue": "未开启自动扣款",
                "statement": "{0} 未开启自动扣款，需在缴费期前手动完成缴费。".format(label),
            })
        if verified is not None and (current_year - verified) >= 1:
            issues.append({
                "policy": label,
                "issue": "扣款账户核验时间较久",
                "statement": "{0} 的扣款账户最近核验年份为 {1}，距今 {2} 年，建议重新确认账户状态。".format(
                    label, int(verified), int(current_year - verified)),
            })
    return {
        "issues": issues,
        "count": len(issues),
        "statement": ("未发现扣款方式相关记录问题。" if not issues
                      else "发现 {0} 条扣款方式相关记录问题。".format(len(issues))),
    }


# --------------------------------------------------------------------------- #
# 待办清单组装
# --------------------------------------------------------------------------- #
def build_todos(coverage, conflicts, capacity, member_cov, timeline, beneficiary, autopay):
    """把各分项发现汇总为按紧急度排序的待办清单。

    紧急度分档：30 天内 / 90 天内 / 年度事项。

    Args:
        coverage: 保障缺口分析结果。
        conflicts: 缴费日冲突分析结果。
        capacity: 缴费能力占比结果。
        member_cov: 成员覆盖分析结果。
        timeline: 时间节点分析结果。
        beneficiary: 受益人分析结果。
        autopay: 自动扣款分析结果。

    Returns:
        dict，含三个分档的列表。
    """
    todos = {"30天内": [], "90天内": [], "年度事项": []}

    def add(bucket, title, detail, severity="中", due=None, days=None):
        """向指定分档追加一条待办。

        Args:
            bucket: 分档名称。
            title: 标题。
            detail: 详情。
            severity: 严重度 高/中/低。
            due: 截止日期字符串。
            days: 剩余天数。
        """
        todos[bucket].append({
            "title": title,
            "detail": detail,
            "severity": severity,
            "due_date": due,
            "days_left": days,
        })

    for item in timeline["upcoming_payments"]:
        days = item["days_left"]
        if days <= 30:
            bucket = "30天内"
            severity = "高"
        elif days <= 90:
            bucket = "90天内"
            severity = "中"
        else:
            continue
        auto_text = "已开启自动扣款，请提前确认账户余额" if item["auto_pay"] else "未开启自动扣款，需手动缴费"
        add(bucket, "确认 {0} 的年缴扣款".format(item["policy"]),
            "{0} 应缴 {1:,.0f} 元（{2}）。".format(item["due_date"], item["annual_premium"], auto_text),
            severity=severity, due=item["due_date"], days=days)

    for item in timeline["grace_periods"]:
        days = item["days_left"]
        if days <= 30:
            add("30天内", "核对 {0} 的宽限期起止".format(item["policy"]),
                item["statement"], severity="高",
                due=item["grace_end_date"], days=days)

    for item in timeline["lapsed_policies"]:
        severity = "高" if item["beyond_reinstatement_threshold"] else "中"
        add("年度事项", "核实 {0} 的当前状态".format(item["policy"]),
            item["statement"], severity=severity)

    for item in timeline["dormant_policies"]:
        add("年度事项", "核实 {0} 是否仍在保障中".format(item["policy"]),
            item["statement"], severity="中")

    for item in timeline["maturity"]:
        if item["status"] == "推算的保障年度已过":
            add("年度事项", "核对 {0} 的续保与保障年度".format(item["policy"]),
                item["statement"], severity="中")
        elif item["status"] == "推算的保障年度为本年度":
            add("90天内", "确认 {0} 的续保状态".format(item["policy"]),
                item["statement"], severity="中")

    for item in beneficiary["issues"]:
        add("年度事项", "补充 {0} 的受益人信息".format(item["policy"]),
            item["statement"], severity="高")

    for item in autopay["issues"]:
        severity = "高" if item["issue"] in ("已开启自动扣款但未登记扣款账户", "未确认扣款方式") else "中"
        add("年度事项", "核对 {0} 的扣款方式".format(item["policy"]),
            item["statement"], severity=severity)

    for group in conflicts["same_day_groups"]:
        add("年度事项", "分散 {0} 日的集中扣款".format(group["pay_day"]),
            group["statement"], severity="中")

    for group in conflicts["same_month_groups"]:
        add("年度事项", "检查 {0} 的扣款集中情况".format(group["pay_month"]),
            group["statement"], severity="低")

    if capacity.get("ratio") is not None and capacity["ratio"] > PREMIUM_INCOME_ALERT_RATIO:
        add("年度事项", "复核家庭年缴保费占收入比例",
            "{0} {1}".format(capacity["statement"], capacity["status"]), severity="中")

    for item in coverage["items"]:
        if item["risk"] == "医疗" and not item["has_medical"]:
            add("年度事项", "确认家庭是否有医疗类保障记录",
                item["statement"], severity="高")
        elif item["risk"] in ("重疾", "意外") and item.get("multiple") is not None:
            if item["status"].startswith("低于"):
                add("年度事项", "对照 {0} 保额与参考区间".format(item["risk"]),
                    "{0} {1}".format(item["statement"], item["reference_text"]), severity="中")

    for item in member_cov["uncovered_members"]:
        add("年度事项", "确认 {0} 的保障记录".format(item["member"]),
            item["statement"], severity="高")

    for item in member_cov["structure_gaps"]:
        add("年度事项", "记录 {0} 的保障结构差异".format(item["member"]),
            item["statement"], severity="中")

    for bucket in URGENCY_BUCKETS:
        todos[bucket].sort(key=lambda x: (
            SEVERITY_ORDER.get(x["severity"], 9),
            x["days_left"] if x["days_left"] is not None else 9999,
        ))
    return todos


# --------------------------------------------------------------------------- #
# 报告组装与文本渲染
# --------------------------------------------------------------------------- #
def run_audit(data, today: date):
    """执行完整体检流程并返回报告字典。

    Args:
        data: 顶层输入字典。
        today: 当前日期。

    Returns:
        dict，完整报告。
    """
    coverage = analyze_coverage_gap(data)
    conflicts = analyze_payment_conflicts(data)
    capacity = analyze_payment_capacity(data)
    member_cov = analyze_member_coverage(data)
    timeline = analyze_timeline(data, today)
    beneficiary = analyze_beneficiaries(data)
    autopay = analyze_auto_pay(data, today)
    todos = build_todos(coverage, conflicts, capacity, member_cov, timeline, beneficiary, autopay)

    policies = data.get("policies") or []
    active = [p for p in policies if p.get("active", True)]
    total_todos = sum(len(v) for v in todos.values())

    summary = {
        "generated_at": today.isoformat(),
        "policy_total": len(policies),
        "policy_active": len(active),
        "policy_inactive": len(policies) - len(active),
        "annual_premium_total": sum(_num(p.get("annual_premium")) for p in active),
        "coverage_total": sum(_coverage(p) for p in active),
        "types_present": sorted({normalize_type(p.get("type") or p.get("product")) for p in active}),
        "todo_total": total_todos,
        "todo_30d": len(todos["30天内"]),
        "todo_90d": len(todos["90天内"]),
        "todo_annual": len(todos["年度事项"]),
        "findings_high": sum(1 for bucket in todos.values() for t in bucket if t["severity"] == "高"),
    }

    return {
        "meta": {
            "tool": "policy_audit.py",
            "version": "1.0.0",
            "today": today.isoformat(),
            "basis": "用户自行录入数据；仅做客观算术与规则判定",
        },
        "summary": summary,
        "coverage_gap": coverage,
        "payment_conflicts": conflicts,
        "payment_capacity": capacity,
        "member_coverage": member_cov,
        "timeline": timeline,
        "beneficiary": beneficiary,
        "auto_pay": autopay,
        "todos": todos,
        "disclaimer": DISCLAIMER,
    }


def _rule(char="-", width=72):
    """生成一行分隔线。

    Args:
        char: 分隔字符。
        width: 宽度。

    Returns:
        str，分隔线。
    """
    return char * width


def render_text(report) -> str:
    """把报告渲染为可读文本。

    Args:
        report: run_audit 返回的报告字典。

    Returns:
        str，多行文本。
    """
    s = report["summary"]
    lines = []
    lines.append("=" * 72)
    lines.append("家庭保单年度体检报告（生成日期：{0}）".format(s["generated_at"]))
    lines.append("=" * 72)
    lines.append("")
    lines.append("【一、总体概览】")
    lines.append("  保单总数：{0}（有效 {1} / 停缴或失效 {2}）".format(
        s["policy_total"], s["policy_active"], s["policy_inactive"]))
    lines.append("  有效保单保额合计：{0:,.0f} 元".format(s["coverage_total"]))
    lines.append("  有效保单年缴保费合计：{0:,.0f} 元".format(s["annual_premium_total"]))
    lines.append("  覆盖的保障类别：{0}".format("、".join(s["types_present"]) or "无"))
    lines.append("  待办事项：共 {0} 条（30 天内 {1} / 90 天内 {2} / 年度事项 {3}），其中高优先 {4} 条".format(
        s["todo_total"], s["todo_30d"], s["todo_90d"], s["todo_annual"], s["findings_high"]))
    lines.append("")

    lines.append("【二、保障结构对照（客观倍数，仅供对照）】")
    for item in report["coverage_gap"]["items"]:
        lines.append("  - {0}：{1}".format(item["risk"], item["statement"]))
        lines.append("    参考口径：{0}".format(item["reference_text"]))
        lines.append("    对照结果：{0}".format(item["status"]))
    lines.append("")

    lines.append("【三、缴费结构】")
    lines.append("  {0}".format(report["payment_conflicts"]["statement"]))
    for group in report["payment_conflicts"]["same_day_groups"]:
        lines.append("    同日扣款：{0}".format(group["statement"]))
    for group in report["payment_conflicts"]["same_month_groups"]:
        lines.append("    同月扎堆：{0}".format(group["statement"]))
    lines.append("  {0}".format(report["payment_capacity"]["statement"]))
    lines.append("  占比判定：{0}".format(report["payment_capacity"]["status"]))
    lines.append("")

    lines.append("【四、家庭成员保障覆盖】")
    cov = report["member_coverage"]
    lines.append("  纳入检查的成员数：{0}".format(cov["member_count"]))
    for row in cov["members"]:
        lines.append("  - {0}：有效保单 {1} 件，保额合计 {2:,.0f} 元，年缴 {3:,.0f} 元，类别 {4}".format(
            row["member"], row["active_count"], row["coverage_total"], row["annual_premium_total"],
            "、".join(row["covered_types"]) or "无"))
    for item in cov["uncovered_members"]:
        lines.append("    [无记录] {0}".format(item["statement"]))
    for item in cov["structure_gaps"]:
        lines.append("    [结构差异] {0}".format(item["statement"]))
    lines.append("")

    lines.append("【五、时间节点】")
    tl = report["timeline"]
    if tl["upcoming_payments"]:
        for item in tl["upcoming_payments"]:
            lines.append("  缴费倒计时：{0}".format(item["statement"]))
    else:
        lines.append("  未发现年缴保单的缴费节点（可能为趸缴或未录入缴费日）。")
    for item in tl["grace_periods"]:
        lines.append("  宽限期提示：{0}".format(item["statement"]))
    for item in tl["maturity"]:
        lines.append("  满期推算：{0}".format(item["statement"]))
    for item in tl["lapsed_policies"]:
        lines.append("  停缴或失效：{0}".format(item["statement"]))
    for item in tl["dormant_policies"]:
        lines.append("  长期未动：{0}".format(item["statement"]))
    lines.append("")

    lines.append("【六、受益人与扣款账户】")
    lines.append("  {0}".format(report["beneficiary"]["statement"]))
    for item in report["beneficiary"]["issues"]:
        lines.append("    - {0}".format(item["statement"]))
    lines.append("  {0}".format(report["auto_pay"]["statement"]))
    for item in report["auto_pay"]["issues"]:
        lines.append("    - {0}".format(item["statement"]))
    lines.append("")

    lines.append("【七、待办清单（按紧急度）】")
    for bucket in URGENCY_BUCKETS:
        items = report["todos"][bucket]
        lines.append("  ({0}) 共 {1} 条".format(bucket, len(items)))
        if not items:
            lines.append("    无")
        for idx, item in enumerate(items, 1):
            due = " 截止 {0}".format(item["due_date"]) if item["due_date"] else ""
            lines.append("    {0}. [{1}] {2}{3}".format(idx, item["severity"], item["title"], due))
            lines.append("       {0}".format(item["detail"]))
    lines.append("")

    lines.append(_rule("="))
    lines.append("免责声明：{0}".format(report["disclaimer"]))
    lines.append(_rule("="))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 命令行入口
# --------------------------------------------------------------------------- #
def load_json(path):
    """读取并解析输入 JSON 文件。

    Args:
        path: 文件路径。

    Returns:
        dict，解析后的数据。

    Raises:
        SystemExit: 文件不存在或 JSON 格式错误时退出。
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        sys.stderr.write("错误：找不到输入文件 {0}\n".format(path))
        raise SystemExit(2)
    except json.JSONDecodeError as exc:
        sys.stderr.write("错误：输入文件不是合法 JSON（{0}）：{1}\n".format(path, exc))
        raise SystemExit(2)


def parse_args(argv=None):
    """解析命令行参数。

    Args:
        argv: 参数列表，默认取 sys.argv。

    Returns:
        argparse.Namespace。
    """
    parser = argparse.ArgumentParser(
        description="家庭保单年度体检助手：客观核对保单保障倍数、缴费节点与失效风险，不做产品推荐与理赔判断。")
    parser.add_argument("--input", required=True, help="输入的 policies.json 路径")
    parser.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 形式输出报告")
    parser.add_argument("--today", default=None, help="覆盖当前日期（YYYY-MM-DD），便于复现与测试")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    """命令行主函数。

    Args:
        argv: 参数列表，默认取 sys.argv。

    Returns:
        int，进程退出码，0 表示成功。
    """
    args = parse_args(argv)
    data = load_json(args.input)

    if args.today:
        try:
            today = date.fromisoformat(args.today)
        except ValueError:
            sys.stderr.write("错误：--today 需要 YYYY-MM-DD 格式\n")
            return 2
    else:
        today = date.today()

    if not isinstance(data, dict):
        sys.stderr.write("错误：输入 JSON 的顶层结构必须是对象\n")
        return 2

    report = run_audit(data, today)

    if args.as_json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(report))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
