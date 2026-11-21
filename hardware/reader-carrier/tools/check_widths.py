#!/usr/bin/env python3
"""Fail if any routed track on a power net is narrower than netlist.POWER_NETS says.

(Short necks into pads narrower than the track are allowed; see below. Each one is listed.)

DRC only enforces the board-wide minimum (0.15 mm), so a power net routed thin
would pass it. Run after routing (build.sh does).
"""

import collections
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from netlist import POWER_LOADS, POWER_NETS, POWER_VIAS  # noqa: E402

board = pcbnew.LoadBoard(sys.argv[1])
# A short neck where a track enters a pad is allowed: Freerouting narrows the last
# bit to fit a small part's pin (sometimes in two short segments), and the USB-C
# pins need pad-width stubs. A neck is a run of connected narrow segments, at most
# 3 mm long in all, no narrower than the pad, that ends on a pad of the same net. Anywhere else, a power
# track must be full width.
NECK_MM = 3.0
pads = collections.defaultdict(list)
for fp in board.GetFootprints():
    for pad in fp.Pads():
        pads[pad.GetNetname()].append((fp.GetReference(), pad))

tracks = collections.defaultdict(list)
for t in board.GetTracks():
    if t.GetClass() == "PCB_TRACK":
        tracks[t.GetNetname()].append(t)


def runs(thin):
    """Group narrow segments that share an end point."""
    left, out = list(thin), []
    while left:
        run = [left.pop()]
        ends = {(p.x, p.y) for p in (run[0].GetStart(), run[0].GetEnd())}
        grew = True
        while grew:
            grew = False
            for t in list(left):
                te = {(p.x, p.y) for p in (t.GetStart(), t.GetEnd())}
                if te & ends:
                    run.append(t)
                    ends |= te
                    left.remove(t)
                    grew = True
        out.append(run)
    return out


def neck_pad(run, net, want):
    """The pad a neck leads into, if the run is a neck: at most NECK_MM long and ending on a
    same-net pad that is itself narrower than the full track (so the track can't enter it at
    full width). A narrow run near a big pad, or anywhere else, isn't a neck."""
    if sum(pcbnew.ToMM(t.GetLength()) for t in run) > NECK_MM:
        return None
    for t in run:
        for p in (t.GetStart(), t.GetEnd()):
            for ref, pad in pads[net]:
                size = pad.GetSize()
                narrow = pcbnew.ToMM(min(size.x, size.y))
                # ...and the neck must be at least as wide as that pad (or 0.5 mm): it carries the same current
                if pad.HitTest(p) and narrow < want - 1e-6 and \
                        min(pcbnew.ToMM(s.GetWidth()) for s in run) >= min(narrow, 0.5) - 0.01:
                    return f"{ref} pad {pad.GetNumber()} ({pcbnew.ToMM(min(size.x, size.y)):.2f} mm wide)"
    return None


bad = False
for net, want in POWER_NETS.items():
    got = tracks.get(net, [])
    thin = [t for t in got if pcbnew.ToMM(t.GetWidth()) < want - 1e-6]
    necks = [(r, neck_pad(r, net, want)) for r in runs(thin)]
    necks = [(r, pad) for r, pad in necks if pad is not None]
    allowed = {id(t) for r, _ in necks for t in r}
    wrong = [t for t in thin if id(t) not in allowed]
    full = [pcbnew.ToMM(t.GetWidth()) for t in got if id(t) not in allowed]
    print(f"{net:7} want >= {want} mm: {len(full)} segments, narrowest {min(full) if full else '-'} mm,"
          f" {len(necks)} pad necks" + (f"  <-- {len(wrong)} too narrow" if wrong else ""))
    for r, pad in necks:
        print(f"          neck into {pad}:"
              f" {sum(pcbnew.ToMM(t.GetLength()) for t in r):.2f} mm at"
              f" {min(pcbnew.ToMM(t.GetWidth()) for t in r):.2f} mm")
    for t in wrong:
        print(f"          too narrow: {pcbnew.ToMM(t.GetWidth()):.2f} mm, {pcbnew.ToMM(t.GetLength()):.2f} mm long,"
              f" at ({pcbnew.ToMM(t.GetStart().x) - 100:.1f}, {pcbnew.ToMM(t.GetStart().y) - 80:.1f})")
    bad |= bool(wrong)
# Vias on the nets that carry the whole load must be the big ones (netlist.POWER_VIAS), so the
# barrel isn't the thinnest copper in the path.
for net, (size, drill) in POWER_VIAS.items():
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == net]
    small = [v for v in vias if pcbnew.ToMM(v.GetDrillValue()) < drill - 1e-6 or pcbnew.ToMM(v.GetWidth()) < size - 1e-6]
    print(f"{net:7} vias: {len(vias)}, want >= {size}/{drill} mm" + (f"  <-- {len(small)} too small" if small else ""))
    bad |= bool(small)


def reachable(net, start, min_mm):
    """Pads of `net` joined to pad `start` by tracks at least `min_mm` wide, vias and pads."""
    items = [("pad", f"{fp.GetReference()}.{p.GetNumber()}", p)
             for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == net]
    for t in board.GetTracks():
        if t.GetNetname() != net:
            continue
        if t.GetClass() == "PCB_VIA":
            items.append(("via", None, t))
        elif pcbnew.ToMM(t.GetWidth()) >= min_mm - 1e-6:
            items.append(("seg", None, t))
    parent = list(range(len(items)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def touch(a, b):
        (ka, _, xa), (kb, _, xb) = a, b
        if ka > kb:
            return touch(b, a)
        if ka == "pad" and kb == "seg":
            return xa.IsOnLayer(xb.GetLayer()) and (xa.HitTest(xb.GetStart()) or xa.HitTest(xb.GetEnd()))
        if ka == "pad" and kb == "via":
            return xa.HitTest(xb.GetPosition())
        if ka == "seg" and kb == "seg":
            return xa.GetLayer() == xb.GetLayer() and pcbnew.SEG(xa.GetStart(), xa.GetEnd()).Distance(
                pcbnew.SEG(xb.GetStart(), xb.GetEnd())) < (xa.GetWidth() + xb.GetWidth()) // 2
        if ka == "seg" and kb == "via":
            return pcbnew.SEG(xa.GetStart(), xa.GetEnd()).Distance(xb.GetPosition()) < xb.GetWidth() // 2
        return False

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if touch(items[i], items[j]):
                parent[root(i)] = root(j)
    first = next(i for i, it in enumerate(items) if it[1] == start)
    return {it[1] for i, it in enumerate(items) if it[0] == "pad" and root(i) == root(first)}


# A neck must never be in series with a load: each load is reached at full width.
for net, (source, loads) in POWER_LOADS.items():
    got = {w: reachable(net, source, w) for w in set(loads.values())}
    missing = [f"{pad} (needs {w} mm)" for pad, w in loads.items() if pad not in got[w]]
    print(f"{net:7} from {source} at full width: {len(loads) - len(missing)} of {len(loads)} loads"
          + (f"  <-- only through a neck: {', '.join(missing)}" if missing else ""))
    bad |= bool(missing)
sys.exit("power tracks or vias under-sized" if bad else 0)
