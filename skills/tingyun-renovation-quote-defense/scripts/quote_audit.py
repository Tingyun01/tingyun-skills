#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quote_audit.py — 装修报价单要素对照与活口条款审计（零依赖标准库）

用途：
    把装修公司给出的报价单，按"项目 / 单位 / 数量 / 单价 / 是否按实结算 /
    是否写明品牌型号"六要素拆解，逐项标出留了后路的"活口条款"，
    按付款节点倒推被卡住的风险，给出增项风险的**参考区间**估算，
    并输出可直接使用的追问话术清单。

    定位：报价单要素自查与条款参考。
    不做工程造价鉴定、不评价工程合理性、不出具法律意见。

用法：
    python quote_audit.py --input quote.json
    python quote_audit.py --input quote.json --json
    python quote_audit.py --input quote.json --settle-coeff 0.15 --high-ratio 0.6

输入 JSON 示例（示例数据，非真实项目）：
    {
      "budget": 200000,
      "payment_schedule": [0.3, 0.3, 0.2, 0.15, 0.05],
      "quotes": [
        {"project": "拆除", "unit": "㎡", "qty": 85, "price": 55,
         "settle_actual": false, "brand_spec": "", "note": ""},
        {"project": "水电改造", "unit": "米", "qty": 400, "price": 120,
         "settle_actual": true, "brand_spec": "",
         "note": "按实际发生"},
        {"project": "综合费用", "unit": "项", "qty": 1, "price": 6000,
         "settle_actual": true, "brand_spec": "", "note": "含零星辅材"}
      ]
    }

字段说明：
    budget             可选，装修预算总额（元），用于对比总价
    payment_schedule  可选，付款比例数组（如 [0.3, 0.35, 0.2, 0.1, 0.05]）
    quotes             必填，报价明细数组
      project        项目名称（字符串）
      unit           计量单位（字符串，如 ㎡ / 米 / 项 / 延米）
      qty            数量（数字）
      price          单价（元，数字）
      settle_actual  是否按实结算（布尔；缺省视为 false）
      brand_spec     品牌 / 型号 / 规格（字符串，空字符串视为未写明）
      note           备注（字符串，可空）
    categories        可选，{"项目名关键词": "大类名"}，用于单位混用检测
                      未提供时使用内置大类关键词表

输出：
    默认输出人类可读文本报告；加 --json 输出 JSON 报告（UTF-8）。

退出码：
    0  正常完成
    2  输入文件不存在 / JSON 非法 / 参数错误（友好提示，不抛堆栈）

重要声明：
    增项区间的"经验系数"来自装修行业普遍反映与常见市场做法整理，
    仅用于给出量级参考，**不是造价依据，不构成工程造价鉴定或咨询**。
