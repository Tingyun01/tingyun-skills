#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生育津贴待遇测算器 —— 属地口径 + 计发规则 + 差额自查。

用法::

    python scripts/maternity_benefit.py --input case.json
    python scripts/maternity_benefit.py --input case.json --json
    python scripts/maternity_benefit.py --list-regions
    python scripts/maternity_benefit.py --selfcheck

设计原则
--------
1. 只做客观算术与规则比对：按属地已采集口径计算应发金额、差额、比例档位。
   不做资格认定，不做仲裁判断，不预测审核结果。
2. 属地未采集时输出〔待补〕并列出"该去问经办机构哪几个问题"，绝不臆造数字。
3. 每个结论都写明依据条款出处（属地区 + 规则名），便于用户复核。
4. 仅依赖 Python 标准库，零第三方依赖；不联网、不读环境变量、不写文件。
5. 绝不输出 emoji；所有中文提示均为纯文本。
6. 政策数字以参保地经办机构当期口径为准，本脚本内置数据仅供测算参考。

输入 JSON 格式示例
------------------
{
  "region": "北京市",
  "identity": "在职职工",
  "scenario": "顺产",
  "base_wage": 14000,
  "own_wage": 14000,
  "contribution_months": 12,
  "social_avg_monthly_wage": 12000,
  "employer_paid_wage": 8000,
  "monthly_base_wage_flexible": null,
  "received_allowance": 32000
}

字段说明（缺失项按缺省处理，不会报错）
------------------------------------
region：属地名，须能匹配 scripts/regions.json 中的 key（可传"北京""Shanghai 上海市"等别名）。
identity：在职职工 / 灵活就业 / 失业人员 / 男职工配偶（未参保） / 其他。
scenario：顺产 / 难产顺产 / 多胞胎双胞胎 / 多胞胎三胞胎 / 终止妊娠 / 计划生育手术。
base_wage：计算基数原始值（单位上年度职工月平均工资；灵活就业填最低工资标准）。
own_wage：本人产假期间的月工资标准（用于差额补足比对，可选）。
contribution_months：生育前连续/累计缴费月数。
social_avg_monthly_wage：当地上年度全口径城镇单位就业人员月平均工资（用于托底封顶校验，可选）。
employer_paid_wage：单位已发放的产假期间工资（用于差额自查，可选）。
received_allowance：已实际收到的生育津贴金额（用于差额自查，可选）。
monthly_base_wage_flexible：宁夏灵活就业场景下的一类地区月最低工资标准（可选）。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

HERE = os.path.dirname(os.path.abspath(__file__))
REGIONS_FILE = os.path.join(HERE, "regions.json")

# 通用国家底线：女职工劳动保护特别规定
NATIONAL_BASE_DAYS = 98

# 属地别名 -> regions.json 的 key
ALIASES = {
    "北京": "北京市", "北京市": "北京市",
    "上海": "上海市", "上海市": "上海市",
    "佛山": "佛山市", "佛山市": "佛山市", "广东佛山": "佛山市",
    "阳江": "阳江市", "阳江市": "阳江市", "广东阳江": "阳江市",
    "宁德": "宁德市", "宁德市": "宁德市", "福建宁德": "宁德市",
    "宁夏": "宁夏回族自治区", "宁夏回族自治区": "宁夏回族自治区",
    "防城港": "防城港市", "防城港市": "防城港市", "广西防城港": "防城港市",
    "广东省": "佛山市", "广西": "防城港市", "福建省": "宁德市",
}

# 场景 -> (属地 days_by_scenario 的 key, 描述)
SCENARIO_KEYS = {
    "顺产": ("顺产", "顺产"),
    "难产": ("难产顺产", "难产（含剖宫产）"),
    "难产顺产": ("难产顺产", "难产（含剖宫产）"),
    "多胞胎双胞胎": ("多胞胎双胞胎", "双胞胎"),
    "双胞胎": ("多胞胎双胞胎", "双胞胎"),
    "多胞胎三胞胎": ("多胞胎三胞胎", "三胞胎"),
    "三胞胎": ("多胞胎三胞胎", "三胞胎"),
}

TODO = "〔待补〕"


def load_regions():
    with open(REGIONS_FILE, encoding="utf-8") as f:
        return json.load(f)


