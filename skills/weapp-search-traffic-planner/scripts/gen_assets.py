#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_assets.py —— 为 weapp-search-traffic-planner 生成 logo 与截图（纯代码绘制，不用 AI 绘图）

零第三方依赖：只写 SVG，再用自带的极简 PNG 编码器输出 PNG（zlib + struct，纯标准库）。
输出: assets/logo.svg / assets/logo.png / assets/screenshot-*.svg
"""

import os
import struct
import sys
import zlib

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(BASE), "assets")

# 配色: 青绿山水（与工作区设计 Token 一致）
INK = "#1F3A34"
JADE = "#2E8B72"
MIST = "#EAF4F0"
GOLD = "#C9A227"
PAPER = "#FFFFFF"
GREY = "#5B6B66"


def svg_header(w, h):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d">' % (w, h, w, h))


def write_svg(name, body, w=1200, h=630):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(svg_header(w, h))
        f.write(body)
        f.write("</svg>")
    print("wrote", p)
    return p


# ---------------------------------------------------------------- PNG 编码
def png_bytes(width, height, pixels):
    """pixels: bytearray of length width*height*3 (RGB). 返回 PNG 文件字节。"""
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter type 0
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def render_logo_png(size=512):
    """代码绘制 logo: 青绿底 + 放大镜(搜索) + 三层索引条 + 金色关键词点。"""
    W = H = size
    px = bytearray(W * H * 3)

    def rgb(h):
        h = h.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    ink = rgb(INK)
    jade = rgb(JADE)
    mist = rgb(MIST)
    gold = rgb(GOLD)
    paper = rgb(PAPER)

    cx, cy, r = size * 0.42, size * 0.40, size * 0.20
    # 手柄: 从镜圈右下角沿 45 度方向延伸的粗线段
    hx, hy = size * 0.545, size * 0.535
    hlen = size * 0.19
    hw = size * 0.042

    for y in range(H):
        for x in range(W):
            i = (y * W + x) * 3
            # 背景: 竖向渐变 ink -> jade
            t = y / (H - 1)
            c = tuple(int(ink[k] * (1 - t) + jade[k] * t) for k in range(3))
            # 放大镜镜身: 圆形区域
            dx, dy = x - cx, y - cy
            d = (dx * dx + dy * dy) ** 0.5
            if d < r:
                c = mist
                # 镜圈描边
                if r - d < size * 0.028:
                    c = ink
                else:
                    # 镜内三条索引横条（表示被收录的页面）
                    for k, frac in enumerate((0.34, 0.50, 0.66)):
                        by = cy - r * 0.30 + k * r * 0.30
                        bx0 = cx - r * 0.56
                        bx1 = bx0 + r * (1.12 if k == 2 else (0.86 if k == 1 else 0.66))
                        if abs(y - by) < size * 0.035 and bx0 <= x <= bx1:
                            c = jade if k < 2 else gold
            # 手柄: 沿 (1,1) 方向的线段
            if hx <= x <= hx + hlen and hy <= y <= hy + hlen:
                if abs((x - hx) - (y - hy)) <= hw:
                    c = ink
            px[i] = c[0]
            px[i + 1] = c[1]
            px[i + 2] = c[2]
    return png_bytes(W, H, px)


# ---------------------------------------------------------------- SVG 构件
def logo_svg():
    return """
