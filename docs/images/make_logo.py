#!/usr/bin/env python3
"""Build the MagicbHAnds logo (icon + wordmark) as SVG, for rendering to PNG.

    python3 docs/images/make_logo.py light > logo.svg
    python3 docs/images/make_logo.py dark  > logo-dark.svg

Then render each at 1100 x 256 with a transparent background, e.g. with
Playwright (page.screenshot(omit_background=True)), from this folder so the
font path resolves.

The wordmark is set in Waltograph by Justin Callaghan (mickeyavenue.com),
released under Creative Commons Attribution-NonCommercial-ShareAlike; the
font, its readme and licence are in custom_components/magicband/frontend/
fonts/ (the lighter cut, waltograph42-light.otf, is made by
make_light_font.py). The logo images made with it carry the same licence. The PNGs are used by the
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
FONT = "../../custom_components/magicband/frontend/fonts/waltograph42-light.otf"


def build(mode: str) -> str:
    icon = (HERE / "icon.svg").read_text()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", icon, re.S).group(1)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
  <style>@font-face{{font-family:"Waltograph";src:url("{FONT}") format("opentype")}}</style>
  <svg x="0" y="0" width="{H}" height="{H}" viewBox="0 0 512 512">{inner}</svg>
  <text x="276" y="182" font-family="Waltograph" font-size="166" letter-spacing="3"
        fill="{TEXT[mode]}">Magicb<tspan dx="12" fill="{HA}">HA</tspan><tspan dx="6">nds</tspan></text>
</svg>
"""


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "light"))
