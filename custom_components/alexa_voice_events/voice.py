"""Fresh upstream records become self-contained, household-independent events."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol, TypedDict
from uuid import uuid4


class VoiceRecord(Protocol):
    """The upstream fields used by the event contract."""

    timestamp: int
    title: str


class VoiceEnvelope(TypedDict):
    """A flat snapshot; callers must not mutate published envelopes."""

    schema_version: int
    event_id: str
    session_id: str
    device_id: str
    reception_entity_id: str
    source_timestamp_ms: int
    received_at: str
    voice_command: str


@dataclass
class VoiceSession:
    """One speaker's publication authority and record deduplication."""

    account_id: str
    serial: str
    device_id: str
    started_at: datetime
    session_id: str = field(default_factory=lambda: uuid4().hex)
    _seen_ms: int = field(default=0, init=False)

    def accept(
        self, record: VoiceRecord, received_at: datetime, reception_entity_id: str
    ) -> VoiceEnvelope | None:
        """Accept only a new record belonging to this active time window."""
        stamp, text = record.timestamp, record.title
        now_ms = int(received_at.timestamp() * 1000)
        if (
            type(stamp) is not int
            or not self.started_at.timestamp() * 1000 <= stamp <= now_ms
            or now_ms - stamp >= 15_000
            or stamp <= self._seen_ms
            or not isinstance(text, str)
            or not text.strip()
        ):
            return None
        self._seen_ms = stamp
        identity = f"{self.account_id}\0{self.serial}\0{stamp}"
        return {
            "schema_version": 1,
            "event_id": sha256(identity.encode()).hexdigest(),
            "session_id": self.session_id,
            "device_id": self.device_id,
            "reception_entity_id": reception_entity_id,
            "source_timestamp_ms": stamp,
            "received_at": received_at.astimezone(UTC).isoformat(),
            "voice_command": text,
        }
