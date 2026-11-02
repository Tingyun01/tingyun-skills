# 保单续保与健康告知自查顾问

> 为保险客户与代理人梳理续保前的健康告知核对、等待期与既往症影响、宽限期与失效风险，输出逐单处理清单。

## 这个 Skill 解决什么

很多人在续保时才发现健康告知这一关过不去，或者宽限期内忘了缴费导致保单失效。这套顾问把续保前必须核对的项目拆成一张逐单清单：健康告知问卷与既往就诊记录怎么对、等待期什么时候开始算、宽限期有多长、缴费方式改了会不会漏保、续保年龄上限和停售节点。每份保单一张卡，标出需要提前动作的项目和截止时间，方便客户自己看懂，也方便代理人跟进。

## 什么时候用

- My renewal is next month and I had a hospital visit last year. What should I check before renewing?
- How long is the grace period on this policy and what happens if I miss it?
- I changed my bank card. Will the automatic deduction still work at renewal?

## 你会拿到什么

- Per-policy renewal card with a date-ordered action list
- Health disclosure matching checklist against medical records
- Waiting period, grace period and lapse consequence comparison table
- Age limit and product closure notice board template
- Three renewal scenarios showing where renewals most often go wrong

## 用法

```bash
# 在 Claude Code / Codex CLI / Cursor 中
npx skills add Tingyun01/tingyun-skills
```

或直接把本目录的 `SKILL.md` 指给你的 agent。

## 常见问答

**Q: Can I change my health disclosure answers at renewal?**

A: Sometimes. Whether an answer can be changed depends on the contract terms, and changing it can affect underwriting. The honest answer is that you should check the specific clause with the insurer before renewing, not rely on a general rule.

**Q: What happens if I miss one premium payment?**

A: Most policies have a grace period after the due date, but the length and the conditions vary, and the coverage is not necessarily continuous during that window. The renewal card lists the exact dates so there is no guessing.

**Q: Do I need a new health questionnaire at every renewal?**

A: Not at every renewal, but any policy where the underwriting class changes, or where the contract asks for an updated declaration, will require a fresh one. The checklist flags which of your policies fall into that group.

## 说明

- 输出为**决策支持与清单辅助**，不构成法律、税务、医疗专业意见，重要结论请人工复核。
- 所有脚本仅用 Python 标准库，无网络调用。
- 英文版与打包版：https://www.agensi.io/r/CREATOR8796142

**完整技能仓库**：https://github.com/Tingyun01/tingyun-skills
