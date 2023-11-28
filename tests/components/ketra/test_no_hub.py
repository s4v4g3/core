"""Tests for situations where the hub is not available."""
from unittest.mock import patch

import pytest

from homeassistant.components.light import DOMAIN as LIGHT_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .common import LIGHT_GROUP_ENTITY_ID, setup_platform


@pytest.mark.parametrize("platform_type", ["light", "scene", "switch"])
async def test_no_hub(hass: HomeAssistant, platform_type: str):
    """Test empty hub."""

    async def patched_get_hub(*args, **kwargs):
        return None

    with patch("aioketraapi.n4_hub.N4Hub.get_hub", new=patched_get_hub), patch(
        "homeassistant.components.ketra.KETRA_PLATFORMS", [platform_type]
    ):
        entry = await setup_platform(hass)
        assert entry is not None
        assert entry.state == ConfigEntryState.SETUP_ERROR
        state = hass.states.get(f"{LIGHT_DOMAIN}.{LIGHT_GROUP_ENTITY_ID}")
        assert state is None
