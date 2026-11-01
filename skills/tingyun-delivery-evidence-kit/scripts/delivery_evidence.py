#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""虚拟商品交付履约凭证助手 —— 交付清单、承诺核对与凭证页生成脚本。

用法::

    python scripts/delivery_evidence.py --input delivery.json
    python scripts/delivery_evidence.py --input delivery.json --json
    python scripts/delivery_evidence.py --input delivery.json --out ./输出目录
    python scripts/delivery_evidence.py --selftest

设计原则
--------
1. 只做客观归档与文本核对：计算校验值、统计件数与页数、把商品页承诺与实际交付物
   逐条比对、渲染规则文本。不评估内容质量，不判断纠纷责任，不生成法律结论。
2. 承诺核对的核心是“缺件可被发现”：任何一条商品页承诺如果在交付物里找不到对应项，
   都要明确输出“未在交付物中找到对应项”，而不是静默通过。
3. 退换规则文本一律保护消费者一侧：未下载可退、缺件与不符永久补发，
   且不排除消费者依法享有的权利。
4. 仅依赖 Python 标准库，零第三方依赖。
5. 输出不含任何 emoji；所有示例数据均为占位示例。

输入 JSON 格式示例
------------------
{
  "order": {
    "no": "20261101-XY-001",
    "platform": "示例平台",
    "product": "家庭保单体检表",
    "price": 19.9
  },
  "seller": {
    "name": "示例工作室",
    "contact": "示例联系方式"
  },
  "files": [
    {
      "path": "打包内容/保单汇总表.xlsx",
      "pages": 1,
      "items": 6,
      "note": "含 6 个表"
    },
    {
      "path": "打包内容/使用说明.pdf",
      "pages": 8,
      "items": 0,
      "note": ""
    }
  ],
  "commitments": [
    "商品页承诺：含 6 张体检表",
    "商品页承诺：附使用说明"
  ],
  "delivery_channel": "网盘链接",
  "prerequisites": "需使用百度网盘客户端下载",
  "valid_days": 30,
  "version": "v1.2",
  "refund_policy": "not_downloaded_refundable"
}

字段说明
--------
order      订单信息，no/platform/product/price 均可选，no 建议填写。
seller     卖家信息，name/contact 可选，contact 建议填写。
files      交付物清单。每项含 path（相对 base_dir 或绝对路径）、pages（页数）、
           items（条目数，如表格数/题目数）、note（该文件的件数说明）。
commitments 商品页或详情页的原始承诺，逐条录入，脚本逐条核对。
base_dir   交付物根目录，默认为输入 JSON 所在目录。
delivery_channel  交付渠道，如“网盘链接”“在线文档”。
prerequisites     前置条件说明（下载工具要求、账号要求、格式要求等）。
valid_days  下载有效期（天），缺失时视为未告知有效期。
version     交付版本号，会写入凭证页。
refund_policy 退换规则策略，取值：
               not_downloaded_refundable  未下载可退（默认）
               downloaded_no_refund       已下载不退
               missing_permanent_resend   缺件永久补发
               多个策略可用 "+" 连接，如 "not_downloaded_refundable+missing_permanent_resend"
sha256      可选，files 中可直接给定已算好的校验值，脚本不再重复读取文件。

输出
----
默认向标准输出打印中文文本报告；加 --json 输出结构化 JSON；
加 --out DIR 时额外写出“交付清单.csv”与“交付凭证.md”两个文件。

免责声明
--------
本脚本输出仅为交付管理与纠纷减少的辅助工具，不构成法律意见，也不构成对任何纠纷
责任的认定。所有规则文本需人工复核后使用，并以平台当期规则与法律法规为准。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta

try:  # 保证在 GBK 控制台环境下也能安全输出中文
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:  # pragma: no cover - 极端环境下静默跳过
    pass


DISCLAIMER = (
    "本工具输出仅为交付管理与纠纷减少的辅助材料，不构成法律意见，不构成对任何"
    "争议责任的认定，也不构成对平台规则的解释。规则文本使用前须人工复核，"
    "并以平台当期规则与法律法规为准。"
)

TOOL_NAME = "虚拟商品交付履约凭证助手"
TOOL_VERSION = "1.0.0"

# 承诺解析时需要忽略的填充词（不参与关键词匹配，避免误判为“已交付”）。
STOPWORDS = (
    "商品页承诺", "商品页", "详情页承诺", "详情页", "承诺", "商品描述", "描述",
    "含", "包含", "内含", "附", "附带", "附送", "赠送", "送", "送赠", "带",
    "提供", "配套", "共", "总计", "合计", "一共", "以及", "和", "与", "等",
    "可", "的", "了", "是", "有", "并", "其中", "包括", "内容", "资料",
    "一份", "一套", "全部", "完整版", "完整", "共计", "总", "量",
)

# 数量短语识别：数字 + 量词。
NUM_QUANT = r"(\d+(?:\.\d+)?|[零一二三四五六七八九十两]+)\s*(个|张|份|套|道|条|页|章|节|例|款|种)"

# 计数名词 -> 规范单位。
NOUN_UNIT = {
    "表": "表", "表格": "表", "工作表": "表", "页表": "表",
    "题": "题", "试题": "题", "题目": "题", "例题": "题", "练习题": "题",
    "页": "页",
    "章": "章", "章节": "章",
    "节": "节",
    "条": "条", "口诀": "条", "公式": "条",
    "套": "套", "模板": "套",
    "份": "份",
    "文件": "文件", "资料包": "文件",
}

# 单位 -> 可能的英文/口语同义词（用于关键词命中判断）。
UNIT_WORDS = {
    "表": ("表",),
    "题": ("题",),
    "页": ("页",),
    "章": ("章",),
    "节": ("节",),
    "条": ("条", "口诀"),
    "套": ("套", "模板"),
    "份": ("份",),
    "文件": ("文件",),
}

# 单位 -> 交付物文件名的判定字符（用于 items 兜底计数）。
UNIT_NAME_CHAR = {
    "表": "表", "题": "题", "条": "条", "套": "套", "份": "份",
    "章": "章", "节": "节",
}

# 承诺与交付物中常见的模糊描述词（高纠纷风险词）。
VAGUE_WORDS = (
    "全套", "大全", "全部", "完整版", "精讲", "最全", "最全版", "全部资料",
    "全部内容", "应有尽有", "包罗万象", "超值", "海量", "从零到一",
)