def resolve_region(name, regions):
    if not name:
        return None
    n = str(name).strip()
    if n in regions:
        return n
    for k in regions:
        if k.startswith("_"):
            continue
        if n in k or k in n:
            return k
    if n in ALIASES:
        return ALIASES[n]
    for a, target in ALIASES.items():
        if a in n:
            return target
    return None


def find_scenario_days(reg, scenario):
    """返回 (天数, 依据说明)。找不到返回 (None, 说明)。"""
    dbs = reg.get("days_by_scenario") or {}
    label = scenario
    if scenario in SCENARIO_KEYS:
        key, label = SCENARIO_KEYS[scenario]
        if key in dbs:
            return dbs[key], "属地情形表：%s = %d 天" % (label, dbs[key])
    if scenario == "终止妊娠":
        for g in (reg.get("gestation_termination_days") or []):
            if scenario in g.get("condition", "") or g.get("condition") in scenario:
                if g.get("days"):
                    return g["days"], "属地终止妊娠口径：%s = %d 天" % (g["condition"], g["days"])
                return None, "属地终止妊娠口径：%s（%s）" % (g["condition"], g.get("note") or "天数需按医疗机构意见确定")
        return None, "该属地终止妊娠天数未在采集表中单列"
    if scenario == "计划生育手术":
        return None, "该属地计划生育手术休假天数需按手术类型单独核对"
    if scenario in dbs:
        return dbs[scenario], "属地情形表：%s = %d 天" % (scenario, dbs[scenario])
    return None, "该属地该情形的天数未采集"


def apply_ratio_tiers(reg, months, identity):
    """按属地分档比例返回 (比例, 说明)。无分档规则返回 (None, 说明)。"""
    tiers = reg.get("ratio_tiers") or []
    if not tiers:
        return None, "该属地未采集分档比例规则（多数为全额或由单位支付）"
    scope_filter = None
    if identity == "灵活就业":
        scope_filter = "灵活就业"
    elif identity == "在职职工":
        scope_filter = "单位职工"
    best = None
    for t in tiers:
        if scope_filter and t.get("scope") and t["scope"] != scope_filter:
            continue
        lo = t.get("min_months") or 0
        hi = t.get("max_months")
        if months is None:
            continue
        if months >= lo and (hi is None or months <= hi):
            best = t
            break
    if not best:
        return None, "缴费月数 %s 未匹配到该属地的比例档位" % months
    rng = "%d-%d 个月" % (best.get("min_months") or 0, best["max_months"]) if best.get("max_months") else "满 %d 个月" % (best.get("min_months") or 0)
    return best.get("ratio"), "%s：连续参保 %s，按 %s 比例享受" % (best.get("scope") or "", rng, best.get("ratio"))


