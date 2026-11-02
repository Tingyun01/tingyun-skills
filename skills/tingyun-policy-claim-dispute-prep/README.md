# 理赔争议材料准备与申诉要点顾问

> 为理赔被拒或部分赔付的客户梳理争议点、补充材料清单与申诉陈述结构，输出可直接使用的材料包。

## 这个 Skill 解决什么

理赔被拒之后最耗时的不是申诉本身，而是不知道该补什么材料、按什么顺序讲。这套顾问把争议拆成四层：合同约定的赔付条件是什么、保险公司这次援引的是哪一条、事实层面还缺什么证据、申诉陈述应该怎么写才让人看得懂。每一步都给出可执行的材料清单和话术框架，不对结果做承诺，也不代替律师出具意见。

## 什么时候用

- My claim was denied for a pre-existing condition. How do I work out what to contest?
- What documents do I need to submit a formal appeal on a partial payout?
- How should I structure a written complaint so the reviewer actually reads it?

## 你会拿到什么

- Four-layer dispute analysis worksheet
- Supplementary evidence checklist organised by claim type
- Contract clause and insurer reasoning comparison table
- Written submission statement framework with example paragraph structures
- Escalation path and escalation letter skeleton

## 用法

```bash
# 在 Claude Code / Codex CLI / Cursor 中
npx skills add Tingyun01/tingyun-skills
```

或直接把本目录的 `SKILL.md` 指给你的 agent。

## 常见问答

**Q: Will this help me win the claim?**

A: No promise. What it does is make sure the dispute is put on the right footing: the right clause, the right evidence, in a form the reviewer can act on. Whether that changes the outcome depends on the facts and the contract.

**Q: How long do I have to appeal?**

A: Deadlines are set by the contract and by the platform rules, and they differ by product and by how the claim was handled. The worksheet puts the deadline you need to confirm at the top, with a reminder to check it early rather than late.

**Q: Can I do this without a lawyer?**

A: For straightforward disputes over missing documents, yes. For anything involving a contested medical fact, a large sum, or a possible coverage exclusion, the cost of getting it wrong is high enough to be worth advice. The advisor flags which category your case falls into.

## 说明

- 输出为**决策支持与清单辅助**，不构成法律、税务、医疗专业意见，重要结论请人工复核。
- 所有脚本仅用 Python 标准库，无网络调用。
- 英文版与打包版：https://www.agensi.io/r/CREATOR8796142

**完整技能仓库**：https://github.com/Tingyun01/tingyun-skills
