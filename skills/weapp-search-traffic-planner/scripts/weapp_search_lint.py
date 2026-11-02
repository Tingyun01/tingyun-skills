#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weapp_search_lint.py —— 微信小程序命名合规 + 关键词布局 自检脚本

纯 Python 标准库，零第三方依赖。不联网、不读环境变量、不写用户目录。
用途：对用户提交的候选名称/简介/关键词表做机器可判的规则筛查，
      机器判不了的（名称唯一性、商标授权、类目是否可改）一律输出 [待人工确认]。

用法:
    python weapp_search_lint.py --self-check
    python weapp_search_lint.py --name "成都烘焙" --summary "新鲜采摘24小时直达，坏果包赔" --category "商家自营" --keywords "生鲜,配送,社区团购"
    python weapp_search_lint.py --file plan.json

输入 JSON 格式（--file）:
{
  "name": "候选名称",
  "summary": "简介文字",
  "category": "服务类目",
  "tags": ["标签1","标签2"],
  "keywords": ["词1","词2"],
  "pages": [{"path":"pages/x/index","title":"..."}]
}

退出码: 0 = 无必改项; 1 = 存在必改项; 2 = 参数错误
"""

import argparse
import json
import re
import sys
import unicodedata

# 规则来源: 微信小程序平台运营规范「账号基本信息规范」与「混淆行为」条款
# 核验日期 2026-11-02。规则会更新，以微信后台与官方文档最新版本为准。

# 通用词/品类词: 名称仅由这些词构成时官方明确要求改为「品牌+功能描述」
# 官��反例是「短裤短裙」——两个并列品类词，因此词典必须覆盖具体品类名，
# 而不只是「商城/工具」这类抽象词。
GENERIC_ONLY_WORDS = {
    # 抽象功能词
    "商城", "商店", "工具", "助手", "平台", "服务", "中心", "专家",
    "查询", "查询器", "计算器", "生成器", "资讯", "信息", "大全", "攻略",
    "教程", "视频", "音乐", "图片", "文字", "翻译", "预订", "预约",
    "计算", "查询", "下载", "下载器", "管理器", "盒子",
    # 具体品类词（并列品类词是官方点名反例的形态）
    "短裙", "短裤", "衣服", "服装", "女装", "男装", "童装", "鞋子", "帽子",
    "零食", "水果", "蔬菜", "生鲜", "快递", "搬家", "保洁", "装修", "空调",
    "家具", "家纺", "母婴", "玩具", "文具", "五金", "电器", "手机", "电脑",
    "汽车", "房子", "租房", "买房", "婚庆", "摄影", "化妆", "减肥", "养生",
    "算命", "占卜", "测试", "测试器", "游戏", "签文", "运势", "牌阵",
    "家政", "保洁", "维修", "保险", "贷款", "装修", "设计", "翻译", "家教",
}

# 商业化用语: 官方举例「免费自助餐」「女装巨便宜」「名牌包包清仓」
COMMERCIAL_WORDS = {
    "免费", "清仓", "巨便宜", "便宜", "低价", "特价", "打折", "折扣",
    "秒杀", "包邮", "正品", "官方直营", "厂家直销",
}

# 广告法极限用语
SUPERLATIVE_WORDS = {
    "最", "第一", "唯一", "国家级", "顶级", "最佳", "首选", "绝对",
    "极致", "全网", "独家", "首个", "冠军", "极致品",
}

# 平台自有品牌/常见冒用词（需授权）
PROTECTED_BRANDS = {
    "微信", "wechat", "腾讯", "tencent", "支付宝", "alipay", "抖音",
    "douyin", "百度", "百度一下", "apple", "iphone", "android",
}

# 与服务无关的高风险蹭词（堆砌热门搜索词）
HOT_KEYWORDS = {
    "下载", "免费观看", "在线观看", "小说", "影视", "音乐", "游戏",
    "直播", "交友", "聊天", "招聘", "刷单", "返利", "赚钱", "兼职",
    "彩票", "股票", "贷款", "贷款办理", "办证", "考试", "证书",
}

# 搜索意图分类关键词
INTENT_KEYWORDS = {
    "找功能": ["怎么", "如何", "生成", "制作", "工具", "教程", "步骤", "方法", "攻略"],
    "找地域": ["本地", "附近", "同城", "上门", "配送", "到家"],
    "找价格": ["价格", "多少钱", "费用", "报价", "收费", "优惠", "免费"],
    "找品牌": ["官方", "旗舰", "正品", "官网"],
}

# web-view 组件: 其内容不会被收录
WEBVIEW_PAT = re.compile(r"web-view|webview", re.I)

# 类目不可逆提示
IRREVERSIBLE_CATEGORY_HINTS = {"游戏", "小游戏"}

# 需要人工查证项（平台数据，脚本拿不到）
MANUAL_CHECKS = [
    ("A8", "名称 / 简介 / 服务类目 / 标签 四处是否在说同一件事", "逐项人工比对；官方要求服务范围与实际类目标签一致"),
    ("A11", "名称长度是否在后台允许区间", "微信公众平台 → 设置 → 基本设置 → 小程序名称（看字段旁字数提示）"),
    ("A12", "名称全局唯一性 / 近似查重", "微信搜一搜输入候选名，看是否已有同名或近似小程序"),
    ("A13", "第三方商标授权状态", "国家知识产权局商标查询入口核对"),
    ("A14", "服务类目提交后是否可修改", "微信公众平台 → 设置 → 基本设置 → 服务类目（游戏类目不可改）"),
    ("A15", "当前页面收录概况", "微信公众平台 → 功能 → 页面内容接入 → 收录概况（配置后需等待，非即时）"),
]

# 各位置允许的词数参考
MAX_NAME_CORE_WORDS = 2
SUMMARY_FRONT_CHARS = 28


def norm(text):
    """全角转半角 + 去空白，便于稳定匹配。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    return re.sub(r"\s+", "", text)


