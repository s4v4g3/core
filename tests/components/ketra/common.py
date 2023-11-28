"""Test helpers for the Ketra Light platform."""

import asyncio
from typing import Optional
from unittest.mock import AsyncMock, Mock

from aioketraapi import WebsocketV2Notification
from aioketraapi.models import LampState

from homeassistant.components.ketra import DOMAIN as KETRA_DOMAIN
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry

SCENE_ENTITY_ID = "ketra_scene_name"
LIGHT_GROUP_ENTITY_ID = "ketra_group_name"
SWITCH_ENTITY_ID = "ketra_scene_name"


class MockKeypad:
    """Mock keypad class."""

    def __init__(self):
        """Initialize the mock keypad object."""
        self.id = "123456"
        self.name = "keypad name"
        self.buttons = []

    async def update_state(self):
        """Update the keypad state."""


class MockHub:
    """Mock hub class."""

    def __init__(self):
        """Initialize the mock hub object."""
        self.installation_id = "12345"
        self.oauth_token = "12345"
        self.url_base = "https://10.4.1.104/ketra.cgi"
        self.close = False
        self.keypad = Mock()
        self.keypad.id = "123456"
        self.keypad.name = "keypad name"
        self.keypad.update_state = AsyncMock()

        self.button = Mock()
        self.button.id = "12345"
        self.button.scene_name = SCENE_ENTITY_ID
        self.button.active = 0

        def activate():
            self.button.active = 1

        def deactivate():
            self.button.active = 0

        self.button.activate = AsyncMock(side_effect=activate)
        self.button.deactivate = AsyncMock(side_effect=deactivate)
        self.button.keypad = self.keypad
        self.keypad.buttons = [self.button]
        self.group = Mock()
        self.group.id = "1234567"
        self.group.name = LIGHT_GROUP_ENTITY_ID
        self.group.state = LampState(
            brightness=1.0,
            power_on=True,
            vibrancy=0.5,
            cct=0,
            x_chromaticity=0.5,
            y_chromaticity=0.5,
        )
        self.group.set_state = self.__set_lamp_state
        self.group.update_state = AsyncMock()
        self.websocket_exception: Optional[Exception] = None
        self.websocket_notification_queue: asyncio.Queue[
            WebsocketV2Notification
        ] = asyncio.Queue()

        self.groups = [self.group]
        self.keypads = [self.keypad]

    def add_group(self):
        """Add a group."""
        group = Mock()
        group.id = "12345678"
        group.name = "ketra_group_name_2"
        group.state = LampState(
            brightness=1.0,
            power_on=True,
            vibrancy=0.5,
            cct=0,
            x_chromaticity=0.5,
            y_chromaticity=0.5,
        )
        group.update_state = AsyncMock()
        self.groups.append(group)

    def remove_groups(self):
        """Remove all groups."""
        self.groups = []

    def add_keypad_button(self):
        """Add a keypad button."""
        new_button = Mock()
        new_button.id = "1234567"
        new_button.scene_name = "ketra_scene_name_2"
        new_button.activate = AsyncMock()
        self.keypad.buttons.append(new_button)

    def remove_keypad_buttons(self):
        """Remove all keypad buttons."""
        self.keypad.buttons = []

    async def __set_lamp_state(self, lamp_state):
        for key in lamp_state.to_dict():
            if lamp_state.to_dict()[key] is not None:
                setattr(self.group.state, key, lamp_state.to_dict()[key])

    async def get_groups(self):
        """Return the groups."""
        return self.groups

    async def get_keypads(self):
        """Return the keypads."""
        return self.keypads

    async def __websocket_loop(self):
        while not self.close:
            await asyncio.sleep(0.1)

    async def register_websocket_callback(self, callback):
        """Emulate the websocket registration."""
        while not self.close:
            await asyncio.sleep(0.1)
            if self.websocket_notification_queue.qsize() > 0:
                await callback(await self.websocket_notification_queue.get())
                self.websocket_notification_queue.task_done()

            if self.websocket_exception:
                websocket_exception = self.websocket_exception
                self.websocket_exception = None
                raise websocket_exception

    async def disconnect_websocket_callback(self):
        """Stop the websocket loop."""
        self.close = True

    def raise_websocket_exception(self, exception: BaseException):
        """Raise a websocket exception."""
        self.websocket_exception = exception

    async def websocket_notification(self, notification: WebsocketV2Notification):
        """Append a notification to the websocket notification queue."""
        await self.websocket_notification_queue.put(notification)
        await self.websocket_notification_queue.join()


async def setup_platform(hass):
    """Set up the Ketra platform."""
    mock_entry = MockConfigEntry(
        domain=KETRA_DOMAIN,
        data={
            CONF_ACCESS_TOKEN: "12345",
            "installation_id": "12345",
            "installation_name": "test installation",
        },
    )
    mock_entry.add_to_hass(hass)

    assert await async_setup_component(hass, KETRA_DOMAIN, {})
    await hass.async_block_till_done()

    return mock_entry
