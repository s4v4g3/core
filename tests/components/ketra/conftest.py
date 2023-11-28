"""Define fixtures available for all tests."""
from unittest.mock import patch

import pytest

from homeassistant.components.ketra import DOMAIN as KETRA_DOMAIN
from homeassistant.core import HomeAssistant

from .common import MockHub, setup_platform


@pytest.fixture
def mock_hub(request):
    """Create a MockHub instance."""
    return MockHub()


@pytest.fixture(name="config_entry", params=[])
async def setup_config_entry(hass: HomeAssistant, mock_hub: MockHub, request):
    """Set up config entry."""

    async def patched_get_hub(*args, **kwargs):
        return mock_hub

    with patch("aioketraapi.n4_hub.N4Hub.get_hub", new=patched_get_hub), patch(
        "homeassistant.components.ketra.KETRA_PLATFORMS", [request.param]
    ), patch("homeassistant.components.ketra.WEBSOCKET_RECONNECT_DELAY", 0.1):
        entry = await setup_platform(hass)
        yield entry


@pytest.fixture(name="platform_common")
async def setup_platform_common(hass: HomeAssistant, config_entry):
    """Set up platform."""
    cmn_plat = hass.data[KETRA_DOMAIN][config_entry.unique_id]["common_platform"]
    yield cmn_plat
    await cmn_plat.shutdown()