def hit_positions(text, words):
    """返回命中的词列表（去重）。"""
    t = norm(text)
    return sorted({w for w in words if w and w in t})


def is_generic_only(name):
    """名称是否仅由通用词/品类词构成。

    判定方式: 剥掉所有通用词/品类词后，剩余部分长度 <= 2（只允许极短的品牌残留）。
    例: 「短裤短裙」→ 剥掉「短裙」「短裤」后剩 0 字 → 命中;
        「成都烘焙·某某到家」→ 剥不掉 → 不命中。
    """
    n = norm(name)
    if not n:
        return False
    stripped = n
    for w in sorted(GENERIC_ONLY_WORDS, key=len, reverse=True):
        stripped = stripped.replace(w, "")
    return len(stripped) <= 2


def classify_intent(word):
    for intent, kws in INTENT_KEYWORDS.items():
        if any(k in word for k in kws):
            return intent
    return "找功能/泛词"


def check_name(name):
    """返回该名称的问题列表 [(行号, 检查项, 说明, 严重度)]"""
    issues = []
    n = norm(name)
    if not n:
        return [("A0", "名称为空", "名称不得为空", "必改")]

    if is_generic_only(name):
        issues.append(("A1", "名称仅由通用词/品类词构成",
                       "官方要求改为「品牌与产品描述或功能描述的结合」，如官方反例「短裤短裙」", "必改"))

    hot = hit_positions(name, HOT_KEYWORDS)
    if hot:
        issues.append(("A2", "名称含无关热门搜索词",
                       "堆砌无关搜索词属违规（官方条款：不得堆砌热门搜索词或与自身服务无关的关键词）", "必改"))

    comm = hit_positions(name, COMMERCIAL_WORDS)
    if comm:
        issues.append(("A3", "名称含商业化用语",
                       "官方举例「免费自助餐」「女装巨便宜」「名牌包包清仓」应删除商业化用语", "必改"))

    sup = hit_positions(name, SUPERLATIVE_WORDS)
    if sup:
        issues.append(("A4", "名称含广告法极限用语",
                       "命中: " + "、".join(sup), "必改"))

    prot = hit_positions(name, PROTECTED_BRANDS)
    if prot:
        issues.append(("A6", "名称疑似含第三方品牌标识",
                       "命中: " + "、".join(prot) + "；未经授权使用他人品牌标识属侵权，官方举例「微信小助手」", "需人工确认"))

    if len(n) > 30:
        issues.append(("A11", "名称长度超过 30 字符",
                       "业内经验区间为 4-30 字符，实际以注册后台提示为准", "需人工确认"))

    return issues


