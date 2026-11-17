#!/usr/bin/env python3
"""Draw the MagicBand Reader breadboard layout (docs/reader-breadboard.svg), ring-only build.

Everything is placed on the real 0.1" grid of one full-size 830-point
breadboard (63 rows, columns a-j, a power rail pair on each side). Hole
positions in the build spec (hardware/reader-breadboard/README.md) use the
same names, e.g. "a21" or "L+24".

The ESP32-S3-DevKitC-1 straddles the centre channel with header J1 in
column c and J3 in column j (its headers are 22.86 mm = 9 holes apart),
antenna towards row 1, USB ports towards row 25. That leaves holes a and b
free beside every J1 pin.

Usage: python3 make_diagram.py > ../../docs/reader-breadboard.svg
"""

from __future__ import annotations

P = 16                      # hole pitch in px (0.1")
ROWS = 63
X0, Y0 = 452, 118           # x of column "L-", y of row 1

COL = {"L-": 0, "L+": 1, "a": 3, "b": 4, "c": 5, "d": 6, "e": 7,
       "f": 10, "g": 11, "h": 12, "i": 13, "j": 14, "R+": 16, "R-": 17}

W, H = 1340, Y0 + ROWS * P + 80

# ESP32-S3-DevKitC-1 header J1, pin 1 (antenna end) to pin 22 (USB end).
# Source: Espressif ESP32-S3-DevKitC-1 v1.1 user guide, "Header Block" table.
J1 = ["3V3", "3V3", "RST", "4", "5", "6", "7", "15", "16", "17", "18", "8",
      "3", "46", "9", "10", "11", "12", "13", "14", "5V", "GND"]
J1_ROW = {name: 1 + i for i, name in enumerate(J1)}   # rows 1..22
USED = {"3V3": "3V3", "5": "LRC", "6": "BCLK", "7": "DIN", "8": "SDA",
        "9": "SCL", "10": "LED", "5V": "5V in", "GND": "GND"}

IC_TOP = 34        # 74AHCT125 pin 1 row (column e)
AMP_TOP = 46       # MAX98357A LRC row (header in column h)

out: list[str] = []


def x(col: str) -> float:
    return X0 + COL[col] * P


def y(row: float) -> float:
    return Y0 + (row - 1) * P


def h(name: str) -> tuple[float, float]:
    """Hole by name: 'a21', 'L+24', 'R-33'."""
    for c in ("L+", "L-", "R+", "R-"):
        if name.startswith(c):
            return x(c), y(int(name[len(c):]))
    return x(name[0]), y(int(name[1:]))


def add(s: str) -> None:
    out.append(s)


def text(xx, yy, s, cls="lbl", anchor="start", extra=""):
    add(f'<text x="{xx:.1f}" y="{yy:.1f}" class="{cls}" text-anchor="{anchor}" {extra}>{s}</text>')


def wire(points, cls, ends=True):
    pts = " ".join(f"{px:.1f},{py:.1f}" for px, py in points)
    add(f'<polyline points="{pts}" class="w {cls}"/>')
    if ends:
        for px, py in (points[0], points[-1]):
            add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.4" class="end {cls}"/>')


def jumper(a: str, b: str, cls: str, via=None):
    """A jumper between two holes; `via` are intermediate points."""
    pts = [h(a)] + (via or []) + [h(b)]
    wire(pts, cls)


