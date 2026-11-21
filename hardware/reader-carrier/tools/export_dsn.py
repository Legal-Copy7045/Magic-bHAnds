#!/usr/bin/env python3
"""Export a Specctra DSN for Freerouting, without the ground pours.

With the pours in, KiCad exports GND as a plane and Freerouting leaves ground
unrouted. Without them, every ground pad gets a real track; the pours are
added back on top (import_ses.py refills them). The power nets get their own
net classes (netlist.POWER_NETS) so the router uses wide tracks for them.

Usage: export_dsn.py board.kicad_pcb board.dsn
"""

import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from netlist import POWER_NETS  # noqa: E402

board = pcbnew.LoadBoard(sys.argv[1])
classes = board.GetDesignSettings().m_NetSettings.m_NetClasses
for net, width in POWER_NETS.items():
    name = "P_" + net.replace("+", "").replace("_", "")
    nc = pcbnew.NETCLASS(name)
    nc.SetTrackWidth(pcbnew.FromMM(width))
    nc.SetClearance(pcbnew.FromMM(0.25))
    nc.SetViaDiameter(pcbnew.FromMM(0.8))
    nc.SetViaDrill(pcbnew.FromMM(0.4))
    classes[name] = nc
    board.FindNet(net).SetNetClass(nc)
for zone in list(board.Zones()):
    if not zone.GetIsRuleArea():
        board.Remove(zone)
print("exported" if pcbnew.ExportSpecctraDSN(board, sys.argv[2]) else "export failed")
