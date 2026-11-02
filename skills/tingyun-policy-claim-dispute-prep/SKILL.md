---
slug: tingyun-policy-claim-dispute-prep
name: tingyun-policy-claim-dispute-prep
version: 1.0.0
displayName: 理赔争议材料准备与申诉要点顾问
description: "理赔被拒之后最耗时的不是申诉本身，而是不知道该补什么材料、按什么顺序讲。这套顾问把争议拆成四层：合同约定的赔付条件是什么、保险公司这次援引的是哪一条、事实层面还缺什么证据、申诉陈述应该怎么写才让人看得懂。每一步都给出可执行的材料清单和话术框架，不对结果做承诺，也不代替律师出具意见。 为理赔被拒或部分赔付的客户梳理争议点、补充材料清单与申诉陈述结构，输出可直接使用的材料包。 技术触发词「理赔争议」。口语触发词「My claim was denied for a pre-existing condition. How do I work out what to contest?」。输出可直接使用的清单、对照表与行动项。仅作规划与清单辅助，不构成法律/税务/医疗专业意见，需人工复核。 The slow part of disputing a claim is not the complaint, it is working out what evidence is missing and in what order to present it. This advisor separates the dispute into four layers: what the contract actually promises, which clause the insurer relied on, what facts still lack evidence, and how to write a submission that can actually be read. Each step produces an actionable evidence list and a statement framework. It makes no promise about the outcome and is not a substitute for a lawyer. Turns a denied or partial claim into an organised dispute: identifies the contestable points, lists the supplementary evidence, and structures the written submission. Covers: 理赔争议, 保险申诉, 证据材料. Use when the user asks to tingyun-policy-claim-dispute-prep. Tags: 理赔争议, 保险申诉, 证据材料."
summary: 为理赔被拒或部分赔付的客户梳理争议点、补充材料清单与申诉陈述结构，输出可直接使用的材料包。
tags:
  - 理赔争议
  - 保险申诉
  - 证据材料
---

# 理赔争议材料准备与申诉要点顾问

> **中文简介**：理赔被拒之后最耗时的不是申诉本身，而是不知道该补什么材料、按什么顺序讲。这套顾问把争议拆成四层：合同约定的赔付条件是什么、保险公司这次援引的是哪一条、事实层面还缺什么证据、申诉陈述应该怎么写才让人看得懂。每一步都给出可执行的材料清单和话术框架，不对结果做承诺，也不代替律师出具意见。
>
> **何时使用**：当你需要**为理赔被拒或部分赔付的客户梳理争议点、补充材料清单与申诉陈述结构，输出可直接使用的材料包。**时。本 Skill 给出判断标准 + 检查清单 + 固定输出格式，产出是可以直接用的对照表与行动清单，不是资料搬运。
>
> **不做什么**：不提供法律/税务/医疗专业意见；遇到需要执业资格才能定论的问题，本 Skill 会明确指出并建议转人工复核。

## 一、什么时候用这个 Skill

- "My claim was denied for a pre-existing condition. How do I work out what to contest?"
- "What documents do I need to submit a formal appeal on a partial payout?"
- "How should I structure a written complaint so the reviewer actually reads it?"

## 二、你会拿到什么

- Four-layer dispute analysis worksheet
- Supplementary evidence checklist organised by claim type
- Contract clause and insurer reasoning comparison table
- Written submission statement framework with example paragraph structures
- Escalation path and escalation letter skeleton

## 三、工作方法

### 第一步：把问题分类

先判断这件事属于哪一类，不同类的处理路径完全不同。不要把所有情况都当成"查一下清单"。

### 第二步：套用对应清单

每类场景都有对应的检查项。逐项过，不要跳步——跳过的项通常正是出问题的那项。

### 第三步：输出结构化结果

固定输出三段：**结论先行 → 风险等级 → 待办清单**。待办清单必须带责任方和时间点，否则客户看完也不知道先动哪一件。

### 第四步：标注不确定项

凡是需要具体合同条款、行业口径或个案事实才能定的，明确写"此项需按你的合同/当地口径确认"，不要替客户下结论。

## 四、常见问答

```yaml
  - q: "Will this help me win the claim?"
    a: "No promise. What it does is make sure the dispute is put on the right footing: the right clause, the right evidence, in a form the reviewer can act on. Whether that changes the outcome depends on the facts and the contract."
  - q: "How long do I have to appeal?"
    a: "Deadlines are set by the contract and by the platform rules, and they differ by product and by how the claim was handled. The worksheet puts the deadline you need to confirm at the top, with a reminder to check it early rather than late."
  - q: "Can I do this without a lawyer?"
    a: "For straightforward disputes over missing documents, yes. For anything involving a contested medical fact, a large sum, or a possible coverage exclusion, the cost of getting it wrong is high enough to be worth advice. The advisor flags which category your case falls into."
```

## 五、边界与免责

- 本 Skill 输出的是**决策支持与清单辅助**，不构成法律、税务、医疗或财务意见。
- 涉及具体合同条款、监管口径、个案认定的地方，必须提示用户向持牌专业人士或官方渠道确认。
- 不对结果做任何形式的承诺（"一定能通过""保证能赔"这类表述一律禁止）。
- 涉及用户个人敏感信息时，提醒脱敏，不要在对话中留存完整原始文件。

## 六、参考资料

- `references/争议材料组织法.md` — 四层争议分析 + 补充证据清单模板

---

**English edition and bundled packs**: https://www.agensi.io/r/CREATOR8796142
**Full catalogue**: https://github.com/Tingyun01/tingyun-skills
