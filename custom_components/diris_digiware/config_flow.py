"""Config flow for the Socomec DIRIS Digiware integration."""

from __future__ import annotations

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CIRCUIT_NAME_OID,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .snmp import SnmpClient, SnmpCommunicationError

CONF_AUTH_KEY = "auth_key"
CONF_PRIV_KEY = "priv_key"


class DirisDigiwareConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a DIRIS Digiware device."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, str | int] | None = None
    ) -> FlowResult:
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            username = str(user_input[CONF_USERNAME]).strip()
            auth_key = str(user_input[CONF_AUTH_KEY])
            priv_key = str(user_input[CONF_PRIV_KEY])
            await self.async_set_unique_id(f"{host.lower()}:{port}")
            self._abort_if_unique_id_configured()

            try:
                async with SnmpClient(
                    host, port, username, auth_key, priv_key
                ) as client:
                    await client.walk(CIRCUIT_NAME_OID)
            except SnmpCommunicationError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"DIRIS Digiware ({host})",
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_USERNAME: username,
                        CONF_AUTH_KEY: auth_key,
                        CONF_PRIV_KEY: priv_key,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_AUTH_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(CONF_PRIV_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> DirisDigiwareOptionsFlow:
        """Create the options flow."""
        return DirisDigiwareOptionsFlow()


class DirisDigiwareOptionsFlow(config_entries.OptionsFlowWithReload):
    """Configure the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, int] | None = None
    ) -> FlowResult:
        """Configure the coordinator polling interval."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.options.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
