"""Generate placeholder Lift List PNG icons with the standard library only.

Design §9: rounded-square primary-blue background, white checklist mark, and a
small barbell. Real artwork replaces these later.

Usage: python bin/make_icons.py
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "static" / "img" / "icons"

PRIMARY = (0x2B, 0x7F, 0xFF, 0xFF)
WHITE = (0xFF, 0xFF, 0xFF, 0xFF)
TRANSPARENT = (0, 0, 0, 0)


def sd_rounded_rect(x, y, cx, cy, hw, hh, radius):
    qx = abs(x - cx) - (hw - radius)
    qy = abs(y - cy) - (hh - radius)
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    inside = min(max(qx, qy), 0.0)
    return outside + inside - radius


def sd_box(x, y, cx, cy, hw, hh):
    dx = abs(x - cx) - hw
    dy = abs(y - cy) - hh
    outside = math.hypot(max(dx, 0.0), max(dy, 0.0))
    inside = min(max(dx, dy), 0.0)
    return outside + inside


def sd_segment(x, y, ax, ay, bx, by):
    px, py = x - ax, y - ay
    vx, vy = bx - ax, by - ay
    length_sq = vx * vx + vy * vy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, (px * vx + py * vy) / length_sq))
    return math.hypot(px - vx * t, py - vy * t)


def render(size: int, *, maskable: bool = False) -> list[bytearray]:
    """Render one icon at ``size`` px, supersampled 3x for smooth edges."""
    ss = 3
    n = size * ss
    inset = 0.20 * n if maskable else 0.06 * n
    span = n - 2 * inset
    radius = 0.0 if maskable else 0.22 * n

    def px(u: float) -> float:
        return inset + (u / 100.0) * span

    # Barbell (top) and checklist mark (below).
    bar = (px(28), px(30), px(72), px(30), px(4) / 2)
    left_plate = (px(27.5), px(30), px(2.5), px(8))
    right_plate = (px(72.5), px(30), px(2.5), px(8))
    left_outer = (px(22.5), px(30), px(2), px(5))
    right_outer = (px(77.5), px(30), px(2), px(5))
    check_one = (px(32), px(56), px(45), px(69), px(8) / 2)
    check_two = (px(45), px(69), px(70), px(45), px(8) / 2)

    def in_capsule(x, y, ax, ay, bx, by, half):
        return sd_segment(x, y, ax, ay, bx, by) <= half

    def is_white(x: float, y: float) -> bool:
        if in_capsule(x, y, *bar):
            return True
        if sd_box(x, y, *left_plate) <= 0 or sd_box(x, y, *right_plate) <= 0:
            return True
        if sd_box(x, y, *left_outer) <= 0 or sd_box(x, y, *right_outer) <= 0:
            return True
        return in_capsule(x, y, *check_one) or in_capsule(x, y, *check_two)

    rows: list[bytearray] = []
    for output_y in range(size):
        row = bytearray()
        for output_x in range(size):
            r_acc = g_acc = b_acc = a_acc = 0.0
            for sy in range(ss):
                y = output_y * ss + sy + 0.5
                for sx in range(ss):
                    x = output_x * ss + sx + 0.5
                    if maskable:
                        inside = True
                    else:
                        inside = sd_rounded_rect(x, y, n / 2, n / 2, n / 2, n / 2, radius) <= 0
                    if not inside:
                        continue
                    color = WHITE if is_white(x, y) else PRIMARY
                    r_acc += color[0]
                    g_acc += color[1]
                    b_acc += color[2]
                    a_acc += 255.0
            samples = ss * ss
            if a_acc == 0:
                row.extend(TRANSPARENT)
                continue
            row.append(round(r_acc / samples))
            row.append(round(g_acc / samples))
            row.append(round(b_acc / samples))
            row.append(round(a_acc / samples))
        rows.append(row)
    return rows


def write_png(path: Path, size: int, rows: list[bytearray]) -> None:
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw.extend(row)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", header)
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)
    print(f"Wrote {path.name} ({size}x{size})")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("apple-touch-icon.png", 180, False),
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-512-maskable.png", 512, True),
    ]
    for name, size, maskable in jobs:
        write_png(OUT_DIR / name, size, render(size, maskable=maskable))


if __name__ == "__main__":
    main()
