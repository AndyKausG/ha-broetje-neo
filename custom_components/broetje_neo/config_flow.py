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
    CONF_ALLOW_PRICE_LOCK,
    CONF_ALLOW_PV,
    CONF_ALLOW_WRITE,
    CONF_EXPECTED_SPF,
    CONF_GRID_SIGNAL,
    CONF_HEATING_CIRCUIT,
    CONF_HEATING_SYSTEM,
    CONF_MODEL,
    CONF_PRICE_LOCK_MAX,
    CONF_PRICE_LOCK_SWITCH,
    CONF_PV_MAX_POWER,
    CONF_PV_WATCHDOG,
    CONF_ROOM_GROUPING,
    CONF_ROOM_SENSORS,
    CONF_SCAN_INTERVAL,
    CONF_UNIT_ID,
    DEFAULT_ALLOW_PRICE_LOCK,
    DEFAULT_ALLOW_PV,
    DEFAULT_ALLOW_WRITE,
    DEFAULT_HEATING_CIRCUIT,
    DEFAULT_HEATING_SYSTEM,
    DEFAULT_MODEL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_PV_MAX_POWER,
    DEFAULT_PV_WATCHDOG,
    DEFAULT_ROOM_GROUPING,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    HEATING_CIRCUITS,
    HEATING_SYSTEMS,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MODBUS_TIMEOUT,
    ROOM_GROUPINGS,
)
from .registers import T_OUTDOOR
from .safety import PRICE_LOCK_MAX_MINUTES_DEFAULT, PRICE_LOCK_MAX_MINUTES_LIMIT

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
    """Options: write permissions, polling interval and PV safety settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            data = {
                k: (v if isinstance(v, (bool, str, list)) else int(v))
                for k, v in user_input.items()
            }
            data[CONF_EXPECTED_SPF] = float(user_input.get(CONF_EXPECTED_SPF, 0))
            return self.async_create_entry(data=data)
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_HEATING_SYSTEM,
                    default=opts.get(CONF_HEATING_SYSTEM, DEFAULT_HEATING_SYSTEM),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=HEATING_SYSTEMS,
                        translation_key="heating_system",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_HEATING_CIRCUIT,
                    default=opts.get(CONF_HEATING_CIRCUIT, DEFAULT_HEATING_CIRCUIT),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=HEATING_CIRCUITS,
                        translation_key="heating_circuit_option",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_ROOM_SENSORS,
                    default=opts.get(CONF_ROOM_SENSORS, []),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor", device_class="temperature", multiple=True
                    )
                ),
                vol.Required(
                    CONF_ROOM_GROUPING,
                    default=opts.get(CONF_ROOM_GROUPING, DEFAULT_ROOM_GROUPING),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=ROOM_GROUPINGS,
                        translation_key="room_grouping",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_EXPECTED_SPF,
                    default=opts.get(CONF_EXPECTED_SPF, 0),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=7, step=0.1, mode=selector.NumberSelectorMode.BOX
                    )
                ),
                vol.Optional(
                    CONF_GRID_SIGNAL,
                    description={"suggested_value": opts.get(CONF_GRID_SIGNAL)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor")),
                vol.Required(
                    CONF_ALLOW_WRITE,
                    default=opts.get(CONF_ALLOW_WRITE, DEFAULT_ALLOW_WRITE),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_ALLOW_PV,
                    default=opts.get(CONF_ALLOW_PV, DEFAULT_ALLOW_PV),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_ALLOW_PRICE_LOCK,
                    default=opts.get(CONF_ALLOW_PRICE_LOCK, DEFAULT_ALLOW_PRICE_LOCK),
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_PRICE_LOCK_MAX,
                    default=opts.get(CONF_PRICE_LOCK_MAX, PRICE_LOCK_MAX_MINUTES_DEFAULT),
                ): _num(30, PRICE_LOCK_MAX_MINUTES_LIMIT, 10),
                vol.Optional(
                    CONF_PRICE_LOCK_SWITCH,
                    description={"suggested_value": opts.get(CONF_PRICE_LOCK_SWITCH)},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="switch")),
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
