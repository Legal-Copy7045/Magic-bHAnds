#!/usr/bin/env python3
"""Place the MagicBand Reader carrier board from netlist.py (KiCad 7 pcbnew API).

Writes an unrouted .kicad_pcb (footprints, nets, outline, ground pours,
antenna keep-out, silkscreen) and the .kicad_pro with the net classes the
autorouter uses. build.sh then routes it with Freerouting.

Board: 90 x 64 mm, 2 layers, four M3 holes 4 mm in from each corner, for a
4.92 in (125 mm) box. The ESP32-S3-DevKitC-1 lies along the middle with its
antenna end over a copper-free strip on the right. USB-C and the power parts
are on the left edge; the leads (LED ring, NFC, amplifier) plug in along the
top edge, nearest the Mickey head.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from netlist import PARTS, POWER_NETS  # noqa: E402

FPDIR = Path("/usr/share/kicad/footprints")
LOCAL = Path(__file__).parent / "lib"
X0, Y0 = 100.0, 80.0  # board origin on the page (mm)
W, H = 90.0, 64.0
ROW1, ROW3 = 26.0, 26.0 + 22.86  # dev board socket rows (J1 top, J3 bottom), 0.9 in apart
PIN1_X = 72.0  # both sockets' pin 1 (antenna end) at the right
ANTENNA = (75.5, ROW1 - 4.0, W, ROW3 + 4.0)  # copper-free strip under the antenna (x0, y0, x1, y1)
USB_X = 3.67  # USB-C: shell front 0.5 mm past the left edge

# ref: (x, y, rotation) relative to the board's top-left corner. 270 turns a
# footprint whose pins run down (+y) so they run left (-x).
PLACE = {
    "H1": (4, 4, 0), "H2": (W - 4, 4, 0), "H3": (4, H - 4, 0), "H4": (W - 4, H - 4, 0),
    "XJ1": (PIN1_X, ROW1, 270), "XJ3": (PIN1_X, ROW3, 270),
    # Top edge: LED ring and its parts, NFC, amplifier (kit header and Adafruit socket)
    "C5": (12.0, 15.0, 0),
    "J3": (20.5, 6.5, 90), "U2": (24.5, 15.0, 0), "C4": (24.5, 18.5, 0), "R7": (28.5, 15.0, 90),
    "U3": (32.0, 20.0, 90),
    "J2": (36.0, 6.5, 90), "R5": (39.5, 15.0, 90), "R6": (41.5, 15.0, 90),
    "J4": (51.0, 6.5, 90), "C6": (54.0, 15.5, 0), "C7": (60.0, 15.0, 90),
    "J5": (65.0, 6.5, 90),
    # Left edge: USB-C, PD controller, fuse, TVS, 5 V OK LED, Schottky to the dev board
    "J1": (USB_X, 40.0, 270),
    "U1": (12.5, 31.5, 0), "R1": (6.5, 26.0, 0), "C1": (9.5, 26.0, 0), "R2": (12.5, 26.0, 0), "R3": (16.5, 31.5, 90),
    "F1": (12.0, 46.5, 90), "D2": (12.0, 54.0, 90), "C2": (17.5, 54.5, 0), "C3": (17.5, 57.5, 0),
    "R4": (19.5, 59.5, 0), "D1": (22.5, 59.5, 180),
    "D3": (24.5, 21.0, 0),
    # Test points along the bottom edge
    "TP1": (30.0, 59.5, 0), "TP2": (36.0, 59.5, 0), "TP3": (42.0, 59.5, 0),
}


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(X0 + x), mm(Y0 + y))


def add_outline(board: pcbnew.BOARD, r: float = 3.0) -> None:
    def seg(a, b):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pt(*a))
        s.SetEnd(pt(*b))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    def arc(center, start, angle):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetCenter(pt(*center))
        s.SetStart(pt(*start))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T), True)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    seg((r, 0), (W - r, 0))
    seg((W, r), (W, H - r))
    seg((W - r, H), (r, H))
    seg((0, H - r), (0, r))
    arc((W - r, r), (W - r, 0), 90)
    arc((W - r, H - r), (W, H - r), 90)
    arc((r, H - r), (r, H), 90)
    arc((r, r), (0, r), 90)


def rect_outline(zone: pcbnew.ZONE, x0, y0, x1, y1) -> None:
    o = zone.Outline()
    o.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(mm(X0 + x), mm(Y0 + y))


def add_pour(board: pcbnew.BOARD, net: pcbnew.NETINFO_ITEM, layer: int) -> None:
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(net)
    rect_outline(zone, 0, 0, W, H)
    zone.SetLocalClearance(mm(0.3))
    zone.SetMinThickness(mm(0.25))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)  # hand-soldered through-hole parts
    zone.SetThermalReliefGap(mm(0.3))
    zone.SetThermalReliefSpokeWidth(mm(0.5))
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    zone.SetIsFilled(False)
    board.Add(zone)


def add_keepout(board: pcbnew.BOARD, x0, y0, x1, y1) -> None:
    """No copper, tracks or vias on either layer: under the ESP32's antenna."""
    zone = pcbnew.ZONE(board)
    zone.SetIsRuleArea(True)
    zone.SetDoNotAllowCopperPour(True)
    zone.SetDoNotAllowTracks(True)
    zone.SetDoNotAllowVias(True)
    zone.SetDoNotAllowPads(False)
    zone.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET()
    ls.AddLayer(pcbnew.F_Cu)
    ls.AddLayer(pcbnew.B_Cu)
    zone.SetLayerSet(ls)
    rect_outline(zone, x0, y0, x1, y1)
    zone.SetZoneName("antenna keep-out")
    board.Add(zone)


