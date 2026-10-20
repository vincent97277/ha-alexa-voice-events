"""Drive real config flows, push dispatch, parser and HA entities."""

import asyncio
from copy import deepcopy
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import history_row

DOMAIN = "alexa_voice_events"


async def configure(hass: HomeAssistant, upstream):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "alexa_entry_id": upstream.config_entry.entry_id,
        },
    )
    assert result["step_id"] == "speaker"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "speakers": ["speaker-a"],
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "volume_push", "allow_unverified": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    return result["result"]


async def push(hass: HomeAssistant, upstream):
    await upstream.api._http2_push_event_handler(
        "PUSH_VOLUME_CHANGE",
        {
            "dopplerId": {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"},
            "volumeSetting": 21,
            "isMuted": False,
        },
    )
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_select_speaker_and_receive_a_real_parsed_event(hass, upstream, remote_history):
    entry = await configure(hass, upstream)
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    event_id = next(e.entity_id for e in entries if e.domain == "event")
    switch_id = next(e.entity_id for e in entries if e.domain == "switch")
    assert hass.states.get(switch_id).state == "on"
    assert hass.states.get(event_id).attributes["event_type"] is None
    stamp = int(dt_util.utcnow().timestamp() * 1000)
    remote_history.return_value = {"alexaHistoryRecords": [history_row(stamp)]}
    await push(hass, upstream)
    state = hass.states.get(event_id)
    assert state.attributes["voice_command"] == "alexa test phrase"
    assert state.attributes["event_type"] == "voice_received"
    assert state.attributes["reception_entity_id"] == switch_id
    assert state.attributes["session_id"] == hass.states.get(switch_id).attributes["session_id"]
    assert upstream.vocal_records["speaker-a"].title == "alexa test phrase"
    assert upstream._volume_states["speaker-a"].volume == 21
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)


@pytest.mark.parametrize(
    "bad_source", ["unknown", "wrong_type", "conflict", "malformed", "wake_word"]
)
async def test_real_parser_never_emits_an_untrusted_source(
    hass, upstream, remote_history, bad_source
):
    await configure(hass, upstream)
    row = history_row(int(dt_util.utcnow().timestamp() * 1000))
    if bad_source == "unknown":
        row = history_row(row["timestamp"], serial="unselected-speaker")
    elif bad_source == "wrong_type":
        row["activityKey"] = row["activityKey"].replace("A20E9PVI3HANVQ", "other-type")
    elif bad_source == "conflict":
        row["voiceHistoryRecordItems"][0]["recordItemKey"] = f"{row['timestamp']}#other#other#0"
    elif bad_source == "malformed":
        row["activityKey"] = "not-a-source-key"
    else:
        row["utteranceType"] = "WAKE_WORD_ONLY"
        row["deviceInfo"] = {"deviceSerialNumber": "speaker-a"}
    remote_history.return_value = {"alexaHistoryRecords": [row]}
    await push(hass, upstream)
    assert all(s.attributes["event_type"] is None for s in hass.states.async_all("event"))
    assert remote_history.await_count <= 2


async def test_native_association_and_raw_payload_are_preserved(hass, upstream, remote_history):
    await configure(hass, upstream)
    row = history_row(int(dt_util.utcnow().timestamp() * 1000))
    row["deviceInfo"] = {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"}
    original = deepcopy(row)
    remote_history.return_value = {"alexaHistoryRecords": [row]}
    await push(hass, upstream)
    assert row == original
    assert (
        next(iter(hass.states.async_all("event"))).attributes["voice_command"]
        == "alexa test phrase"
    )


async def test_invalid_selections_and_duplicate_account_are_rejected(
    hass, upstream, remote_history
):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"alexa_entry_id": "missing"}
        )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "alexa_entry_id": upstream.config_entry.entry_id,
        },
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(result["flow_id"], {"speakers": ["foreign"]})
    hass.config_entries.flow.async_abort(result["flow_id"])
    await configure(hass, upstream)
    duplicate = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    duplicate = await hass.config_entries.flow.async_configure(
        duplicate["flow_id"],
        {
            "alexa_entry_id": upstream.config_entry.entry_id,
        },
    )
    assert duplicate["type"] is FlowResultType.ABORT
    assert duplicate["reason"] == "already_configured"


