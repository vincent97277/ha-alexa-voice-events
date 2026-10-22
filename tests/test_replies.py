"""Exercise interruption and replies through the real HA automation engine."""

import asyncio
import json
from datetime import timedelta

import probatio
import pytest
from homeassistant.components.notify.const import NOTIFY_SERVICE_SCHEMA
from homeassistant.components.trace.util import async_get_trace, async_list_traces
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.json import ExtendedJSONEncoder
from homeassistant.util import dt as dt_util

from .conftest import history_row
from .test_blueprint import install_blueprint
from .test_integration import configure, push
from .test_scheduling import signal
from .test_selection import add_speaker


async def prepare(hass, upstream):
    entry = await configure(hass, upstream)
    registry = er.async_get(hass)
    voice = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "event"
    )
    targets = {}
    for key, domain in (("media", "media_player"), ("speak", "notify"), ("announce", "notify")):
        target = registry.async_get_or_create(
            domain,
            "alexa_devices",
            f"speaker-a-{key}",
            device_id=voice.device_id,
            config_entry=upstream.config_entry,
            suggested_object_id=f"arbitrary_{key}",
        )
        hass.states.async_set(
            target.entity_id,
            "unknown" if domain == "notify" else "idle",
            {"supported_features": 4096},
        )
        targets[key] = target.entity_id
    return entry, voice.entity_id, targets


async def test_default_interruption_precedes_household_action(hass, upstream, remote_history):
    entry, voice, targets = await prepare(hass, upstream)
    order = []
    hass.services.async_register(
        "media_player", "media_stop", lambda call: order.append(("stop", call.data["entity_id"]))
    )
    await install_blueprint(hass, upstream, entry=entry, event_ids=[voice])
    hass.services.async_register("test", "record", lambda call: order.append(("household", None)))
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert order == [("stop", [targets["media"]]), ("household", None)]


async def test_reply_renders_after_household_action(hass, upstream, remote_history):
    entry, voice, targets = await prepare(hass, upstream)
    spoken = []
    hass.states.async_set("sensor.synthetic_value", "before")
    hass.services.async_register("media_player", "media_stop", lambda call: None)
    hass.services.async_register(
        "notify", "send_message", lambda call: spoken.append(dict(call.data))
    )
    await install_blueprint(
        hass,
        upstream,
        entry=entry,
        event_ids=[voice],
        inputs={
            "reply_message": "Value after action: {{ states('sensor.synthetic_value') }}",
        },
    )
    hass.services.async_register(
        "test", "record", lambda call: hass.states.async_set("sensor.synthetic_value", "after")
    )
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert spoken == [{"entity_id": [targets["speak"]], "message": "Value after action: after"}]


@pytest.mark.parametrize("mode", ["speak", "announce"])
async def test_saved_reply_options_cannot_redirect_source_speech(
    hass, upstream, remote_history, mode
):
    add_speaker(upstream, "speaker-b")
    entry, voice, targets = await prepare(hass, upstream)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=upstream.config_entry.entry_id, identifiers={("alexa_devices", "speaker-b")}
    )
    reply = er.async_get(hass).async_get_or_create(
        "notify",
        "alexa_devices",
        f"speaker-b-{mode}",
        device_id=device.id,
        config_entry=upstream.config_entry,
    )
    hass.states.async_set(reply.entity_id, "unknown")
    stopped, spoken = [], []
    hass.services.async_register(
        "media_player", "media_stop", lambda call: stopped.extend(call.data["entity_id"])
    )
    hass.services.async_register(
        "notify", "send_message", lambda call: spoken.append(dict(call.data))
    )
    await install_blueprint(
        hass,
        upstream,
        entry=entry,
        event_ids=[voice],
        inputs={
            "reply_message": "Synthetic reply",
            "reply_device": device.id,
            "reply_mode": mode,
        },
    )
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert stopped == [targets["media"]]
    assert spoken == [{"entity_id": [targets["speak"]], "message": "Synthetic reply"}]


@pytest.mark.parametrize(
    "message",
    ["", "  ", "{{ none }}", "{{ ['bad'] }}", "{{ {'bad': 1} }}", "{{ true }}", "{{ 1 / 0 }}"],
)
async def test_empty_or_invalid_reply_never_speaks_or_reverts_household(
    hass, upstream, remote_history, message
):
    entry, voice, _targets = await prepare(hass, upstream)
    spoken = []
    hass.services.async_register(
        "notify", "send_message", lambda call: spoken.append(dict(call.data))
    )
    _entry, _voice, household = await install_blueprint(
        hass,
        upstream,
        entry=entry,
        event_ids=[voice],
        inputs={
            "interrupt_native_reply": False,
            "reply_message": message,
        },
    )
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert spoken == []
    assert household == ["alexa test phrase"]


