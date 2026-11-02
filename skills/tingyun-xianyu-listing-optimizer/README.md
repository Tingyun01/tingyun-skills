# 闲鱼虚拟资料商品优化顾问

> 为闲鱼与小红书虚拟资料卖家梳理标题公式、描述结构、关键词布局与合规红线，输出可直接上架的商品页。

## 这个 Skill 解决什么

虚拟资料在闲鱼上架，最常见的两个问题是搜不到和被下架。这套顾问给的是可执行的结构而不是灵感：标题怎么组词才能被搜到、描述按哪几段写才让人看完、关键词放哪几个位置、哪些词一写就容易被判违规、定价怎么设才不亏。每一步都给了可直接套用的模板和对照表，并附一份自检表，上架前自己过一遍。

## 什么时候用

- My virtual materials listing never gets views. How should I write the title?
- Which words in a listing description get it flagged or taken down?
- How do I set a price for a template bundle on Xianyu without losing margin?

## 你会拿到什么

- Title formula reference with keyword slot map
- Description section template with a five-paragraph layout
- Prohibited and risky wording comparison table
- Pricing and margin worksheet for bundle listings
- Pre-listing self-check list covering both searchability and compliance

## 用法

```bash
# 在 Claude Code / Codex CLI / Cursor 中
npx skills add Tingyun01/tingyun-skills
```

或直接把本目录的 `SKILL.md` 指给你的 agent。

## 常见问答

**Q: How many keywords should a title carry?**

A: Enough to be found, few enough to stay readable. The reference shows which slot carries the intent word, which carries the category word, and which carries the differentiator, so you can see the structure rather than guess a count.

**Q: Why was my listing taken down?**

A: Virtual-goods listings get pulled for several reasons, most often unclear delivery terms, claims that cannot be substantiated, or wording that implies a guaranteed outcome. The self-check covers the most common ones before you publish.

**Q: Should I put a link in the description?**

A: Links to external payment or off-platform destinations are the single most common trigger for removal, and they also make the listing look like a redirect. The template keeps contact inside the platform messaging path.

## 说明

- 输出为**决策支持与清单辅助**，不构成法律、税务、医疗专业意见，重要结论请人工复核。
- 所有脚本仅用 Python 标准库，无网络调用。
- 英文版与打包版：https://www.agensi.io/r/CREATOR8796142

**完整技能仓库**：https://github.com/Tingyun01/tingyun-skills
