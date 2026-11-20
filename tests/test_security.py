"""Regression tests for the security review (see docs/security.md)."""

from __future__ import annotations

from datetime import timedelta
import random
import re
import shutil
import tempfile
import subprocess
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser, async_fire_time_changed

from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.magicband.readers import READER_LIST_CAPACITY
from homeassistant.helpers import issue_registry as ir
from tests.conftest import make_esphome_device
from custom_components.magicband.beacons import MAX_UNCLAIMED
from custom_components.magicband.const import DOMAIN
from custom_components.magicband.listener import EVENTS_PER_MINUTE
from custom_components.magicband.registry import MAX_UNASSIGNED_BANDS, normalize_uid, parse_uid

REPO = Path(__file__).resolve().parents[1]
BAND_X = "C0 0F 01 01 48 9E 24 36 F8 EF A8 42 C8 00 35 33 00"
TAG = "04AABBCCDDEEFF"


def _data(hass: HomeAssistant):
    return hass.config_entries.async_entries(DOMAIN)[0].runtime_data


def _beacon(hass: HomeAssistant, payload: str | bytes, rssi: int = -62, address: str = "11:22:33:44:55:66"):
    raw = bytes.fromhex(payload) if isinstance(payload, str) else payload
    return _data(hass).beacons.async_beacon(address, rssi, "hci0", raw)


def _random_beacon(rnd: random.Random) -> bytes:
    return bytes([0xC0, 0x0F, 1, 1, 50, *(rnd.getrandbits(8) for _ in range(8)), 0, 0x35, 0x33, 0])


def _notification(hass: HomeAssistant, notification_id: str):
    from homeassistant.components import persistent_notification

    return persistent_notification._async_get_or_create_notifications(hass).get(notification_id)


# ---------------------------------------------------------------------------- band IDs


def test_parse_uid_accepts_only_real_nfc_ids() -> None:
    assert parse_uid("04-53-65-2a-c0-5f-80") == "0453652AC05F80"
    assert parse_uid("04:53:65:2A") == "0453652A"
    assert parse_uid("04 53 65 2A C0 5F 80 11 22 33") == "0453652AC05F80112233"
    for bad in ("TEST", "", "!!!", "04-É3-65-2A", "０４５３６５２Ａ", "0453652AC05F8", "0453652AC05F80AA", None, 1234):
        assert parse_uid(bad) is None, bad
    assert normalize_uid("04-É3") == "043"  # lookups never keep non-ASCII characters


async def test_non_band_tags_from_a_reader_are_ignored(hass: HomeAssistant, setup_integration, reader_device) -> None:
    taps = []
    hass.bus.async_listen("magicband_tap", lambda e: taps.append(e.data))
    for tag in ("TEST", "!!!", "04-É3-65-2A", "０４５３６５２Ａ", 1234, None):
        hass.bus.async_fire("tag_scanned", {"tag_id": tag, "device_id": reader_device.id})
    hass.bus.async_fire("tag_scanned", {"device_id": reader_device.id})  # no tag_id at all
    await hass.async_block_till_done()
    assert taps == []
    assert _data(hass).registry.bands == []


async def test_assigning_an_invalid_band_id_is_refused(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Kid"}, blocking=True)
    for bad in ("TEST", "04-É3-65-2A"):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "assign_band", {"band": bad, "person": "Kid"}, blocking=True)
    assert _data(hass).registry.allowed_uids() == []


async def test_stored_invalid_ids_are_never_allowed(hass: HomeAssistant, hass_storage) -> None:
    hass_storage["magicband.registry"] = {
        "version": 1,
        "data": {
            "people": [{"id": "p1", "name": "Kid", "ha_person": None, "allowed": True}, {"broken": True}, "junk"],
            "bands": [
                {"uid": "TEST", "person_id": "p1"},
                {"uid": "0453652AC05F80", "person_id": "p1"},
                {"no_uid": 1},
            ],
        },
    }
    hass_storage["magicband.bluetooth"] = {"version": 1, "data": {"bands": [{"id": "zz"}, "junk"], "encrypted": "x"}}
    entry = MockConfigEntry(domain=DOMAIN, title="MagicbHAnds", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)  # a damaged store doesn't stop setup
    await hass.async_block_till_done()
    registry = entry.runtime_data.registry
    assert [p.name for p in registry.people] == ["Kid"]
    assert registry.allowed_uids() == ["0453652AC05F80"]
    await hass.services.async_call(DOMAIN, "remove_band", {"band": "TEST"}, blocking=True)  # can still be removed
    assert registry.get_band("TEST") is None
    assert entry.runtime_data.beacons.bands == {}


