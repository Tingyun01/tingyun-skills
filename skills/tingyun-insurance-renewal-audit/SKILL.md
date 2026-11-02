---
slug: tingyun-insurance-renewal-audit
name: tingyun-insurance-renewal-audit
version: 1.0.0
displayName: 保单续保与健康告知自查顾问
description: "很多人在续保时才发现健康告知这一关过不去，或者宽限期内忘了缴费导致保单失效。这套顾问把续保前必须核对的项目拆成一张逐单清单：健康告知问卷与既往就诊记录怎么对、等待期什么时候开始算、宽限期有多长、缴费方式改了会不会漏保、续保年龄上限和停售节点。每份保单一张卡，标出需要提前动作的项目和截止时间，方便客户自己看懂，也方便代理人跟进。 为保险客户与代理人梳理续保前的健康告知核对、等待期与既往症影响、宽限期与失效风险，输出逐单处理清单。 技术触发词「保险续保」。口语触发词「My renewal is next month and I had a hospital visit last year. What should I check before renewing?」。输出可直接使用的清单、对照表与行动项。仅作规划与清单辅助，不构成法律/税务/医疗专业意见，需人工复核。 Many people only discover at renewal time that a health disclosure cannot be passed, or that a missed payment during the grace period silently lapsed the policy. This advisor breaks the pre-renewal checklist into one card per policy: how to match disclosure questionnaires against medical records, when a waiting period starts, how long the grace period runs, whether a payment-method change risks a missed payment, and where age limits or product closures cut off. Each card marks the items that need action before a deadline, so the client can see it plainly and the agent can follow up. Reviews renewal-time health disclosure, waiting periods, pre-existing condition effects and lapse risk, producing a per-policy action list. Covers: 保险续保, 健康告知, 保单管理. Use when the user asks to tingyun-insurance-renewal-audit. Tags: 保险续保, 健康告知, 保单管理."
summary: 为保险客户与代理人梳理续保前的健康告知核对、等待期与既往症影响、宽限期与失效风险，输出逐单处理清单。
tags:
  - 保险续保
  - 健康告知
  - 保单管理
---

# 保单续保与健康告知自查顾问

> **中文简介**：很多人在续保时才发现健康告知这一关过不去，或者宽限期内忘了缴费导致保单失效。这套顾问把续保前必须核对的项目拆成一张逐单清单：健康告知问卷与既往就诊记录怎么对、等待期什么时候开始算、宽限期有多长、缴费方式改了会不会漏保、续保年龄上限和停售节点。每份保单一张卡，标出需要提前动作的项目和截止时间，方便客户自己看懂，也方便代理人跟进。
>
> **何时使用**：当你需要**为保险客户与代理人梳理续保前的健康告知核对、等待期与既往症影响、宽限期与失效风险，输出逐单处理清单。**时。本 Skill 给出判断标准 + 检查清单 + 固定输出格式，产出是可以直接用的对照表与行动清单，不是资料搬运。
>
> **不做什么**：不提供法律/税务/医疗专业意见；遇到需要执业资格才能定论的问题，本 Skill 会明确指出并建议转人工复核。

## 一、什么时候用这个 Skill

- "My renewal is next month and I had a hospital visit last year. What should I check before renewing?"
- "How long is the grace period on this policy and what happens if I miss it?"
- "I changed my bank card. Will the automatic deduction still work at renewal?"

## 二、你会拿到什么

- Per-policy renewal card with a date-ordered action list
- Health disclosure matching checklist against medical records
- Waiting period, grace period and lapse consequence comparison table
- Age limit and product closure notice board template
- Three renewal scenarios showing where renewals most often go wrong

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
  - q: "Can I change my health disclosure answers at renewal?"
    a: "Sometimes. Whether an answer can be changed depends on the contract terms, and changing it can affect underwriting. The honest answer is that you should check the specific clause with the insurer before renewing, not rely on a general rule."
  - q: "What happens if I miss one premium payment?"
    a: "Most policies have a grace period after the due date, but the length and the conditions vary, and the coverage is not necessarily continuous during that window. The renewal card lists the exact dates so there is no guessing."
  - q: "Do I need a new health questionnaire at every renewal?"
    a: "Not at every renewal, but any policy where the underwriting class changes, or where the contract asks for an updated declaration, will require a fresh one. The checklist flags which of your policies fall into that group."
```

## 五、边界与免责

- 本 Skill 输出的是**决策支持与清单辅助**，不构成法律、税务、医疗或财务意见。
- 涉及具体合同条款、监管口径、个案认定的地方，必须提示用户向持牌专业人士或官方渠道确认。
- 不对结果做任何形式的承诺（"一定能通过""保证能赔"这类表述一律禁止）。
- 涉及用户个人敏感信息时，提醒脱敏，不要在对话中留存完整原始文件。

## 六、参考资料

- `references/续保前核对清单.md` — 逐单续保动作清单模板 + 常见续保失败场景

---

**English edition and bundled packs**: https://www.agensi.io/r/CREATOR8796142
**Full catalogue**: https://github.com/Tingyun01/tingyun-skills
