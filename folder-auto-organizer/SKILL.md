---
name: "folder-auto-organizer"
version: "1.0.0"
display_name: "Folder Auto-Organizer"
display_name_en: "Folder Auto-Organizer"
description: "One-click folder cleanup: sorts files by type, removes duplicates, trashes junk, and archives old items. Works on Downloads, Desktop, or any messy folder."
description_zh: "一键整理文件夹：按类型自动分类、查重、清垃圾、归档旧文件。专治桌面和下载文件夹乱成狗，一条命令 5 秒搞定。跨平台零依赖。"
author: "Tingyun AI"
category: "Productivity Tools"
---

# Folder Auto-Organizer

## What It Does
Sorts files by type into 12 categories, removes duplicates by content hash, trashes junk, archives old items untouched > N days. One command, zero dependencies.

## Quick Start
```bash
python scripts/folder_organizer.py ~/Downloads --dry-run
python scripts/folder_organizer.py ~/Downloads --dedupe --archive-days 90
python scripts/folder_organizer.py C:/Users/You/Desktop --dedupe --archive-days 90 --junk
```

## Safety
Dry-run safe by default. Keeps your subfolder structure. Logs everything. Permission errors don't crash.

## Zero Dependencies
Pure Python stdlib.