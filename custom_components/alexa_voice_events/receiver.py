"""One account owns reception work; each selected speaker owns its authority."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from math import ceil

from aioamazondevices.structures import AmazonVocalRecord
from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .adapter import UnsupportedUpstream, UpstreamAdapter
from .const import DOMAIN, UPSTREAM_DOMAIN
from .profiles import SpeakerConfig, evidence, validate_selection
from .voice import VoiceEnvelope, VoiceSession

DISPATCH_COOLDOWN = 1


class SpeakerReception:
    """A speaker's selection, independent session, observations and subscribers."""

    def __init__(self, account: AccountReceiver, serial: str, config: SpeakerConfig) -> None:
        self.account, self.serial = account, serial
        self.config = config.copy()
        self.coordinator = account.coordinator
        source = dr.async_get(account.hass).async_get_or_create(
            config_entry_id=account.entry.data["alexa_entry_id"],
            identifiers={(UPSTREAM_DOMAIN, serial)},
            name=self.coordinator.data[serial].account_name,
        )
        self.device_id = source.id
        self.requested_enabled = account.entry.data.get("enabled", {}).get(serial, self.allowed)
        self.last_received: datetime | None = None
        self.last_error: str | None = None
        self._listeners: set[Callable[[], None]] = set()
        self._voice_listeners: set[Callable[[VoiceEnvelope], None]] = set()
        self._removers: set[Callable[[], Awaitable[None]]] = set()
        self.reset()

    @property
    def validation_scope(self) -> str:
        return evidence(self.coordinator.data[self.serial].device_type, self.config["method"])

    @property
    def allowed(self) -> bool:
        return self.validation_scope != "unverified" or self.config["allow_unverified"]

    @property
    def enabled(self) -> bool:
        return self.allowed and self.requested_enabled

    def reset(self) -> None:
        self.session = VoiceSession(
            self.account.entry.data["alexa_entry_id"], self.serial, self.device_id, dt_util.utcnow()
        )
        self.state = "ready" if self.enabled else "disabled"
        self.last_error = None if self.allowed else "unverified_opt_in_required"

    def unique_id(self, key: str) -> str:
        return sha256(
            f"{DOMAIN}\0{self.account.entry.data['alexa_entry_id']}\0{self.serial}\0{key}".encode()
        ).hexdigest()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def subscribe_voice(self, listener: Callable[[VoiceEnvelope], None]) -> Callable[[], None]:
        self._voice_listeners.add(listener)
        return lambda: self._voice_listeners.discard(listener)

    def subscribe_removed(self, remove: Callable[[], Awaitable[None]]) -> Callable[[], None]:
        self._removers.add(remove)
        return lambda: self._removers.discard(remove)

    @callback
    def notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    async def remove(self) -> None:
        for remove in tuple(self._removers):
            await remove()

    async def set_enabled(self, enabled: bool) -> None:
        await self.account.set_enabled(self.serial, enabled)


@dataclass
class PendingPush:
    session: VoiceSession
    triggered_at: datetime
    attempts: int = 0


