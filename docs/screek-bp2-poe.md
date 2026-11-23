# SCREEK BP2-POE as a MagicBand bridge

The SCREEK BP2-POE is an ESP32-S3 Bluetooth proxy with W5500 Ethernet and PoE.
`esphome/screek-bp2-poe.yaml` rebuilds its factory firmware from the boot log
and adds the MagicBand add-on. It keeps working as a Bluetooth proxy, and it
also becomes a MagicBand bridge that the blueprint's "all bridges" default
picks up automatically.

What changes compared with the factory firmware:

- **Kept:** Ethernet, the Bluetooth proxy (active, 4 connections,
  1100 ms continuous scanning), the Identify LED, the diagnostic sensors, and
  the Reboot, Safe Mode Boot and Factory Reset buttons.
- **Added:** a **Bluetooth proxy** switch (under Configuration), the same as
  the MagicBand Bridge's. It's on by default, so the board stays a proxy unless
  you turn it off.
- **Re-created:** the Scan Interval and Scan Window numbers, with the same
  names and defaults (1100 ms, 1100 ms). The code behind them is ours,
  because SCREEK's isn't published. Changing one briefly restarts scanning.
  Settings survive reboots.
- **Removed:** the Scan Active Mode switch. Home Assistant now chooses
  active or passive scanning itself (see below), and the switch fought that
  choice: Home Assistant then reported the scanner as broken.
- **Added:** MagicBand entities and actions, and encryption on the connection
  to Home Assistant and on network updates. The factory firmware had neither.

## 1. Back up the factory firmware (recommended)

Plug the BP2-POE's USB-C into your computer. On Windows, in PowerShell:

```powershell
py -m pip install esptool
py -m esptool --chip esp32s3 --port COM4 --baud 921600 read-flash 0 0x1000000 screek-bp2-poe-backup.bin
py -m esptool --chip esp32s3 --port COM4 verify-flash 0 screek-bp2-poe-backup.bin
```

To restore it later:

```powershell
py -m esptool --chip esp32s3 --port COM4 --baud 921600 write-flash 0 screek-bp2-poe-backup.bin
```

SCREEK's own web installer (tool.screek.io) can also reinstall a fresh copy
of the factory firmware.

## 2. Install

Either way needs **no secrets**. The connection to Home Assistant is
encrypted, and Home Assistant gives the board its own key when it first
connects.

**From the web installer:** plug the BP2-POE's USB-C into your computer, open
https://legal-copy7045.github.io/Magic-bHAnds/ in Chrome or Edge, and click
**Install on a BP2-POE**. Then connect Ethernet/PoE.

**From the ESPHome Device Builder** (e.g. if it's already running ESPHome
firmware from here): make the device's config
```yaml
substitutions:
  name: screek-bp2-poe-849a4c        # your board's hostname
  friendly_name: SCREEK BP2-POE 849a4c

packages:
  bp2:
    url: https://github.com/Legal-Copy7045/Magic-bHAnds
    ref: main
    files: [esphome/screek-bp2-poe.yaml]
    refresh: 1h

esphome:
  name_add_mac_suffix: false
```
or paste the single-file
[`esphome/screek-bp2-poe-standalone.yaml`](../esphome/screek-bp2-poe-standalone.yaml),
then **Install → Wirelessly**. The full hostname matters: the Device Builder
can't find a board by a name generated on the device. That's why the config
sets it, with `name_add_mac_suffix: false`.

**Switching from your own Device Builder firmware:** *Install → Wirelessly*
needs the config to include ESPHome's network upload method, which the
published firmware leaves out (it updates from GitHub). In your Device
Builder copy, replace the `ota:` section with the following, using the key
the board currently has (e.g. `bp2_api_key` in **Secrets**):
```yaml
ota:
  - platform: http_request
  - platform: esphome
    encryption:
      key: !secret bp2_api_key
```
This also keeps wireless installs from the Device Builder working later.
Alternatively, install once over USB from the web installer.

**Factory SCREEK firmware has an update password,** so the first install
over it must be over USB.

## 3. In Home Assistant

- If Home Assistant says the device **disabled transport encryption**,
  confirm it. Home Assistant then sets up a new key with the board
  automatically.
- From now on, new firmware appears as a **Firmware** update on the device,
  and installs over Ethernet. You don't need the Device Builder again. Turn on
  **Automatic updates** to have it install new releases by itself between 3
  and 4 am (local time).
- The Scan Interval and Scan Window entities use SCREEK's names, so they
  attach to your existing ones. The old **Scan Active Mode** entity shows as
  unavailable after the update: delete it from the device page.
- **Active or passive scanning** is set in Home Assistant: **Settings →
  Devices & services → ESPHome → the BP2-POE → Configure → Bluetooth
  scanning mode** (Auto, Active or Passive). Active scanning also asks
  devices for their names and extra data; passive only listens, and uses
  less airtime. Either works for MagicBand broadcasts and for hearing bands.

## Recovering

If it doesn't come back on the network, plug it into USB and read its log at
https://web.esphome.io (Connect, then Logs), or restore your backup with
esptool.
