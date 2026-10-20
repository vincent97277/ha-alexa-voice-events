"""Use real Home Assistant and upstream objects; mock the remote history boundary."""

from importlib.metadata import version
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aioamazondevices.structures import AmazonVolumeState
from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import __version__ as core_version
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def hass_config_dir(tmp_path):
    """Use a clean HA config, discovering this checkout's custom component."""
    return str(tmp_path)


@pytest.fixture(autouse=True)
def target_environment(enable_custom_integrations):
    """Fail if the locked harness stops testing the declared baseline."""
    assert core_version == "2026.10.1"
    assert version("aioamazondevices") == "16.3.2"


@pytest.fixture
async def upstream(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain="alexa_devices",
        title="Synthetic Alexa",
        unique_id="synthetic-account",
        version=1,
        minor_version=3,
        data={"username": "synthetic@example.invalid", "password": "unused", "login_data": {}},
    )
    entry.add_to_hass(hass)
    coordinator = AmazonDevicesCoordinator(hass, entry, async_get_clientsession(hass))
    device = SimpleNamespace(
        account_name="Test speaker",
        device_type="A20E9PVI3HANVQ",
        voice_control_supported=True,
        online=True,
        serial_number="speaker-a",
        model="Uxbridge",
        parent_clusters=[],
        device_cluster_members={},
    )
    coordinator.async_set_updated_data({"speaker-a": device})
    coordinator.api._device_handler.devices["speaker-a"] = device
    coordinator.api._device_volumes_initialized = True
    coordinator.api._media_handler.update_cached_device_volume(
        "speaker-a", AmazonVolumeState(20, False)
    )
    entry.runtime_data = coordinator
    entry.mock_state(hass, ConfigEntryState.LOADED)
    with patch("aioamazondevices.implementation.history.BACKEND_REFRESH_WAIT_SECONDS", 0):
        yield coordinator


def history_row(stamp: int, *, text: str = "alexa test phrase", serial: str = "speaker-a") -> dict:
    """Synthetic source identity, not a captured household history record."""
    device_type = "A20E9PVI3HANVQ"
    return {
        "timestamp": stamp,
        "utteranceType": "GENERAL",
        "title": text,
        "intent": "SyntheticIntent",
        "subTitle": "Synthetic reply",
        "deviceInfo": None,
        "activityKey": f"synthetic-account#{stamp}#{device_type}#{serial}",
        "voiceHistoryRecordItems": [{"recordItemKey": f"{stamp}#{device_type}#{serial}#0-0"}],
    }


@pytest.fixture
def remote_history(upstream):
    with patch.object(
        upstream.api._history_handler, "_vocal_history_json", new_callable=AsyncMock
    ) as fetch:
        fetch.return_value = {"alexaHistoryRecords": []}
        yield fetch
