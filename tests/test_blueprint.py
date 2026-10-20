"""Run the supplied Blueprint through HA's real automation and script engine."""

import asyncio
from datetime import timedelta
from pathlib import Path

from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from .conftest import history_row
from .test_integration import configure, push


async def install_blueprint(hass, upstream):
    entry = await configure(hass, upstream)
    event_id = next(s.entity_id for s in hass.states.async_all("event"))
    source = (
        Path(__file__).parents[1] / "blueprints/automation/alexa_voice_events/phrase_to_action.yaml"
    )
    target = Path(
        hass.config.path("blueprints/automation/alexa_voice_events/phrase_to_action.yaml")
    )

    def copy_blueprint():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text())

    await hass.async_add_executor_job(copy_blueprint)
    calls = []
    hass.services.async_register(
        "test", "record", lambda call: calls.append(call.data["envelope"]["voice_command"])
    )
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "id": "test_voice",
                    "alias": "Test voice",
                    "use_blueprint": {
                        "path": "alexa_voice_events/phrase_to_action.yaml",
                        "input": {
                            "voice_entities": [event_id],
                            "phrases": "alexa test phrase\nother phrase",
                            "actions": [
                                {
                                    "action": "test.record",
                                    "data": {
                                        "envelope": "{{ dict(trigger.to_state.attributes) }}",
                                    },
                                }
                            ],
                        },
                    },
                }
            ]
        },
    )
    await hass.async_block_till_done()
    return entry, event_id, calls


async def test_first_matching_voice_runs_the_selected_action(hass, upstream, remote_history):
    _entry, _event_id, calls = await install_blueprint(hass, upstream)
    assert calls == []
    stamp = int(dt_util.utcnow().timestamp() * 1000)
    text = "  ALEXA   TEST Phrase  "
    remote_history.return_value = {"alexaHistoryRecords": [history_row(stamp, text=text)]}
    await push(hass, upstream)
    assert calls == [text]


async def test_unmatched_speech_off_switch_and_reload_do_not_replay(
    hass, upstream, remote_history, freezer
):
    entry, event_id, calls = await install_blueprint(hass, upstream)
    switch_id = next(s.entity_id for s in hass.states.async_all("switch"))
    remote_history.return_value = {
        "alexaHistoryRecords": [
            history_row(int(dt_util.utcnow().timestamp() * 1000), text="unmatched phrase")
        ]
    }
    await push(hass, upstream)
    assert calls == []
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch_id}, blocking=True)
    freezer.tick(timedelta(seconds=1))
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert calls == []
    assert entry.options["enabled"] is False
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(switch_id).state == "off"
    assert hass.states.get(event_id).attributes["event_type"] is None
    freezer.tick(timedelta(seconds=1))
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch_id}, blocking=True)
    await push(hass, upstream)  # History from before re-enable cannot execute.
    assert calls == []
    freezer.tick(timedelta(seconds=1))
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert calls == ["alexa test phrase"]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(event_id).attributes["event_type"] is None
    assert calls == ["alexa test phrase"]


async def test_entity_rename_keeps_the_blueprint_control_binding(hass, upstream, remote_history):
    _entry, _event_id, calls = await install_blueprint(hass, upstream)
    switch_id = next(s.entity_id for s in hass.states.async_all("switch"))
    er.async_get(hass).async_update_entity(switch_id, new_entity_id="switch.renamed_reception")
    await hass.async_block_till_done()
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert calls == ["alexa test phrase"]


async def test_off_on_revokes_queued_actions_but_not_a_running_user_action(
    hass, upstream, remote_history, freezer
):
    _entry, _event_id, calls = await install_blueprint(hass, upstream)
    started, release = asyncio.Event(), asyncio.Event()

    async def hold_action(call):
        started.set()
        await release.wait()
        calls.append(call.data["envelope"]["voice_command"])

    hass.services.async_register("test", "record", hold_action)
    switch_id = next(s.entity_id for s in hass.states.async_all("switch"))
    freezer.tick(timedelta(seconds=1))
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await upstream.api._http2_push_event_handler(
        "PUSH_VOLUME_CHANGE",
        {
            "dopplerId": {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"},
            "volumeSetting": 22,
            "isMuted": False,
        },
    )
    await asyncio.wait_for(started.wait(), 1)
    freezer.tick(timedelta(seconds=1))
    remote_history.return_value = {
        "alexaHistoryRecords": [
            history_row(int(dt_util.utcnow().timestamp() * 1000), text="other phrase")
        ]
    }
    await upstream.api._http2_push_event_handler(
        "PUSH_VOLUME_CHANGE",
        {
            "dopplerId": {"deviceSerialNumber": "speaker-a", "deviceType": "A20E9PVI3HANVQ"},
            "volumeSetting": 23,
            "isMuted": False,
        },
    )
    for _ in range(30):
        if hass.states.get("automation.test_voice").attributes.get("current") == 2:
            break
        await asyncio.sleep(0)
    assert hass.states.get("automation.test_voice").attributes["current"] == 2
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch_id}, blocking=True)
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch_id}, blocking=True)
    release.set()
    await hass.async_block_till_done()
    assert calls == ["alexa test phrase"]
