"""Resolve official targets through HA's public response-only action."""

from copy import copy

import pytest
from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .test_integration import configure


async def test_selected_source_resolves_official_roles_after_entity_rename(hass, upstream):
    entry = await configure(hass, upstream)
    registry = er.async_get(hass)
    voice = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "event"
    )
    targets = {}
    for role, domain in (("media", "media_player"), ("speak", "notify"), ("announce", "notify")):
        target = registry.async_get_or_create(
            domain,
            "alexa_devices",
            f"speaker-a-{role}",
            config_entry=upstream.config_entry,
            device_id=voice.device_id,
            suggested_object_id=f"original_{role}",
        )
        target = registry.async_update_entity(
            target.entity_id, new_entity_id=f"{domain}.renamed_{role}"
        )
        hass.states.async_set(
            target.entity_id,
            "unknown" if domain == "notify" else "idle",
            {"supported_features": 4096},
        )
        targets[role] = target.entity_id
    result = await hass.services.async_call(
        "alexa_voice_events",
        "resolve_targets",
        {"source_entity_id": voice.entity_id},
        blocking=True,
        return_response=True,
    )
    assert result == {
        "schema_version": 1,
        "source_valid": True,
        "source_reason": None,
        "source_device_id": voice.device_id,
        "reply_device_id": voice.device_id,
        "stop": {"entity_id": targets["media"], "reason": None},
        "speak": {"entity_id": targets["speak"], "reason": None},
        "announce": {"entity_id": targets["announce"], "reason": None},
    }


async def test_api_rebind_immediately_invalidates_source_before_observation_tick(hass, upstream):
    entry = await configure(hass, upstream)
    voice = next(
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "event"
    )
    upstream.api = AmazonDevicesCoordinator(
        hass, upstream.config_entry, async_get_clientsession(hass)
    ).api
    result = await hass.services.async_call(
        "alexa_voice_events",
        "resolve_targets",
        {"source_entity_id": voice.entity_id},
        blocking=True,
        return_response=True,
    )
    assert result["source_valid"] is False
    assert result["source_reason"] == "account_not_ready"


async def test_invalid_explicit_target_never_falls_back_and_source_is_metadata_only(hass, upstream):
    entry = await configure(hass, upstream)
    voice = next(
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "event"
    )
    switch = next(
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "switch"
    )
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": switch.entity_id}, blocking=True
    )
    result = await hass.services.async_call(
        "alexa_voice_events",
        "resolve_targets",
        {"source_entity_id": voice.entity_id, "reply_device_id": "nonexistent-device"},
        blocking=True,
        return_response=True,
    )
    assert result["source_valid"] is True  # Identity is not event/session authorization.
    assert result["stop"]["reason"] == "entity_not_found"
    assert result["speak"] == {"entity_id": None, "reason": "device_not_found"}
    assert result["announce"] == {"entity_id": None, "reason": "device_not_found"}


async def test_one_account_unload_keeps_response_service_for_another(
    hass, upstream, upstream_factory
):
    first = await configure(hass, upstream)
    other = upstream_factory("other")
    second = await configure(hass, other)
    registry = er.async_get(hass)
    voices = [
        next(
            e.entity_id
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if e.domain == "event"
        )
        for entry in (first, second)
    ]
    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()
    results = [
        await hass.services.async_call(
            "alexa_voice_events",
            "resolve_targets",
            {"source_entity_id": voice},
            blocking=True,
            return_response=True,
        )
        for voice in voices
    ]
    assert results[0]["source_valid"] is False
    assert results[1]["source_valid"] is True
    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service("alexa_voice_events", "resolve_targets")
    result = await hass.services.async_call(
        "alexa_voice_events",
        "resolve_targets",
        {"source_entity_id": voices[1]},
        blocking=True,
        return_response=True,
    )
    assert result["source_valid"] is False


async def test_explicit_reply_offline_runtime_is_not_hidden_by_stale_state(hass, upstream):
    entry = await configure(hass, upstream)
    registry = er.async_get(hass)
    voice = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "event"
    )
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=upstream.config_entry.entry_id,
        identifiers={("alexa_devices", "speaker-offline")},
    )
    target = registry.async_get_or_create(
        "notify",
        "alexa_devices",
        "speaker-offline-speak",
        config_entry=upstream.config_entry,
        device_id=device.id,
    )
    hass.states.async_set(target.entity_id, "unknown")
    result = await hass.services.async_call(
        "alexa_voice_events",
        "resolve_targets",
        {"source_entity_id": voice.entity_id, "reply_device_id": device.id},
        blocking=True,
        return_response=True,
    )
    assert result["source_valid"] is True
    assert result["speak"]["entity_id"] is None
    assert result["speak"]["reason"] == "entity_unavailable"


