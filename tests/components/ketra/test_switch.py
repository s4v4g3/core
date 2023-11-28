"""Tests for the Ketra switch platform."""
import asyncio
import logging
from typing import cast

from aioketraapi.models import (
    ButtonChange,
    ButtonChangeNotification,
    HubReady,
    WebsocketV2Notification,
)
from aioketraapi.n4_hub import N4HubWebSocketConnectionError
import pytest

from homeassistant.components.ketra import DOMAIN as KETRA_DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import async_get_platforms

from .common import SWITCH_ENTITY_ID, MockHub

_LOGGER = logging.getLogger(__name__)


pytestmark = pytest.mark.parametrize("config_entry", ["switch"], indirect=True)


async def test_switch_platform_creation(
    hass: HomeAssistant, config_entry, platform_common
):
    """Test platform creation."""
    assert len(platform_common.platforms) == 1
    entries = hass.config_entries.async_entries(KETRA_DOMAIN)
    assert len(entries) == 1
    state = hass.states.get(f"{SWITCH_DOMAIN}.{SWITCH_ENTITY_ID}")
    assert state is not None
    assert state.attributes.get(ATTR_FRIENDLY_NAME) == SWITCH_ENTITY_ID
    switch_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert switch_platform.domain == SWITCH_DOMAIN
    assert len(switch_platform.entities) == 1


async def test_switch_entity_refresh(hass: HomeAssistant, platform_common):
    """Test platform refresh."""
    await platform_common.platforms[0].refresh_entity_state()
    assert len(platform_common.platforms[0].button_map) == 1
    entries = hass.config_entries.async_entries(KETRA_DOMAIN)
    assert len(entries) == 1
    # verify that we have 1 entity
    switch_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(switch_platform.entities) == 1


async def test_switch_reload_platform(hass: HomeAssistant, platform_common):
    """Test platform reload."""
    platform_common.hub.add_keypad_button()
    await platform_common.platforms[0].reload_platform()
    assert len(platform_common.platforms[0].button_map) == 2
    await hass.async_block_till_done()
    # verify that we have 2 entities
    switch_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(switch_platform.entities) == 2


async def test_switch_reload_platform_via_hubready(
    hass: HomeAssistant, platform_common
):
    """Test platform reload."""
    platform_common.hub.add_keypad_button()
    await platform_common.platforms[0].websocket_notification(
        HubReady(notification_type="HubReady", time_utc="now")
    )
    assert len(platform_common.platforms[0].button_map) == 2
    await hass.async_block_till_done()
    switch_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(switch_platform.entities) == 2


async def test_switch_removed(hass: HomeAssistant, platform_common):
    """Test platform reload."""
    platform_common.hub.remove_keypad_buttons()
    await platform_common.platforms[0].reload_platform()
    assert len(platform_common.platforms[0].button_map) == 0
    await hass.async_block_till_done()
    entries = hass.config_entries.async_entries(KETRA_DOMAIN)
    assert len(entries) == 1
    switch_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(switch_platform.entities) == 0


async def test_switch_activation(hass: HomeAssistant, platform_common):
    """Test switch activation."""
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: f"{SWITCH_DOMAIN}.{SWITCH_ENTITY_ID}"},
        blocking=True,
    )
    await hass.async_block_till_done()
    platform_common.hub.button.activate.assert_called_once()
    assert platform_common.platforms[0].button_map["12345"].is_on


async def test_switch_deactivation(hass: HomeAssistant, platform_common):
    """Test switch deactivation."""
    await hass.services.async_call(
        SWITCH_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: f"{SWITCH_DOMAIN}.{SWITCH_ENTITY_ID}"},
        blocking=True,
    )
    await hass.async_block_till_done()
    platform_common.hub.button.deactivate.assert_called_once()
    assert not platform_common.platforms[0].button_map["12345"].is_on


async def test_switch_websocket_button_change_notification(
    hass: HomeAssistant, platform_common, mock_hub: MockHub
):
    """Test switch notification."""
    button = platform_common.platforms[0].button_map["12345"]
    notifications = []

    def listener(event):
        notifications.append(event)

    # listen for ketra_button_press - (listener should not be called for switch platform)
    hass.bus.async_listen("ketra_button_press", listener)

    await button._button.activate()
    btn_change = ButtonChange(
        notification_type="ButtonChange",
        time_utc="now",
        contents=ButtonChangeNotification(button_id="12345", activated=True),
    )
    await platform_common.platforms[0].websocket_notification(btn_change)
    await hass.async_block_till_done()
    assert len(notifications) == 0

    button._button.keypad.update_state.assert_called_once()
    assert button.is_on

    button._button.keypad.update_state.reset_mock()
    await button._button.deactivate()
    btn_change.contents = ButtonChangeNotification(button_id="12345", activated=False)
    await mock_hub.websocket_notification(cast(WebsocketV2Notification, btn_change))
    await hass.async_block_till_done()
    assert len(notifications) == 0

    button._button.keypad.update_state.assert_called_once()
    assert button.is_on is False


async def test_switch_websocket_button_change_invalid_notification(
    hass: HomeAssistant, platform_common, mock_hub: MockHub
):
    """Test invalid switch notification."""
    button = platform_common.platforms[0].button_map["12345"]
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
    button._button.keypad.update_state.assert_not_called()
    assert button.is_on is False


async def test_websocket_exception(
    hass: HomeAssistant, platform_common, mock_hub: MockHub
):
    """Test websocket exception cases."""
    mock_hub.raise_websocket_exception(Exception("test exception"))
    await asyncio.sleep(1)
    mock_hub.raise_websocket_exception(N4HubWebSocketConnectionError())
    await asyncio.sleep(1)