async def test_unassigned_bands_are_capped(hass: HomeAssistant, setup_integration, reader_device) -> None:
    for i in range(MAX_UNASSIGNED_BANDS + 20):
        hass.bus.async_fire("tag_scanned", {"tag_id": f"04AABBCCDD{i:04X}", "device_id": reader_device.id})
        await hass.async_block_till_done()
    bands = _data(hass).registry.bands
    assert len(bands) == MAX_UNASSIGNED_BANDS
    assert bands[0].uid == f"04AABBCCDD{MAX_UNASSIGNED_BANDS + 19:04X}"  # the newest is kept


# ---------------------------------------------------------------------------- automatic Bluetooth pairing


async def _tap_then_beacon(hass: HomeAssistant, freezer: FrozenDateTimeFactory, reader_device, tag: str) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": tag, "device_id": reader_device.id})
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=10))
    _beacon(hass, BAND_X)
    freezer.tick(timedelta(minutes=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_auto_pairing_never_lets_an_unknown_tag_in(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Casey"}, blocking=True)
    band = _beacon(hass, BAND_X)
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "person": "Casey"}, blocking=True)

    await _tap_then_beacon(hass, freezer, reader_device, TAG)  # someone taps a blank tag

    registry = _data(hass).registry
    assert registry.allowed_uids() == []
    assert registry.get_band(TAG).person_id is None
    assert band.band_uid is None and band.person_id is not None
    assert _notification(hass, f"{DOMAIN}_pair_{TAG}") is not None  # asks for a manual link instead


async def test_auto_pairing_still_links_the_owners_own_band(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Casey"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": TAG, "person": "Casey"}, blocking=True)
    band = _beacon(hass, BAND_X)
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "person": "Casey"}, blocking=True)

    await _tap_then_beacon(hass, freezer, reader_device, TAG)

    assert band.band_uid == TAG  # same owner on both sides: nothing about access changes
    assert _notification(hass, f"{DOMAIN}_pair_{TAG}") is not None  # and it says so


# ---------------------------------------------------------------------------- who can call what


ADMIN_ONLY = [
    ("add_person", {"name": "Mallory"}),
    ("update_person", {"person": "Casey", "allowed": True}),
    ("remove_person", {"person": "Casey"}),
    ("assign_band", {"band": TAG, "person": "Casey"}),
    ("unassign_band", {"band": TAG}),
    ("remove_band", {"band": TAG}),
    ("list", {}),
    ("list_bluetooth_bands", {}),
    ("list_heard", {}),
    ("link_bluetooth", {"bluetooth_band": "last", "person": "Casey"}),
    ("unlink_bluetooth", {"bluetooth_band": "last"}),
    ("forget_bluetooth", {"bluetooth_band": "last"}),
    ("set_band_access", {"band": TAG, "from": "07:00:00"}),
    ("enrol", {"person": "Casey"}),
    ("stop_enrolment", {}),
    ("history", {}),
    ("answer", {"device_id": "x", "allow": True}),
]


@pytest.mark.parametrize(("service", "data"), ADMIN_ONLY, ids=[s for s, _ in ADMIN_ONLY])
async def test_access_changes_and_band_lists_need_an_admin(
    hass: HomeAssistant, setup_integration, hass_read_only_user: MockUser, service: str, data: dict
) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Casey"}, blocking=True)
    response = service in ("list", "list_bluetooth_bands", "list_heard", "history")
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, service, data, blocking=True, context=Context(user_id=hass_read_only_user.id), return_response=response
        )
    assert _data(hass).registry.allowed_uids() == []


# ---------------------------------------------------------------------------- magicband.send


@pytest.fixture
def bridge(hass: HomeAssistant) -> str:
    entry = MockConfigEntry(domain="esphome", title="Bridge")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, connections={(dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:09")}
    )
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "light", "esphome", "light1", device_id=device.id, original_name="MagicBand", suggested_object_id="bridge_magicband"
    )
    return ent_reg.async_get_or_create(
        "text", "esphome", "cmd1", device_id=device.id, original_name="Command", suggested_object_id="bridge_command"
    ).entity_id


@pytest.fixture
def text_calls(hass: HomeAssistant) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("text", "set_value", handler)
    return calls


