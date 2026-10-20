"""Alexa Voice Events integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .receiver import AccountReceiver

type VoiceConfigEntry = ConfigEntry[AccountReceiver]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.EVENT, Platform.SWITCH, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: VoiceConfigEntry) -> bool:
    receiver = entry.runtime_data = AccountReceiver(hass, entry, None)
    try:
        await receiver.start()
        entry.async_on_unload(entry.add_update_listener(_options_updated))
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await receiver.close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VoiceConfigEntry) -> bool:
    await entry.runtime_data.close()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _options_updated(hass: HomeAssistant, entry: VoiceConfigEntry) -> None:
    await entry.runtime_data.configure()
