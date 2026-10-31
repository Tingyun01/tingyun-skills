#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""社保医保公积金办事指引助手 —— 属地办事指引查询脚本。

只依赖 Python 标准库，零第三方依赖。

用法::

    python social_insurance_lookup.py --list
    python social_insurance_lookup.py --province 安徽省 --city 合肥市 --item cross_region_filing
    python social_insurance_lookup.py --province 安徽省 --city 合肥市 --item all --json
    python social_insurance_lookup.py --province 江苏省 --city 南京市 --item all --data ./localities.json

设计约定：

* 事项键固定为四个：``cross_region_filing`` / ``chronic_disease`` /
  ``housing_fund`` / ``flexible_employment``。
* 数据文件默认读取脚本同级的 ``../data/localities.json``，也可用 ``--data`` 指定。
* 找不到属地或事项时输出友好提示与可选项列表，退出码为 1，不抛异常堆栈。
* 本脚本只输出办事指引与材料清单，不做任何待遇金额测算。
"""

import argparse
import json
import os
import sys
from datetime import date, datetime

# 保证在 Windows 终端下也能正确输出中文，避免 UnicodeEncodeError。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception:  # pragma: no cover - 极端环境下静默降级
        pass

# 事项键 -> 中文名称。
ITEM_LABELS = {
    "cross_region_filing": "异地就医备案",
    "chronic_disease": "门诊慢特病认定",
    "housing_fund": "住房公积金提取",
    "flexible_employment": "灵活就业参保与断缴补缴",
}

# 事项键 -> 材料三档的划分规则（按材料文本关键词判定必带 / 按情况带 / 建议带）。
REQUIRED_KEYWORDS = (
    "身份证", "社保卡", "医保电子凭证", "就业登记", "离职证明", "退休证",
    "备案表", "申请表",
)
CONDITIONAL_KEYWORDS = (
    "居住证", "户口簿", "劳动合同", "派出", "转诊", "购房", "不动产权",
    "装修", "物业", "租赁", "无房", "承诺书", "授权", "单位证明",
)

# 事项键 -> 建议携带的材料（降低退回风险但非硬性要求）。
SUGGESTED_EXTRA = {
    "cross_region_filing": ["社保卡或医保电子凭证截图", "近期居住证明复印件"],
    "chronic_disease": ["近 3 个月内复查报告", "既往门诊病历复印件"],
    "housing_fund": ["本人名下银行账户信息", "不动产权证书复印件"],
    "flexible_employment": ["就业登记回执", "银行卡余额确认"],
}

# 事项键 -> 办理顺序表的步骤模板（每步说明"这一步缺什么会卡住"）。
STEP_TEMPLATES = {
    "cross_region_filing": [
        ("确认备案类型", "长期居住类还是临时外出类？类型选错，后面材料全要重来"),
        ("备齐身份与情形材料", "缺居住证或户口簿（长期居住）、转诊材料（转诊）会被当场退回"),
        ("线上提交或窗口递交", "线上要上传清晰的认定材料扫描件，窗口要带原件"),
        ("查询备案状态与生效日", "承诺制必须记下补齐材料截止日，否则备案会失效"),
    ],
    "chronic_disease": [
        ("到二级及以上定点医院就诊", "没有定点医院的诊断材料，后面申请表拿不到"),
        ("取得完整病历资料", "出院小结、门诊病历、检验检查报告缺项会被退回"),
        ("医师填写认定申请表并盖章", "缺医师签名或医院医保部门印章直接作废"),
        ("提交认定申请", "材料不全当场退回；线上提交后仍需等审核结果"),
        ("查询认定结果与有效期", "未认定前发生的费用不能按慢特病待遇报销"),
    ],
    "housing_fund": [
        ("确认提取情形", "支付房租、购房、装修、物业费等 9 类情形材料要求不同，选错要重备"),
        ("备齐对应证明材料", "证明不在有效期内或口径不符会被退回"),
        ("线上提交或窗口递交", "线上上传扫描件需清晰完整，窗口需带原件"),
        ("等待提取决定", "受理后 3 日内出决定，被驳回会说明理由"),
        ("到受委托银行支取", "注意同一用途不要重复提取，可能被认定为骗提"),
    ],
    "flexible_employment": [
        ("办理就业登记", "部分省份要求先就业登记再参保，缺这一步无法生成参保信息"),
        ("办理灵活就业参保登记", "非本地户籍通常还需居住证或居住登记材料"),
        ("在税务渠道选缴费档次", "未选档无法缴费，档次区间以当年公布的上下限为准"),
        ("按月缴费并确认到账", "扣款失败或未缴会造成断缴，事后通常不能追补"),
        ("关注医保待遇起算", "首次参保一般需连续缴费满一定月数后才享受待遇"),
    ],
}

# 白跑警示严重度关键词（命中的条目排在前面）。
SEVERITY_RULES = (
    ("高", ("失效", "不再享受", "追回", "失信", "不得", "骗提", "违法", "作废", "中断", "处罚")),
    ("中", ("退回", "不认可", "不作为", "不符", "过期", "缺少", "不认")),
    ("低", ("建议", "确认", "查询", "口径")),
)

# 固定结尾提示，强调法律边界。
DISCLAIMER = (
    "提示：以上仅为办事指引与材料准备辅助，不预测待遇金额，"
    "所有审核结论以参保地经办机构为准；政策有时效，办理前请以参保地最新公告为准。"
)


class LookupError_(Exception):
    """查找失败时携带可展示的提示信息与可选项列表。"""


def load_data(data_path=None):
    """读取属地数据文件。

    :param data_path: 数据文件路径，None 时使用默认路径。
    :return: 解析后的字典。
    :raises LookupError_: 文件不存在或 JSON 非法时抛出，消息可直接展示给用户。
    """
    path = data_path or default_data_path()
    if not os.path.isfile(path):
        raise LookupError_(
            "找不到属地数据文件：%s\n"
            "请确认文件是否存在，或用 --data 指定正确路径。" % path
        )
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise LookupError_(
            "属地数据文件不是合法 JSON：%s\n错误位置：第 %d 行第 %d 列。"
            % (path, exc.lineno, exc.colno)
        )
    except OSError as exc:
        raise LookupError_("读取属地数据文件失败：%s\n%s" % (path, exc))


def default_data_path():
    """返回默认数据文件路径：脚本同级的 ``../data/localities.json``。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, os.pardir, "data", "localities.json")


