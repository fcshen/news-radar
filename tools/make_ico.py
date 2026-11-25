#!/usr/bin/env python3
"""生成 Windows 快捷方式用的 .ico（多尺寸，纯标准库）。

复用 make_icons 的像素绘制，把 16/32/48/64/128/256 六个尺寸打包进一个 ico。
ICO 允许直接内嵌 PNG（Vista 以后系统都认），所以不必转成 BMP。

用法：python tools/make_ico.py
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from make_icons import pixel, OUT     # noqa: E402

SIZES = (16, 32, 48, 64, 128, 256)


def png_bytes(size):
    import zlib
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            row += bytes(pixel(x, y, size)) + b"\xff"
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    return png


def main():
    OUT.mkdir(exist_ok=True)
    images = [(s, png_bytes(s)) for s in SIZES]

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        b = 0 if size >= 256 else size          # 0 表示 256
        entries += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)

    path = OUT / "radar.ico"
    path.write_bytes(header + entries + blobs)
    print(f"  ✓ assets/radar.ico  {len(images)} 个尺寸 "
          f"{'/'.join(str(s) for s in SIZES)}  共 {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