# ---------------------------------------------------------------- breadboard
def breadboard():
    left, right = x("L-") - 16, x("R-") + 16
    add(f'<rect x="{left}" y="{y(1) - 34}" width="{right - left}" height="{(ROWS - 1) * P + 68}" rx="10" class="board"/>')
    gx = (x("e") + x("f")) / 2
    add(f'<rect x="{gx - 10}" y="{y(1) - 14}" width="20" height="{(ROWS - 1) * P + 28}" class="channel"/>')
    for c, kind in (("L-", "neg"), ("L+", "pos"), ("R+", "pos"), ("R-", "neg")):
        add(f'<line x1="{x(c)}" y1="{y(1) - 16}" x2="{x(c)}" y2="{y(ROWS) + 16}" class="rail {kind}"/>')
        sym = "+" if "+" in c else "−"
        text(x(c), y(1) - 21, sym, "railsym", "middle")
        text(x(c), y(ROWS) + 30, sym, "railsym", "middle")
    for c in "abcdefghij":
        text(x(c), y(1) - 20, c, "collbl", "middle")
        text(x(c), y(ROWS) + 26, c, "collbl", "middle")
    for r in range(1, ROWS + 1):
        if r == 1 or r % 5 == 0:
            text(x("L-") - 22, y(r) + 4, str(r), "rowlbl", "end")
            text(x("R-") + 22, y(r) + 4, str(r), "rowlbl", "start")
        for c in COL:
            add(f'<rect x="{x(c) - 3}" y="{y(r) - 3}" width="6" height="6" rx="1.3" class="hole"/>')
    text((left + right) / 2, y(ROWS) + 50, "Full-size 830-point breadboard (63 rows)", "cap", "middle")


# ---------------------------------------------------------------- ESP32-S3-DevKitC-1
def devkit():
    l, r = x("c") - 20, x("j") + 20          # board is 25.4 mm wide, pins 1.27 mm in from each edge
    top, bottom = y(1) - 12, y(22) + 3.15 * P   # 8 mm from pin 22 to the USB edge
    add(f'<rect x="{l}" y="{top}" width="{r - l}" height="{bottom - top}" rx="5" class="pcb"/>')
    add(f'<rect x="{l + 30}" y="{top + 4}" width="{r - l - 60}" height="{2.3 * P}" rx="3" class="antenna"/>')
    text((l + r) / 2, top + 1.5 * P, "antenna", "silk", "middle")
    add(f'<rect x="{l + 26}" y="{top + 2.6 * P}" width="{r - l - 52}" height="{6.4 * P}" rx="3" class="can"/>')
    text((l + r) / 2, top + 5.6 * P, "ESP32-S3", "chip", "middle")
    text((l + r) / 2, top + 6.8 * P, "WROOM-1 N16R8", "silk2", "middle")
    for ux, lab in ((l + 34, "UART"), (r - 34, "USB")):
        add(f'<rect x="{ux - 15}" y="{bottom - 15}" width="30" height="21" rx="4" class="usb"/>')
        text(ux, bottom - 20, lab, "silk", "middle")
    text((l + r) / 2, y(17), "ESP32-S3-", "chipsm", "middle")
    text((l + r) / 2, y(18), "DevKitC-1", "chipsm", "middle")
    text((l + r) / 2, y(19.4), "top view", "silk", "middle")
    for i, name in enumerate(J1):
        rr = 1 + i
        for cx in (x("c"), x("j")):
            add(f'<rect x="{cx - 4}" y="{y(rr) - 4}" width="8" height="8" rx="2" class="pin"/>')
        cls = "pinlbl used" if name in USED else "pinlbl"
        text(x("c") + 9, y(rr) + 3.5, name, cls, "start")
    text(x("j") - 9, y(11) + 4, "J3", "silk", "end")
    text(x("j") - 9, y(12.2) + 4, "(no", "silk", "end")
    text(x("j") - 9, y(13.2) + 4, "wires)", "silk", "end")
    text(x("c") + 9, y(1) - 16 + 3, "J1", "silk", "start")


