#!/usr/bin/env python3
"""Write the KiCad 7 schematic from netlist.py.

Every pin gets a net label (or a no-connect flag), so the schematic is
connected by name rather than by drawn wires. Symbols come from KiCad's stock
libraries (/usr/share/kicad/symbols) and are embedded in the file.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from netlist import PARTS, PWR_FLAGS  # noqa: E402

SYMDIR = Path("/usr/share/kicad/symbols")
NAMESPACE = uuid.UUID("6f1d7c2e-3c55-4b8e-9d0e-6b5a7a1f0c11")


def uid(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "/".join(parts)))


def block(text: str, start: int) -> str:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("unbalanced")


_lib_cache: dict[str, str] = {}


def raw_symbol(lib: str, name: str) -> str:
    text = _lib_cache.setdefault(lib, (SYMDIR / f"{lib}.kicad_sym").read_text())
    m = re.search(r'\(symbol "%s"' % re.escape(name), text)
    if not m:
        raise KeyError(f"{lib}:{name}")
    return block(text, m.start())


def flat_symbol(lib: str, name: str) -> str:
    """The symbol with any `extends` resolved, named lib:name."""
    sym = raw_symbol(lib, name)
    m = re.search(r'\(extends "([^"]+)"\)', sym)
    if m:
        parent = flat_symbol(lib, m.group(1))
        parent_name = m.group(1)
        # Child's properties replace the parent's.
        child_props = re.findall(r'\(property "[^"]+".*?\n\s*\)', sym, re.S)
        body = re.sub(r'\(property "[^"]+".*?\n\s*\)\s*', "", parent, flags=re.S)
        body = body.replace(f'(symbol "{lib}:{parent_name}"', f'(symbol "{name}"', 1)
        body = body.replace(f'(symbol "{parent_name}_', f'(symbol "{name}_')
        # Re-insert the child's properties after the header line.
        head_end = body.index("\n")
        sym = body[: head_end + 1] + "\n".join("    " + p for p in child_props) + "\n" + body[head_end + 1 :]
    return re.sub(r'^\(symbol "%s"' % re.escape(name), f'(symbol "{lib}:{name}"', sym, count=1)


def pins_of(flat: str) -> dict[str, tuple[float, float, int, str]]:
    pins = {}
    for m in re.finditer(r"\(pin (\w+) \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\).*?\(number \"([^\"]*)\"", flat, re.S):
        etype, x, y, rot, num = m.groups()
        pins.setdefault(num, (float(x), float(y), int(rot), etype))
    return pins


def snap(v: float) -> float:
    return round(round(v / 1.27) * 1.27, 2)


# Placement on an A4 sheet, in mm (top-left origin).
LAYOUT = {
    "U1": (88.9, 88.9),
    "C1": (40.64, 50.8), "C2": (50.8, 50.8), "R1": (40.64, 66.04), "C3": (50.8, 66.04), "SW1": (40.64, 81.28),
    "R2": (40.64, 99.06), "SW2": (40.64, 114.3),
    "J1": (154.94, 60.96), "R3": (185.42, 45.72), "R4": (195.58, 45.72), "U5": (190.5, 76.2),
    "U2": (177.8, 111.76), "C4": (165.1, 124.46), "C5": (190.5, 124.46),
    "U3": (139.7, 152.4), "R5": (116.84, 147.32), "C6": (162.56, 160.02), "C7": (172.72, 160.02),
    "U4": (68.58, 152.4), "C8": (86.36, 162.56), "R6": (91.44, 144.78), "C9": (101.6, 162.56),
    "R7": (40.64, 134.62), "R8": (50.8, 134.62),
    "J2": (220.98, 99.06), "J3": (220.98, 116.84), "J4": (220.98, 132.08),
}


def main(out: Path) -> None:
    root = uid("root")
    lib_symbols: dict[str, str] = {}
    body: list[str] = []
    for part in PARTS:
        lib, name = part["sym"].split(":")
        lib_id = f"{lib}:{name}"
        if lib_id not in lib_symbols:
            lib_symbols[lib_id] = flat_symbol(lib, name)
        flat = lib_symbols[lib_id]
        pins = pins_of(flat)
        x, y = LAYOUT[part["ref"]]
        ref = part["ref"]
        unknown = set(part["pins"]) - set(pins)
        if unknown:
            raise SystemExit(f"{ref}: pins {unknown} not in symbol {lib_id}")
        props = [
            ("Reference", ref, 0, -2.54 if ref[0] in "RC" else -5.08, False),
            ("Value", part["value"], 0, 2.54 if ref[0] in "RC" else 5.08, False),
            ("Footprint", part["fp"], 0, 0, True),
            ("Datasheet", "", 0, 0, True),
            ("MPN", part["mpn"], 0, 0, True),
            ("LCSC", part["lcsc"], 0, 0, True),
        ]
        body.append(f'  (symbol (lib_id "{lib_id}") (at {x} {y} 0) (unit 1)')
        body.append("    (in_bom yes) (on_board yes) (dnp no)")
        body.append(f'    (uuid {uid("sym", ref)})')
        for key, val, dx, dy, hidden in props:
            body.append(
                f'    (property "{key}" "{val}" (at {x + dx} {y + dy} 0)'
                f' (effects (font (size 1.27 1.27)){" hide" if hidden else ""}))'
            )
        for num in pins:
            body.append(f'    (pin "{num}" (uuid {uid("pin", ref, num)}))')
        body.append(f'    (instances (project "magicband-reader" (path "/{root}" (reference "{ref}") (unit 1))))')
        body.append("  )")
        # Labels / no-connects at each pin end.
        for num, (px, py, rot, etype) in pins.items():
            ex, ey = round(x + px, 2), round(y - py, 2)
            net = part["pins"].get(num)
            if net is None:
                if etype != "no_connect":
                    body.append(f'  (no_connect (at {ex} {ey}) (uuid {uid("nc", ref, num)}))')
                continue
            angle = (rot + 180) % 360
            justify = {0: "left", 180: "right", 90: "left", 270: "right"}[angle]
            body.append(
                f'  (label "{net}" (at {ex} {ey} {angle}) (fields_autoplaced)'
                f' (effects (font (size 1.0 1.0)) (justify {justify}))'
                f' (uuid {uid("label", ref, num)}))'
            )

    # PWR_FLAGs on nets fed only through passive pins.
    flag = flat_symbol("power", "PWR_FLAG")
    lib_symbols["power:PWR_FLAG"] = flag
    for i, net in enumerate(PWR_FLAGS):
        x, y = 30.48 + i * 15.24, 172.72
        ref = f"#FLG0{i + 1}"
        body.append(f'  (symbol (lib_id "power:PWR_FLAG") (at {x} {y} 0) (unit 1)')
        body.append("    (in_bom no) (on_board no) (dnp no)")
        body.append(f'    (uuid {uid("sym", ref)})')
        body.append(f'    (property "Reference" "{ref}" (at {x} {y - 3} 0) (effects (font (size 1.27 1.27)) hide))')
        body.append(f'    (property "Value" "PWR_FLAG" (at {x} {y - 3.81} 0) (effects (font (size 1.27 1.27))))')
        body.append(f'    (property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))')
        body.append(f'    (property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))')
        body.append(f'    (pin "1" (uuid {uid("pin", ref)}))')
        body.append(f'    (instances (project "magicband-reader" (path "/{root}" (reference "{ref}") (unit 1))))')
        body.append("  )")
        body.append(
            f'  (label "{net}" (at {x} {y} 270) (fields_autoplaced) (effects (font (size 1.0 1.0)) (justify right))'
            f' (uuid {uid("flaglabel", net)}))'
        )

    notes = [
        "MagicBand Reader PCB - ESP32-S3-WROOM-1-N16R8",
        "GPIO: I2S LRCLK 5, BCLK 6, DOUT 7 | I2C SDA 8, SCL 9 | LEDs 10 | USB D- 19, D+ 20",
        "Generated by hardware/reader-pcb/tools/make_schematic.py - edit netlist.py and regenerate",
    ]
    for i, text in enumerate(notes):
        body.append(
            f'  (text "{text}" (at 25.4 {190.5 + i * 3.81} 0)'
            f' (effects (font (size 1.778 1.778)) (justify left bottom)) (uuid {uid("note", str(i))}))'
        )

    out.write_text(
        "(kicad_sch (version 20230121) (generator eeschema)\n"
        f"  (uuid {root})\n"
        '  (paper "A4")\n'
        "  (title_block (title \"MagicBand Reader\") (company \"Magic bHAnds\") (rev \"1.0\"))\n"
        "  (lib_symbols\n"
        + "\n".join("    " + s.replace("\n", "\n    ") for s in lib_symbols.values())
        + "\n  )\n"
        + "\n".join(body)
        + "\n  (sheet_instances (path \"/\" (page \"1\")))\n"
        ")\n"
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
