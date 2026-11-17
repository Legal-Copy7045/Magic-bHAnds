#!/usr/bin/env python3
"""Draw the reader's power distribution (docs/reader-power.svg).

Shared by every build: a USB-C charger, a USB-C PD board set to 5 V (the
Adafruit HUSB238, or a generic CH224K board), two lever-connector hubs, and
a separate branch to each load.

Usage: python3 make_power_diagram.py > ../docs/reader-power.svg
"""

W, H = 1320, 860
out: list[str] = []


def add(s):
    out.append(s)


def text(x, y, s, cls="t", anchor="start", extra=""):
    add(f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}" {extra}>{s}</text>')


def box(x, y, w, h, cls="card", r=10):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" class="{cls}"/>')


def wire(pts, cls, ends=True):
    add(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" class="w {cls}"/>')
    if ends:
        for x, y in (pts[0], pts[-1]):
            add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.6" class="end {cls}"/>')


def pad(x, y, label, state):
    """A solder-jumper pad pair: state 'closed', 'open' or 'cut'."""
    add(f'<rect x="{x}" y="{y}" width="9" height="14" rx="2" class="padj"/>')
    add(f'<rect x="{x + 13}" y="{y}" width="9" height="14" rx="2" class="padj"/>')
    if state == "closed":
        add(f'<rect x="{x + 7}" y="{y + 4}" width="8" height="6" class="bridge"/>')
    if state == "cut":
        add(f'<line x1="{x + 11}" y1="{y - 3}" x2="{x + 11}" y2="{y + 17}" class="cut"/>')
    text(x + 11, y + 28, label, "jl", "middle")


def hub(x, y, title, cls, labels):
    w = 30 + 5 * 22
    add(f'<rect x="{x}" y="{y}" width="{w}" height="52" rx="7" class="hub {cls}"/>')
    main, _, sub = title.partition(" (")
    text(x + w / 2, y + 70, main, "h3", "middle")
    if sub:
        text(x + w / 2, y + 86, sub.rstrip(")"), "small", "middle")
    ports = []
    for k in range(5):
        cx = x + 26 + k * 22
        add(f'<rect x="{cx - 6}" y="{y + 6}" width="12" height="12" rx="2" class="hubport"/>')
        add(f'<rect x="{cx - 5}" y="{y + 26}" width="10" height="16" rx="2" class="lever"/>')
        ports.append((cx, y + 6))
    return ports


def load(x, y, w, h, title, lines, amps):
    box(x, y, w, h, "load")
    text(x + 14, y + 24, title, "h3w")
    for k, l in enumerate(lines):
        text(x + 14, y + 44 + k * 16, l, "tw")
    add(f'<rect x="{x + w - 92}" y="{y + 10}" width="80" height="22" rx="11" class="amp"/>')
    text(x + w - 52, y + 25, amps, "ampt", "middle")
    return (x, y + h - 30), (x, y + h - 14)


def build():
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
        f'aria-label="MagicBand Reader power distribution">')
    add(f"<style>{CSS}</style>")
    add(f'<rect width="{W}" height="{H}" class="bg"/>')
    text(24, 36, "MagicBand Reader: power", "title")
    text(24, 58, "The same for every build. Each load gets its own wires from the hubs; every ground meets at the GND hub.", "sub")

    # ---------------------------------------------------------------- charger
    box(24, 96, 220, 92, "chg")
    text(40, 124, "USB-C charger", "h3w")
    text(40, 144, "20 W or more, e.g. a laptop", "tw")
    text(40, 160, "USB-C charger or Apple 20 W.", "tw")
    text(40, 176, "At 5 V it gives up to 3 A.", "tw")
    add('<path d="M244 142 C 268 142, 270 250, 300 250" class="cable"/>')
    add('<path d="M244 142 C 268 142, 270 470, 300 470" class="cable"/>')
    text(250, 300, "USB-C cable", "small", "start", 'transform="rotate(90 250 300)"')

    # ---------------------------------------------------------------- option B: HUSB238 (drawn lower)
    add('<g transform="translate(0 220)">')
    box(300, 180, 380, 200, "opt")
    text(316, 206, "Option B: Adafruit HUSB238 (5807)", "h3")
    text(316, 226, "Solder jumpers: can't change by accident.", "t")
    text(316, 262, "Keep 5V closed", "ok")
    text(316, 278, "(never cut it: that", "t")
    text(316, 294, "asks for up to 20 V)", "t")
    text(316, 322, "Cut 1A, leave 2A", "ok")
    text(316, 338, "open = 3 A", "t")
    add('<rect x="460" y="240" width="200" height="120" rx="8" class="pcbb"/>')
    add('<rect x="520" y="236" width="44" height="14" rx="4" class="usbc"/>')
    for i, (lab, st) in enumerate((("5V", "closed"), ("9V", "open"), ("12V", "open"), ("15V", "open"), ("18V", "open"))):
        pad(468 + i * 32, 268, lab, st)
    pad(468, 316, "1A", "cut")
    pad(500, 316, "2A", "open")
    add('<rect x="624" y="300" width="26" height="44" rx="3" class="term"/>')
    text(637, 316, "+", "termt", "middle")
    text(637, 338, "−", "termt", "middle")
    add('</g>')
    b_plus, b_minus = (650, 532), (650, 554)

    # ---------------------------------------------------------------- option A: CH224K PD trigger (drawn upper)
    add('<g transform="translate(0 -220)">')
    box(300, 400, 380, 200, "opt")
    text(316, 426, "Option A: USB-C PD trigger (CH224K)", "h3")
    text(316, 446, "5–20 V DIP switch: set, check, lock.", "t")
    text(316, 482, "Set 5 V from the", "ok")
    text(316, 498, "board's own table", "t")
    text(316, 526, "Cover the switch", "ok")
    text(316, 542, "with Kapton tape", "t")
    text(316, 558, "or hot glue", "t")
    add('<rect x="460" y="460" width="200" height="120" rx="8" class="pcbg"/>')
    add('<rect x="520" y="456" width="44" height="14" rx="4" class="usbc"/>')
    add('<rect x="478" y="492" width="96" height="38" rx="4" class="dip"/>')
    for k in range(3):
        add(f'<rect x="{488 + k * 28}" y="498" width="18" height="26" rx="2" class="dipsl"/>')
        add(f'<rect x="{491 + k * 28}" y="{512 if k else 501}" width="12" height="10" rx="2" class="dipkn"/>')
    add('<rect x="474" y="486" width="104" height="50" rx="4" class="tape"/>')
    text(526, 552, "tape over it", "smallw", "middle")
    add('<rect x="624" y="520" width="26" height="44" rx="3" class="term"/>')
    text(637, 536, "+", "termt", "middle")
    text(637, 558, "−", "termt", "middle")
    add('</g>')
    a_plus, a_minus = (650, 312), (650, 334)

    box(300, 618, 380, 76, "warn")
    text(316, 642, "Before connecting anything:", "h3")
    text(316, 662, "measure 4.75–5.25 V across + and −,", "t")
    text(316, 678, "unplug and re-plug, and measure again.", "t")

    # ---------------------------------------------------------------- hubs
    hp = hub(720, 230, "5 V hub (5-way lever connector)", "hubp", [])
    hg = hub(720, 470, "GND hub (5-way lever connector)", "hubg", [])
    # power board -> hubs (either option; B dashed)
    wire([a_plus, (700, a_plus[1]), (700, hp[0][1] - 18), (hp[0][0], hp[0][1] - 18), hp[0]], "p5 thick")
    wire([a_minus, (712, a_minus[1]), (712, hg[0][1] - 18), (hg[0][0], hg[0][1] - 18), hg[0]], "gnd thick")
    wire([b_plus, (700, b_plus[1]), (700, a_plus[1])], "p5 thick dash", ends=False)
    wire([b_minus, (712, b_minus[1]), (712, a_minus[1])], "gnd thick dash", ends=False)
    add(f'<circle cx="{b_plus[0]}" cy="{b_plus[1]}" r="3.6" class="end p5"/>')
    add(f'<circle cx="{b_minus[0]}" cy="{b_minus[1]}" r="3.6" class="end gnd"/>')
    text(490, 712, "Use one board or the other (B's wires dashed). 22 AWG stranded, ≤ 30 cm to the hubs.", "small", "middle")

    # ---------------------------------------------------------------- loads
    lx, lw = 940, 356
    loads = [
        ("ESP32-S3 board: 5V and GND pins", ["Own wires from the hubs (terminal base: soldered", "to its 5V/GND pads). Breadboard: fed from the",
                                             "rail via a21/a22. Unplug its 5 V before using USB."], "≤ 0.5 A", "22 AWG, ≤ 20 cm"),
        ("Breadboard rails or interface board", ["PN532 (5 V), 74AHCT125, I²C pull-ups.",
                                                 "Breadboard: L+24 / L−25. Interface board: L+25 / L−26."], "≤ 0.2 A", "22 AWG, ≤ 20 cm"),
        ("Amplifier (MAX98357A) VIN / GND", ["100 µF across VIN and GND within 5 cm of the", "amplifier, stripe to GND (breadboard: g51–g52)."], "≤ 0.65 A", "22 AWG, ≤ 30 cm"),
        ("LED ring or strip: 5V / GND pads", ["1000 µF 10 V soldered across its input pads,", "stripe to GND. Over 24 LEDs: firmware caps it."], "≤ 1.44 A", "22 AWG, ≤ 50 cm"),
    ]
    for k, (title, lines, amps, awg) in enumerate(loads):
        y = 96 + k * 150
        (px, py), (gx, gy) = load(lx, y, lw, 118, title, lines, amps)
        add(f'<rect x="{lx - 6}" y="{py - 5}" width="10" height="10" rx="2" class="pinr"/>')
        add(f'<rect x="{lx - 6}" y="{gy - 5}" width="10" height="10" rx="2" class="pinb"/>')
        text(lx + 12, py + 4, "5V", "pinl")
        text(lx + 12, gy + 4, "GND", "pinl")
        thick = " thick" if k == 3 else ""
        sp, sg = hp[k + 1], hg[k + 1]
        lane_p = 880 + k * 10
        lane_g = 875 + k * 10 + 5
        wire([sp, (sp[0], 214 - k * 8), (lane_p, 214 - k * 8), (lane_p, py), (lx - 1, py)], "p5" + thick)
        wire([sg, (sg[0], 454 - k * 8), (lane_g + 2, 454 - k * 8), (lane_g + 2, gy), (lx - 1, gy)], "gnd" + thick)
        text(lx + lw - 10, y + 112, awg, "small", "end")
        if k == 0:
            add(f'<circle cx="{lx - 24}" cy="{py - 16}" r="10" class="mark"/>')
            text(lx - 24, py - 12, "!", "markno", "middle")

    # ---------------------------------------------------------------- footer
    box(24, 730, 1272, 112, "foot")
    text(40, 756, "Worst case: 0.5 + 0.2 + 0.65 + 1.44 ≈ 2.75 A (every maximum at once), within the charger's 3 A. Normal use: about 0.3 A idle, 1.4 A during a welcome.", "t")
    text(40, 780, "Lever connectors: strip 11 mm, twist the strands, push in fully, close the lever and tug. Don't tin wires going into lever connectors or screw terminals.", "t")
    text(40, 804, "Colours: red for 5 V, black for ground, everywhere. Keep each 5 V wire next to its ground wire.", "t")
    text(40, 828, "The ESP32's USB and the 5 V supply must never power it together: pull the ESP32's 5 V wire (marked !) before plugging USB into the ESP32.", "t")

    add("</svg>")
    return "\n".join(out)


