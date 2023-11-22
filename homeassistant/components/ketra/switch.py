"""Ketra Switch Platform integration."""
import logging
from typing import Any

from aioketraapi import ButtonChange, WebsocketV2Notification

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import KetraPlatformBase, KetraPlatformCommon
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Ketra switch platform via config entry."""

    plat_common = hass.data[DOMAIN][entry.unique_id]["common_platform"]
    platform = KetraSwitchPlatform(async_add_entities, plat_common, _LOGGER)
    await platform.setup_platform()
    _LOGGER.info("Platform init complete")


class KetraSwitchPlatform(KetraPlatformBase):
    """Ketra Switch Platform helper class."""

    def __init__(
        self, add_entities, platform_common: KetraPlatformCommon, logger: logging.Logger
    ) -> None:
        """Initialize the switch platform class."""
        super().__init__(add_entities, platform_common, logger)
        self.button_map: dict[str, KetraSwitch] = {}
        self.keypad_map: dict[str, list[KetraSwitch]] = {}

    async def setup_platform(self) -> None:
        """Perform platform setup."""
        self.logger.info("Beginning setup_platform()")
        switches = []
        keypads = await self.hub.get_keypads()
        for keypad in keypads:
            buttons = []
            for button in keypad.buttons:
                switch = KetraSwitch(button)
                switches.append(switch)
                self.button_map[button.id] = switch
                buttons.append(switch)
            self.keypad_map[keypad.id] = buttons
        self.add_entities(switches)
        self.logger.info("%d switches added", len(switches))
        self.platform_common.add_platform(self)

    async def reload_platform(self) -> None:
        """Reload the platform after a Design Studio Publish operation."""
        new_switches = []
        current_switch_ids = []
        keypads = await self.hub.get_keypads()
        for keypad in keypads:
            for button in keypad.buttons:
                current_switch_ids.append(button.id)
                if button.id not in self.button_map:
                    switch = KetraSwitch(button)
                    new_switches.append(switch)
                    self.button_map[button.id] = switch
        if len(new_switches) > 0:
            self.logger.info("%d new switches added", len(new_switches))
            self.add_entities(new_switches)
        for button_id in list(self.button_map.keys()):
            if button_id not in current_switch_ids:
                self.logger.info("Removing switch id '%s'", button_id)
                await self.button_map.pop(button_id).async_remove()

    async def refresh_entity_state(self) -> None:
        """Refresh the state of all entities."""
        keypads = await self.hub.get_keypads()
        for keypad in keypads:
            for button in keypad.buttons:
                if button.id in self.button_map:
                    self.button_map[button.id].update_button(button)

    async def websocket_notification(self, notification_model: WebsocketV2Notification):
        """Handle websocket events (invoked from platform_common)."""
        await super().websocket_notification(notification_model)

        if isinstance(notification_model, ButtonChange):
            button_id = notification_model.contents.button_id
            activated = notification_model.contents.activated
            if button_id in self.button_map:
                await self.button_map[button_id].update_state(True)

                self.logger.debug(
                    "Keypad button '%s' %s",
                    self.button_map[button_id].name,
                    "activated" if activated else "deactivated",
                )
                for button in self.keypad_map[self.button_map[button_id].keypad_id]:
                    await button.update_state(False)


class KetraSwitch(SwitchEntity):
    """Representation of a Ketra keypad button."""

    def __init__(self, button):
        """Initialize the switch entity from the Ketra button object."""
        self._button = button
        self._name = button.scene_name

    @property
    def keypad_id(self):
        """Return the keypad id."""
        return self._button.keypad.id

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._button.id

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def icon(self):
        """Icon to use in the frontend."""
        return "mdi:lightbulb"

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        return self._button.active != 0

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        await self._button.activate()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        await self._button.deactivate()

    async def update_state(self, query_keypad):
        """Update the state of the switch."""
        if query_keypad:
            await self._button.keypad.update_state()
        self.schedule_update_ha_state(force_refresh=False)

    def update_button(self, button):
        """Update the button after a websocket reconnection."""
        self._button = button
        self.schedule_update_ha_state(force_refresh=False)