"""

import argparse
import json
import os
import sys

# ---------------------------------------------------------------- 输出编码
# Windows 控制台默认编码可能不是 UTF-8，先重配 stdout，避免中文报错。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
except AttributeError:  # pragma: no cover - Python < 3.7 兜底
    pass


# ---------------------------------------------------------------- 经验系数表
# 以下系数为行业普遍反映的常见经验值，仅用于给出**量级参考**，
# 不是造价依据，不构成工程造价鉴定。口径为"该项最终实际支出
# 相对报价单所列金额的常见上浮比例"。
SETTLE_COEFF_DEFAULT = {
    "default": 0.15,
    "拆除": 0.20,
    "拆改": 0.20,
    "水电": 0.25,
    "防水": 0.15,
    "瓦工": 0.12,
    "木工": 0.15,
    "油漆": 0.10,
    "吊顶": 0.12,
    "地面": 0.12,
    "铺贴": 0.12,
    "管理费": 0.10,
    "垃圾清运": 0.30,
    "清运": 0.30,
    "设计费": 0.05,
}

# 品牌不明（未写明品牌型号）的常见上浮参考系数，同样只是经验量级。
BRAND_MISSING_COEFF = 0.12

# 名称笼统项的常见上浮参考系数。
VAGUE_NAME_COEFF = 0.15

# 增项不设上限 / 以实际发生为准 —— 这是最危险的一类，单独抬高系数。
OPEN_ENDED_COEFF = 0.25

# 大类关键词 -> 大类名（用于单位混用检测）
CATEGORY_KEYWORDS = [
    (("拆除", "拆改", "拆墙"), "拆改"),
    (("水电", "水路", "电改造", "电路", "给排水"), "水电"),
    (("防水", "防水"), "防水"),
    (("瓦工", "贴砖", "铺贴", "砌筑", "找平"), "瓦工"),
    (("木工", "吊顶", "石膏板", "柜体", "木作", "踢脚线"), "木工"),
    (("油漆", "涂装", "乳胶漆", "腻子"), "油漆"),
    (("地面", "地板", "地砖", "石材"), "地面"),
    (("门", "门窗", "套装门", "橱柜门"), "门窗"),
    (("灯具", "灯"), "灯具"),
    (("洁具", "马桶", "台盆", "浴室柜"), "洁具"),
    (("开关", "插座", "面板"), "开关插座"),
    (("暖气", "地暖", "采暖"), "暖气"),
    (("空调", "新风", "通风"), "空调设备"),
    (("燃气", "烟道", "排烟"), "燃气烟道"),
    (("垃圾", "清运", "垃圾清运"), "垃圾清运"),
    (("管理费", "管理"), "管理费"),
    (("设计费", "设计"), "设计费"),
    (("成品保护", "保洁", "开荒"), "收尾保洁"),
]

# 常见单位（同大类下单位不一致即为混用嫌疑）
NORMAL_UNITS = {
    "拆改": {"㎡", "米", "项", "个", "处"},
    "水电": {"米", "项", "个", "处"},
    "防水": {"㎡", "项", "处"},
    "瓦工": {"㎡", "项"},
    "木工": {"㎡", "米", "项", "延米", "个"},
    "油漆": {"㎡", "项", "延米"},
    "地面": {"㎡", "项"},
    "门窗": {"樘", "个", "㎡", "套", "项"},
    "灯具": {"个", "套", "项"},
    "洁具": {"套", "个", "项"},
    "开关插座": {"个", "项"},
    "暖气": {"㎡", "组", "项"},
    "空调设备": {"台", "个", "项"},
    "燃气烟道": {"米", "项", "个"},
    "垃圾清运": {"车", "次", "项", "立方"},
    "管理费": {"项", "天", "月", "%"},
    "设计费": {"项", "㎡", "元"},
    "收尾保洁": {"㎡", "项"},
}

# 计量族：同一大类下若出现不同计量族，说明换算口径可能不一致
UNIT_FAMILY = {
    "㎡": "面积", "平米": "面积", "平方": "面积",
    "米": "长度", "延米": "长度", "m": "长度",
    "项": "整体", "个": "个数", "套": "套数", "樘": "套数",
    "台": "台数", "处": "处数", "次": "车次", "车": "车次",
    "立方": "体积", "方": "体积", "组": "组数", "天": "时间",
    "月": "时间", "%": "比例", "元": "金额",
}

# 名称笼统关键词
VAGUE_KEYWORDS = ("综合", "杂项", "其他", "零星", "辅助", "等", "若干",
                  "含以上", "相关费用", "其它", "附加费", "配合费")

# 需要写明品牌 / 型号 / 规格的大类。
# 纯人工或纯服务类项目（拆除、清运、管理费、设计费、保洁等）不涉及品牌，
# 对其判"品牌不明"属于误报，故排除。
BRAND_REQUIRED_CATEGORIES = {
    "水电", "防水", "瓦工", "木工", "油漆", "地面", "门窗",
    "灯具", "洁具", "开关插座", "暖气", "空调设备",
}

# 只写修饰词、不含具体品牌 / 型号 / 数字规格的品牌表述（常见模糊写法）
BRAND_VAGUE_WORDS = ("优质", "合资", "一线", "品牌", "国标", "进口",
                     "环保", "高级", "知名", "大厂", "主流", "顶级")

# 活口高危关键词（在 note / project 里出现即说明"以实际发生为准"类表述）
OPEN_ENDED_KEYWORDS = ("按实", "实报", "实际发生", "据实", "以现场为准",
                       "以实际为准", "现场定", "暂估", "暂按", "预估")

# 常见增项类型与幅度参考（用于报告尾部提示，不参与金额计算）
ADDON_TYPE_HINTS = [
    ("拆改类", "承重结构/非承重墙认定差异、垃圾清运超量、成品保护补做"),
    ("水电类", "线管走线超米数、开槽回填超厚、点位增加、弱电箱外移"),
    ("防水类", "淋浴区与干区面积口径差异、地梁加做、包管附加"),
    ("瓦工类", "包管、包角、找平拉线、地砖上墙、斜切拼花"),
    ("木工类", "异形吊顶、灯槽、检修口、柜体超出投影面积"),
    ("辅料类", "瓷砖胶/水泥砂浆用量、界面剂、挂件、膨胀螺栓"),
    ("人工类", "拆除搬运、二次搬运、成品保护、垃圾装袋"),
    ("管理费类", "工期延长、进场频次增加、远程施工、重复进场"),
    ("垃圾清运费类", "车次不足、超距、电梯不可用时人工搬运"),
]


# ---------------------------------------------------------------- 工具函数
def _to_float(value):
    """把可能是字符串/None 的值安全转为 float，失败返回 0.0。"""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "").replace("，", ""))
    except (TypeError, ValueError):
        return 0.0


def _to_bool(value):
    """把多种真值写法（true/"是"/"按实"/1）统一转为 bool。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes", "y", "是", "按实", "按实际", "实报", "待定"):
            return True
    return False


