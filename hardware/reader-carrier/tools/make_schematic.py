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


LOCAL = Path(__file__).parent / "lib"


def raw_symbol(lib: str, name: str) -> str:
    path = LOCAL / f"{lib}.kicad_sym" if (LOCAL / f"{lib}.kicad_sym").exists() else SYMDIR / f"{lib}.kicad_sym"
    text = _lib_cache.setdefault(lib, path.read_text())
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


# Automatic placement on an A3 sheet: parts in rows, big symbols given more room.
def layout() -> dict[str, tuple[float, float]]:
    pos, x, y, row_h = {}, 25.4, 30.48, 0.0
    for part in PARTS:
        big = part["sym"].split(":")[1] in ("USB_C_Receptacle_USB2.0_16P", "Conn_01x22", "CH224K", "SRV05-4")
        w, h = (55.88, 66.04) if part["sym"].endswith("Conn_01x22") else (50.8, 40.64) if big else (30.48, 20.32)
        if x + w > 400:
            x, y, row_h = 25.4, y + row_h, 0.0
        pos[part["ref"]] = (snap(x + w / 2), snap(y + h / 2))
        x += w
        row_h = max(row_h, h)
    return pos


LAYOUT: dict[str, tuple[float, float]] = {}


def main(out: Path) -> None:
    LAYOUT.update(layout())
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
        body.append(f'    (instances (project "magicband-carrier" (path "/{root}" (reference "{ref}") (unit 1))))')
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
        x, y = 30.48 + i * 15.24, 270.0
        ref = f"#FLG0{i + 1}"
        body.append(f'  (symbol (lib_id "power:PWR_FLAG") (at {x} {y} 0) (unit 1)')
        body.append("    (in_bom no) (on_board no) (dnp no)")
        body.append(f'    (uuid {uid("sym", ref)})')
        body.append(f'    (property "Reference" "{ref}" (at {x} {y - 3} 0) (effects (font (size 1.27 1.27)) hide))')
        body.append(f'    (property "Value" "PWR_FLAG" (at {x} {y - 3.81} 0) (effects (font (size 1.27 1.27))))')
        body.append(f'    (property "Footprint" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))')
        body.append(f'    (property "Datasheet" "" (at {x} {y} 0) (effects (font (size 1.27 1.27)) hide))')
        body.append(f'    (pin "1" (uuid {uid("pin", ref)}))')
        body.append(f'    (instances (project "magicband-carrier" (path "/{root}" (reference "{ref}") (unit 1))))')
        body.append("  )")
        body.append(
            f'  (label "{net}" (at {x} {y} 270) (fields_autoplaced) (effects (font (size 1.0 1.0)) (justify right))'
            f' (uuid {uid("flaglabel", net)}))'
        )

    notes = [
        "MagicBand Reader carrier board - ESP32-S3-DevKitC-1 (N16R8) in sockets",
        "GPIO: I2S LRC 5, BCLK 6, DIN 7 | I2C SDA 8, SCL 9 | LEDs 10 | USB-C power fixed at 5 V (CH224K CFG1 high)",
        "Generated by hardware/reader-carrier/tools/make_schematic.py - edit netlist.py and regenerate",
    ]
    for i, text in enumerate(notes):
        body.append(
            f'  (text "{text}" (at 25.4 {280.0 + i * 3.81} 0)'
            f' (effects (font (size 1.778 1.778)) (justify left bottom)) (uuid {uid("note", str(i))}))'
        )

    out.write_text(
        "(kicad_sch (version 20230121) (generator eeschema)\n"
        f"  (uuid {root})\n"
        '  (paper "A3")\n'
        "  (title_block (title \"MagicBand Reader carrier\") (company \"Magic bHAnds\") (rev \"1.0\"))\n"
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
