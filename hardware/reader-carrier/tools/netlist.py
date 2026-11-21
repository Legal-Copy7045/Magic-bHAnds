"""MagicBand Reader carrier board: parts and connections (one source for schematic and PCB).

The "brains" board for the reader: the ESP32-S3-DevKitC-1 (N16R8) plugs into
two 22-pin sockets, the MAX98357A amplifier kit plugs into a 5-pin header with
its own cable (or an Adafruit 3006 breakout into the 7-pin socket), and the
LED ring and PN532 NFC board go on leads. Every lead plugs into a 2.54 mm
female header in its own cable's pin order, the way it plugs into a breadboard. USB-C power with a CH224A
(or CH224K) fixed at 5 V (CFG1 high: it can never ask for more), a 3.5 A resettable fuse, a
TVS clamp, and a Schottky diode so the dev board's own USB can't back-feed the
board. GPIOs match esphome/magicband-reader.yaml.

Each part: ref, symbol (lib:name; "MagicbHAnds" = tools/lib), value, footprint,
MPN, LCSC part number (every "smt" part has one; "" for parts you solder),
assembly ("smt" by JLCPCB, "tht" soldered by hand), and {pin: net}.
Pins not listed are left unconnected.
"""

GND, V5, VBUS, V3 = "GND", "+5V", "VBUS", "+3V3"

# Dev-board socket J1 (left row with the antenna up; the top row on this board).
# Pin n of each socket: n = 1 nearest the antenna.
J1_PINS = {"1": V3, "2": V3, "5": "I2S_LRC", "6": "I2S_BCLK", "7": "I2S_DIN",
           "12": "I2C_SDA", "15": "I2C_SCL", "16": "LED_3V3", "21": "ESP_5V", "22": GND}
J3_PINS = {"1": GND, "21": GND, "22": GND}

R0402, C0402, C0805 = "Resistor_SMD:R_0402_1005Metric", "Capacitor_SMD:C_0402_1005Metric", "Capacitor_SMD:C_0805_2012Metric"