# 交付形态类风险表述（只提示，不下结论）。
FORM_RISK_WORDS = (
    "自行整理", "自己整理", "需自行", "仅提供问题", "只列问题", "仅题目",
    "部分内容", "随机发放", "示例内容", "后续补发", "陆续更新",
)

CN_DIGITS = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def parse_cn_number(text):
    """解析中文数字（支持 0~99 的常见写法）。

    Args:
        text: 数字文本，如 "12"、“六”、“二十三”。

    Returns:
        int，解析成功返回整数，失败返回 None。
    """
    text = (text or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if "十" not in text:
        total = 0
        for ch in text:
            if ch not in CN_DIGITS:
                return None
            total = total * 10 + CN_DIGITS[ch] if total else CN_DIGITS[ch]
        return total
    head, _, tail = text.partition("十")
    tens = 1
    if head:
        if head not in CN_DIGITS:
            return None
        tens = CN_DIGITS[head]
    ones = 0
    if tail:
        if len(tail) != 1 or tail not in CN_DIGITS:
            return None
        ones = CN_DIGITS[tail]
    return tens * 10 + ones


def _text(value):
    """把任意值转为去除首尾空白的字符串，None 转为空串。"""
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "、".join(_text(item) for item in value)
    if isinstance(value, dict):
        return ""
    return str(value).strip()


def _num(value, default=0):
    """把任意值安全转为数值，失败返回默认值。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return default
        try:
            return float(cleaned)
        except ValueError:
            cn = parse_cn_number(cleaned)
            if cn is not None:
                return cn
    return default


def _int(value, default=0):
    """把任意值安全转为整数，失败返回默认值。"""
    result = _num(value, default)
    try:
        return int(round(result))
    except (TypeError, ValueError):
        return default


def sha256_of(path):
    """计算文件的 SHA-256 十六进制摘要。

    Args:
        path: 文件路径。

    Returns:
        str，小写十六进制摘要；文件不存在或不可读时返回空串。
    """
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except (OSError, ValueError):
        return ""
    return digest.hexdigest()


def file_format(path):
    """根据扩展名推断可读格式名。"""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext.upper() if ext else "未知格式"


def load_json(path):
    """读取并解析输入 JSON 文件。

    Args:
        path: 文件路径。

    Returns:
        tuple，解析后的数据与 None；失败时返回 (None, 错误信息)。
    """
    if not os.path.isfile(path):
        return None, "错误：找不到输入文件 {0}".format(path)
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle), None
    except json.JSONDecodeError as exc:
        return None, "错误：输入文件不是合法 JSON（{0}）：{1}".format(path, exc)
    except OSError as exc:
        return None, "错误：无法读取输入文件（{0}）：{1}".format(path, exc)


def extract_file_units(text):
    """从一段文本（文件名 + 备注）中抽取各单位的件数。

    Args:
        text: 待解析文本。

    Returns:
        dict，键为单位名（表/题/页/章/节/条/套/份），值为件数。
    """
    result = {}
    if not text:
        return result
    consumed = [False] * len(text)
    for match in re.finditer(NUM_QUANT, text):
        number = parse_cn_number(match.group(1))
        if number is None:
            continue
        quant = match.group(2)
        tail = text[match.end():match.end() + 12]
        unit = None
        for noun in re.finditer(r"表|表格|工作表|试题|题目|例题|练习题|口诀|公式|章节|模板|资料包|题|页|章|节|条|套|份|文件", tail):
            unit = NOUN_UNIT.get(noun.group(0))
            if unit:
                break
        if unit is None:
            unit = NOUN_UNIT.get(quant, quant)
        if unit in ("个", "张", "道", "例", "款", "种"):
            unit = None
        if unit is None:
            continue
        overlap = any(consumed[match.start():match.end()])
        if overlap:
            continue
        for index in range(match.start(), match.end()):
            consumed[index] = True
        result[unit] = result.get(unit, 0) + number
    return result


def build_manifest(data, base_dir):
    """构建交付清单，逐文件计算校验值并统计件数。

    Args:
        data: 输入 JSON 解析结果。
        base_dir: 交付物根目录。

    Returns:
        list，字典列表，每个字典描述一个交付文件。
    """
    manifest = []
    files = data.get("files") or []
    if not isinstance(files, list):
        files = []
    for index, raw in enumerate(files, start=1):
        if not isinstance(raw, dict):
            raw = {"path": _text(raw)}
        rel_path = _text(raw.get("path"))
        abs_path = rel_path
        if rel_path and not os.path.isabs(rel_path):
            abs_path = os.path.join(base_dir, rel_path)
        exists = bool(rel_path) and os.path.isfile(abs_path)
        checksum = _text(raw.get("sha256")).lower()
        if not checksum and exists:
            checksum = sha256_of(abs_path)
        size = 0
        if exists:
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                size = 0
        manifest.append({
            "index": index,
            "path": rel_path,
            "name": os.path.basename(rel_path) if rel_path else "(未命名文件)",
            "format": _text(raw.get("format")) or file_format(rel_path),
            "pages": _int(raw.get("pages"), 0),
            "items": _int(raw.get("items"), 0),
            "note": _text(raw.get("note")),
            "exists": exists,
            "size": size,
            "sha256": checksum,
            "sha256_short": checksum[:16],
            "abs_path": abs_path,
        })
    return manifest


def compute_actual_counts(manifest):
    """统计实际交付物中可核对的件数。

    Args:
        manifest: build_manifest 产出的清单。

    Returns:
        tuple，(单位计数表, 计数来源说明表)。
    """
    note_counts = {}
    note_sources = {}
    for row in manifest:
        blob = "{0} {1}".format(row["name"], row["note"])
        for unit, number in extract_file_units(blob).items():
            note_counts[unit] = note_counts.get(unit, 0) + number
            note_sources.setdefault(unit, []).append(
                "{0}：{1}".format(row["name"], number))
    totals = {
        "文件": len(manifest),
        "页": sum(row["pages"] for row in manifest),
    }
    for unit, number in note_counts.items():
        totals.setdefault(unit, number)
    item_counts = {}
    for row in manifest:
        if row["items"] <= 0:
            continue
        blob = "{0} {1}".format(row["name"], row["note"])
        for unit, char in UNIT_NAME_CHAR.items():
            if char in blob:
                item_counts[unit] = item_counts.get(unit, 0) + row["items"]
                break
    for unit, number in item_counts.items():
        if unit not in totals:
            totals[unit] = number
            note_sources.setdefault(unit, []).append(
                "按登记条目数累计：{0}".format(number))
    return totals, note_sources


def parse_commitment(raw):
    """解析一条商品页承诺，抽出数量单位或关键词。

    Args:
        raw: 承诺原文。

    Returns:
        dict，含 text、count、unit、tokens 字段。
    """
    text = _text(raw)
    result = {"text": text, "count": None, "unit": None, "tokens": []}
    for match in re.finditer(NUM_QUANT, text):
        number = parse_cn_number(match.group(1))
        if number is None:
            continue
        quant = match.group(2)
        tail = text[match.end():match.end() + 14]
        unit = None
        for noun in re.finditer(
                r"表格|工作表|试题|题目|例题|练习题|口诀|公式|章节|模板|资料包|表|题|页|章|节|条|套|份|文件",
                tail):
            unit = NOUN_UNIT.get(noun.group(0))
            if unit:
                break
        if unit is None:
            unit = NOUN_UNIT.get(quant, quant)
        if unit in ("个", "张", "道", "例", "款", "种"):
            unit = None
        if unit is None:
            continue
        result["count"] = number
        result["unit"] = unit
        break
    cleaned = text
    for word in STOPWORDS:
        cleaned = cleaned.replace(word, " ")
    cleaned = re.sub(r"[:：,，。、;；()（）\[\]【】\"'’“”]+", " ", cleaned)
    chunks = [chunk.strip() for chunk in cleaned.split()]
    result["tokens"] = [chunk for chunk in chunks if len(chunk) >= 2]
    return result


def match_commitment(commitment, manifest, totals, sources):
    """把一条承诺与实际交付物比对。

    Args:
        commitment: parse_commitment 的结果。
        manifest: 交付清单。
        totals: 实际件数统计。
        sources: 计数来源说明。

    Returns:
        dict，含 status、wording、evidence 字段。
    """
    text = commitment["text"]
    count = commitment["count"]
    unit = commitment["unit"]
    blob = " ".join(
        "{0} {1}".format(row["name"], row["note"]) for row in manifest).lower()
    if count is not None and unit:
        actual = totals.get(unit)
        if actual is None:
            return {
                "text": text,
                "count": count,
                "unit": unit,
                "status": "not_found",
                "wording": "未在交付物中找到对应项：承诺“{0}”，交付物中没有可核对的{1}数。".format(text, unit),
                "evidence": [],
            }
        if actual < count:
            return {
                "text": text,
                "count": count,
                "unit": unit,
                "status": "mismatch",
                "wording": "件数不符：承诺“{0}”，实际交付 {1} 个{2}，缺 {3} 个{2}。".format(
                    text, actual, unit, count - actual),
                "evidence": sources.get(unit, []),
            }
        if actual > count:
            return {
                "text": text,
                "count": count,
                "unit": unit,
                "status": "matched_more",
                "wording": "已对应：承诺“{0}”，实际交付 {1} 个{2}，超出承诺 {3} 个。".format(
                    text, actual, unit, actual - count),
                "evidence": sources.get(unit, []),
            }
        return {
            "text": text,
            "count": count,
            "unit": unit,
            "status": "matched",
            "wording": "已对应：承诺“{0}”，实际交付 {1} 个{2}。".format(text, actual, unit),
            "evidence": sources.get(unit, []),
        }
    tokens = commitment["tokens"]
    if tokens:
        hit = None
        for token in tokens:
            if token.lower() in blob:
                hit = token
                break
        if hit:
            return {
                "text": text,
                "count": count,
                "unit": unit,
                "status": "matched",
                "wording": "已对应：承诺“{0}”，在交付物中命中关键词“{1}”。".format(text, hit),
                "evidence": [hit],
            }
        return {
            "text": text,
            "count": count,
            "unit": unit,
            "status": "not_found",
            "wording": "未在交付物中找到对应项：承诺“{0}”，交付物文件名与备注中未见对应内容。".format(text),
            "evidence": [],
        }
    return {
        "text": text,
        "count": count,
        "unit": unit,
        "status": "unknown",
        "wording": "无法自动核对：承诺“{0}”，未识别到可计数的数量或关键词，请人工逐字核对。".format(text),
        "evidence": [],
    }


def render_refund_policy(keys, order, seller, valid_days):
    """渲染退换规则文本。

    Args:
        keys: 策略键列表。
        order: 订单信息。
        seller: 卖家信息。
        valid_days: 下载有效期天数。

    Returns:
        tuple，(策略名列表, 规则文本)。
    """
    order_no = _text(order.get("no")) or "(订单号待填)"
    seller_name = _text(seller.get("name")) or "卖家"
    names = []
    blocks = []
    for key in keys:
        if key == "not_downloaded_refundable":
            names.append("未下载可退")
            blocks.append(
                "【策略一 · 未下载可退】\n"
                "1. 判定标准：以交付链接是否被访问、文件是否被解压或打开为准。买家在未下载、"
                "未解压、未打开任何交付文件的前提下，可申请全额退款，无需说明理由。\n"
                "2. 时效：自交付链接发出之日起 24 小时内提出申请，卖家当日确认退款。\n"
                "3. 已下载但发现问题：不受本策略限制，按策略三处理（缺件与不符永久补发）。\n"
                "4. 争议处理：双方对“是否已下载”有分歧时，以交付清单中的校验值与买家回执"
                "（下载记录或截图）为准；无回执的按未下载处理。"
            )
        elif key == "downloaded_no_refund":
            names.append("已下载不退")
            blocks.append(
                "【策略二 · 已下载不退（附缺件补发）】\n"
                "1. 适用范围：买家已解压或打开交付文件，且交付物与商品页承诺一致、件数齐全。\n"
                "2. 条款：属于虚拟商品且已完成交付并被下载的，不支持无理由退款。\n"
                "3. 例外（优先适用）：出现缺件、数量不符、形态与描述不符、文件损坏无法打开、"
                "交付链接失效且无法补发的，卖家提供等值补发或退款；缺件与不符项永久补发。\n"
                "4. 说明：已下载不退仅适用于“内容齐全且与描述一致”的情形，"
                "不适用于交付缺件或与描述不符的情形。"
            )
        elif key == "missing_permanent_resend":
            names.append("缺件永久补发")
            blocks.append(
                "【策略三 · 缺件永久补发】\n"
                "1. 适用范围：交付物中缺少商品页承诺的任何一项，或数量、形态与承诺不一致。\n"
                "2. 处理：卖家在买家提出后 24 小时内免费补发缺失部分，并同步更新交付清单"
                "与校验值；同一缺件项再次发生仍免费补发，不设次数与时限上限。\n"
                "3. 无法补发：若该内容确因版权、平台规则或自身下架原因无法继续提供，"
                "卖家按未交付处理并全额退款。\n"
                "4. 举证：买家可按交付凭证页中的校验值自行核对文件完整性，"
                "卖家按同一校验值复核，双方结论应一致。"
            )
    if not blocks:
        blocks.append(
            "【默认 · 未下载可退 + 缺件永久补发】\n"
            "1. 未下载、未解压、未打开交付文件的，可申请全额退款。\n"
            "2. 缺件、数量不符或与描述不符的，永久免费补发。\n"
            "3. 已下载且内容齐全、与描述一致的，按虚拟商品不重复退款处理。")
        names.append("未下载可退 + 缺件永久补发")
    header = (
        "退换与补发规则（订单 {0}，卖家 {1}）\n"
        "交付链接有效期：{2}\n".format(
            order_no, seller_name,
            ("自交付之日起 {0} 天内有效".format(valid_days)) if valid_days else "未设定（须补充）"))
    footer = (
        "\n以上规则不排除、不限制消费者依法享有的权利，包括但不限于就商品与描述不符、"
        "商品存在质量问题而主张退货退款或赔偿的权利；如与平台当期规则或法律法规不一致，"
        "以对消费者更有利者及法律法规的强制性规定为准。规则须经卖家人工复核后使用。")
    return names, header + "\n\n".join(blocks) + footer


def run_checks(data, manifest, totals, cross_results):
    """执行可自动化的交付前自检（15 项中的可判定部分）。

    Args:
        data: 输入数据。
        manifest: 交付清单。
        totals: 件数统计。
        cross_results: 承诺核对结果列表。

    Returns:
        list，findings 列表，每条含 level、wording、suggestion。
    """
    findings = []
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    seller = data.get("seller") if isinstance(data.get("seller"), dict) else {}

    def add(level, wording, suggestion):
        findings.append({"level": level, "wording": wording, "suggestion": suggestion})

    missing = [row["name"] for row in manifest if not row["exists"]]
    if missing:
        add("error",
            "交付文件缺失：{0} 个文件在交付目录中找不到。".format(len(missing)),
            "补齐缺失文件后重新生成凭证，或从交付清单中删除并同步修改商品页承诺：{0}".format(
                "、".join(missing)))
    elif manifest:
        add("ok", "交付文件全部存在于交付目录中，共 {0} 个。".format(len(manifest)),
            "保持打包目录与清单一致，不要临时替换文件。")

    empty = [row["name"] for row in manifest if row["exists"] and row["size"] == 0]
    if empty:
        add("error",
            "存在空文件：{0} 个文件大小为 0 字节。".format(len(empty)),
            "空文件在买家侧会表现为“无法打开”，属于形态不符，请重新导出后交付：{0}".format(
                "、".join(empty)))
    elif manifest:
        add("ok", "未发现 0 字节空文件。", "保持导出完整。")

    no_hash = [row["name"] for row in manifest if row["exists"] and not row["sha256"]]
    if no_hash:
        add("error",
            "有 {0} 个文件未能计算校验值，买家无法自行核对完整性。".format(len(no_hash)),
            "确认文件可读后重新生成凭证：{0}".format("、".join(no_hash)))
    elif manifest:
        add("ok", "全部文件均已生成 SHA-256 校验值。", "把校验值随交付消息一并发给买家。")

    hint_names = ("说明", "目录", "索引", "readme", "使用", "手册", "指南")
    has_guide = any(
        any(word in row["name"].lower() for word in hint_names) for row in manifest)
    if not has_guide:
        add("warn", "交付物中未发现使用说明或目录类文件。",
            "补一份说明文件（使用方式、文件对应关系、前置要求），这是“形态不符”投诉最常见的落点。")
    else:
        add("ok", "已包含使用说明或目录类文件。", "在说明中写明每个文件对应商品页的哪一条承诺。")

    if not _text(order.get("no")):
        add("error", "订单号为空，凭证无法与具体订单绑定。",
            "补填订单号；无平台单号时可使用自建流水号（示例格式：日期-渠道-序号）。")
    else:
        add("ok", "订单号已填写：{0}。".format(_text(order.get("no"))), "确认与平台订单号一致。")

    version = _text(data.get("version"))
    if version:
        add("ok", "交付版本号已设定：{0}。".format(version), "更新内容时同步升版并重新出凭证。")
    else:
        add("warn", "未设定交付版本号。",
            "补一个版本号（如 v1.2），便于区分“补发前”与“补发后”的交付。")

    not_found = [item["text"] for item in cross_results if item["status"] == "not_found"]
    mismatch = [item["text"] for item in cross_results if item["status"] == "mismatch"]
    unknown = [item["text"] for item in cross_results if item["status"] == "unknown"]
    if not_found:
        add("error",
            "有 {0} 条商品页承诺未在交付物中找到对应项。".format(len(not_found)),
            "逐条补齐后再交付；无法补齐的要在商品页先行修改承诺，避免交付与描述不一致：{0}".format(
                "；".join(not_found)))
    if mismatch:
        add("error",
            "有 {0} 条承诺的件数与实际交付不符。".format(len(mismatch)),
            "补足件数，或把商品页承诺改成实际可交付的数量：{0}".format("；".join(mismatch)))
    if unknown:
        add("warn",
            "有 {0} 条承诺无法自动核对。".format(len(unknown)),
            "人工逐字核对以下承诺与交付物的对应关系，并在清单备注中写明：{0}".format(
                "；".join(unknown)))
    if not (not_found or mismatch or unknown):
        add("ok", "商品页承诺与实际交付物逐条对应，未发现缺件。",
            "保持商品页承诺与交付版本同步修改。")

    page_mismatch = [item for item in cross_results
                     if item.get("unit") == "页" and item["status"] in ("mismatch", "not_found")]
    if page_mismatch:
        add("error", "页数口径的承诺与实际交付不一致。",
            "页数是最容易被买家直接点数的项，交付前用阅读器确认总页数并写入清单。")
    elif totals.get("页"):
        add("ok", "页数口径一致，实际交付共 {0} 页。".format(totals["页"]), "在清单中标注每个文件的页数。")

    channel = _text(data.get("delivery_channel"))
    prereq = _text(data.get("prerequisites"))
    if not channel:
        add("error", "未填写交付渠道。",
            "写明交付渠道（如网盘链接、在线文档、邮件附件），渠道本身是纠纷高频点。")
    else:
        add("ok", "交付渠道已声明：{0}。".format(channel), "把链接与凭证页一起发出。")
    if not prereq:
        add("warn", "未声明交付前置条件。",
            "写明下载工具要求（是否必须用某网盘客户端）、账号要求、文件格式与打开方式；"
            "前置条件未告知是典型的退款理由。")
    elif channel and ("网盘" in channel or "网盘" in prereq):
        add("ok", "已声明前置条件：{0}。".format(prereq), "同时在商品页首屏显著位置重复一次。")

    valid_days = _int(data.get("valid_days"), 0)
    if valid_days <= 0:
        add("error", "未告知下载链接有效期。",
            "给出明确的有效期天数（如 30 天）并写进商品页与凭证页；链接有效期未告知极易被判定为商家单方切断获取渠道。")
    else:
        add("ok", "下载有效期已设定：自交付之日起 {0} 天。".format(valid_days),
            "到期前主动提醒续期，或到期前 3 天统一延长一次。")

    policy_key = _text(data.get("refund_policy"))
    known = ("not_downloaded_refundable", "downloaded_no_refund", "missing_permanent_resend")
    keys = [part.strip() for part in policy_key.split("+") if part.strip()]
    if not keys:
        keys = ["not_downloaded_refundable"]
    bad = [key for key in keys if key not in known]
    if bad:
        add("error", "退换规则策略取值无法识别：{0}。".format("、".join(bad)),
            "取值只能是 not_downloaded_refundable / downloaded_no_refund / missing_permanent_resend，多个用 + 连接。")
    else:
        add("ok", "退换规则策略已选定并可正常渲染。", "规则文本须人工复核后再发给买家。")

    if not _text(seller.get("contact")):
        add("warn", "卖家联系方式未填写。", "留一个可回复的联系方式，便于买家核对时直接找你，减少升级为平台投诉的概率。")
    else:
        add("ok", "卖家联系方式已留痕。", "保持与商品页展示一致。")

    price = _num(order.get("price"), -1)
    if price < 0:
        add("warn", "订单信息中未填写成交金额。", "补填金额，让凭证页与订单金额一致。")
    else:
        add("ok", "订单金额已记录：{0}。".format(price), "确认与实际成交价一致。")

    checksums = [row["sha256"] for row in manifest if row["sha256"]]
    duplicated = set()
    seen = set()
    for value in checksums:
        if value in seen:
            duplicated.add(value[:16])
        seen.add(value)
    if duplicated:
        add("warn", "有 {0} 组文件内容完全相同（校验值重复）。".format(len(duplicated)),
            "重复内容通常是误打包或占位文件未替换，请逐个核对：{0}".format("、".join(sorted(duplicated))))
    elif manifest:
        add("ok", "未发现内容完全相同的重复文件。", "保持打包目录干净。")

    blob = " ".join([_text(order.get("product"))] +
                    [item["text"] for item in cross_results])
    vague_hit = [word for word in VAGUE_WORDS if word in blob]
    if vague_hit:
        add("warn", "承诺或商品标题中出现模糊描述词：{0}。".format("、".join(vague_hit)),
            "把“全套/大全/精讲”替换成可点数的写法（X章=Y节、共N页、含M题），"
            "模糊词是“货不对板”投诉最容易站得住脚的入口。")
    else:
        add("ok", "未发现高风险模糊描述词。", "继续使用可核对的数字表述。")

    form_hit = [word for word in FORM_RISK_WORDS if word in blob]
    if form_hit:
        add("warn", "承诺中出现交付形态类表述：{0}。".format("、".join(form_hit)),
            "把“只列问题让买家自己整理”这类形态写清（是否含答案、答案在哪个文件、"
            "格式为可打印还是仅电子版），形态不符是最高频的投诉理由之一。")
    else:
        add("ok", "未发现交付形态类风险表述。", "在商品页补一句“交付形态”说明更稳。")

    return findings


def render_manifest_rows(manifest):
    """把清单渲染为 Markdown 表格行。"""
    lines = []
    for row in manifest:
        size_text = "未找到" if not row["exists"] else "{0} KB".format(max(1, round(row["size"] / 1024)))
        count_parts = []
        if row["pages"]:
            count_parts.append("{0} 页".format(row["pages"]))
        if row["items"]:
            count_parts.append("{0} 条".format(row["items"]))
        count_text = " / ".join(count_parts) if count_parts else "-"
        lines.append(
            "| {0} | {1} | {2} | {3} | {4} | {5} | {6} |".format(
                row["index"], row["name"], row["format"], count_text,
                row["sha256_short"] or "-", size_text, row["note"] or "-"))
    return lines


def render_evidence(data, manifest, totals, cross_results, policy_names, policy_text,
                    findings, generated_at):
    """生成买家可见的《交付凭证》Markdown 文本。

    Args:
        data: 输入数据。
        manifest: 交付清单。
        totals: 件数统计。
        cross_results: 承诺核对结果。
        policy_names: 策略名列表。
        policy_text: 规则文本。
        findings: 自检结果。
        generated_at: 生成时间。

    Returns:
        str，Markdown 文本。
    """
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    seller = data.get("seller") if isinstance(data.get("seller"), dict) else {}
    lines = []
    lines.append("# 交付凭证")
    lines.append("")
    lines.append("本凭证用于记录本次交付的内容、数量与完整性，方便买家自行核对，也方便卖家在"
                 "发生争议时说明实际交付了什么。请在收到交付物后核对一遍。")
    lines.append("")
    lines.append("## 一、订单与交付信息")
    lines.append("")
    lines.append("| 项目 | 内容 |")
    lines.append("| --- | --- |")
    lines.append("| 订单号 | {0} |".format(_text(order.get("no")) or "(待填)"))
    lines.append("| 交付平台 | {0} |".format(_text(order.get("platform")) or "(待填)"))
    lines.append("| 商品名称 | {0} |".format(_text(order.get("product")) or "(待填)"))
    lines.append("| 成交金额 | {0} |".format(_text(order.get("price")) or "(待填)"))
    lines.append("| 卖家 | {0} |".format(_text(seller.get("name")) or "(待填)"))
    lines.append("| 卖家联系方式 | {0} |".format(_text(seller.get("contact")) or "(待填)"))
    lines.append("| 交付渠道 | {0} |".format(_text(data.get("delivery_channel")) or "(待填)"))
    lines.append("| 交付前置条件 | {0} |".format(_text(data.get("prerequisites")) or "无特殊要求"))
    lines.append("| 交付版本 | {0} |".format(_text(data.get("version")) or "(未标注)"))
    lines.append("| 下载有效期 | {0} |".format(
        "自交付之日起 {0} 天".format(_int(data.get("valid_days"), 0))
        if _int(data.get("valid_days"), 0) else "未设定"))
    lines.append("| 交付时间戳 | {0} |".format(generated_at))
    lines.append("")
    lines.append("## 二、交付清单摘要")
    lines.append("")
    lines.append("本次交付共 **{0}** 个文件，合计 **{1}** 页，合计 **{2}** 个条目（表格、题目、"
                 "章节等按登记口径计）。".format(
                     totals.get("文件", 0), totals.get("页", 0),
                     sum(row["items"] for row in manifest)))
    lines.append("")
    lines.append("| 序号 | 文件名 | 格式 | 页数/条目数 | 校验值(前16位) | 大小 | 备注 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    lines.extend(render_manifest_rows(manifest))
    lines.append("")
    lines.append("## 三、商品页承诺逐条核对")
    lines.append("")
    lines.append("| 序号 | 商品页承诺 | 核对结果 | 说明 |")
    lines.append("| --- | --- | --- | --- |")
    status_text = {
        "matched": "已对应",
        "matched_more": "已对应（多于承诺）",
        "mismatch": "件数不符",
        "not_found": "未在交付物中找到对应项",
        "unknown": "需人工核对",
    }
    for index, item in enumerate(cross_results, start=1):
        lines.append("| {0} | {1} | {2} | {3} |".format(
            index, item["text"], status_text.get(item["status"], item["status"]),
            item["wording"]))
    lines.append("")
    lines.append("## 四、买家如何自行核对")
    lines.append("")
    lines.append("1. **数件数**：按上表逐个打开文件，核对文件个数、页数与条目数是否与上表一致。")
    lines.append("2. **验校验值**：每个文件的校验值见上表。校验值相同的文件内容完全一致，"
                 "校验值不同的文件内容一定不同。文件被替换、截断或损坏时，校验值会随之改变。")
    lines.append("3. **查缺件**：若上表第三列出现“未在交付物中找到对应项”或“件数不符”，"
                 "说明该条承诺尚未兑现，请直接联系卖家补发。")
    lines.append("")
    lines.append("## 五、有效期与后续服务")
    lines.append("")
    valid_days = _int(data.get("valid_days"), 0)
    if valid_days:
        lines.append("- 下载链接有效期：自交付之日起 **{0} 天**；到期前卖家会主动提醒延长，"
                     "不会在未通知的情况下直接取消分享。".format(valid_days))
    else:
        lines.append("- 下载链接有效期：**未设定**，卖家将在确认后补齐并重新出具本凭证。")
    lines.append("- 缺件、数量不符或与描述不符的内容，**永久免费补发**，不设次数与时限上限。")
    lines.append("")
    lines.append("## 六、退换与补发规则")
    lines.append("")
    lines.append("适用策略：{0}".format("、".join(policy_names)))
    lines.append("")
    lines.append(policy_text)
    lines.append("")
    lines.append("## 七、争议处理路径")
    lines.append("")
    lines.append("1. **先核对凭证**：对照第二、三节逐项核对，缺什么、哪一项不符写清楚。")
    lines.append("2. **联系卖家补发**：把凭证编号与缺失项一并发给卖家，缺件与不符项 24 小时内补发。")
    lines.append("3. **规则适用争议**：如双方对适用哪一条规则有分歧，以保护消费者一侧的约定与"
                 "平台当期规则为准；具体流程以平台当期规则为准。")
    lines.append("4. **平台渠道**：上述沟通未达成一致的，可通过购买平台的官方售后通道发起售后申请。")
    lines.append("")
    lines.append("## 八、买家确认")
    lines.append("")
    lines.append("请在核对完成后，于下方确认（复制回复即可）：")
    lines.append("")
    lines.append("```text")
    lines.append("确认回执")
    lines.append("订单号：{0}".format(_text(order.get("no")) or "(待填)"))
    lines.append("交付版本：{0}".format(_text(data.get("version")) or "(未标注)"))
    lines.append("交付时间戳：{0}".format(generated_at))
    lines.append("文件个数：{0}".format(totals.get("文件", 0)))
    lines.append("总页数：{0}".format(totals.get("页", 0)))
    lines.append("核对结论：□ 全部一致　□ 有缺件（缺件项：____________）　□ 有不符（具体：____________）")
    lines.append("确认人昵称：____________　确认时间：____________")
    lines.append("```")
    lines.append("")
    lines.append("未收到确认回执不影响买家的法定权利，也不影响卖家就缺件与不符进行补发。")
    lines.append("")
    lines.append("## 九、交付前自检结果")
    lines.append("")
    lines.append("| 级别 | 检查结论 | 建议 |")
    lines.append("| --- | --- | --- |")
    for item in findings:
        lines.append("| {0} | {1} | {2} |".format(
            item["level"], item["wording"], item["suggestion"]))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(DISCLAIMER)
    lines.append("")
    return "\n".join(lines)


def build_report(data, base_dir, now=None):
    """构建完整报告数据。

    Args:
        data: 输入 JSON。
        base_dir: 交付物根目录。
        now: 生成时间，datetime 对象，默认为当前时间。

    Returns:
        dict，报告数据，可直接 json.dumps。
    """
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    seller = data.get("seller") if isinstance(data.get("seller"), dict) else {}
    generated_at = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    manifest = build_manifest(data, base_dir)
    totals, sources = compute_actual_counts(manifest)
    commitments = data.get("commitments") or []
    if not isinstance(commitments, list):
        commitments = []
    cross_results = []
    for raw in commitments:
        parsed = parse_commitment(raw)
        cross_results.append(match_commitment(parsed, manifest, totals, sources))
    findings = run_checks(data, manifest, totals, cross_results)
    keys = [part.strip() for part in _text(data.get("refund_policy")).split("+") if part.strip()]
    if not keys:
        keys = ["not_downloaded_refundable"]
    policy_names, policy_text = render_refund_policy(keys, order, seller, _int(data.get("valid_days"), 0))
    evidence = render_evidence(data, manifest, totals, cross_results, policy_names,
                               policy_text, findings, generated_at)
    errors = sum(1 for item in findings if item["level"] == "error")
    warns = sum(1 for item in findings if item["level"] == "warn")
    return {
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "generated_at": generated_at,
        "order": order,
        "seller": seller,
        "base_dir": base_dir,
        "totals": totals,
        "manifest": [
            {
                "index": row["index"],
                "path": row["path"],
                "name": row["name"],
                "format": row["format"],
                "pages": row["pages"],
                "items": row["items"],
                "note": row["note"],
                "exists": row["exists"],
                "size": row["size"],
                "sha256": row["sha256"],
                "sha256_short": row["sha256_short"],
            }
            for row in manifest
        ],
        "commitment_checks": cross_results,
        "findings": findings,
        "summary": {
            "file_count": totals.get("文件", 0),
            "total_pages": totals.get("页", 0),
            "total_items": sum(row["items"] for row in manifest),
            "commitment_total": len(cross_results),
            "commitment_not_found": sum(1 for item in cross_results if item["status"] == "not_found"),
            "commitment_mismatch": sum(1 for item in cross_results if item["status"] == "mismatch"),
            "commitment_matched": sum(1 for item in cross_results if item["status"] in ("matched", "matched_more")),
            "commitment_unknown": sum(1 for item in cross_results if item["status"] == "unknown"),
            "error_count": errors,
            "warn_count": warns,
        },
        "refund_policy": {
            "keys": keys,
            "names": policy_names,
            "text": policy_text,
        },
        "evidence_markdown": evidence,
        "disclaimer": DISCLAIMER,
    }


def render_text(report):
    """把报告渲染为中文文本，输出到标准输出。"""
    lines = []
    lines.append("=" * 66)
    lines.append("{0} v{1} · 交付履约凭证".format(report["tool"], report["tool_version"]))
    lines.append("生成时间：{0}".format(report["generated_at"]))
    lines.append("=" * 66)
    order = report["order"]
    lines.append("订单号：{0}　平台：{1}　商品：{2}　金额：{3}".format(
        _text(order.get("no")) or "(待填)", _text(order.get("platform")) or "(待填)",
        _text(order.get("product")) or "(待填)", _text(order.get("price")) or "(待填)"))
    lines.append("卖家：{0}　联系方式：{1}".format(
        _text(report["seller"].get("name")) or "(待填)",
        _text(report["seller"].get("contact")) or "(待填)"))
    lines.append("")
    summary = report["summary"]
    lines.append("交付合计：{0} 个文件　{1} 页　{2} 条目".format(
        summary["file_count"], summary["total_pages"], summary["total_items"]))
    lines.append("")
    lines.append("交付清单")
    lines.append("-" * 66)
    for row in report["manifest"]:
        flag = "OK " if row["exists"] else "缺失"
        count_parts = []
        if row["pages"]:
            count_parts.append("{0}页".format(row["pages"]))
        if row["items"]:
            count_parts.append("{0}条".format(row["items"]))
        lines.append("[{0}] {1}　{2}　{3}　校验值 {4}".format(
            flag, row["index"], row["name"], "/".join(count_parts) or "-",
            row["sha256_short"] or "-"))
    lines.append("")
    lines.append("承诺核对")
    lines.append("-" * 66)
    if not report["commitment_checks"]:
        lines.append("（未录入商品页承诺，无法核对。请把商品页承诺逐条录入 commitments 字段。）")
    for item in report["commitment_checks"]:
        lines.append("* {0}".format(item["wording"]))
    lines.append("")
    lines.append("交付前自检")
    lines.append("-" * 66)
    for item in report["findings"]:
        lines.append("[{0}] {1}".format(item["level"], item["wording"]))
        lines.append("      建议：{0}".format(item["suggestion"]))
    lines.append("")
    lines.append("统计：通过 {0} 项　警告 {1} 项　错误 {2} 项".format(
        sum(1 for item in report["findings"] if item["level"] == "ok"),
        report["summary"]["warn_count"], report["summary"]["error_count"]))
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def write_outputs(report, out_dir):
    """把清单 CSV 与凭证 Markdown 写入输出目录。

    Args:
        report: build_report 的结果。
        out_dir: 输出目录。

    Returns:
        tuple，(CSV 路径, Markdown 路径, 错误信息)。
    """
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        return None, None, "错误：无法创建输出目录（{0}）：{1}".format(out_dir, exc)
    csv_path = os.path.join(out_dir, "交付清单.csv")
    md_path = os.path.join(out_dir, "交付凭证.md")
    try:
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["序号", "文件名", "格式", "页数或条目数", "校验值", "备注"])
            for row in report["manifest"]:
                count_parts = []
                if row["pages"]:
                    count_parts.append("{0} 页".format(row["pages"]))
                if row["items"]:
                    count_parts.append("{0} 条".format(row["items"]))
                writer.writerow([
                    row["index"], row["name"], row["format"],
                    " / ".join(count_parts) if count_parts else "-",
                    row["sha256_short"] or "-", row["note"] or "",
                ])
    except OSError as exc:
        return None, None, "错误：写入清单 CSV 失败（{0}）：{1}".format(csv_path, exc)
    try:
        with open(md_path, "w", encoding="utf-8") as handle:
            handle.write(report["evidence_markdown"])
    except OSError as exc:
        return csv_path, None, "错误：写入凭证 Markdown 失败（{0}）：{1}".format(md_path, exc)
    return csv_path, md_path, None


def selftest():
    """内置自测：构造临时交付目录，验证校验值、承诺核对与输出文件。

    Returns:
        int，0 表示全部通过，非 0 表示失败项数。
    """
    import shutil
    import tempfile

    failures = []
    workdir = tempfile.mkdtemp(prefix="delivery_evidence_selftest_")
    try:
        bundle = os.path.join(workdir, "打包内容")
        os.makedirs(bundle)
        target = os.path.join(bundle, "保单汇总表.xlsx")
        with open(target, "wb") as handle:
            handle.write(b"demo-table-content")
        guide = os.path.join(bundle, "使用说明.pdf")
        with open(guide, "wb") as handle:
            handle.write(b"demo-guide-content")

        expected = sha256_of(target)[:16]
        if len(sha256_of(target)) != 64:
            failures.append("SHA-256 长度不是 64")

        payload = {
            "order": {"no": "TEST-001", "platform": "示例平台", "product": "家庭保单体检表", "price": 19.9},
            "seller": {"name": "示例工作室", "contact": "示例联系方式"},
            "files": [
                {"path": "打包内容/保单汇总表.xlsx", "pages": 1, "items": 6, "note": "含 6 个表"},
                {"path": "打包内容/使用说明.pdf", "pages": 8, "items": 0, "note": ""},
            ],
            "commitments": [
                "商品页承诺：含 6 张体检表",
                "商品页承诺：附使用说明",
                "商品页承诺：含 40 道练习题",
            ],
            "delivery_channel": "网盘链接",
            "prerequisites": "需使用示例网盘客户端下载",
            "valid_days": 30,
            "version": "v1.0",
            "refund_policy": "not_downloaded_refundable+missing_permanent_resend",
        }
        input_path = os.path.join(workdir, "delivery.json")
        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)

        data, error = load_json(input_path)
        if error:
            failures.append(error)
            data = None
        if data is not None:
            report = build_report(data, workdir, now=datetime(2026, 11, 1, 10, 0, 0))
            manifest = report["manifest"]
            if len(manifest) != 2:
                failures.append("清单条数不为 2")
            if manifest[0]["sha256_short"] != expected:
                failures.append("校验值与独立计算不一致")
            if report["totals"].get("表") != 6:
                failures.append("表件数统计不正确：{0}".format(report["totals"].get("表")))
            if report["totals"].get("页") != 9:
                failures.append("页数统计不正确：{0}".format(report["totals"].get("页")))
            statuses = {item["text"]: item["status"] for item in report["commitment_checks"]}
            if statuses.get("商品页承诺：含 6 张体检表") != "matched":
                failures.append("件数承诺未被识别为已对应")
            if statuses.get("商品页承诺：附使用说明") != "matched":
                failures.append("关键词承诺未被识别为已对应")
            if statuses.get("商品页承诺：含 40 道练习题") != "not_found":
                failures.append("缺件承诺未被报为未找到对应项")
            if report["summary"]["error_count"] < 1:
                failures.append("存在缺件但未产生 error 级结论")
            out_dir = os.path.join(workdir, "out")
            csv_path, md_path, out_error = write_outputs(report, out_dir)
            if out_error:
                failures.append(out_error)
            if not csv_path or not os.path.isfile(csv_path):
                failures.append("清单 CSV 未生成")
            if not md_path or not os.path.isfile(md_path):
                failures.append("凭证 Markdown 未生成")
            if csv_path and os.path.isfile(csv_path):
                with open(csv_path, "r", encoding="utf-8-sig") as handle:
                    rows = list(csv.reader(handle))
                if len(rows) != 3 or rows[0][0] != "序号":
                    failures.append("CSV 内容行数或表头不正确")
            if md_path and os.path.isfile(md_path):
                with open(md_path, "r", encoding="utf-8") as handle:
                    body = handle.read()
                if "交付凭证" not in body or "未在交付物中找到对应项" not in body:
                    failures.append("凭证 Markdown 缺少关键段落")
            try:
                json.dumps(report, ensure_ascii=False)
            except (TypeError, ValueError) as exc:
                failures.append("报告无法序列化为 JSON：{0}".format(exc))

        bad_path = os.path.join(workdir, "not_exist.json")
        _, error = load_json(bad_path)
        if not error:
            failures.append("缺失文件未返回友好错误")
        broken_path = os.path.join(workdir, "broken.json")
        with open(broken_path, "w", encoding="utf-8") as handle:
            handle.write("{ not json ")
        _, error = load_json(broken_path)
        if not error:
            failures.append("非法 JSON 未返回友好错误")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("自测项：16　失败：{0}".format(len(failures)))
    for item in failures:
        print("  失败：{0}".format(item))
    print("自测结果：{0}".format("通过" if not failures else "未通过"))
    return len(failures)


def parse_args(argv=None):
    """解析命令行参数。

    Args:
        argv: 参数列表，默认取 sys.argv。

    Returns:
        argparse.Namespace。
    """
    parser = argparse.ArgumentParser(
        description="虚拟商品交付履约凭证助手：生成交付清单、件数核对、校验值、"
                    "买家确认页与合规退换规则文本，减少因无法举证而起的退款与纠纷。")
    parser.add_argument("--input", help="输入的 delivery.json 路径")
    parser.add_argument("--json", action="store_true", dest="as_json", help="以 JSON 形式输出结构化结果")
    parser.add_argument("--out", default=None, help="输出目录，写入交付清单.csv 与 交付凭证.md")
    parser.add_argument("--selftest", action="store_true", dest="as_selftest", help="运行内置自测并退出")
    return parser.parse_args(argv)


def main(argv=None):
    """命令行主函数。

    Args:
        argv: 参数列表，默认取 sys.argv。

    Returns:
        int，进程退出码，0 表示成功，2 表示输入或输出错误。
    """
    args = parse_args(argv)
    if args.as_selftest:
        return 0 if selftest() == 0 else 1
    if not args.input:
        sys.stderr.write("错误：缺少 --input 参数，请指定 delivery.json 路径\n")
        return 2

    data, error = load_json(args.input)
    if error:
        sys.stderr.write(error + "\n")
        return 2
    if not isinstance(data, dict):
        sys.stderr.write("错误：输入 JSON 的顶层结构必须是对象\n")
        return 2

    base_dir = _text(data.get("base_dir"))
    if base_dir and not os.path.isabs(base_dir):
        base_dir = os.path.join(os.path.dirname(os.path.abspath(args.input)), base_dir)
    if not base_dir:
        base_dir = os.path.dirname(os.path.abspath(args.input))

    report = build_report(data, base_dir)

    if args.out:
        csv_path, md_path, out_error = write_outputs(report, args.out)
        if out_error:
            sys.stderr.write(out_error + "\n")
            return 2
        report["outputs"] = {"manifest_csv": csv_path, "evidence_md": md_path}

    if args.as_json:
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(report))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