def check_summary(summary):
    issues = []
    s = norm(summary)
    if not s:
        return issues
    comm = hit_positions(summary, COMMERCIAL_WORDS)
    if comm:
        issues.append(("A3b", "简介含商业化用语",
                       "命中: " + "、".join(comm), "必改"))
    sup = hit_positions(summary, SUPERLATIVE_WORDS)
    if sup:
        issues.append(("A4b", "简介含广告法极限用语",
                       "命中: " + "、".join(sup), "必改"))
    prot = hit_positions(summary, PROTECTED_BRANDS)
    if prot:
        issues.append(("A6b", "简介疑似含第三方品牌标识",
                       "命中: " + "、".join(prot), "需人工确认"))
    hot = hit_positions(summary, HOT_KEYWORDS)
    if hot and len(hot) >= 3:
        issues.append(("A2b", "简介堆砌大量无关热门词",
                       "命中 " + str(len(hot)) + " 个: " + "、".join(hot[:6]) + "；数量多易被判堆砌", "必改"))
    return issues


def check_consistency(name, summary, category, tags):
    issues = []
    blob = norm(name + summary + category + "".join(tags or []))
    if category and IRREVERSIBLE_CATEGORY_HINTS & {norm(category)}:
        issues.append(("A9", "服务类目疑似为游戏类目",
                       "游戏类目一旦提交不可修改为其他类目，请确认后再提交", "需人工确认"))
    if not blob:
        issues.append(("A0", "基础信息全空", "请至少提供名称", "必改"))
    return issues


def check_keywords(keywords):
    """返回 (词级建议列表, 问题列表)"""
    rows = []
    issues = []
    for kw in keywords or []:
        w = norm(kw)
        if not w:
            continue
        if len(w) <= 2:
            level = "通用短词（慎用）"
        elif any(k in w for k in INTENT_KEYWORDS["找地域"]):
            level = "长尾场景词（地域）"
        elif any(k in w for k in INTENT_KEYWORDS["找价格"]):
            level = "长尾场景词（价格）"
        elif len(w) >= 5:
            level = "长尾词"
        else:
            level = "核心候选词"
        hot = hit_positions(w, HOT_KEYWORDS)
        row = {
            "词": kw,
            "建议词级": level,
            "搜索意图": classify_intent(w),
            "与业务相关性": "存疑（可能是蹭流量词）" if hot else "待用户判断",
        }
        if hot:
            row["命中风险词"] = "、".join(hot)
            issues.append(("A2c", "关键词含无关热门词",
                           "「%s」命中: %s" % (kw, "、".join(hot)), "必改"))
        rows.append(row)
    return rows, issues