async def test_send_only_targets_bridges(hass: HomeAssistant, setup_integration, bridge, text_calls) -> None:
    for target in (["text.alarm_code"], [bridge, "text.alarm_code"]):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "send", {"command": {"x": 1}, "bridges": target}, blocking=True)
    assert text_calls == []


async def test_send_uses_the_callers_context(
    hass: HomeAssistant, setup_integration, bridge, text_calls, hass_read_only_user: MockUser
) -> None:
    ctx = Context(user_id=hass_read_only_user.id)
    await hass.services.async_call(DOMAIN, "send", {"effect": "ping", "bridges": [bridge]}, blocking=True, context=ctx)
    await hass.services.async_call(DOMAIN, "send", {"effect": "ping"}, blocking=True, context=ctx)  # default: every bridge
    assert [c.data["entity_id"] for c in text_calls] == [[bridge], [bridge]]
    assert all(c.context.user_id == hass_read_only_user.id for c in text_calls)


# ---------------------------------------------------------------------------- reader sync


def _esphome_device(hass: HomeAssistant, node: str, model: str) -> dr.DeviceEntry:
    return make_esphome_device(hass, node, model)


async def _with_readers(hass: HomeAssistant, behaviour: dict[str, Exception | None]) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []
    for name, error in behaviour.items():
        if not name.startswith("rogue"):
            _esphome_device(hass, name, "magicband-reader")

        async def handler(call: ServiceCall, name=name, error=error) -> None:
            sent.append((name, call.data["bands"]))
            if error is not None:
                raise error

        hass.services.async_register("esphome", f"{name}_set_known_bands", handler)
    return sent


async def test_sync_reports_readers_that_refuse_the_list(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Casey"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": TAG, "person": "Casey"}, blocking=True)
    await _with_readers(hass, {"front": None, "garage": HomeAssistantError("Too many bands")})
    result = await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert result == {"readers": 2, "applied": 1, "failed": ["garage"]}
    issues = [i for (d, i) in ir.async_get(hass).issues if d == DOMAIN and i.startswith("reader_sync_failed")]
    assert len(issues) == 1
    assert ir.async_get(hass).async_get_issue(DOMAIN, issues[0]).translation_placeholders["error"] == "Too many bands"

    hass.services.async_remove("esphome", "garage_set_known_bands")
    _ = await _with_readers(hass, {"rogue_fixed": None})  # garage comes back working
    hass.services.async_register("esphome", "garage_set_known_bands", lambda call: None)
    result = await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert result["failed"] == []
    assert ir.async_get(hass).async_get_issue(DOMAIN, issues[0]) is None  # cleared once the reader has it