def normalize(name):
    """归一化属地名称：去掉省市后缀与空白，便于模糊匹配。

    :param name: 原始名称，如"安徽省"、"合肥"。
    :return: 归一化后的字符串。
    """
    if not name:
        return ""
    text = str(name).strip()
    for suffix in ("省", "市", "区", "县"):
        if text.endswith(suffix) and len(text) > len(suffix):
            text = text[: -len(suffix)]
            break
    return text.replace(" ", "")


def match_province(localities, wanted):
    """在数据中匹配省份。

    :param localities: 属地字典。
    :param wanted: 用户输入的省份名。
    :return: 匹配到的省份键。
    :raises LookupError_: 无匹配时抛出并给出可选项。
    """
    if wanted in localities:
        return wanted
    target = normalize(wanted)
    for name in localities:
        if normalize(name) == target:
            return name
    for name in localities:
        if target and (target in normalize(name) or normalize(name) in target):
            return name
    raise LookupError_(
        "没有找到省份「%s」。\n当前数据文件已收录的省份：%s"
        % (wanted, "、".join(sorted(localities.keys())))
    )


def match_city(cities, wanted):
    """在数据中匹配城市。

    :param cities: 城市字典。
    :param wanted: 用户输入的城市名。
    :return: 匹配到的城市键。
    :raises LookupError_: 无匹配时抛出并给出可选项。
    """
    if wanted in cities:
        return wanted
    target = normalize(wanted)
    for name in cities:
        if normalize(name) == target:
            return name
    for name in cities:
        if target and (target in normalize(name) or normalize(name) in target):
            return name
    raise LookupError_(
        "没有找到城市「%s」。\n当前省份已收录的城市：%s"
        % (wanted, "、".join(sorted(cities.keys())))
    )


def classify_materials(item_key, materials):
    """把材料清单拆成必带 / 按情况带 / 建议带三档。

    :param item_key: 事项键。
    :param materials: 原始材料列表。
    :return: (必带列表, 按情况带列表, 建议带列表)。
    """
    required, conditional, suggested = [], [], []
    for material in materials or []:
        text = str(material)
        if any(key in text for key in REQUIRED_KEYWORDS):
            required.append(text)
        elif any(key in text for key in CONDITIONAL_KEYWORDS):
            conditional.append(text)
        else:
            suggested.append(text)
    for extra in SUGGESTED_EXTRA.get(item_key, []):
        if extra not in suggested:
            suggested.append(extra)
    return required, conditional, suggested