def check_pages(pages):
    issues = []
    rows = []
    titles = []
    for p in pages or []:
        path = str(p.get("path", ""))
        title = str(p.get("title", ""))
        titles.append(norm(title))
        flags = []
        if WEBVIEW_PAT.search(path) or WEBVIEW_PAT.search(title):
            flags.append("web-view（内容不被收录）")
        if str(p.get("type", "")).lower() in ("web-view", "webview"):
            flags.append("web-view（内容不被收录）")
        if not title:
            flags.append("无独立标题")
        elif norm(title) in ("首页", "home", "index", "主页面"):
            flags.append("标题为泛称（等于放弃长尾落地页）")
        rows.append({"页面路径": path, "页面标题": title, "风险标记": "；".join(flags) or "无"})
        if flags:
            issues.append(("K", "页面收录风险",
                           "%s → %s" % (path, "；".join(flags)), "必改" if "无独立标题" in flags else "需人工确认"))
    dup = {t for t in titles if t}
    if len(dup) < len([t for t in titles if t]):
        issues.append(("K4", "多个页面共用同一标题",
                       "每个页面应独立标题，格式「核心关键词 + 品牌名」", "必改"))
    return rows, issues


def build_plan(data):
    name = data.get("name", "")
    summary = data.get("summary", "")
    category = data.get("category", "")
    tags = data.get("tags") or []
    keywords = data.get("keywords") or []
    pages = data.get("pages") or []

    issues = []
    issues += check_name(name)
    issues += check_summary(summary)
    issues += check_consistency(name, summary, category, tags)
    kw_rows, kw_issues = check_keywords(keywords)
    issues += kw_issues
    page_rows, page_issues = check_pages(pages)
    issues += page_issues

    return {
        "输入": {"名称": name, "简介": summary, "类目": category,
                "标签": tags, "关键词": keywords, "页面数": len(pages)},
        "命名与基础信息问题": issues,
        "关键词分级建议": kw_rows,
        "页面收录风险": page_rows,
        "必须人工查证项": [{"编号": c[0], "检查项": c[1], "去哪查": c[2]} for c in MANUAL_CHECKS],
        "必改项数": len([i for i in issues if i[3] == "必改"]),
        "需人工确认项数": len([i for i in issues if i[3] == "需人工确认"]),
    }


def print_plan(plan):
    out = sys.stdout
    out.write("=== 小程序搜一搜命名/关键词自检报告 ===\n")
    out.write("输入: %s\n\n" % json.dumps(plan["输入"], ensure_ascii=False))

    out.write("--- 一、命名与基础信息问题 ---\n")
    if not plan["命名与基础信息问题"]:
        out.write("  无机器可判问题。\n")
    for code, item, detail, sev in plan["命名与基础信息问题"]:
        out.write("  [%s] %s %s\n      -> %s\n" % (sev, code, item, detail))

    out.write("\n--- 二、关键词分级建议 ---\n")
    if not plan["关键词分级建议"]:
        out.write("  未提供关键词。\n")
    for r in plan["关键词分级建议"]:
        extra = "  (命中风险词: %s)" % r.get("命中风险词", "") if r.get("命中风险词") else ""
        out.write("  %-14s | %-16s | %s%s\n" % (r["词"], r["建议词级"], r["搜索意图"], extra))

    out.write("\n--- 三、页面收录风险 ---\n")
    if not plan["页面收录风险"]:
        out.write("  未提供页面。\n")
    for r in plan["页面收录风险"]:
        out.write("  %-28s | %-22s | %s\n" % (r["页面路径"], r["页面标题"], r["风险标记"]))

    out.write("\n--- 四、必须人工查证项（平台数据，脚本拿不到）---\n")
    for m in plan["必须人工查证项"]:
        out.write("  [%s] %s\n      去哪查: %s\n" % (m["编号"], m["检查项"], m["去哪查"]))

    out.write("\n=== 汇总: 必改 %d 项, 需人工确认 %d 项 ===\n" %
              (plan["必改项数"], plan["需人工确认项数"]))
    out.write("提示: 本脚本只做机器可判的规则筛查，不承诺搜索排名，也不替代微信平台的平台收录判定。\n")