async def test_sync_warns_when_the_list_is_too_long_for_readers(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Everyone"}, blocking=True)
    registry = _data(hass).registry
    n = READER_LIST_CAPACITY // 15 + 1  # 7-byte IDs take 15 characters each
    for i in range(n):
        await hass.services.async_call(DOMAIN, "assign_band", {"band": f"04AABBCCDD{i:04X}", "person": "Everyone"}, blocking=True)
    await _with_readers(hass, {"front": None})
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert len(registry.allowed_uids()) == n
    assert ir.async_get(hass).async_get_issue(DOMAIN, "list_too_long") is not None


# ---------------------------------------------------------------------------- Bluetooth flooding


async def test_made_up_beacons_cant_fill_home_assistant(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Casey"}, blocking=True)
    mine = _beacon(hass, BAND_X)
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": mine.id, "person": "Casey"}, blocking=True)
    rnd = random.Random(7)
    for i in range(MAX_UNCLAIMED * 4):
        _beacon(hass, _random_beacon(rnd), address=f"{i:012x}")
    await hass.async_block_till_done()
    bands = _data(hass).beacons.bands
    assert len(bands) == MAX_UNCLAIMED + 1  # the cap, plus Casey's band, which is never dropped
    assert mine.id in bands
    assert _beacon(hass, BAND_X) is mine  # still recognised


async def test_unclaimed_bands_that_went_away_make_room(
    hass: HomeAssistant, setup_integration, freezer: FrozenDateTimeFactory
) -> None:
    rnd = random.Random(8)
    for i in range(MAX_UNCLAIMED):
        _beacon(hass, _random_beacon(rnd), address=f"{i:012x}")
    freezer.tick(timedelta(hours=2))  # all of them away
    new = _beacon(hass, BAND_X)
    assert new is not None and len(_data(hass).beacons.bands) == MAX_UNCLAIMED


async def test_heard_events_are_rate_limited(hass: HomeAssistant, setup_integration) -> None:
    events = []
    hass.bus.async_listen("magicband_heard", lambda e: events.append(e))
    listener = _data(hass).listener
    for i in range(EVENTS_PER_MINUTE * 3):
        listener.async_heard(f"{i:012x}", None, -70, "hci0", bytes([0xC0, i % 256]))
    await hass.async_block_till_done()
    assert len(events) == EVENTS_PER_MINUTE
    assert len(listener.bands) <= 200  # the history stays bounded too


# ---------------------------------------------------------------------------- reader firmware (compiled on the host)

_HARNESS = r"""
#include <algorithm>
#include <array>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <string>
#include "%s"
namespace magicband = esphome::magicband;
static std::array<char, %d> known_list;
static std::string sync_error;
static magicband::ReaderKey pair_key{};
#define id(x) x
#define ESP_LOGI(tag, ...) std::printf(__VA_ARGS__), std::printf("\n")
#define ESP_LOGW(tag, ...) std::printf(__VA_ARGS__), std::printf("\n")
#define ESP_LOGE(tag, ...) std::printf(__VA_ARGS__), std::printf("\n")
static void set_known_bands(const std::string &bands, const std::string &key) {
%s
}
int main(int argc, char **argv) {
  const char *k = std::getenv("KEY");
  const std::string key = k ? k : "";
  set_known_bands(argv[1], "");
  if (const char *p = std::getenv("PAIR")) magicband::reader_pair(pair_key, p, false);
  set_known_bands(argv[2], key);
  std::printf("LIST=%%s\nERROR=%%s\n", known_list.data(), sync_error.c_str());
}
"""


def _reader_firmware(tmp_path: Path) -> Path:
    if shutil.which("g++") is None:
        pytest.skip("no C++ compiler")
    yaml = (REPO / "esphome" / "magicband-reader.yaml").read_text()
    block = yaml.split("- action: set_known_bands", 1)[1].split("- lambda: |-", 1)[1]
    body = block.split("- component.update: known_band_count", 1)[0]
    src = tmp_path / "reader.cpp"
    size = int(re.search(r"id: known_list\s+type: std::array<char, (\d+)>", yaml).group(1))
    assert size - 1 == READER_LIST_CAPACITY  # the integration and the firmware agree
    src.write_text(_HARNESS % (REPO / "components" / "magicband" / "reader_key.h", size, body))
    exe = tmp_path / "reader"
    subprocess.run(["g++", "-std=c++17", "-o", str(exe), str(src)], check=True, capture_output=True)
    return exe


def _run(exe: Path, first: str, second: str, env: dict[str, str] | None = None) -> dict[str, str]:
    out = subprocess.run([str(exe), first, second], check=True, capture_output=True, text=True, env=env).stdout
    return dict(re.findall(r"^(LIST|ERROR)=(.*)$", out, re.M))


def test_reader_applies_a_valid_list(tmp_path: Path) -> None:
    exe = _reader_firmware(tmp_path)
    result = _run(exe, "", "04-53-65-2a-c0-5f-80,0453652A")
    assert result == {"LIST": ",0453652AC05F80,0453652A,", "ERROR": ""}


def test_reader_never_keeps_a_revoked_band(tmp_path: Path) -> None:
    exe = _reader_firmware(tmp_path)
    too_many = ",".join(f"04AABBCCDD{i:04X}" for i in range(READER_LIST_CAPACITY // 15 + 1))
    result = _run(exe, "0453652AC05F80", too_many)  # allowed, then a list too long to store
    assert result["LIST"] == ""  # emptied: the old band isn't still allowed
    assert result["ERROR"].startswith("Too many bands")


KEY = "a1" * 32


def test_paired_reader_refuses_a_list_without_its_key(tmp_path: Path) -> None:
    """Other Home Assistant users can call ESPHome actions; once paired, only the integration's key works."""
    exe = _reader_firmware(tmp_path)
    result = _run(exe, "0453652AC05F80", "04AABBCCDD0001", env={"PAIR": KEY, "KEY": ""})
    assert result["LIST"] == ",0453652AC05F80," and "Wrong key" in result["ERROR"]  # unchanged
    result = _run(exe, "0453652AC05F80", "04AABBCCDD0001", env={"PAIR": KEY, "KEY": "b2" * 32})
    assert result["LIST"] == ",0453652AC05F80,"
    result = _run(exe, "0453652AC05F80", "04AABBCCDD0001", env={"PAIR": KEY, "KEY": KEY})
    assert result["LIST"] == ",04AABBCCDD0001," and result["ERROR"] == ""


def test_pairing_rules() -> None:
    """A paired reader takes a new key only in its power-on window (reader_key.h, compiled on the host)."""
    if shutil.which("g++") is None:
        pytest.skip("no C++ compiler")
    src = Path(tempfile.mkdtemp()) / "pair.cpp"
    src.write_text(
        f'#include <cstdio>\n#include "{REPO / "components" / "magicband" / "reader_key.h"}"\n'
        """using namespace esphome::magicband;
int main() {
  ReaderKey k{};
  const std::string a(64, 'a'), b(64, 'b');
  std::printf("%d", reader_key_ok(k, ""));                    // unpaired: anyone (as before)
  std::printf("%d", reader_pair(k, "nothex!", false).empty()); // a bad key is refused
  std::printf("%d", reader_pair(k, a, false).empty());         // first pairing
  std::printf("%d", reader_key_ok(k, a));
  std::printf("%d", reader_key_ok(k, ""));                     // paired: no key, no entry
  std::printf("%d", reader_pair(k, b, false).empty());         // another key, outside the window
  std::printf("%d", reader_key_ok(k, a));                      // still the first key
  std::printf("%d", reader_pair(k, b, true).empty());          // after a power-on: re-paired
  std::printf("%d", reader_key_ok(k, b));
}
""")
    exe = src.with_suffix("")
    subprocess.run(["g++", "-std=c++17", "-o", str(exe), str(src)], check=True, capture_output=True)
    assert subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout == "101100111"


@pytest.mark.parametrize("bad", ["TEST", "0453652AC05F8", "04É3652AC05F80", "0453652AC05F80;rm"])
def test_reader_rejects_malformed_lists(tmp_path: Path, bad: str) -> None:
    exe = _reader_firmware(tmp_path)
    result = _run(exe, "0453652AC05F80", f"0453652A,{bad}")
    assert result["LIST"] == "" and result["ERROR"]


# ---------------------------------------------------------------------------- who counts as a reader


async def test_only_esphome_readers_count(hass: HomeAssistant, setup_integration) -> None:
    """A device from another integration (e.g. a phone registered with the mobile app, where any user
    picks the model and name) can't pose as a reader."""
    taps = []
    hass.bus.async_listen("magicband_tap", lambda e: taps.append(e.data))
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Alice"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": TAG, "person": "Alice"}, blocking=True)
    phone_entry = MockConfigEntry(domain="mobile_app", title="Phone")
    phone_entry.add_to_hass(hass)
    fake = dr.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id,
        identifiers={("mobile_app", "fake")},
        model="magicband-reader",
        name="Front Door MagicBand Reader",
    )
    hass.bus.async_fire("tag_scanned", {"tag_id": TAG, "device_id": fake.id})
    await hass.async_block_till_done()
    assert taps == []

    real = _esphome_device(hass, "front-door", "magicband-reader")
    hass.bus.async_fire("tag_scanned", {"tag_id": TAG, "device_id": real.id})
    await hass.async_block_till_done()
    assert [t["allowed"] for t in taps] == [True]
    assert taps[0]["reader_device_id"] == real.id


async def test_allowed_list_only_goes_to_readers(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Alice"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": TAG, "person": "Alice"}, blocking=True)
    sent = await _with_readers(hass, {"front": None})
    _esphome_device(hass, "smart-plug", "some-plug")  # an ESPHome device that isn't a reader...
    for name in ("smart_plug", "rogue_plug"):  # ...and one with no device at all, both declaring the action

        async def handler(call: ServiceCall, name=name) -> None:
            sent.append((name, call.data["bands"]))

        hass.services.async_register("esphome", f"{name}_set_known_bands", handler)
    result = await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert result["readers"] == 1
    assert [name for name, _ in sent] == ["front"]


