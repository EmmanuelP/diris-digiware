# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

"""Data update coordinator for DIRIS Digiware."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    ACTIVE_ENERGY_OID,
    ACTIVE_ENERGY_RESIDUAL_OID,
    ACTIVE_POWER_OID,
    CIRCUIT_NAME_OID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .snmp import SnmpClient, SnmpCommunicationError

_LOGGER = logging.getLogger(__name__)
type CircuitKey = tuple[int, int]


@dataclass(frozen=True)
class CircuitReading:
    """Measurements associated with a named circuit."""

    name: str
    active_energy_kwh: float | None
    active_power_w: int | None


class DirisDigiwareCoordinator(
    DataUpdateCoordinator[dict[CircuitKey, CircuitReading]]
):
    """Fetch circuit names and active metering data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        scan_interval = max(
            MIN_SCAN_INTERVAL,
            entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        super().__init__(
            hass,
            _LOGGER,
            name="Socomec DIRIS Digiware",
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self._entry = entry
        self._last_energy: dict[CircuitKey, float] = {}

    async def _async_update_data(self) -> dict[CircuitKey, CircuitReading]:
        """Read all documented tables and combine rows by their table indexes."""
        try:
            async with SnmpClient(
                self._entry.data["host"],
                self._entry.data["port"],
                self._entry.data["username"],
                self._entry.data["auth_key"],
                self._entry.data["priv_key"],
            ) as client:
                names = await client.walk(CIRCUIT_NAME_OID)
                energy = await client.walk(ACTIVE_ENERGY_OID)
                residual = await client.walk(ACTIVE_ENERGY_RESIDUAL_OID)
                power = await client.walk(ACTIVE_POWER_OID)
        except SnmpCommunicationError as err:
            raise UpdateFailed(
                f"Unable to poll the DIRIS Digiware device: {err}"
            ) from err

        name_by_key = {
            (index[0], index[1]): str(name)
            for index, name in names.items()
            if len(index) == 2 and isinstance(name, str) and name.strip()
        }
        energy_by_key = {
            index: value
            for index, value in energy.items()
            if len(index) == 2 and isinstance(value, int)
        }
        residual_by_key = {
            index: value
            for index, value in residual.items()
            if len(index) == 2 and isinstance(value, int)
        }
        power_by_key = {
            index: value
            for index, value in power.items()
            if len(index) == 2 and isinstance(value, int)
        }

        readings: dict[CircuitKey, CircuitReading] = {}
        for key, name in name_by_key.items():
            energy_kwh = None
            if key in energy_by_key:
                energy_kwh = energy_from_counters(
                    energy_by_key[key], residual_by_key.get(key)
                )
                energy_kwh = max(energy_kwh, self._last_energy.get(key, energy_kwh))
                self._last_energy[key] = energy_kwh
            readings[key] = CircuitReading(name, energy_kwh, power_by_key.get(key))
        return readings


def energy_from_counters(whole_kwh: int, residual_dwh: int | None) -> float:
    """Convert kWh and the documented 1/10 Wh residual into kWh."""
    return whole_kwh if residual_dwh is None else whole_kwh + residual_dwh / 10_000
