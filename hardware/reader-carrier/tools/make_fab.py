#!/usr/bin/env python3
"""JLCPCB assembly files (BOM + component placement) from the .kicad_pcb.

Run after routing too; placement doesn't change. Positions are in the same frame as
the Gerbers and drill files (KiCad's page coordinates, y up), so the placement lines up
with the copper without any offset.

Two placement files:
- cpl.csv, for JLCPCB: KiCad's angle plus JLC_ROTATION, because JLCPCB's own models of
  some parts sit at a different angle from KiCad's footprints. The corrections were read
  off JLCPCB's placement preview (Nov 2026): pin 1 on the silkscreen triangle.
- cpl-kicad.csv, for other assemblers (PCBWay and so on): KiCad's angles as they are.

Two BOMs: bom.csv in JLCPCB's columns, and bom-pcbway.csv in PCBWay's (quantity per board,
manufacturer, package, part type, notes).
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from netlist import PARTS  # noqa: E402



# Degrees added to KiCad's angle (counter-clockwise) for JLCPCB's models. U1: its model's
# leads run the other way and pin 1 sits a quarter-turn round; U2, U3: SOT-23 models are
# half a turn from KiCad's footprints.
JLC_ROTATION = {"U1": 270, "U2": 180, "U3": 180}

# Manufacturer of each MPN, from its LCSC listing (Nov 2026), for assemblers that ask for it.
MAKER = {
    "CL05A105KA5NQNC": "Samsung Electro-Mechanics", "CL21A106KAYNNNE": "Samsung Electro-Mechanics",
    "CL05B104KO5NNNC": "Samsung Electro-Mechanics", "KT-0603G": "Hubei KENTO Elec",
    "SMAJ5.0A": "MDD (Microdiode Semiconductor)", "SS34": "MDD (Microdiode Semiconductor)",
    "SMD1812P350TF/16": "RUILON (Shenzhen Ruilongyuan Elec)", "TYPE-C-31-M-12": "Korean Hroparts Elec (HRO)",
    "CH224A": "WCH (Jiangsu Qin Heng)", "SN74AHCT1G125DBVR": "Texas Instruments", "SRV05-4.TCT": "Semtech",
}
# The package as an assembler names it, from the KiCad footprint.
PACKAGE = {"C_0402_1005Metric": "0402", "R_0402_1005Metric": "0402", "C_0805_2012Metric": "0805",
           "LED_0603_1608Metric": "0603", "D_SMA": "SMA (DO-214AC)", "Fuse_1812_4532Metric": "1812",
           "SOT-23-5": "SOT-23-5", "SOT-23-6": "SOT-23-6", "CH224K_ESSOP-10": "ESSOP-10 (exposed pad)",
           "USB_C_Receptacle_HRO_TYPE-C-31-M-12_EdgeTrim": "USB-C 16-pin SMD + 4 through-hole shell tabs"}
NOTES = {
    "U1": "No substitute. Pin 1 at the silkscreen triangle. Exposed pad is GND, must be soldered",
    "U2": "Pin 1 at the silkscreen triangle", "U3": "Pin 1 at the silkscreen triangle",
    "D1": "Polarised: cathode to pad 1", "D2": "Unidirectional TVS: cathode (band) to pad 1",
    "D3": "Polarised: cathode (band) to pad 1", "F1": "No substitute: must be the 16 V version (/16)",
    "J1": "No substitute. Overhangs the board edge 0.5 mm by design; solder the 4 shell tabs",
}


def main(pcb: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    board = pcbnew.LoadBoard(str(pcb))
    info = {p["ref"]: p for p in PARTS}
    groups = defaultdict(list)
    rows = []
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if info[ref].get("asm") != "smt":
            continue  # hand-soldered or not a part
        pos = fp.GetPosition()
        x = pcbnew.ToMM(pos.x)  # same origin as the Gerbers (absolute), which flip y
        y = -pcbnew.ToMM(pos.y)
        rows.append((ref, x, y, fp.GetOrientationDegrees()))
        p = info[ref]
        groups[(p["value"], p["fp"].split(":")[1], p["mpn"], p["lcsc"])].append(ref)
    for name, extra in (("cpl.csv", JLC_ROTATION), ("cpl-kicad.csv", {})):
        with open(out / name, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
            for ref, x, y, rot in rows:
                w.writerow([ref, f"{x:.3f}mm", f"{y:.3f}mm", "Top", f"{(rot + extra.get(ref, 0)) % 360:.0f}"])
    with open(out / "bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "MPN", "LCSC Part #"])
        for (value, fp, mpn, lcsc), refs in sorted(groups.items(), key=lambda g: g[1][0]):
            w.writerow([value, ",".join(sorted(refs)), fp, mpn, lcsc])
    with open(out / "bom-pcbway.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Item #", "Designator", "Qty", "Manufacturer", "Mfg Part #", "Description / Value",
                    "Package / Footprint", "Type", "LCSC Part #", "Notes"])
        for i, ((value, fp, mpn, lcsc), refs) in enumerate(sorted(groups.items(), key=lambda g: g[1][0]), 1):
            refs = sorted(refs)
            maker = MAKER.get(mpn) or ("UNI-ROYAL (Uniroyal Elec)" if mpn.startswith("0402WGF") else "")
            note = "; ".join(NOTES[r] for r in refs if r in NOTES)
            w.writerow([i, ",".join(refs), len(refs), maker, mpn, value, PACKAGE.get(fp, fp), "SMD", lcsc, note])
    print(f"wrote {out}/bom.csv, bom-pcbway.csv, cpl.csv (JLCPCB) and cpl-kicad.csv")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
