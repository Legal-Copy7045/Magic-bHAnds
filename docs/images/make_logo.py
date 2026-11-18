#!/usr/bin/env python3
"""Build the MagicbHAnds logo (icon + wordmark) as SVG, for rendering to PNG.

    python3 docs/images/make_logo.py light > logo.svg
    python3 docs/images/make_logo.py dark  > logo-dark.svg

Then render each at 1100 x 256 with a transparent background, e.g. with
Playwright (page.screenshot(omit_background=True)). The PNGs are used by the
README (docs/images/logo*.png) and the integration (custom_components/
magicband/brand/logo.png, dark_logo.png).
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
W, H = 1100, 256
TEXT = {"light": "#1E1B4B", "dark": "#F3F2FF"}
HA = "#3B82F6"


def build(mode: str) -> str:
    icon = (HERE / "icon.svg").read_text()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", icon, re.S).group(1)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <svg x="0" y="0" width="{H}" height="{H}" viewBox="0 0 512 512">{inner}</svg>
  <text x="284" y="172" font-family="Inter, 'Inter Display', sans-serif" font-weight="800" font-size="116"
        letter-spacing="-3" fill="{TEXT[mode]}">Magicb<tspan fill="{HA}">HA</tspan>nds</text>
</svg>
"""


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "light"))
