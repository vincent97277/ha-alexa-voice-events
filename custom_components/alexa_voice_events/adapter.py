"""Version-scoped upstream access; never owns credentials or the connection."""

from collections.abc import Callable
from importlib import metadata
from typing import Any

from aioamazondevices.structures import AmazonVocalRecord
from homeassistant import const as ha_const
from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator

from .const import SUPPORTED_CLIENT, SUPPORTED_CORE


def normalize_history(payload: Any, devices: dict[str, tuple[str, int]]) -> Any:
    """Recover a missing association only from consistent known source keys."""
    if not isinstance(payload, dict) or not isinstance(payload.get("alexaHistoryRecords"), list):
        return payload
    rows = []
    for row in payload["alexaHistoryRecords"]:
        if not isinstance(row, dict) or row.get("deviceInfo") is not None:
            rows.append(row)
            continue
        stamp, key = row.get("timestamp"), row.get("activityKey")
        parts = key.split("#") if isinstance(key, str) else []
        items = row.get("voiceHistoryRecordItems") or []
        valid = (
            type(stamp) is int
            and len(parts) == 4
            and bool(parts[0])
            and parts[1] == str(stamp)
            and parts[3] in devices
            and devices[parts[3]][0] == parts[2]
            and stamp >= devices[parts[3]][1]
            and isinstance(items, list)
        )
        if valid:
            for item in items:
                item_key = item.get("recordItemKey") if isinstance(item, dict) else False
                if item_key is None:
                    continue
                item_parts = item_key.split("#") if isinstance(item_key, str) else []
                if len(item_parts) < 4 or item_parts[:3] != [str(stamp), parts[2], parts[3]]:
                    valid = False
                    break
        rows.append(
            {
                **row,
                "deviceInfo": {
                    "deviceSerialNumber": parts[3],
                    "deviceType": parts[2],
                },
            }
            if valid
            else row
        )
    return {**payload, "alexaHistoryRecords": rows}


class UnsupportedUpstream(Exception):
    """A private upstream seam is outside the checked compatibility scope."""


class UpstreamAdapter:
    """One native listener and reversible compatibility hook pair per account."""

    def __init__(self, coordinator: AmazonDevicesCoordinator) -> None:
        self.coordinator = coordinator
        self.api = coordinator.api
        self._restore: Callable[[], None] | None = None
        self._owned: Callable[[], bool] = lambda: False
        self._active = False
        self.compatibility_error: str | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._sources: dict[str, tuple[str, int]] = {}
        self._on_push: Callable[[str], None] = lambda serial: None

    def matches(self, coordinator: AmazonDevicesCoordinator | None) -> bool:
        return coordinator is self.coordinator and coordinator.api is self.api

    def start(self, on_native: Callable[[], None], on_push: Callable[[str], None]) -> None:
        if (
            ha_const.__version__ != SUPPORTED_CORE
            or metadata.version("aioamazondevices") != SUPPORTED_CLIENT
        ):
            raise UnsupportedUpstream("unsupported_version")
        if not isinstance(self.coordinator.data, dict) or not isinstance(self.records, dict):
            raise UnsupportedUpstream("unsupported_structure")
        self._active = True
        self._on_push = on_push
        self._unsubscribe = self.coordinator.async_add_listener(on_native)

    def set_compatibility(self, sources: dict[str, tuple[str, int]]) -> None:
        """Change active sources without disturbing other speakers' sessions."""
        if not sources:
            self._sources = {}
            self._stop_hooks()
            return
        if self._restore is not None and not self._owned():
            self.compatibility_error = "ownership_conflict"
            self._sources = {}
            self._stop_hooks()
        if self.compatibility_error:
            raise UnsupportedUpstream(self.compatibility_error)
        self._sources = sources
        if self._restore is not None:
            return
        api: Any = self.api
        if (
            owner := getattr(api, "_alexa_voice_events_owner", None)
        ) is not None and owner is not self:
            self.compatibility_error = "ownership_conflict"
            self._sources = {}
            raise UnsupportedUpstream(self.compatibility_error)
        handler: Any = getattr(api, "_history_handler", None)
        history = getattr(handler, "_vocal_history_json", None)
        volume = getattr(api, "_handle_volume_change_event", None)
        if (
            not callable(history)
            or not callable(volume)
            or not callable(getattr(api, "sync_history_state", None))
        ):
            self.compatibility_error = "unsupported_structure"
            self._sources = {}
            raise UnsupportedUpstream(self.compatibility_error)

        async def normalized() -> Any:
            return normalize_history(await history(), self._sources)

        async def pushed(payload: dict[str, Any]) -> None:
            await volume(payload)
            source = payload.get("dopplerId")
            if self._active and self._owned() and isinstance(source, dict):
                serial = source.get("deviceSerialNumber")
                if serial in self._sources and source.get("deviceType") == self._sources[serial][0]:
                    self._on_push(serial)

        def restore() -> None:
            if getattr(handler, "_vocal_history_json", None) is normalized:
                handler._vocal_history_json = history
            if getattr(api, "_handle_volume_change_event", None) is pushed:
                api._handle_volume_change_event = volume
            if getattr(api, "_alexa_voice_events_owner", None) is self:
                delattr(api, "_alexa_voice_events_owner")

        self._restore = restore
        self._owned = lambda: (
            getattr(api, "_history_handler", None) is handler
            and getattr(handler, "_vocal_history_json", None) is normalized
            and getattr(api, "_handle_volume_change_event", None) is pushed
        )
        api._alexa_voice_events_owner = self
        handler._vocal_history_json = normalized
        api._handle_volume_change_event = pushed

    def _stop_hooks(self) -> None:
        if self._restore is not None:
            self._restore()
            self._restore = None

    def stop(self) -> None:
        self._active = False
        self._sources = {}
        self._stop_hooks()
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @property
    def records(self) -> dict[str, AmazonVocalRecord]:
        return self.coordinator.vocal_records

    async def fetch(self) -> dict[str, AmazonVocalRecord]:
        await self.coordinator.sync_history_state()
        self.coordinator.async_update_listeners()
        return dict(self.records)
