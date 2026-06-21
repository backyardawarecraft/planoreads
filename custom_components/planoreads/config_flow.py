"""Config flow for PlanoReads."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACCOUNT,
    CONF_HISTORY_DAYS,
    CONF_METER,
    CONF_ZIP,
    DEFAULT_HISTORY_DAYS,
    DOMAIN,
)
from .planoreads_client import PlanoReadsAuthError, PlanoReadsClient, PlanoReadsError

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCOUNT): str,
        vol.Required(CONF_ZIP): str,
        vol.Required(CONF_METER): str,
        vol.Optional(
            CONF_HISTORY_DAYS, default=DEFAULT_HISTORY_DAYS
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=90, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
    }
)


class PlanoReadsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the PlanoReads config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials and validate by attempting a fetch."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_ACCOUNT]}_{user_input[CONF_METER]}".lower()
            )
            self._abort_if_unique_id_configured()

            client = PlanoReadsClient(
                user_input[CONF_ACCOUNT],
                user_input[CONF_ZIP],
                user_input[CONF_METER],
                dt_util.DEFAULT_TIME_ZONE,
            )
            try:
                await client.async_fetch(int(user_input[CONF_HISTORY_DAYS]))
            except PlanoReadsAuthError:
                errors["base"] = "invalid_auth"
            except PlanoReadsError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"Plano Water ({user_input[CONF_METER]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )
