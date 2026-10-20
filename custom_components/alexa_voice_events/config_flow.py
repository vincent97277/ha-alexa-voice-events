"""Choose an existing account and speaker, with backend membership checks."""

from typing import Any

import probatio
from homeassistant.config_entries import ConfigEntryState, ConfigFlow, ConfigFlowResult

from .const import DOMAIN, UPSTREAM_DOMAIN
from .profiles import PROFILES


class VoiceConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        accounts = {
            e.entry_id: e.title for e in self.hass.config_entries.async_entries(UPSTREAM_DOMAIN)
        }
        if not accounts:
            return self.async_abort(reason="alexa_required")
        errors = {}
        if user_input is not None:
            account = self.hass.config_entries.async_get_entry(user_input.get("alexa_entry_id", ""))
            if account is not None and account.domain == UPSTREAM_DOMAIN:
                if account.state is not ConfigEntryState.LOADED:
                    errors["base"] = "account_not_loaded"
                else:
                    await self.async_set_unique_id(account.entry_id)
                    self._abort_if_unique_id_configured()
                    self.account_id = account.entry_id
                    return await self.async_step_speaker()
            else:
                errors["base"] = "invalid_account"
        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required("alexa_entry_id"): probatio.In(accounts),
                }
            ),
            errors=errors,
        )

    async def async_step_speaker(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        account = self.hass.config_entries.async_get_entry(self.account_id)
        if account is None or account.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="account_not_loaded")
        choices = {
            serial: f"{device.account_name} ({PROFILES[device.device_type].name})"
            for serial, device in account.runtime_data.data.items()
            if device.voice_control_supported and device.device_type in PROFILES
        }
        if not choices:
            return self.async_abort(reason="no_supported_speakers")
        errors = {}
        if user_input is not None:
            serial = user_input.get("speaker")
            if serial in choices:
                return self.async_create_entry(
                    title="Alexa Voice Events",
                    data={
                        "alexa_entry_id": self.account_id,
                        "speaker": serial,
                    },
                )
            errors["base"] = "invalid_speaker"
        return self.async_show_form(
            step_id="speaker",
            data_schema=probatio.Schema(
                {
                    probatio.Required("speaker"): probatio.In(choices),
                }
            ),
            errors=errors,
        )
