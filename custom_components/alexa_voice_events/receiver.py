"""One account owns reception work; each selected speaker owns its authority."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from importlib import metadata
from math import ceil

from aioamazondevices.structures import AmazonVocalRecord
from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .adapter import UnsupportedUpstream, UpstreamAdapter
from .const import DOMAIN, UPSTREAM_DOMAIN
from .lifecycle import AccountBinding
from .profiles import METHODS, SpeakerConfig, evidence
from .voice import VoiceEnvelope, VoiceSession

DISPATCH_COOLDOWN = 1
FETCH_BACKOFF = (30, 60, 120, 240)


class SpeakerReception:
    """A speaker's selection, independent session, observations and subscribers."""

    def __init__(self, account: AccountReceiver, serial: str, config: SpeakerConfig) -> None:
        self.account, self.serial = account, serial
        self.config = config.copy()
        details = account.device_details(serial)
        self.device_type = details.get("device_type", "")
        source = account.source_device(serial, details.get("name", "Alexa speaker"))
        self.device_id = source.id if source else ""
        self.requested_enabled = account.entry.data.get("enabled", {}).get(serial, True)
        self.last_received: datetime | None = None
        self.last_error: str | None = None
        self._listeners: set[Callable[[], None]] = set()
        self._voice_listeners: set[Callable[[VoiceEnvelope], None]] = set()
        self._removers: set[Callable[[], Awaitable[None]]] = set()
        self._live = False
        self.reset()

    @property
    def validation_scope(self) -> str:
        return evidence(self.device_type, self.config["method"])

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
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator: AmazonDevicesCoordinator | None
    ) -> None:
        self.hass, self.entry, self.coordinator = hass, entry, coordinator
        self.adapter: UpstreamAdapter | None = None
        self._client_version = ""
        self.binding = AccountBinding(hass, entry.data["alexa_entry_id"], self._binding_changed)
        self._reconcile_task: asyncio.Task[None] | None = None
        self._changed = False
        self.speakers: dict[str, SpeakerReception] = {}
        self._added: dict[str, Callable[[SpeakerReception], None]] = {}
        self._pending: dict[str, PendingPush] = {}
        self._task: asyncio.Task[None] | None = None
        self._dispatch_cancel: Callable[[], None] | None = None
        self._next_dispatch = dt_util.utcnow()
        self._lock = asyncio.Lock()
        self._closed = False
        self._stop_listener: Callable[[], None] | None = None
        self._unsupported: str | None = None
        self.consecutive_failures = 0
        self.retry_at = dt_util.utcnow()
        self._fetch_error: str | None = None
        self._fetch_sessions: dict[str, VoiceSession] | None = None

    async def start(self) -> None:
        try:
            self._client_version = await self.hass.async_add_executor_job(
                metadata.version, "aioamazondevices"
            )
        except metadata.PackageNotFoundError:
            self._client_version = ""
        self._closed = False
        self._stop_listener = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._shutdown
        )
        self.binding.start()
        await self._reconcile()

    def device_details(self, serial: str) -> dict[str, str]:
        if (
            self.coordinator is not None
            and isinstance(self.coordinator.data, dict)
            and (device := self.coordinator.data.get(serial))
        ):
            return {"device_type": device.device_type, "name": device.account_name}
        return dict(self.entry.data.get("devices", {}).get(serial, {}))

    def source_device(self, serial: str, name: str) -> dr.DeviceEntry | None:
        registry = dr.async_get(self.hass)
        source = registry.async_get_device_by_identifier(
            (UPSTREAM_DOMAIN, serial), self.entry.data["alexa_entry_id"]
        )
        if source is None and self.binding.account is not None:
            source = registry.async_get_or_create(
                config_entry_id=self.entry.data["alexa_entry_id"],
                identifiers={(UPSTREAM_DOMAIN, serial)},
                name=name,
            )
        return source

    @callback
    def _binding_changed(self) -> None:
        if self._closed:
            return
        current = self.binding.current
        if self.adapter is not None and not self.adapter.matches(current):
            self._revoke_binding()
        self._changed = True
        if self._reconcile_task is None or self._reconcile_task.done():
            self._reconcile_task = self.hass.async_create_task(self._reconcile_changes())

    async def _reconcile_changes(self) -> None:
        while self._changed and not self._closed:
            self._changed = False
            await self._reconcile()

    def _revoke_binding(self) -> None:
        if self.adapter is not None:
            self.adapter.stop()
            self.adapter = None
        self._pending.clear()
        if self._dispatch_cancel is not None:
            self._dispatch_cancel()
            self._dispatch_cancel = None
        for speaker in self.speakers.values():
            speaker.reset()
            if speaker.enabled:
                speaker.state, speaker.last_error = "waiting", "account_not_ready"
            speaker.notify()
        if self._task is not None:
            self._task.cancel()

    async def _reconcile(self) -> None:
        async with self._lock:
            if self._closed:
                return
            current = self.binding.current
            if self.adapter is not None and not self.adapter.matches(current):
                self._revoke_binding()
            if self.adapter is None:
                await self._cancel_if_unused()
                if self._closed:
                    return
                self.consecutive_failures = 0
                self._fetch_error = None
                self.retry_at = dt_util.utcnow()
                self._next_dispatch = dt_util.utcnow()
                self.coordinator = current
                self._unsupported = None
                if current is not None:
                    adapter = UpstreamAdapter(current, self._client_version)
                    try:
                        adapter.start(
                            lambda: self._native_updated(adapter),
                            lambda serial: self._pushed(serial, adapter),
                        )
                    except UnsupportedUpstream as err:
                        self._unsupported = str(err)
                    else:
                        self.adapter = adapter
                    for speaker in self.speakers.values():
                        speaker.reset()
            await self._configure()

    async def configure(self) -> None:
        async with self._lock:
            if not self._closed:
                await self._configure()

    def subscribe_added(
        self, domain: str, listener: Callable[[SpeakerReception], None]
    ) -> Callable[[], None]:
        self._added[domain] = listener

        def remove() -> None:
            if self._added.get(domain) is listener:
                self._added.pop(domain)

        return remove

    async def _configure(self) -> None:
        """Apply the latest options, preserving unaffected objects and sessions."""
        selection = self.entry.options["speakers"]
        if not selection or any(
            config.get("method") not in METHODS or type(config.get("allow_unverified")) is not bool
            for config in selection.values()
        ):
            raise ServiceValidationError("Select supported reception methods")
        for serial in set(self.speakers) - selection.keys():
            speaker = self.speakers.pop(serial)
            speaker.requested_enabled = False
            speaker.reset()
            self._pending.pop(serial, None)
            await speaker.remove()
            registry = er.async_get(self.hass)
            for key in ("voice", "reception", "status", "last_received", "last_error"):
                domain = "event" if key == "voice" else "switch" if key == "reception" else "sensor"
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
        devices = {serial: self.device_details(serial) for serial in selection}
        if devices != self.entry.data.get("devices", {}):
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "devices": devices}
            )
        for speaker in self.speakers.values():
            details = devices[speaker.serial]
            speaker.device_type = details.get("device_type", speaker.device_type)
            source = self.source_device(speaker.serial, details.get("name", "Alexa speaker"))
            if source is not None and speaker.device_id != source.id:
                speaker.device_id = source.id
                speaker.reset()
        self._refresh_adapter()
        for speaker in added:
            for listener in tuple(self._added.values()):
                listener(speaker)
        for speaker in self.speakers.values():
            speaker.notify()
        await self._cancel_if_unused()

    def _refresh_adapter(self) -> None:
        sources = {}
        for serial, speaker in self.speakers.items():
            device = (
                self.coordinator.data.get(serial)
                if self.coordinator is not None and isinstance(self.coordinator.data, dict)
                else None
            )
            if device is not None and speaker.device_type != device.device_type:
                speaker.device_type = device.device_type
                speaker.reset()
            compatibility_error = (
                self.adapter.compatibility_error
                if self.adapter is not None and speaker.config["method"] == "volume_push"
                else None
            )
            live = bool(
                self.adapter is not None
                and not compatibility_error
                and device is not None
                and self.coordinator is not None
                and self.coordinator.last_update_success
                and device.online
                and device.voice_control_supported
                and speaker.enabled
            )
            if live != speaker._live:
                speaker._live = live
                speaker.reset()
                self._pending.pop(serial, None)
            if not speaker.enabled:
                speaker.state = "disabled"
                speaker.last_error = None if speaker.allowed else "unverified_opt_in_required"
            elif self._unsupported:
                speaker.state, speaker.last_error = "unsupported", self._unsupported
            elif self.adapter is None:
                reason = self.binding.reason
                speaker.state = "unsupported" if reason == "unsupported_structure" else "waiting"
                speaker.last_error = reason
            elif compatibility_error:
                speaker.state, speaker.last_error = "unsupported", compatibility_error
            elif not live:
                speaker.state, speaker.last_error = (
                    "waiting",
                    (
                        "account_unavailable"
                        if self.coordinator is not None and not self.coordinator.last_update_success
                        else "speaker_not_available"
                    ),
                )
            else:
                speaker.state, speaker.last_error = "ready", None
                if speaker.config["method"] == "volume_push":
                    if self.consecutive_failures:
                        speaker.state = (
                            "error"
                            if self.consecutive_failures >= 5
                            else ("waiting" if dt_util.utcnow() < self.retry_at else "ready")
                        )
                        speaker.last_error = self._fetch_error
                    sources[serial] = (
                        speaker.device_type,
                        ceil(speaker.session.started_at.timestamp() * 1000),
                    )
            speaker.notify()
        if self.adapter is None:
            return
        try:
            self.adapter.set_compatibility(sources)
        except UnsupportedUpstream as err:
            for serial in sources:
                speaker = self.speakers[serial]
                if speaker.state != "unsupported":
                    speaker.reset()
                speaker._live = False
                self._pending.pop(serial, None)
                speaker.state, speaker.last_error = "unsupported", str(err)
                speaker.notify()

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
    def _native_updated(self, adapter: UpstreamAdapter) -> None:
        if self._closed or adapter is not self.adapter:
            return
        if not adapter.matches(self.binding.current):
            self._binding_changed()
            return
        self._refresh_adapter()
        for serial, speaker in self.speakers.items():
            if speaker.config["method"] == "native" and (record := adapter.records.get(serial)):
                session = (
                    speaker.session
                    if self._fetch_sessions is None
                    else self._fetch_sessions.get(serial)
                )
                if session is not None:
                    self._publish(speaker, session, record)

    @callback
    def _pushed(self, serial: str, adapter: UpstreamAdapter) -> None:
        if adapter is not self.adapter or not adapter.matches(self.binding.current):
            self._binding_changed()
            return
        self._refresh_adapter()
        speaker = self.speakers.get(serial)
        if self._closed or speaker is None or not speaker._live or speaker.state == "unsupported":
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
        adapter = self.adapter
        if adapter is None:
            return
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
                self._fetch_sessions = {
                    serial: speaker.session
                    for serial, speaker in self.speakers.items()
                    if speaker.enabled
                }
                records = await asyncio.wait_for(adapter.fetch(), timeout=20)
                self._fetch_sessions = None
                if adapter is not self.adapter or not adapter.matches(self.binding.current):
                    self._binding_changed()
                    return
                self.consecutive_failures = 0
                self._fetch_error = None
                self.retry_at = dt_util.utcnow()
                self._refresh_adapter()
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
        except Exception as err:
            if adapter is self.adapter and not self._closed:
                self.consecutive_failures = min(5, self.consecutive_failures + 1)
                self._fetch_error = (
                    "history_timeout"
                    if isinstance(err, TimeoutError) or isinstance(err.__cause__, TimeoutError)
                    else "history_fetch_failed"
                )
                delay = FETCH_BACKOFF[min(self.consecutive_failures - 1, len(FETCH_BACKOFF) - 1)]
                self.retry_at = dt_util.utcnow() + timedelta(seconds=delay)
                self._pending.clear()
                self._refresh_adapter()
        finally:
            self._fetch_sessions = None
            self._task = None
            self._next_dispatch = max(
                dt_util.utcnow() + timedelta(seconds=DISPATCH_COOLDOWN), self.retry_at
            )
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

    async def _shutdown(self, _event: Event) -> None:
        await self.close()

    async def close(self) -> None:
        self._closed = True
        if self._stop_listener is not None:
            self._stop_listener()
            self._stop_listener = None
        self.binding.stop()
        self._revoke_binding()
        if self._reconcile_task is not None:
            self._reconcile_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reconcile_task

        await self._cancel_if_unused()
