"""Multi-speaker selection through HA's real flow and entity interfaces."""

import asyncio
from copy import copy
from datetime import timedelta

import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .conftest import history_row
from .test_integration import DOMAIN


async def select(hass, upstream, speakers, configs=None):
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"alexa_entry_id": upstream.config_entry.entry_id}
    )
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"speakers": speakers})
    for _serial in speakers:
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            (configs or {}).get(_serial, {"method": "volume_push", "allow_unverified": False}),
        )
    assert flow["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)
    return flow["result"]


def add_speaker(upstream, serial, *, device_type="A20E9PVI3HANVQ", name="Test speaker"):
    device = copy(next(iter(upstream.data.values())))
    device.serial_number, device.device_type, device.account_name = serial, device_type, name
    upstream.api._device_handler.devices[serial] = device
    upstream.async_set_updated_data({**upstream.data, serial: device})


async def test_two_selected_speakers_have_independent_controls(hass, upstream, remote_history):
    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    switches = [e.entity_id for e in entities if e.domain == "switch"]
    assert len(switches) == 2
    assert len([e for e in entities if e.domain == "event"]) == 2
    sessions = {s: hass.states.get(s).attributes["session_id"] for s in switches}
    await hass.services.async_call("switch", "turn_off", {"entity_id": switches[0]}, blocking=True)
    assert hass.states.get(switches[0]).state == "off"
    assert hass.states.get(switches[1]).state == "on"
    assert hass.states.get(switches[1]).attributes["session_id"] == sessions[switches[1]]
    assert remote_history.await_count == 0


async def options(hass, entry, selection):
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"speakers": list(selection)}
    )
    for config in selection.values():
        flow = await hass.config_entries.options.async_configure(flow["flow_id"], config)
    assert flow["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done(wait_background_tasks=True)


def entities_for(hass, entry, serial):
    registry = er.async_get(hass)
    native_device = dr.async_get(hass).async_get_device_by_identifier(
        ("alexa_devices", serial), entry.data["alexa_entry_id"]
    )
    return {
        entity.domain
        if entity.domain != "sensor"
        else entity.entity_id.rsplit("_", 1)[-1]: entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if entity.device_id == native_device.id
    }


async def test_unverified_native_requires_explicit_options_opt_in_and_uses_source_time(
    hass, upstream, remote_history, freezer
):
    add_speaker(upstream, "unknown", device_type="UNVERIFIED")
    entry = await select(
        hass, upstream, ["unknown"], {"unknown": {"method": "native", "allow_unverified": False}}
    )
    switch = next(s for s in hass.states.async_all("switch"))
    assert switch.state == "off"
    with pytest.raises(ServiceValidationError, match="options"):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": switch.entity_id}, blocking=True
        )
    assert (
        next(s for s in hass.states.async_all("sensor") if s.entity_id.endswith("last_error")).state
        == "unverified_opt_in_required"
    )
    await options(hass, entry, {"unknown": {"method": "native", "allow_unverified": True}})
    assert hass.states.get(switch.entity_id).state == "on"
    freezer.tick(timedelta(seconds=1))
    stamp = int(dt_util.utcnow().timestamp() * 1000)
    row = history_row(stamp, serial="unknown")
    row["deviceInfo"] = {"deviceSerialNumber": "unknown", "deviceType": "UNVERIFIED"}
    remote_history.return_value = {"alexaHistoryRecords": [row]}
    freezer.tick(timedelta(seconds=1))
    await upstream.api._http2_push_event_handler("PUSH_EQUALIZER_STATE_CHANGE", {})
    await hass.async_block_till_done()
    event = next(s for s in hass.states.async_all("event"))
    assert event.attributes["source_timestamp_ms"] == stamp
    assert event.attributes["voice_command"] == "alexa test phrase"
    status = next(
        s for s in hass.states.async_all("sensor") if s.entity_id.endswith("reception_status")
    )
    assert status.attributes["validation_scope"] == "unverified"
    assert status.attributes["method"] == "native"
    assert remote_history.await_count == 1


