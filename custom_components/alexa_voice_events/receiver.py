"""Account reception ownership for the initial single-speaker slice."""

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from hashlib import sha256

from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .adapter import UnsupportedUpstream, UpstreamAdapter
from .const import DOMAIN
from .profiles import PROFILES
from .voice import VoiceEnvelope, VoiceSession


class AccountReceiver:
    """Coordinate one account without knowing household phrases or actions."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: AmazonDevicesCoordinator,
        device_id: str,
    ) -> None:
        self.hass, self.entry = hass, entry
        self.coordinator = coordinator
        self.serial: str = entry.data["speaker"]
        self.device_id = device_id
        self.enabled: bool = entry.options.get("enabled", True)
        self.state = "disabled"
        self.last_received: datetime | None = None
        self.last_error: str | None = None
        self.session = self._new_session()
        self.adapter = UpstreamAdapter(
            coordinator, self.serial, PROFILES[coordinator.data[self.serial].device_type]
        )
        self._listeners: set[Callable[[], None]] = set()
        self._voice_listeners: set[Callable[[VoiceEnvelope], None]] = set()
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    def _new_session(self) -> VoiceSession:
        return VoiceSession(
            self.entry.data["alexa_entry_id"], self.serial, self.device_id, dt_util.utcnow()
        )

    def unique_id(self, key: str) -> str:
        """Stable across labels, switch state and reloads."""
        return sha256(
            f"{DOMAIN}\0{self.entry.data['alexa_entry_id']}\0{self.serial}\0{key}".encode()
        ).hexdigest()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def subscribe_voice(self, listener: Callable[[VoiceEnvelope], None]) -> Callable[[], None]:
        self._voice_listeners.add(listener)
        return lambda: self._voice_listeners.discard(listener)

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    def start(self) -> None:
        """Attach a bounded push receiver if reception is requested."""
        if not self.enabled:
            return
        try:
            self.adapter.start(self.session.started_at, self._pushed)
        except UnsupportedUpstream as err:
            self.state, self.last_error = "unsupported", str(err)
        else:
            self.state, self.last_error = "ready", None

    @callback
    def _pushed(self) -> None:
        if self.enabled and not self._closed and self.state == "ready":
            if self._task is None or self._task.done():
                self._task = self.hass.async_create_background_task(
                    self._fetch(self.session, dt_util.utcnow()), f"{DOMAIN}-history"
                )

    async def _fetch(self, session: VoiceSession, pushed_at: datetime) -> None:
        try:
            for _attempt in range(2):
                record = await asyncio.wait_for(self.adapter.fetch(), timeout=20)
                if self._closed or not self.enabled or self.session is not session:
                    return
                reception_id = er.async_get(self.hass).async_get_entity_id(
                    "switch", DOMAIN, self.unique_id("reception")
                )
                if record is not None and reception_id is not None:
                    event = session.accept(record, dt_util.utcnow(), reception_id)
                    if event is not None:
                        self.last_received = dt_util.parse_datetime(event["received_at"])
                        for listener in tuple(self._voice_listeners):
                            listener(event.copy())
                        self._notify()
                if record is not None and record.timestamp >= int(pushed_at.timestamp() * 1000):
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            if self.session is session and not self._closed:
                self.state, self.last_error = "error", "history_fetch_failed"
                self._notify()

    async def _cancel_fetch(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        self._task = None

    async def set_enabled(self, enabled: bool) -> None:
        """Revoke prior work before persisting a reception choice."""
        async with self._lock:
            if enabled == self.enabled:
                return
            self.enabled = enabled
            self.session = self._new_session()
            self.state, self.last_error = "disabled", None
            self._notify()
            self.adapter.stop()
            await self._cancel_fetch()
            self.hass.config_entries.async_update_entry(
                self.entry, options={**self.entry.options, "enabled": enabled}
            )
            self.start()
            self._notify()

    async def close(self) -> None:
        """Unload owned resources without persisting a false off choice."""
        self._closed = True
        self.session = self._new_session()
        self.adapter.stop()
        await self._cancel_fetch()