@pytest.mark.parametrize("failure", ["stop", "household", "notify"])
async def test_error_policy_keeps_completed_household_effects(
    hass, upstream, remote_history, failure
):
    entry, voice, _targets = await prepare(hass, upstream)
    completed, spoken = [], []

    def stop(call):
        if failure == "stop":
            raise HomeAssistantError("synthetic stop failure")

    def household(call):
        completed.append("effect")
        if failure == "household":
            raise HomeAssistantError("synthetic household failure")

    def notify(call):
        spoken.append("attempt")
        if failure == "notify":
            raise HomeAssistantError("synthetic notify failure")

    hass.services.async_register("media_player", "media_stop", stop)
    hass.services.async_register("notify", "send_message", notify)
    await install_blueprint(
        hass, upstream, entry=entry, event_ids=[voice], inputs={"reply_message": "Reply"}
    )
    hass.services.async_register("test", "record", household)
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert completed == ["effect"]
    assert spoken == ([] if failure == "household" else ["attempt"])


@pytest.mark.parametrize("change", ["newer_unmatched", "expired", "off_on", "removed_target"])
async def test_old_reply_is_dropped_after_household_action(
    hass, upstream, remote_history, freezer, change
):
    entry, voice, targets = await prepare(hass, upstream)
    started, release = asyncio.Event(), asyncio.Event()
    spoken, effects = [], []
    hass.services.async_register("media_player", "media_stop", lambda call: None)
    hass.services.async_register(
        "notify", "send_message", lambda call: spoken.append(dict(call.data))
    )
    await install_blueprint(
        hass, upstream, entry=entry, event_ids=[voice], inputs={"reply_message": "Old reply"}
    )

    async def hold(call):
        started.set()
        await release.wait()
        effects.append("completed")

    hass.services.async_register("test", "record", hold)
    freezer.tick(timedelta(seconds=1))
    try:
        remote_history.return_value = {
            "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
        }
        await signal(upstream, "speaker-a")
        await asyncio.wait_for(started.wait(), 1)
        if change == "newer_unmatched":
            freezer.tick(timedelta(seconds=1))
            remote_history.return_value = {
                "alexaHistoryRecords": [
                    history_row(
                        int(dt_util.utcnow().timestamp() * 1000), text="native weather question"
                    )
                ]
            }
            await signal(upstream, "speaker-a")
            for _ in range(100):
                if (
                    hass.states.get(voice).attributes.get("voice_command")
                    == "native weather question"
                ):
                    break
                await asyncio.sleep(0)
            assert hass.states.get(voice).attributes["voice_command"] == "native weather question"
        elif change == "expired":
            freezer.tick(timedelta(seconds=15))
        elif change == "off_on":
            switch = next(s.entity_id for s in hass.states.async_all("switch"))
            await hass.services.async_call(
                "switch", "turn_off", {"entity_id": switch}, blocking=True
            )
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch}, blocking=True
            )
        else:
            er.async_get(hass).async_remove(targets["speak"])
    finally:
        release.set()
    await hass.async_block_till_done()
    assert effects == ["completed"]
    assert spoken == []
    if change in ("newer_unmatched", "expired", "off_on"):
        reasons = set()
        for run in await async_list_traces(hass, "automation", "automation.test_voice"):
            trace = await async_get_trace(hass, "automation.test_voice", run["run_id"])
            exported = json.loads(json.dumps(trace, cls=ExtendedJSONEncoder))
            for steps in exported["trace"].values():
                for step in steps:
                    reason = step.get("changed_variables", {}).get("voice_guard_reason")
                    if reason:
                        reasons.add(reason)
        expected_reason = {
            "newer_unmatched": "event_superseded",
            "expired": "event_expired",
            "off_on": "session_revoked",
        }[change]
        assert expected_reason in reasons


@pytest.mark.parametrize("template, expected", [("{{ 0 }}", "0"), ("{{ 25.1 }}", "25.1")])
async def test_finite_numeric_reply_uses_official_text_validation(
    hass, upstream, remote_history, template, expected
):
    entry, voice, targets = await prepare(hass, upstream)
    spoken = []
    # Use the real notify message schema at the mocked external device boundary.
    schema = NOTIFY_SERVICE_SCHEMA.extend({probatio.Optional("entity_id"): list})
    hass.services.async_register(
        "notify", "send_message", lambda call: spoken.append(dict(call.data)), schema=schema
    )
    await install_blueprint(
        hass,
        upstream,
        entry=entry,
        event_ids=[voice],
        inputs={
            "interrupt_native_reply": False,
            "actions": [],
            "reply_message": template,
        },
    )
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert spoken == [{"entity_id": [targets["speak"]], "message": expected}]


