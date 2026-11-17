#!/usr/bin/env python3
"""Draw the terminal-base and point-to-point wiring diagrams.

    python3 make_diagrams.py terminal-base  > ../../docs/reader-terminal-base.svg
    python3 make_diagrams.py point-to-point > ../../docs/reader-point-to-point.svg

Both share the interface board (an Adafruit Perma-Proto half-sized PCB,
drawn hole for hole: rows 1-30, columns a-j, a rail pair on each side), the
power hubs, the USB-C supply, PN532, LED ring, amplifier and speaker. Only
the ESP32 side differs. Hole names (e2, L+25, ...) match
hardware/reader-wired/README.md.
"""

from __future__ import annotations

import sys

P = 16
ROWS = 30
BX, BY = 640, 150              # interface board: x of column "L-", y of row 1
COL = {"L-": 0, "L+": 1, "a": 3, "b": 4, "c": 5, "d": 6, "e": 7,
       "f": 10, "g": 11, "h": 12, "i": 13, "j": 14, "R+": 16, "R-": 17}
W, H = 1340, 1080
IC = 10                        # 74AHCT125 pin 1 row (column e)

out: list[str] = []


def add(s):
    out.append(s)


def text(x, y, s, cls="leg", anchor="start", extra=""):
    add(f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}" {extra}>{s}</text>')


def bx(c):
    return BX + COL[c] * P


def by(r):
    return BY + (r - 1) * P


def hole(name):
    for c in ("L+", "L-", "R+", "R-"):
        if name.startswith(c):
            return bx(c), by(int(name[len(c):]))
    return bx(name[0]), by(int(name[1:]))


