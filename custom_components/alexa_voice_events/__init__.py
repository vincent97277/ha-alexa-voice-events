"""Alexa Voice Events integration."""

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, UPSTREAM_DOMAIN
from .profiles import PROFILES
from .receiver import AccountReceiver

type VoiceConfigEntry = ConfigEntry[AccountReceiver]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.EVENT, Platform.SWITCH, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: VoiceConfigEntry) -> bool:
    account = hass.config_entries.async_get_entry(entry.data["alexa_entry_id"])
    if (
        account is None
        or account.domain != UPSTREAM_DOMAIN
        or account.state is not ConfigEntryState.LOADED
    ):
        raise ConfigEntryNotReady("Selected Alexa account is not loaded")
    serial = entry.data["speaker"]
    coordinator = account.runtime_data
    device = coordinator.data.get(serial)
    if device is None or not device.voice_control_supported or device.device_type not in PROFILES:
        raise ConfigEntryNotReady("Selected speaker is not available for this reception profile")
    registry = dr.async_get(hass)
    source = registry.async_get_or_create(
        config_entry_id=account.entry_id,
        identifiers={(UPSTREAM_DOMAIN, serial)},
        name=device.account_name,
    )
    receiver = entry.runtime_data = AccountReceiver(hass, entry, coordinator, source.id)
    receiver.start()
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await receiver.close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VoiceConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.close()
        return True
    return False
