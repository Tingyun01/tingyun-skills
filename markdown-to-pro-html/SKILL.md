---
name: "markdown-to-pro-html"
version: "1.0.0"
display_name: "Markdown → Pro HTML"
display_name_en: "Markdown → Pro HTML"
description: "Convert messy Markdown files to polished standalone HTML with table of contents, dark mode, code highlighting, and responsive layout. One command, zero dependencies."
description_zh: "把一堆 Markdown 变成好看的单页 HTML：自动生成目录、代码高亮、深浅色模式切换、响应式布局，零依赖、一条命令搞定。"
author: "Tingyun AI"
category: "Content Tools"
---

# Markdown → Pro HTML

## What It Does
Turn any .md file into a polished, self-contained HTML page — TOC, syntax highlighting, dark mode toggle, responsive layout. Ship to Netlify, Vercel, GitHub Pages.

## Quick Start
```bash
python scripts/md2html.py my-notes.md
python scripts/md2html.py ./docs/ --output ./public/ --dark
python scripts/md2html.py . --output ./public/
```

## Features
Auto TOC, 40+ language highlight, dark mode toggle, responsive, print-friendly, all assets inline.

## Zero Dependencies
Pure Python stdlib.