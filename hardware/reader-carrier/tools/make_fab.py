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
    print(f"wrote {out}/bom.csv, {out}/cpl.csv (JLCPCB) and {out}/cpl-kicad.csv")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
