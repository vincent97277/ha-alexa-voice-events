"""Compact reception diagnostics; no utterance history or trial state."""

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VoiceConfigEntry
from .entity import ReceiverEntity
from .receiver import AccountReceiver


async def async_setup_entry(
    hass: HomeAssistant, entry: VoiceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            ReceptionSensor(entry.runtime_data, "status", "Reception status"),
            ReceptionSensor(entry.runtime_data, "last_received", "Last received"),
            ReceptionSensor(entry.runtime_data, "last_error", "Last error"),
        ]
    )


class ReceptionSensor(ReceiverEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, receiver: AccountReceiver, key: str, name: str) -> None:
        super().__init__(receiver, key, name)
        self.key = key
        if key == "last_received":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> str | datetime | None:
        if self.key == "status":
            return self.receiver.state
        if self.key == "last_received":
            return self.receiver.last_received
        return self.receiver.last_error
