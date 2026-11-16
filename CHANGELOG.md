# Changelog

All notable changes to Magic bHAnds. The bridge firmware, reader firmware and
Home Assistant integration share one version number.

## [0.7.1] - 2026-11-16

### Security
- **Bridge and reader connections to Home Assistant are now encrypted.**
  Home Assistant gives each board its own key the first time it connects, so
  there's nothing to set up. Boards on 0.7.0 may show a one-off "disabled
  transport encryption" notice: confirm it, then install this update, and
  encryption is switched back on.
- **Unencrypted network firmware uploads are no longer accepted** by the
  installer firmware. Updates come through Home Assistant's Firmware update
  entity. "Take control" in the ESPHome Device Builder adds its own
  password-protected uploads.

### Added
- **Published firmware for the SCREEK BP2-POE**, built from the same shared
  MagicBand code as the bridge and reader. Install it from the web installer
  or the Device Builder, with no secrets needed. Updates then arrive through
  Home Assistant like the other boards. PSRAM is enabled for update headroom.
- CI fails if the single-file BP2-POE config drifts from the shared add-on.

### Fixed
- Starting a release from the Actions page can no longer be cancelled by a
  later push.

### Integration
- No functional changes; version bumped to match.

## [0.7.0] - 2026-11-16

First release with proper version numbers. Everything before this was
development builds (bridge 0.1.0–0.5.2, reader 0.6.0, integration 0.1.0–0.2.0).

### Added
- **Two-part project:** the MagicBand Bridge (Bluetooth effects for
  MagicBand+) and the MagicBand Reader (NFC tap point for original MagicBands
  and MagicBand+), tied together by the MagicBand integration.
- **Web installer for the reader**, alongside the bridge: no secrets or YAML
  needed, Wi-Fi set up in the browser, and updates over Wi-Fi from Home
  Assistant.
- **Integration icons and logo**, shown in Home Assistant 2026.3 and later.
- **`magicband.send` action**, which finds every bridge itself, and
  `magicband.list_bridges`.
- **The integration installs the *MagicBand+ notification* blueprint** and
  keeps it updated, including a copy imported from GitHub.
- **GitHub Releases** with firmware and the integration attached; CI checks
  that all versions match.

### Changed
- The blueprint now uses `magicband.send` and needs the MagicBand integration.
- Reader: LED data moved to GPIO10 (matches the Lonely Binary terminal base),
  and the I2S LRC/BCLK pins were swapped (GPIO5/GPIO6) for straight breadboard
  wiring.
- Reader devices get a unique name (`magicband-reader-xxxxxx`), like bridges.

### Fixed
- **Firmware updates over Wi-Fi failing** on bridges: the PSRAM on N16R8
  boards is now enabled, leaving memory for the HTTPS download alongside
  Bluetooth. Bridges on 0.5.2 or earlier need one USB re-install from the web
  installer to get this fix.

## Development history (before 0.7.0)

- **Bridge 0.5.x:** alternating E1/E2 prefix (more reliable repeats),
  experimental "both" prefix mode, MagicBand light on by default.
- **Bridge 0.4.x:** Bluetooth proxy scanning paused while broadcasting,
  +20 dBm on ESP32-S3.
- **Bridge 0.3.x:** multiple bridges, Command entity, optional Bluetooth
  proxy, reusable add-on package, SCREEK BP2-POE config.
- **Bridge 0.2.0:** decoded timing, RGB colour light, LED masks, animations.
- **Bridge 0.1.0:** first web-installable firmware.
- **Reader 0.6.0:** NFC reader with LED ring, Mickey head, sounds, on-device
  known bands.
- **Integration 0.1.0–0.2.0:** people and bands, reader sync, `magicband.send`.
