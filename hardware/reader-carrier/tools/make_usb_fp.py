"""Write the project's USB-C footprint: KiCad's HRO TYPE-C-31-M-12 without the three
silkscreen lines on the plug side.

The socket overhangs the board's left edge on purpose (the plug face sits just past it),
so the stock footprint's silk lines on that side (y >= 2 mm in footprint coordinates)
would print off the board. Keeping the trimmed copy in tools/lib, rather than trimming
at build time, lets the DRC check the board against its library. Run once; the result
is committed.
"""
import re
from pathlib import Path

NAME = "USB_C_Receptacle_HRO_TYPE-C-31-M-12"
SRC = Path("/usr/share/kicad/footprints/Connector_USB.pretty") / f"{NAME}.kicad_mod"
OUT = Path(__file__).parent / "lib" / "MagicbHAnds.pretty" / f"{NAME}_EdgeTrim.kicad_mod"

LINE = re.compile(r'\s*\(fp_line \(start \S+ (\S+)\) \(end \S+ (\S+)\) \(layer "F\.SilkS"\).*')
out, cut = [], 0
for line in SRC.read_text().splitlines():
    m = LINE.fullmatch(line)
    if m and float(m.group(1)) >= 2 and float(m.group(2)) >= 2:
        cut += 1
        continue
    out.append(line)
text = "\n".join(out) + "\n"
text = text.replace(f'(footprint "{NAME}"', f'(footprint "{NAME}_EdgeTrim"', 1)
assert cut == 3, cut
OUT.write_text(text)
print(f"wrote {OUT} ({cut} silk lines removed)")
