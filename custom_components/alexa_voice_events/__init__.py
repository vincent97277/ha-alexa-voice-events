"""Alexa Voice Events integration."""

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, UPSTREAM_DOMAIN
from .profiles import validate_selection
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
    coordinator = account.runtime_data
    if not validate_selection(coordinator.data, entry.options.get("speakers", {})):
        raise ConfigEntryNotReady("Selected speakers or reception methods are unavailable")
    receiver = entry.runtime_data = AccountReceiver(hass, entry, coordinator)
    await receiver.start()
    entry.async_on_unload(entry.add_update_listener(_options_updated))
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


async def _options_updated(hass: HomeAssistant, entry: VoiceConfigEntry) -> None:
    await entry.runtime_data.configure()
