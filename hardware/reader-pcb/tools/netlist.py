"""MagicBand Reader PCB: parts and connections (single source for schematic and PCB).

ESP32-S3-WROOM-1-N16R8 module with native USB-C, 3.3 V LDO, MAX98357A I2S
amplifier, 5 V level shifter for the LEDs, and connectors for leads to the
NFC reader, speaker and LED ring / Mickey head. GPIOs match
esphome/magicband-reader.yaml.

Each part: ref, symbol (lib:name), value, footprint (lib:name), MPN, LCSC
part number ("" where you should pick one in JLCPCB's parts search), and
{pin number: net}. Pins not listed are left unconnected (no-connect).
"""

GND, V5, V3 = "GND", "+5V", "+3V3"

PARTS = [
    # --- MCU ---------------------------------------------------------------
    dict(ref="U1", sym="RF_Module:ESP32-S3-WROOM-1", value="ESP32-S3-WROOM-1-N16R8",
         fp="RF_Module:ESP32-S3-WROOM-1", mpn="ESP32-S3-WROOM-1-N16R8", lcsc="C2913202",
         pins={"1": GND, "40": GND, "41": GND, "2": V3, "3": "EN", "27": "BOOT",
               "5": "I2S_LRCLK", "6": "I2S_BCLK", "7": "I2S_DOUT",
               "12": "I2C_SDA", "17": "I2C_SCL", "18": "LED_3V3",
               "13": "USB_DN", "14": "USB_DP"}),
    dict(ref="C1", sym="Device:C_Small", value="22uF", fp="Capacitor_SMD:C_0805_2012Metric",
         mpn="CL21A226MAQNNNE", lcsc="C45783", pins={"1": V3, "2": GND}),
    dict(ref="C2", sym="Device:C_Small", value="100nF", fp="Capacitor_SMD:C_0402_1005Metric",
         mpn="CL05B104KO5NNNC", lcsc="C1525", pins={"1": V3, "2": GND}),
    dict(ref="R1", sym="Device:R_Small", value="10k", fp="Resistor_SMD:R_0402_1005Metric",
         mpn="0402WGF1002TCE", lcsc="C25744", pins={"1": V3, "2": "EN"}),
    dict(ref="C3", sym="Device:C_Small", value="1uF", fp="Capacitor_SMD:C_0402_1005Metric",
         mpn="CL05A105KA5NQNC", lcsc="C52923", pins={"1": "EN", "2": GND}),
    dict(ref="SW1", sym="Switch:SW_Push", value="RESET", fp="Button_Switch_SMD:SW_SPST_B3U-1000P",
         mpn="B3U-1000P", lcsc="", pins={"1": "EN", "2": GND}),
    dict(ref="R2", sym="Device:R_Small", value="10k", fp="Resistor_SMD:R_0402_1005Metric",
         mpn="0402WGF1002TCE", lcsc="C25744", pins={"1": V3, "2": "BOOT"}),
    dict(ref="SW2", sym="Switch:SW_Push", value="BOOT", fp="Button_Switch_SMD:SW_SPST_B3U-1000P",
         mpn="B3U-1000P", lcsc="", pins={"1": "BOOT", "2": GND}),
    # --- USB-C power and data -----------------------------------------------
    dict(ref="J1", sym="Connector:USB_C_Receptacle_USB2.0_16P", value="USB-C",
         fp="Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
         mpn="USB4105-GF-A", lcsc="",
         pins={"A4": V5, "A9": V5, "B4": V5, "B9": V5,
               "A1": GND, "A12": GND, "B1": GND, "B12": GND, "S1": GND,
               "A5": "CC1", "B5": "CC2", "A6": "USB_C_DP", "B6": "USB_C_DP",
               "A7": "USB_C_DN", "B7": "USB_C_DN"}),
    dict(ref="R3", sym="Device:R_Small", value="5.1k", fp="Resistor_SMD:R_0402_1005Metric",
         mpn="0402WGF5101TCE", lcsc="C25905", pins={"1": "CC1", "2": GND}),
    dict(ref="R4", sym="Device:R_Small", value="5.1k", fp="Resistor_SMD:R_0402_1005Metric",
         mpn="0402WGF5101TCE", lcsc="C25905", pins={"1": "CC2", "2": GND}),
    # USBLC6-2SC6: flow-through, connector side on 1/3, ESP32 side on 6/4.
    dict(ref="U5", sym="Power_Protection:USBLC6-2SC6", value="USBLC6-2SC6",
         fp="Package_TO_SOT_SMD:SOT-23-6", mpn="USBLC6-2SC6", lcsc="C7519",
         pins={"1": "USB_C_DP", "6": "USB_DP", "3": "USB_C_DN", "4": "USB_DN", "2": GND, "5": V5}),
    # --- 3.3 V ---------------------------------------------------------------
    dict(ref="U2", sym="Regulator_Linear:AMS1117-3.3", value="AMS1117-3.3",
         fp="Package_TO_SOT_SMD:SOT-223-3_TabPin2", mpn="AMS1117-3.3", lcsc="C6186",
         pins={"1": GND, "2": V3, "3": V5}),
    dict(ref="C4", sym="Device:C_Small", value="10uF", fp="Capacitor_SMD:C_0805_2012Metric",
         mpn="CL21A106KAYNNNE", lcsc="C15850", pins={"1": V5, "2": GND}),
    dict(ref="C5", sym="Device:C_Small", value="22uF", fp="Capacitor_SMD:C_0805_2012Metric",
         mpn="CL21A226MAQNNNE", lcsc="C45783", pins={"1": V3, "2": GND}),
    # --- Audio: MAX98357A ----------------------------------------------------
    # SD_MODE: 1M to VDD with the internal 100k pull-down gives ~0.45 V,
    # i.e. (L+R)/2 mono, like the Adafruit breakout. GAIN_SLOT open = 9 dB.
    dict(ref="U3", sym="Audio:MAX98357A", value="MAX98357A",
         fp="Package_DFN_QFN:TQFN-16-1EP_3x3mm_P0.5mm_EP1.23x1.23mm",
         mpn="MAX98357AETE+T", lcsc="C910544",
         pins={"1": "I2S_DOUT", "14": "I2S_LRCLK", "16": "I2S_BCLK", "4": "SD_MODE",
               "7": V5, "8": V5, "3": GND, "11": GND, "15": GND, "17": GND,
               "9": "SPK_P", "10": "SPK_N"}),
    dict(ref="R5", sym="Device:R_Small", value="1M", fp="Resistor_SMD:R_0402_1005Metric",
         mpn="0402WGF1004TCE", lcsc="C26083", pins={"1": V5, "2": "SD_MODE"}),
    dict(ref="C6", sym="Device:C_Small", value="10uF", fp="Capacitor_SMD:C_0805_2012Metric",
         mpn="CL21A106KAYNNNE", lcsc="C15850", pins={"1": V5, "2": GND}),
    dict(ref="C7", sym="Device:C_Small", value="100nF", fp="Capacitor_SMD:C_0402_1005Metric",
         mpn="CL05B104KO5NNNC", lcsc="C1525", pins={"1": V5, "2": GND}),
    # --- LEDs: 3.3 V -> 5 V data buffer --------------------------------------
    dict(ref="U4", sym="74xGxx:74AHCT1G125", value="74AHCT1G125",
         fp="Package_TO_SOT_SMD:SOT-23-5", mpn="SN74AHCT1G125DBVR", lcsc="",
         pins={"1": GND, "2": "LED_3V3", "3": GND, "4": "LED_5V", "5": V5}),
    dict(ref="C8", sym="Device:C_Small", value="100nF", fp="Capacitor_SMD:C_0402_1005Metric",
         mpn="CL05B104KO5NNNC", lcsc="C1525", pins={"1": V5, "2": GND}),
    dict(ref="R6", sym="Device:R_Small", value="330R", fp="Resistor_SMD:R_0402_1005Metric",
         mpn="0402WGF3300TCE", lcsc="C25104", pins={"1": "LED_5V", "2": "LED_DATA"}),
    dict(ref="C9", sym="Device:C_Small", value="22uF", fp="Capacitor_SMD:C_0805_2012Metric",
         mpn="CL21A226MAQNNNE", lcsc="C45783", pins={"1": V5, "2": GND}),
    # --- I2C pull-ups (most PN532 boards have their own; harmless together) ---
    dict(ref="R7", sym="Device:R_Small", value="4.7k", fp="Resistor_SMD:R_0402_1005Metric",
         mpn="0402WGF4701TCE", lcsc="C25900", pins={"1": V3, "2": "I2C_SDA"}),
    dict(ref="R8", sym="Device:R_Small", value="4.7k", fp="Resistor_SMD:R_0402_1005Metric",
         mpn="0402WGF4701TCE", lcsc="C25900", pins={"1": V3, "2": "I2C_SCL"}),
    # --- Connectors for leads -------------------------------------------------
    # NFC: JST SH 4-pin in the Qwiic / STEMMA QT order (GND, 3V3, SDA, SCL).
    dict(ref="J2", sym="Connector_Generic:Conn_01x04", value="NFC (Qwiic)",
         fp="Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal",
         mpn="SM04B-SRSS-TB(LF)(SN)", lcsc="",
         pins={"1": GND, "2": V3, "3": "I2C_SDA", "4": "I2C_SCL"}),
    # Speaker: JST PH 2-pin (common on small 4-8 ohm speakers).
    dict(ref="J3", sym="Connector_Generic:Conn_01x02", value="Speaker",
         fp="Connector_JST:JST_PH_S2B-PH-SM4-TB_1x02-1MP_P2.00mm_Horizontal",
         mpn="S2B-PH-SM4-TB(LF)(SN)", lcsc="",
         pins={"1": "SPK_P", "2": "SPK_N"}),
    # LEDs: JST PH 3-pin, 5V / DATA / GND (ring first, Mickey chained after it).
    dict(ref="J4", sym="Connector_Generic:Conn_01x03", value="LEDs",
         fp="Connector_JST:JST_PH_S3B-PH-SM4-TB_1x03-1MP_P2.00mm_Horizontal",
         mpn="S3B-PH-SM4-TB(LF)(SN)", lcsc="",
         pins={"1": V5, "2": "LED_DATA", "3": GND}),
]

# Nets driven only through passive pins get a PWR_FLAG in the schematic.
PWR_FLAGS = [V5, GND]

# Track widths (mm) per net; everything else uses the default.
POWER_NETS = {GND: 0.3, V5: 0.4, V3: 0.4}  # see the net classes in the .kicad_pro
