#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合同风险扫描器（执行型）
=================================
一条命令扫描合同，直接输出可用的风险报告：命中条款原文摘录、大白话解释、
可直接发给对方的协商话术、法律依据，以及合同**缺失**的关键条款。

支持格式：
  .txt / .md / .csv / .json          纯文本
  .docx                              Word（stdlib 解压读取，无需装库）
  .pdf                               文本型 PDF（尽力而为，扫描件读不出文字会提示）
  -                                 从标准输入读取

用法：
  python scan_contract.py 合同.docx
  python scan_contract.py 合同.pdf --output 报告.md
  python scan_contract.py 合同.txt --format json
  python scan_contract.py 合同.docx --side 乙方

零依赖：只用 Python 3 标准库。
"""
import argparse
import io
import json
import os
import re
import sys
import zipfile
import zlib
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rules_data import RULES  # noqa: E402

# ------------------------------------------------------------------ 常量
LEVEL_CN = {"high": "高危", "medium": "中危", "low": "提示"}
LEVEL_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}
LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2}

TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".html", ".htm"}
SUPPORTED_EXT = TEXT_EXT | {".docx", ".pdf"}

# ---------------------------------------------------------------- 合同类型识别
TYPE_RULES = [
    ("房屋租赁", ["租赁", "房东", "押金", "退租", "租户", "承租人", "出租人", "月租金", "房租"]),
    ("劳动用工", ["试用期", "劳动合同", "加班", "社保", "工资", "离职", "辞退", "入职", "竞业限制", "用人单位"]),
    ("装修工程", ["装修", "施工", "工期", "增项", "主材", "辅材", "验收", "泥瓦", "装饰"]),
    ("保险", ["保险", "投保", "保单", "被保险人", "免赔", "理赔", "等待期", "保险人"]),
    ("借款借贷", ["借款", "借条", "欠条", "借据", "出借", "本金", "利息", "还款", "借款人"]),
    ("担保", ["担保", "保证人", "连带责任", "担保范围", "保证期间"]),
    ("股权合伙", ["股权", "合伙", "出资", "股东", "分红", "退股", "对赌"]),
    ("加盟特许", ["加盟", "特许", "品牌授权", "加盟费", "特许经营"]),
    ("婚姻家庭", ["离婚", "夫妻", "抚养", "婚前财产", "继承", "遗嘱"]),
    ("教育培训", ["培训", "课程", "学费", "课时", "报名", "考证", "辅导"]),
    ("服务劳务", ["服务", "劳务", "承揽", "交付成果", "服务合同"]),
    ("买卖采购", ["买卖", "采购", "货款", "交付货物", "标的物", "验收单"]),
    ("二手车", ["二手车", "过户", "车架号", "行驶证", "车辆"]),
    ("宠物交易", ["宠物", "猫", "狗", "疫苗", "活体"]),
    ("健身预付", ["健身", "私教", "年卡", "预付卡", "会员卡"]),
    ("医美", ["医美", "整形", "注射", "美容医疗", "手术"]),
]

# ---------------------------------------------------------------- 类型→规则分类
# 识别出合同类型后，只保留相关分类的规则，避免「损坏」这类泛词跨类误报
TYPE_TO_CATS = {
    "房屋租赁": {"租房合同"},
    "劳动用工": {"劳动合同"},
    "装修工程": {"装修/服务合同"},
    "保险": {"保险/金融"},
    "借款借贷": {"借贷合同", "担保/保证"},
    "担保": {"担保/保证"},
    "股权合伙": {"股权/合伙"},
    "加盟特许": {"加盟/特许经营"},
    "婚姻家庭": {"婚姻/家庭"},
    "教育培训": {"教育培训", "教育留学"},
    "服务劳务": {"服务/劳务", "装修/服务合同"},
    "买卖采购": {"买卖/采购", "大宗交易"},
    "二手车": {"二手车交易"},
    "宠物交易": {"宠物/活体交易"},
    "健身预付": {"健身/预付消费"},
    "医美": {"医美/美容医疗"},
}
ALWAYS_CATS = {"通用条款", "其他"}

# ---------------------------------------------------------------- 缺失条款检测
MISSING_CHECKS = {
    "房屋租赁": [
        ("押金退还期限", ["个工作日内退还", "退还押金", "押金退还"]),
        ("押金扣罚依据", ["维修发票", "实际损失", "正常使用损耗", "凭据"]),
        ("房屋及物品清单", ["物品清单", "家电清单", "附属设施清单", "家具清单"]),
        ("维修责任划分", ["主体结构", "非人为损坏", "甲方负责维修", "维修由"]),
        ("禁止单方涨租", ["不得单方面涨租", "不得涨租", "单方解除"]),
        ("退租交接确认", ["交接", "退租时", "退房"]),
    ],
    "劳动用工": [
        ("试用期期限与工资", ["试用期", "转正", "录用条件"]),
        ("社会保险约定", ["社会保险", "社保", "五险", "公积金"]),
        ("工资标准与构成", ["工资", "月薪", "基本工资", "薪资"]),
        ("工作内容与岗位", ["工作岗位", "岗位职责", "工作内容", "岗位"]),
        ("解除与离职", ["解除劳动合同", "离职", "辞职"]),
        ("竞业限制补偿", ["竞业限制", "竞业禁止", "补偿", "不得从事同类", "不得从事"]),
    ],
    "装修工程": [
        ("工程总价与付款节点", ["总价", "付款", "进度款", "首付款", "尾款"]),
        ("增项上限约定", ["增项", "变更", "签证", "增减项"]),
        ("工期与延期责任", ["工期", "交期", "开工", "竣工", "延期"]),
        ("质量保修期", ["质保", "保修", "保修期"]),
        ("材料品牌与规格", ["品牌", "型号", "规格", "主材"]),
    ],
    "借款借贷": [
        ("借款金额（含大写）", ["元整", "大写", "借款金额", "借到人民币"]),
        ("还款期限", ["还款", "期限", "到期"]),
        ("利息约定", ["利率", "利息", "年化"]),
        ("借款人身份信息", ["身份证号", "住址"]),
    ],
    "服务劳务": [
        ("服务内容", ["服务内容", "工作内容", "承揽"]),
        ("验收标准", ["验收", "确认", "标准"]),
        ("费用与支付", ["费用", "价款", "支付", "结算"]),
        ("完成时间", ["工期", "完成", "交付期限"]),
    ],
    "教育培训": [
        ("预收费金额与期限", ["学费", "课时", "预收费", "报名费"]),
        ("退费规则", ["退费", "退款", "不退"]),
    ],
    "股权合伙": [
        ("出资方式与数额", ["出资", "出资额", "认缴"]),
        ("利润分配", ["分红", "利润分配", "收益分配"]),
        ("退出机制", ["退出", "退股", "转让", "回购"]),
    ],
    "婚姻家庭": [
        ("财产约定", ["财产", "共同财产", "婚前"]),
        ("子女安排", ["抚养", "子女", "抚养费"]),
    ],
    "保险": [
        ("保险标的与保额", ["保险标的", "保额", "保险金额"]),
        ("免责与免赔", ["免责", "免赔额", "除外责任"]),
    ],
    "担保": [
        ("保证方式", ["一般保证", "连带责任保证", "保证方式"]),
        ("保证期间", ["保证期间", "担保期限"]),
    ],
    "加盟特许": [
        ("加盟费与保证金", ["加盟费", "保证金", "特许权使用费"]),
        ("退出与冷静期", ["冷静期", "解约", "退还加盟费"]),
    ],
    "二手车": [
        ("车辆状况承诺", ["事故", "泡水", "火烧", "里程"]),
        ("过户与交付时间", ["过户", "交付", "车架号"]),
    ],
    "健身预付": [
        ("退款与转让规则", ["退款", "转让", "退卡"]),
        ("服务期限与次数", ["有效期", "次数", "期限"]),
    ],
}

GENERIC_MISSING = [
    ("合同主体身份信息", ["身份证号", "统一社会信用代码", "法定代表人", "身份证"]),
    ("签字盖章", ["签字", "盖章", "手印"]),
    ("合同份数", ["一式", "各执一份", "份数"]),
    ("争议解决方式", ["仲裁", "人民法院", "协商解决"]),
    ("生效条件", ["之日起生效", "签字后生效", "盖章后生效"]),
]

# 缺失项 → 可直接粘贴的补充条款
SUPPLEMENTS = {
    "押金退还期限": "甲方应于乙方退租并完成交接后 7 个工作日内，将押金余额全额退还至乙方指定账户。",
    "押金扣罚依据": "甲方扣除押金须提供维修发票或第三方定损凭据，且仅限乙方人为损坏造成的实际损失；正常使用损耗不得扣款。",
    "房屋及物品清单": "本合同附件一《房屋及附属物品清单》列明全部家具、家电及其现状，双方签字确认后作为交房与退租验收依据。",
    "维修责任划分": "房屋主体结构及非因乙方人为损坏的设施维修由甲方负责，并在接到通知后 3 日内修复；因乙方使用不当造成的损坏由乙方负责。",
    "禁止单方涨租": "租赁期内甲方不得单方面调整租金；确需调整的，须经双方书面协商一致。",
    "退租交接确认": "退租时双方共同查验房屋及物品并签署《交接确认单》，确认无异议后押金按约定退还。",
    "试用期期限与工资": "试用期不超过 ____ 个月（劳动合同期限 1 年以上不满 3 年的不超过 2 个月，3 年以上不超过 6 个月）；试用期工资不低于本单位相同岗位最低档工资或约定工资的 80%，且不低于当地最低工资标准。",
    "社会保险约定": "甲方自用工之日起 30 日内为乙方办理社会保险登记并按时足额缴纳；乙方自愿放弃社保的约定无效。",
    "工资标准与构成": "乙方月工资为人民币 ____ 元，由基本工资 ____ 元、绩效工资 ____ 元构成，于每月 ____ 日前发放。",
    "解除与离职": "乙方提前 30 日以书面形式通知甲方可解除劳动合同，试用期内提前 3 日通知即可；甲方解除须符合法定情形并支付经济补偿。",
    "竞业限制补偿": "竞业限制期限不超过 2 年，甲方应在竞业限制期内按月支付经济补偿（不低于劳动合同终止前十二个月平均工资的 30%）；未支付的，乙方不受竞业限制约束。",
    "工程总价与付款节点": "工程总价为人民币 ____ 元（详见附件报价清单）；付款节点：开工付 30%，中期验收付 30%，竣工验收付 30%，保修期满付 10%。",
    "增项上限约定": "任何增项须经甲方书面确认后方可施工；未经确认的增项费用由施工方承担；增项总额不得超过合同总价的 10%。",
    "工期与延期责任": "工期自 ____ 年 __ 月 __ 日起至 ____ 年 __ 月 __ 日止；因施工方原因逾期竣工的，每逾期一日按合同总价的 0.5% 支付违约金。",
    "质量保修期": "隐蔽工程保修 5 年，其他项目保修 2 年，自竣工验收合格之日起算；保修期内非人为损坏由施工方免费维修。",
    "材料品牌与规格": "主要材料品牌、型号、规格、等级详见附件《材料清单》，施工方不得擅自更换；确需更换须经甲方书面同意且不降低标准。",
    "借款金额（含大写）": "借款金额为人民币 ____ 元（大写：____ 元整），以实际到账金额为准。",
    "还款期限": "借款人应于 ____ 年 __ 月 __ 日前一次性偿还全部借款本金及利息。",
    "利息约定": "借款年利率为 ____%（不超过合同成立时一年期 LPR 的四倍），利息按实际借款天数计算。",
    "借款人身份信息": "借款人姓名 ____，身份证号 ____，住址 ____，联系电话 ____。",
    "服务内容": "服务方应按附件《服务清单》完成以下工作内容：____，并交付相应成果。",
    "验收标准": "交付成果按以下标准验收：____；甲方应在收到成果后 5 个工作日内书面确认或提出异议，逾期未提出视为验收合格。",
    "费用与支付": "服务费用总额为人民币 ____ 元，支付方式：合同签订后付 ____%，验收合格后付 ____%。",
    "完成时间": "服务方应于 ____ 年 __ 月 __ 日前完成全部服务并交付成果。",
    "预收费金额与期限": "培训费用总额为人民币 ____ 元；预收费期限不超过 3 个月，且不超过课时总数的 ____%。",
    "退费规则": "学员在开课前申请退费的，扣除已发生的合理费用后退还剩余款项；开课后按已上课时比例扣除。",
    "出资方式与数额": "各方出资方式与数额：甲方以 ____ 出资 ____ 元，占股 ____%；乙方以 ____ 出资 ____ 元，占股 ____%。",
    "利润分配": "每年度利润按各方持股比例分配，于年度结算后 ____ 日内分配到位。",
    "退出机制": "合伙人退伙须提前 60 日书面通知；退伙时按届时净资产评估值回购其份额，其他合伙人在同等条件下有优先受让权。",
    "财产约定": "双方确认下列财产归各自所有：____；婚姻关系存续期间所得财产归共同所有。",
    "子女安排": "子女 ____ 由 ____ 直接抚养，另一方每月支付抚养费 ____ 元至子女年满 18 周岁，并享有探视权。",
    "保险标的与保额": "保险标的为 ____，保险金额为人民币 ____ 元。",
    "免责与免赔": "下列情形保险人不承担赔偿责任：____；每次事故免赔额为人民币 ____ 元。",
    "保证方式": "保证方式为一般保证／连带责任保证（择一勾选），保证人承担保证责任的范围限于主债务本金及利息。",
    "保证期间": "保证期间为主债务履行期限届满之日起 6 个月。",
    "加盟费与保证金": "加盟费人民币 ____ 元，保证金人民币 ____ 元；保证金于合同终止且无违约情形时无息退还。",
    "退出与冷静期": "被特许人可在签约后 7 日内无理由解除合同，特许人应全额退还加盟费及保证金。",
    "车辆状况承诺": "出卖人承诺该车无重大事故、无泡水、无火烧，表显里程真实；如有不符，买受人有权解除合同并要求全额退款。",
    "过户与交付时间": "双方应于 ____ 年 __ 月 __ 日前完成过户及交付，车辆交付前的一切违章及事故责任由出卖人承担。",
    "退款与转让规则": "会员卡可转让一次，转让手续费不超过卡内余额的 10%；因经营者原因停业的，按未消费金额全额退款。",
    "服务期限与次数": "会员卡有效期 ____ 个月，共 ____ 次服务，未消费次数可在有效期内结转使用。",
    "合同主体身份信息": "甲方（自然人）：姓名 ____，身份证号 ____，住址 ____；或（法人）：名称 ____，统一社会信用代码 ____，法定代表人 ____。",
    "签字盖章": "本合同由双方法定代表人或授权代表签字并加盖公章后生效，自然人签字并按指印。",
    "合同份数": "本合同一式两份，甲乙双方各执一份，具有同等法律效力。",
    "争议解决方式": "因本合同发生的争议，双方应协商解决；协商不成的，任何一方可向 ____ 人民法院提起诉讼。",
    "生效条件": "本合同自双方签字（盖章）之日起生效。",
}

# ---------------------------------------------------------------- 人工复核项
MANUAL_ITEMS = [
    ("空白处未填写", ["____", "＿＿", "待定", "另议", "（空白）", "(空白)"],
     "空白处签字等于授权对方事后填写，务必当场划掉或写明"),
    ("金额大小写不一致", ["元整", "大写", "小写", "¥", "￥"],
     "大小写不一致以大写为准，逐字核对数字"),
    ("日期缺失或留空", ["____年", "__年", "年__月", "月__日"],
     "日期不明确会导致履行期无法确定"),
    ("甲方/乙方信息留空", ["甲方：_", "乙方：_", "甲方（签字）：_", "乙方（签字）：_"],
     "主体不明就无法确定谁承担责任"),
    ("证件号缺失", ["身份证号：_", "证件号", "统一社会信用代码：_"],
     "缺证件号将来难以主张权利"),
    ("签字栏为空", ["签字：_", "盖章：_", "签章"],
     "签字是合同成立的关键要件"),
    ("附件未列明", ["附件", "作为本合同", "不可分割"],
     "附件未列明将来难以举证其内容"),
]


# ================================================================== 文本提取
def _decode(raw):
    for enc in ("utf-8", "gbk", "gb18030", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def read_plain(path):
    return _decode(open(path, "rb").read())


def read_docx(path):
    """stdlib 读取 docx 正文：zip → word/document.xml → 去标签。"""
    parts = []
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if re.match(r"word/(document|header\d*|footer\d*)\.xml$", n)]
            for n in names:
                xml = z.read(n).decode("utf-8", errors="replace")
                xml = re.sub(r"</w:p>", "\n", xml)
                xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
                xml = re.sub(r"<w:br[^>]*/>", "\n", xml)
                xml = re.sub(r"<[^>]+>", "", xml)
                parts.append(xml)
    except Exception as e:
        raise RuntimeError("docx 解析失败：%s" % e)
    txt = "\n".join(parts)
    return (txt.replace("&amp;", "&").replace("&lt;", "<")
               .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))


def _pdf_unescape(s):
    s = s.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
    s = s.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
    s = re.sub(r"\\([0-7]{1,3})", lambda m: chr(int(m.group(1), 8)), s)
    return s


def read_pdf(path):
    """尽力而为：解压 FlateDecode 流，抽取 Tj / TJ 文本。扫描件无文字层。"""
    data = open(path, "rb").read()
    chunks = []
    for m in re.finditer(rb"stream\r?\n", data):
        start = m.end()
        end = data.find(b"endstream", start)
        if end == -1:
            continue
        raw = data[start:end]
        try:
            raw = zlib.decompress(raw)
        except Exception:
            continue
        chunks.append(raw)

    text_parts = []
    for raw in chunks:
        try:
            s = raw.decode("latin-1")
        except Exception:
            continue
        # 文本显示操作符： (...) Tj / [ (...) ] TJ
        for m in re.finditer(r"\((?:\\.|[^\\()])*\)\s*Tj|\[(?:[^\]]*)\]\s*TJ", s):
            seg = m.group(0)
            for lit in re.finditer(r"\((?:\\.|[^\\()])*\)", seg):
                text_parts.append(_pdf_unescape(lit.group(0)[1:-1]))
            text_parts.append("\n")
        if text_parts:
            text_parts.append("\n")
    txt = "".join(text_parts)
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    return txt


def load_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return read_docx(path)
    if ext == ".pdf":
        return read_pdf(path)
    return read_plain(path)


def collect_files(root):
    if os.path.isfile(root):
        return [root]
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in (".git", "node_modules", "__pycache__")]
        for f in fn:
            if os.path.splitext(f)[1].lower() in SUPPORTED_EXT:
                out.append(os.path.join(dp, f))
    return sorted(out)


# ================================================================== 分析
def detect_types(text):
    scores = []
    for t, kws in TYPE_RULES:
        sc = sum(text.count(k) for k in kws)
        if sc:
            scores.append({"type": t, "score": sc})
    scores.sort(key=lambda x: -x["score"])
    if not scores:
        return []
    top = scores[0]["score"]
    # 次级类型必须达到主类型的 1/3，避免「社会保险」被判成保险合同
    return [s for s in scores if s["score"] >= max(2, top / 3.0)]


def excerpt(text, kw, width=34):
    """取关键词首次出现处前后文，压成一行。"""
    idx = text.find(kw)
    if idx < 0:
        return ""
    a = max(0, idx - width)
    b = min(len(text), idx + len(kw) + width)
    frag = text[a:b]
    frag = re.sub(r"\s+", " ", frag).strip()
    return frag


def scan_file(path, text, allowed_cats=None):
    hits = []
    for rule in RULES:
        if allowed_cats and rule["category"] not in allowed_cats:
            continue
        matched = [k for k in rule["keywords"] if k in text]
        if not matched:
            continue
        hits.append({
            "id": rule["id"],
            "title": rule["title"],
            "category": rule["category"],
            "level": rule["level"],
            "keywords": matched,
            "plain": rule["plain"],
            "negotiation": rule["negotiation"],
            "legal": rule["legal"],
            "excerpt": excerpt(text, matched[0]),
        })

    manual = []
    for name, pats, note in MANUAL_ITEMS:
        cnt = sum(text.count(p) for p in pats)
        if cnt:
            manual.append({"item": name, "count": cnt, "note": note})

    return hits, manual


def find_missing(text, types):
    missing = []
    for t in types:
        for name, kws in MISSING_CHECKS.get(t, []):
            if not any(k in text for k in kws):
                missing.append({"type": t, "item": name, "supplement": SUPPLEMENTS.get(name, "")})
    for name, kws in GENERIC_MISSING:
        if not any(k in text for k in kws):
            missing.append({"type": "通用", "item": name, "supplement": SUPPLEMENTS.get(name, "")})
    return missing


def build_result(files, use_filter=True):
    all_text = "\n".join(t for _, t in files)
    types = detect_types(all_text)
    main_types = [t["type"] for t in types[:2]]

    allowed = None
    if use_filter and main_types:
        allowed = set(ALWAYS_CATS)
        for t in main_types:
            allowed |= TYPE_TO_CATS.get(t, set())

    merged = {}
    manual_all = {}
    for fp, text in files:
        hits, manual = scan_file(fp, text, allowed)
        for h in hits:
            key = h["id"]
            if key not in merged:
                merged[key] = dict(h, file=os.path.basename(fp))
            else:
                prev = merged[key]
                if len(prev["keywords"]) < len(h["keywords"]):
                    prev["keywords"] = h["keywords"]
                if not prev["excerpt"] and h["excerpt"]:
                    prev["excerpt"] = h["excerpt"]
        for m in manual:
            manual_all[m["item"]] = manual_all.get(m["item"], 0) + m["count"]

    hits = sorted(merged.values(), key=lambda x: (LEVEL_ORDER[x["level"]], x["id"]))
    manual_list = [{"item": k, "count": v,
                    "note": next((n for nm, _, n in MANUAL_ITEMS if nm == k), "")}
                   for k, v in manual_all.items()]
    manual_list.sort(key=lambda x: -x["count"])
    missing = find_missing(all_text, main_types)

    high = [h for h in hits if h["level"] == "high"]
    medium = [h for h in hits if h["level"] == "medium"]
    low = [h for h in hits if h["level"] == "low"]

    if high or len(missing) >= 3:
        verdict = "改完再签"
        reason = "存在 %d 条高危条款、%d 项关键条款缺失，直接签大概率吃亏" % (len(high), len(missing))
    elif medium or missing:
        verdict = "可签，但先把中危项谈清楚"
        reason = "未发现高危条款，但仍有 %d 条中危和 %d 项缺失需要确认" % (len(medium), len(missing))
    else:
        verdict = "风险较低"
        reason = "未发现明显风险条款，仍建议人工核对金额、日期与签章"

    return {
        "files": [os.path.basename(f) for f, _ in files],
        "types": types[:3],
        "hits": hits,
        "missing": missing,
        "manual": manual_list,
        "counts": {"high": len(high), "medium": len(medium), "low": len(low), "missing": len(missing)},
        "verdict": verdict,
        "reason": reason,
        "top": [h for h in hits if h["level"] in ("high", "medium")][:3],
    }


# ================================================================== 输出
def render_markdown(res, side=None):
    L = []
    L.append("# 合同风险扫描报告\n")
    L.append("> 扫描文件：%s" % "、".join(res["files"]))
    L.append("> 识别类型：%s" % ("、".join(t["type"] for t in res["types"]) or "未识别"))
    if side:
        L.append("> 你的立场：**%s**（以下风险按对你是否有利判断）" % side)
    c = res["counts"]
    L.append("> 风险分布：🔴 高危 %d · 🟡 中危 %d · 🟢 提示 %d · 缺失条款 %d\n" % (
        c["high"], c["medium"], c["low"], c["missing"]))

    L.append("## 一、结论\n")
    L.append("**【%s】** —— %s\n" % (res["verdict"], res["reason"]))
    if res["top"]:
        L.append("**最该谈的 %d 条**：" % len(res["top"]))
        for i, h in enumerate(res["top"], 1):
            L.append("%d. %s%s｜%s" % (i, LEVEL_ICON[h["level"]], h["id"], h["title"]))
        L.append("")

    L.append("## 二、逐条风险（高危在前）\n")
    if not res["hits"]:
        L.append("未命中任何风险规则。这不等于合同没问题——请人工核对金额、日期、签章与主体信息。\n")
    for h in res["hits"]:
        L.append("### %s %s｜%s" % (LEVEL_ICON[h["level"]], h["id"], h["title"]))
        if h["excerpt"]:
            L.append("**合同原文**：> %s" % h["excerpt"])
        L.append("**命中关键词**：%s" % "、".join(h["keywords"][:6]))
        if h["plain"]:
            L.append("**这意味着什么**：%s" % h["plain"])
        if h["negotiation"]:
            L.append("**你可以这样说**：「%s」" % h["negotiation"])
        if h["legal"]:
            L.append("**法律依据**：%s" % h["legal"])
        L.append("")

    L.append("## 三、缺失条款（本该有但没找到）\n")
    if not res["missing"]:
        L.append("关键条款齐全。\n")
    else:
        L.append("> 缺失比命中更隐蔽——合同里没有的东西，审核时最容易被忽略。\n")
        for m in res["missing"]:
            L.append("### ⚠️ [%s] %s" % (m["type"], m["item"]))
            if m["supplement"]:
                L.append("**可直接补进合同**：")
                L.append("> %s" % m["supplement"])
            L.append("")

    L.append("## 四、必须人工复核\n")
    if not res["manual"]:
        L.append("未发现明显形式问题，仍需过一遍金额与日期。\n")
    else:
        L.append("| 检查项 | 出现次数 | 为什么必须看 |")
        L.append("|---|---:|---|")
        for m in res["manual"]:
            L.append("| %s | %d | %s |" % (m["item"], m["count"], m["note"]))
        L.append("")

    L.append("## 五、签约前必查清单\n")
    checklist = []
    if res["counts"]["high"]:
        checklist.append("把上面每一条高危条款谈成双向对等或删除，再进入下一步")
    for m in res["missing"][:4]:
        checklist.append("补上「%s」" % m["item"])
    checklist.append("核对金额大小写、日期起止、双方名称与证件号逐字一致")
    checklist.append("确认签字/盖章/按手印齐全，空白处全部划掉")
    checklist.append("所有口头承诺写进合同或书面补充协议")
    checklist.append("保留一份双方签字后的完整扫描件")
    for x in checklist:
        L.append("- [ ] %s" % x)
    L.append("")

    L.append("## 六、边界说明\n")
    L.append("- 本报告由规则引擎自动生成，**只做风险预筛，不构成法律意见，不替代律师**。")
    L.append("- 关键词命中 ≠ 风险必然成立，请回原文看上下文；同一条款对甲乙方利弊相反。")
    L.append("- 涉及房产、股权、大额资金、涉外、知识产权转让等，请让执业律师复核。")
    return "\n".join(L)


def render_json(res):
    return json.dumps(res, ensure_ascii=False, indent=2)


# ================================================================== main
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("path")
    ap.add_argument("--format", default="markdown", choices=["markdown", "md", "json"])
    ap.add_argument("--output", default=None)
    ap.add_argument("--side", default=None)
    ap.add_argument("--all", action="store_true", help="不做类型过滤，输出全部 94 条规则的命中")
    args, _ = ap.parse_known_args()

    files = []
    if args.path == "-":
        files = [("<stdin>", sys.stdin.read())]
    else:
        if not os.path.exists(args.path):
            print("路径不存在：%s" % args.path)
            return 2
        paths = collect_files(args.path)
        if not paths:
            print("未找到可扫描文件（支持 %s）：%s" % (" ".join(sorted(SUPPORTED_EXT)), args.path))
            return 2
        for p in paths:
            try:
                t = load_text(p)
            except Exception as e:
                print("[跳过] %s：%s" % (os.path.basename(p), e), file=sys.stderr)
                continue
            if t and t.strip():
                files.append((p, t))

    if not files:
        print("没有可用的文本内容。若是扫描版 PDF，请先转成文字版或改用 docx/txt。")
        return 2

    total_chars = sum(len(t) for _, t in files)
    result = build_result(files, use_filter=not args.all)
    result["stats"] = {"files": len(files), "chars": total_chars}

    out = render_json(result) if args.format == "json" else render_markdown(result, args.side)

    if total_chars < 200 and any(f.lower().endswith(".pdf") for f in result["files"]):
        out = ("> ⚠️ 该 PDF 抽取到的文字很少（%d 字），可能是扫描件或加密文件。"
               "请先转成文字版 PDF / docx / txt 再扫描。\n\n" % total_chars) + out

    if args.output:
        io.open(args.output, "w", encoding="utf-8").write(out)
        print("已写入：%s（%d 字）" % (args.output, len(out)))
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())