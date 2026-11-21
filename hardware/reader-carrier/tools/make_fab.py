#!/usr/bin/env python3
"""JLCPCB assembly files (BOM + component placement) from the .kicad_pcb.

Run after routing too; placement doesn't change. Positions are in the same frame as
the Gerbers and drill files (KiCad's page coordinates, y up), so the placement lines up
with the copper without any offset. Rotations are KiCad's: JLCPCB sometimes needs a part
rotated in their preview before ordering.
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from netlist import PARTS  # noqa: E402



def main(pcb: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    board = pcbnew.LoadBoard(str(pcb))
    info = {p["ref"]: p for p in PARTS}
    groups = defaultdict(list)
    with open(out / "cpl.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
            ref = fp.GetReference()
            if info[ref].get("asm") != "smt":
                continue  # hand-soldered or not a part
            pos = fp.GetPosition()
            x = pcbnew.ToMM(pos.x)  # same origin as the Gerbers (absolute), which flip y
            y = -pcbnew.ToMM(pos.y)
            w.writerow([ref, f"{x:.3f}mm", f"{y:.3f}mm", "Top", f"{fp.GetOrientationDegrees() % 360:.0f}"])
            p = info[ref]
            groups[(p["value"], p["fp"].split(":")[1], p["mpn"], p["lcsc"])].append(ref)
    with open(out / "bom.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "MPN", "LCSC Part #"])
        for (value, fp, mpn, lcsc), refs in sorted(groups.items(), key=lambda g: g[1][0]):
            w.writerow([value, ",".join(sorted(refs)), fp, mpn, lcsc])
    print(f"wrote {out}/bom.csv and {out}/cpl.csv")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
