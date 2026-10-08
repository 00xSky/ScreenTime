"""Builds assets/ScreenTime.ico from the tray icon design.

The design is the one ScreenTimeApp.create_image() in main.py draws at
64 px: three accent bars on a dark square. Each icon size is drawn on its
own pixel grid instead of being scaled down from one image, so the bars stay
sharp at 16-24 px. At 64 px the output matches create_image() pixel for pixel.

Run from the project root after changing the design in main.py:

    python tools/make_icon.py
"""

import math
import os

from PIL import Image, ImageDraw

# Same values as main.py create_image(), on its 64 px grid
BASE = 64
BACKGROUND = "#151821"
ACCENT = "#5B8DEF"
BAR_TOPS = (38, 26, 16)  # left to right
BAR_LEFT = 14            # first bar's left edge
BAR_PITCH = 13           # left edge to left edge
BAR_WIDTH = 10           # rectangle [x, top, x + 9, 50] covers 10 px
BAR_BOTTOM = 51          # one past the last row drawn (50)

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "ScreenTime.ico")


def _round(value):
    return int(math.floor(value + 0.5))


def render(size):
    s = size / BASE
    pitch = _round(BAR_PITCH * s)
    width = min(_round(BAR_WIDTH * s), pitch - 1)  # keep at least 1 px gap
    span = pitch * (len(BAR_TOPS) - 1) + width
    center = (BAR_LEFT + (BAR_PITCH * (len(BAR_TOPS) - 1) + BAR_WIDTH) / 2) * s
    left = _round(center - span / 2)
    bottom = _round(BAR_BOTTOM * s)

    image = Image.new("RGBA", (size, size), BACKGROUND)
    dc = ImageDraw.Draw(image)
    for i, top in enumerate(BAR_TOPS):
        x = left + i * pitch
        height = max(1, _round((BAR_BOTTOM - top) * s))
        dc.rectangle([x, bottom - height, x + width - 1, bottom - 1], fill=ACCENT)
    return image


def main():
    images = [render(size) for size in SIZES]
    largest = images[-1]
    # Uncompressed (BMP) entries: Tk's iconbitmap cannot read PNG entries and
    # would fall back to a blurry rescale for the window icon
    largest.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES],
                 append_images=images[:-1], bitmap_format="bmp")
    print(f"{OUT}: {', '.join(str(s) for s in SIZES)} px")


if __name__ == "__main__":
    main()
