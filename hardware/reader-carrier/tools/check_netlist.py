#!/usr/bin/env python3
"""Fail unless every pin in the schematic is on the same net on the board, and vice versa.

KiCad 7's headless DRC doesn't compare the board with the schematic, so this does: it reads
the netlist kicad-cli exports from the .kicad_sch and checks each pad of the .kicad_pcb.

Usage: check_netlist.py board.kicad_pcb schematic.net
"""
import re
import sys

import pcbnew

text = open(sys.argv[2]).read()
sch = {}
for m in re.finditer(r'\(net \(code "?\d+"?\) \(name "([^"]*)"\)(.*?)\)\s*(?=\(net |\)\s*\)\s*$)', text, re.S):
    name = m.group(1).lstrip("/")
    for ref, pin in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"', m.group(2)):
        sch[(ref, pin)] = "" if name.startswith("unconnected-") else name
board = pcbnew.LoadBoard(sys.argv[1])
pcb = {}
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetNumber():
            pcb.setdefault((fp.GetReference(), pad.GetNumber()), set()).add(pad.GetNetname())
bad = [f"{r}.{p}: schematic {n!r}, board {sorted(pcb.get((r, p), ['missing']))}"
       for (r, p), n in sorted(sch.items()) if pcb.get((r, p)) != {n}]
bad += [f"{r}.{p}: on the board ({sorted(n)}) but not in the schematic"
        for (r, p), n in sorted(pcb.items()) if (r, p) not in sch and n != {""}]
print(f"schematic vs board: {len(sch)} pins, {len(bad)} differences")
for line in bad:
    print("  " + line)
sys.exit(1 if bad or not sch else 0)
