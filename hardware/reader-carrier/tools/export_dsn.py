#!/usr/bin/env python3
"""Export a Specctra DSN for Freerouting, without the ground pours.

With the pours in, KiCad exports GND as a plane and Freerouting leaves ground
unrouted. Without them, every ground pad gets a real track; the pours are
added back on top (import_ses.py refills them). The power nets get their own
net classes (netlist.POWER_NETS) so the router uses wide tracks for them.

Usage: export_dsn.py board.kicad_pcb board.dsn
"""

import re
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from netlist import POWER_NETS, POWER_VIA_DEFAULT, POWER_VIAS  # noqa: E402

board = pcbnew.LoadBoard(sys.argv[1])
classes = board.GetDesignSettings().m_NetSettings.m_NetClasses
for net, width in POWER_NETS.items():
    name = "P_" + net.replace("+", "").replace("_", "")
    nc = pcbnew.NETCLASS(name)
    nc.SetTrackWidth(pcbnew.FromMM(width))
    nc.SetClearance(pcbnew.FromMM(0.25))
    via, drill = POWER_VIAS.get(net, POWER_VIA_DEFAULT)
    nc.SetViaDiameter(pcbnew.FromMM(via))
    nc.SetViaDrill(pcbnew.FromMM(drill))
    classes[name] = nc
    board.FindNet(net).SetNetClass(nc)
for zone in list(board.Zones()):
    if not zone.GetIsRuleArea():
        board.Remove(zone)
if not pcbnew.ExportSpecctraDSN(board, sys.argv[2]):
    raise SystemExit("export failed")

# KiCad 7 writes the power classes' rules but still lists every net in
# kicad_default, so Freerouting routed power at 0.2 mm. Move each power net
# out of the default class's net list and into its own class.
dsn = Path(sys.argv[2]).read_text()
m = re.search(r'\(class kicad_default ""(.*?)\(circuit', dsn, re.S)
members = m.group(1).split()
for net in POWER_NETS:
    members.remove(net)
    name = "P_" + net.replace("+", "").replace("_", "")
    dsn, n = re.subn(r"\(class %s\s*\n" % re.escape(name), f"(class {name} {net}\n", dsn)
    if n != 1:
        raise SystemExit(f"class {name} not found in the DSN")
dsn = dsn[: m.start(1)] + " " + " ".join(members) + "\n      " + dsn[m.end(1):]
Path(sys.argv[2]).write_text(dsn)
print("exported, power nets in their own classes:", ", ".join(POWER_NETS))
