"""Per-speaker reception intent and current session authority."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VoiceConfigEntry
from .entity import ReceiverEntity
from .receiver import AccountReceiver


async def async_setup_entry(
    hass: HomeAssistant, entry: VoiceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ReceptionSwitch(entry.runtime_data)])


class ReceptionSwitch(ReceiverEntity, SwitchEntity):
    def __init__(self, receiver: AccountReceiver) -> None:
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
