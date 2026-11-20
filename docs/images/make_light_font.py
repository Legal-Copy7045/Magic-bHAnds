#!/usr/bin/env python3
"""Make the lighter cut of Waltograph used for the MagicbHAnds wordmark and headings.

    pip install fonttools skia-pathops
    python3 docs/images/make_light_font.py

Waltograph is quite heavy at heading sizes. This thins every glyph by eroding its
outline by 0.7 % of the em (the outline minus a 1.4 %-wide stroke along it),
then takes the same amount off each side of the glyph's advance so the letters
keep their original spacing (thinning alone would open up the gaps), and writes custom_components/magicband/frontend/fonts/waltograph42-light.otf, named
"Waltograph Light (MagicbHAnds)".

Waltograph is by Justin Callaghan (mickeyavenue.com), released under Creative
Commons Attribution-NonCommercial-ShareAlike. This modified version carries the
same licence: see waltograph.txt and license.txt next to it.
"""

from pathlib import Path

from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
import pathops

FONTS = Path(__file__).resolve().parents[2] / "custom_components" / "magicband" / "frontend" / "fonts"
ERODE = 0.014  # stroke width as a fraction of the em; the glyph loses half of it on each side


def main() -> None:
    font = TTFont(FONTS / "waltograph42.otf")
    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    glyphs = font.getGlyphSet()
    width = ERODE * font["head"].unitsPerEm
    nominal = getattr(top.Private, "nominalWidthX", 0)
    thinned = {}
    for name in font.getGlyphOrder():
        glyph = glyphs[name]
        path = pathops.Path()
        glyph.draw(path.getPen(glyphSet=glyphs))
        if not path:
            continue
        path.simplify(fix_winding=True)
        edge = pathops.Path(path)
        edge.stroke(width, pathops.LineCap.ROUND_CAP, pathops.LineJoin.ROUND_JOIN, 4)
        edge.convertConicsToQuads()
        # Shift left by what each side lost and narrow the advance to match.
        advance = max(0, round(glyph.width - width))
        # CFF stores a glyph's width relative to the font's nominalWidthX; renderers
        # that read it from the CFF (DirectWrite on Windows) must get the same width
        # as the hmtx table below.
        pen = T2CharStringPen(advance - nominal, glyphs)
        pathops.op(path, edge, pathops.PathOp.DIFFERENCE).draw(TransformPen(pen, (1, 0, 0, 1, -width / 2, 0)))
        thinned[name] = pen.getCharString(private=top.Private, globalSubrs=cff.GlobalSubrs)
        font["hmtx"][name] = (advance, font["hmtx"][name][1])  # the left edge moves back to where it was
    for name, charstring in thinned.items():  # after all are drawn: composites use the originals
        top.CharStrings[name] = charstring
    family = "Waltograph Light (MagicbHAnds)"
    for record in font["name"].names:
        if record.nameID in (1, 4, 16):
            record.string = family
        elif record.nameID == 6:
            record.string = "WaltographLight-MagicbHAnds"
    top.FamilyName = top.FullName = family
    cff.fontNames[0] = "WaltographLight-MagicbHAnds"
    font.save(FONTS / "waltograph42-light.otf")


if __name__ == "__main__":
    main()
