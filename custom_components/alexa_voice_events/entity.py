"""Device association and listener ownership shared by HA entities."""

from collections.abc import Callable, Iterable

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VoiceConfigEntry
from .receiver import SpeakerReception


class ReceiverEntity(Entity):
    """An entity attached to the existing upstream physical speaker."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, receiver: SpeakerReception, key: str, name: str) -> None:
        self.receiver = receiver
        self._attr_unique_id = receiver.unique_id(key)
        self._attr_name = name
        self.device_entry = dr.async_get(receiver.account.hass).async_get(receiver.device_id)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.receiver.subscribe(self._updated))
        self.async_on_remove(self.receiver.subscribe_removed(self.async_remove))

    def _updated(self) -> None:
        device = dr.async_get(self.hass).async_get(self.receiver.device_id)
        if device is not None and (self.device_entry is None or self.device_entry.id != device.id):
            self.device_entry = device
            if self.registry_entry is not None:
                er.async_get(self.hass).async_update_entity(self.entity_id, device_id=device.id)
        self.async_write_ha_state()


def setup_speakers(
    entry: VoiceConfigEntry,
    add_entities: AddEntitiesCallback,
    domain: str,
    factory: Callable[[SpeakerReception], Iterable[Entity]],
) -> None:
    """Add current and future selections without reloading existing entities."""
    add_entities(
        [entity for speaker in entry.runtime_data.speakers.values() for entity in factory(speaker)]
    )
    entry.async_on_unload(
        entry.runtime_data.subscribe_added(
            domain, lambda speaker: add_entities(list(factory(speaker)))
        )
    )
