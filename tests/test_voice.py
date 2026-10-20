"""Public record-to-event contract, with synthetic upstream records."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.alexa_voice_events.voice import VoiceSession


def test_new_record_is_a_self_contained_event_and_same_words_can_repeat():
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    session = VoiceSession("account-a", "speaker-a", "ha-device-a", now - timedelta(seconds=2))
    record = SimpleNamespace(timestamp=int(now.timestamp() * 1000), title="alexa test phrase")
    event = session.accept(record, now, "switch.speaker_reception")
    assert event is not None
    assert event["voice_command"] == "alexa test phrase"
    assert event["schema_version"] == 1
    assert event["device_id"] == "ha-device-a"
    assert event["reception_entity_id"] == "switch.speaker_reception"
    assert "speaker-a" not in event["event_id"]
    assert "account-a" not in event["event_id"]
    assert session.accept(record, now, "switch.speaker_reception") is None
    later = now + timedelta(seconds=1)
    repeated = SimpleNamespace(timestamp=int(later.timestamp() * 1000), title=record.title)
    next_event = session.accept(repeated, later, "switch.speaker_reception")
    assert next_event is not None
    assert next_event["event_id"] != event["event_id"]
    assert next_event["voice_command"] == event["voice_command"]


def test_submillisecond_session_start_rejects_the_previous_millisecond():
    started = datetime(2026, 10, 20, 12, microsecond=500, tzinfo=UTC)
    session = VoiceSession("account-a", "speaker-a", "device-a", started)
    old = SimpleNamespace(timestamp=int(started.timestamp() * 1000), title="old phrase")
    assert session.accept(old, started + timedelta(seconds=1), "switch.reception") is None


@pytest.mark.parametrize(
    "stamp,text",
    [
        (None, "phrase"),
        (True, "phrase"),
        (1.5, "phrase"),
        (float("nan"), "phrase"),
        (1792497600001, "phrase"),
        (1792497585000, "phrase"),
        (1792497600000, ""),
        (1792497600000, "  "),
        (1792497600000, None),
    ],
)
def test_invalid_future_or_stale_records_cannot_become_events(stamp, text):
    now = datetime(2026, 10, 20, 12, tzinfo=UTC)
    session = VoiceSession("account-a", "speaker-a", "device-a", now - timedelta(minutes=1))
    assert (
        session.accept(SimpleNamespace(timestamp=stamp, title=text), now, "switch.reception")
        is None
    )