def calc(case, regions):
    findings = []
    out = {"属地": None, "口径来源": None, "结论": []}

    reg_name = resolve_region(case.get("region"), regions)
    if not reg_name:
        out["结论"].append({
            "项": "属地",
            "结果": TODO,
            "说明": "未采集该属地口径，无法测算金额。请用下方三个问题去问参保地经办机构。",
            "依据": "属地未采集",
        })
        out["待人工确认"] = [
            "本人生育/流产时所在用人单位上年度职工月平均工资是多少（用于计算基数）",
            "本次应享受的生育津贴天数是多少天（国家基础98天 + 地方奖励假 + 难产加假 + 多胞胎加假）",
            "生育前连续缴费需满几个月才能由基金支付；不满几个月时津贴由谁出",
        ]
        return out

    reg = regions[reg_name]
    out["属地"] = reg.get("name")
    out["口径来源"] = reg.get("source_url")
    out["口径核验日期"] = reg.get("verified_date")
    out["属地特别提示"] = reg.get("notes")

    identity = case.get("identity") or "在职职工"
    scenario = case.get("scenario") or "顺产"
    base_wage = case.get("base_wage")
    own_wage = case.get("own_wage")
    months = case.get("contribution_months")
    social_avg = case.get("social_avg_monthly_wage")
    employer_paid = case.get("employer_paid_wage")
    received = case.get("received_allowance")

    # 1) 天数
    days, days_src = find_scenario_days(reg, scenario)
    if days is None:
        out["结论"].append({"项": "应享受天数", "结果": TODO, "说明": days_src, "依据": "属地口径未采集该情形"})
        out["待人工确认"] = out.get("待人工确认", []) + ["本次应享受的生育津贴天数（%s情形）" % scenario]
    else:
        out["结论"].append({"项": "应享受天数", "结果": "%d 天" % days, "说明": days_src, "依据": reg.get("name") + " 生育津贴计发口径"})
        out["应享受天数"] = days

    # 2) 基数（含托底封顶）
    base_final = base_wage
    base_note = ""
    base_src = ""
    if base_wage is None:
        out["结论"].append({"项": "计算基数", "结果": TODO, "说明": "未提供基数原始值", "依据": "缺输入"})
    else:
        base_final = float(base_wage)
        base_src = "输入值"
        fl = reg.get("base_floor_ratio")
        cp = reg.get("base_cap_ratio")
        if social_avg is not None and (fl or cp):
            social_avg = float(social_avg)
            if fl and base_final < social_avg * fl:
                base_final = social_avg * fl
                base_note = "低于社平工资 %.0f%% 下限，已按托底值 %.2f 元计" % (fl * 100, base_final)
            if cp and base_final > social_avg * cp:
                base_final = social_avg * cp
                base_note = "高于社平工资 %.0f 倍上限，已按封顶值 %.2f 元计" % (cp, base_final)
        out["结论"].append({
            "项": "计算基数",
            "结果": "%.2f 元/月" % base_final,
            "说明": base_note or "按 %s 口径，未触发托底或封顶" % {
                "employer_avg_wage": "单位上年度职工月平均工资",
                "social_avg_wage": "全口径城镇单位就业人员月平均工资",
                "min_wage": "最低工资标准",
            }.get(reg.get("base_type"), "属地基数口径"),
            "依据": base_src + (" / " + base_note if base_note else ""),
        })
    out["计算基数"] = base_final

    # 3) 缴费比例
    ratio, ratio_src = apply_ratio_tiers(reg, months, identity)
    if ratio is not None:
        out["结论"].append({"项": "缴费比例档位", "结果": "%.0f%%" % (ratio * 100), "说明": ratio_src, "依据": reg.get("name") + " 生育保险政策"})

    # 4) 缴费不足的承担方
    req = reg.get("contribution_months_required")
    if req is not None and months is not None:
        if months < req:
            payer = reg.get("shortfall_payer")
            payer_txt = {"fund": "生育保险基金", "employer": "用人单位"}.get(payer, TODO)
            out["结论"].append({
                "项": "缴费连续性",
                "结果": "不足 %d 个月（当前 %d 个月）" % (req, months),
                "说明": ("津贴由%s支付" % payer_txt) if payer else "津贴承担方需向经办机构确认",
                "依据": reg.get("name") + " 申领条件" + ("；" + reg.get("shortfall_repay_after") if reg.get("shortfall_repay_after") else ""),
            })
            findings.append({
                "级别": "高",
                "问题": "生育前连续缴费不足 %d 个月" % req,
                "后果": "津贴可能不由基金支付，改由用人单位支付；单位不付即为个人损失",
                "建议": "确认是否满足补支条件（如属地允许：%s）" % (reg.get("shortfall_repay_after") or "需问经办机构"),
            })
        else:
            out["结论"].append({
                "项": "缴费连续性",
                "结果": "满足（需 %d 个月，实际 %d 个月）" % (req, months),
                "说明": "满足基金支付条件（仍需核对是否满足'连续'而非仅'累计'）",
                "依据": reg.get("name") + " 申领条件",
            })
    elif req is not None:
        out["结论"].append({"项": "缴费连续性", "结果": TODO, "说明": "未提供缴费月数", "依据": "缺输入"})

    # 5) 金额
    if base_final is not None and days is not None:
        daily = base_final / 30.0
        gross = daily * days
        final = gross * ratio if ratio is not None else gross
        out["日计发标准"] = round(daily, 2)
        out["应发生育津贴"] = round(final, 2)
        out["计算过程"] = "%.2f ÷ 30 × %d 天%s = %.2f 元" % (
            base_final, days, (" × %.0f%%" % (ratio * 100)) if ratio is not None else "", final)
        out["结论"].append({
            "项": "应发生育津贴",
            "结果": "%.2f 元" % final,
            "说明": out["计算过程"],
            "依据": reg.get("name") + " 生育津贴计发口径",
        })

        # 6) 差额（单位补足）
        if own_wage is not None and reg.get("employer_topup"):
            own_total = float(own_wage) / 30.0 * days
            if final < own_total:
                gap = own_total - final
                out["结论"].append({
                    "项": "单位应补足差额",
                    "结果": "%.2f 元" % gap,
                    "说明": "本人产假工资标准测算 %.2f 元，高于津贴 %.2f 元；属地明文差额由用人单位补足" % (own_total, final),
                    "依据": reg.get("name") + " 生育津贴与产假工资就高不就低规定",
                })
                findings.append({
                    "级别": "高",
                    "问题": "津贴低于本人产假工资标准，差额 %.2f 元单位未补足" % gap,
                    "后果": "少拿 %.2f 元；多数属地明文'差额由用人单位补足'" % gap,
                    "建议": "以工资流水与津贴到账记录为据向单位书面主张；协商不成可咨询 12348",
                })
            else:
                out["结论"].append({
                    "项": "单位应补足差额",
                    "结果": "无差额",
                    "说明": "津贴 %.2f 元不低于本人产假工资测算值 %.2f 元" % (final, own_total),
                    "依据": reg.get("name") + " 就高不就低规定",
                })

        # 7) 实发差额
        if received is not None:
            diff = float(received) - final
            if abs(diff) >= 1:
                out["结论"].append({
                    "项": "已收与应发差额",
                    "结果": "%+.2f 元" % diff,
                    "说明": "已收 %.2f 元 vs 应发 %.2f 元" % (float(received), final),
                    "依据": "按上述口径测算",
                })
                findings.append({
                    "级别": "高",
                    "问题": "已收金额与测算应发相差 %+.2f 元" % diff,
                    "后果": "多收需退回；少收需向单位或经办机构主张",
                    "建议": "核对基数口径是否与单位申报一致，再核对天数口径",
                })
            else:
                out["结论"].append({
                    "项": "已收与应发差额",
                    "结果": "基本一致",
                    "说明": "已收 %.2f 元 vs 应发 %.2f 元" % (float(received), final),
                    "依据": "按上述口径测算",
                })

        if employer_paid is not None and own_wage is not None and reg.get("employer_topup"):
            paid_total = float(employer_paid) / 30.0 * days
            if paid_total + final < paid_total + own_total - 1 and final < own_total:
                pass
            out["单位已发产假工资"] = "%.2f 元（按 %.2f 元/月 × %d 天测算）" % (paid_total, float(employer_paid), days)

    # 8) 基数口径提醒（最高频争议）
    if base_wage is not None and own_wage is not None and float(base_wage) > float(own_wage):
        findings.append({
            "级别": "提示",
            "问题": "计算基数 %.2f 元高于本人工资 %.2f 元" % (float(base_wage), float(own_wage)),
            "后果": "属地明文按'单位上年度职工月平均工资'而非本人工资计算，此处对本人有利",
            "建议": "核对单位申报的基数是否真实；单位整体压低基数会影响所有女职工",
        })
    if base_wage is not None and own_wage is not None and float(base_wage) < float(own_wage):
        findings.append({
            "级别": "中",
            "问题": "计算基数 %.2f 元低于本人工资 %.2f 元" % (float(base_wage), float(own_wage)),
            "后果": "单位可能压低了缴费基数，导致津贴基数偏低",
            "建议": "核对单位上年度全部参保职工月平均工资的真实数；必要时咨询社保稽核口径",
        })

    out["自查提示"] = findings
    if not findings:
        out["自查提示"] = [{"级别": "提示", "问题": "未发现明显异常", "后果": "-", "建议": "仍需核对单位申报基数与属地天数口径"}]
    return out


