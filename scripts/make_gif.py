#!/usr/bin/env python3
"""Render assets/simulate.gif — a terminal-style animation of the CLI output.

Uses the real `python simulate.py` output (captured live) typed line by line.
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

BG = "#1a1a19"
FG = "#d6d5cd"
PROMPT = "#0ca30c"
MUTED = "#898781"

W, H, PAD, LINE_H = 760, 470, 22, 19
FONT_SIZE = 13


def load_font():
    for path in ("/System/Library/Fonts/Menlo.ttc",
                 "/System/Library/Fonts/Monaco.ttf"):
        try:
            return ImageFont.truetype(path, FONT_SIZE)
        except OSError:
            continue
    return ImageFont.load_default()


def frame(lines, font):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = PAD
    for text, color in lines:
        d.text((PAD, y), text, fill=color, font=font)
        y += LINE_H
    return img


def main() -> None:
    out = subprocess.run(
        [sys.executable, str(ROOT / "simulate.py")],
        capture_output=True, text=True, check=True).stdout
    body = []
    for ln in out.splitlines():
        ln = ln.rstrip()
        if len(ln) > 92 and " · " in ln:  # wrap wide annotation lines
            head, *rest = ln.split(" · ")
            body.append(head)
            body.append("  · " + " · ".join(rest))
        else:
            body.append(ln)
    font = load_font()

    lines = [("$ python simulate.py", PROMPT)]
    frames = [frame(lines, font)]
    durations = [900]
    for ln in body:
        color = MUTED if ("format:" in ln or "verify =" in ln
                          or "expected LLM calls" in ln) else FG
        lines.append((ln, color))
        frames.append(frame(lines, font))
        durations.append(110)
    durations[-1] = 4500  # hold the finished table

    dest = ROOT / "assets" / "simulate.gif"
    frames[0].save(dest, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    print(f"wrote {dest} ({dest.stat().st_size // 1024} KB, "
          f"{len(frames)} frames)")


if __name__ == "__main__":
    main()
