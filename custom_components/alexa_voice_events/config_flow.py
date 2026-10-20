"""Account-scoped speaker selection and explicit reception choices."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import probatio
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import DOMAIN, UPSTREAM_DOMAIN
from .profiles import METHODS, PROFILES, SpeakerConfig, validate_selection


class SpeakerSteps:
    """The same speaker/method editor in setup and options flows."""

    hass: HomeAssistant
    account_id: str
    current: dict[str, SpeakerConfig]
    selected: dict[str, SpeakerConfig]
    remaining: list[str]

    if TYPE_CHECKING:
        async_show_form: Callable[..., ConfigFlowResult]
        async_abort: Callable[..., ConfigFlowResult]

    def finish(self) -> ConfigFlowResult:
        raise NotImplementedError

    def account(self) -> ConfigEntry | None:
        entry = self.hass.config_entries.async_get_entry(self.account_id)
        if entry and entry.domain == UPSTREAM_DOMAIN and entry.state is ConfigEntryState.LOADED:
            return entry
        return None

    async def async_step_speaker(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        account = self.account()
        if account is None:
            return self.async_abort(reason="account_not_loaded")
        choices = []
        for serial, device in account.runtime_data.data.items():
            if device.voice_control_supported:
                profile = PROFILES.get(device.device_type)
                label = f"{device.account_name} ({profile.name if profile else 'Unverified'})"
                choices.append(selector.SelectOptionDict(value=serial, label=label))
        if not choices:
            return self.async_abort(reason="no_supported_speakers")
        errors = {}
        if user_input is not None:
            serials = user_input.get("speakers", [])
            valid = {c["value"] for c in choices}
            if serials and all(s in valid for s in serials):
                self.selected = {}
                self.remaining = list(dict.fromkeys(serials))
                return await self.async_step_method()
            errors["base"] = "invalid_speaker"
        return self.async_show_form(
            step_id="speaker",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        "speakers", default=list(self.current)
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=choices, multiple=True)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_method(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        account = self.account()
        if account is None:
            return self.async_abort(reason="account_not_loaded")
        serial = self.remaining[0]
        device = account.runtime_data.data.get(serial)
        if device is None or not device.voice_control_supported:
            return self.async_abort(reason="invalid_speaker")
        profile = PROFILES.get(device.device_type)
        current: dict[str, Any] = dict(self.current.get(serial, {}))
        errors = {}
        if user_input is not None:
            candidate = {
                "method": user_input.get("method"),
                "allow_unverified": user_input.get("allow_unverified", False),
            }
            if validate_selection(account.runtime_data.data, {serial: candidate}):
                self.selected[serial] = cast(SpeakerConfig, candidate)
                self.remaining.pop(0)
                if self.remaining:
                    return await self.async_step_method()
                if not validate_selection(account.runtime_data.data, self.selected):
                    return self.async_abort(reason="invalid_speaker")
                return self.finish()
            errors["base"] = "invalid_method"
        return self.async_show_form(
            step_id="method",
            description_placeholders={
                "speaker": device.account_name,
                "profile": profile.name if profile else "Unverified speaker",
                "evidence": profile.evidence if profile else "unverified",
            },
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        "method",
                        default=current.get("method", profile.method if profile else "native"),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=list(METHODS))
                    ),
                    probatio.Required(
                        "allow_unverified", default=current.get("allow_unverified", False)
                    ): bool,
                }
            ),
            errors=errors,
        )


class VoiceConfigFlow(SpeakerSteps, ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return VoiceOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        accounts = {
            e.entry_id: e.title for e in self.hass.config_entries.async_entries(UPSTREAM_DOMAIN)
        }
        if not accounts:
            return self.async_abort(reason="alexa_required")
        errors = {}
        if user_input is not None:
            self.account_id = user_input.get("alexa_entry_id", "")
            if self.account() is not None:
                await self.async_set_unique_id(self.account_id)
                self._abort_if_unique_id_configured()
                self.current = {}
                return await self.async_step_speaker()
            errors["base"] = (
                "account_not_loaded" if self.account_id in accounts else "invalid_account"
            )
        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required("alexa_entry_id"): probatio.In(accounts),
                }
            ),
            errors=errors,
        )

    def finish(self) -> ConfigFlowResult:
        account = self.account()
        if account is None:
            return self.async_abort(reason="account_not_loaded")
        return self.async_create_entry(
            title="Alexa Voice Events",
            data={
                "alexa_entry_id": self.account_id,
                "devices": {
                    serial: {
                        "device_type": account.runtime_data.data[serial].device_type,
                        "name": account.runtime_data.data[serial].account_name,
                    }
                    for serial in self.selected
                },
            },
            options={"speakers": self.selected},
        )


class VoiceOptionsFlow(SpeakerSteps, OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        self.account_id = self.config_entry.data["alexa_entry_id"]
        self.current = dict(self.config_entry.options["speakers"])
        return await self.async_step_speaker(user_input)

    def finish(self) -> ConfigFlowResult:
        return self.async_create_entry(title="", data={"speakers": self.selected})