def self_check():
    """合成自检: 验证规则命中与不误伤。"""
    cases = [
        # (输入, 期望出现的行号或None)
        ({"name": "短裤短裙", "summary": "女装", "category": "电商"}, "A1"),
        ({"name": "免费自助餐", "summary": "", "category": "餐饮"}, "A3"),
        ({"name": "最优家政", "summary": "", "category": "生活服务"}, "A4"),
        ({"name": "微信小助手", "summary": "", "category": "工具"}, "A6"),
        ({"name": "小说下载器", "summary": "", "category": "工具"}, "A2"),
        ({"name": "成都烘焙·某某到家", "summary": "新鲜采摘24小时直达，坏果包赔", "category": "商家自营"}, None),
        ({"name": "寿山趣测", "summary": "道系签文与性格测试卡片", "category": "工具"}, None),
    ]
    ok = 0
    fail = 0
    for data, expect in cases:
        plan = build_plan(data)
        codes = [i[0] for i in plan["命名与基础信息问题"]]
        if expect is None:
            if codes:
                fail += 1
                print("FAIL(误伤) %s -> %s" % (data["name"], codes))
            else:
                ok += 1
                print("OK   %s" % data["name"])
        else:
            if expect in codes:
                ok += 1
                print("OK   %s -> %s" % (data["name"], expect))
            else:
                fail += 1
                print("FAIL(漏判) %s 期望 %s 实得 %s" % (data["name"], expect, codes))

    # 关键词与页面用例
    plan = build_plan({
        "name": "测试号",
        "summary": "正常简介无问题",
        "category": "工具",
        "keywords": ["成都", "生鲜配送", "小说下载"],
        "pages": [
            {"path": "pages/index/index", "title": "首页"},
            {"path": "pages/wv/index", "title": "内容页", "type": "web-view"},
            {"path": "pages/detail/index", "title": ""},
        ],
    })
    kw_issues = [i[0] for i in plan["命名与基础信息问题"] if i[0] == "A2c"]
    pg = [r["风险标记"] for r in plan["页面收录风险"]]
    if kw_issues:
        ok += 1
        print("OK   关键词风险词命中")
    else:
        fail += 1
        print("FAIL 关键词风险词未命中")
    if any("web-view" in m for m in pg):
        ok += 1
        print("OK   web-view 标记")
    else:
        fail += 1
        print("FAIL web-view 未标记")
    if any("泛称" in m for m in pg):
        ok += 1
        print("OK   泛标题标记")
    else:
        fail += 1
        print("FAIL 泛标题未标记")
    if any("无独立标题" in m for m in pg):
        ok += 1
        print("OK   缺标题标记")
    else:
        fail += 1
        print("FAIL 缺标题未标记")

    print("\n自检: %d 通过 / %d 失败" % (ok, fail))
    return 0 if fail == 0 else 1


def main():
    ap = argparse.ArgumentParser(description="微信小程序命名合规与关键词布局自检（纯本地，无网络）")
    ap.add_argument("--self-check", action="store_true", help="运行合成自检")
    ap.add_argument("--name", default="")
    ap.add_argument("--summary", default="")
    ap.add_argument("--category", default="")
    ap.add_argument("--tags", default="", help="逗号分隔")
    ap.add_argument("--keywords", default="", help="逗号分隔")
    ap.add_argument("--pages", default="", help='JSON 数组字符串，如 [{"path":"pages/index/index","title":"首页"}]')
    ap.add_argument("--file", default="", help="从 JSON 文件读取全部输入")
    args = ap.parse_args()

    if args.self_check:
        return self_check()

    data = {}
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            sys.stderr.write("读取文件失败: %s\n" % e)
            return 2
    else:
        data = {
            "name": args.name,
            "summary": args.summary,
            "category": args.category,
            "tags": [t for t in args.tags.split(",") if t.strip()],
            "keywords": [k for k in args.keywords.split(",") if k.strip()],
            "pages": json.loads(args.pages) if args.pages.strip() else [],
        }
        if not (data["name"] or data["summary"] or data["keywords"]):
            sys.stderr.write("请至少提供 --name 或 --file，或使用 --self-check\n")
            return 2

    plan = build_plan(data)
    print_plan(plan)
    return 1 if plan["必改项数"] > 0 else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.exit(main())