# ---------------------------------------------------------------- parts on the breadboard
def ic():
    l, r = x("e") - 7, x("f") + 7
    add(f'<rect x="{l}" y="{y(IC_TOP) - 9}" width="{r - l}" height="{6 * P + 18}" rx="3" class="ic"/>')
    add(f'<circle cx="{(l + r) / 2}" cy="{y(IC_TOP) - 3}" r="3" class="notch"/>')
    for i in range(7):
        add(f'<rect x="{x("e") - 3}" y="{y(IC_TOP + i) - 3}" width="6" height="6" class="icpin"/>')
        add(f'<rect x="{x("f") - 3}" y="{y(IC_TOP + i) - 3}" width="6" height="6" class="icpin"/>')
    cx, cy = (l + r) / 2, y(IC_TOP + 3)
    text(cx, cy + 4, "74AHCT125", "icname", "middle", f'transform="rotate(90 {cx} {cy})"')
    for i in range(7):
        text(x("e") - 9, y(IC_TOP + i) + 3, str(1 + i), "pinno", "end")
        text(x("f") + 9, y(IC_TOP + i) + 3, str(14 - i), "pinno", "start")


def resistor_lying(a: str, b: str, bands, label, lab_side="end"):
    (x1, y1), (x2, y2) = h(a), h(b)
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="lead"/>')
    my = (y1 + y2) / 2
    add(f'<rect x="{x1 - 5}" y="{my - 17}" width="10" height="34" rx="4" class="res"/>')
    for k, band in enumerate(bands):
        add(f'<rect x="{x1 - 5}" y="{my - 12 + k * 7}" width="10" height="3" class="{band}"/>')
    return my


def ceramic(a: str, b: str):
    (x1, y1), (x2, y2) = h(a), h(b)
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="lead"/>')
    add(f'<rect x="{x1 - 7}" y="{(y1 + y2) / 2 - 6}" width="14" height="12" rx="5" class="cer"/>')


def electrolytic(neg: str, pos: str, r=9):
    (x1, y1), (x2, y2) = h(neg), h(pos)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" class="elec"/>')
    add(f'<path d="M{cx - r * 0.6} {cy - r * 0.8} A{r} {r} 0 0 0 {cx + r * 0.6} {cy - r * 0.8}" class="stripe"/>')


def amp():
    """Adafruit MAX98357A: 7-pin header in column h, body overhanging the right rails."""
    names = ["LRC", "BCLK", "DIN", "GAIN", "SD", "GND", "Vin"]
    l, r = x("h") - 9, x("R-") + 96
    add(f'<rect x="{l}" y="{y(AMP_TOP) - 11}" width="{r - l}" height="{6 * P + 22}" rx="4" class="mod"/>')
    for i, n in enumerate(names):
        add(f'<rect x="{x("h") - 4}" y="{y(AMP_TOP + i) - 4}" width="8" height="8" rx="1.5" class="pin"/>')
        text(x("h") + 9, y(AMP_TOP + i) + 3.5, n, "modpin", "start")
    text(r - 8, y(AMP_TOP) + 4, "MAX98357A", "modname", "end")
    text(r - 8, y(AMP_TOP + 1) + 4, "Adafruit 3006", "modsub", "end")
    text(r - 8, y(AMP_TOP + 2) + 4, "overhangs the", "modsub", "end")
    text(r - 8, y(AMP_TOP + 3) + 4, "right rails", "modsub", "end")
    add(f'<rect x="{r - 18}" y="{y(AMP_TOP + 4) - 4}" width="14" height="30" rx="2" class="term"/>')
    text(r - 22, y(AMP_TOP + 5) + 4, "+ −", "modsub", "end")
    return (r - 4, y(AMP_TOP + 4) + 4), (r - 4, y(AMP_TOP + 5) + 10)


# ---------------------------------------------------------------- off-board
def module(xx, yy, w, hh, title, pins, notes=(), side="left", cls="mod"):
    add(f'<rect x="{xx}" y="{yy}" width="{w}" height="{hh}" rx="8" class="{cls}"/>')
    text(xx + 12, yy + 22, title, "modname", "start")
    for k, line in enumerate(notes):
        text(xx + 12, yy + 39 + 14 * k, line, "modsub", "start")
    pos = {}
    px = xx + w if side == "right" else xx
    for k, name in enumerate(pins):
        py = yy + hh - 14 - (len(pins) - 1 - k) * 18
        add(f'<rect x="{px - 4}" y="{py - 4}" width="8" height="8" rx="1.5" class="pin"/>')
        if side == "right":
            text(px - 10, py + 4, name, "modpin", "end")
        else:
            text(px + 10, py + 4, name, "modpin", "start")
        pos[name] = (px, py)
    return pos