class AccountReceiver:
    """Own the upstream listener, shared bounded worker and configuration lock."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator: AmazonDevicesCoordinator
    ) -> None:
        self.hass, self.entry, self.coordinator = hass, entry, coordinator
        self.adapter = UpstreamAdapter(coordinator)
        self.speakers: dict[str, SpeakerReception] = {}
        self._added: set[Callable[[SpeakerReception], None]] = set()
        self._pending: dict[str, PendingPush] = {}
        self._task: asyncio.Task[None] | None = None
        self._dispatch_cancel: Callable[[], None] | None = None
        self._next_dispatch = dt_util.utcnow()
        self._lock = asyncio.Lock()
        self._closed = False
        self._unsupported: str | None = None

    async def start(self) -> None:
        try:
            self.adapter.start(self._native_updated, self._pushed)
        except UnsupportedUpstream as err:
            self._unsupported = str(err)
        await self.configure()

    def subscribe_added(self, listener: Callable[[SpeakerReception], None]) -> Callable[[], None]:
        self._added.add(listener)
        return lambda: self._added.discard(listener)

    async def configure(self) -> None:
        """Apply the latest options, preserving unaffected objects and sessions."""
        async with self._lock:
            selection = self.entry.options["speakers"]
            if not validate_selection(self.coordinator.data, selection):
                raise ServiceValidationError(
                    "Choose available speakers and supported reception methods"
                )
            for serial in set(self.speakers) - selection.keys():
                speaker = self.speakers.pop(serial)
                speaker.requested_enabled = False
                speaker.reset()
                self._pending.pop(serial, None)
                await speaker.remove()
                registry = er.async_get(self.hass)
                for key in ("voice", "reception", "status", "last_received", "last_error"):
                    domain = (
                        "event" if key == "voice" else "switch" if key == "reception" else "sensor"
                    )
                    if entity_id := registry.async_get_entity_id(
                        domain, DOMAIN, speaker.unique_id(key)
                    ):
                        registry.async_remove(entity_id)
            added = []
            for serial, config in selection.items():
                if serial not in self.speakers:
                    speaker = self.speakers[serial] = SpeakerReception(self, serial, config)
                    added.append(speaker)
                else:
                    speaker = self.speakers[serial]
                    if speaker.config != config:
                        was_allowed = speaker.allowed
                        speaker.config = config.copy()
                        if (
                            not was_allowed
                            and speaker.allowed
                            and serial not in self.entry.data.get("enabled", {})
                        ):
                            speaker.requested_enabled = True
                        speaker.reset()
                        self._pending.pop(serial, None)
            self._refresh_adapter()
            for speaker in added:
                for listener in tuple(self._added):
                    listener(speaker)
            for speaker in self.speakers.values():
                speaker.notify()
            await self._cancel_if_unused()

    def _refresh_adapter(self) -> None:
        if self._unsupported:
            for speaker in self.speakers.values():
                if speaker.enabled:
                    speaker.state, speaker.last_error = "unsupported", self._unsupported
            return
        sources = {
            serial: (
                self.coordinator.data[serial].device_type,
                ceil(speaker.session.started_at.timestamp() * 1000),
            )
            for serial, speaker in self.speakers.items()
            if speaker.enabled and speaker.config["method"] == "volume_push"
        }
        try:
            self.adapter.set_compatibility(sources)
        except UnsupportedUpstream as err:
            for serial in sources:
                self.speakers[serial].state, self.speakers[serial].last_error = (
                    "unsupported",
                    str(err),
                )

    def _publish(
        self, speaker: SpeakerReception, session: VoiceSession, record: AmazonVocalRecord
    ) -> None:
        if (
            self._closed
            or not speaker.enabled
            or speaker.session is not session
            or speaker.state != "ready"
        ):
            return
        reception_id = er.async_get(self.hass).async_get_entity_id(
            "switch", DOMAIN, speaker.unique_id("reception")
        )
        if reception_id is None:
            return
        if event := session.accept(record, dt_util.utcnow(), reception_id):
            speaker.last_received = dt_util.parse_datetime(event["received_at"])
            for listener in tuple(speaker._voice_listeners):
                listener(event.copy())
            speaker.notify()

    @callback
    def _native_updated(self) -> None:
        for serial, speaker in self.speakers.items():
            if speaker.config["method"] == "native" and (
                record := self.adapter.records.get(serial)
            ):
                self._publish(speaker, speaker.session, record)

    @callback
    def _pushed(self, serial: str) -> None:
        speaker = self.speakers.get(serial)
        if self._closed or speaker is None or not speaker.enabled or speaker.state != "ready":
            return
        now = dt_util.utcnow()
        if serial in self._pending:
            self._pending[serial].triggered_at = now
        else:
            self._pending[serial] = PendingPush(speaker.session, now)
        self._schedule()

    @callback
    def _schedule(self, _now: datetime | None = None) -> None:
        if self._closed or not self._pending or self._task is not None:
            return
        if self._dispatch_cancel is not None:
            self._dispatch_cancel()
            self._dispatch_cancel = None
        delay = (self._next_dispatch - dt_util.utcnow()).total_seconds()
        if delay > 0:
            self._dispatch_cancel = async_call_later(self.hass, delay, self._schedule)
        else:
            self._task = self.hass.async_create_background_task(self._fetch(), f"{DOMAIN}-history")

    async def _fetch(self) -> None:
        try:
            for _ in range(2):
                if not self._pending:
                    break
                sessions = {
                    serial: speaker.session
                    for serial, speaker in self.speakers.items()
                    if speaker.enabled and speaker.config["method"] == "volume_push"
                }
                for hint in self._pending.values():
                    hint.attempts += 1
                records = await asyncio.wait_for(self.adapter.fetch(), timeout=20)
                for serial, session in sessions.items():
                    if serial in self.speakers and (record := records.get(serial)):
                        self._publish(self.speakers[serial], session, record)
                for serial, hint in list(self._pending.items()):
                    if serial not in sessions or hint.session is not sessions[serial]:
                        continue
                    record = records.get(serial)
                    if hint.attempts >= 2 or (
                        record is not None
                        and type(record.timestamp) is int
                        and record.timestamp >= int(hint.triggered_at.timestamp() * 1000)
                    ):
                        self._pending.pop(serial, None)
        except asyncio.CancelledError:
            raise
        except Exception:
            for speaker in self.speakers.values():
                if speaker.enabled and speaker.config["method"] == "volume_push":
                    speaker.state, speaker.last_error = "error", "history_fetch_failed"
                    speaker.notify()
            self._pending.clear()
        finally:
            self._task = None
            self._next_dispatch = dt_util.utcnow() + timedelta(seconds=DISPATCH_COOLDOWN)
            self._schedule()

    async def set_enabled(self, serial: str, enabled: bool) -> None:
        async with self._lock:
            speaker = self.speakers[serial]
            if enabled and not speaker.allowed:
                raise ServiceValidationError(
                    "Enable unverified reception explicitly in integration options first"
                )
            if enabled == speaker.enabled:
                return
            speaker.requested_enabled = enabled
            speaker.reset()
            self._pending.pop(serial, None)
            self._refresh_adapter()
            speaker.notify()
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={
                    **self.entry.data,
                    "enabled": {**self.entry.data.get("enabled", {}), serial: enabled},
                },
            )
            await self._cancel_if_unused()

    async def _cancel_if_unused(self) -> None:
        if self._pending:
            return
        if self._dispatch_cancel is not None:
            self._dispatch_cancel()
            self._dispatch_cancel = None
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def close(self) -> None:
        self._closed = True
        for speaker in self.speakers.values():
            speaker.reset()
        self._pending.clear()
        self.adapter.stop()
        await self._cancel_if_unused()