async def test_selected_sensors_reply_uses_values_after_household_actions(
    hass, upstream, remote_history
):
    entry, voice, targets = await prepare(hass, upstream)
    spoken = []
    attributes = {"friendly_name": "Room temperature", "unit_of_measurement": "°C"}
    hass.states.async_set("sensor.synthetic_temperature", "20.0", attributes)
    hass.states.async_set(
        "sensor.synthetic_humidity",
        "43",
        {"friendly_name": "Room humidity", "unit_of_measurement": "%"},
    )
    hass.services.async_register(
        "notify", "send_message", lambda call: spoken.append(dict(call.data))
    )
    await install_blueprint(
        hass,
        upstream,
        entry=entry,
        event_ids=[voice],
        inputs={
            "interrupt_native_reply": False,
            "reply_sensors": ["sensor.synthetic_temperature", "sensor.synthetic_humidity"],
        },
    )
    hass.services.async_register(
        "test",
        "record",
        lambda call: hass.states.async_set("sensor.synthetic_temperature", "22.1", attributes),
    )
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert spoken == [
        {
            "entity_id": [targets["speak"]],
            "message": (
                "Home Assistant reports: Room temperature is 22.1 °C; Room humidity is 43 %."
            ),
        }
    ]


@pytest.mark.parametrize("value", [None, "unknown", "unavailable", "not a number", "nan", "inf"])
async def test_sensor_report_marks_invalid_measurements_unavailable(
    hass, upstream, remote_history, value
):
    entry, voice, targets = await prepare(hass, upstream)
    spoken = []
    hass.states.async_set("sensor.zero", "0", {"friendly_name": "Zero", "unit_of_measurement": "%"})
    if value is not None:
        hass.states.async_set("sensor.missing", value, {"unit_of_measurement": "°C"})
    hass.services.async_register(
        "notify", "send_message", lambda call: spoken.append(call.data["message"])
    )
    await install_blueprint(
        hass,
        upstream,
        entry=entry,
        event_ids=[voice],
        inputs={
            "interrupt_native_reply": False,
            "reply_sensors": ["sensor.zero", "sensor.missing"],
        },
    )
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert spoken == ["Home Assistant reports: Zero is 0 %; sensor.missing is unavailable."]


async def test_custom_reply_overrides_selected_sensors(hass, upstream, remote_history):
    entry, voice, targets = await prepare(hass, upstream)
    spoken = []
    hass.services.async_register(
        "notify", "send_message", lambda call: spoken.append(call.data["message"])
    )
    await install_blueprint(
        hass,
        upstream,
        entry=entry,
        event_ids=[voice],
        inputs={
            "interrupt_native_reply": False,
            "reply_sensors": ["sensor.missing"],
            "reply_message": "Custom reply",
        },
    )
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert spoken == ["Custom reply"]


@pytest.mark.parametrize(
    ("value", "state_class", "expected"),
    [
        ("not a number", "measurement", "unavailable"),
        ("1e9999", "measurement", "unavailable"),
        ("1e9999", None, "unavailable"),
        ("0", "measurement", "0"),
        ("Open", None, "Open"),
    ],
)
async def test_unitless_sensor_report_respects_measurement_metadata(
    hass, upstream, remote_history, value, state_class, expected
):
    entry, voice, targets = await prepare(hass, upstream)
    spoken = []
    hass.states.async_set(
        "sensor.unitless_measurement",
        value,
        {"friendly_name": "Measurement", **({"state_class": state_class} if state_class else {})},
    )
    hass.services.async_register(
        "notify", "send_message", lambda call: spoken.append(call.data["message"])
    )
    await install_blueprint(
        hass,
        upstream,
        entry=entry,
        event_ids=[voice],
        inputs={
            "interrupt_native_reply": False,
            "reply_sensors": ["sensor.unitless_measurement"],
        },
    )
    remote_history.return_value = {
        "alexaHistoryRecords": [history_row(int(dt_util.utcnow().timestamp() * 1000))]
    }
    await push(hass, upstream)
    assert spoken == [f"Home Assistant reports: Measurement is {expected}."]
