"""Ketra Light Platform integration."""
import logging

from aioketraapi import GroupStateChange, LampState, WebsocketV2Notification

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_TRANSITION,
    ATTR_WHITE,
    ATTR_XY_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.util.color as color_util

from . import KetraPlatformBase, KetraPlatformCommon
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Ketra light platform via config entry."""

    plat_common = hass.data[DOMAIN][entry.unique_id]["common_platform"]
    platform = KetraLightPlatform(async_add_entities, plat_common, _LOGGER)
    await platform.setup_platform()
    _LOGGER.info("Platform init complete")


class KetraLightPlatform(KetraPlatformBase):
    """Ketra Light Platform helper class."""

    def __init__(
        self, add_entities, platform_common: KetraPlatformCommon, logger: logging.Logger
    ) -> None:
        """Initialize the light platform class."""
        super().__init__(add_entities, platform_common, logger)
        self.group_map: dict[str, KetraGroup] = {}

    async def setup_platform(self) -> None:
        """Perform platform setup."""
        self.logger.info("Beginning setup_platform()")
        groups = []
        for group in await self.hub.get_groups():
            group_entity = KetraGroup(group)
            groups.append(group_entity)
            self.group_map[group.id] = group_entity
        self.add_entities(groups)
        self.logger.info("%d light groups added", len(groups))
        self.platform_common.add_platform(self)

    async def reload_platform(self) -> None:
        """Reload the platform after a Design Studio Publish operation."""
        new_groups = []
        current_groups = await self.hub.get_groups()
        current_groups_ids = []
        for group in current_groups:
            current_groups_ids.append(group.id)
            if group.id not in self.group_map:
                group_entity = KetraGroup(group)
                new_groups.append(group_entity)
                self.group_map[group.id] = group_entity
        for group_id in list(self.group_map.keys()):
            if group_id not in current_groups_ids:
                self.logger.info("Removing group id '%s'", group_id)
                await self.group_map.pop(group_id).async_remove()
        if len(new_groups) > 0:
            self.logger.info("%d new lights added", len(new_groups))
            self.add_entities(new_groups)

    async def refresh_entity_state(self) -> None:
        """Refresh the state of all entities."""
        self.logger.info("Refreshing state of all light entities")
        all_groups = await self.hub.get_groups()
        for group in all_groups:
            if group.id in self.group_map:
                self.group_map[group.id].update_state(group)

    async def websocket_notification(self, notification_model: WebsocketV2Notification):
        """Handle websocket events (invoked from platform_common)."""
        await super().websocket_notification(notification_model)

        if isinstance(notification_model, GroupStateChange):
            changed_groups = notification_model.group_ids
            if len(changed_groups) > 4:
                # get all groups in one shot instead of one at a time
                all_groups = await self.hub.get_groups()
                for group in all_groups:
                    if group.id in self.group_map and group.id in changed_groups:
                        self.group_map[group.id].update_state(group)
            else:
                for group_id in changed_groups:
                    if group_id in self.group_map:
                        self.logger.debug(
                            "Group %s changed", self.group_map[group_id].name
                        )
                        self.group_map[group_id].update_state()


class KetraGroup(LightEntity):
    """Representation of a Ketra Light Group as a Hass Light Entity."""

    def __init__(self, group):
        """Initialize the light entity from the Ketra Group object."""
        self._attr_supported_color_modes: set[ColorMode | str] = set()
        self._attr_supported_color_modes.add(ColorMode.XY)
        self._attr_supported_color_modes.add(ColorMode.COLOR_TEMP)
        self._attr_supported_color_modes.add(ColorMode.HS)
        self._attr_supported_color_modes.add(ColorMode.RGB)
        self._attr_supported_color_modes.add(ColorMode.RGBW)
        self._attr_supported_color_modes.add(ColorMode.WHITE)
        self._attr_supported_features = LightEntityFeature.TRANSITION
        self._group = group
        self._lamp_state = group.state

    async def async_added_to_hass(self):
        """Handle entity about to be added to hass event."""
        await super().async_added_to_hass()
        self.schedule_update_ha_state(force_refresh=False)

    def update_state(self, updated_group=None):
        """Update the state of the entity.

        Called by KetraLightPlatform in response to a websocket callback indicating a change to a light group.
        Adopts the state of updated_group if it is provided, and calls schedule_update_ha_state to trigger
        an entity state update, with force_refresh=True only if updated_group is None.
        """
        if updated_group is not None:
            self._group = updated_group
            self._lamp_state = self._group.state
        self.schedule_update_ha_state(force_refresh=(updated_group is None))

    @property
    def should_poll(self):
        """Return whether hass should poll the state of the entity.

        The state will updated through the websocket connection to the hub, thus polling is disabled.
        """
        return False

    @property
    def unique_id(self):
        """Return the unique ID of this light."""
        return self._group.id

    @property
    def device_id(self):
        """Return the ID of this light."""
        return self._group.id

    @property
    def name(self):
        """Return the display name of this light."""
        return self._group.name

    @property
    def brightness(self):
        """Return the brightness of the light."""
        if not self.is_on:
            return None
        return self._lamp_state.brightness * 255

    @property
    def color_temp_kelvin(self):
        """Return the CT color value in kelvin."""
        cct = self._lamp_state.cct
        if cct == 0 or cct is None:
            return None
        return cct

    @property
    def color_temp(self):
        """Return the CT color value in mireds."""
        cct = self.color_temp_kelvin
        return 1000000 / cct if cct else None

    @property
    def xy_color(self):
        """Return the XY color value."""
        return (
            self._lamp_state.x_chromaticity,
            self._lamp_state.y_chromaticity,
        )

    @property
    def color_mode(self) -> ColorMode:
        """Return the color mode of the light."""
        return ColorMode.COLOR_TEMP if self.color_temp_kelvin else ColorMode.XY

    @property
    def min_mireds(self):
        """Return the coldest color_temp that this light supports."""
        return 1000000 / 10000

    @property
    def max_mireds(self):
        """Return the warmest color_temp that this light supports."""
        return 1000000 / 1100

    @property
    def min_color_temp_kelvin(self) -> int:
        """Return the warmest color_temp_kelvin that this light supports."""
        return 1100

    @property
    def max_color_temp_kelvin(self) -> int:
        """Return the coldest color_temp_kelvin that this light supports."""
        return 10000

    @property
    def white_value(self):
        """Return the white value of this light between 0..255.

        This corresponds inversely to the Ketra Vibrancy property which is in the range from 0..1.
        """
        vibrancy = self._lamp_state.vibrancy
        white_level = 1.0 - vibrancy
        return white_level * 255

    @property
    def is_on(self):
        """Return true if light is on."""
        return self._lamp_state.power_on

    async def __async_set_lamp_state(self, power_state: bool, **kwargs):
        """Set the state of the light."""
        lamp_state = LampState(power_on=power_state)
        if ATTR_TRANSITION in kwargs:
            lamp_state.transition_time = int(kwargs[ATTR_TRANSITION] * 1000)

        if ATTR_XY_COLOR in kwargs:
            lamp_state.x_chromaticity = kwargs[ATTR_XY_COLOR][0]
            lamp_state.y_chromaticity = kwargs[ATTR_XY_COLOR][1]
        elif ATTR_RGB_COLOR in kwargs:
            xy_color = color_util.color_RGB_to_xy(*kwargs[ATTR_RGB_COLOR])
            lamp_state.x_chromaticity = xy_color[0]
            lamp_state.y_chromaticity = xy_color[1]
        elif ATTR_RGBW_COLOR in kwargs:
            xy_color = color_util.color_RGB_to_xy(*kwargs[ATTR_RGBW_COLOR][:3])
            lamp_state.x_chromaticity = xy_color[0]
            lamp_state.y_chromaticity = xy_color[1]
            lamp_state.vibrancy = 1 - (kwargs[ATTR_RGBW_COLOR][-1] / 255.0)
        elif ATTR_HS_COLOR in kwargs:
            xy_color = color_util.color_hs_to_xy(*kwargs[ATTR_HS_COLOR])
            lamp_state.x_chromaticity = xy_color[0]
            lamp_state.y_chromaticity = xy_color[1]
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            temp = kwargs[ATTR_COLOR_TEMP_KELVIN]
            lamp_state.cct = temp

        if ATTR_BRIGHTNESS in kwargs:
            lamp_state.brightness = kwargs[ATTR_BRIGHTNESS] / 255.0

        if ATTR_WHITE in kwargs:
            lamp_state.vibrancy = 1 - (kwargs[ATTR_WHITE] / 255.0)

        await self._group.set_state(lamp_state)
        self._lamp_state = self._group.state
        self.schedule_update_ha_state(force_refresh=False)

    async def async_turn_on(self, **kwargs):
        """Instruct the light to turn on."""
        _LOGGER.debug("async_turn_on called for %s", self.name)
        await self.__async_set_lamp_state(True, **kwargs)

    async def async_turn_off(self, **kwargs):
        """Instruct the light to turn off."""
        _LOGGER.debug("async_turn_off called for %s", self.name)
        await self.__async_set_lamp_state(False, **kwargs)

    async def async_update(self):
        """Fetch new state data for this light."""
        await self._group.update_state()
        self._lamp_state = self._group.state