def severity_of(text):
    """判定一条白跑警示的严重度。

    :param text: 警示文本。
    :return: "高" / "中" / "低"。
    """
    for level, keywords in SEVERITY_RULES:
        if any(keyword in text for keyword in keywords):
            return level
    return "低"


def build_steps(item_key, entry):
    """生成办理顺序表。

    :param item_key: 事项键。
    :param entry: 事项数据字典。
    :return: 步骤列表，每项为 (步骤名, 动作说明, 缺失后果)。
    """
    steps = []
    action_pool = [
        entry.get("applicable", ""),
        "按材料清单准备：%s" % "、".join((entry.get("materials") or [])[:3]),
        entry.get("channel", ""),
        entry.get("duration", "") or entry.get("certification_cycle", ""),
        entry.get("validity", "") or entry.get("rental_rule", ""),
    ]
    for index, (name, blocker) in enumerate(STEP_TEMPLATES.get(item_key, []), start=1):
        action = action_pool[index - 1] if index <= len(action_pool) else ""
        steps.append((str(index), name, action, blocker))
    return steps


def build_deadlines(entry):
    """整理时间节点清单。

    :param entry: 事项数据字典。
    :return: 节点列表，每项为 (节点名, 说明, 截止逻辑)。
    """
    deadlines = []
    if entry.get("commitment_note"):
        deadlines.append(
            (
                "承诺制补齐材料",
                entry["commitment_note"],
                "逾期本次备案失效，且今后不再享受承诺制备案服务，逾期期间结算可能纳入医保信用评价",
            )
        )
    elif entry.get("commitment_period_days"):
        deadlines.append(
            (
                "承诺制补齐材料",
                "备案申请提交次日起 %d 日内一次性补齐有效认定材料" % entry["commitment_period_days"],
                "逾期本次备案失效，且今后不再享受承诺制备案服务，逾期期间结算可能纳入医保信用评价",
            )
        )
    if entry.get("validity"):
        deadlines.append(("备案/资格有效期", entry["validity"], "到期前需确认是否需要续办或变更，逾期影响待遇享受"))
    if entry.get("decision_deadline"):
        deadlines.append(("提取决定时限", entry["decision_deadline"], "超期未出决定可向经办机构查询办理进度"))
    if entry.get("advance_days"):
        deadlines.append(
            (
                "可提前办理天数",
                "可提前 %d 日办理" % entry["advance_days"],
                "未在窗口期前提交会影响生效日",
            )
        )
    if entry.get("certification_cycle"):
        deadlines.append(("认定周期", entry["certification_cycle"], "超过周期未出结果可电话查询，必要时申请复核"))
    return deadlines


