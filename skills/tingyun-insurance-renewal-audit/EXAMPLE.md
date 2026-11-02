# 示例：保单续保与健康告知自查顾问

## 场景

用户提出：「My renewal is next month and I had a hospital visit last year. What should I check before renewing?」

## 本 Skill 的处理过程

1. **分类** —— 判断属于哪一类场景，决定用哪张清单
2. **逐项核对** —— 对照检查表逐项过，不跳步
3. **输出结论** —— 结论先行，标注风险等级
4. **列待办** —— 每条待办带责任方与时间点
5. **标不确定** —— 需要按合同或当地口径确认的，明确标出

## 产出结构

```
【结论】
（两三句话，直接回答能不能做 / 该怎么做的方向）

【风险等级】
高：必须处理，附时限
中：建议本周期内处理
低：记录备查

【待办清单】
| # | 事项 | 责任方 | 截止 | 依据 |
|---|---|---|---|---|
| 1 | ... | ... | ... | ... |

【需人工确认】
- 本项需按你的合同 / 当地口径确认
```

## 你会拿到的材料

- Per-policy renewal card with a date-ordered action list
- Health disclosure matching checklist against medical records
- Waiting period, grace period and lapse consequence comparison table
- Age limit and product closure notice board template
- Three renewal scenarios showing where renewals most often go wrong

## 边界

本 Skill 不出具法律、税务、医疗专业意见，不对结果做承诺。
