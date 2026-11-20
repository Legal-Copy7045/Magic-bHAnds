"""The lighter Waltograph cut must keep its letter widths consistent.

A CFF font stores each glyph's advance width twice: in the hmtx table and in
the CFF charstring (relative to nominalWidthX). Browsers on Linux read hmtx;
Windows (DirectWrite) reads the CFF. When they disagreed, the wordmark looked
fine in tests but widely spaced on Windows.
"""

from pathlib import Path

import pytest

TTFont = pytest.importorskip("fontTools.ttLib").TTFont

FONTS = Path(__file__).parents[1] / "custom_components" / "magicband" / "frontend" / "fonts"


@pytest.mark.parametrize("name", ["waltograph42.otf", "waltograph42-light.otf"])
def test_cff_widths_match_hmtx(name):
    from fontTools.misc.psCharStrings import T2WidthExtractor

    font = TTFont(FONTS / name)
    top = font["CFF "].cff.topDictIndex[0]
    private = top.Private
    hmtx = font["hmtx"]
    wrong = []
    for g in font.getGlyphOrder():
        charstring = top.CharStrings[g]
        extractor = T2WidthExtractor(
            getattr(private, "Subrs", []), top.GlobalSubrs, private.nominalWidthX, private.defaultWidthX
        )
        extractor.execute(charstring)
        if extractor.width != hmtx[g][0]:
            wrong.append((g, extractor.width, hmtx[g][0]))
    assert not wrong, f"{len(wrong)} glyphs disagree (glyph, CFF, hmtx), e.g. {wrong[:5]}"


def test_light_cut_is_not_wider_than_the_original():
    original, light = TTFont(FONTS / "waltograph42.otf"), TTFont(FONTS / "waltograph42-light.otf")
    for g in "aeMnsH":
        assert light["hmtx"][g][0] <= original["hmtx"][g][0]
