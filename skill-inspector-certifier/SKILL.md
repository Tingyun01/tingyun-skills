---
name: "skill-inspector-certifier"
version: "1.0.0"
display_name: "Skill Inspector & Certifier"
display_name_en: "Skill Inspector & Certifier"
description: "One-click pre-publish validator for any SKILL.md package. Checks structure, frontmatter, body length, dangling references, size limits and sensitive wording. Emits a certificate score with itemized fixes."
description_zh: "SKILL.md 技能包一键校验器：检查目录结构、frontmatter 字段完整性、正文字数、references 引用是否存在、包体积上限、敏感表述扫描，输出逐项问题 + 修复建议 + 合规评分证书。"
author: "Tingyun AI"
category: "Developer Tools"
---

# Skill Inspector & Certifier

## What It Does
You just wrote a SKILL.md. Before zipping and submitting to Agensi / SquidBay / WorkBuddy / Coze — run this inspector. 14 validation rules output a certificate score with itemized fixes.

## Quick Start
```bash
python scripts/skill_inspect.py ./my-skill-folder
python scripts/skill_inspect.py ./my-skill.zip --format json
python scripts/skill_inspect.py ./skill --market agensi
```

## 14 Rules
SKILL.md exists at root, valid frontmatter, required fields present, body length, dangling refs, credentials, size limit, directory depth, junk files, sensitive wording, semver, kebab-case, external URLs in code, quoted values.

## Zero Dependencies
Pure Python stdlib.