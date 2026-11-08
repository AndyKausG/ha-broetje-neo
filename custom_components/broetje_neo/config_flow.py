"""Config flow for the Brötje NEO integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
import voluptuous as vol

from .const import (
    CONF_MODEL,
    CONF_PV_MAX_POWER,
    CONF_PV_WATCHDOG,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_PV_MAX_POWER,
    DEFAULT_PV_WATCHDOG,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MODBUS_TIMEOUT,
)
from .registers import T_OUTDOOR

_LOGGER = logging.getLogger(__name__)

_INT_BOX = selector.NumberSelectorMode.BOX


def _num(vmin: int, vmax: int, step: int = 1) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=vmin, max=vmax, step=step, mode=_INT_BOX)
    )


async def async_test_connection(host: str, port: int, unit: int) -> None:
    """Read the outdoor temperature register once."""
    client = AsyncModbusTcpClient(host, port=port, timeout=MODBUS_TIMEOUT, retries=1)
    try:
        await client.connect()
        if not client.connected:
            raise ConnectionError("not connected")
        result = await client.read_input_registers(T_OUTDOOR.address, count=1, device_id=unit)
        if result.isError():
            raise ModbusException(str(result))
    finally:
        client.close()


class BroetjeNeoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_PORT] = int(user_input[CONF_PORT])
            user_input[CONF_UNIT_ID] = int(user_input[CONF_UNIT_ID])
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_UNIT_ID]}"
            )
            self._abort_if_unique_id_configured()
            try:
                await async_test_connection(
                    user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_UNIT_ID]
                )
            except (ConnectionError, ModbusException, OSError, TimeoutError) as err:
                _LOGGER.debug("Connection test failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): _num(1, 65535),
                vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): _num(1, 247),
                vol.Optional(CONF_MODEL, default=DEFAULT_MODEL): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return BroetjeNeoOptionsFlow()


class BroetjeNeoOptionsFlow(OptionsFlow):
    """Options: polling interval and PV safety settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data={k: int(v) for k, v in user_input.items()})
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): _num(MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL),
                vol.Required(
                    CONF_PV_WATCHDOG,
                    default=opts.get(CONF_PV_WATCHDOG, DEFAULT_PV_WATCHDOG),
                ): _num(0, 3600),
                vol.Required(
                    CONF_PV_MAX_POWER,
                    default=opts.get(CONF_PV_MAX_POWER, DEFAULT_PV_MAX_POWER),
                ): _num(500, 20000, 50),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
