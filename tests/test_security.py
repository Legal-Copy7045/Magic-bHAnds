"""Regression tests for the security review (see docs/security.md)."""

from __future__ import annotations

from datetime import timedelta
import random
import re
import shutil
import subprocess
from pathlib import Path

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, MockUser, async_fire_time_changed

from homeassistant.core import Context, HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.magicband import READER_LIST_CAPACITY, SYNC_NOTIFICATION_ID
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
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Andrew"}, blocking=True)
    band = _beacon(hass, BAND_X)
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "person": "Andrew"}, blocking=True)

    await _tap_then_beacon(hass, freezer, reader_device, TAG)  # someone taps a blank tag

    registry = _data(hass).registry
    assert registry.allowed_uids() == []
    assert registry.get_band(TAG).person_id is None
    assert band.band_uid is None and band.person_id is not None
    assert _notification(hass, f"{DOMAIN}_pair_{TAG}") is not None  # asks for a manual link instead


async def test_auto_pairing_still_links_the_owners_own_band(
    hass: HomeAssistant, setup_integration, reader_device, freezer: FrozenDateTimeFactory
) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Andrew"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": TAG, "person": "Andrew"}, blocking=True)
    band = _beacon(hass, BAND_X)
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": band.id, "person": "Andrew"}, blocking=True)

    await _tap_then_beacon(hass, freezer, reader_device, TAG)

    assert band.band_uid == TAG  # same owner on both sides: nothing about access changes
    assert _notification(hass, f"{DOMAIN}_pair_{TAG}") is not None  # and it says so


# ---------------------------------------------------------------------------- who can call what


ADMIN_ONLY = [
    ("add_person", {"name": "Mallory"}),
    ("update_person", {"person": "Andrew", "allowed": True}),
    ("remove_person", {"person": "Andrew"}),
    ("assign_band", {"band": TAG, "person": "Andrew"}),
    ("unassign_band", {"band": TAG}),
    ("remove_band", {"band": TAG}),
    ("list", {}),
    ("list_bluetooth_bands", {}),
    ("list_heard", {}),
    ("link_bluetooth", {"bluetooth_band": "last", "person": "Andrew"}),
    ("unlink_bluetooth", {"bluetooth_band": "last"}),
    ("forget_bluetooth", {"bluetooth_band": "last"}),
]


@pytest.mark.parametrize(("service", "data"), ADMIN_ONLY, ids=[s for s, _ in ADMIN_ONLY])
async def test_access_changes_and_band_lists_need_an_admin(
    hass: HomeAssistant, setup_integration, hass_read_only_user: MockUser, service: str, data: dict
) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Andrew"}, blocking=True)
    response = service in ("list", "list_bluetooth_bands", "list_heard")
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


async def _with_readers(hass: HomeAssistant, behaviour: dict[str, Exception | None]) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []
    for name, error in behaviour.items():

        async def handler(call: ServiceCall, name=name, error=error) -> None:
            sent.append((name, call.data["bands"]))
            if error is not None:
                raise error

        hass.services.async_register("esphome", f"{name}_set_known_bands", handler)
    return sent


async def test_sync_reports_readers_that_refuse_the_list(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Andrew"}, blocking=True)
    await hass.services.async_call(DOMAIN, "assign_band", {"band": TAG, "person": "Andrew"}, blocking=True)
    await _with_readers(hass, {"front": None, "garage": HomeAssistantError("Too many bands")})
    result = await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert result == {"readers": 2, "applied": 1, "failed": ["garage_set_known_bands"]}
    assert "Too many bands" in _notification(hass, SYNC_NOTIFICATION_ID)["message"]

    hass.services.async_remove("esphome", "garage_set_known_bands")
    result = await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert result["failed"] == []
    assert _notification(hass, SYNC_NOTIFICATION_ID) is None  # cleared once every reader has it


async def test_sync_warns_when_the_list_is_too_long_for_readers(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Everyone"}, blocking=True)
    registry = _data(hass).registry
    n = READER_LIST_CAPACITY // 15 + 1  # 7-byte IDs take 15 characters each
    for i in range(n):
        await hass.services.async_call(DOMAIN, "assign_band", {"band": f"04AABBCCDD{i:04X}", "person": "Everyone"}, blocking=True)
    await _with_readers(hass, {"front": None})
    await hass.services.async_call(DOMAIN, "sync", {}, blocking=True, return_response=True)
    assert len(registry.allowed_uids()) == n
    assert "too long" in _notification(hass, SYNC_NOTIFICATION_ID)["message"]


# ---------------------------------------------------------------------------- Bluetooth flooding


async def test_made_up_beacons_cant_fill_home_assistant(hass: HomeAssistant, setup_integration) -> None:
    await hass.services.async_call(DOMAIN, "add_person", {"name": "Andrew"}, blocking=True)
    mine = _beacon(hass, BAND_X)
    await hass.services.async_call(DOMAIN, "link_bluetooth", {"bluetooth_band": mine.id, "person": "Andrew"}, blocking=True)
    rnd = random.Random(7)
    for i in range(MAX_UNCLAIMED * 4):
        _beacon(hass, _random_beacon(rnd), address=f"{i:012x}")
    await hass.async_block_till_done()
    bands = _data(hass).beacons.bands
    assert len(bands) == MAX_UNCLAIMED + 1  # the cap, plus Andrew's band, which is never dropped
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
#include <string>
static std::array<char, 1600> known_list;
static std::string sync_error;
#define id(x) x
#define ESP_LOGI(tag, ...) std::printf(__VA_ARGS__), std::printf("\n")
#define ESP_LOGE(tag, ...) std::printf(__VA_ARGS__), std::printf("\n")
static void set_known_bands(const std::string &bands) {
%s
}
int main(int argc, char **argv) {
  set_known_bands(argv[1]);
  set_known_bands(argv[2]);
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
    src.write_text(_HARNESS % body)
    exe = tmp_path / "reader"
    subprocess.run(["g++", "-std=c++17", "-o", str(exe), str(src)], check=True, capture_output=True)
    return exe


def _run(exe: Path, first: str, second: str) -> dict[str, str]:
    out = subprocess.run([str(exe), first, second], check=True, capture_output=True, text=True).stdout
    return dict(re.findall(r"^(LIST|ERROR)=(.*)$", out, re.M))


def test_reader_applies_a_valid_list(tmp_path: Path) -> None:
    exe = _reader_firmware(tmp_path)
    result = _run(exe, "", "04-53-65-2a-c0-5f-80,0453652A")
    assert result == {"LIST": ",0453652AC05F80,0453652A,", "ERROR": ""}


def test_reader_never_keeps_a_revoked_band(tmp_path: Path) -> None:
    exe = _reader_firmware(tmp_path)
    too_many = ",".join(f"04AABBCCDD{i:04X}" for i in range(200))
    result = _run(exe, "0453652AC05F80", too_many)  # allowed, then a list too long to store
    assert result["LIST"] == ""  # emptied: the old band isn't still allowed
    assert result["ERROR"].startswith("Too many bands")


@pytest.mark.parametrize("bad", ["TEST", "0453652AC05F8", "04É3652AC05F80", "0453652AC05F80;rm"])
def test_reader_rejects_malformed_lists(tmp_path: Path, bad: str) -> None:
    exe = _reader_firmware(tmp_path)
    result = _run(exe, "0453652AC05F80", f"0453652A,{bad}")
    assert result["LIST"] == "" and result["ERROR"]
