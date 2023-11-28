"""Tests for the Ketra Scene platform."""

import logging
from typing import cast

from aioketraapi.models import (
    ButtonChange,
    ButtonChangeNotification,
    HubReady,
    WebsocketV2Notification,
)
import pytest

from homeassistant.components.ketra import DOMAIN as KETRA_DOMAIN
from homeassistant.components.scene import DOMAIN as SCENE_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID, ATTR_FRIENDLY_NAME, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import async_get_platforms

from .common import SCENE_ENTITY_ID, MockHub

_LOGGER = logging.getLogger(__name__)

pytestmark = pytest.mark.parametrize("config_entry", ["scene"], indirect=True)


async def test_scene_platform_creation(
    hass: HomeAssistant, config_entry, platform_common
):
    """Test platform creation."""
    assert len(platform_common.platforms) == 1
    entries = hass.config_entries.async_entries(KETRA_DOMAIN)
    assert len(entries) == 1
    state = hass.states.get(f"{SCENE_DOMAIN}.{SCENE_ENTITY_ID}")
    assert state is not None
    assert state.attributes.get(ATTR_FRIENDLY_NAME) == SCENE_ENTITY_ID
    scene_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(scene_platform.entities) == 1


async def test_scene_entity_refresh(hass: HomeAssistant, platform_common):
    """Test platform refresh."""
    await platform_common.platforms[0].refresh_entity_state()
    assert len(platform_common.platforms[0].button_map) == 1
    entries = hass.config_entries.async_entries(KETRA_DOMAIN)
    assert len(entries) == 1
    # verify that we have 1 entity
    scene_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(scene_platform.entities) == 1


async def test_scene_reload_platform(hass: HomeAssistant, platform_common):
    """Test platform reload."""
    platform_common.hub.add_keypad_button()
    await platform_common.platforms[0].reload_platform()
    assert len(platform_common.platforms[0].button_map) == 2
    await hass.async_block_till_done()
    # verify that we have 2 entities
    scene_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(scene_platform.entities) == 2


async def test_scene_reload_platform_via_hubready(
    hass: HomeAssistant, platform_common, mock_hub
):
    """Test platform reload."""
    platform_common.hub.add_keypad_button()
    await mock_hub.websocket_notification(
        cast(
            WebsocketV2Notification,
            HubReady(notification_type="HubReady", time_utc="now"),
        )
    )
    assert len(platform_common.platforms[0].button_map) == 2
    await hass.async_block_till_done()
    scene_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(scene_platform.entities) == 2


async def test_scene_removed(hass: HomeAssistant, platform_common):
    """Test platform reload."""
    platform_common.hub.remove_keypad_buttons()
    await platform_common.platforms[0].reload_platform()
    assert len(platform_common.platforms[0].button_map) == 0
    await hass.async_block_till_done()
    entries = hass.config_entries.async_entries(KETRA_DOMAIN)
    assert len(entries) == 1
    scene_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(scene_platform.entities) == 0


async def test_scene_activation(hass: HomeAssistant, platform_common):
    """Test scene activation."""
    await hass.services.async_call(
        SCENE_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: f"{SCENE_DOMAIN}.{SCENE_ENTITY_ID}"},
        blocking=True,
    )
    await hass.async_block_till_done()
    platform_common.hub.button.activate.assert_called_once()


async def test_scene_websocket_button_change_notification(
    hass: HomeAssistant, platform_common, mock_hub: MockHub
):
    """Test scene notification."""
    notifications = []

    def listener(event):
        notifications.append(event)

    # listen for ketra_button_press
    hass.bus.async_listen("ketra_button_press", listener)

    btn_change = ButtonChange(
        notification_type="ButtonChange",
        time_utc="now",
        contents=ButtonChangeNotification(button_id="12345", activated=True),
    )
    await mock_hub.websocket_notification(cast(WebsocketV2Notification, btn_change))
    await hass.async_block_till_done()
    assert len(notifications) == 1
    assert notifications[0].event_type == "ketra_button_press"
    assert notifications[0].data["button_id"] == "12345"
    assert notifications[0].data["name"] == "ketra_scene_name"
    assert notifications[0].data["keypad_name"] == "keypad name"
    assert notifications[0].data["activated"]


async def test_scene_websocket_button_change_invalid_notification(
    hass: HomeAssistant, platform_common, mock_hub: MockHub
):
    """Test invalid scene notification."""
    notifications = []

    def listener(event):
        notifications.append(event)

    # listen for ketra_button_press
    hass.bus.async_listen("ketra_button_press", listener)
    btn_change = ButtonChange(
        notification_type="ButtonChange",
        time_utc="now",
        contents=ButtonChangeNotification(button_id="123456", activated=True),
    )
    await mock_hub.websocket_notification(cast(WebsocketV2Notification, btn_change))
    await hass.async_block_till_done()
    assert len(notifications) == 0
