"""Tests for the Ketra Light platform."""


from typing import cast

from aioketraapi.models import GroupStateChange, HubReady, WebsocketV2Notification
import pytest

from homeassistant.components.ketra import DOMAIN as KETRA_DOMAIN
from homeassistant.components.ketra.light import BULK_GROUP_UPDATE_THRESHOLD
from homeassistant.components.light import (
    DOMAIN as LIGHT_DOMAIN,
    ColorMode,
    LightEntityFeature,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_FRIENDLY_NAME,
    ATTR_SUPPORTED_FEATURES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import async_get_platforms

from .common import LIGHT_GROUP_ENTITY_ID, MockHub

pytestmark = pytest.mark.parametrize("config_entry", ["light"], indirect=True)


async def test_light_platform_creation(
    hass: HomeAssistant,
    platform_common,
    entity_registry: er.EntityRegistry,
):
    """Test platform creation."""
    assert len(platform_common.platforms) == 1
    state = hass.states.get(f"{LIGHT_DOMAIN}.{LIGHT_GROUP_ENTITY_ID}")
    assert state.attributes.get(ATTR_FRIENDLY_NAME) == LIGHT_GROUP_ENTITY_ID
    assert (
        state.attributes.get(ATTR_SUPPORTED_FEATURES) == LightEntityFeature.TRANSITION
    )
    assert "min_color_temp_kelvin" in state.attributes
    assert "max_color_temp_kelvin" in state.attributes
    assert "min_mireds" in state.attributes
    assert "max_mireds" in state.attributes
    assert "color_mode" in state.attributes
    assert "brightness" in state.attributes
    assert "color_temp_kelvin" in state.attributes
    assert "color_temp" in state.attributes
    assert "hs_color" in state.attributes
    assert "rgb_color" in state.attributes
    assert "xy_color" in state.attributes
    assert "rgbw_color" in state.attributes
    assert "supported_color_modes" in state.attributes
    for mode in [
        ColorMode.COLOR_TEMP,
        ColorMode.XY,
        ColorMode.HS,
        ColorMode.RGB,
        ColorMode.WHITE,
        ColorMode.XY,
    ]:
        assert mode in state.attributes["supported_color_modes"]
    entity = platform_common.platforms[0].group_map["1234567"]
    entity.update_state()


async def test_light_entity_refresh(hass: HomeAssistant, platform_common):
    """Test platform refresh."""
    await platform_common.platforms[0].refresh_entity_state()
    assert len(platform_common.platforms[0].group_map) == 1
    entries = hass.config_entries.async_entries(KETRA_DOMAIN)
    assert len(entries) == 1
    # verify that we have 1 entity
    scene_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(scene_platform.entities) == 1


async def test_light_reload_platform(hass: HomeAssistant, platform_common):
    """Test platform reload."""
    light_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(light_platform.entities) == 1

    await platform_common.platforms[0].reload_platform()
    assert len(platform_common.platforms[0].group_map) == 1
    await hass.async_block_till_done()
    assert len(light_platform.entities) == 1

    platform_common.hub.add_group()
    await platform_common.platforms[0].reload_platform()
    assert len(platform_common.platforms[0].group_map) == 2
    await hass.async_block_till_done()
    assert len(light_platform.entities) == 2

    platform_common.hub.remove_groups()
    await platform_common.platforms[0].reload_platform()
    assert len(platform_common.platforms[0].group_map) == 0
    await hass.async_block_till_done()
    assert len(light_platform.entities) == 0


async def test_light_reload_platform_via_hubready(
    hass: HomeAssistant, platform_common, mock_hub
):
    """Test platform reload."""
    await mock_hub.websocket_notification(
        HubReady(notification_type="HubReady", time_utc="now")
    )
    assert len(platform_common.platforms[0].group_map) == 1
    await hass.async_block_till_done()
    light_platform = async_get_platforms(hass, KETRA_DOMAIN)[0]
    assert len(light_platform.entities) == 1


@pytest.mark.parametrize(
    "changed_group_ids",
    [
        [],
        ["1234567"],
        ["1234567", "invalid"],
        ["1234567", "1234567"],
        ["1234567", "invalid"] * 5,
        ["1234567", "1234567"] * 5,
    ],
)
async def test_light_websocket_group_change_notification(
    hass: HomeAssistant, platform_common, mock_hub: MockHub, changed_group_ids
):
    """Test group notification."""
    platform_common.hub.add_group()
    group_change = GroupStateChange(
        notification_type="GroupStateChange",
        time_utc="now",
        group_ids=changed_group_ids,
    )
    await mock_hub.websocket_notification(cast(WebsocketV2Notification, group_change))
    await hass.async_block_till_done()
    for group_id in platform_common.platforms[0].group_map:
        if len(changed_group_ids) > BULK_GROUP_UPDATE_THRESHOLD:
            # If the number of changed groups exceeds BULK_GROUP_UPDATE_THRESHOLD,
            # lights are updated by getting the state of all light groups from the hub
            # and calling update_state on each of the entities, passing in
            # the updated state of each group. This means that the async_update
            # method on the entity will not be called and thus the update_state()
            # method on the _group member will not be called
            platform_common.platforms[0].group_map[
                group_id
            ]._group.update_state.assert_not_called()
        else:
            # If the number of changed groups does not exceed BULK_GROUP_UPDATE_THRESHOLD,
            # lights are updated by calling update_state on each of the entities, without
            # supplying the new state for the group.   This will cause a forced refresh of
            # the entity state, which will call the async_update method on the entity, which
            # will in turn call the update_state() method on the _group member
            count = 0
            for changed_group_id in changed_group_ids:
                if group_id == changed_group_id:
                    count += 1
            assert (
                platform_common.platforms[0]
                .group_map[group_id]
                ._group.update_state.call_count
                == count
            )


async def test_light_turn_on(hass: HomeAssistant, platform_common):
    """Test turning on light."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_ON,
        {
            ATTR_ENTITY_ID: f"{LIGHT_DOMAIN}.{LIGHT_GROUP_ENTITY_ID}",
            "hs_color": [240, 100],
            "brightness": 255,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert platform_common.hub.group.state.power_on
    assert platform_common.hub.group.state.x_chromaticity == 0.136
    assert platform_common.hub.group.state.y_chromaticity == 0.04
    assert platform_common.hub.group.state.brightness == 1.0
    state = hass.states.get(f"{LIGHT_DOMAIN}.{LIGHT_GROUP_ENTITY_ID}")
    assert state.state == STATE_ON


async def test_light_turn_off(hass: HomeAssistant, platform_common):
    """Test turning off light."""
    await hass.services.async_call(
        LIGHT_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: f"{LIGHT_DOMAIN}.{LIGHT_GROUP_ENTITY_ID}"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert not platform_common.hub.group.state.power_on
    state = hass.states.get(f"{LIGHT_DOMAIN}.{LIGHT_GROUP_ENTITY_ID}")
    assert state.state == STATE_OFF
