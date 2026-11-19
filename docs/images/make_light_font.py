#!/usr/bin/env python3
"""Make the lighter cut of Waltograph used for the MagicbHAnds wordmark and headings.

    pip install fonttools skia-pathops
    python3 docs/images/make_light_font.py

Waltograph is quite heavy at heading sizes. This thins every glyph by eroding its
outline by 1.25 % of the em (the outline minus a 2.5 %-wide stroke along it) and
writes custom_components/magicband/frontend/fonts/waltograph42-light.otf, named
"Waltograph Light (MagicbHAnds)".

Waltograph is by Justin Callaghan (mickeyavenue.com), released under Creative
Commons Attribution-NonCommercial-ShareAlike. This modified version carries the
same licence: see waltograph.txt and license.txt next to it.
"""

from pathlib import Path

from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont
import pathops

FONTS = Path(__file__).resolve().parents[2] / "custom_components" / "magicband" / "frontend" / "fonts"
ERODE = 0.025  # stroke width as a fraction of the em; the glyph loses half of it on each side


def main() -> None:
    font = TTFont(FONTS / "waltograph42.otf")
    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    glyphs = font.getGlyphSet()
    width = ERODE * font["head"].unitsPerEm
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
        pen = T2CharStringPen(glyph.width, glyphs)
        pathops.op(path, edge, pathops.PathOp.DIFFERENCE).draw(pen)
        thinned[name] = pen.getCharString(private=top.Private, globalSubrs=cff.GlobalSubrs)
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
