"""Tests for the Ketra config flow."""
from contextlib import contextmanager
from unittest.mock import Mock, patch

from homeassistant import config_entries, data_entry_flow
from homeassistant.components.ketra import config_flow
from homeassistant.components.ketra.const import DOMAIN
from homeassistant.const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant

from tests.common import MockConfigEntry

FAKE_ACCOUNT_INFO = {
    CONF_USERNAME: "blah",
    CONF_PASSWORD: "blah",
    CONF_CLIENT_ID: "blah",
    CONF_CLIENT_SECRET: "blah",
}


@contextmanager
def setup_config_flow(
    hass: HomeAssistant, patched_request_token=None, patched_get_installations=None
):
    """Patch the config flow."""
    flow = config_flow.KetraConfigFlow()
    flow.hass = hass
    if not patched_request_token:
        yield flow
    else:
        with patch(
            "homeassistant.components.ketra.config_flow.OAuthTokenResponse.request_token",
            new=patched_request_token,
        ):
            if not patched_get_installations:
                yield flow
            else:
                with patch(
                    "homeassistant.components.ketra.config_flow.KetraConfigFlow._get_installations",
                    new=patched_get_installations,
                ):
                    yield flow


async def patched_token_request_failure(*_):
    """Simulate a token request failure."""
    return None


async def patched_token_request_success(*_):
    """Simulate a token request success."""
    oauth_request = Mock()
    oauth_request.access_token = "1234"
    return oauth_request


async def patched_get_installations_failure(*_):
    """Simulate a get installations failure."""
    return None


async def patched_get_installations_success(*_):
    """Simulate a get installations success."""
    return {"123456": "My Installation"}


async def patched_get_installations_empty(*_):
    """Simulate a get installations success that returns an empty set."""
    return {}


async def test_show_form(hass: HomeAssistant):
    """Test that the form is served with no input."""
    with setup_config_flow(hass) as flow:
        result = await flow.async_step_user(user_input=None)

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"
        assert result["errors"] is None


async def test_oauth_error_handling(hass: HomeAssistant):
    """Test that a login error is displayed when the oauth token request fails."""
    with setup_config_flow(hass, patched_token_request_failure) as flow:
        result = await flow.async_step_user(user_input=FAKE_ACCOUNT_INFO)

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"
        assert result["errors"] == {CONF_PASSWORD: "login"}


async def test_server_connection_error_handling(hass: HomeAssistant):
    """Test that a connection error is displayed when _get_installations() returns None."""
    with setup_config_flow(
        hass, patched_token_request_success, patched_get_installations_failure
    ) as flow:
        result = await flow.async_step_user(user_input=FAKE_ACCOUNT_INFO)

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "init"
        assert result["errors"] == {"installation_id": "connection"}


async def test_show_select_installations(hass: HomeAssistant):
    """Test that the select installations form is shown."""
    with setup_config_flow(
        hass, patched_token_request_success, patched_get_installations_success
    ) as flow:
        result = await flow.async_step_user(user_input=FAKE_ACCOUNT_INFO)

        assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert result["step_id"] == "select_installation"
        assert result["errors"] is None
        assert result["data_schema"].schema.get("installation_id").container == {
            "123456": "My Installation"
        }


async def test_abort_if_no_installations(hass: HomeAssistant):
    """Test that we abort if there are no installations available."""
    with setup_config_flow(
        hass, patched_token_request_success, patched_get_installations_empty
    ) as flow:
        result = await flow.async_step_user(user_input=FAKE_ACCOUNT_INFO)

        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "no_installations"


async def test_abort_if_installations_configured(hass: HomeAssistant):
    """Test that the config flow is aborted if all installations are already configured."""
    with setup_config_flow(
        hass, patched_token_request_success, patched_get_installations_success
    ) as flow:
        MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ACCESS_TOKEN: "12345",
                "installation_id": "123456",
                "installation_name": "my inst",
            },
        ).add_to_hass(hass)

        result = await flow.async_step_user(user_input=FAKE_ACCOUNT_INFO)

        assert result["type"] == data_entry_flow.RESULT_TYPE_ABORT
        assert result["reason"] == "no_installations"


async def test_flow_init(hass: HomeAssistant):
    """Test that the flow is initialized."""
    with setup_config_flow(
        hass, patched_token_request_success, patched_get_installations_success
    ):
        flow = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=None,
        )
        assert flow["step_id"] == "init"
        assert flow["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert flow["errors"] is None
        assert flow["flow_id"] is not None


async def test_entry_created(hass: HomeAssistant):
    """Test that the config entry is created when the config flow is completed."""
    with setup_config_flow(
        hass, patched_token_request_success, patched_get_installations_success
    ):
        flow = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=FAKE_ACCOUNT_INFO,
        )

        assert flow["step_id"] == "select_installation"
        assert flow["type"] == data_entry_flow.RESULT_TYPE_FORM
        assert flow["errors"] is None
        assert flow["flow_id"] is not None

        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], user_input={"installation_id": "123456"}
        )

        assert result
        assert isinstance(result, dict)
        assert result["title"] == "My Installation"
        assert result["data"]["access_token"] == "1234"
        assert result["data"]["installation_id"] == "123456"
        assert result["data"]["installation_name"] == result["title"]


class _MockResponse:
    def __init__(self, status, json):
        self.json_data = json
        self._status = status

    @property
    def status_code(self):
        """Return the status."""
        return self._status

    def json(self):
        """Return the json."""
        return self.json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self


class _MockClientSession:
    locations_resp = (200, {})
    n4_query_resp = (200, {})

    def __init__(self):
        pass

    async def get(self, url):
        """Return the mock response."""
        if url.startswith("https://my.goketra.com/api/v4/locations.json"):
            return _MockResponse(*self.locations_resp)
        if url.startswith("https://my.goketra.com/api/n4/v1/query"):
            return _MockResponse(*self.n4_query_resp)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return self


async def test_get_installations():
    """Test the happy path of _get_installations."""
    _MockClientSession.locations_resp = (
        200,
        {"content": [{"id": "12345", "title": "my_inst"}]},
    )
    _MockClientSession.n4_query_resp = (
        200,
        {"content": [{"installation_id": "12345"}]},
    )

    with patch("httpx.AsyncClient", _MockClientSession):
        flow = config_flow.KetraConfigFlow()
        inst_map = await flow._get_installations()  # pylint: disable=protected-access
        assert len(inst_map) == 1


async def test_get_installations_failures():
    """Test the failure cases of _get_installations."""
    _MockClientSession.locations_resp = (400, {})
    _MockClientSession.n4_query_resp = (
        200,
        {"content": [{"installation_id": "12345"}]},
    )

    with patch("httpx.AsyncClient", _MockClientSession):
        flow = config_flow.KetraConfigFlow()
        inst_map = await flow._get_installations()  # pylint: disable=protected-access
        assert inst_map is None

    _MockClientSession.locations_resp = (
        200,
        {"content": [{"id": "12345", "title": "my_inst"}]},
    )
    _MockClientSession.n4_query_resp = (400, {})

    with patch("httpx.AsyncClient", _MockClientSession):
        flow = config_flow.KetraConfigFlow()
        inst_map = await flow._get_installations()  # pylint: disable=protected-access
        assert inst_map is None