def _is_vague_brand(brand_spec):
    """判断品牌栏是否只写了修饰词而没有可核对的型号 / 规格。

    例："优质石膏板""某品牌一线瓷砖""合资卫浴"——
    去掉修饰词后若不含任何数字或英文型号片段，视为品牌模糊。
    """
    if not brand_spec:
        return False
    residue = brand_spec
    for w in BRAND_VAGUE_WORDS:
        residue = residue.replace(w, "")
    has_code = any(ch.isdigit() for ch in residue)
    has_model = any("-" in part or part.isupper() and len(part) >= 2
                    for part in residue.replace("(", " ").replace(")", " ").split())
    return not has_code and not has_model


def _pick_category(project, categories):
    """根据项目名判断所属大类；categories 可由调用方覆盖。"""
    name = project or ""
    table = categories if categories else CATEGORY_KEYWORDS
    for keywords, cat in table:
        for kw in keywords:
            if kw in name:
                return cat
    return "其他"


def _coef_for(project, table, default):
    """按项目名匹配经验系数，命中返回该系数，否则返回默认值。"""
    name = project or ""
    best = default
    for key, value in table.items():
        if key != "default" and key in name:
            best = max(best, value)
    return best


# ---------------------------------------------------------------- 逐项审计
def audit_item(item, index, settle_coeff_table, categories=None):
    """审计单条报价项，返回该条的风险记录字典。

    识别规则：
      - settle_actual 为真 -> 活口项
      - brand_spec 为空     -> 品牌不明（仅对涉及材料的大类判定，
                               纯人工/服务类项目不做此项判定，避免误报）
      - 名称含笼统关键词   -> 名称笼统
      - qty<=0 或 price<=0 -> 待定项
      - 备注/名称含"以实际发生为准"类表述 -> 开口项
    """
    project = str(item.get("project", "") or "").strip()
    unit = str(item.get("unit", "") or "").strip()
    qty = _to_float(item.get("qty"))
    price = _to_float(item.get("price"))
    settle_actual = _to_bool(item.get("settle_actual"))
    brand_spec = str(item.get("brand_spec", "") or "").strip()
    note = str(item.get("note", "") or "").strip()
    amount = qty * price
    category = _pick_category(project, categories)
    brand_required = category in BRAND_REQUIRED_CATEGORIES

    flags = []          # 风险标签
    reasons = []        # 判定理由
    coeffs = []         # 参与估算的系数

    if settle_actual:
        flags.append("按实结算")
        reasons.append("标记为按实结算，最终金额随现场实际发生量变化")
        coeffs.append(_coef_for(project, settle_coeff_table,
                                settle_coeff_table.get("default", 0.15)))

    if not brand_spec and brand_required:
        flags.append("品牌不明")
        reasons.append("未写明品牌 / 型号 / 规格，实际可替换范围大")
        coeffs.append(BRAND_MISSING_COEFF)
    elif brand_spec and _is_vague_brand(brand_spec):
        flags.append("品牌模糊")
        reasons.append("品牌栏只写了“%s”一类修饰词，没有具体型号或规格"
                       % brand_spec)
        coeffs.append(BRAND_MISSING_COEFF)

    if any(kw in project for kw in VAGUE_KEYWORDS):
        flags.append("名称笼统")
        reasons.append("项目名称为概括性表述，无法核对其包含内容")
        coeffs.append(VAGUE_NAME_COEFF)

    if qty <= 0 or price <= 0:
        flags.append("待定项")
        reasons.append("数量或单价未确定，金额无法锁定")
        coeffs.append(OPEN_ENDED_COEFF)

    text_all = project + " " + note
    if any(kw in text_all for kw in OPEN_ENDED_KEYWORDS):
        if "按实结算" not in flags:
            flags.append("开口表述")
            reasons.append("出现“以实际发生/据实/暂估”类表述")
        coeffs.append(OPEN_ENDED_COEFF)

    # 品牌不明 + 按实结算 叠加，风险显著抬高
    if "按实结算" in flags and "品牌不明" in flags:
        flags.append("双活口叠加")
        reasons.append("既按实结算又未锁定品牌型号，金额上限完全开放")

    if not flags:
        return {
            "index": index,
            "project": project,
            "category": category,
            "unit": unit,
            "qty": qty,
            "price": price,
            "amount": round(amount, 2),
            "settle_actual": settle_actual,
            "brand_spec": brand_spec,
            "note": note,
            "flags": [],
            "reasons": [],
            "risk_level": "低",
            "coeff": 0.0,
            "risk_low": 0.0,
            "risk_high": 0.0,
            "ask": "确认单价是否包干、质保范围与验收标准。",
        }

    coeff = max(coeffs) if coeffs else 0.0
    risk_low = amount * coeff * 0.6
    risk_high = amount * coeff * 1.6

    # 风险等级
    if "双活口叠加" in flags or "待定项" in flags or coeff >= 0.25:
        level = "高"
    elif len(flags) >= 2 or coeff >= 0.12:
        level = "中"
    else:
        level = "低"

    if level == "高":
        ask = ("该项须书面锁定：确认最终计价方式（包干或按实）、锁定品牌型号与规格、"
               "并约定未经书面确认不实施不计价不付款。")
    elif level == "中":
        ask = ("要求补充品牌型号/规格与施工做法说明，明确是否包干；"
               "若按实结算，需约定计量方式与结算上限。")
    else:
        ask = "请对方书面确认该项为包干价并写明品牌型号，避免后续以次充好。"

    return {
        "index": index,
        "project": project,
        "category": category,
        "unit": unit,
        "qty": qty,
        "price": price,
        "amount": round(amount, 2),
        "settle_actual": settle_actual,
        "brand_spec": brand_spec,
        "note": note,
        "flags": flags,
        "reasons": reasons,
        "risk_level": level,
        "coeff": round(coeff, 4),
        "risk_low": round(risk_low, 2),
        "risk_high": round(risk_high, 2),
        "ask": ask,
    }