# ---------------------------------------------------------------------------- second-round limits


async def test_replayed_beacons_are_rate_limited(hass: HomeAssistant, setup_integration) -> None:
    seen = []
    hass.bus.async_listen("magicband_band_seen", lambda e: seen.append(e))
    for i in range(500):
        p = bytearray(bytes.fromhex(BAND_X))
        p[4] = 50 + i % 50  # a replaying attacker can change the level byte too
        _beacon(hass, bytes(p), address=f"{i:012x}")
    await hass.async_block_till_done()
    assert len(seen) == 1
    band = next(iter(_data(hass).beacons.bands.values()))
    assert band.beacons == 1 and band.level == 50


async def test_beacons_heard_by_several_adapters_all_count(hass: HomeAssistant, setup_integration) -> None:
    beacons = _data(hass).beacons
    for source, rssi in (("hci0", -80), ("proxy1", -55), ("proxy2", -70)):
        beacons.async_beacon("11:22:33:44:55:66", rssi, source, bytes.fromhex(BAND_X))
    band = next(iter(beacons.bands.values()))
    assert set(band.heard) == {"hci0", "proxy1", "proxy2"}
    assert band.closest()[0] == "proxy1"


async def test_auto_linked_bands_still_count_towards_the_cap(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    rnd = random.Random(9)
    for i in range(MAX_UNCLAIMED + 15):
        hass.bus.async_fire("tag_scanned", {"tag_id": f"04AABBCCDD{i:04X}", "device_id": reader_device.id})
        await hass.async_block_till_done()
        _beacon(hass, _random_beacon(rnd), address=f"{i:012x}")
        freezer.tick(timedelta(minutes=21))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert len(_data(hass).beacons.bands) <= MAX_UNCLAIMED


async def test_band_type_doesnt_protect_unassigned_bands(hass: HomeAssistant, setup_integration, reader_device) -> None:
    hass.bus.async_fire("tag_scanned", {"tag_id": "04AABBCCDD0000", "device_id": reader_device.id})
    await hass.async_block_till_done()
    _data(hass).registry.set_band_type("04AABBCCDD0000", "classic")  # any user can do this through the select
    for i in range(1, MAX_UNASSIGNED_BANDS + 1):
        hass.bus.async_fire("tag_scanned", {"tag_id": f"04AABBCCDD{i:04X}", "device_id": reader_device.id})
        await hass.async_block_till_done()
    assert _data(hass).registry.get_band("04AABBCCDD0000") is None
    assert len(_data(hass).registry.bands) == MAX_UNASSIGNED_BANDS


async def test_send_is_rate_limited_per_bridge(hass: HomeAssistant, setup_integration, bridge, text_calls) -> None:
    from custom_components.magicband.bridges import MAX_SENDS_PER_MINUTE

    for _ in range(MAX_SENDS_PER_MINUTE):
        await hass.services.async_call(DOMAIN, "send", {"effect": "ping"}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "send", {"effect": "ping"}, blocking=True)
    assert len(text_calls) == MAX_SENDS_PER_MINUTE


@pytest.mark.parametrize("command", [{"effect": "raw", "hex": "E9", "duration_ms": 600000}, {"effect": "wake", "seconds": 3600},
                                     {"effect": "wake", "seconds": "lots"}])
async def test_raw_commands_have_the_same_time_limits(
    hass: HomeAssistant, setup_integration, bridge, text_calls, command: dict
) -> None:
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "send", {"command": command}, blocking=True)
    await hass.services.async_call(DOMAIN, "send", {"command": {"effect": "raw", "hex": "E9", "duration_ms": 5000}}, blocking=True)
    assert len(text_calls) == 1