CSS = """
.bg{fill:#ffffff} .title{font:700 22px Inter,system-ui,sans-serif;fill:#1d1b16} .sub{font:500 13px Inter,system-ui,sans-serif;fill:#5c5a52}
.t{font:500 12px Inter,system-ui,sans-serif;fill:#2b2a26} .tw{font:500 11.5px Inter,system-ui,sans-serif;fill:#e6edf8}
.small{font:600 11px Inter,system-ui,sans-serif;fill:#5c5a52} .smallw{font:600 10.5px Inter,system-ui,sans-serif;fill:#e6edf8} .h3{font:700 13.5px Inter,system-ui,sans-serif;fill:#1d1b16}
.h3w{font:700 13.5px Inter,system-ui,sans-serif;fill:#ffffff} .ok{font:700 12px Inter,system-ui,sans-serif;fill:#1b7a3a}
.jl{font:700 10px ui-monospace,Menlo,Consolas,monospace;fill:#ffffff}
.card{fill:#faf9f5;stroke:#d9d6ca} .opt{fill:#faf9f5;stroke:#cfccbf} .warn{fill:#fff6e0;stroke:#f0d48a}
.foot{fill:#faf9f5;stroke:#d9d6ca} .chg{fill:#3c3c44;stroke:#22222a} .load{fill:#1d4f8f;stroke:#123562}
.pcbb{fill:#1d3f86} .pcbg{fill:#1f3d2f} .usbc{fill:#9ca3ad} .padj{fill:#e3c167;stroke:#9d7f2c}
.bridge{fill:#e3c167} .cut{stroke:#d62f2f;stroke-width:3}
.term{fill:#2f9e5b;stroke:#1d6b3c} .termt{font:700 13px ui-monospace,Menlo,Consolas,monospace;fill:#ffffff}
.dip{fill:#c0392b} .dipsl{fill:#f2f2f2} .dipkn{fill:#2b2b2b} .tape{fill:#e9a23b;opacity:.35;stroke:#c8811a;stroke-dasharray:4 3}
.cable{fill:none;stroke:#5c5c66;stroke-width:6;stroke-linecap:round}
.hub{stroke-width:1.5} .hubp{fill:#fbe3e3;stroke:#d62f2f} .hubg{fill:#e3e3e8;stroke:#2c2c2c}
.hubport{fill:#6b6b6b} .lever{fill:#f08a24}
.amp{fill:#ffffff} .ampt{font:700 11.5px Inter,system-ui,sans-serif;fill:#1d4f8f}
.pinr{fill:#d62f2f} .pinb{fill:#222222} .pinl{font:700 10.5px ui-monospace,Menlo,Consolas,monospace;fill:#ffffff}
.mark{fill:#b42318} .markno{font:800 13px Inter,system-ui,sans-serif;fill:#ffffff}
.w{fill:none;stroke-width:3.4;stroke-linejoin:round;stroke-linecap:round} .w.thick{stroke-width:6} .w.dash{stroke-dasharray:10 7}
.end{stroke:none}
.p5{stroke:#d62f2f;fill:#d62f2f} .gnd{stroke:#222222;fill:#222222}
polyline.w{fill:none}
"""

if __name__ == "__main__":
    print(build())
