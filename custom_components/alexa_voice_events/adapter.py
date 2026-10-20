"""Version-scoped upstream access; never owns credentials or the connection."""

from collections.abc import Callable
from datetime import datetime
from importlib.metadata import version
from math import ceil
from typing import Any

from aioamazondevices.structures import AmazonVocalRecord
from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator
from homeassistant.const import __version__ as core_version

from .const import SUPPORTED_CLIENT, SUPPORTED_CORE
from .profiles import ReceptionProfile


def normalize_history(payload: Any, devices: dict[str, str], since_ms: int) -> Any:
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
            and stamp >= since_ms
            and len(parts) == 4
            and bool(parts[0])
            and parts[1] == str(stamp)
            and devices.get(parts[3]) == parts[2]
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
    """Wrap only one selected upstream API instance, reversibly."""

    def __init__(
        self, coordinator: AmazonDevicesCoordinator, serial: str, profile: ReceptionProfile
    ) -> None:
        self.coordinator = coordinator
        self.serial = serial
        self.profile = profile
        self._restore: Callable[[], None] | None = None

    def start(self, since: datetime, on_push: Callable[[], None]) -> None:
        """Preserve native handling and notify reception on matching pushes."""
        if core_version != SUPPORTED_CORE or version("aioamazondevices") != SUPPORTED_CLIENT:
            raise UnsupportedUpstream("unsupported_version")
        if self.profile.method != "volume_push":
            raise UnsupportedUpstream("unsupported_method")
        api: Any = self.coordinator.api
        handler: Any = getattr(api, "_history_handler", None)
        history = getattr(handler, "_vocal_history_json", None)
        volume = getattr(api, "_handle_volume_change_event", None)
        if not callable(history) or not callable(volume):
            raise UnsupportedUpstream("unsupported_structure")
        device_type = self.coordinator.data[self.serial].device_type

        async def normalized() -> Any:
            return normalize_history(
                await history(), {self.serial: device_type}, ceil(since.timestamp() * 1000)
            )

        async def pushed(payload: dict[str, Any]) -> None:
            await volume(payload)
            source = payload.get("dopplerId")
            if isinstance(source, dict) and (
                source.get("deviceSerialNumber") == self.serial
                and source.get("deviceType") == device_type
            ):
                on_push()

        def restore() -> None:
            if handler._vocal_history_json is normalized:
                handler._vocal_history_json = history
            if api._handle_volume_change_event is pushed:
                api._handle_volume_change_event = volume

        self._restore = restore
        handler._vocal_history_json = normalized
        api._handle_volume_change_event = pushed

    def stop(self) -> None:
        """Remove only this adapter's wrappers; leave the upstream API alive."""
        if self._restore is not None:
            self._restore()
            self._restore = None

    async def fetch(self) -> AmazonVocalRecord | None:
        """Use the real upstream parser and coordinator notification path."""
        await self.coordinator.sync_history_state()
        self.coordinator.async_update_listeners()
        return self.coordinator.vocal_records.get(self.serial)