_COLOUR_HARNESS = r"""
#include <algorithm>
#include <array>
#include <cctype>
#include <cstdio>
#include <string>
#include "%s"
namespace magicband = esphome::magicband;
static std::array<char, %d> band_colours;
static std::string sync_error;
static magicband::ReaderKey pair_key{};
#define id(x) x
#define ESP_LOGI(tag, ...) std::printf(__VA_ARGS__), std::printf("\n")
#define ESP_LOGW(tag, ...) std::printf(__VA_ARGS__), std::printf("\n")
static void set_band_colours(const std::string &colours, const std::string &key = "") {
%s
}
int main(int argc, char **argv) {
  set_band_colours(argv[1]);
  std::printf("LIST=%%s\nERROR=%%s\n", band_colours.data(), sync_error.c_str());
}
"""


def _colour_firmware(tmp_path: Path) -> Path:
    if shutil.which("g++") is None:
        pytest.skip("no C++ compiler")
    yaml = (REPO / "esphome" / "magicband-reader.yaml").read_text()
    block = yaml.split("- action: set_band_colours", 1)[1].split("- lambda: |-", 1)[1]
    body = block.split("- api.respond:", 1)[0]
    size = int(re.search(r"id: band_colours\s+type: std::array<char, (\d+)>", yaml).group(1))
    src = tmp_path / "colours.cpp"
    src.write_text(_COLOUR_HARNESS % (REPO / "components" / "magicband" / "reader_key.h", size, body))
    exe = tmp_path / "colours"
    subprocess.run(["g++", "-std=c++17", "-o", str(exe), str(src)], check=True, capture_output=True)
    return exe