def wire(pts, cls, ends=True):
    add(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" class="w {cls}"/>')
    if ends:
        for x, y in (pts[0], pts[-1]):
            add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" class="end {cls}"/>')


def jumper(a, b, cls):
    wire([hole(a), hole(b)], cls)


def marker(n, x, y):
    add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" class="mark"/>')
    text(x, y + 4, str(n), "markno", "middle")


def module(x, y, w, h, title, pins, notes=(), side="left", cls="mod", pitch=18):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="{cls}"/>')
    text(x + 12, y + 22, title, "modname")
    for k, line in enumerate(notes):
        text(x + 12, y + 39 + 14 * k, line, "modsub")
    pos = {}
    px = x + w if side == "right" else x
    for k, name in enumerate(pins):
        py = y + h - 14 - (len(pins) - 1 - k) * pitch
        add(f'<rect x="{px - 4}" y="{py - 4}" width="8" height="8" rx="1.5" class="pin"/>')
        text(px - 10 if side == "right" else px + 10, py + 4, name, "modpin", "end" if side == "right" else "start")
        pos[name] = (px, py)
    return pos


def hub(x, y, title, cls):
    w = 26 + 5 * 16
    add(f'<rect x="{x}" y="{y}" width="{w}" height="40" rx="6" class="hub {cls}"/>')
    text(x + w, y + 56, title, "modsub2", "end")
    ports = []
    for k in range(5):
        cx = x + 21 + k * 16
        add(f'<rect x="{cx - 5}" y="{y + 4}" width="10" height="10" rx="2" class="hubport"/>')
        add(f'<rect x="{cx - 4}" y="{y + 20}" width="8" height="12" rx="2" class="lever"/>')
        ports.append((cx, y + 4))
    return ports


def elec(x, y, r=9, vertical=False):
    add(f'<circle cx="{x}" cy="{y}" r="{r}" class="elec"/>')
    add(f'<path d="M{x - r * 0.6} {y + r * 0.8} A{r} {r} 0 0 0 {x + r * 0.6} {y + r * 0.8}" class="stripe"/>')


def lying_res(a, b, bands):
    (x1, y1), (x2, y2) = hole(a), hole(b)
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="lead"/>')
    my = (y1 + y2) / 2
    add(f'<rect x="{x1 - 5}" y="{my - 16}" width="10" height="32" rx="4" class="res"/>')
    for k, band in enumerate(bands):
        add(f'<rect x="{x1 - 5}" y="{my - 11 + k * 7}" width="10" height="3" class="{band}"/>')


# ---------------------------------------------------------------- interface board
def interface_board():
    l, r = bx("L-") - 16, bx("R-") + 16
    add(f'<rect x="{l}" y="{by(1) - 34}" width="{r - l}" height="{(ROWS - 1) * P + 70}" rx="8" class="perma"/>')
    gx = (bx("e") + bx("f")) / 2
    add(f'<rect x="{gx - 9}" y="{by(1) - 12}" width="18" height="{(ROWS - 1) * P + 24}" class="pchan"/>')
    for c, kind in (("L-", "neg"), ("L+", "pos"), ("R+", "pos"), ("R-", "neg")):
        add(f'<line x1="{bx(c)}" y1="{by(1) - 14}" x2="{bx(c)}" y2="{by(ROWS) + 14}" class="rail {kind}"/>')
        text(bx(c), by(1) - 20, "+" if "+" in c else "−", "railsym", "middle")
    for c in "abcdefghij":
        text(bx(c), by(1) - 20, c, "collbl", "middle")
    for rr in range(1, ROWS + 1):
        if rr == 1 or rr % 5 == 0:
            text(bx("R-") + 20, by(rr) + 4, str(rr), "rowlbl")
        for c in COL:
            add(f'<circle cx="{bx(c)}" cy="{by(rr)}" r="3.6" class="pad"/>')
    text((l + r) / 2, by(ROWS) + 26, "Interface board: Adafruit Perma-Proto half (1609)", "pcap", "middle")
    # 74AHCT125
    il, ir = bx("e") - 7, bx("f") + 7
    add(f'<rect x="{il}" y="{by(IC) - 9}" width="{ir - il}" height="{6 * P + 18}" rx="3" class="ic"/>')
    add(f'<circle cx="{(il + ir) / 2}" cy="{by(IC) - 3}" r="3" class="notch"/>')
    for i in range(7):
        text(bx("e") - 9, by(IC + i) + 3, str(1 + i), "pinno", "end")
        text(bx("f") + 9, by(IC + i) + 3, str(14 - i), "pinno")
    cx, cy = (il + ir) / 2, by(IC + 3)
    text(cx, cy + 4, "74AHCT125", "icname", "middle", f'transform="rotate(90 {cx} {cy})"')
    # 0.1 uF, pull-ups
    (x1, y1), (x2, y2) = hole("h9"), hole("h10")
    add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="lead"/>')
    add(f'<rect x="{x1 - 7}" y="{(y1 + y2) / 2 - 6}" width="14" height="12" rx="5" class="cer"/>')
    lying_res("a2", "a6", ("b-y", "b-v", "b-r", "b-gd"))
    lying_res("b2", "b7", ("b-y", "b-v", "b-r", "b-gd"))
    # ties, decoupling ground, rail bridges
    for a, b, cls in (("a10", "L-10", "gnd"), ("a13", "L+13", "p5"), ("a14", "L-14", "gnd"), ("a16", "L-16", "gnd"),
                      ("j9", "R-9", "gnd"), ("j10", "R+10", "p5"), ("j11", "R+11", "p5"), ("j12", "R-12", "gnd"),
                      ("j14", "R+14", "p5"), ("j15", "R-15", "gnd"), ("L+20", "R+20", "p5"), ("L-21", "R-21", "gnd")):
        jumper(a, b, cls)


NOTES = [
    "ESP32 5 V: unclip this wire from the 5 V hub before plugging USB into the ESP32.",
    "Two 4.7 kΩ I²C pull-ups to the ESP32's 3.3 V (a2–a6 SDA, b2–b7 SCL).",
    "0.1 µF across the 74AHCT125 supply (h9–h10); row 9 grounded by j9.",
    "Unused 74AHCT125 channels tied off: enables to 5 V, inputs to ground.",
    "Rail bridges (rows 20 and 21): the right-hand rails get 5 V and ground.",
    "100 µF soldered across the amplifier's Vin and GND pins, stripe to GND.",
    "470 Ω at the ring end of the data wire; 1000 µF across the ring's 5V/GND pads.",
]

J1 = ["3V3", "3V3", "RST", "4", "5", "6", "7", "15", "16", "17", "18", "8", "3", "46", "9", "10",
      "11", "12", "13", "14", "5V", "GND"]


def esp_point_to_point():
    """DevKitC-1 drawn turned 90° anticlockwise: antenna left, J1 along the bottom edge."""
    x0, y0, w, h = 40, 130, 440, 150
    add(f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="6" class="pcb"/>')
    add(f'<rect x="{x0 + 6}" y="{y0 + 22}" width="38" height="{h - 44}" rx="3" class="antenna"/>')
    text(x0 + 25, y0 + h / 2 + 3, "ant.", "silk", "middle")
    add(f'<rect x="{x0 + 50}" y="{y0 + 22}" width="104" height="{h - 44}" rx="3" class="can"/>')
    text(x0 + 102, y0 + h / 2 + 5, "ESP32-S3", "chip", "middle")
    text(x0 + 270, y0 + 66, "ESP32-S3-DevKitC-1 N16R8", "chipsm", "middle")
    text(x0 + 270, y0 + 84, "top view, turned 90°", "silk", "middle")
    for i, lab in enumerate(("UART", "USB")):
        add(f'<rect x="{x0 + w - 20}" y="{y0 + 28 + i * 66}" width="22" height="30" rx="4" class="usb"/>')
        text(x0 + w - 26, y0 + 47 + i * 66, lab, "silk", "end")
    pins = {}
    for i, n in enumerate(J1):
        px = x0 + 58 + i * 16.5
        add(f'<rect x="{px - 4}" y="{y0 + h - 12}" width="8" height="8" rx="2" class="pin"/>')
        add(f'<rect x="{px - 4}" y="{y0 + 4}" width="8" height="8" rx="2" class="pin"/>')
        used = (n in ("5", "6", "7", "8", "9", "10", "5V", "GND")) or i == 0
        cy = y0 + h - 18
        text(px + 3, cy, f"{n}", "pinlbl used" if used else "pinlbl", "start", f'transform="rotate(-90 {px + 3} {cy})"')
        if used:
            pins[n] = (px, y0 + h - 8)
    text(210, 404, "J1 is the bottom edge here: female jumpers on its pins", "partsub")
    text(210, 418, "(pin 1 = 3V3, nearest the antenna).", "partsub")
    text(x0 + w / 2, y0 - 6, "J3 (no connections)", "partsub", "middle")
    return pins, y0 + h


def esp_terminal_base():
    """Terminal base drawn turned 90° anticlockwise; only the terminals used, by printed label."""
    x0, y0, w, h = 40, 110, 440, 200
    add(f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="10" class="base"/>')
    add(f'<rect x="{x0 + 30}" y="{y0 + 40}" width="{w - 60}" height="{h - 80}" rx="5" class="pcb"/>')
    text(x0 + w / 2, y0 + 92, "ESP32-S3-DevKitC-1 N16R8", "chipsm", "middle")
    text(x0 + w / 2, y0 + 110, "plugged into the Lonely Binary terminal base", "silk", "middle")
    pins = {}
    for i, n in enumerate(("3V3", "7", "8", "9", "10")):        # left-hand terminals (bottom edge here)
        px = x0 + 60 + i * 52
        add(f'<rect x="{px - 18}" y="{y0 + h - 30}" width="36" height="24" rx="3" class="term"/>')
        text(px, y0 + h - 14, n, "termlbl", "middle")
        pins[n] = (px, y0 + h - 6)
    for i, n in enumerate(("5", "6")):                          # right-hand terminals (top edge here)
        px = x0 + 60 + i * 52
        add(f'<rect x="{px - 18}" y="{y0 + 6}" width="36" height="24" rx="3" class="term"/>')
        text(px, y0 + 22, n, "termlbl", "middle")
        pins[n] = (px, y0 + 6)
    for i, n in enumerate(("5V", "GND")):                        # pads by the USB ports
        px = x0 + w - 70 + i * 40
        add(f'<rect x="{px - 14}" y="{y0 + h - 26}" width="28" height="16" rx="3" class="padsq"/>')
        text(px, y0 + h - 32, n, "silk2", "middle")
        pins[n] = (px, y0 + h - 10)
    text(170, 404, "Left terminals 3V3, 7–10 (bottom here); right terminals 5, 6 (top).", "partsub")
    text(170, 418, "5V/GND: wires soldered to the pads by the USB ports.", "partsub")
    text(170, 432, "Match terminals by their printed labels.", "partsub")
    return pins, y0 + h + 30


def build(kind: str) -> str:
    out.clear()
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
        f'aria-label="MagicBand Reader {kind} wiring">')
    add(f"<style>{CSS}</style>")
    add(f'<rect width="{W}" height="{H}" class="bg"/>')
    title = "terminal base" if kind == "terminal-base" else "point-to-point"
    text(24, 34, f"MagicBand Reader: {title} build (ring only)", "title")
    text(24, 54, "Hole names (c2, L+25 …) match hardware/reader-wired/README.md. Adafruit product numbers in brackets.", "sub")

    interface_board()
    pins, esp_bottom = esp_point_to_point() if kind == "point-to-point" else esp_terminal_base()

    # ---------------------------------------------------------------- modules (right column)
    pn = module(1000, 110, 240, 140, "PN532 NFC module V3", ["GND", "VCC", "SDA", "SCL"],
                ["Your AITRIP V3. Switches: I²C", "(1 = ON, 2 = OFF). VCC from 5 V"], side="left")
    ring = module(1040, 300, 220, 116, "NeoPixel Ring 24 (1586)", ["DIN", "5V", "GND"],
                  ["PN532 sits inside the ring", "1000 µF across 5V/GND pads"], side="left")
    amp = module(1000, 470, 210, 168, "MAX98357A (3006)", ["LRC", "BCLK", "DIN", "GAIN", "SD", "GND", "Vin"],
                 [], side="left")
    tx = 1000 + 210 - 18
    add(f'<rect x="{tx}" y="{amp["LRC"][1] - 6}" width="14" height="30" rx="2" class="termg"/>')
    sx, sy = 1270, 720
    add(f'<circle cx="{sx}" cy="{sy}" r="32" class="spk"/><circle cx="{sx}" cy="{sy}" r="13" class="spkc"/>')
    text(sx, sy + 48, "Speaker 3 W 4 Ω", "partlbl", "middle")
    text(sx, sy + 62, "(3351)", "partlbl", "middle")
    wire([(tx + 14, amp["LRC"][1] + 2), (1262, amp["LRC"][1] + 2), (1262, sy - 32)], "spkw")
    wire([(tx + 14, amp["LRC"][1] + 16), (1280, amp["LRC"][1] + 16), (1280, sy - 31)], "spkw")
    elec(amp["GND"][0] - 22, (amp["GND"][1] + amp["Vin"][1]) / 2)
    elec(ring["5V"][0] - 22, (ring["5V"][1] + ring["GND"][1]) / 2)

    # ---------------------------------------------------------------- power (below the interface board)
    hp = hub(620, 760, "5 V hub (874)", "hubp")
    hg = hub(800, 760, "GND hub (874)", "hubg")
    psu = module(620, 900, 300, 104, "USB-C PD board, set to 5 V", ["+", "−"],
                 ["Adafruit HUSB238 (5807) or a CH224K", "board: see the power diagram.", "USB-C charger of 20 W or more"],
                 side="right", cls="psu")
    wire([psu["+"], (940, psu["+"][1]), (940, 860), (hp[0][0], 860), (hp[0][0], hp[0][1] + 36)], "p5 thick", ends=False)
    add(f'<circle cx="{psu["+"][0]}" cy="{psu["+"][1]}" r="3.4" class="end p5"/>')
    wire([psu["−"], (952, psu["−"][1]), (952, 870), (hg[0][0], 870), (hg[0][0], hg[0][1] + 36)], "gnd thick", ends=False)
    add(f'<circle cx="{psu["−"][0]}" cy="{psu["−"][1]}" r="3.4" class="end gnd"/>')
    text(960, 960, "22 AWG stranded, ≤ 30 cm", "awg")
    # hubs -> interface rails
    wire([hp[1], (hp[1][0], 730), (bx("L+") - 22, 730), (bx("L+") - 22, by(25)), hole("L+25")], "p5")
    wire([hg[1], (hg[1][0], 722), (bx("L-") - 30, 722), (bx("L-") - 30, by(26)), hole("L-26")], "gnd")
    # hubs -> amplifier
    wire([hp[2], (hp[2][0], 714), (968, 714), (968, amp["Vin"][1]), amp["Vin"]], "p5")
    wire([hg[2], (hg[2][0], 706), (958, 706), (958, amp["GND"][1]), amp["GND"]], "gnd")
    # hubs -> ring
    wire([hp[3], (hp[3][0], 698), (988, 698), (988, ring["5V"][1]), ring["5V"]], "p5 thick")
    wire([hg[3], (hg[3][0], 690), (998, 690), (998, ring["GND"][1]), ring["GND"]], "gnd thick")
    # hubs -> ESP32 5V / GND
    p5x, p5y = pins["5V"]
    gx_, gy_ = pins["GND"]
    wire([(p5x, p5y), (p5x, 376), (560, 376), (560, 744), (hp[4][0], 744), (hp[4][0], hp[4][1])], "p5")
    wire([(gx_, gy_), (gx_, 384), (570, 384), (570, 752), (hg[4][0], 752), (hg[4][0], hg[4][1])], "gnd")

    # ---------------------------------------------------------------- ESP32 signals
    def to_board(sig, dest, cls, lane_y):
        x_, y_ = pins[sig]
        dx, dy = hole(dest)
        wire([(x_, y_), (x_, lane_y), (bx("L-") - 46 + (lane_y - 330) * 0.3, lane_y),
              (bx("L-") - 46 + (lane_y - 330) * 0.3, dy), (dx, dy)], cls)

    def to_amp(sig, dest, cls, lane_y, lane_x):
        x_, y_ = pins[sig]
        dx, dy = dest
        if y_ < esp_bottom - 60:          # terminal on the top edge: go up and over
            top = 80 + (lane_x - 900) * 0.4
            wire([(x_, y_), (x_, top), (lane_x, top), (lane_x, dy), (dx, dy)], cls)
        else:
            wire([(x_, y_), (x_, lane_y), (lane_x, lane_y), (lane_x, dy), (dx, dy)], cls)

    to_board("3V3", "c2", "p33", 330)
    to_board("8", "d6", "sda", 338)
    to_board("9", "d7", "scl", 346)
    to_board("10", "d11", "led", 354)
    to_amp("5", amp["LRC"], "i2s1", 662, 920)
    to_amp("6", amp["BCLK"], "i2s2", 670, 930)
    to_amp("7", amp["DIN"], "i2s3", 678, 940)

    # ---------------------------------------------------------------- interface board -> PN532 and ring
    wire([hole("c6"), (bx("c") + 4, by(6) - 7), (bx("R-") + 40, by(6) - 7), (bx("R-") + 40, pn["SDA"][1]), pn["SDA"]], "sda")
    wire([hole("c7"), (bx("c") + 4, by(7) + 7), (bx("R-") + 50, by(7) + 7), (bx("R-") + 50, pn["SCL"][1]), pn["SCL"]], "scl")
    wire([hole("L+4"), (bx("L+") - 10, by(4)), (bx("L+") - 10, by(1) - 44), (bx("R-") + 60, by(1) - 44),
          (bx("R-") + 60, pn["VCC"][1]), pn["VCC"]], "p5")
    wire([hole("L-3"), (bx("L-") - 10, by(3)), (bx("L-") - 10, by(1) - 52), (bx("R-") + 70, by(1) - 52),
          (bx("R-") + 70, pn["GND"][1]), pn["GND"]], "gnd")
    rx = ring["DIN"][0] - 46
    wire([hole("c12"), (bx("c"), by(12) + 8), (bx("b") - 8, by(12) + 8), (bx("b") - 8, by(28)),
          (bx("R-") + 80, by(28)), (bx("R-") + 80, ring["DIN"][1]), (rx - 17, ring["DIN"][1])], "led")
    add(f'<rect x="{rx - 17}" y="{ring["DIN"][1] - 5}" width="34" height="10" rx="4" class="res"/>')
    for k, band in enumerate(("b-y", "b-v", "b-br", "b-gd")):
        add(f'<rect x="{rx - 12 + k * 7}" y="{ring["DIN"][1] - 5}" width="3" height="10" class="{band}"/>')
    wire([(rx + 17, ring["DIN"][1]), ring["DIN"]], "led", ends=False)
    text(rx, ring["DIN"][1] - 10, "470 Ω", "partlbl", "middle")

    # ---------------------------------------------------------------- markers
    marker(1, p5x + 14, 366)
    marker(2, bx("L-") - 22, by(5))
    marker(3, bx("i") + 4, by(8.3))
    marker(4, bx("R-") + 22, by(13))
    marker(5, bx("R-") + 22, by(20.5))
    marker(6, amp["GND"][0] - 22, amp["Vin"][1] + 22)
    marker(7, rx - 32, ring["DIN"][1] - 14)

    # ---------------------------------------------------------------- notes + legend (bottom left)
    nx, ny, nw = 24, 690, 520
    add(f'<rect x="{nx}" y="{ny}" width="{nw}" height="{H - ny - 16}" rx="10" class="notes"/>')
    text(nx + 14, ny + 24, "Numbered points", "modname2")
    yy = ny + 48
    for k, note in enumerate(NOTES):
        marker(k + 1, nx + 24, yy - 4)
        words, line, lines = note.split(), "", []
        for wd in words:
            if len(line) + len(wd) > 66:
                lines.append(line)
                line = wd
            else:
                line = f"{line} {wd}".strip()
        lines.append(line)
        for li, ln in enumerate(lines):
            text(nx + 42, yy + li * 14, ln, "leg2")
        yy += 14 * len(lines) + 8
    ly = yy + 10
    text(nx + 14, ly, "Wires", "modname2")
    items = (("p5", "5 V"), ("gnd", "Ground"), ("p33", "3.3 V"), ("sda", "SDA (GPIO8)"), ("scl", "SCL (GPIO9)"),
             ("i2s1", "LRC (GPIO5)"), ("i2s2", "BCLK (GPIO6)"), ("i2s3", "DIN (GPIO7)"), ("led", "LED data (GPIO10)"))
    for k, (cls, lab) in enumerate(items):
        col, row = k % 3, k // 3
        x_, y_ = nx + 16 + col * 168, ly + 22 + row * 20
        wire([(x_, y_), (x_ + 30, y_)], cls, ends=False)
        text(x_ + 38, y_ + 4, lab, "leg2")

    add("</svg>")
    return "\n".join(out)


def build_interface_board() -> str:
    """Close-up of the interface board with every wire in and out labelled."""
    global BX, BY
    BX, BY = 470, 130
    out.clear()
    w, h = 1330, 690
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
        f'aria-label="MagicBand Reader interface board">')
    add(f"<style>{CSS}</style>")
    add(f'<rect width="{w}" height="{h}" class="bg"/>')
    text(24, 34, "Interface board (terminal base and point-to-point builds)", "title")
    text(24, 54, "Adafruit Perma-Proto half-sized PCB (1609), component side. Holes are row and column (c2 = row 2, column c).", "sub")
    interface_board()

    def tag(x, y, label, sub, cls, anchor):
        tw = 7.0 * max(len(label), len(sub) * 0.85) + 24
        bx_ = x - tw if anchor == "end" else x
        add(f'<rect x="{bx_}" y="{y - 15}" width="{tw}" height="{34 if sub else 22}" rx="6" class="tag {cls}tag"/>')
        text(bx_ + 10, y + 1, label, "tagt")
        if sub:
            text(bx_ + 10, y + 14, sub, "tags")

    ins = [("c2", "ESP32 3V3", "3.3 V for the pull-ups", "p33", 0),
           ("d6", "ESP32 GPIO8", "I²C SDA", "sda", 1),
           ("d7", "ESP32 GPIO9", "I²C SCL", "scl", 2),
           ("d11", "ESP32 GPIO10", "LED data in (IC pin 2)", "led", 3),
           ("L+25", "5 V hub", "22 AWG red", "p5", 4),
           ("L-26", "GND hub", "22 AWG black", "gnd", 5)]
    text(BX - 210, 112, "IN", "h3l", "middle")
    for hole_, lab, sub, cls, k in ins:
        hx, hy = hole(hole_)
        ty = 140 + k * 76
        lane = bx("L-") - 30 - k * 6
        wire([(hx, hy), (lane, hy), (lane, ty), (BX - 120, ty)], cls)
        tag(BX - 120, ty, lab, sub, cls, "end")

    outs = [("L-3", "PN532 GND", "", "gnd", 0),
            ("L+4", "PN532 VCC", "5 V", "p5", 1),
            ("c6", "PN532 SDA", "", "sda", 2),
            ("c7", "PN532 SCL", "", "scl", 3),
            ("c12", "LED data out", "→ 470 Ω at the ring → DIN", "led", 4)]
    text(bx("R-") + 190, 112, "OUT", "h3l", "middle")
    for hole_, lab, sub, cls, k in outs:
        hx, hy = hole(hole_)
        ty = 140 + k * 70
        lx_ = bx("R-") + 120
        if hole_ in ("L-3", "L+4"):
            top = by(1) - 44 - k * 8
            pts = [(hx, hy), (hx - 10 - k * 4, hy), (hx - 10 - k * 4, top), (lx_ - 20 + k * 4, top), (lx_ - 20 + k * 4, ty), (lx_, ty)]
        elif hole_ == "c12":
            pts = [(hx, hy), (hx, hy + 8), (bx("b") - 8, hy + 8), (bx("b") - 8, by(28)), (lx_ - 8, by(28)), (lx_ - 8, ty), (lx_, ty)]
        else:
            yy = hy - 7 if hole_ == "c6" else hy + 7
            pts = [(hx, hy), (hx + 4, yy), (lx_ - 30 + k * 6, yy), (lx_ - 30 + k * 6, ty), (lx_, ty)]
        wire(pts, cls)
        tag(lx_, ty, lab, sub, cls, "start")

    # pin key
    kx, ky = bx("R-") + 120, 470
    add(f'<rect x="{kx}" y="{ky}" width="430" height="170" rx="10" class="notes"/>')
    text(kx + 14, ky + 22, "74AHCT125 pins (notch towards row 1)", "modname2")
    left = ["1 1OE → GND (on)", "2 1A ← GPIO10", "3 1Y → LED out", "4 2OE → 5 V (off)",
            "5 2A → GND", "6 2Y (open)", "7 GND"]
    right = ["14 VCC → 5 V", "13 4OE → 5 V (off)", "12 4A → GND", "11 4Y (open)",
             "10 3OE → 5 V (off)", "9 3A → GND", "8 3Y (open)"]
    for i, (lt, rt) in enumerate(zip(left, right)):
        text(kx + 14, ky + 46 + i * 17, lt, "mono")
        text(kx + 230, ky + 46 + i * 17, rt, "mono")
    text(24, h - 20, "Before fitting the IC: e10, e14, e16, f12, f15 beep to GND; e13, f10, f11, f14 beep to 5 V; 5 V to GND doesn't beep; c6 and c7 each read 4.7 kΩ to c2.", "sub")
    add("</svg>")
    return "\n".join(out)


CSS = """
.bg{fill:#ffffff} .title{font:700 22px Inter,system-ui,sans-serif;fill:#1d1b16} .sub{font:500 13px Inter,system-ui,sans-serif;fill:#5c5a52}
.perma{fill:#1d3f86;stroke:#122a5c;stroke-width:1.5} .pchan{fill:#173570} .pad{fill:#e3c167;stroke:#9d7f2c;stroke-width:.8}
.rail{stroke-width:2.4;opacity:.8} .rail.pos{stroke:#ff6b6b} .rail.neg{stroke:#9fb8ff}
.railsym,.collbl,.rowlbl,.pinno{font:600 10px ui-monospace,Menlo,Consolas,monospace;fill:#cfdcff}
.tag{stroke-width:1.5} .p5tag{fill:#fdecec;stroke:#d62f2f} .gndtag{fill:#ececee;stroke:#222} .p33tag{fill:#fff1df;stroke:#ef8a17} .sdatag{fill:#e6f3fb;stroke:#1f8fd6} .scltag{fill:#e8f5ec;stroke:#2e9a4f} .ledtag{fill:#fff8d6;stroke:#d6a900}
.tagt{font:700 12px Inter,system-ui,sans-serif;fill:#1d1b16} .tags{font:500 10.5px Inter,system-ui,sans-serif;fill:#3d3b34} .h3l{font:800 13px Inter,system-ui,sans-serif;fill:#5c5a52} .mono{font:500 11.5px ui-monospace,Menlo,Consolas,monospace;fill:#2b2a26}
.cap{font:600 12px Inter,system-ui,sans-serif;fill:#3d3b34} .pcap{font:600 11px Inter,system-ui,sans-serif;fill:#cfdcff}
.pcb{fill:#1f3d2f;stroke:#14281e;stroke-width:1.5} .antenna{fill:none;stroke:#cfe0d4;stroke-dasharray:3 3}
.can{fill:#c8ccd2;stroke:#14281e} .usb{fill:#9ca3ad} .base{fill:#2b2b31;stroke:#18181c;stroke-width:1.5}
.term{fill:#2f9e5b;stroke:#1d6b3c} .termg{fill:#2f9e5b} .padsq{fill:#d9b44a;stroke:#8c7023}
.termlbl{font:700 11px ui-monospace,Menlo,Consolas,monospace;fill:#ffffff}
.chip{font:700 14px Inter,system-ui,sans-serif;fill:#2b2f36} .chipsm{font:700 11.5px Inter,system-ui,sans-serif;fill:#e8efe9}
.silk{font:600 9.5px Inter,system-ui,sans-serif;fill:#d9e6dc} .silk2{font:600 9px Inter,system-ui,sans-serif;fill:#e8efe9}
.pin{fill:#d9b44a;stroke:#8c7023}
.pinlbl{font:500 9.5px ui-monospace,Menlo,Consolas,monospace;fill:#d9e6dc;opacity:.5} .pinlbl.used{opacity:1;font-weight:700;fill:#ffffff}
.ic{fill:#2a2a2e} .notch{fill:#1d3f86} .icname{font:700 10px ui-monospace,Menlo,Consolas,monospace;fill:#f2f2f2}
.mod{fill:#1d4f8f;stroke:#123562;stroke-width:1.5} .psu{fill:#3c3c44;stroke:#22222a;stroke-width:1.5}
.modname{font:700 13px Inter,system-ui,sans-serif;fill:#eef4ff} .modsub{font:500 10.5px Inter,system-ui,sans-serif;fill:#d6e2f5}
.modname2{font:700 13px Inter,system-ui,sans-serif;fill:#1d1b16} .modsub2{font:600 11px Inter,system-ui,sans-serif;fill:#3d3b34}
.modpin{font:600 10.5px ui-monospace,Menlo,Consolas,monospace;fill:#eef4ff}
.spk{fill:#3a3a3f;stroke:#22222a} .spkc{fill:#55555c}
.cer{fill:#d9a441;stroke:#8a6420} .elec{fill:#24324a;stroke:#111a29} .stripe{fill:none;stroke:#e5e9f0;stroke-width:3}
.lead{stroke:#c9c9c9;stroke-width:2} .res{fill:#d8c3a0;stroke:#a68f68}
.b-y{fill:#e8c51c} .b-v{fill:#8a3fc1} .b-r{fill:#d62f2f} .b-br{fill:#7a4a24} .b-gd{fill:#c9a646}
.partlbl{font:600 11px Inter,system-ui,sans-serif;fill:#2b2a26} .partsub{font:500 10px Inter,system-ui,sans-serif;fill:#5c5a52}
.awg{font:600 10.5px Inter,system-ui,sans-serif;fill:#5c5a52}
.hub{stroke-width:1.5} .hubp{fill:#fbe3e3;stroke:#d62f2f} .hubg{fill:#e3e3e8;stroke:#2c2c2c}
.hubport{fill:#6b6b6b} .lever{fill:#f08a24}
.notes{fill:#faf9f5;stroke:#d9d6ca} .leg{font:500 11.5px Inter,system-ui,sans-serif;fill:#2b2a26} .leg2{font:500 10.5px Inter,system-ui,sans-serif;fill:#2b2a26}
.mark{fill:#b42318} .markno{font:700 11px Inter,system-ui,sans-serif;fill:#ffffff}
.w{fill:none;stroke-width:3.2;stroke-linejoin:round;stroke-linecap:round;opacity:.94} .w.thick{stroke-width:5.5}
.end{stroke:none}
.p5{stroke:#d62f2f;fill:#d62f2f} .gnd{stroke:#222222;fill:#222222} .p33{stroke:#ef8a17;fill:#ef8a17}
.sda{stroke:#1f8fd6;fill:#1f8fd6} .scl{stroke:#2e9a4f;fill:#2e9a4f}
.i2s1{stroke:#7a4ad8;fill:#7a4ad8} .i2s2{stroke:#b04ad8;fill:#b04ad8} .i2s3{stroke:#4a5bd8;fill:#4a5bd8}
.led{stroke:#d6a900;fill:#d6a900} .spkw{stroke:#8a8a8a;fill:#8a8a8a}
polyline.w{fill:none}
"""

if __name__ == "__main__":
    print(build_interface_board() if sys.argv[1] == "interface-board" else build(sys.argv[1]))
