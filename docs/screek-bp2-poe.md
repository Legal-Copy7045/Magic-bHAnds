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
- **Re-created:** the Scan Interval and Scan Window numbers and the Scan Active
  Mode switch, with the same names and defaults (1100 ms, 1100 ms, on). The
  code behind them is ours, because SCREEK's isn't published. Changing one
  briefly restarts scanning. Settings survive reboots.
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

## 2. Create the device in the ESPHome Device Builder

1. Open the ESPHome Device Builder in Home Assistant and click **+ New device**,
   then **Continue**, give it any name, choose **ESP32-S3**, and **Skip** the
   install.
2. Click **Edit** on the new device and **replace everything** with:
   ```yaml
   packages:
     bp2:
       url: https://github.com/Legal-Copy7045/Magic-bHAnds
       ref: main
       files: [esphome/screek-bp2-poe.yaml]
       refresh: 1h
   ```
   This pulls the full config from GitHub, so improvements arrive without
   re-pasting. Click **Install** when you want them. To customise instead,
   paste the full contents of
   [`esphome/screek-bp2-poe.yaml`](../esphome/screek-bp2-poe.yaml).
3. Click **Secrets** (top right) and add a key on its own line:
   ```yaml
   bp2_api_key: "PASTE-A-32-BYTE-BASE64-KEY"
   ```
   To generate one, run
   `py -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"`,
   or copy the `key:` the Device Builder put in the new device before you
   replaced its contents.

## 3. First install over USB

The factory firmware's network updates are password-protected, so the first
install has to go over USB.

1. Plug the BP2-POE into the computer you're browsing from. Use Chrome or Edge.
2. In the Device Builder, open the device's **⋮** menu, choose **Install**,
   then **Plug into this computer**. Wait for the build, which takes a few
   minutes the first time, then pick its COM port.
   - If your Home Assistant isn't on HTTPS, choose **Manual download** instead,
     select the **Factory format** file, and flash it at
     https://web.esphome.io (Connect, then Install).
3. When it finishes, unplug it, connect Ethernet (and PoE), and it boots on
   the network as `screek-bp2-poe-xxxxxx`.

**Later updates never need USB.** They install over Ethernet: click
**Install** in the Device Builder and choose **Wirelessly**.

## 4. Reconnect in Home Assistant

Home Assistant knows the BP2-POE without encryption. After the install it will
show the device as needing attention: open **Settings → Devices & services →
ESPHome**, click **Reconfigure** on it, and enter the `bp2_api_key`. If
nothing prompts you, delete the old BP2-POE entry and add it again; it's
discovered automatically.

The Scan Interval, Scan Window and Scan Active Mode entities use the same
names as SCREEK's, so they should attach to your existing ones. If any old
entities show as unavailable, delete them.

## Recovering

If it doesn't come back on the network, plug it into USB and read its log at
https://web.esphome.io (Connect, then Logs), or restore your backup with
esptool.
