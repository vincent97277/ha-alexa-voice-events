"""Known model defaults, separate from reception logic."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReceptionProfile:
    """A known model's reception defaults, not a hardware guarantee."""

    name: str
    method: str


PROFILES = {
    "A20E9PVI3HANVQ": ReceptionProfile("Marshall Uxbridge", "volume_push"),
}
