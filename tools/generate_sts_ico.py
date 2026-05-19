#!/usr/bin/env python3
"""Generate the Windows .ico used by the STS packaged application.

The source application artwork is `src/ui/assets/sts_logo.svg`.  This helper
creates a dependency-free ICO companion in the same assets folder so PyInstaller
and Windows taskbar/shortcut metadata can use a native icon format.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable, Tuple

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "ui" / "assets" / "sts_logo.ico"
SIZES = (256, 128, 64, 48, 32, 16)
Color = Tuple[int, int, int, int]


def blend(dst: Color, src: Color) -> Color:
    sr, sg, sb, sa = src
    dr, dg, db, da = dst
    a = sa / 255.0
    inv = 1.0 - a
    return (
        int(sr * a + dr * inv),
        int(sg * a + dg * inv),
        int(sb * a + db * inv),
        int(sa + da * inv),
    )


def put(px: list[list[Color]], x: int, y: int, color: Color) -> None:
    if 0 <= y < len(px) and 0 <= x < len(px[0]):
        px[y][x] = blend(px[y][x], color)


def rect(px: list[list[Color]], x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
    for y in range(max(0, y0), min(len(px), y1)):
        row = px[y]
        for x in range(max(0, x0), min(len(row), x1)):
            row[x] = blend(row[x], color)


def rounded_rect(px: list[list[Color]], x0: int, y0: int, x1: int, y1: int, r: int, color: Color, border: Color | None = None, border_w: int = 0) -> None:
    for y in range(max(0, y0), min(len(px), y1)):
        for x in range(max(0, x0), min(len(px[0]), x1)):
            cx = min(max(x, x0 + r), x1 - r - 1)
            cy = min(max(y, y0 + r), y1 - r - 1)
            inside = (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2
            if not inside:
                continue
            if border and border_w:
                inner_x0, inner_y0 = x0 + border_w, y0 + border_w
                inner_x1, inner_y1 = x1 - border_w, y1 - border_w
                inner_r = max(1, r - border_w)
                icx = min(max(x, inner_x0 + inner_r), inner_x1 - inner_r - 1)
                icy = min(max(y, inner_y0 + inner_r), inner_y1 - inner_r - 1)
                inner = (inner_x0 <= x < inner_x1 and inner_y0 <= y < inner_y1 and (x - icx) ** 2 + (y - icy) ** 2 <= inner_r ** 2)
                put(px, x, y, color if inner else border)
            else:
                put(px, x, y, color)


def line(px: list[list[Color]], x0: int, y0: int, x1: int, y1: int, color: Color, width: int = 1) -> None:
    dx, dy = x1 - x0, y1 - y0
    steps = max(abs(dx), abs(dy), 1)
    rad = max(0, width // 2)
    for i in range(steps + 1):
        x = round(x0 + dx * i / steps)
        y = round(y0 + dy * i / steps)
        for yy in range(y - rad, y + rad + 1):
            for xx in range(x - rad, x + rad + 1):
                if (xx - x) ** 2 + (yy - y) ** 2 <= rad ** 2 + 0.2:
                    put(px, xx, yy, color)


def circle(px: list[list[Color]], cx: int, cy: int, radius: int, color: Color, fill: bool = True, width: int = 1) -> None:
    r2 = radius * radius
    inner = max(0, radius - width) ** 2
    for y in range(cy - radius - 1, cy + radius + 2):
        for x in range(cx - radius - 1, cx + radius + 2):
            d = (x - cx) ** 2 + (y - cy) ** 2
            if (fill and d <= r2) or (not fill and inner <= d <= r2):
                put(px, x, y, color)


FONT = {
    "S": ["111", "100", "100", "111", "001", "001", "111"],
    "T": ["111", "010", "010", "010", "010", "010", "010"],
}


def draw_text(px: list[list[Color]], text: str, x: int, y: int, scale: int, color: Color) -> None:
    cur = x
    for ch in text:
        glyph = FONT.get(ch.upper())
        if not glyph:
            cur += 4 * scale
            continue
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit == "1":
                    rect(px, cur + gx * scale, y + gy * scale, cur + (gx + 1) * scale, y + (gy + 1) * scale, color)
        cur += (len(glyph[0]) + 1) * scale


def make_image(size: int) -> list[list[Color]]:
    px: list[list[Color]] = [[(0, 0, 0, 0) for _ in range(size)] for __ in range(size)]
    s = size / 256.0
    def sc(v: int) -> int: return max(1, round(v * s))

    rounded_rect(px, sc(18), sc(18), sc(238), sc(238), sc(42), (8, 37, 92, 255), (68, 173, 255, 255), max(1, sc(5)))
    rounded_rect(px, sc(35), sc(35), sc(221), sc(221), sc(30), (9, 47, 112, 155), None, 0)

    # Document sheet
    rounded_rect(px, sc(62), sc(38), sc(188), sc(178), sc(9), (239, 247, 255, 255), (255, 255, 255, 255), max(1, sc(3)))
    # Folded corner
    line(px, sc(156), sc(40), sc(195), sc(78), (190, 220, 248, 255), max(1, sc(3)))
    line(px, sc(158), sc(40), sc(158), sc(78), (198, 220, 245, 255), max(1, sc(2)))
    line(px, sc(158), sc(78), sc(192), sc(78), (198, 220, 245, 255), max(1, sc(2)))

    for yy, w in [(82, 88), (104, 94), (126, 86), (148, 68)]:
        line(px, sc(78), sc(yy), sc(78 + w), sc(yy), (128, 180, 230, 255), max(1, sc(5)))

    # Magnifier
    circle(px, sc(168), sc(133), sc(38), (5, 28, 78, 255), fill=False, width=sc(13))
    circle(px, sc(168), sc(133), sc(32), (135, 229, 255, 170), fill=True)
    circle(px, sc(168), sc(133), sc(33), (140, 232, 255, 255), fill=False, width=max(1, sc(4)))
    line(px, sc(197), sc(164), sc(234), sc(201), (5, 28, 78, 255), sc(18))
    line(px, sc(200), sc(166), sc(235), sc(201), (71, 156, 232, 255), sc(9))

    # Footer STS text
    scale = max(1, sc(7))
    text_w = (3 + 1 + 3 + 1 + 3) * scale
    draw_text(px, "STS", (size - text_w) // 2, sc(195), scale, (242, 249, 255, 255))
    return px


def dib_for(px: list[list[Color]]) -> bytes:
    h = len(px)
    w = len(px[0])
    header = struct.pack("<IIIHHIIIIII", 40, w, h * 2, 1, 32, 0, w * h * 4, 0, 0, 0, 0)
    bgra = bytearray()
    for row in reversed(px):
        for r, g, b, a in row:
            bgra += bytes((b, g, r, a))
    mask_stride = ((w + 31) // 32) * 4
    and_mask = bytes(mask_stride * h)
    return header + bytes(bgra) + and_mask


def write_ico(images: Iterable[tuple[int, bytes]]) -> None:
    imgs = list(images)
    header = struct.pack("<HHH", 0, 1, len(imgs))
    offset = 6 + 16 * len(imgs)
    entries = bytearray()
    blobs = bytearray()
    for size, data in imgs:
        entries += struct.pack("<BBBBHHII", 0 if size >= 256 else size, 0 if size >= 256 else size, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(header + entries + blobs)


def main() -> None:
    write_ico((size, dib_for(make_image(size))) for size in SIZES)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