async def test_without_an_existing_account_no_credentials_are_requested(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "alexa_required"


async def test_a_second_fetch_does_not_delay_the_first_accepted_event(
    hass, upstream, remote_history, freezer
):
    await configure(hass, upstream)
    freezer.tick(timedelta(seconds=1))
    row = history_row(int(dt_util.utcnow().timestamp() * 1000))
    freezer.tick(timedelta(seconds=1))  # Force one conditional follow-up.
    second_started, release = asyncio.Event(), asyncio.Event()
    requests = 0

    async def history():
        nonlocal requests
        requests += 1
        if requests == 2:
            second_started.set()
            await release.wait()
        return {"alexaHistoryRecords": [row]}

    remote_history.side_effect = history
    await upstream.api._http2_push_event_handler(
        "PUSH_VOLUME_CHANGE",
        {
            "dopplerId": {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"},
            "volumeSetting": 24,
            "isMuted": False,
        },
    )
    try:
        await second_started.wait()
        assert (
            next(iter(hass.states.async_all("event"))).attributes["voice_command"]
            == "alexa test phrase"
        )
    finally:
        release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert requests == 2


async def test_reception_off_cancels_late_remote_work(hass, upstream, remote_history, freezer):
    await configure(hass, upstream)
    freezer.tick(timedelta(seconds=1))
    row = history_row(int(dt_util.utcnow().timestamp() * 1000))
    started = asyncio.Event()

    async def delayed_history():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return {"alexaHistoryRecords": [row]}

    remote_history.side_effect = delayed_history
    await upstream.api._http2_push_event_handler(
        "PUSH_VOLUME_CHANGE",
        {
            "dopplerId": {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"},
            "volumeSetting": 25,
            "isMuted": False,
        },
    )
    await started.wait()
    switch_id = next(s.entity_id for s in hass.states.async_all("switch"))
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch_id}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(switch_id).state == "off"
    assert next(iter(hass.states.async_all("event"))).attributes["event_type"] is None


async def test_unload_leaves_native_volume_handling_and_stops_compatibility_fetch(
    hass, upstream, remote_history
):
    entry = await configure(hass, upstream)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    await push(hass, upstream)
    assert remote_history.await_count == 0
    assert upstream._volume_states["speaker-a"].volume == 21


async def test_overlapping_push_keeps_the_latest_hint_with_two_attempts(
    hass, upstream, remote_history, freezer
):
    await configure(hass, upstream)
    freezer.tick(timedelta(seconds=1))
    first = history_row(int(dt_util.utcnow().timestamp() * 1000))
    started, release = asyncio.Event(), asyncio.Event()
    requests = 0

    async def history():
        nonlocal requests
        requests += 1
        if requests == 1:
            started.set()
            await release.wait()
            return {"alexaHistoryRecords": [first]}
        return {
            "alexaHistoryRecords": [
                history_row(int(dt_util.utcnow().timestamp() * 1000), text="newer phrase")
            ]
        }

    remote_history.side_effect = history
    payload = {
        "dopplerId": {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"},
        "volumeSetting": 22,
        "isMuted": False,
    }
    await upstream.api._http2_push_event_handler("PUSH_VOLUME_CHANGE", payload)
    try:
        await asyncio.wait_for(started.wait(), 1)
        freezer.tick(timedelta(seconds=1))
        await upstream.api._http2_push_event_handler("PUSH_VOLUME_CHANGE", payload)
    finally:
        release.set()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert requests == 2
    assert next(iter(hass.states.async_all("event"))).attributes["voice_command"] == "newer phrase"
