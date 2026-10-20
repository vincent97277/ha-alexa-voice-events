"""Per-speaker reception intent and current session authority."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VoiceConfigEntry
from .entity import ReceiverEntity, setup_speakers
from .receiver import SpeakerReception


async def async_setup_entry(
    hass: HomeAssistant, entry: VoiceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    setup_speakers(entry, async_add_entities, lambda speaker: [ReceptionSwitch(speaker)])


class ReceptionSwitch(ReceiverEntity, SwitchEntity):
    def __init__(self, receiver: SpeakerReception) -> None:
        super().__init__(receiver, "reception", "Reception")

    @property
    def is_on(self) -> bool:
        return self.receiver.enabled

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"session_id": self.receiver.session.session_id}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.receiver.set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.receiver.set_enabled(False)