def render_item(item_key, entry, indent=0):
    """把单个事项渲染成可读的文本块。

    :param item_key: 事项键。
    :param entry: 事项数据字典。
    :param indent: 缩进空格数。
    :return: 文本行列表。
    """
    pad = " " * indent
    lines = []
    title = ITEM_LABELS.get(item_key, item_key)
    lines.append("%s【%s】" % (pad, title))

    lines.append("%s一、适用人群与基本信息" % pad)
    if entry.get("applicable"):
        lines.append("%s  适用人群：%s" % (pad, entry["applicable"]))
    if entry.get("disease_scope"):
        lines.append("%s  病种范围：%s" % (pad, entry["disease_scope"]))
    if entry.get("validity"):
        lines.append("%s  有效期：%s" % (pad, entry["validity"]))
    if entry.get("commitment_note"):
        lines.append("%s  承诺制补齐时限：%s" % (pad, entry["commitment_note"]))
    elif entry.get("commitment_period_days"):
        lines.append(
            "%s  承诺制补齐时限：备案提交次日起 %d 日内一次性补齐"
            % (pad, entry["commitment_period_days"])
        )
    else:
        lines.append("%s  承诺制补齐时限：以参保地公布为准" % pad)
    if entry.get("advance_days"):
        lines.append("%s  可提前办理：%d 日" % (pad, entry["advance_days"]))
    else:
        lines.append("%s  可提前办理：以参保地公布为准" % pad)
    if entry.get("rental_rule"):
        lines.append("%s  提取规则：%s" % (pad, entry["rental_rule"]))
    if entry.get("contribution_range"):
        lines.append("%s  缴费档次：%s" % (pad, entry["contribution_range"]))
    if entry.get("back_payment_rule"):
        lines.append("%s  补缴规则：%s" % (pad, entry["back_payment_rule"]))

    lines.append("%s二、材料清单" % pad)
    required, conditional, suggested = classify_materials(item_key, entry.get("materials"))
    for label, items in (
        ("必带", required),
        ("按情况带", conditional),
        ("建议带", suggested),
    ):
        if items:
            lines.append("%s  [%s]" % (pad, label))
            for material in items:
                lines.append("%s    - %s" % (pad, material))
        else:
            lines.append("%s  [%s] 无" % (pad, label))

    lines.append("%s三、办理顺序" % pad)
    for number, name, action, blocker in build_steps(item_key, entry):
        lines.append("%s  第 %s 步：%s" % (pad, number, name))
        if action:
            lines.append("%s    动作：%s" % (pad, action))
        lines.append("%s    缺这一步会卡住：%s" % (pad, blocker))

    lines.append("%s四、白跑警示（按严重度排序）" % pad)
    pitfalls = list(entry.get("pitfalls") or [])
    if not pitfalls:
        pitfalls = ["暂无属地提示，办理前请以参保地最新公告为准"]
    ordered = sorted(pitfalls, key=lambda text: {"高": 0, "中": 1, "低": 2}[severity_of(text)])
    for text in ordered:
        lines.append("%s  [%s] %s" % (pad, severity_of(text), text))

    lines.append("%s五、时间节点" % pad)
    deadlines = build_deadlines(entry)
    if deadlines:
        for name, detail, logic in deadlines:
            lines.append("%s  - %s：%s" % (pad, name, detail))
            lines.append("%s    截止逻辑：%s" % (pad, logic))
    else:
        lines.append("%s  - 以参保地公布为准" % pad)

    lines.append("%s六、来源与核对日期" % pad)
    lines.append("%s  政策来源：%s" % (pad, entry.get("source", "未标注")))
    lines.append("%s  核对日期：%s" % (pad, entry.get("verified_on", "未标注")))
    lines.append("")
    return lines


def select_items(items, item, city_key):
    """从城市事项字典中挑出要展示的事项。

    :param items: 城市下的事项字典。
    :param item: 事项键或 "all"。
    :param city_key: 城市键，用于错误提示。
    :return: {事项键: 事项数据}。
    :raises LookupError_: 事项不存在时抛出并给出可选项。
    """
    if item == "all":
        selected = {k: v for k, v in items.items() if k in ITEM_LABELS}
        if not selected:
            raise LookupError_("城市「%s」下没有可用事项数据。" % city_key)
        return selected
    if item not in items:
        raise LookupError_(
            "城市「%s」下没有事项「%s」。\n该城市可查事项：%s"
            % (
                city_key,
                ITEM_LABELS.get(item, item),
                "、".join(
                    ITEM_LABELS.get(k, k) for k in sorted(items) if k in ITEM_LABELS
                ),
            )
        )
    return {item: items[item]}


def lookup(data, province, city, item):
    """查询属地事项数据。

    :param data: 已加载的数据字典。
    :param province: 省份名。
    :param city: 城市名。
    :param item: 事项键或 "all"。
    :return: (省份键, 城市键, {事项键: 事项数据})。
    :raises LookupError_: 属地或事项不存在时抛出。
    """
    localities = data.get("localities") or {}
    if not localities:
        raise LookupError_("属地数据文件中没有 localities 字段，数据格式可能有误。")
    province_key = match_province(localities, province)
    cities = (localities[province_key] or {}).get("cities") or {}
    if not cities:
        raise LookupError_("省份「%s」下没有城市数据。" % province_key)
    city_key = match_city(cities, city)
    return province_key, city_key, select_items(cities[city_key] or {}, item, city_key)