def hub(xx, yy, title, n=5, cls="hubp"):
    w = 26 + n * 16
    add(f'<rect x="{xx}" y="{yy}" width="{w}" height="40" rx="6" class="hub {cls}"/>')
    text(xx - 8, yy + 16, title[0], "modsub2", "end")
    text(xx - 8, yy + 31, title[1], "modsub2", "end")
    ports = []
    for k in range(n):
        cx = xx + 13 + k * 16 + 8
        add(f'<rect x="{cx - 5}" y="{yy + 24}" width="10" height="10" rx="2" class="hubport"/>')
        add(f'<rect x="{cx - 4}" y="{yy + 6}" width="8" height="12" rx="2" class="lever"/>')
        ports.append((cx, yy + 34))
    return ports


def marker(n: int, xx: float, yy: float) -> None:
    add(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="9" class="mark"/>')
    text(xx, yy + 4, str(n), "markno", "middle")


NOTES = [
    "Pull this 5 V jumper (a21–L+21) before plugging USB into the ESP32.",
    "3.3 V from the ESP32 to two 4.7 kΩ I²C pull-ups (a26–a30, b26–b31).",
    "Rail-split bridges (L+29–35, L−30–36). Fit them even if your rails are continuous.",
    "0.1 µF across the 74AHCT125 supply (h33–h34); row 33 is grounded by j33.",
    "Unused 74AHCT125 channels tied off: enables to 5 V, inputs to ground.",
    "Left-to-right rail bridges (rows 42 and 43) feed the right-hand rails.",
    "100 µF at the amplifier supply (g51–g52), stripe (−) to row 51.",
    "470 Ω at the ring end of the data wire; 1000 µF across the ring's 5V/GND pads.",
]


NOTES_H = 50 + 8 * 39          # 8 notes of about two lines each
RING_Y = 440 + NOTES_H + 40


def build() -> str:
    out.clear()
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
        f'role="img" aria-label="MagicBand Reader breadboard layout">')
    add(f"<style>{CSS}</style>")
    add(f'<rect width="{W}" height="{H}" class="bg"/>')
    text(24, 34, "MagicBand Reader: breadboard proof of concept (ring only)", "title", "start")
    text(24, 54, "Hole names (a21, L+24 …) match the wiring table in hardware/reader-breadboard/README.md. Top view.", "sub", "start")

    breadboard()

    # ---- on-board parts
    ic()
    ceramic("h33", "h34")
    resistor_lying("a26", "a30", ("b-y", "b-v", "b-r", "b-gd"), "")
    resistor_lying("b26", "b31", ("b-y", "b-v", "b-r", "b-gd"), "")
    a_spk_p, a_spk_n = amp()
    electrolytic("g51", "g52")

    # ---- rail feeds, split bridges, left-right bridges
    jumper("L+29", "L+35", "p5", via=[(x("L+") - 7, y(29)), (x("L+") - 7, y(35))])
    jumper("L-30", "L-36", "gnd", via=[(x("L-") - 7, y(30)), (x("L-") - 7, y(36))])
    jumper("L+42", "R+42", "p5")
    jumper("L-43", "R-43", "gnd")

    devkit()

    # ---- ESP32 power
    jumper("a21", "L+21", "p5")
    jumper("a22", "L-22", "gnd")

    # ---- 3V3 and I2C
    jumper("b1", "e26", "p33", via=[(x("b") + 6, y(1)), (x("b") + 6, y(24.6)), (x("e"), y(24.6))])
    jumper("a12", "e30", "sda", via=[(x("a") - 7, y(12)), (x("a") - 7, y(24.2)), (x("d") + 7, y(24.2)), (x("d") + 7, y(30))])
    jumper("a15", "e31", "scl", via=[(x("a") - 9.5, y(15)), (x("a") - 9.5, y(24.9)), (x("e") + 6, y(24.9)), (x("e") + 6, y(31))])

    # ---- 74AHCT125
    jumper("b16", "d35", "led", via=[(x("b") + 3, y(16)), (x("b") + 3, y(33.4)), (x("d"), y(33.4))])
    for a_, b_, c_ in (("a34", "L-34", "gnd"), ("a37", "L+37", "p5"), ("a38", "L-38", "gnd"), ("a40", "L-40", "gnd"),
                       ("j33", "R-33", "gnd"), ("j34", "R+34", "p5"), ("j35", "R+35", "p5"), ("j36", "R-36", "gnd"),
                       ("j38", "R+38", "p5"), ("j39", "R-39", "gnd")):
        jumper(a_, b_, c_)

    # ---- I2S
    for gpio, row, off, cls in (("5", AMP_TOP, -2.5, "i2s1"), ("6", AMP_TOP + 1, -5, "i2s2"), ("7", AMP_TOP + 2, -7.5, "i2s3")):
        src = f"b{J1_ROW[gpio]}"
        lane = x("L-") - 10 + off * 2
        jumper(src, f"f{row}", cls, via=[(x("b") - 4, y(J1_ROW[gpio])), (x("b") - 4, y(J1_ROW[gpio]) + 4),
                                         (lane, y(J1_ROW[gpio]) + 4), (lane, y(44.4 + (row - AMP_TOP) * 0.5)),
                                         (x("f") - 4, y(44.4 + (row - AMP_TOP) * 0.5)), (x("f") - 4, y(row))])

    # ---------------------------------------------------------------- power: USB-C -> hubs
    hp = hub(150, y(49), ("5 V hub", "Adafruit 874"), n=5, cls="hubp")
    hg = hub(150, y(54), ("GND hub", "Adafruit 874"), n=5, cls="hubg")
    psu = module(36, y(59.5), 230, 122, "USB-C PD board, 5 V", ["+", "−"],
                 ["HUSB238 (5807) or CH224K", "board: see power diagram.", "USB-C charger, 20 W+"], side="right", cls="psu")
    wire([psu["+"], (300, psu["+"][1]), (300, hp[0][1] + 14), (hp[0][0], hp[0][1] + 14), hp[0]], "p5 thick")
    wire([psu["−"], (286, psu["−"][1]), (286, hg[0][1] + 14), (hg[0][0], hg[0][1] + 14), hg[0]], "gnd thick")
    text(310, y(61), "22 AWG, ≤30 cm", "awg", "start")
    # hubs -> breadboard rails (22 AWG solid)
    wire([hp[1], (hp[1][0], y(47.6)), (338, y(47.6)), (338, y(24)), h("L+24")], "p5")
    wire([hg[1], (hg[1][0], y(52.6)), (350, y(52.6)), (350, y(25)), h("L-25")], "gnd")
    text(334, y(40), "22 AWG", "awg", "end")
    # hubs -> amplifier rows (22 AWG solid)
    wire([hp[2], (hp[2][0], y(48.2)), (x("f") - 9, y(48.2)), (x("f") - 9, y(AMP_TOP + 6)), h(f"f{AMP_TOP + 6}")], "p5")
    wire([hg[2], (hg[2][0], y(53.2)), (x("f") - 12, y(53.2)), (x("f") - 12, y(AMP_TOP + 5) + 2), (x("f"), y(AMP_TOP + 5) + 2), h(f"f{AMP_TOP + 5}")], "gnd")

    # ---------------------------------------------------------------- PN532
    pn = module(36, 176, 236, 196, "PN532 NFC module V3", ["GND", "VCC", "SDA", "SCL"],
                ["Elechouse V3 or clone (AITRIP)", "Switches: 1 = ON, 2 = OFF (I²C)", "Header: GND VCC SDA SCL",
                 "VCC from 5 V. Its header has no", "pull-ups: the 4.7 kΩ add them"], side="right")
    wire([pn["GND"], (300, pn["GND"][1]), (300, y(28)), h("L-28")], "gnd")
    wire([pn["VCC"], (312, pn["VCC"][1]), (312, y(27)), h("L+27")], "p5")
    wire([pn["SDA"], (324, pn["SDA"][1]), (324, y(30) + 5), (x("c") - 5, y(30) + 5), (x("c") - 5, y(30)), h("c30")], "sda")
    wire([pn["SCL"], (288, pn["SCL"][1]), (288, y(31) + 5), (x("c") - 2, y(31) + 5), h("c31")], "scl")
    text(154, 392, "female-to-male jumpers, ≤20 cm", "awg", "middle")

    # ---------------------------------------------------------------- LED ring
    ring = module(1010, RING_Y, 210, 128, "NeoPixel Ring 24", ["DIN", "5V", "GND"],
                  ["Adafruit 1586, 24 LEDs: the", "PN532 sits inside the ring;", "1000 µF across 5V/GND pads"], side="left")
    capx = ring["5V"][0] - 18
    capy = (ring["5V"][1] + ring["GND"][1]) / 2
    add(f'<circle cx="{capx}" cy="{capy}" r="9" class="elec"/>')
    add(f'<path d="M{capx - 5.4} {capy + 7.2} A9 9 0 0 0 {capx + 5.4} {capy + 7.2}" class="stripe"/>')
    rx = ring["DIN"][0] - 44
    wire([h("c36"), (x("c"), y(36) - 7), (x("b") - 10, y(36) - 7), (x("b") - 10, y(44.0)),
          (918, y(44.0)), (918, ring["DIN"][1]), (rx - 18, ring["DIN"][1])], "led")
    add(f'<rect x="{rx - 18}" y="{ring["DIN"][1] - 5}" width="34" height="10" rx="4" class="res"/>')
    for k, band in enumerate(("b-or", "b-or", "b-br", "b-gd")):
        add(f'<rect x="{rx - 13 + k * 7}" y="{ring["DIN"][1] - 5}" width="3" height="10" class="{band}"/>')
    wire([(rx + 16, ring["DIN"][1]), ring["DIN"]], "led", ends=False)
    text(rx, ring["DIN"][1] - 10, "470 Ω", "partlbl", "middle")
    wire([hp[3], (hp[3][0], y(45.2)), (930, y(45.2)), (930, ring["5V"][1]), ring["5V"]], "p5 thick")
    wire([hg[3], (hg[3][0], hg[3][1] + 8), (250, hg[3][1] + 8), (250, y(44.6)), (942, y(44.6)), (942, ring["GND"][1]), ring["GND"]], "gnd thick")
    text(1010, RING_Y + 146, "Ring power comes straight from the hubs", "awg", "start")
    text(1010, RING_Y + 161, "(22 AWG), never through the breadboard.", "awg", "start")

    # ---------------------------------------------------------------- speaker
    sx, sy = 930, y(60)
    add(f'<circle cx="{sx}" cy="{sy}" r="34" class="spk"/><circle cx="{sx}" cy="{sy}" r="14" class="spkc"/>')
    text(sx, sy + 52, "Speaker 3 W 4 Ω (Adafruit 3351)", "partlbl", "middle")
    wire([a_spk_p, (850, a_spk_p[1]), (850, sy - 10), (sx - 34, sy - 10)], "spkw")
    wire([a_spk_n, (862, a_spk_n[1]), (862, sy + 10), (sx - 34, sy + 10)], "spkw")

    # ---------------------------------------------------------------- markers
    marker(1, x("L-") - 24, y(21.5))
    marker(2, x("L-") - 24, y(28.5) - 4)
    marker(3, x("L-") - 24, y(33))
    marker(4, x("i") + 4, y(32.6))
    marker(5, x("R-") + 22, y(37))
    marker(6, x("R-") + 22, y(42.5))
    marker(7, x("e") + 2, y(53.4))
    marker(8, rx - 34, ring["DIN"][1] - 22)

    # ---------------------------------------------------------------- legend + notes (right column)
    lx, ly = 930, 150
    add(f'<rect x="{lx}" y="{ly}" width="372" height="270" rx="10" class="legend"/>')
    text(lx + 16, ly + 26, "Wires", "modname2", "start")
    items = [("p5", "5 V"), ("gnd", "Ground"), ("p33", "3.3 V (from the ESP32's 3V3 pin)"),
             ("sda", "I²C SDA (GPIO8)"), ("scl", "I²C SCL (GPIO9)"), ("i2s1", "I²S LRC (GPIO5)"),
             ("i2s2", "I²S BCLK (GPIO6)"), ("i2s3", "I²S DIN (GPIO7)"), ("led", "LED data: GPIO10 → 74AHCT125 → ring"),
             ("spkw", "Speaker")]
    for k, (cls, lab) in enumerate(items):
        yy = ly + 48 + k * 20
        wire([(lx + 18, yy), (lx + 56, yy)], cls, ends=False)
        text(lx + 68, yy + 4, lab, "leg", "start")
    text(lx + 16, ly + 256, "Thick lines: 22 AWG stranded power runs", "leg2", "start")

    nx, ny = 930, 440
    add(f'<rect x="{nx}" y="{ny}" width="372" height="{NOTES_H}" rx="10" class="rules"/>')
    text(nx + 16, ny + 26, "Numbered points", "modname2", "start")
    yy = ny + 50
    for k, note in enumerate(NOTES):
        marker(k + 1, nx + 26, yy - 4)
        words, line, lines = note.split(), "", []
        for wd in words:
            if len(line) + len(wd) > 46:
                lines.append(line)
                line = wd
            else:
                line = f"{line} {wd}".strip()
        lines.append(line)
        for li, ln in enumerate(lines):
            text(nx + 44, yy + li * 15, ln, "leg", "start")
        yy += 15 * len(lines) + 9

    add("</svg>")
    return "\n".join(out)


