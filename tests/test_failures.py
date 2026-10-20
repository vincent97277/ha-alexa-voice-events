"""Bounded cloud failures and support guards at upstream/HA boundaries."""

from unittest.mock import patch

import pytest

from .test_recovery import advance
from .test_scheduling import signal
from .test_selection import entities_for, select


def diagnostic(hass, source, suffix):
    return hass.states.get(next(e for e in source.values() if e.endswith(suffix)))


async def test_failures_back_off_without_idle_fetches_and_success_resets_the_budget(
    hass, upstream, remote_history, freezer
):
    entry = await select(hass, upstream, ["speaker-a"])
    source = entities_for(hass, entry, "speaker-a")
    remote_history.side_effect = RuntimeError("private account serial voice password")
    for failure, delay in enumerate([30, 60, 120, 240, 240], 1):
        await signal(upstream, "speaker-a")
        await hass.async_block_till_done(wait_background_tasks=True)
        assert remote_history.await_count == failure
        state = diagnostic(hass, source, "reception_status")
        assert state.state == ("error" if failure == 5 else "waiting")
        assert diagnostic(hass, source, "last_error").state == "history_fetch_failed"
        assert diagnostic(hass, source, "last_received").state == "unknown"
        assert "private" not in repr(state.attributes)
        await advance(hass, freezer, delay)
        assert remote_history.await_count == failure  # Local recovery does not poll history.
    remote_history.side_effect = None
    remote_history.return_value = {"alexaHistoryRecords": []}
    await signal(upstream, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert remote_history.await_count == 7  # Success + one conditional follow-up.
    assert diagnostic(hass, source, "reception_status").state == "ready"
    assert diagnostic(hass, source, "last_received").state == "unknown"
    await advance(hass, freezer, 1)
    remote_history.side_effect = RuntimeError("private")
    await signal(upstream, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert diagnostic(hass, source, "reception_status").state == "waiting"
    assert diagnostic(hass, source, "reception_status").attributes["consecutive_failures"] == 1


async def test_foreign_hook_takeover_is_preserved_and_old_callbacks_cannot_receive(
    hass, upstream, remote_history, freezer
):
    native = upstream.api._handle_volume_change_event
    entry = await select(hass, upstream, ["speaker-a"])
    source = entities_for(hass, entry, "speaker-a")
    owned = upstream.api._handle_volume_change_event

    async def foreign(payload):
        await native(payload)

    upstream.api._handle_volume_change_event = foreign
    await advance(hass, freezer)
    assert diagnostic(hass, source, "reception_status").state == "unsupported"
    assert diagnostic(hass, source, "last_error").state == "ownership_conflict"
    assert upstream.api._handle_volume_change_event is foreign
    assert upstream.api._history_handler._vocal_history_json is remote_history
    await owned(
        {
            "dopplerId": {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"},
            "volumeSetting": 29,
            "isMuted": False,
        }
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert remote_history.await_count == 0
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert upstream.api._handle_volume_change_event is foreign


async def test_pushes_during_backoff_wait_for_the_existing_deadline(
    hass, upstream, remote_history, freezer
):
    entry = await select(hass, upstream, ["speaker-a"])
    source = entities_for(hass, entry, "speaker-a")
    remote_history.side_effect = TimeoutError("private payload")
    await signal(upstream, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert diagnostic(hass, source, "last_error").state == "history_timeout"
    await signal(upstream, "speaker-a")
    await advance(hass, freezer, 29)
    assert remote_history.await_count == 1
    await advance(hass, freezer, 1)
    assert remote_history.await_count == 2
    assert diagnostic(hass, source, "reception_status").attributes["consecutive_failures"] == 2


async def test_actual_twenty_second_fetch_timeout_is_canceled_and_sanitized(
    hass, upstream, remote_history, freezer
):
    import asyncio

    entry = await select(hass, upstream, ["speaker-a"])
    source = entities_for(hass, entry, "speaker-a")
    started, canceled = asyncio.Event(), asyncio.Event()

    async def blocked():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            canceled.set()

    remote_history.side_effect = blocked
    await signal(upstream, "speaker-a")
    await asyncio.wait_for(started.wait(), 1)
    await advance(hass, freezer, 21)
    assert canceled.is_set()
    assert remote_history.await_count == 1
    assert diagnostic(hass, source, "last_error").state == "history_timeout"
    assert diagnostic(hass, source, "last_received").state == "unknown"


@pytest.mark.parametrize("environment", ["core", "client"])
async def test_unsupported_versions_preserve_official_native_processing(
    hass, upstream, remote_history, environment
):
    original = upstream.api._handle_volume_change_event
    context = (
        patch("homeassistant.const.__version__", "2099.1.0")
        if environment == "core"
        else patch("importlib.metadata.version", return_value="0.0.0")
    )
    with context:
        entry = await select(hass, upstream, ["speaker-a"])
        source = entities_for(hass, entry, "speaker-a")
        assert diagnostic(hass, source, "reception_status").state == "unsupported"
        assert diagnostic(hass, source, "last_error").state == "unsupported_version"
        assert upstream.api._handle_volume_change_event == original
        await signal(upstream, "speaker-a")
        await hass.async_block_till_done(wait_background_tasks=True)
        assert upstream._volume_states["speaker-a"].volume == 25
        assert remote_history.await_count == 0


async def test_missing_compatibility_structure_leaves_native_reception_working(
    hass, upstream, remote_history, freezer
):
    from aioamazondevices.structures import AmazonVocalRecord
    from homeassistant.util import dt as dt_util

    from .test_selection import add_speaker

    add_speaker(upstream, "native", device_type="SYNTHETIC_NATIVE")
    with patch.object(upstream.api._history_handler, "_vocal_history_json", None):
        entry = await select(
            hass,
            upstream,
            ["speaker-a", "native"],
            {
                "speaker-a": {"method": "volume_push", "allow_unverified": False},
                "native": {"method": "native", "allow_unverified": True},
            },
        )
        compat, native = entities_for(hass, entry, "speaker-a"), entities_for(hass, entry, "native")
        assert diagnostic(hass, compat, "reception_status").state == "unsupported"
        assert diagnostic(hass, compat, "last_error").state == "unsupported_structure"
        await advance(hass, freezer, 1)
        await upstream.history_state_event_handler(
            {
                "native": AmazonVocalRecord(
                    int(dt_util.utcnow().timestamp() * 1000),
                    "GENERAL",
                    "Synthetic",
                    "native phrase",
                    "reply",
                )
            }
        )
        await hass.async_block_till_done(wait_background_tasks=True)
        assert hass.states.get(native["event"]).attributes["voice_command"] == "native phrase"
        assert remote_history.await_count == 0


async def test_existing_owner_is_not_overwritten(hass, upstream, remote_history):
    foreign_owner = object()
    upstream.api._alexa_voice_events_owner = foreign_owner
    native = upstream.api._handle_volume_change_event
    entry = await select(hass, upstream, ["speaker-a"])
    source = entities_for(hass, entry, "speaker-a")
    assert diagnostic(hass, source, "last_error").state == "ownership_conflict"
    assert upstream.api._alexa_voice_events_owner is foreign_owner
    assert upstream.api._handle_volume_change_event == native
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert upstream.api._alexa_voice_events_owner is foreign_owner
    assert upstream.api._history_handler._vocal_history_json is remote_history