def national_checklist():
    """全国统一口径：育儿补贴 + 个税专项附加扣除。"""
    return [
        {
            "项": "育儿补贴（全国统一）",
            "标准": "每孩每年 3600 元（每孩每月 300 元），至年满 3 周岁",
            "覆盖": "不分城乡/民族/区域，不分一孩二孩三孩，多孩可叠加，免征个税，不计入低保家庭收入",
            "规模": "2026 年中央财政下达 999 亿元（较上年 +10.6%），全年各级约 1100 亿元",
            "进度": "截至 2026-07-21 已提交申请 2751 万条、已审核发放 2516 万人",
            "动作": "通过支付宝、微信或省级政务服务平台登录'育儿补贴信息管理系统'申领；2026 年新增一键续领；2022-2024 年出生的首次申请截止日已延长至 2026-12-31",
            "依据": "https://www.gov.cn/yaowen/liebiao/202607/content_7076217.htm",
        },
        {
            "项": "婴幼儿个税专项附加扣除（全国统一）",
            "标准": "每孩每月抵扣 2000 元个税额度",
            "覆盖": "家中有 3 周岁以下婴幼儿，父母缴纳个税即可抵扣",
            "动作": "每年个税汇算期间在个税 APP 一键申报",
            "依据": "https://news.qq.com/rain/a/20260610A07AMB00",
        },
        {
            "项": "生育津贴直接到个人账户",
            "标准": "2025 年 12 月起全国多数统筹区已实现由医保部门直接打到个人账户",
            "覆盖": "各地推进程度不一，部分属地仍有单位先行垫付环节（例：广东阳江 2025-12-01 前分娩的由单位垫付）",
            "动作": "确认本属地是否已直发个人；未直发的需向单位索取垫付凭证",
            "依据": "https://www.ce.cn/xwzx/gnsz/gdxw/202601/t20260127_2732086.shtml",
        },
        {
            "项": "生育医疗费用待遇（与津贴并列，非替代）",
            "标准": "生育医疗费用待遇与生育津贴是两项并列待遇，不是二选一",
            "覆盖": "各地对分娩费用报销比例、起付线、个人自付部分的处理不同",
            "动作": "分娩后核对是否已联网结算；未结算的按属地时限申请零星报销（例：广东阳江为次日起 3 年内）",
            "依据": "http://www.yangjiang.gov.cn/yjylbzj/attachment/0/83/83359/925446.pdf",
        },
    ]


