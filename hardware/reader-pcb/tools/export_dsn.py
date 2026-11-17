#!/usr/bin/env python3
"""Export a Specctra DSN for Freerouting, without the ground pours.

With the pours in, KiCad exports GND as a plane and Freerouting leaves ground
unrouted. Without them, every ground pad gets a real track; the pours are
added back on top (import_ses.py refills them).

Usage: export_dsn.py board.kicad_pcb board.dsn
"""

import sys

import pcbnew

board = pcbnew.LoadBoard(sys.argv[1])
for zone in list(board.Zones()):
    if not zone.GetIsRuleArea():
        board.Remove(zone)
print("exported" if pcbnew.ExportSpecctraDSN(board, sys.argv[2]) else "export failed")
