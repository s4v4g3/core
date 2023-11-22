"""Support for Ketra Lighting."""

from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Final

from aioketraapi import HubReady, WebsocketV2Notification
from aioketraapi.n4_hub import N4Hub, N4HubWebSocketConnectionError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ATTR_INSTALLATION_ID = "__installation_id__"
KETRA_PLATFORMS = ["light", "scene", "switch"]
WEBSOCKET_RECONNECT_DELAY = 5

PLATFORM_SCHEMA: Final = cv.PLATFORM_SCHEMA


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Ketra platform."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ketra platforms from config entry."""

    _LOGGER.info("Setting up config entry with unique ID '%s'", entry.unique_id)

    installation_id = entry.data.get("installation_id")
    oauth_token = entry.data.get(CONF_ACCESS_TOKEN)

    hub = await N4Hub.get_hub(installation_id, oauth_token, loop=hass.loop)
    if hub is None:
        _LOGGER.error(
            "Failed to connect to any N4 Hub of installation '%s'", installation_id
        )
        return False

    _LOGGER.info(
        "Discovered N4 Hub at endpoint '%s' for installation '%s'",
        hub.url_base,
        installation_id,
    )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.unique_id] = {
        "common_platform": KetraPlatformCommon(hass, hub, _LOGGER)
    }

    for platform in KETRA_PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    tasks = []

    for platform in KETRA_PLATFORMS:
        tasks.append(hass.config_entries.async_forward_entry_unload(entry, platform))

    await asyncio.gather(*tasks)

    common_platform = hass.data[DOMAIN][entry.unique_id]["common_platform"]
    await common_platform.shutdown()

    return True


class KetraPlatformBase(ABC):
    """Base class for Ketra Platform."""

    def __init__(self, add_entities, platform_common, logger) -> None:
        """Initialize platform base class."""
        self.logger = logger
        self.platform_common = platform_common
        self.add_entities = add_entities

    @property
    def hub(self) -> N4Hub:
        """Return the N4 Hub object."""
        return self.platform_common.hub

    @abstractmethod
    async def reload_platform(self) -> None:
        """Abstract method for reloating the platform.

        Called by platform_common in response to a websocket HubReady event, which occurs after
        a Design Studio publish operation is complete.  Must be implemented by derived class to handle
        added or removed items.
        """

    @abstractmethod
    async def refresh_entity_state(self):
        """Refresh the state of all entities.

        Called by platform_common in response to a websocket reconnection.  Should be overridden
        by derived class to update the hub and/or force an entity refresh.
        """

    async def websocket_notification(self, notification_model: WebsocketV2Notification):
        """Respond to websocket notifications.

        Called by platform_common in response to a websocket notification.  Should be overridden
        by derived class to respond to specific notification types, but this super-class implementation
        should always be called as well to handle the HubReady notification.
        """
        if isinstance(notification_model, HubReady):
            self.logger.info("HubReady notification!  Reloading Platforms")
            await self.reload_platform()


class KetraPlatformCommon:
    """Platform Common helper class."""

    def __init__(self, hass: HomeAssistant, hub: N4Hub, logger: logging.Logger) -> None:
        """Initialize platform common object."""
        self.hass = hass
        self.hub = hub
        self.logger = logger
        self.ws_task = asyncio.ensure_future(self.__register_websocket_callback())
        self.platforms: list[KetraPlatformBase] = []
        self.is_closing = False

        async def hass_shutdown(_):
            """Call shutdown to close websocket connection."""
            await self.shutdown()

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, hass_shutdown)

    async def shutdown(self):
        """Shutdown platform."""
        self.is_closing = True
        await self.hub.disconnect_websocket_callback()
        await self.ws_task
        self.logger.debug("Closed websocket connection")

    def add_platform(self, platform: KetraPlatformBase):
        """Add a platform to enable websocket notification callbacks."""
        self.platforms.append(platform)

    async def __register_websocket_callback(self):
        while True:
            self.logger.debug(
                "Connecting websocket to N4 Hub at endpoint '%s'", self.hub.url_base
            )
            try:
                await self.hub.register_websocket_callback(
                    self.__websocket_notification
                )
            except N4HubWebSocketConnectionError:
                self.logger.warning("ketra websocket connection error!")
            except Exception as e:  # pylint: disable=broad-except
                self.logger.warning("unexpected ketra websocket connection error!")
                self.logger.warning(str(e))
            if self.hass.is_stopping or self.is_closing:
                break
            self.logger.warning(
                "Websocket connection error, attempting reconnection in %s seconds",
                str(WEBSOCKET_RECONNECT_DELAY),
            )
            await asyncio.sleep(WEBSOCKET_RECONNECT_DELAY)
            self.hub = await N4Hub.get_hub(
                self.hub.installation_id,
                self.hub.oauth_token,
                loop=self.hass.loop,
            )
            self.logger.warning(
                "Reconnecting websocket to N4 Hub at endpoint '%s'", self.hub.url_base
            )
            # update the state of all entities since we may have missed notifications and/or switched to a different hub
            for platform in self.platforms:
                await platform.refresh_entity_state()

    async def __websocket_notification(
        self, notification_model: WebsocketV2Notification
    ):
        self.logger.debug("Received websocket notification")
        for platform in self.platforms:
            await platform.websocket_notification(notification_model)
