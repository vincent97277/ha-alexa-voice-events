"""Compact reception diagnostics; no utterance history or trial state."""

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VoiceConfigEntry
from .entity import ReceiverEntity, setup_speakers
from .receiver import SpeakerReception


async def async_setup_entry(
    hass: HomeAssistant, entry: VoiceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    setup_speakers(
        entry,
        async_add_entities,
        lambda speaker: [
            ReceptionSensor(speaker, "status", "Reception status"),
            ReceptionSensor(speaker, "last_received", "Last received"),
            ReceptionSensor(speaker, "last_error", "Last error"),
        ],
    )


class ReceptionSensor(ReceiverEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, receiver: SpeakerReception, key: str, name: str) -> None:
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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.key != "status":
            return None
        return {
            "method": self.receiver.config["method"],
            "validation_scope": self.receiver.validation_scope,
            "new_hardware_acceptance": "pending",
        }