def selfcheck():
    """合成用例自检：不依赖外部文件内容以外的任何东西。"""
    regions = load_regions()
    checks = []

    # 1) 已知属地能解析
    cases = [
        ({"region": "北京", "identity": "在职职工", "scenario": "顺产", "base_wage": 14000,
          "own_wage": 14000, "contribution_months": 12, "social_avg_monthly_wage": 12000,
          "employer_paid_wage": 8000, "received_allowance": 32000}, "北京市"),
        ({"region": "上海", "identity": "灵活就业", "scenario": "顺产", "base_wage": 12000,
          "contribution_months": 13}, "上海市"),
        ({"region": "宁德", "identity": "在职职工", "scenario": "顺产", "base_wage": 8000,
          "contribution_months": 8}, "宁德市"),
        ({"region": "不存在的属地", "scenario": "顺产", "base_wage": 5000}, None),
    ]
    for case, expect in cases:
        r = calc(case, regions)
        got = r.get("属地")
        ok = (got is not None and expect is not None and expect in got) if expect \
            else (r["结论"][0]["结果"] == TODO)
        checks.append(("属地解析 %s" % case.get("region"), ok, "期望=%s 实得=%s" % (expect, got)))

    # 2) 北京算术：14000/30*128 = 59733.33；托底检查 14000>12000*0.6=7200 且 <12000*3=36000
    r = calc(cases[0][0], regions)
    checks.append(("北京天数=128", r.get("应享受天数") == 128, str(r.get("应享受天数"))))
    expect_amt = round(14000 / 30.0 * 128, 2)
    checks.append(("北京金额≈%.2f" % expect_amt,
                   abs((r.get("应发生育津贴") or 0) - expect_amt) < 0.05,
                   str(r.get("应发生育津贴"))))
    # 3) 差额识别：单位补足差额（津贴 < 本人产假工资）与实收差额 两类都要能抓出来
    gap_case = {"region": "北京", "identity": "在职职工", "scenario": "顺产", "base_wage": 14000,
                "own_wage": 16000, "contribution_months": 12, "social_avg_monthly_wage": 12000,
                "received_allowance": 32000}
    r = calc(gap_case, regions)
    issues = " | ".join(str(x.get("问题")) for x in r.get("自查提示", []))
    expect_gap = round(16000 / 30.0 * 128 - 14000 / 30.0 * 128, 2)
    checks.append(("识别出单位补足差额(应≈%.2f)" % expect_gap,
                   "单位未补足" in issues, issues[:160]))
    checks.append(("识别出已收少于应发", "已收金额与测算应发相差" in issues, issues[:160]))

    # 3) 宁德比例分档：8 个月 -> 50%
    r = calc(cases[2][0], regions)
    ratio_txt = " ".join(str(c.get("结果")) for c in r.get("结论", []))
    checks.append(("宁德 8 个月 -> 50% 档", "50%" in ratio_txt, ratio_txt[:120]))

    # 4) 缴费不足被识别
    r = calc({"region": "北京", "scenario": "顺产", "base_wage": 14000, "contribution_months": 5}, regions)
    hi = [x for x in r.get("自查提示", []) if x.get("级别") == "高"]
    checks.append(("北京缴费 5 个月不足 9 个月被标高风险", len(hi) >= 1, str(hi[:1])[:140]))

    # 5) 未知属地输出待补而非报错
    r = calc(cases[3][0], regions)
    checks.append(("未知属地输出待补 + 人工确认清单",
                   r["结论"][0]["结果"] == TODO and len(r.get("待人工确认", [])) == 3,
                   str(r.get("待人工确认"))[:140]))

    # 6) 全国清单存在
    nc = national_checklist()
    checks.append(("全国统一清单 4 项", len(nc) == 4, str(len(nc))))

    # 7) 每个已采集属地字段完整性
    bad = []
    for k, v in regions.items():
        if k.startswith("_"):
            continue
        for f in ("name", "source_url", "verified_date", "base_type"):
            if not v.get(f):
                bad.append("%s 缺 %s" % (k, f))
    checks.append(("属地必需字段完整", not bad, "; ".join(bad) or "全部完整"))

    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print("[%s] %s%s" % ("PASS" if ok else "FAIL", name, "" if ok else "  -> " + detail))
    print("自检结果：%d/%d 通过" % (passed, len(checks)))
    return 0 if passed == len(checks) else 1


