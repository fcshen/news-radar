#!/usr/bin/env python3
"""生成 App 图标（纯标准库，不依赖 Pillow）。

画一个雷达：同心圆环 + 扫描扇区 + 中心红点。
用法：python tools/make_icons.py
"""
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

BG = (15, 17, 21)
RING = (42, 49, 64)
ACCENT = (229, 72, 77)


def blend(base, top, alpha):
    return tuple(int(b + (t - b) * alpha) for b, t in zip(base, top))


def pixel(x, y, size, content=1.0):
    """content：图案占画布的比例。安卓 maskable 图标必须把内容缩到中心，
    否则启动器裁成圆形时外圈会被切掉（这是安卓上图标变形的根因）。"""
    c = size / 2.0
    # 除以 content 等于把图案整体缩小，四周自然留出背景色安全区
    dx, dy = (x + 0.5 - c) / content, (y + 0.5 - c) / content
    r = math.hypot(dx, dy)
    scale = size / 512.0

    col = BG

    # 同心圆环
    for radius in (150, 230, 310):
        if abs(r - radius * scale) < 2.2 * scale:
            col = RING

    # 扫描扇区（-70° ~ 0°，越靠近 0° 越亮）
    if 40 * scale < r < 340 * scale:
        ang = math.degrees(math.atan2(dy, dx))      # -180..180
        if -70 <= ang <= 0:
            strength = 1.0 + ang / 70.0             # 0° → 1.0，-70° → 0
            col = blend(col, ACCENT, 0.10 + 0.45 * strength * strength)

    # 扫描前沿的亮线
    if 40 * scale < r < 345 * scale:
        ang = math.degrees(math.atan2(dy, dx))
        if -1.5 <= ang <= 0:
            col = blend(col, ACCENT, 0.95)

    # 中心点
    if r < 30 * scale:
        col = ACCENT

    return col


def write_png(path, size, content=1.0):
    rows = []
    for y in range(size):
        row = bytearray([0])                          # filter type 0
        for x in range(size):
            row += bytes(pixel(x, y, size, content)) + b"\xff"
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


# 常规图标留 8% 边：多数安卓启动器会加圆角/圆形遮罩，铺满会被切掉
# maskable 缩到 60%：安卓安全区是中心直径 66% 的圆，超出 80% 的部分会被裁掉
ANY = 0.92
MASKABLE = 0.60


def main():
    OUT.mkdir(exist_ok=True)
    jobs = [
        (512, "icon-512.png", ANY),
        (192, "icon-192.png", ANY),
        (144, "icon-144.png", ANY),
        (180, "apple-touch-icon.png", ANY),
        (512, "icon-maskable-512.png", MASKABLE),
    ]
    for size, name, content in jobs:
        write_png(OUT / name, size, content)
        tag = "maskable" if content < 1.0 and "maskable" in name else "any"
        print(f"  ✓ assets/{name}  {size}x{size}  content={content} ({tag})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
