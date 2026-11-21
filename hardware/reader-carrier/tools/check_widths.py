#!/usr/bin/env python3
"""Fail if any routed track on a power net is narrower than netlist.POWER_NETS says.

(Short necks into pads are allowed; see below.)

DRC only enforces the board-wide minimum (0.15 mm), so a power net routed thin
would pass it. Run after routing (build.sh does).
"""

import collections
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from netlist import POWER_NETS  # noqa: E402

board = pcbnew.LoadBoard(sys.argv[1])
# A short neck (up to 1.5 mm) where a track enters a pad is allowed: Freerouting
# narrows the last bit to fit a small part's pin, and the USB-C pins need
# pad-width stubs. Anywhere else, a power track must be full width.
pads = collections.defaultdict(list)
for fp in board.GetFootprints():
    for pad in fp.Pads():
        pads[pad.GetNetname()].append(pad)


def neck(t) -> bool:
    if pcbnew.ToMM(t.GetLength()) > (2.5 if t.IsLocked() else 1.5):
        return False
    return any(pad.HitTest(t.GetStart()) or pad.HitTest(t.GetEnd()) for pad in pads[t.GetNetname()])


widths = collections.defaultdict(list)
for t in board.GetTracks():
    if t.GetClass() == "PCB_TRACK" and not neck(t):
        widths[t.GetNetname()].append(pcbnew.ToMM(t.GetWidth()))
bad = False
for net, want in POWER_NETS.items():
    got = widths.get(net, [])
    thin = [w for w in got if w < want - 1e-6]
    print(f"{net:7} want >= {want} mm: {len(got)} segments, narrowest {min(got) if got else '-'} mm"
          + (f"  <-- {len(thin)} too narrow" if thin else ""))
    bad |= bool(thin)
sys.exit("power tracks narrower than specified" if bad else 0)
