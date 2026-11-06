---
name: "contract-risk-scanner"
version: "1.0.0"
display_name: "合同风险扫描器"
display_name_en: "Contract Risk Scanner"
description: "扫描合同、协议、借条、租房合同、劳动合同、装修合同，逐条列出对你不利的条款，附原文摘录、大白话解释、可直接发给对方的协商话术和法律依据，并检测合同缺失的关键条款。支持 docx/txt/pdf 直读，零依赖。"
description_zh: "把合同丢进来，一条命令出体检报告：94 条实战风险规则，命中条款自动附原文摘录 + 大白话解释 + 可直接复制的谈判话术 + 法律依据；同时检测这类合同本该有却没写的关键条款，并给出可直接粘贴的补充条款文本。支持 docx / txt / pdf 直读。"
description_en: "Drop in a contract, get a risk report in one command — 94 field-tested rules with original clause excerpt, plain-language explanation, ready-to-send negotiation wording and legal basis, plus detection of missing key clauses with paste-ready replacement text. Reads docx/txt/pdf directly, zero dependencies."
author: "停云文化"
category: "办公效率"
---

# 合同风险扫描器

用户传一份合同（docx / pdf / txt），你跑一次脚本，把报告原样交给他。**不要自己编法律意见，所有内容都来自脚本输出的 94 条规则库。**

## 什么时候用

- 用户要签租房合同、劳动合同、装修合同、借条、服务合同、加盟合同、二手车合同
- 用户问「这份合同有没有坑」「帮我看看这个协议」
- 用户已经签了，问「这条对我有没有不利」
- 用户拿不准某一条要不要谈

## 怎么跑

```bash
# 最常用：直接扫一份合同
python scripts/scan_contract.py 合同.docx

# 告诉脚本用户是哪一方，报告口径更准
python scripts/scan_contract.py 合同.pdf --side 承租人

# 存成文件
python scripts/scan_contract.py 合同.txt --output 报告.md

# 机器可读
python scripts/scan_contract.py 合同.docx --format json

# 不按合同类型过滤，输出全部 94 条命中（默认按识别出的类型过滤，避免误报）
python scripts/scan_contract.py 合同.docx --all
```

支持格式：`.docx` `.pdf` `.txt` `.md` `.csv` `.json`，也可以传目录（批量扫）、传 `-` 从标准输入读。

## 报告结构（脚本已生成，直接交付）

1. **结论** — 签 / 改完再签 / 不建议签，一句话理由
2. **最该谈的 3 条** — 优先级最高的问题
3. **逐条风险** — 高危在前，每条含：
   - 合同原文摘录
   - 命中关键词
   - 这意味着什么（大白话，说"你"不说"乙方"）
   - 你可以这样说（可直接复制发给对方的话）
   - 法律依据
4. **缺失条款** — 这类合同本该有却没写的条款，附**可直接粘进合同的补充条款文本**
5. **必须人工复核** — 空白处、大小写、日期、签章、证件号
6. **签约前必查清单** — 可勾选
7. **边界说明**

## 交付方式

- 用户要报告 → 把脚本输出原样贴给他，**不要改写、不要删减话术**
- 用户只要重点 → 只贴「结论 + 最该谈的 3 条 + 缺失条款」
- 用户要文件 → 用 `--output` 存成 `.md` 再发给他

## 铁律

- **关键词命中 ≠ 风险成立。** 报告里每条都带原文摘录，判断前回原文看上下文；同一条款对甲乙方利弊相反，先确认用户在哪一方（用 `--side` 或问一句）。
- **不编法条。** 法条只取脚本输出里的「法律依据」。规则库没覆盖的，直接说「这一点规则库未覆盖，建议咨询律师」。
- **不做法律意见，不替代律师。** 房产、股权、大额资金、涉外、知识产权转让，明确提示找执业律师复核。
- **不催签。** 高危条款多就说「建议改完再签」，不要为了显得有用说「总体还行」。
- **扫描版 PDF 读不出字**：脚本会提示文字太少，让用户先转成文字版 PDF 或 docx 再扫。

## 素材

- `scripts/scan_contract.py` — 主脚本（文本提取 + 规则匹配 + 报告生成）
- `scripts/rules_data.py` — 94 条规则数据（等级 / 分类 / 关键词 / 大白话 / 话术 / 法条）
- `references/rule-library.md` — 完整规则库原文，需要展开解释时查这里