def audit_units(quotes, categories):
    """检测同一大类下单位混用，返回警告列表。

    两类判定：
      1) 出现不在该大类常见单位集合中的单位；
      2) 出现分属不同计量族（面积 / 长度 / 整体 / 个数…）的单位。
    """
    buckets = {}
    for idx, item in enumerate(quotes):
        project = str(item.get("project", "") or "")
        unit = str(item.get("unit", "") or "").strip()
        cat = _pick_category(project, categories)
        if not unit:
            continue
        buckets.setdefault(cat, {}).setdefault(unit, []).append(idx + 1)

    warnings = []
    for cat, units in buckets.items():
        if len(units) <= 1:
            continue
        allowed = NORMAL_UNITS.get(cat, set())
        out_of_set = sorted(u for u in units if allowed and u not in allowed)
        families = {}
        for u in units:
            families.setdefault(UNIT_FAMILY.get(u, "其他"), []).append(u)
        mixed_family = len(families) > 1
        if out_of_set or mixed_family:
            warnings.append({
                "category": cat,
                "units": sorted(units.keys()),
                "families": sorted(families.keys()),
                "items": sorted(i for v in units.values() for i in v),
                "advice": ("同一大类出现多种计量单位且不属常见组合，请确认换算口径，"
                           "例如“延米”与“㎡”、“项”与“米”之间如何折算，"
                           "以及是否会在结算时重复计取。"),
            })
    return warnings


