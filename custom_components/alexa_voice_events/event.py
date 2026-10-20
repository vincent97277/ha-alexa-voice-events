"""A fresh voice event, explicitly excluding HA's restored last event."""

from homeassistant.components.event import EventEntity, EventExtraStoredData
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VoiceConfigEntry
from .entity import ReceiverEntity, setup_speakers
from .receiver import SpeakerReception
from .voice import VoiceEnvelope


async def async_setup_entry(
    hass: HomeAssistant, entry: VoiceConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    setup_speakers(entry, async_add_entities, lambda speaker: [VoiceEvent(speaker)])


class VoiceEvent(ReceiverEntity, EventEntity):
    _attr_event_types = ["voice_received"]

    def __init__(self, receiver: SpeakerReception) -> None:
        super().__init__(receiver, "voice", "Voice")

    async def async_get_last_event_data(self) -> EventExtraStoredData | None:
        """A restored voice record is never a new command."""
        return None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.receiver.subscribe_voice(self.receive))

    @callback
    def receive(self, envelope: VoiceEnvelope) -> None:
        self._trigger_event("voice_received", dict(envelope))
        self.async_write_ha_state()
