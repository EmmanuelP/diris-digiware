# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

"""Data update coordinator for DIRIS Digiware."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    ACTIVE_ENERGY_NEG_OID,
    ACTIVE_ENERGY_NEG_RESIDUAL_OID,
    ACTIVE_ENERGY_OID,
    ACTIVE_ENERGY_RESIDUAL_OID,
    ACTIVE_POWER_OID,
    APPARENT_ENERGY_OID,
    APPARENT_ENERGY_RESIDUAL_OID,
    APPARENT_POWER_OID,
    CIRCUIT_NAME_OID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REACTIVE_ENERGY_NEG_OID,
    REACTIVE_ENERGY_NEG_RESIDUAL_OID,
    REACTIVE_ENERGY_OID,
    REACTIVE_ENERGY_RESIDUAL_OID,
    REACTIVE_POWER_OID,
)
from .snmp import SnmpClient, SnmpCommunicationError

_LOGGER = logging.getLogger(__name__)
POLL_TIMEOUT = 20
type CircuitKey = tuple[int, int]


@dataclass(frozen=True)
class Measurement:
    """A per-circuit SNMP column, optionally refined by a 1/10 unit residual."""

    key: str
    oid: str
    residual_oid: str | None = None
    enabled_by_default: bool = False


MEASUREMENTS: tuple[Measurement, ...] = (
    Measurement("active_energy", ACTIVE_ENERGY_OID, ACTIVE_ENERGY_RESIDUAL_OID, True),
    Measurement(
        "active_energy_production",
        ACTIVE_ENERGY_NEG_OID,
        ACTIVE_ENERGY_NEG_RESIDUAL_OID,
    ),
    Measurement("reactive_energy", REACTIVE_ENERGY_OID, REACTIVE_ENERGY_RESIDUAL_OID),
    Measurement(
        "reactive_energy_production",
        REACTIVE_ENERGY_NEG_OID,
        REACTIVE_ENERGY_NEG_RESIDUAL_OID,
    ),
    Measurement("apparent_energy", APPARENT_ENERGY_OID, APPARENT_ENERGY_RESIDUAL_OID),
    Measurement("active_power", ACTIVE_POWER_OID, enabled_by_default=True),
    Measurement("reactive_power", REACTIVE_POWER_OID),
    Measurement("apparent_power", APPARENT_POWER_OID),
)


@dataclass(frozen=True)
class CircuitReading:
    """Measurements associated with a named circuit, keyed by measurement key."""

    name: str
    values: dict[str, float | int]


def measurement_from_unique_id(unique_id: str) -> Measurement | None:
    """Return the measurement encoded at the end of a sensor unique ID."""
    for measurement in MEASUREMENTS:
        if unique_id.endswith(f"_{measurement.key}"):
            return measurement
    return None


class DirisDigiwareCoordinator(
    DataUpdateCoordinator[dict[CircuitKey, CircuitReading]]
):
    """Fetch circuit names and the metering data of enabled sensors."""

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
        self._last_energy: dict[tuple[str, CircuitKey], float] = {}

    def requested_measurements(self) -> list[Measurement]:
        """Return measurements with an enabled sensor or a default-enabled new one."""
        registry = er.async_get(self.hass)
        registered: set[str] = set()
        enabled: set[str] = set()
        for entity in er.async_entries_for_config_entry(
            registry, self._entry.entry_id
        ):
            measurement = measurement_from_unique_id(entity.unique_id)
            if measurement is None:
                continue
            registered.add(measurement.key)
            if not entity.disabled:
                enabled.add(measurement.key)
        return [
            measurement
            for measurement in MEASUREMENTS
            if measurement.key in enabled
            or (measurement.enabled_by_default and measurement.key not in registered)
        ]

    async def _async_update_data(self) -> dict[CircuitKey, CircuitReading]:
        """Read names and requested columns, then join rows by table indexes."""
        measurements = self.requested_measurements()
        columns: dict[str, dict[tuple[int, ...], object]] = {}
        try:
            async with asyncio.timeout(POLL_TIMEOUT):
                async with SnmpClient(
                    self._entry.data["host"],
                    self._entry.data["port"],
                    self._entry.data["username"],
                    self._entry.data["auth_key"],
                    self._entry.data["priv_key"],
                ) as client:
                    names = await client.walk(CIRCUIT_NAME_OID)
                    for measurement in measurements:
                        columns[measurement.oid] = await client.walk(measurement.oid)
                        if measurement.residual_oid is not None:
                            columns[measurement.residual_oid] = await client.walk(
                                measurement.residual_oid
                            )
        except (SnmpCommunicationError, TimeoutError) as err:
            raise UpdateFailed(
                f"Unable to poll the DIRIS Digiware device: {err}"
            ) from err

        name_by_key = {
            (index[0], index[1]): str(name)
            for index, name in names.items()
            if len(index) == 2 and isinstance(name, str) and name.strip()
        }
        integers = {
            oid: {
                index: value
                for index, value in values.items()
                if len(index) == 2 and isinstance(value, int)
            }
            for oid, values in columns.items()
        }

        readings: dict[CircuitKey, CircuitReading] = {}
        for key, name in name_by_key.items():
            values: dict[str, float | int] = {}
            for measurement in measurements:
                value = integers[measurement.oid].get(key)
                if value is None:
                    continue
                if measurement.residual_oid is not None:
                    last_key = (measurement.key, key)
                    value = energy_from_counters(
                        value, integers[measurement.residual_oid].get(key)
                    )
                    value = max(value, self._last_energy.get(last_key, value))
                    self._last_energy[last_key] = value
                values[measurement.key] = value
            readings[key] = CircuitReading(name, values)
        return readings


def energy_from_counters(whole: int, residual: int | None) -> float:
    """Combine a whole-kilo-unit counter with its documented 1/10 unit residual."""
    return whole if residual is None else whole + residual / 10_000