def audit_payment(payment_schedule, high_ratio=0.6, prefix_stages=2):
    """按付款比例数组计算"前 N 阶段付款占比"，判断是否存在"付款过前"。

    前 N 阶段默认取前两个节点（行业通行做法中风险最高的一组：
    开工 + 水电/拆改进场），可用 --prefix-stages 调整。
    """
    result = {"has_schedule": False, "ratios": [], "prefix_ratio": 0.0,
              "prefix_stages": prefix_stages, "first_ratio": 0.0,
              "high": False, "advice": ""}
    if not payment_schedule:
        result["advice"] = ("报价单/合同未提供付款节点。建议要求对方书面列明各阶段付款比例，"
                             "并把尾款与竣工验收挂钩。")
        return result

    ratios = [_to_float(x) for x in payment_schedule]
    result["has_schedule"] = True
    result["ratios"] = ratios
    if not ratios:
        result["advice"] = "付款比例数据异常，无法计算。"
        return result

    total = sum(ratios)
    if total <= 0:
        result["advice"] = "付款比例数据异常，无法计算。"
        return result

    # 若比例按百分数填写（如 30 表示 30%），自动归一
    norm = [r / total for r in ratios]

    n = min(prefix_stages, len(norm))
    prefix = sum(norm[:n])
    result["prefix_ratio"] = round(prefix, 4)
    result["first_ratio"] = round(norm[0], 4)
    result["high"] = prefix > high_ratio

    if result["high"]:
        result["advice"] = ("前 %d 个节点付款比例合计 %.1f%%，偏高；"
                             "一旦中途增项，议价能力很弱。建议把节点后移："
                             "水电验收、泥木验收、竣工验收各留 3%%-5%% 尾款，"
                             "整体保留 5%%-10%% 至整改完成后支付。"
                             % (n, prefix * 100))
    else:
        result["advice"] = ("前 %d 个节点付款比例合计 %.1f%%，节奏基本合理；"
                             "仍建议保留 5%%-10%% 尾款，与竣工验收和整改完成挂钩。"
                             % (n, prefix * 100))
    return result


