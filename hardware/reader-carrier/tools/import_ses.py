#!/usr/bin/env python3
"""Import a Freerouting .ses (Specctra session) into a .kicad_pcb, headless.

KiCad 7's pcbnew.ImportSpecctraSES only works inside the editor, so this reads
the session's wires and vias and adds them as tracks and vias, then refills
the zones.

Usage: import_ses.py board.kicad_pcb board.ses
"""

from __future__ import annotations

import re
import sys

import pcbnew


def tokens(text: str):
    for m in re.finditer(r'\(|\)|"[^"]*"|[^\s()]+', text):
        yield m.group(0)


def parse(text: str):
    stack: list[list] = [[]]
    for tok in tokens(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(tok.strip('"'))
    return stack[0][0]


def find(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def add_stitching(board, pitch_mm=5.0, size_mm=0.6, drill_mm=0.3) -> int:
    """GND vias on a grid wherever they clear other nets, holes and parts.

    They tie the front and back ground pours together so no pour island (or
    pad that relies on one) is left floating. None go in the antenna keep-out.
    """
    mm = pcbnew.FromMM
    gnd = board.FindNet("GND")
    edge = board.GetBoardEdgesBoundingBox()
    clearance = mm(0.25)
    radius = mm(size_mm) // 2
    items = [t for t in board.GetTracks()]
    pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
    courtyards = [fp.GetCourtyard(pcbnew.F_CrtYd) for fp in board.GetFootprints()]
    keepouts = [z for z in board.Zones() if z.GetIsRuleArea()]
    added = 0
    corner = mm(5.0)  # keep clear of the rounded corners and mounting holes

    def near_corner(q):
        dx = min(q.x - edge.GetX(), edge.GetRight() - q.x)
        dy = min(q.y - edge.GetY(), edge.GetBottom() - q.y)
        return dx < corner and dy < corner

    y = edge.GetY() + mm(2.0)
    while y < edge.GetBottom() - mm(2.0):
        x = edge.GetX() + mm(2.0)
        while x < edge.GetRight() - mm(2.0):
            p = pcbnew.VECTOR2I(int(x), int(y))
            circle = pcbnew.SHAPE_CIRCLE(p, radius)
            ok = not any(c.OutlineCount() and c.Contains(p) for c in courtyards)
            m = radius + mm(0.3)
            probes = [p] + [pcbnew.VECTOR2I(p.x + dx, p.y + dy) for dx in (-m, 0, m) for dy in (-m, 0, m)]
            ok = ok and not near_corner(p) and not any(z.Outline().Contains(q) for z in keepouts for q in probes)
            if ok:
                for it in items:
                    gap = mm(0.3) if it.GetClass() == "PCB_VIA" else clearance
                    if it.GetNetCode() == gnd.GetNetCode() and it.GetClass() != "PCB_VIA":
                        continue
                    if it.GetEffectiveShape(it.GetLayer()).Collide(circle, gap):
                        ok = False
                        break
            if ok:
                for pad in pads:
                    gap = mm(0.3) if pad.HasHole() else clearance
                    shape = pad.GetEffectiveShape(pcbnew.F_Cu if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
                    if (pad.GetNetCode() != gnd.GetNetCode() or pad.HasHole()) and shape.Collide(circle, gap):
                        ok = False
                        break
            if ok:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(p)
                v.SetWidth(mm(size_mm))
                v.SetDrill(mm(drill_mm))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetNet(gnd)
                board.Add(v)
                items.append(v)
                added += 1
            x += mm(pitch_mm)
        y += mm(pitch_mm)
    return added


def _via_fits(board, p, gnd, radius, others):
    circle = pcbnew.SHAPE_CIRCLE(p, radius)
    for it in others:
        if it.GetNetCode() == gnd.GetNetCode() and not (it.GetClass() == "PCB_VIA" or (it.GetClass() == "PAD" and it.HasHole())):
            continue
        if it.GetClass() == "PAD":
            layer = pcbnew.F_Cu if it.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            gap = pcbnew.FromMM(0.3) if it.HasHole() else pcbnew.FromMM(0.25)
            if it.GetEffectiveShape(layer).Collide(circle, gap):
                return False
        else:
            gap = pcbnew.FromMM(0.3) if it.GetClass() == "PCB_VIA" else pcbnew.FromMM(0.25)
            if it.GetEffectiveShape(it.GetLayer()).Collide(circle, gap):
                return False
    return True


def _via_beside_pad(board, piece, layer, gnd, radius, size_mm, drill_mm, vias, others) -> int:
    import math

    mm = pcbnew.FromMM
    width = mm(0.3)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() != gnd.GetNetCode() or not pad.IsOnLayer(layer) or not piece.Contains(pad.GetPosition()):
                continue
            c = pad.GetPosition()
            for dist in (0.9, 1.1, 1.3, 1.6, 2.0):
                for k in range(16):
                    a = 2 * math.pi * k / 16
                    p = pcbnew.VECTOR2I(int(c.x + mm(dist) * math.cos(a)), int(c.y + mm(dist) * math.sin(a)))
                    if not _via_fits(board, p, gnd, radius, others):
                        continue
                    seg = pcbnew.SHAPE_SEGMENT(c, p, width)
                    clash = False
                    for it in others:
                        if it.GetNetCode() == gnd.GetNetCode():
                            continue
                        if it.GetClass() == "PAD":
                            if not it.IsOnLayer(layer):
                                continue
                            shape = it.GetEffectiveShape(layer)
                        else:
                            if it.GetLayer() != layer and it.GetClass() != "PCB_VIA":
                                continue
                            shape = it.GetEffectiveShape(layer)
                        if shape.Collide(seg, mm(0.2)):
                            clash = True
                            break
                    if clash:
                        continue
                    t = pcbnew.PCB_TRACK(board)
                    t.SetStart(c)
                    t.SetEnd(p)
                    t.SetWidth(width)
                    t.SetLayer(layer)
                    t.SetNet(gnd)
                    board.Add(t)
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(p)
                    v.SetWidth(mm(size_mm))
                    v.SetDrill(mm(drill_mm))
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    v.SetNet(gnd)
                    board.Add(v)
                    vias.append(v)
                    others.extend([t, v])
                    return 1
    return 0


def stitch_fragments(board, size_mm=0.6, drill_mm=0.3) -> int:
    """Put a GND via in every piece of ground pour that has none, so each
    piece joins the pour on the other side."""
    mm = pcbnew.FromMM
    gnd = board.FindNet("GND")
    radius = mm(size_mm) // 2
    vias = [t for t in board.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetCode() == gnd.GetNetCode()]
    others = list(board.GetTracks()) + [p for fp in board.GetFootprints() for p in fp.Pads()]
    added = 0
    for zone in board.Zones():
        if zone.GetNetCode() != gnd.GetNetCode() or zone.GetIsRuleArea():
            continue
        layer = zone.GetLayer()
        polys = zone.GetFilledPolysList(layer)
        for i in range(polys.OutlineCount()):
            piece = pcbnew.SHAPE_POLY_SET()
            piece.AddOutline(polys.Outline(i))
            for h in range(polys.HoleCount(i)):
                piece.AddHole(polys.Hole(i, h))
            if any(piece.Contains(v.GetPosition()) for v in vias):
                continue
            # Shrink so the whole via sits inside the copper, then search a grid.
            inner = pcbnew.SHAPE_POLY_SET(piece)
            inner.Deflate(radius + mm(0.05), 8)
            if inner.OutlineCount() == 0:
                # Too small for a via: run a short track from a GND pad in
                # this piece to a via just outside it.
                added += _via_beside_pad(board, piece, layer, gnd, radius, size_mm, drill_mm, vias, others)
                continue
            bb = inner.BBox()
            step = mm(0.2)
            placed = False
            y = bb.GetY()
            while y <= bb.GetBottom() and not placed:
                x = bb.GetX()
                while x <= bb.GetRight():
                    p = pcbnew.VECTOR2I(int(x), int(y))
                    if inner.Contains(p) and _via_fits(board, p, gnd, radius, others):
                        v = pcbnew.PCB_VIA(board)
                        v.SetPosition(p)
                        v.SetWidth(mm(size_mm))
                        v.SetDrill(mm(drill_mm))
                        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                        v.SetNet(gnd)
                        board.Add(v)
                        vias.append(v)
                        others.append(v)
                        added += 1
                        placed = True
                        break
                    x += step
                y += step
    return added


def main(pcb_path: str, ses_path: str) -> None:
    board = pcbnew.LoadBoard(pcb_path)
    session = parse(open(ses_path).read())
    routes = find(session, "routes")[0]
    res = find(routes, "resolution")[0]
    scale = {"um": 1000, "mm": 1_000_000, "mil": 25_400}[res[1]] / int(res[2])  # session units -> nm

    def pos(x: str, y: str) -> pcbnew.VECTOR2I:
        return pcbnew.VECTOR2I(int(round(float(x) * scale)), int(round(-float(y) * scale)))

    layers = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    vias_size = {}
    for ps in find(find(routes, "library_out")[0], "padstack"):
        m = re.search(r"_(\d+):(\d+)_um", ps[1])
        if m:
            vias_size[ps[1]] = (int(m.group(1)) * 1000, int(m.group(2)) * 1000)

    # Drop any existing tracks so re-running is safe.
    for t in list(board.GetTracks()):
        board.Remove(t)

    n_tracks = n_vias = 0
    for net_node in find(find(routes, "network_out")[0], "net"):
        net = board.FindNet(net_node[1])
        if net is None:
            raise SystemExit(f"net {net_node[1]} not on the board")
        for wire in find(net_node, "wire"):
            path = find(wire, "path")[0]
            layer, width, coords = path[1], int(float(path[2]) * scale), path[3:]
            pts = [pos(coords[i], coords[i + 1]) for i in range(0, len(coords) - 1, 2)]
            for a, b in zip(pts, pts[1:]):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(a)
                t.SetEnd(b)
                t.SetWidth(width)
                t.SetLayer(layers[layer])
                t.SetNet(net)
                board.Add(t)
                n_tracks += 1
        for via in find(net_node, "via"):
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pos(via[2], via[3]))
            size, drill = vias_size.get(via[1], (600_000, 300_000))
            v.SetWidth(size)
            v.SetDrill(drill)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(net)
            board.Add(v)
            n_vias += 1

    n_stitch = add_stitching(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    for _ in range(3):
        added = stitch_fragments(board)
        n_stitch += added
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        if not added:
            break
    board.Save(pcb_path)
    print(f"imported {n_tracks} track segments and {n_vias} vias, added {n_stitch} ground stitching vias; "
          f"unrouted connections: {board.GetConnectivity().GetUnconnectedCount(True)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
