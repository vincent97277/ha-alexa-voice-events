"""Reception methods and model evidence, separate from reception logic."""

from dataclasses import dataclass
from typing import Literal, TypedDict

Method = Literal["native", "volume_push"]
METHODS: tuple[Method, ...] = ("native", "volume_push")


class SpeakerConfig(TypedDict):
    method: Method
    allow_unverified: bool


@dataclass(frozen=True)
class ReceptionProfile:
    """Recorded evidence suggests a default; tests never infer hardware acceptance."""

    name: str
    method: Method
    evidence: str


PROFILES = {
    "A20E9PVI3HANVQ": ReceptionProfile("Marshall Uxbridge", "volume_push", "uxbridge_volume_push"),
}


def evidence(device_type: str, method: Method) -> str:
    profile = PROFILES.get(device_type)
    return profile.evidence if profile is not None and profile.method == method else "unverified"


def validate_selection(devices: dict, selection: dict) -> bool:
    """Validate saved selections as well as submitted flow data."""
    return bool(selection) and all(
        serial in devices
        and devices[serial].voice_control_supported
        and isinstance(settings, dict)
        and settings.get("method") in METHODS
        and type(settings.get("allow_unverified")) is bool
        for serial, settings in selection.items()
    )