def audit_quote(doc, settle_coeff_table=None, high_ratio=0.6, prefix_stages=2):
    """对整份报价单做完整审计，返回报告字典。"""
    if settle_coeff_table is None:
        settle_coeff_table = SETTLE_COEFF_DEFAULT

    quotes = doc.get("quotes") or []
    if not isinstance(quotes, list):
        raise ValueError("quotes 字段必须是数组")

    categories = doc.get("categories") if isinstance(doc.get("categories"), dict) else None
    budget = _to_float(doc.get("budget"))

    items = [audit_item(it, i + 1, settle_coeff_table, categories)
             for i, it in enumerate(quotes)]

    total = sum(i["amount"] for i in items)
    risky = [i for i in items if i["flags"]]
    risk_low = sum(i["risk_low"] for i in items)
    risk_high = sum(i["risk_high"] for i in items)

    # 按实结算项小计
    settle_items = [i for i in items if i["settle_actual"]]
    settle_amount = sum(i["amount"] for i in settle_items)
    settle_share = (settle_amount / total) if total > 0 else 0.0

    unit_warnings = audit_units(quotes, categories)
    payment = audit_payment(doc.get("payment_schedule"), high_ratio, prefix_stages)

    # 总体评级
    high_count = len([i for i in items if i["risk_level"] == "高"])
    mid_count = len([i for i in items if i["risk_level"] == "中"])
    if high_count >= 3 or (high_count >= 1 and settle_share >= 0.3):
        overall = "高"
    elif high_count >= 1 or mid_count >= 3 or settle_share >= 0.2:
        overall = "中"
    else:
        overall = "低"

    budget_block = {"budget": budget, "total": round(total, 2)}
    if budget > 0:
        diff = total - budget
        budget_block["diff"] = round(diff, 2)
        budget_block["diff_ratio"] = round(diff / budget, 4)
        if diff > 0:
            budget_block["note"] = ("报价合计已超出预算约 %.1f%%，属于常见的中性提醒："
                                    "建议按预留 5%%-10%% 浮动的口径检查预算，"
                                    "并要求对方书面列出所有可能触发的增项条件。"
                                    % (diff / budget * 100))
        else:
            budget_block["note"] = ("报价合计低于预算约 %.1f%%，仍需确认是否已含"
                                    "拆除清运、成品保护、管理费、开荒保洁等常见漏项。"
                                    % (abs(diff) / budget * 100))
    else:
        budget_block["note"] = "未提供预算金额，跳过预算对比。"

    # 追问清单：按风险等级排序
    ask_list = []
    order = {"高": 0, "中": 1, "低": 2}
    for i in sorted(risky, key=lambda x: (order.get(x["risk_level"], 3), -x["risk_high"])):
        ask_list.append({
            "project": i["project"],
            "risk_level": i["risk_level"],
            "flags": i["flags"],
            "ask": i["ask"],
            "risk_low": i["risk_low"],
            "risk_high": i["risk_high"],
        })

    return {
        "total_amount": round(total, 2),
        "item_count": len(items),
        "budget_compare": budget_block,
        "risk_summary": {
            "high_count": high_count,
            "mid_count": mid_count,
            "low_count": len(items) - high_count - mid_count,
            "overall": overall,
        },
        "settle_actual": {
            "count": len(settle_items),
            "amount": round(settle_amount, 2),
            "share": round(settle_share, 4),
            "items": [
                {"project": i["project"], "amount": i["amount"],
                 "risk_low": i["risk_low"], "risk_high": i["risk_high"]}
                for i in settle_items
            ],
        },
        "risky_items": [
            {k: v for k, v in i.items() if k != "index"} for i in risky
        ],
        "unit_warnings": unit_warnings,
        "payment": payment,
        "ask_list": ask_list,
        "addon_type_hints": [
            {"type": t, "trigger": d} for t, d in ADDON_TYPE_HINTS
        ],
        "disclaimer": (
            "本报告为报价单要素自查与条款参考，仅对要素缺失与条款开口做客观提示；"
            "增项区间为经验估算，非造价依据，不构成工程造价咨询或法律意见。"
            "重大合同签署前请咨询执业律师。"
        ),
    }


