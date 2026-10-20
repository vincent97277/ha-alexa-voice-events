"""The real HA engine retains source snapshots and dispatch authority across accounts."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util

from .conftest import history_row
from .test_blueprint import install_blueprint
from .test_scheduling import signal
from .test_selection import add_speaker, entities_for, select


async def queue_size(hass, size):
    for _ in range(100):
        if hass.states.get("automation.test_voice").attributes["current"] == size:
            return
        await asyncio.sleep(0)
    assert hass.states.get("automation.test_voice").attributes["current"] == size


@pytest.mark.parametrize("revoke", [False, True, "rebind"])
async def test_blueprint_binds_rapid_snapshots_and_revocation_to_their_account_and_speaker(
    hass, upstream, upstream_factory, remote_history, freezer, revoke
):
    add_speaker(upstream, "native", device_type="SYNTHETIC_NATIVE")
    entry = await select(
        hass,
        upstream,
        ["speaker-a", "native"],
        {
            "speaker-a": {"method": "volume_push", "allow_unverified": False},
            "native": {"method": "native", "allow_unverified": True},
        },
    )
    other = upstream_factory("other-account")
    with patch.object(
        other.api._history_handler, "_vocal_history_json", new_callable=AsyncMock
    ) as other_history:
        second_entry = await select(
            hass,
            other,
            ["speaker-a"],
            {"speaker-a": {"method": "native", "allow_unverified": True}},
        )
        a, b, c = (
            entities_for(hass, e, serial)
            for e, serial in ((entry, "speaker-a"), (entry, "native"), (second_entry, "speaker-a"))
        )
        await install_blueprint(
            hass, upstream, entry=entry, event_ids=[e["event"] for e in (a, b, c)]
        )
        captured, expected = [], []
        started, release = asyncio.Event(), asyncio.Event()

        async def record(call):
            captured.append(dict(call.data["envelope"]))
            if len(captured) == 1:
                started.set()
                await release.wait()

        hass.services.async_register("test", "record", record)
        try:
            freezer.tick(timedelta(seconds=1))
            remote_history.return_value = {
                "alexaHistoryRecords": [
                    history_row(
                        int(dt_util.utcnow().timestamp() * 1000), text="  ALEXA   test phrase  "
                    )
                ]
            }
            await signal(upstream, "speaker-a")
            await asyncio.wait_for(started.wait(), 1)
            expected.append(dict(hass.states.get(a["event"]).attributes))
            freezer.tick(timedelta(seconds=1))
            row = history_row(
                int(dt_util.utcnow().timestamp() * 1000), serial="native", text="other phrase"
            )
            row["deviceInfo"] = {"deviceSerialNumber": "native", "deviceType": "SYNTHETIC_NATIVE"}
            remote_history.return_value = {"alexaHistoryRecords": [row]}
            await upstream.api._http2_push_event_handler("PUSH_EQUALIZER_STATE_CHANGE", {})
            await queue_size(hass, 2)
            expected.append(dict(hass.states.get(b["event"]).attributes))
            freezer.tick(timedelta(seconds=1))
            remote_history.return_value = {
                "alexaHistoryRecords": [
                    history_row(int(dt_util.utcnow().timestamp() * 1000), text="alexa test phrase")
                ]
            }
            await signal(upstream, "speaker-a")
            await queue_size(hass, 3)
            if not revoke:
                expected.append(dict(hass.states.get(a["event"]).attributes))
            freezer.tick(timedelta(seconds=1))
            row = history_row(int(dt_util.utcnow().timestamp() * 1000), text="alexa test phrase")
            row["deviceInfo"] = {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"}
            other_history.return_value = {"alexaHistoryRecords": [row]}
            await other.api._http2_push_event_handler("PUSH_EQUALIZER_STATE_CHANGE", {})
            await queue_size(hass, 4)
            expected.append(dict(hass.states.get(c["event"]).attributes))
            if revoke is True:
                await hass.services.async_call(
                    "switch", "turn_off", {"entity_id": a["switch"]}, blocking=True
                )
            elif revoke == "rebind":
                expected.pop(1)  # Both queued records from this account lose authority.

                async def restore(_hass, account):
                    account.runtime_data = upstream
                    return True

                with patch("homeassistant.components.alexa_devices.async_setup_entry", restore):
                    assert await hass.config_entries.async_reload(upstream.config_entry.entry_id)
        finally:
            release.set()
        await hass.async_block_till_done(wait_background_tasks=True)
        assert captured == expected
        assert captured[0]["reception_entity_id"] == a["switch"]
        if revoke != "rebind":
            assert captured[1]["reception_entity_id"] == b["switch"]
        assert captured[-1]["reception_entity_id"] == c["switch"]
        assert captured[0]["device_id"] != captured[-1]["device_id"]
