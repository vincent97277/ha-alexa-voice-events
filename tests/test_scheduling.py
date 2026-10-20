"""Cross-speaker dispatch through the real upstream parser and push path."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import history_row
from .test_selection import add_speaker, entities_for, options, select


async def signal(upstream, serial):
    await upstream.api._http2_push_event_handler(
        "PUSH_VOLUME_CHANGE",
        {
            "dopplerId": {
                "deviceSerialNumber": serial,
                "deviceType": upstream.data[serial].device_type,
            },
            "volumeSetting": 25,
            "isMuted": False,
        },
    )


async def test_interleaved_speakers_share_fetches_and_keep_source_identity(
    hass, upstream, remote_history, freezer
):
    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    a, b = entities_for(hass, entry, "speaker-a"), entities_for(hass, entry, "speaker-b")
    started, release = asyncio.Event(), asyncio.Event()
    requests, active, peak = 0, 0, 0
    freezer.tick(timedelta(seconds=1))
    first_stamp = int(dt_util.utcnow().timestamp() * 1000)

    async def history():
        nonlocal requests, active, peak
        requests += 1
        active += 1
        peak = max(active, peak)
        try:
            if requests == 1:
                started.set()
                await release.wait()
                return {"alexaHistoryRecords": [history_row(first_stamp, text="from A")]}
            return {
                "alexaHistoryRecords": [
                    history_row(
                        int(dt_util.utcnow().timestamp() * 1000), serial="speaker-b", text="from B"
                    )
                ]
            }
        finally:
            active -= 1

    remote_history.side_effect = history
    await signal(upstream, "speaker-a")
    try:
        await asyncio.wait_for(started.wait(), 1)
        freezer.tick(timedelta(seconds=1))
        await signal(upstream, "speaker-b")
        await signal(upstream, "speaker-a")
    finally:
        release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert requests == 2 and peak == 1
    assert hass.states.get(a["event"]).attributes["voice_command"] == "from A"
    assert hass.states.get(b["event"]).attributes["voice_command"] == "from B"
    assert hass.states.get(a["event"]).attributes["reception_entity_id"] == a["switch"]
    assert hass.states.get(b["event"]).attributes["reception_entity_id"] == b["switch"]
    assert upstream._volume_states["speaker-a"].volume == 25
    assert upstream._volume_states["speaker-b"].volume == 25


async def test_new_speaker_hint_during_second_attempt_gets_a_bounded_cooldown_turn(
    hass, upstream, remote_history, freezer
):
    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    b = entities_for(hass, entry, "speaker-b")
    second_started, release = asyncio.Event(), asyncio.Event()
    requests = 0
    freezer.tick(timedelta(seconds=1))

    async def history():
        nonlocal requests
        requests += 1
        if requests == 2:
            second_started.set()
            await release.wait()
        if requests < 3:
            return {"alexaHistoryRecords": []}
        return {
            "alexaHistoryRecords": [
                history_row(int(dt_util.utcnow().timestamp() * 1000), serial="speaker-b")
            ]
        }

    remote_history.side_effect = history
    await signal(upstream, "speaker-a")
    try:
        await asyncio.wait_for(second_started.wait(), 1)
        await signal(upstream, "speaker-b")
    finally:
        release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert requests == 2
    freezer.tick(timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert requests == 3
    assert hass.states.get(b["event"]).attributes["voice_command"] == "alexa test phrase"
    freezer.tick(timedelta(seconds=5))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert requests == 3  # No idle history polling.


@pytest.mark.parametrize("change", ["off_on", "remove"])
async def test_revoked_speaker_does_not_publish_shared_inflight_results(
    hass, upstream, remote_history, freezer, change
):
    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    a, b = entities_for(hass, entry, "speaker-a"), entities_for(hass, entry, "speaker-b")
    started, release = asyncio.Event(), asyncio.Event()
    freezer.tick(timedelta(seconds=1))

    async def history():
        started.set()
        await release.wait()
        stamp = int(dt_util.utcnow().timestamp() * 1000)
        return {"alexaHistoryRecords": [history_row(stamp), history_row(stamp, serial="speaker-b")]}

    remote_history.side_effect = history
    await signal(upstream, "speaker-a")
    option_task = None
    try:
        await asyncio.wait_for(started.wait(), 1)
        await signal(upstream, "speaker-b")
        if change == "off_on":
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": b["switch"]}, blocking=True
            )
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": b["switch"]}, blocking=True
            )
        else:
            option_task = asyncio.create_task(
                options(
                    hass, entry, {"speaker-a": {"method": "volume_push", "allow_unverified": False}}
                )
            )
            for _ in range(100):
                if hass.states.get(b["event"]) is None:
                    break
                await asyncio.sleep(0)
            assert hass.states.get(b["event"]) is None
        freezer.tick(timedelta(seconds=1))
    finally:
        release.set()
        if option_task is not None:
            await option_task
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(a["event"]).attributes["event_type"] == "voice_received"
    assert remote_history.await_count == 1
    if change == "off_on":
        assert hass.states.get(b["event"]).attributes["event_type"] is None
        freezer.tick(timedelta(seconds=1))
        await signal(upstream, "speaker-b")
        await hass.async_block_till_done(wait_background_tasks=True)
        assert hass.states.get(b["event"]).attributes["event_type"] == "voice_received"
    else:
        assert hass.states.get(b["event"]) is None


async def test_unverified_compatibility_reuses_method_without_claiming_hardware_support(
    hass, upstream, remote_history, freezer
):
    add_speaker(upstream, "unknown", device_type="SYNTHETIC_TYPE")
    entry = await select(
        hass,
        upstream,
        ["unknown"],
        {"unknown": {"method": "volume_push", "allow_unverified": True}},
    )
    source = entities_for(hass, entry, "unknown")
    assert hass.states.get(source["switch"]).state == "on"
    freezer.tick(timedelta(seconds=1))
    remote_history.return_value = {
        "alexaHistoryRecords": [
            history_row(
                int(dt_util.utcnow().timestamp() * 1000),
                serial="unknown",
                device_type="SYNTHETIC_TYPE",
            )
        ]
    }
    await signal(upstream, "unknown")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(source["event"]).attributes["voice_command"] == "alexa test phrase"
    status = hass.states.get(next(e for e in source.values() if e.endswith("reception_status")))
    assert status.attributes["validation_scope"] == "unverified"
    assert "new_hardware_acceptance" not in status.attributes


async def test_same_serial_and_phrase_in_two_accounts_have_distinct_event_and_control_identity(
    hass, upstream, upstream_factory, remote_history, freezer
):
    other = upstream_factory("other-account")
    with patch.object(
        other.api._history_handler, "_vocal_history_json", new_callable=AsyncMock
    ) as other_history:
        first_entry = await select(hass, upstream, ["speaker-a"])
        second_entry = await select(hass, other, ["speaker-a"])
        a = entities_for(hass, first_entry, "speaker-a")
        b = entities_for(hass, second_entry, "speaker-a")
        freezer.tick(timedelta(seconds=1))
        row = history_row(int(dt_util.utcnow().timestamp() * 1000))
        remote_history.return_value = other_history.return_value = {"alexaHistoryRecords": [row]}
        await signal(upstream, "speaker-a")
        await signal(other, "speaker-a")
        await hass.async_block_till_done(wait_background_tasks=True)
        first, second = hass.states.get(a["event"]), hass.states.get(b["event"])
        assert first.attributes["event_id"] != second.attributes["event_id"]
        assert first.attributes["device_id"] != second.attributes["device_id"]
        assert first.attributes["reception_entity_id"] == a["switch"]
        assert second.attributes["reception_entity_id"] == b["switch"]
        assert remote_history.await_count == other_history.await_count == 1
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": a["switch"]}, blocking=True
        )
        freezer.tick(timedelta(seconds=1))
        other_history.return_value = {
            "alexaHistoryRecords": [
                history_row(int(dt_util.utcnow().timestamp() * 1000), text="other account")
            ]
        }
        await signal(other, "speaker-a")
        await hass.async_block_till_done(wait_background_tasks=True)
        assert hass.states.get(b["event"]).attributes["voice_command"] == "other account"
        assert remote_history.await_count == 1


async def test_continuous_pushes_cannot_extend_a_dispatch_into_an_unbounded_loop(
    hass, upstream, remote_history, freezer
):
    await select(hass, upstream, ["speaker-a"])
    freezer.tick(timedelta(seconds=1))

    async def history():
        await signal(upstream, "speaker-a")
        return {"alexaHistoryRecords": []}

    remote_history.side_effect = history
    await signal(upstream, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert remote_history.await_count == 2
    freezer.tick(timedelta(seconds=2))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert remote_history.await_count == 2
