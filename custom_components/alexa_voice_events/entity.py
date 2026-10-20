"""Device association and listener ownership shared by HA entities."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import UPSTREAM_DOMAIN
from .receiver import AccountReceiver


class ReceiverEntity(Entity):
    """An entity attached to the existing upstream physical speaker."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, receiver: AccountReceiver, key: str, name: str) -> None:
        self.receiver = receiver
        self._attr_unique_id = receiver.unique_id(key)
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(UPSTREAM_DOMAIN, receiver.serial)},
            name=receiver.coordinator.data[receiver.serial].account_name,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.receiver.subscribe(self.async_write_ha_state))
