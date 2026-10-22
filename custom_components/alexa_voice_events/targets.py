"""Read-only official action targets, resolved by identity rather than names."""

from typing import Any

import probatio as vol
from aioamazondevices.const.devices import SPEAKER_GROUP_FAMILY
from homeassistant.components.alexa_devices.coordinator import AmazonDevicesCoordinator
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, UPSTREAM_DOMAIN
from .receiver import AccountReceiver, SpeakerReception

SERVICE = "resolve_targets"


def _target(entity_id: str | None = None, reason: str | None = None) -> dict[str, Any]:
    return {"entity_id": entity_id, "reason": reason}


def _roles(hass: HomeAssistant, device_id: str, account_id: str, serial: str) -> dict[str, Any]:
    registry = er.async_get(hass)
    entities = er.async_entries_for_device(registry, device_id, include_disabled_entities=True)
    result = {}
    for role, domain, key in (
        ("stop", "media_player", "media"),
        ("speak", "notify", "speak"),
        ("announce", "notify", "announce"),
    ):
        candidates = [
            e
            for e in entities
            if e.domain == domain
            and e.platform == UPSTREAM_DOMAIN
            and e.config_entry_id == account_id
            and e.unique_id == f"{serial}-{key}"
        ]
        if len(candidates) != 1:
            result[role] = _target(reason="ambiguous_entity" if candidates else "entity_not_found")
            continue
        entity = candidates[0]
        state = hass.states.get(entity.entity_id)
        if entity.disabled_by is not None:
            reason = "entity_disabled"
        elif state is None or state.state == "unavailable":
            reason = "entity_unavailable"
        elif (
            role == "stop"
            and not state.attributes.get("supported_features", 0) & MediaPlayerEntityFeature.STOP
        ):
            reason = "unsupported_capability"
        else:
            reason = None
        result[role] = _target(entity.entity_id if reason is None else None, reason)
    return result


def _source(hass: HomeAssistant, entity_id: str) -> tuple[AccountReceiver, SpeakerReception] | str:
    entity = er.async_get(hass).async_get(entity_id)
    if entity is None:
        return "source_not_found"
    entry = hass.config_entries.async_get_entry(entity.config_entry_id or "")
    if (
        entity.domain != "event"
        or entity.platform != DOMAIN
        or entry is None
        or entry.domain != DOMAIN
        or entry.state is not ConfigEntryState.LOADED
    ):
        return "source_not_configured"
    account = getattr(entry, "runtime_data", None)
    if not isinstance(account, AccountReceiver):
        return "source_not_configured"
    current = account.binding.current
    if (
        current is None
        or current is not account.coordinator
        or account.adapter is None
        or not account.adapter.matches(current)
    ):
        return "account_not_ready"
    speaker = next(
        (s for s in account.speakers.values() if s.unique_id("voice") == entity.unique_id), None
    )
    if speaker is None:
        return "source_not_configured"
    device = dr.async_get(hass).async_get_device_by_identifier(
        (UPSTREAM_DOMAIN, speaker.serial), entry.data["alexa_entry_id"]
    )
    if (
        device is None
        or device.id != entity.device_id
        or device.id != speaker.device_id
        or device.disabled_by is not None
        or entity.disabled_by is not None
    ):
        return "source_mismatch"
    if speaker.serial not in current.data or not current.data[speaker.serial].online:
        return "source_unavailable"
    return account, speaker


def resolve(
    hass: HomeAssistant, source_entity_id: str, reply_device_id: str | None
) -> dict[str, Any]:
    """Resolve metadata only; the caller must separately check event/session authority."""
    source = _source(hass, source_entity_id)
    response: dict[str, Any] = {
        "schema_version": 1,
        "source_valid": False,
        "source_reason": None,
        "source_device_id": None,
        "reply_device_id": None,
        **{role: _target(reason="source_not_configured") for role in ("stop", "speak", "announce")},
    }
    if isinstance(source, str):
        response["source_reason"] = source
        for role in ("stop", "speak", "announce"):
            response[role] = _target(reason=source)
        return response
    account, speaker = source
    account_id = account.entry.data["alexa_entry_id"]
    response.update(source_valid=True, source_device_id=speaker.device_id)
    response.update(_roles(hass, speaker.device_id, account_id, speaker.serial))
    response["reply_device_id"] = speaker.device_id if reply_device_id is None else reply_device_id
    if reply_device_id is None:
        return response
    device = dr.async_get(hass).async_get(reply_device_id)
    reason = None
    if device is None:
        reason = "device_not_found"
    elif device.disabled_by is not None:
        reason = "entity_disabled"
    else:
        official = hass.config_entries.async_get_entry(device.config_entry_id or "")
        serials = [
            identifier for domain, identifier in device.identifiers if domain == UPSTREAM_DOMAIN
        ]
        coordinator = getattr(official, "runtime_data", None)
        if official is None or official.domain != UPSTREAM_DOMAIN:
            reason = "account_not_ready"
        elif len(serials) != 1:
            reason = "ambiguous_account" if serials else "unsupported_capability"
        elif official.state is not ConfigEntryState.LOADED or not isinstance(
            coordinator, AmazonDevicesCoordinator
        ):
            reason = "account_not_ready"
        elif serials[0] not in coordinator.data or not coordinator.data[serials[0]].online:
            reason = "entity_unavailable"
        elif getattr(coordinator.data[serials[0]], "device_family", None) == SPEAKER_GROUP_FAMILY:
            reason = "unsupported_capability"
        else:
            roles = _roles(hass, device.id, official.entry_id, serials[0])
            response.update({role: roles[role] for role in ("speak", "announce")})
    if reason:
        for role in ("speak", "announce"):
            response[role] = _target(reason=reason)
    return response


def setup(hass: HomeAssistant) -> None:
    """Register once per HA component, independently of individual entry unloads."""

    async def handle(call: ServiceCall) -> dict[str, Any]:
        return resolve(hass, call.data["source_entity_id"], call.data.get("reply_device_id"))

    hass.services.async_register(
        DOMAIN,
        SERVICE,
        handle,
        schema=vol.Schema(
            {
                vol.Required("source_entity_id"): cv.entity_id,
                vol.Optional("reply_device_id"): cv.string,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