async def test_options_add_remove_and_method_override_leave_other_sessions_unchanged(
    hass, upstream, remote_history
):
    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a"])
    a = entities_for(hass, entry, "speaker-a")
    original_session = hass.states.get(a["switch"]).attributes["session_id"]
    original_entities = set(a.values())
    await options(
        hass,
        entry,
        {
            "speaker-a": {"method": "volume_push", "allow_unverified": False},
            "speaker-b": {"method": "volume_push", "allow_unverified": False},
        },
    )
    b = entities_for(hass, entry, "speaker-b")
    assert len(hass.states.async_all("event")) == 2
    assert set(entities_for(hass, entry, "speaker-a").values()) == original_entities
    assert hass.states.get(a["switch"]).attributes["session_id"] == original_session
    b_session = hass.states.get(b["switch"]).attributes["session_id"]
    await options(
        hass,
        entry,
        {
            "speaker-a": {"method": "native", "allow_unverified": False},
            "speaker-b": {"method": "volume_push", "allow_unverified": False},
        },
    )
    assert hass.states.get(a["switch"]).state == "off"
    assert hass.states.get(a["switch"]).attributes["session_id"] != original_session
    assert hass.states.get(b["switch"]).attributes["session_id"] == b_session
    await options(
        hass,
        entry,
        {
            "speaker-b": {"method": "volume_push", "allow_unverified": False},
        },
    )
    assert hass.states.get(a["event"]) is None
    assert er.async_get(hass).async_get(a["event"]) is None
    assert hass.states.get(b["switch"]).attributes["session_id"] == b_session
    assert dr.async_get(hass).async_get_device_by_identifier(
        ("alexa_devices", "speaker-a"), entry.data["alexa_entry_id"]
    )
    assert remote_history.await_count == 0


async def test_open_options_does_not_overwrite_concurrent_switch_intent(hass, upstream):
    add_speaker(upstream, "speaker-b")
    entry = await select(hass, upstream, ["speaker-a", "speaker-b"])
    a, b = entities_for(hass, entry, "speaker-a"), entities_for(hass, entry, "speaker-b")
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(
        flow["flow_id"], {"speakers": ["speaker-a", "speaker-b"]}
    )
    await asyncio.gather(
        *(
            hass.services.async_call(
                "switch", "turn_off", {"entity_id": e["switch"]}, blocking=True
            )
            for e in (a, b)
        )
    )
    for _ in range(2):
        flow = await hass.config_entries.options.async_configure(
            flow["flow_id"], {"method": "volume_push", "allow_unverified": False}
        )
    await hass.async_block_till_done(wait_background_tasks=True)
    assert entry.data["enabled"] == {"speaker-a": False, "speaker-b": False}
    assert hass.states.get(a["switch"]).state == hass.states.get(b["switch"]).state == "off"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(a["switch"]).state == hass.states.get(b["switch"]).state == "off"


async def test_accounts_reject_cross_membership_and_preserve_identity_after_rename(
    hass, upstream, upstream_factory
):
    other = upstream_factory("other-account")
    add_speaker(other, "foreign", name="Test speaker")
    entry = await select(hass, upstream, ["speaker-a"])
    second = await select(hass, other, ["foreign"])
    a = entities_for(hass, entry, "speaker-a")
    b = entities_for(hass, second, "foreign")
    assert a["switch"] != b["switch"]
    unique = er.async_get(hass).async_get(a["event"]).unique_id
    device = dr.async_get(hass).async_get(er.async_get(hass).async_get(a["event"]).device_id)
    dr.async_get(hass).async_update_device(device.id, name_by_user="Renamed speaker")
    upstream.data["speaker-a"].account_name = "Renamed speaker"
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            flow["flow_id"], {"speakers": ["foreign"]}
        )
    hass.config_entries.options.async_abort(flow["flow_id"])
    await options(hass, entry, {"speaker-a": {"method": "volume_push", "allow_unverified": False}})
    assert er.async_get(hass).async_get(a["event"]).unique_id == unique
    assert len(list(dr.async_get(hass).devices)) == 2
    await hass.services.async_call("switch", "turn_off", {"entity_id": a["switch"]}, blocking=True)
    assert hass.states.get(b["switch"]).state == "on"


async def test_backend_rechecks_membership_and_capability_before_saving(hass, upstream):
    add_speaker(upstream, "speaker-b")
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"alexa_entry_id": upstream.config_entry.entry_id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"speakers": ["speaker-a", "speaker-b"]}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"method": "volume_push", "allow_unverified": False}
    )
    upstream.data["speaker-a"].voice_control_supported = False
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"method": "volume_push", "allow_unverified": False}
    )
    assert flow["type"] is FlowResultType.ABORT
    assert flow["reason"] == "invalid_speaker"
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_known_and_unknown_selection_suggest_defaults_without_implicit_opt_in(hass, upstream):
    add_speaker(upstream, "unknown", device_type="UNVERIFIED")
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"alexa_entry_id": upstream.config_entry.entry_id}
    )
    flow = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {"speakers": ["speaker-a", "unknown"]}
    )
    assert flow["data_schema"]({}) == {"method": "volume_push", "allow_unverified": False}
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    assert flow["data_schema"]({}) == {"method": "native", "allow_unverified": False}
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    await hass.async_block_till_done(wait_background_tasks=True)
    entry = flow["result"]
    assert hass.states.get(entities_for(hass, entry, "speaker-a")["switch"]).state == "on"
    assert hass.states.get(entities_for(hass, entry, "unknown")["switch"]).state == "off"
