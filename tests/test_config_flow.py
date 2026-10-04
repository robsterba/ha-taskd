"""Tests for the taskd config flow and options flow."""

from unittest.mock import AsyncMock

from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.taskd.const import (
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from custom_components.taskd.exceptions import TaskdApiError, TaskdConnectionError


async def test_user_flow_success(
    hass: HomeAssistant, client, setup_integration
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "192.168.1.140:8000"}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "taskd"
    # Bare host:port is normalized with scheme and kept as entered with port
    assert result["data"][CONF_URL] == "http://192.168.1.140:8000"

    client.async_get_health.assert_awaited_once()


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, client, setup_integration
) -> None:
    client.async_get_health = AsyncMock(side_effect=TaskdConnectionError("boom"))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "http://192.168.1.140:8000"}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"url": "cannot_connect"}


async def test_user_flow_invalid_url(hass: HomeAssistant, setup_integration) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "http://"}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"url": "invalid_url"}


async def test_options_flow_scan_interval(
    hass: HomeAssistant, client, setup_integration
) -> None:
    entry = await setup_integration()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    # Default is pre-filled
    assert result["data_schema"]({}) == {
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        CONF_API_KEY: "",
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 120}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 120, CONF_API_KEY: ""}

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.update_interval.total_seconds() == 120


async def test_options_flow_rejects_below_minimum(
    hass: HomeAssistant, client, setup_integration
) -> None:
    entry = await setup_integration()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 5}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"scan_interval": "invalid_scan_interval"}
    # Entry options unchanged: no reload happened
    assert entry.options == {}


async def test_user_flow_with_api_key(
    hass: HomeAssistant, client, setup_integration
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "http://192.168.1.140:8000", CONF_API_KEY: "secret-123"},
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_URL: "http://192.168.1.140:8000",
        CONF_API_KEY: "secret-123",
    }
    validation_calls = [
        c
        for c in client.async_list_tasks.await_args_list
        if c.args and c.args[0] == {"limit": 1}
    ]
    assert len(validation_calls) == 1


async def test_user_flow_invalid_api_key(
    hass: HomeAssistant, client, setup_integration
) -> None:
    client.async_list_tasks = AsyncMock(
        side_effect=TaskdApiError(401, "Invalid or missing API key")
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "http://192.168.1.140:8000", CONF_API_KEY: "wrong"},
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {CONF_API_KEY: "invalid_api_key"}


async def test_user_flow_without_api_key_skips_validation(
    hass: HomeAssistant, client, setup_integration
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "http://192.168.1.140:8000"}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_API_KEY not in result["data"]
    validation_calls = [
        c
        for c in client.async_list_tasks.await_args_list
        if c.args and c.args[0] == {"limit": 1}
    ]
    assert not validation_calls


async def test_options_flow_updates_api_key(
    hass: HomeAssistant, client, setup_integration
) -> None:
    entry = await setup_integration()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 60, CONF_API_KEY: "new-key"}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_SCAN_INTERVAL: 60, CONF_API_KEY: "new-key"}
