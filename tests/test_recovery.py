"""Recovery through actual HA entry/entity lifecycle and upstream boundaries."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import history_row
from .test_scheduling import signal
from .test_selection import add_speaker, entities_for, select


async def advance(hass, freezer, seconds=5):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_selected_account_delayed_availability_restores_intent_without_falling_back(
    hass, upstream, upstream_factory, remote_history, freezer
):
    add_speaker(upstream, "speaker-b")
    other = upstream_factory("other-account")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    a, b = entities_for(hass, entry, "speaker-a"), entities_for(hass, entry, "speaker-b")
    session = hass.states.get(a["switch"]).attributes["session_id"]
    await hass.services.async_call("switch", "turn_off", {"entity_id": b["switch"]}, blocking=True)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_unload(upstream.config_entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    status = next(
        s
        for s in hass.states.async_all("sensor")
        if s.entity_id.endswith("reception_status") and s.entity_id in a.values()
    )
    assert status.state == "waiting"
    assert hass.states.get(b["switch"]).state == "off"
    assert hass.states.get(a["switch"]).attributes["session_id"] != session
    await advance(hass, freezer)
    assert remote_history.await_count == 0
    assert other.config_entry.state.value == "loaded"


async def test_account_returns_without_replay_and_keeps_the_disabled_speaker_off(
    hass, upstream, remote_history, freezer
):
    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    a, b = entities_for(hass, entry, "speaker-a"), entities_for(hass, entry, "speaker-b")
    freezer.tick(timedelta(seconds=1))
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await signal(upstream, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    old_event = hass.states.get(a["event"]).attributes["event_id"]
    old_session = hass.states.get(a["switch"]).attributes["session_id"]
    await hass.services.async_call("switch", "turn_off", {"entity_id": b["switch"]}, blocking=True)
    assert await hass.config_entries.async_unload(upstream.config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(a["switch"]).attributes["session_id"] != old_session
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(a["event"]).attributes["event_type"] is None

    async def restore(_hass, account):
        account.runtime_data = upstream
        return True

    freezer.tick(timedelta(seconds=1))
    with patch("homeassistant.components.alexa_devices.async_setup_entry", restore):
        assert await hass.config_entries.async_setup(upstream.config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(b["switch"]).state == "off"
    await signal(upstream, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(a["event"]).attributes["event_type"] is None
    freezer.tick(timedelta(seconds=1))
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await signal(upstream, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(a["event"]).attributes["event_id"] != old_event


async def test_device_unavailability_revokes_only_its_session_and_recovers_without_fetch(
    hass, upstream, remote_history, freezer
):
    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    a, b = entities_for(hass, entry, "speaker-a"), entities_for(hass, entry, "speaker-b")
    first = hass.states.get(a["switch"]).attributes["session_id"]
    other = hass.states.get(b["switch"]).attributes["session_id"]
    upstream.data["speaker-a"].online = False
    upstream.async_update_listeners()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(a["switch"]).attributes["session_id"] != first
    assert hass.states.get(b["switch"]).attributes["session_id"] == other
    status = next(
        s
        for s in hass.states.async_all("sensor")
        if s.entity_id.endswith("reception_status") and s.entity_id in a.values()
    )
    assert status.state == "waiting"
    upstream.data["speaker-a"].online = True
    upstream.async_update_listeners()
    await advance(hass, freezer)
    assert hass.states.get(status.entity_id).state == "ready"
    assert remote_history.await_count == 0


@pytest.mark.parametrize("replacement_kind", ["api", "coordinator"])
async def test_api_replacement_rejects_late_callbacks_and_preserves_upstream_ownership(
    hass, upstream, remote_history, freezer, replacement_kind
):
    import asyncio
    from pathlib import Path
    from unittest.mock import AsyncMock

    from aioamazondevices.api import AmazonEchoApi
    from aioamazondevices.structures import AmazonSaveDataConfig
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    entry = await select(hass, upstream, ["speaker-a"])
    source = entities_for(hass, entry, "speaker-a")
    old_api = upstream.api
    old_callback = old_api._handle_volume_change_event
    session = hass.states.get(source["switch"]).attributes["session_id"]
    started = asyncio.Event()

    async def late_history():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return {"alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]}

    remote_history.side_effect = late_history
    freezer.tick(timedelta(seconds=1))
    await signal(upstream, "speaker-a")
    await asyncio.wait_for(started.wait(), 1)
    target = upstream
    if replacement_kind == "coordinator":
        from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator

        target = AmazonDevicesCoordinator(
            hass, upstream.config_entry, async_get_clientsession(hass)
        )
        target.update_interval = None
        target.async_set_updated_data(dict(upstream.data))
    api = (
        target.api
        if replacement_kind == "coordinator"
        else AmazonEchoApi(
            async_get_clientsession(hass),
            "synthetic@example.invalid",
            "unused",
            login_data={},
            save_data=AmazonSaveDataConfig(path=Path(hass.config.path("synthetic-api"))),
        )
    )
    api._device_handler.devices.update(upstream.data)
    api._device_volumes_initialized = True
    fresh_history = AsyncMock(return_value={"alexaHistoryRecords": []})
    api._history_handler._vocal_history_json = fresh_history
    target.api = api
    upstream.config_entry.runtime_data = target
    await advance(hass, freezer)
    assert hass.states.get(source["switch"]).attributes["session_id"] != session
    assert hass.states.get(source["event"]).attributes["event_type"] is None
    await old_callback(
        {
            "dopplerId": {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"},
            "volumeSetting": 31,
            "isMuted": False,
        }
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert fresh_history.await_count == 0
    freezer.tick(timedelta(seconds=1))
    fresh_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await signal(target, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(source["event"]).attributes["event_type"] == "voice_received"
    close = AsyncMock()
    with patch.object(api, "stop_http2_processing", close):
        assert await hass.config_entries.async_unload(entry.entry_id)
    close.assert_not_called()
    assert api._handle_volume_change_event != old_callback


async def test_changing_method_during_shared_fetch_cannot_publish_through_new_native_session(
    hass, upstream, remote_history, freezer
):
    import asyncio

    from .test_selection import options

    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    a, b = entities_for(hass, entry, "speaker-a"), entities_for(hass, entry, "speaker-b")
    started, release = asyncio.Event(), asyncio.Event()
    freezer.tick(timedelta(seconds=1))

    async def history():
        started.set()
        await release.wait()
        stamp = int(dt_util.utcnow().timestamp() * 1000)
        native_row = history_row(stamp, serial="speaker-b")
        native_row["deviceInfo"] = {
            "deviceSerialNumber": "speaker-b",
            "deviceType": "A20E9PVI3HANVQ",
        }
        return {"alexaHistoryRecords": [history_row(stamp), native_row]}

    remote_history.side_effect = history
    await signal(upstream, "speaker-a")
    task = None
    try:
        await asyncio.wait_for(started.wait(), 1)
        task = asyncio.create_task(
            options(
                hass,
                entry,
                {
                    "speaker-a": {"method": "volume_push", "allow_unverified": False},
                    "speaker-b": {"method": "native", "allow_unverified": True},
                },
            )
        )
        for _ in range(100):
            status = hass.states.get(b["reception_status"])
            if status.attributes["method"] == "native":
                break
            await asyncio.sleep(0)
        assert status.attributes["method"] == "native"
        freezer.tick(timedelta(seconds=1))
    finally:
        release.set()
        if task:
            await task
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(a["event"]).attributes["event_type"] == "voice_received"
    assert hass.states.get(b["event"]).attributes["event_type"] is None

    freezer.tick(timedelta(seconds=1))
    await upstream.api._http2_push_event_handler("PUSH_EQUALIZER_STATE_CHANGE", {})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(b["event"]).attributes["event_type"] == "voice_received"


async def test_recent_restore_storage_and_saved_intent_are_safe_on_startup(
    hass, upstream, remote_history, freezer, hass_storage
):
    from pytest_homeassistant_custom_component.common import (
        async_mock_restore_state_shutdown_restart,
        mock_restore_cache_with_extra_data,
    )

    from .test_blueprint import install_blueprint

    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    a, b = entities_for(hass, entry, "speaker-a"), entities_for(hass, entry, "speaker-b")
    _, _, calls = await install_blueprint(
        hass, upstream, entry=entry, event_ids=[a["event"], b["event"]]
    )
    freezer.tick(timedelta(seconds=1))
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await signal(upstream, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert calls == ["alexa test phrase"]
    old = hass.states.get(a["event"])
    session = hass.states.get(a["switch"]).attributes["session_id"]
    await hass.services.async_call("switch", "turn_off", {"entity_id": b["switch"]}, blocking=True)
    await async_mock_restore_state_shutdown_restart(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                old,
                {
                    "last_event_type": "voice_received",
                    "last_event_attributes": dict(old.attributes),
                },
            )
        ],
    )
    freezer.tick(
        timedelta(milliseconds=1)
    )  # Stored event is still within the fifteen-second window.
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(a["event"]).attributes["event_type"] is None
    assert "voice_command" not in hass.states.get(a["event"]).attributes
    assert hass.states.get(a["switch"]).attributes["session_id"] != session
    assert hass.states.get(b["switch"]).state == "off"
    assert calls == ["alexa test phrase"]


async def test_removing_selected_account_waits_and_removing_our_entry_cleans_local_work(
    hass, upstream, upstream_factory, remote_history, freezer
):
    upstream_factory("other-account")
    entry = await select(hass, upstream, ["speaker-a"])
    source = entities_for(hass, entry, "speaker-a")
    old = upstream.api._handle_volume_change_event
    result = await hass.config_entries.async_remove(upstream.config_entry.entry_id)
    assert result["require_restart"] is False
    await advance(hass, freezer)
    assert hass.states.get(source["reception_status"]).state == "waiting"
    assert remote_history.await_count == 0
    result = await hass.config_entries.async_remove(entry.entry_id)
    assert result["require_restart"] is False
    await advance(hass, freezer)
    assert hass.states.get(source["event"]) is None
    await old(
        {
            "dopplerId": {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"},
            "volumeSetting": 28,
            "isMuted": False,
        }
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert remote_history.await_count == 0


async def test_failed_platform_unload_restores_receiving_with_fresh_authority(
    hass, upstream, remote_history, freezer
):
    from unittest.mock import AsyncMock

    from .test_selection import options

    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a"])
    source = entities_for(hass, entry, "speaker-a")
    previous = hass.states.get(source["switch"]).attributes["session_id"]
    with patch(
        "homeassistant.components.sensor.async_unload_entry",
        new_callable=AsyncMock,
        return_value=False,
    ):
        assert not await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(source["event"]) is not None
    assert hass.states.get(source["switch"]).attributes["session_id"] != previous
    freezer.tick(timedelta(seconds=1))
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await signal(upstream, "speaker-a")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get(source["event"]).attributes["event_type"] == "voice_received"
    await options(
        hass,
        entry,
        {
            "speaker-a": {"method": "volume_push", "allow_unverified": False},
            "speaker-b": {"method": "volume_push", "allow_unverified": False},
        },
    )
    assert len(hass.states.async_all("event")) == 2
    assert len(hass.states.async_all("switch")) == 2
