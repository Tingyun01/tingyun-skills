# weapp-search-traffic-planner

> 给微信小程序做搜一搜自然流量规划：起名前的命名合规预检、名称/简介/页面标题的关键词布局表、sitemap 收录与页面路径推送配置清单，输出可直接执行的三段式落地卡
>
> 专攻微信小程序搜一搜自然流量：命名合规预检 + 关键词-页面对应表 + sitemap 收录与页面路径推送配置。技术触发词「小程序搜索优化、小程序 ASO、搜一搜排名、关键词布局、sitemap 收录」。

## 这个 Skill 做什么

把「小程序搜索流量」这个场景最容易出错、也最没人负责的环节，拆成**可执行的判断步骤 + 检查清单 + 固定输出格式**。
你给案情/材料，它输出该问什么、该查什么、该准备什么、风险点在哪。

## 什么时候会触发

当你要处理以下事情时，这个 Skill 会被自动激活：

- 我的小程序搜不到
- 搜出来排在后面
- 名字被驳回让我改
- 该起什么名字才能被搜到
- 页面标题怎么写才有人点

## 里面有什么

```
weapp-search-traffic-planner/
├── SKILL.md
├── assets/  (5 个文件)
│   ├── logo.png
│   ├── logo.svg
│   ├── screenshot-1-naming.svg
│   ├── screenshot-2-keyword.svg
│   └── screenshot-3-sitemap.svg
├── meta.json
├── references/  (2 个文件)
│   ├── keyword-mapping-workbook.md
│   └── wx-search-rules.md
└── scripts/  (2 个文件)
    ├── gen_assets.py
    └── weapp_search_lint.py
```

## 怎么用

1. 安装到你的 agent（Claude Skills 目录 / 扣子技能商店）
2. 直接用日常说法提需求，例如：
   我的小程序搜不到
3. 它会追问关键信息（缺的信息会标〔待补〕，不会替你编）
4. 输出可直接用的清单 / 对照表 / 台账

## 输出

- 判断步骤与检查清单
- 对照表 / 台账
- 待办与需要人工核实的问题

## 边界

- 不构成法律 / 税务 / 医疗专业意见，最终判断需人工复核
- 遇到需要执业资格才能定论的问题，它会明确说"建议转专业机构"
- 单次购买、单人授权使用；**不可转售或再分发**

## 许可

原创方法论整理，仅供个人工作流使用。不得转售、再分发或作为商品二次售卖。

> English version with demo session: https://www.agensi.io/r/CREATOR8796142?to=/skills/weapp-search-traffic-planner