def add_text(board, text, x, y, size=1.0, layer=pcbnew.F_SilkS, angle=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(size * 0.15, 0.12)))
    t.SetTextAngleDegrees(angle)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def write_project(path: Path) -> None:
    """Net classes for the autorouter: wide 5 V and ground, normal signals."""
    classes = [dict(name="Default", clearance=0.2, track_width=0.25, via_diameter=0.6, via_drill=0.3)]
    patterns = []
    for net, width in POWER_NETS.items():
        name = "P_" + net.replace("+", "").replace("_", "")
        classes.append(dict(name=name, clearance=0.25, track_width=width, via_diameter=0.8, via_drill=0.4))
        patterns.append(dict(netclass=name, pattern=net))
    for c in classes:
        c.update(bus_width=12, diff_pair_gap=0.25, diff_pair_via_gap=0.25, diff_pair_width=0.2, line_style=0,
                 microvia_diameter=0.3, microvia_drill=0.1, pcb_color="rgba(0, 0, 0, 0.000)",
                 schematic_color="rgba(0, 0, 0, 0.000)", wire_width=6)
    proj = {
        "board": {"design_settings": {"defaults": {}, "rules": {
            "min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.5, "min_through_hole_diameter": 0.3,
            "min_copper_edge_clearance": 0.3, "min_hole_to_hole": 0.25, "min_hole_clearance": 0.25}}},
        "meta": {"filename": path.name, "version": 1},
        "net_settings": {"classes": classes, "meta": {"version": 3}, "net_colors": None,
                         "netclass_assignments": None, "netclass_patterns": patterns},
    }
    path.write_text(json.dumps(proj, indent=2) + "\n")


