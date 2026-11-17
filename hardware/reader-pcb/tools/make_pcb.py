#!/usr/bin/env python3
"""Place the MagicBand Reader PCB from netlist.py (KiCad 7 pcbnew API).

Writes an unrouted .kicad_pcb (footprints, nets, outline, ground pours,
silkscreen). route.py then autoroutes it with Freerouting.

Board: 26 x 58 mm, 2 layers. The ESP32-S3 module's antenna sits along the
top edge over a copper-free area. Leads plug in on the edges: NFC (JST SH,
Qwiic order) and speaker (JST PH 2) on the left, LEDs (JST PH 3) on the
right, USB-C on the bottom.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from netlist import PARTS  # noqa: E402

FPDIR = Path("/usr/share/kicad/footprints")
X0, Y0 = 100.0, 80.0  # board origin on the page (mm)
W, H = 26.0, 58.0
USB_EDGE = 3.67  # USB4105 footprint: PCB edge is 3.67 mm in front of its origin

# ref: (x, y, rotation degrees) relative to the board's top-left corner.
# Rotation 270 points a side-entry connector's opening at the left edge, 90 at the right.
PLACE = {
    "U1": (13.0, 12.8, 0),
    # Beside the module: decoupling, EN, I2C pull-ups (left), IO0 pull-up (right)
    "C2": (1.7, 7.9, 90), "C1": (1.9, 10.6, 90), "R1": (1.7, 13.4, 90), "C3": (1.7, 15.4, 90),
    "R7": (1.7, 19.6, 90), "R8": (1.7, 21.6, 90), "R2": (24.3, 22.4, 90),
    # Row 1: speaker (left edge), amplifier (middle), LEDs (right edge)
    "J3": (4.95, 31.6, 270), "J4": (21.05, 32.0, 90),
    "U3": (13.0, 29.0, 0), "R5": (13.0, 32.3, 0), "C7": (13.0, 33.5, 0), "C6": (13.0, 35.6, 0),
    # Row 2: RESET, LED buffer, USB ESD + CC resistors, LED bulk cap, BOOT
    "SW1": (3.4, 39.9, 0), "U4": (8.6, 40.0, 0), "C8": (11.8, 39.1, 90), "R6": (11.8, 41.2, 90),
    "U5": (15.3, 40.0, 0), "R3": (18.6, 39.4, 90), "R4": (18.6, 41.4, 90),
    "C9": (20.8, 40.5, 90), "SW2": (24.0, 40.4, 90),
    # Regulator capacitors
    "C4": (20.0, 46.3, 0), "C5": (24.0, 46.3, 0),
    # Bottom: NFC (left edge), USB-C (bottom edge), regulator (right)
    "J2": (3.1, 53.0, 270), "J1": (13.0, H - USB_EDGE, 0), "U2": (22.2, 53.3, 90),
}


def mm(v: float) -> int:
    return pcbnew.FromMM(v)


def pt(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(X0 + x), mm(Y0 + y))


def add_outline(board: pcbnew.BOARD, r: float = 2.0) -> None:
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


def add_zone(board: pcbnew.BOARD, net: pcbnew.NETINFO_ITEM, layer: int) -> None:
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(net)
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in ((0, 0), (W, 0), (W, H), (0, H)):
        outline.Append(mm(X0 + x), mm(Y0 + y))
    zone.SetLocalClearance(mm(0.25))
    zone.SetMinThickness(mm(0.25))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    zone.SetThermalReliefGap(mm(0.3))
    zone.SetThermalReliefSpokeWidth(mm(0.4))
    zone.SetIsFilled(False)
    board.Add(zone)


def add_text(board, text, x, y, size=0.8, layer=pcbnew.F_SilkS, angle=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    t.SetTextAngleDegrees(angle)
    if layer == pcbnew.B_SilkS:
        t.SetMirrored(True)
    board.Add(t)


def main(out: Path) -> None:
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    ds = board.GetDesignSettings()
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_MinClearance = mm(0.15)
    ds.m_ViasMinSize = mm(0.5)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_HoleToHoleMin = mm(0.25)
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
        fp = pcbnew.FootprintLoad(str(FPDIR / f"{lib}.pretty"), name)
        if fp is None:
            raise SystemExit(f"footprint {part['fp']} not found")
        fp.SetReference(part["ref"])
        fp.SetValue(part["value"])
        fp.SetFPIDAsString(part["fp"])
        for key in ("MPN", "LCSC"):
            if part[key.lower()]:
                fp.SetProperty(key, part[key.lower()])
        x, y, rot = PLACE[part["ref"]]
        board.Add(fp)
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            num = pad.GetNumber()
            n = part["pins"].get(num)
            if n is None and num == "MP":
                n = "GND"  # connector mounting pads to ground
            if n is not None:
                pad.SetNet(net(n))
        # Small, tidy reference text; hide values.
        refs = fp.Reference()
        refs.SetTextSize(pcbnew.VECTOR2I(mm(0.6), mm(0.6)))
        refs.SetTextThickness(mm(0.1))
        refs.SetVisible(part["ref"][0] in "UJS")
        fp.Value().SetVisible(False)

    add_outline(board)
    add_zone(board, net("GND"), pcbnew.F_Cu)
    add_zone(board, net("GND"), pcbnew.B_Cu)

    # Connector labels (front) and board info (back).
    add_text(board, "SPK", 8.6, 26.6, 0.7)
    add_text(board, "+  -", 9.0, 36.9, 0.6)
    add_text(board, "LED", 17.6, 26.4, 0.7)
    add_text(board, "NFC", 7.4, 47.6, 0.7)
    add_text(board, "RST", 3.4, 42.4, 0.6)
    add_text(board, "BOOT", 24.0, 37.2, 0.6)
    add_text(board, "MagicBand Reader", 13.0, 30.0, 1.0, pcbnew.B_SilkS)
    add_text(board, "Magic bHAnds v1.0", 13.0, 32.0, 0.8, pcbnew.B_SilkS)
    add_text(board, "NFC: GND 3V3 SDA SCL", 13.0, 35.0, 0.7, pcbnew.B_SilkS)
    add_text(board, "LED: 5V DIN GND", 13.0, 36.5, 0.7, pcbnew.B_SilkS)
    add_text(board, "SPK: + -", 13.0, 38.0, 0.7, pcbnew.B_SilkS)

    board.Save(str(out))
    print(f"wrote {out} with {len(PARTS)} footprints and {len(nets)} nets")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