# ---------------------------------------------------------------- 文本渲染
def render_text(report):
    """把审计报告渲染为人类可读文本。"""
    out = []
    a = out.append
    a("=" * 62)
    a("装修报价单要素对照与活口条款审计")
    a("=" * 62)

    a("")
    a("【一、总价与预算】")
    a("  报价合计：%.2f 元" % report["total_amount"])
    a("  条目数量：%d 项" % report["item_count"])
    bc = report["budget_compare"]
    if bc.get("budget"):
        a("  预算金额：%.2f 元" % bc["budget"])
    a("  说明：%s" % bc.get("note", ""))

    rs = report["risk_summary"]
    a("")
    a("【二、风险总览】")
    a("  高风险 %d 项 / 中风险 %d 项 / 低风险 %d 项"
      % (rs["high_count"], rs["mid_count"], rs["low_count"]))
    a("  总体评级：%s" % rs["overall"])
    sa = report["settle_actual"]
    a("  按实结算项：%d 项，合计 %.2f 元，占总价 %.1f%%"
      % (sa["count"], sa["amount"], sa["share"] * 100))

    a("")
    a("【三、活口条款清单（按风险等级排序）】")
    if not report["risky_items"]:
        a("  未发现明显活口条款。建议仍逐项确认品牌型号与质保范围。")
    else:
        for i, it in enumerate(report["risky_items"], 1):
            a("")
            a("  %d) [%s] %s" % (i, it["risk_level"], it["project"] or "(未命名项目)"))
            a("     计量：%s x %s x %.2f = %.2f 元"
              % (it["qty"], it["unit"] or "无单位", it["price"], it["amount"]))
            a("     活口标签：%s" % "、".join(it["flags"]))
            for r in it["reasons"]:
                a("     - %s" % r)
            a("     增项风险参考：%.0f ~ %.0f 元（经验估算，非造价依据）"
              % (it["risk_low"], it["risk_high"]))
        a("")
        a("  增项风险合计参考：%.0f ~ %.0f 元"
          % (sum(x["risk_low"] for x in report["risky_items"]),
             sum(x["risk_high"] for x in report["risky_items"])))

    if report["unit_warnings"]:
        a("")
        a("【四、单位混用提示】")
        for w in report["unit_warnings"]:
            a("  大类「%s」出现多种单位：%s（对应条目序号 %s）"
              % (w["category"], "、".join(w["units"]), w["items"]))
            a("     %s" % w["advice"])

    pay = report["payment"]
    a("")
    a("【五、付款节点风险】")
    if pay["has_schedule"]:
        a("  付款比例：%s" % " / ".join("%.0f%%" % (r * 100) for r in pay["ratios"]))
        a("  前 %d 个节点累计：%.1f%%%s"
          % (pay["prefix_stages"], pay["prefix_ratio"] * 100,
             "（偏高）" if pay["high"] else ""))
    else:
        a("  未提供付款节点数据。")
    a("  %s" % pay["advice"])

    a("")
    a("【六、建议追问清单】")
    if not report["ask_list"]:
        a("  无高风险条目，保持常规确认即可。")
    else:
        for n, item in enumerate(report["ask_list"], 1):
            a("  %d) 关于「%s」（%s）：%s"
              % (n, item["project"] or "(未命名项目)",
                 item["risk_level"], item["ask"]))

    a("")
    a("【七、常见增项类型提示】")
    for h in report["addon_type_hints"]:
        a("  %s：%s" % (h["type"], h["trigger"]))

    a("")
    a("【免责说明】")
    a("  %s" % report["disclaimer"])
    a("=" * 62)
    return "\n".join(out)


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    """命令行入口：解析参数、读取输入、执行审计、输出报告。"""
    parser = argparse.ArgumentParser(
        description="装修报价单要素对照与活口条款审计（零依赖）")
    parser.add_argument("--input", required=True, help="报价单 JSON 文件路径")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="以 JSON 格式输出报告")
    parser.add_argument("--settle-coeff", type=float, default=None,
                        help="自定义按实结算风险系数（默认取内置经验系数表）")
    parser.add_argument("--high-ratio", type=float, default=0.6,
                        help="前 N 阶段付款占比告警阈值，默认 0.6")
    parser.add_argument("--prefix-stages", type=int, default=2,
                        help="计算前期付款占比的节点数，默认 2")
    args = parser.parse_args(argv)

    path = args.input
    if not os.path.isfile(path):
        sys.stderr.write("错误：找不到输入文件：%s\n" % path)
        sys.stderr.write("请确认路径是否正确，或先准备符合格式的报价单 JSON。\n")
        return 2

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            doc = json.load(f)
    except json.JSONDecodeError as e:
        sys.stderr.write("错误：输入文件不是合法 JSON。\n")
        sys.stderr.write("位置：第 %d 行第 %d 列 - %s\n"
                         % (e.lineno, e.colno, e.msg))
        sys.stderr.write("请检查是否存在多余逗号、单引号或中文引号。\n")
        return 2
    except OSError as e:
        sys.stderr.write("错误：读取文件失败：%s\n" % e)
        return 2

    if not isinstance(doc, dict):
        sys.stderr.write("错误：输入 JSON 顶层必须是对象（包含 quotes 数组）。\n")
        return 2

    if not isinstance(doc.get("quotes"), list) or not doc.get("quotes"):
        sys.stderr.write("错误：输入 JSON 缺少非空的 quotes 数组。\n")
        sys.stderr.write("参考格式：{\"budget\": 200000, \"quotes\": [{\"project\": \"拆除\", ...}]}\n")
        return 2

    table = dict(SETTLE_COEFF_DEFAULT)
    if args.settle_coeff is not None:
        table["default"] = args.settle_coeff

    try:
        report = audit_quote(doc, table, args.high_ratio, args.prefix_stages)
    except ValueError as e:
        sys.stderr.write("错误：数据格式问题：%s\n" % e)
        return 2

    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