def test_reader_takes_welcome_colours(tmp_path: Path) -> None:
    exe = _colour_firmware(tmp_path)
    out = subprocess.run([str(exe), "0453652AC05F80=Purple,04-AA-BB-CC=Warm white"], check=True, capture_output=True, text=True).stdout
    assert dict(re.findall(r"^(LIST|ERROR)=(.*)$", out, re.M)) == {"LIST": ",0453652AC05F80=Purple,04AABBCC=Warm white,", "ERROR": ""}


@pytest.mark.parametrize("bad", ["0453652AC05F80=Plaid", "TEST=Red", "0453652AC05F80", "04;53652AC05F80=Red"])
def test_reader_rejects_bad_welcome_colours(tmp_path: Path, bad: str) -> None:
    exe = _colour_firmware(tmp_path)
    out = subprocess.run([str(exe), bad], check=True, capture_output=True, text=True).stdout
    result = dict(re.findall(r"^(LIST|ERROR)=(.*)$", out, re.M))
    assert result["LIST"] == "" and result["ERROR"]


def test_reader_colours_match_the_integration() -> None:
    from custom_components.magicband.const import READER_COLOURS

    yaml = (REPO / "esphome" / "magicband-reader.yaml").read_text()
    options = re.search(r"id: welcome_colour.*?options:\n((?:\s+- \"[^\"]+\"\n)+)", yaml, re.S).group(1)
    assert re.findall(r'"([^"]+)"', options) == READER_COLOURS


def test_reader_never_touches_the_ring_before_boot_finishes() -> None:
    """A setting restored at start-up runs its on_value before the ring exists (0.9.5, 0.10.9 boot crashes).

    Every handler in the reader firmware that runs reader_idle or turns the ring on must check ring_ready.
    """
    import yaml as pyyaml

    class Loader(pyyaml.SafeLoader):
        pass

    Loader.add_multi_constructor("!", lambda loader, suffix, node: loader.construct_scalar(node)
                                 if isinstance(node, pyyaml.ScalarNode) else None)
    cfg = pyyaml.load((REPO / "esphome" / "magicband-reader.yaml").read_text(), Loader=Loader)

    def touches_ring(actions) -> bool:
        text = repr(actions)
        return "reader_idle" in text or "'ring'" in text

    bad = []
    for domain in ("select", "number", "switch"):
        for item in cfg.get(domain) or []:
            for key in ("on_value", "on_turn_on", "on_turn_off"):
                if item.get(key) and touches_ring(item[key]) and "ring_ready" not in repr(item[key]):
                    bad.append(f"{domain} {item.get('id') or item.get('name')} {key}")
    for key in ("on_client_connected", "on_client_disconnected"):
        actions = (cfg.get("api") or {}).get(key)
        if actions and touches_ring(actions) and "ring_ready" not in repr(actions):
            bad.append(f"api {key}")
    assert bad == []


OPEN_TO_EVERYONE = {"send", "sync", "play_show", "list_bridges"}


async def test_only_these_actions_are_open_to_every_user(hass: HomeAssistant, setup_integration) -> None:
    """Everything else changes access or reveals band IDs, so it needs an administrator."""
    from homeassistant.helpers.service import async_get_all_descriptions  # noqa: F401 - imported for its side effects

    services = set(hass.services.async_services_for_domain(DOMAIN))
    admin = {s for s in services if s not in OPEN_TO_EVERYONE}
    assert OPEN_TO_EVERYONE <= services
    assert {s for s, _ in ADMIN_ONLY} == admin, "a new action must be added to ADMIN_ONLY (or made admin-only)"


async def test_sync_is_rate_limited(hass: HomeAssistant, setup_integration) -> None:
    from homeassistant.exceptions import ServiceValidationError

    for _ in range(6):
        await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "sync", {}, blocking=True)