<rect width="1200" height="1200" rx="240" fill="#1F3A34"/>
<circle cx="504" cy="480" r="240" fill="#EAF4F0"/>
<circle cx="504" cy="480" r="240" fill="none" stroke="#1F3A34" stroke-width="34"/>
<rect x="380" y="374" width="278" height="40" rx="20" fill="#2E8B72"/>
<rect x="380" y="460" width="192" height="40" rx="20" fill="#2E8B72"/>
<rect x="380" y="546" width="116" height="40" rx="20" fill="#C9A227"/>
<line x1="654" y1="642" x2="836" y2="824" stroke="#1F3A34" stroke-width="52" stroke-linecap="round"/>
"""


def shot_svg(title, subtitle, rows, accent="#2E8B72"):
    """通用截图版式: 顶部标题条 + 表格行。"""
    h = 200 + len(rows) * 74
    b = ['<rect width="1200" height="%d" fill="#FFFFFF"/>' % h]
    b.append('<rect width="1200" height="128" fill="#1F3A34"/>')
    b.append('<text x="64" y="56" font-family="Microsoft YaHei,sans-serif" font-size="34" '
             'font-weight="bold" fill="#FFFFFF">%s</text>' % title)
    b.append('<text x="64" y="96" font-family="Microsoft YaHei,sans-serif" font-size="20" '
             'fill="#B9CFC7">%s</text>' % subtitle)
    b.append('<rect x="64" y="164" width="8" height="%d" rx="4" fill="%s"/>' % ((len(rows) * 74) - 20, accent))
    y = 196
    for i, (a, btxt, c) in enumerate(rows):
        bg = "#F5FAF8" if i % 2 == 0 else "#FFFFFF"
        b.append('<rect x="96" y="%d" width="1040" height="62" rx="10" fill="%s"/>' % (y - 34, bg))
        b.append('<text x="124" y="%d" font-family="Microsoft YaHei,sans-serif" font-size="21" '
                 'fill="#1F3A34">%s</text>' % (y + 4, a))
        b.append('<text x="470" y="%d" font-family="Microsoft YaHei,sans-serif" font-size="20" '
                 'fill="#5B6B66">%s</text>' % (y + 4, btxt))
        col = "#C0392B" if c == "必改" else ("#C9A227" if c == "需人工确认" else "#2E8B72")
        b.append('<rect x="960" y="%d" width="150" height="38" rx="19" fill="%s"/>' % (y - 24, col))
        b.append('<text x="985" y="%d" font-family="Microsoft YaHei,sans-serif" font-size="19" '
                 'fill="#FFFFFF">%s</text>' % (y + 4, c))
        y += 74
    return "".join(b)


def main():
    os.makedirs(OUT, exist_ok=True)
    write_svg("logo.svg", logo_svg(), 1200, 1200)
    data = render_logo_png(512)
    p = os.path.join(OUT, "logo.png")
    with open(p, "wb") as f:
        f.write(data)
    print("wrote", p, len(data), "bytes")

    write_svg("screenshot-1-naming.svg", shot_svg(
        "小程序搜一搜落地卡 · 一、命名合规预检表",
        "逐项三态判定；必改与需人工确认清零之前不要提交审核",
        [
            ("仅由通用词/品类词构成", "官方要求改为品牌+功能描述", "必改"),
            ("含商业化用语（免费/清仓）", "删除或改为品牌与产品描述", "必改"),
            ("含广告法极限用语（最/第一）", "全部删除", "必改"),
            ("疑似含第三方品牌标识", "未经授权属侵权，需人工确认", "需人工确认"),
            ("名称全局唯一性查重结果", "微信搜一搜输入候选名", "需人工确认"),
            ("服务类目是否不可逆", "游戏类目提交后不可改", "需人工确认"),
        ]))

    write_svg("screenshot-2-keyword.svg", shot_svg(
        "小程序搜一搜落地卡 · 二、关键词-页面对应表",
        "核心词进名称 · 场景词进简介 · 长尾词进页面标题",
        [
            ("道系签文", "核心候选词 · 落地页 pages/fortune/index", "进名称"),
            ("性格测试", "核心候选词 · 落地页 pages/card/index", "进简介"),
            ("趣味测试", "核心候选词 · 落地页 pages/card/index", "进简介"),
            ("道系运势测试", "长尾场景词 · 落地页 pages/fortune/index", "进标题"),
            ("小说下载", "与业务无关的蹭流量词", "必改"),
        ], "#C9A227"))

    write_svg("screenshot-3-sitemap.svg", shot_svg(
        "小程序搜一搜落地卡 · 三、收录配置清单",
        "sitemap 规则 · 路径推送 · 爬虫一致性三条核查",
        [
            ("sitemap.json 已填", "默认 allow:* + disallow 低价值页", "通过"),
            ("需推送页面已列出", "search.submitPages 主动推送", "通过"),
            ("web-view 页面", "内容不会被收录，不布局关键词", "必改"),
            ("爬虫所见与用户所见", "不一致则该页不进索引", "需人工确认"),
            ("页面标题独立", "每页独立标题，不用统一「首页」", "必改"),
            ("观察排期 ≥3 天", "索引非即时，当天不下结论", "需人工确认"),
        ], "#1F3A34"))
    print("done")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    main()