def main(out: Path) -> None:
    write_project(out.with_suffix(".kicad_pro"))
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_MinClearance = mm(0.15)
    ds.m_ViasMinSize = mm(0.5)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_HoleToHoleMin = mm(0.25)
    ds.m_HoleClearance = mm(0.25)
    ds.m_MinSilkTextHeight = mm(0.7)
    ds.m_MinSilkTextThickness = mm(0.12)
    ds.m_SolderMaskExpansion = mm(0.05)

    nets: dict[str, pcbnew.NETINFO_ITEM] = {}

    def net(name: str) -> pcbnew.NETINFO_ITEM:
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    for part in PARTS:
        lib, name = part["fp"].split(":")
        libdir = LOCAL / f"{lib}.pretty" if (LOCAL / f"{lib}.pretty").exists() else FPDIR / f"{lib}.pretty"
        fp = pcbnew.FootprintLoad(str(libdir), name)
        if fp is None:
            raise SystemExit(f"footprint {part['fp']} not found")
        fp.SetReference(part["ref"])
        fp.SetValue(part["value"])
        fp.SetFPIDAsString(part["fp"])
        for key in ("MPN", "LCSC"):
            if part[key.lower()]:
                fp.SetProperty(key, part[key.lower()])
        if part["asm"] != "smt":
            fp.SetExcludedFromPosFiles(True)
            fp.SetExcludedFromBOM(part["asm"] == "none")
        x, y, rot = PLACE[part["ref"]]
        board.Add(fp)
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            num = pad.GetNumber()
            n = part["pins"].get(num)
            if n is None and num in ("MP", "") and part["ref"].startswith("J1"):
                n = "GND"  # USB-C shell pegs
            if n is not None:
                pad.SetNet(net(n))
        refs = fp.Reference()
        refs.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
        refs.SetTextThickness(mm(0.12))
        refs.SetVisible((part["ref"][0] in "JXUF" or part["ref"].startswith("TP")) and part["ref"] != "J5")
        if part["ref"].startswith("J"):
            for pad in fp.Pads():  # connector grounds: solid, so a blocked spoke can't starve them
                if pad.GetNetname() == "GND":
                    pad.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        fp.Value().SetVisible(False)

    # USB-C VBUS: the pins are 0.5 mm apart, too tight for a 0.8 mm track, so each
    # VBUS pin gets a short pad-width stub out past the pin row. They're locked, so
    # Freerouting keeps them and joins them with full-width VBUS track.
    usb = board.FindFootprintByReference("J1")
    for g in list(usb.GraphicalItems()):  # the socket's outline marks that would run off the board edge
        if g.GetLayer() == pcbnew.F_SilkS and pcbnew.ToMM(g.GetBoundingBox().GetX()) - X0 < 2.5:
            usb.Remove(g)
    for pad in usb.Pads():
        if pad.GetNetname() == "VBUS" and pad.GetNumber() in ("A4", "B4"):
            c = pad.GetPosition()
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(c)
            t.SetEnd(pcbnew.VECTOR2I(c.x + mm(2.2), c.y))
            t.SetWidth(mm(0.6))
            t.SetLayer(pcbnew.F_Cu)
            t.SetNet(net("VBUS"))
            t.SetLocked(True)
            board.Add(t)

    add_outline(board)
    add_keepout(board, *ANTENNA)
    add_pour(board, net("GND"), pcbnew.F_Cu)
    add_pour(board, net("GND"), pcbnew.B_Cu)

    # Labels by the connectors (front) and board info (back).
    add_text(board, "RING 5V DIN GND", 23.0, 3.0, 0.8)
    add_text(board, "NFC GND 5V SDA SCL", 39.8, 3.0, 0.8)
    add_text(board, "AMP G V BCL LRC DIN", 56.0, 11.0, 0.7)
    add_text(board, "ADAFRUIT 3006", 72.6, 11.0, 0.7)
    add_text(board, "USB-C 5V", 4.5, 31.0, 0.8, angle=90)
    add_text(board, "5V OK", 22.5, 61.8, 0.7)
    add_text(board, "5V   3V3   GND", 36.0, 62.2, 0.8)
    add_text(board, "ESP32-S3-DevKitC-1, antenna end -->", 54.0, ROW1 + 11.4, 1.0)
    add_text(board, "no copper", 82.5, ROW1 + 11.4, 0.8, angle=90)
    add_text(board, "MagicBand Reader carrier v1.0", 45.0, 30.0, 1.5, pcbnew.B_SilkS)
    add_text(board, "github.com/Legal-Copy7045/Magic-bHAnds", 45.0, 33.0, 1.0, pcbnew.B_SilkS)
    add_text(board, "USB-C fixed at 5 V. Dev-board USB and the charger can't back-feed each other.", 45.0, 36.0, 0.8,
             pcbnew.B_SilkS)

    pcbnew.SaveBoard(str(out), board)
    print(f"wrote {out} with {len(PARTS)} footprints and {len(nets)} nets")

    # Check the dev board sockets: pin 1 at the antenna end, pins running left.
    for fp in board.GetFootprints():
        if fp.GetReference() in ("XJ1", "XJ3"):
            p = {pad.GetNumber(): pcbnew.ToMM(pad.GetPosition().x) - X0 for pad in fp.Pads()}
            assert p["1"] > p["22"], f"{fp.GetReference()} is reversed"


if __name__ == "__main__":
    main(Path(sys.argv[1]))
