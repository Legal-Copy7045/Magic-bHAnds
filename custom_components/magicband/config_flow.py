"""Set-up and the Configure screens for managing people and bands."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import CONF_BATTERY_LEVEL, CONF_SNAPSHOT_DAYS, DEFAULT_BATTERY_LEVEL, DOMAIN
from .registry import MagicBandRegistry

NEW_PERSON = "__new__"
UNASSIGN = "__none__"


class MagicBandConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="MagicbHAnds", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MagicBandOptionsFlow()


def _ago(iso: str | None) -> str:
    if not iso:
        return "never seen"
    seconds = (dt_util.utcnow() - dt_util.parse_datetime(iso)).total_seconds()
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = int(seconds // size)
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


class MagicBandOptionsFlow(OptionsFlow):
    """Menu for adding people, assigning bands and removing them."""

    def __init__(self) -> None:
        self._band: str | None = None
        self._label: str = ""
        self._person_id: str | None = None

    @property
    def _registry(self) -> MagicBandRegistry:
        return self.config_entry.runtime_data.registry

    # ------------------------------------------------------------------ menu

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["assign_band", "add_person", "edit_person", "link_bluetooth", "remove_band", "remove_person", "settings"],
            description_placeholders={"summary": self._summary()},
        )

    def _summary(self) -> str:
        reg = self._registry
        lines = []
        for person in reg.people:
            bands = ", ".join(b.label or b.display for b in reg.bands_for(person.id)) or "no bands"
            linked = f" ({person.ha_person})" if person.ha_person else ""
            state = "" if person.allowed else " — not allowed"
            lines.append(f"- **{person.name}**{linked}: {bands}{state}")
        tracker = self.config_entry.runtime_data.beacons
        for band in tracker.bands.values():
            where = "nearby" if band.nearby() else f"last heard {_ago(band.last_seen)}"
            lines.append(f"- Bluetooth: **{tracker.display_name(band)}**, {where}")
        unknown = len(reg.unassigned_bands)
        if unknown:
            lines.append(f"\n{unknown} band(s) not assigned to anyone yet.")
        return "\n".join(lines) if lines else "No people yet. Tap a band on a reader, then choose *Add or assign a band*."

    def _band_options(self) -> list[selector.SelectOptionDict]:
        options = []
        for band in self._registry.bands:
            person = self._registry.get_person(band.person_id)
            owner = f"{person.name}'s" if person else "unassigned"
            renamed = self.config_entry.runtime_data.beacons.nfc_display_name(band)
            label = f" '{renamed or band.label}'" if (renamed or band.label) else ""
            where = f" on {band.last_reader}" if band.last_reader else ""
            options.append(
                selector.SelectOptionDict(
                    value=band.uid,
                    label=f"{band.display}{label} — {owner}, {_ago(band.last_seen)}{where}",
                )
            )
        return options

    def _people_options(self) -> list[selector.SelectOptionDict]:
        return [selector.SelectOptionDict(value=p.id, label=p.name) for p in self._registry.people]

    # ------------------------------------------------------------------ assign band

    async def async_step_assign_band(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if not self._registry.bands:
            return self.async_abort(reason="no_bands")
        if user_input is not None:
            self._band = user_input["band"]
            self._label = user_input.get("label", "")
            choice = user_input["person"]
            if choice == NEW_PERSON:
                return await self.async_step_new_person()
            try:
                self._registry.assign_band(self._band, None if choice == UNASSIGN else choice, self._label)
            except ValueError:
                errors["band"] = "invalid_band"
            else:
                persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_unknown_{self._band}")
                return self.async_create_entry(data=dict(self.config_entry.options))

        bands = self._band_options()
        # Default to the most recently seen unassigned band.
        unassigned = self._registry.unassigned_bands
        default_band = unassigned[0].uid if unassigned else bands[0]["value"]
        people = [
            *self._people_options(),
            selector.SelectOptionDict(value=NEW_PERSON, label="➕ New person…"),
            selector.SelectOptionDict(value=UNASSIGN, label="Nobody (unassign)"),
        ]
        schema = vol.Schema(
            {
                vol.Required("band", default=default_band): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=bands, mode=selector.SelectSelectorMode.DROPDOWN)
                ),
                vol.Required("person", default=people[0]["value"]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=people, mode=selector.SelectSelectorMode.DROPDOWN)
                ),
                vol.Optional("label", default=""): selector.TextSelector(),
            }
        )
        return self.async_show_form(step_id="assign_band", data_schema=schema, errors=errors)

    async def async_step_new_person(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                person = self._registry.add_person(
                    user_input["name"], user_input.get("ha_person"), user_input.get("allowed", True)
                )
            except ValueError:
                errors["name"] = "name_taken"
            else:
                if self._band:
                    try:
                        self._registry.assign_band(self._band, person.id, self._label)
                    except ValueError:
                        return self.async_abort(reason="invalid_band")
                    persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_unknown_{self._band}")
                return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(step_id="new_person", data_schema=_person_schema(), errors=errors)

    # ------------------------------------------------------------------ people

    async def async_step_add_person(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self._band = None
        return await self.async_step_new_person(user_input)

    async def async_step_edit_person(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._registry.people:
            return self.async_abort(reason="no_people")
        if user_input is not None:
            self._person_id = user_input["person"]
            return await self.async_step_edit_person_details()
        return self.async_show_form(
            step_id="edit_person",
            data_schema=vol.Schema(
                {vol.Required("person"): selector.SelectSelector(selector.SelectSelectorConfig(options=self._people_options()))}
            ),
        )

    async def async_step_edit_person_details(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        person = self._registry.get_person(self._person_id)
        if person is None:
            return self.async_abort(reason="no_people")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._registry.update_person(
                    person.id,
                    name=user_input["name"],
                    ha_person=user_input.get("ha_person") or "",
                    allowed=user_input.get("allowed", True),
                )
            except ValueError:
                errors["name"] = "name_taken"
            else:
                return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="edit_person_details",
            data_schema=_person_schema(person.name, person.ha_person, person.allowed),
            errors=errors,
            description_placeholders={"name": person.name},
        )

    async def async_step_remove_person(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._registry.people:
            return self.async_abort(reason="no_people")
        if user_input is not None:
            from . import async_remove_person  # noqa: PLC0415 - the package imports this module's neighbours

            await async_remove_person(self.hass, self.config_entry.runtime_data, user_input["person"])
            return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="remove_person",
            data_schema=vol.Schema(
                {vol.Required("person"): selector.SelectSelector(selector.SelectSelectorConfig(options=self._people_options()))}
            ),
        )

    # ------------------------------------------------------------------ Bluetooth

    async def async_step_link_bluetooth(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        tracker = self.config_entry.runtime_data.beacons
        if not tracker.bands:
            return self.async_abort(reason="no_bluetooth_bands")
        if user_input is not None:
            band = tracker.bands[user_input["bluetooth_band"]]
            kind, _, value = user_input["owner"].partition(":")
            if kind == "band":
                tracker.link(band, nfc_uid=value)
            else:
                tracker.link(band, person_id=value or None)
            return self.async_create_entry(data=dict(self.config_entry.options))

        def describe(b) -> str:
            person, nfc = tracker.owner(b)
            owner = f"{person.name}'s" if person else ("linked" if nfc else "unlinked")
            battery = f", battery {b.battery} %?" if b.battery is not None else ""
            signal = f", {b.last_rssi} dBm via {b.last_source}" if b.last_rssi is not None else ""
            return f"{tracker.display_name(b)} ({owner}): {_ago(b.last_seen)}{signal}{battery}"

        bands = sorted(tracker.bands.values(), key=lambda b: (b.band_uid is not None, b.first_seen))
        owners = [
            *(
                selector.SelectOptionDict(value=f"band:{o['value']}", label=f"Band {o['label']}")
                for o in self._band_options()
            ),
            *(selector.SelectOptionDict(value=f"person:{p.id}", label=f"Person: {p.name}") for p in self._registry.people),
            selector.SelectOptionDict(value="person:", label="Nobody (unlink)"),
        ]
        schema = vol.Schema(
            {
                vol.Required("bluetooth_band", default=bands[0].id): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[selector.SelectOptionDict(value=b.id, label=describe(b)) for b in bands],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required("owner", default=owners[0]["value"]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=owners, mode=selector.SelectSelectorMode.DROPDOWN)
                ),
            }
        )
        return self.async_show_form(step_id="link_bluetooth", data_schema=schema)

    # ------------------------------------------------------------------ settings

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, **user_input})
        options = self.config_entry.options
        return self.async_show_form(
            step_id="settings",
            data_schema=vol.Schema(
                {
                    vol.Required("show_in_sidebar", default=options.get("show_in_sidebar", True)): selector.BooleanSelector(),
                    vol.Required(
                        CONF_BATTERY_LEVEL, default=options.get(CONF_BATTERY_LEVEL, DEFAULT_BATTERY_LEVEL)
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=0, max=100, step=5, unit_of_measurement="%",
                                                      mode=selector.NumberSelectorMode.SLIDER)
                    ),
                    vol.Required(CONF_SNAPSHOT_DAYS, default=options.get(CONF_SNAPSHOT_DAYS, 30)): selector.NumberSelector(
                        selector.NumberSelectorConfig(min=1, max=365, step=1, unit_of_measurement="days",
                                                      mode=selector.NumberSelectorMode.BOX)
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------ bands

    async def async_step_remove_band(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if not self._registry.bands:
            return self.async_abort(reason="no_bands")
        if user_input is not None:
            from . import async_remove_band  # noqa: PLC0415

            async_remove_band(self.hass, self.config_entry.runtime_data, user_input["band"])
            return self.async_create_entry(data=dict(self.config_entry.options))
        return self.async_show_form(
            step_id="remove_band",
            data_schema=vol.Schema(
                {
                    vol.Required("band"): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=self._band_options(), mode=selector.SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )


def _person_schema(name: str = "", ha_person: str | None = None, allowed: bool = True) -> vol.Schema:
    ha_key = vol.Optional("ha_person", description={"suggested_value": ha_person}) if ha_person else vol.Optional("ha_person")
    return vol.Schema(
        {
            vol.Required("name", default=name): selector.TextSelector(),
            ha_key: selector.EntitySelector(selector.EntitySelectorConfig(domain="person")),
            vol.Required("allowed", default=allowed): selector.BooleanSelector(),
        }
    )