def print_list(data):
    """打印所有可查属地与事项。

    :param data: 已加载的数据字典。
    """
    localities = data.get("localities") or {}
    version = data.get("version", "未标注")
    notice = data.get("notice", "")
    print("属地办事指引一览")
    print("数据版本：%s" % version)
    if notice:
        print("说明：%s" % notice)
    print("-" * 60)
    for province in sorted(localities.keys()):
        cities = (localities[province] or {}).get("cities") or {}
        print("省份：%s" % province)
        for city in sorted(cities.keys()):
            items = cities[city] or {}
            names = [
                "%s(%s)" % (ITEM_LABELS.get(k, k), k)
                for k in ("cross_region_filing", "chronic_disease", "housing_fund", "flexible_employment")
                if k in items
            ]
            print("  城市：%s" % city)
            for name in names:
                print("    - %s" % name)
    print("-" * 60)
    print("用法示例：")
    print("  python social_insurance_lookup.py --province 安徽省 --city 合肥市 --item cross_region_filing")
    print("  python social_insurance_lookup.py --province 江苏省 --city 南京市 --item all --json")
    print(DISCLAIMER)


def print_result(province_key, city_key, selected, as_json):
    """输出查询结果。

    :param province_key: 省份键。
    :param city_key: 城市键。
    :param selected: 事项字典。
    :param as_json: 是否输出 JSON。
    """
    if as_json:
        payload = {
            "province": province_key,
            "city": city_key,
            "items": selected,
            "notice": (
                "以上仅为办事指引与材料准备辅助，不预测待遇金额，"
                "所有审核结论以参保地经办机构为准；政策有时效，办理前请以参保地最新公告为准。"
            ),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print("属地办事指引：%s / %s" % (province_key, city_key))
    print("=" * 60)
    for item_key in ("cross_region_filing", "chronic_disease", "housing_fund", "flexible_employment"):
        if item_key in selected:
            for line in render_item(item_key, selected[item_key]):
                print(line)
    print("=" * 60)
    print(DISCLAIMER)


def build_parser():
    """构造命令行参数解析器。

    :return: argparse.ArgumentParser 实例。
    """
    parser = argparse.ArgumentParser(
        prog="social_insurance_lookup.py",
        description="按参保地查询社保医保公积金高频事项的办事指引（材料清单、办理顺序、不白跑提醒）。",
    )
    parser.add_argument("--province", help="省份名称，如：安徽省 / 江苏 / 上海")
    parser.add_argument("--city", help="城市名称，如：合肥市 / 南京 / 崇明区")
    parser.add_argument(
        "--item",
        default="all",
        help="事项：cross_region_filing / chronic_disease / housing_fund / flexible_employment / all",
    )
    parser.add_argument("--data", help="属地数据文件路径，默认 ../data/localities.json")
    parser.add_argument("--list", action="store_true", help="列出所有可查属地与事项")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    return parser


def main(argv=None):
    """脚本入口。

    :param argv: 命令行参数列表，None 时取 sys.argv。
    :return: 退出码。
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        data = load_data(args.data)
    except LookupError_ as exc:
        sys.stderr.write("读取数据失败：\n%s\n" % exc)
        return 1

    if args.list:
        print_list(data)
        return 0

    if not args.province:
        localities = data.get("localities") or {}
        sys.stderr.write(
            "缺少参数：--province 必填。\n"
            "已收录的省份：%s\n"
            "可先用 --list 查看所有可查属地与事项。\n"
            % "、".join(sorted(localities.keys()))
        )
        return 1

    if args.item != "all" and args.item not in ITEM_LABELS:
        sys.stderr.write(
            "未知事项「%s」。\n可用事项：%s\n"
            % (args.item, "、".join("%s(%s)" % (v, k) for k, v in ITEM_LABELS.items()))
        )
        return 1

    try:
        localities = data.get("localities") or {}
        if not localities:
            raise LookupError_("属地数据文件中没有 localities 字段，数据格式可能有误。")
        province_key = match_province(localities, args.province)
        cities = (localities[province_key] or {}).get("cities") or {}
        if not cities:
            raise LookupError_("省份「%s」下没有城市数据。" % province_key)

        if not args.city:
            raise LookupError_(
                "缺少参数：--city 必填。\n省份「%s」下已收录的城市：%s"
                % (province_key, "、".join(sorted(cities.keys())))
            )

        city_key = match_city(cities, args.city)
        selected = select_items(cities[city_key] or {}, args.item, city_key)
    except LookupError_ as exc:
        sys.stderr.write("%s\n" % exc)
        return 1

    print_result(province_key, city_key, selected, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