CSS = """
.bg{fill:#ffffff} .title{font:700 22px Inter,system-ui,sans-serif;fill:#1d1b16} .sub{font:500 13px Inter,system-ui,sans-serif;fill:#5c5a52}
.board{fill:#f2f1ea;stroke:#cfccbf;stroke-width:1.5} .channel{fill:#e2e0d4} .hole{fill:#a7a497}
.rail{stroke-width:2.4;opacity:.6} .rail.pos{stroke:#d62f2f} .rail.neg{stroke:#2b5fd1}
.railsym{font:700 14px ui-monospace,Menlo,Consolas,monospace;fill:#5c5a52}
.collbl,.rowlbl,.pinno{font:600 10px ui-monospace,Menlo,Consolas,monospace;fill:#6b695f}
.pcb{fill:#1f3d2f;stroke:#14281e;stroke-width:1.5;opacity:.96} .antenna{fill:none;stroke:#cfe0d4;stroke-dasharray:3 3}
.can{fill:#c8ccd2;stroke:#14281e} .usb{fill:#9ca3ad}
.chip{font:700 14px Inter,system-ui,sans-serif;fill:#2b2f36} .chipsm{font:700 12px Inter,system-ui,sans-serif;fill:#e8efe9}
.silk{font:600 9.5px Inter,system-ui,sans-serif;fill:#d9e6dc} .silk2{font:500 9.5px Inter,system-ui,sans-serif;fill:#2b2f36}
.pin{fill:#d9b44a;stroke:#8c7023}
.pinlbl{font:500 9.5px ui-monospace,Menlo,Consolas,monospace;fill:#d9e6dc;opacity:.55} .pinlbl.used{opacity:1;font-weight:700;fill:#ffffff}
.ic{fill:#2a2a2e} .icpin{fill:#c9c9c9} .notch{fill:#f2f1ea} .icname{font:700 10px ui-monospace,Menlo,Consolas,monospace;fill:#f2f2f2}
.mod{fill:#1d4f8f;stroke:#123562;stroke-width:1.5} .psu{fill:#3c3c44;stroke:#22222a;stroke-width:1.5}
.modname{font:700 13px Inter,system-ui,sans-serif;fill:#eef4ff} .modsub{font:500 10.5px Inter,system-ui,sans-serif;fill:#d6e2f5}
.modname2{font:700 13px Inter,system-ui,sans-serif;fill:#1d1b16} .modsub2{font:600 11px Inter,system-ui,sans-serif;fill:#3d3b34}
.modpin{font:600 10.5px ui-monospace,Menlo,Consolas,monospace;fill:#eef4ff}
.term{fill:#2f9e5b} .spk{fill:#3a3a3f;stroke:#22222a} .spkc{fill:#55555c}
.cer{fill:#d9a441;stroke:#8a6420} .elec{fill:#24324a;stroke:#111a29} .stripe{fill:none;stroke:#e5e9f0;stroke-width:3}
.lead{stroke:#8d8d8d;stroke-width:2} .res{fill:#d8c3a0;stroke:#a68f68}
.b-or{fill:#e07b1f} .b-br{fill:#7a4a24} .b-gd{fill:#c9a646} .b-y{fill:#e8c51c} .b-v{fill:#8a3fc1} .b-r{fill:#d62f2f}
.partlbl{font:600 11px Inter,system-ui,sans-serif;fill:#2b2a26} .partsub{font:500 10px Inter,system-ui,sans-serif;fill:#5c5a52}
.warnlbl{font:700 10.5px Inter,system-ui,sans-serif;fill:#b42318} .awg{font:600 10.5px Inter,system-ui,sans-serif;fill:#5c5a52}
.cap{font:500 12px Inter,system-ui,sans-serif;fill:#5c5a52}
.hub{stroke-width:1.5} .hubp{fill:#fbe3e3;stroke:#d62f2f} .hubg{fill:#e3e3e8;stroke:#2c2c2c}
.hubport{fill:#6b6b6b} .lever{fill:#f08a24}
.mark{fill:#b42318} .markno{font:700 11px Inter,system-ui,sans-serif;fill:#ffffff}
.legend,.rules{fill:#faf9f5;stroke:#d9d6ca} .leg{font:500 11.5px Inter,system-ui,sans-serif;fill:#2b2a26} .leg2{font:500 10.5px Inter,system-ui,sans-serif;fill:#5c5a52}
.w{fill:none;stroke-width:3.4;stroke-linejoin:round;stroke-linecap:round;opacity:.94} .w.thick{stroke-width:6}
.end{stroke:none}
.p5{stroke:#d62f2f;fill:#d62f2f} .gnd{stroke:#222222;fill:#222222} .p33{stroke:#ef8a17;fill:#ef8a17}
.sda{stroke:#1f8fd6;fill:#1f8fd6} .scl{stroke:#2e9a4f;fill:#2e9a4f}
.i2s1{stroke:#7a4ad8;fill:#7a4ad8} .i2s2{stroke:#b04ad8;fill:#b04ad8} .i2s3{stroke:#4a5bd8;fill:#4a5bd8}
.led{stroke:#d6a900;fill:#d6a900} .spkw{stroke:#8a8a8a;fill:#8a8a8a}
polyline.w{fill:none}
"""

if __name__ == "__main__":
    print(build())
