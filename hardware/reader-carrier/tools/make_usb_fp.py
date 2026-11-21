"""Write the project's USB-C footprint: KiCad's HRO TYPE-C-31-M-12, with its pads, holes
and slots set to HRO's recommended PCB layout (the TYPE-C-31-M-12 drawing LCSC serves for
C165948, rev A, 2020-12-08), and without the three silkscreen lines on the plug side.

Checked against the drawing, which allows +-0.05 mm on the PCB layout:
- Pin pitch (0.50 mm), pad widths (0.30 / 0.60 mm), inner pad positions, peg-hole spacing
  (5.78 mm) and shell-slot spacing (8.65 mm) match KiCad's footprint.
- The outer pads (A1/B12/B1/A12, A4/B9/B4/A9) are at +-3.25 / +-2.45 in KiCad and
  +-3.20 / +-2.40 on the drawing: within its 0.05 mm tolerance, so KiCad's are kept. The
  extra 0.05 mm is what lets the CC2 track out between the VBUS pins.
- The signal pads are 1.45 mm long ending 0.72 mm behind the peg holes in KiCad; HRO draws
  1.14 mm ending 0.50 mm behind, which leaves only 0.20 mm from the outer pads to the peg
  holes (under the 0.25 mm hole clearance). KiCad's pads cover all of HRO's but its front
  0.22 mm, so the leads land fully on copper. Kept.
- Changed to the drawing: the shell slots (0.60 x 1.70 drill, 0.90 x 2.00 pad at the back;
  0.60 x 1.40 drill, 0.90 x 1.70 pad at the front, where KiCad's 1.20 mm slot could pinch
  the shell's front tabs) and the peg holes (0.60 mm).
- The drawing puts the board edge 5.79 mm in front of the peg holes, with the shell about
  0.5 mm past it. This board has it 6.27 mm (make_pcb.py USB_X), the shell face flush with
  the edge, which gives the routing room it needs; a plug still seats fully.

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

# HRO's layout, in footprint coordinates (peg holes on y = -2.6, +y towards the plug).
PEG_Y = -2.6
PAD_Y, PAD_L = -4.045, 1.45  # KiCad's (see above)
OUTER = {"A1": -3.25, "B12": -3.25, "A4": -2.45, "B9": -2.45, "B4": 2.45, "A9": 2.45, "B1": 3.25, "A12": 3.25}  # KiCad's
SLOT_BACK_Y = PEG_Y - 0.50          # level with the signal pads' front edge
SLOT_FRONT_Y = SLOT_BACK_Y + 4.18


def pad(m):
    name, kind, shape, x, y, rest = m.groups()
    x, y = float(x), float(y)
    if kind == "smd":
        x = OUTER.get(name, x)
        w = 0.6 if name in OUTER else 0.3
        return f'(pad "{name}" smd {shape} (at {x:g} {PAD_Y:g}) (size {w:g} {PAD_L:g}){rest}'
    if kind == "np_thru_hole":
        return f'(pad "" np_thru_hole circle (at {x:g} {PEG_Y:g}) (size 0.6 0.6) (drill 0.6){rest}'
    # shell slots: the back pair (y < peg line) and the front pair
    back = y < PEG_Y
    ys, l, dl = (SLOT_BACK_Y, 2.0, 1.7) if back else (SLOT_FRONT_Y, 1.7, 1.4)
    return f'(pad "{name}" thru_hole oval (at {x:g} {ys:g}) (size 0.9 {l:g}) (drill oval 0.6 {dl:g}){rest}'


PAD = re.compile(r'\(pad "([^"]*)" (smd|np_thru_hole|thru_hole) (\w+) \(at (\S+) (\S+)\) \(size [^)]*\)(?: \(drill[^)]*\))?(.*)')
text, n = PAD.subn(pad, text)
assert n == 22, n
text = text.replace(f'(footprint "{NAME}"', f'(footprint "{NAME}_EdgeTrim"', 1)
assert cut == 3, cut
OUT.write_text(text)
print(f"wrote {OUT} ({cut} silk lines removed)")