@pytest.mark.parametrize(
    "issue, reason",
    [
        ("disabled", "entity_disabled"),
        ("unavailable", "entity_unavailable"),
        ("unsupported", "unsupported_capability"),
        ("missing", "entity_not_found"),
    ],
)
async def test_stop_role_failure_does_not_invalidate_source_identity(hass, upstream, issue, reason):
    entry = await configure(hass, upstream)
    registry = er.async_get(hass)
    voice = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "event"
    )
    target = registry.async_get_or_create(
        "media_player",
        "alexa_devices",
        "speaker-a-media",
        config_entry=upstream.config_entry,
        device_id=voice.device_id,
    )
    hass.states.async_set(target.entity_id, "idle", {"supported_features": 4096})
    if issue == "disabled":
        registry.async_update_entity(target.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    elif issue == "unavailable":
        hass.states.async_set(target.entity_id, "unavailable")
    elif issue == "unsupported":
        hass.states.async_set(target.entity_id, "idle", {"supported_features": 0})
    else:
        registry.async_remove(target.entity_id)
    result = await hass.services.async_call(
        "alexa_voice_events",
        "resolve_targets",
        {"source_entity_id": voice.entity_id},
        blocking=True,
        return_response=True,
    )
    assert result["source_valid"] is True
    assert result["stop"] == {"entity_id": None, "reason": reason}


async def test_equal_identifiers_in_other_account_never_reuse_official_roles(
    hass, upstream, upstream_factory
):
    first = await configure(hass, upstream)
    registry = er.async_get(hass)
    voice_a = next(
        e
        for e in er.async_entries_for_config_entry(registry, first.entry_id)
        if e.domain == "event"
    )
    target = registry.async_get_or_create(
        "notify",
        "alexa_devices",
        "speaker-a-speak",
        config_entry=upstream.config_entry,
        device_id=voice_a.device_id,
    )
    hass.states.async_set(target.entity_id, "unknown")
    other = upstream_factory("another-account")
    second = await configure(hass, other)
    voice_b = next(
        e
        for e in er.async_entries_for_config_entry(registry, second.entry_id)
        if e.domain == "event"
    )
    result = await hass.services.async_call(
        "alexa_voice_events",
        "resolve_targets",
        {"source_entity_id": voice_b.entity_id},
        blocking=True,
        return_response=True,
    )
    assert result["source_valid"] is True
    assert result["source_device_id"] != voice_a.device_id
    assert result["speak"] == {"entity_id": None, "reason": "entity_not_found"}


async def test_multiple_official_serials_in_explicit_device_fail_closed(hass, upstream):
    entry = await configure(hass, upstream)
    registry = er.async_get(hass)
    voice = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "event"
    )
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=upstream.config_entry.entry_id,
        identifiers={("alexa_devices", "ambiguous-b"), ("alexa_devices", "ambiguous-c")},
    )
    result = await hass.services.async_call(
        "alexa_voice_events",
        "resolve_targets",
        {"source_entity_id": voice.entity_id, "reply_device_id": device.id},
        blocking=True,
        return_response=True,
    )
    assert result["source_valid"] is True
    assert result["speak"] == {"entity_id": None, "reason": "ambiguous_account"}


async def test_explicit_speaker_group_is_not_a_single_reply_target(hass, upstream):
    entry = await configure(hass, upstream)
    registry = er.async_get(hass)
    voice = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "event"
    )
    group = copy(upstream.data["speaker-a"])
    group.device_family = "WHA"
    group.serial_number = "speaker-group"
    upstream.async_set_updated_data({**upstream.data, "speaker-group": group})
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=upstream.config_entry.entry_id,
        identifiers={("alexa_devices", "speaker-group")},
    )
    target = registry.async_get_or_create(
        "notify",
        "alexa_devices",
        "speaker-group-announce",
        config_entry=upstream.config_entry,
        device_id=device.id,
    )
    hass.states.async_set(target.entity_id, "unknown")
    result = await hass.services.async_call(
        "alexa_voice_events",
        "resolve_targets",
        {"source_entity_id": voice.entity_id, "reply_device_id": device.id},
        blocking=True,
        return_response=True,
    )
    assert result["announce"] == {"entity_id": None, "reason": "unsupported_capability"}