def main():
    if "--selfcheck" in sys.argv:
        sys.exit(selfcheck())
    if "--list-regions" in sys.argv:
        regions = load_regions()
        for k, v in regions.items():
            if k.startswith("_"):
                continue
            print("%-14s 天数表=%-3s 基数=%-20s 需缴月=%-5s 核验=%s"
                  % (k, len(v.get("days_by_scenario") or {}),
                     v.get("base_type"), v.get("contribution_months_required"), v.get("verified_date")))
        print("共 %d 个属地已采集" % len([k for k in regions if not k.startswith("_")]))
        return 0

    path = None
    as_json = "--json" in sys.argv
    for i, a in enumerate(sys.argv):
        if a == "--input" and i + 1 < len(sys.argv):
            path = sys.argv[i + 1]
        elif a.startswith("--input="):
            path = a.split("=", 1)[1]
    if not path:
        print(__doc__)
        print("错误：缺少 --input <json文件>")
        return 2

    with open(path, encoding="utf-8") as f:
        case = json.load(f)
    regions = load_regions()
    result = calc(case, regions)
    result["全国统一口径清单"] = national_checklist()
    result["免责"] = "本测算按已采集的属地公开口径做算术推演，不构成资格认定、金额承诺或法律意见；政策口径以参保地经办机构当期规定为准，标注〔待补〕项必须人工复核。"

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print("=" * 70)
    print("生育津贴待遇测算")
    print("=" * 70)
    print("属地：%s" % (result.get("属地") or TODO))
    if result.get("口径来源"):
        print("口径来源：%s（核验日期 %s）" % (result["口径来源"], result.get("口径核验日期")))
    if result.get("属地特别提示"):
        print("属地提示：%s" % result["属地特别提示"])
    print("-" * 70)
    for c in result.get("结论", []):
        print("  %-14s %s" % (c["项"], c["结果"]))
        if c.get("说明"):
            print("  %-14s %s" % ("", c["说明"]))
        if c.get("依据"):
            print("  %-14s 依据：%s" % ("", c["依据"]))
    if result.get("待人工确认"):
        print("-" * 70)
        print("需人工确认（请向参保地经办机构逐条问）：")
        for q in result["待人工确认"]:
            print("  - %s" % q)
    print("-" * 70)
    print("自查提示：")
    for f_ in result.get("自查提示", []):
        print("  [%s] %s" % (f_["级别"], f_["问题"]))
        if f_.get("后果") and f_["后果"] != "-":
            print("      后果：%s" % f_["后果"])
        if f_.get("建议"):
            print("      建议：%s" % f_["建议"])
    print("-" * 70)
    print("全国统一口径（与属地津贴并列，不重复计算）：")
    for n in result.get("全国统一口径清单", []):
        print("  * %s —— %s" % (n["项"], n["标准"]))
        print("      %s" % n["动作"])
    print("=" * 70)
    print(result["免责"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