PARTS = [
    # --- USB-C power in, PD sink fixed at 5 V ---------------------------------
    dict(ref="J1", sym="Connector:USB_C_Receptacle_USB2.0_16P", value="USB-C (power)",
         fp="MagicbHAnds:USB_C_Receptacle_HRO_TYPE-C-31-M-12_EdgeTrim", mpn="TYPE-C-31-M-12", lcsc="C165948", asm="smt",
         pins={"A4": VBUS, "A9": VBUS, "B4": VBUS, "B9": VBUS,
               "A1": GND, "A12": GND, "B1": GND, "B12": GND, "S1": GND,
               "A5": "CC1", "B5": "CC2"}),  # D+/D- unused: power only
    # CH224A: WCH's pin-compatible upgrade of the CH224K (datasheet V2.1, 4.2 and 7.2),
    # and the one JLCPCB stocks. For a CH224K instead, fit R1 = 1k and R2 = 10k.
    dict(ref="U1", sym="MagicbHAnds:CH224K", value="CH224A",
         fp="MagicbHAnds:CH224K_ESSOP-10", mpn="CH224A", lcsc="C42459160", asm="smt",
         pins={"1": "PD_VDD", "2": GND, "3": GND, "6": "CC2", "7": "CC1",
               "8": "PD_VSENSE", "9": "PD_CFG1", "10": "PG", "11": GND}),
    # CH224A (6.1.2): VHV straight from VBUS with 1 uF, VBUS sense tied to VHV, CFG1
    # 100 k to VHV = 5 V. So R1 and R2 are 0 ohm. (CH224K, 6.2: R1 1 k, R2 10 k.)
    # DP/DM are left open: the 5 V request is made over CC (USB PD) alone.
    dict(ref="R1", sym="Device:R_Small", value="0R", fp=R0402, mpn="0402WGF0000TCE", lcsc="C17168", asm="smt",
         pins={"1": VBUS, "2": "PD_VDD"}),
    dict(ref="C1", sym="Device:C_Small", value="1uF", fp=C0402, mpn="CL05A105KA5NQNC", lcsc="C52923", asm="smt",
         pins={"1": "PD_VDD", "2": GND}),
    dict(ref="R2", sym="Device:R_Small", value="0R", fp=R0402, mpn="0402WGF0000TCE", lcsc="C17168", asm="smt",
         pins={"1": VBUS, "2": "PD_VSENSE"}),
    # Datasheet 5.2.2: CFG1 high = 5 V (CFG2, CFG3 don't care; tied low), pulled up
    # through 100 k to pin 1 (VHV on the CH224A, VDD on the CH224K).
    dict(ref="R3", sym="Device:R_Small", value="100k", fp=R0402, mpn="0402WGF1003TCE", lcsc="C25741", asm="smt",
         pins={"1": "PD_VDD", "2": "PD_CFG1"}),
    # "5V OK" LED: PG pulls low once the charger has agreed 5 V.
    dict(ref="R4", sym="Device:R_Small", value="1k", fp=R0402, mpn="0402WGF1001TCE", lcsc="C11702", asm="smt",
         pins={"1": V5, "2": "PG_LED"}),
    dict(ref="D1", sym="Device:LED_Small", value="green", fp="LED_SMD:LED_0603_1608Metric",
         mpn="KT-0603G", lcsc="C12624", asm="smt", pins={"1": "PG", "2": "PG_LED"}),
    # Fuse (3.5 A hold, sized for a warm box; see README) and TVS clamp on the 5 V rail.
    dict(ref="F1", sym="Device:Polyfuse_Small", value="3.5A hold", fp="Fuse:Fuse_1812_4532Metric",
         mpn="SMD1812P350TF/16", lcsc="C46970911", asm="smt", pins={"1": VBUS, "2": V5}),
    dict(ref="D2", sym="Diode:SMAJ5.0A", value="SMAJ5.0A", fp="Diode_SMD:D_SMA",
         mpn="SMAJ5.0A", lcsc="C113952", asm="smt", pins={"1": V5, "2": GND}),
    dict(ref="C2", sym="Device:C_Small", value="10uF", fp=C0805, mpn="CL21A106KAYNNNE", lcsc="C15850", asm="smt",
         pins={"1": V5, "2": GND}),
    dict(ref="C3", sym="Device:C_Small", value="100nF", fp=C0402, mpn="CL05B104KO5NNNC", lcsc="C1525", asm="smt",
         pins={"1": V5, "2": GND}),
    # --- Dev board ---------------------------------------------------------------
    # 5 V to the dev board through a Schottky: the board powers the ESP32, but the
    # dev board's own USB can never power the LEDs and amplifier (no jumper to pull).
    dict(ref="D3", sym="Device:D_Schottky_Small", value="SS34", fp="Diode_SMD:D_SMA",
         mpn="SS34", lcsc="C8678", asm="smt", pins={"1": "ESP_5V", "2": V5}),
    dict(ref="XJ1", sym="Connector_Generic:Conn_01x22", value="DevKitC-1 J1",
         fp="Connector_PinSocket_2.54mm:PinSocket_1x22_P2.54mm_Vertical", mpn="2.54 mm 1x22 female header", lcsc="", asm="tht",
         pins=J1_PINS),
    dict(ref="XJ3", sym="Connector_Generic:Conn_01x22", value="DevKitC-1 J3",
         fp="Connector_PinSocket_2.54mm:PinSocket_1x22_P2.54mm_Vertical", mpn="2.54 mm 1x22 female header", lcsc="", asm="tht",
         pins=J3_PINS),
    # --- I2C to the PN532 (lead) ----------------------------------------------------
    dict(ref="R5", sym="Device:R_Small", value="4.7k", fp=R0402, mpn="0402WGF4701TCE", lcsc="C25900", asm="smt",
         pins={"1": V3, "2": "I2C_SDA"}),
    dict(ref="R6", sym="Device:R_Small", value="4.7k", fp=R0402, mpn="0402WGF4701TCE", lcsc="C25900", asm="smt",
         pins={"1": V3, "2": "I2C_SCL"}),
    # PN532 lead: same order as the PN532's own header (GND VCC SDA SCL), so its
    # Dupont cable's male ends plug straight in, as they do on the breadboard.
    dict(ref="J2", sym="Connector_Generic:Conn_01x04", value="NFC",
         fp="Connector_PinSocket_2.54mm:PinSocket_1x04_P2.54mm_Vertical", mpn="2.54 mm 1x4 female header", lcsc="", asm="tht",
         pins={"1": GND, "2": V5, "3": "I2C_SDA", "4": "I2C_SCL"}),
    # --- LED ring (lead): 3.3 V -> 5 V buffer, 470 ohm, bulk capacitor ----------------
    dict(ref="U2", sym="74xGxx:74AHCT1G125", value="74AHCT1G125", fp="Package_TO_SOT_SMD:SOT-23-5",
         mpn="SN74AHCT1G125DBVR", lcsc="C7484", asm="smt",
         pins={"1": GND, "2": "LED_3V3", "3": GND, "4": "LED_5V", "5": V5}),
    dict(ref="C4", sym="Device:C_Small", value="100nF", fp=C0402, mpn="CL05B104KO5NNNC", lcsc="C1525", asm="smt",
         pins={"1": V5, "2": GND}),
    dict(ref="R7", sym="Device:R_Small", value="470R", fp=R0402, mpn="0402WGF4700TCE", lcsc="C25117", asm="smt",
         pins={"1": "LED_5V", "2": "LED_DATA"}),
    # GPIO10 is high-impedance while the ESP32 resets and boots: hold the level shifter's input
    # low so the ring doesn't get random data (flashes) at power-up.
    dict(ref="R8", sym="Device:R_Small", value="10k", fp=R0402, mpn="0402WGF1002TCE", lcsc="C25744", asm="smt",
         pins={"1": "LED_3V3", "2": GND}),
    dict(ref="C5", sym="Device:C_Polarized_Small", value="1000uF 10V", fp="Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
         mpn="1000 uF 10 V radial, 10 mm", lcsc="", asm="tht", pins={"1": V5, "2": GND}),
    # LED ring lead: the ring's 3-pin plug order (red 5V, green DIN, black GND).
    dict(ref="J3", sym="Connector_Generic:Conn_01x03", value="LED ring",
         fp="Connector_PinSocket_2.54mm:PinSocket_1x03_P2.54mm_Vertical", mpn="2.54 mm 1x3 female header", lcsc="", asm="tht",
         pins={"1": V5, "2": "LED_DATA", "3": GND}),
    # ESD clamp on the lines that leave the box on leads.
    dict(ref="U3", sym="Power_Protection:SRV05-4", value="SRV05-4", fp="Package_TO_SOT_SMD:SOT-23-6",
         mpn="SRV05-4.TCT", lcsc="C13612", asm="smt",
         pins={"1": "I2C_SDA", "2": GND, "3": "I2C_SCL", "4": "LED_DATA", "5": V5}),
    # --- Amplifier --------------------------------------------------------------------
    # The amplifier kit's cable, in its socket's order (G, V, BCL, LRC, DIN); the speaker plugs into the amplifier.
    dict(ref="J4", sym="Connector_Generic:Conn_01x05", value="Amplifier",
         fp="Connector_PinSocket_2.54mm:PinSocket_1x05_P2.54mm_Vertical", mpn="2.54 mm 1x5 female header", lcsc="", asm="tht",
         pins={"1": GND, "2": V5, "3": "I2S_BCLK", "4": "I2S_LRC", "5": "I2S_DIN"}),
    # Or an Adafruit 3006 breakout straight into a socket (LRC BCLK DIN GAIN SD GND Vin).
    dict(ref="J5", sym="Connector_Generic:Conn_01x07", value="Adafruit 3006 (alt)",
         fp="Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical", mpn="2.54 mm 1x7 female header", lcsc="", asm="tht",
         pins={"1": "I2S_LRC", "2": "I2S_BCLK", "3": "I2S_DIN", "6": GND, "7": V5}),
    dict(ref="C6", sym="Device:C_Polarized_Small", value="100uF 16V", fp="Capacitor_THT:CP_Radial_D6.3mm_P2.50mm",
         mpn="100 uF 16 V radial, 6.3 mm", lcsc="", asm="tht", pins={"1": V5, "2": GND}),
    dict(ref="C7", sym="Device:C_Small", value="10uF", fp=C0805, mpn="CL21A106KAYNNNE", lcsc="C15850", asm="smt",
         pins={"1": V5, "2": GND}),
    # --- Test points and mounting holes -------------------------------------------------
    dict(ref="TP1", sym="Connector:TestPoint", value="5V", fp="TestPoint:TestPoint_Pad_D1.5mm",
         mpn="", lcsc="", asm="none", pins={"1": V5}),
    dict(ref="TP2", sym="Connector:TestPoint", value="3V3", fp="TestPoint:TestPoint_Pad_D1.5mm",
         mpn="", lcsc="", asm="none", pins={"1": V3}),
    dict(ref="TP3", sym="Connector:TestPoint", value="GND", fp="TestPoint:TestPoint_Pad_D1.5mm",
         mpn="", lcsc="", asm="none", pins={"1": GND}),
] + [
    dict(ref=f"H{i}", sym="Mechanical:MountingHole", value="M3", fp="MountingHole:MountingHole_3.2mm_M3",
         mpn="", lcsc="", asm="none", pins={})
    for i in range(1, 5)
]

PWR_FLAGS = [VBUS, GND, V3]

# Track widths (mm). +5V carries the LED and amplifier current (up to ~2.2 A at 0.8 mm, 1 oz,
# about 20 C rise); narrow enough to reach the 0.95 mm-pitch SOT-23 pins. Ground is mostly pour.
POWER_NETS = {GND: 0.5, V5: 0.8, VBUS: 0.8, "ESP_5V": 0.6, V3: 0.4}
# Via (pad, drill) in mm per power net. The nets that carry the whole load get a 0.8 mm drill:
# its barrel (2.5 mm round x 18 um plating = 0.045 mm2) has more copper than the 0.8 mm track
# (0.028 mm2 at 1 oz). A 0.4 mm drill (0.023 mm2) would be the thinnest point of the path.
POWER_VIAS = {"+5V": (1.4, 0.8), "VBUS": (1.4, 0.8)}
POWER_VIA_DEFAULT = (0.8, 0.4)
