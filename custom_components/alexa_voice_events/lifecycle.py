"""Observe the selected HA account locally; never own its connection."""

from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import UPSTREAM_DOMAIN


class AccountBinding:
    """Watch public entry states plus local API identity changes without cloud polling."""

    def __init__(self, hass: HomeAssistant, account_id: str, changed: Callable[[], None]) -> None:
        self.hass, self.account_id, self.changed = hass, account_id, changed
        self._account: ConfigEntry | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._timer: Callable[[], None] | None = None

    @property
    def account(self) -> ConfigEntry | None:
        entry = self.hass.config_entries.async_get_entry(self.account_id)
        return entry if entry is not None and entry.domain == UPSTREAM_DOMAIN else None

    @property
    def current(self) -> AmazonDevicesCoordinator | None:
        entry = self.account
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            return None
        coordinator = getattr(entry, "runtime_data", None)
        return (
            coordinator
            if isinstance(coordinator, AmazonDevicesCoordinator)
            and coordinator.config_entry is entry
            else None
        )

    @property
    def reason(self) -> str:
        entry = self.account
        return (
            "unsupported_structure"
            if entry and entry.state is ConfigEntryState.LOADED
            else "account_not_ready"
        )

    def start(self) -> None:
        self._subscribe()
        self._timer = async_track_time_interval(self.hass, self.check, timedelta(seconds=5))

    def _subscribe(self) -> None:
        account = self.account
        if account is self._account:
            return
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._account = account
        if account is not None:
            self._unsubscribe = account.async_on_state_change(self.changed)

    @callback
    def check(self, _now: datetime | None = None) -> None:
        self._subscribe()
        self.changed()

    def stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self._timer is not None:
            self._timer()
            self._timer = None
