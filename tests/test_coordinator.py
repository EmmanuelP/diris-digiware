"""Tests for DIRIS Digiware polling and energy precision."""

from unittest.mock import Mock

import pytest

from custom_components.diris_digiware.const import (
    ACTIVE_ENERGY_OID,
    ACTIVE_ENERGY_RESIDUAL_OID,
    ACTIVE_POWER_OID,
    CIRCUIT_NAME_OID,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from custom_components.diris_digiware.coordinator import (
    DirisDigiwareCoordinator,
    energy_from_counters,
)


def test_energy_from_counters_uses_tenth_watt_hour_resolution() -> None:
    """Convert the residual counter from 1/10 Wh to a kWh fraction."""
    assert energy_from_counters(12, 1234) == pytest.approx(12.1234)
    assert energy_from_counters(12, None) == 12


@pytest.mark.asyncio
async def test_coordinator_merges_documented_table_indexes(hass, monkeypatch) -> None:
    """Use circuit names to label energy and power rows."""
    responses = {
        CIRCUIT_NAME_OID: {(3, 1): "Main circuit"},
        ACTIVE_ENERGY_OID: {(3, 1): 125},
        ACTIVE_ENERGY_RESIDUAL_OID: {(3, 1): 2500},
        ACTIVE_POWER_OID: {(3, 1): 1800},
    }

    class MockSnmpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def walk(self, oid):
            return responses[oid]

    monkeypatch.setattr(
        "custom_components.diris_digiware.coordinator.SnmpClient",
        lambda *_: MockSnmpClient(),
    )
    entry = Mock()
    entry.data = {
        "host": "meter.local",
        "port": 161,
        "username": "diris-user",
        "auth_key": "auth-secret",
        "priv_key": "priv-secret",
    }
    entry.options = {}
    coordinator = DirisDigiwareCoordinator(hass, entry)

    readings = await coordinator._async_update_data()

    assert readings[(3, 1)].name == "Main circuit"
    assert readings[(3, 1)].active_energy_kwh == 125.25
    assert readings[(3, 1)].active_power_w == 1800


@pytest.mark.asyncio
async def test_energy_never_decreases_between_polls(hass, monkeypatch) -> None:
    """Ignore a stale residual reading that would lower the previous state."""
    responses = {
        CIRCUIT_NAME_OID: {(3, 1): "Main circuit"},
        ACTIVE_ENERGY_OID: {(3, 1): 125},
        ACTIVE_ENERGY_RESIDUAL_OID: {(3, 1): 500},
        ACTIVE_POWER_OID: {(3, 1): 1800},
    }

    class MockSnmpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def walk(self, oid):
            return responses[oid]

    monkeypatch.setattr(
        "custom_components.diris_digiware.coordinator.SnmpClient",
        lambda *_: MockSnmpClient(),
    )
    entry = Mock()
    entry.data = {
        "host": "meter.local",
        "port": 161,
        "username": "diris-user",
        "auth_key": "auth-secret",
        "priv_key": "priv-secret",
    }
    entry.options = {}
    coordinator = DirisDigiwareCoordinator(hass, entry)

    first = await coordinator._async_update_data()
    responses[ACTIVE_ENERGY_OID] = {(3, 1): 125}
    responses[ACTIVE_ENERGY_RESIDUAL_OID] = {(3, 1): 0}
    second = await coordinator._async_update_data()

    assert first[(3, 1)].active_energy_kwh == 125.05
    assert second[(3, 1)].active_energy_kwh == 125.05


@pytest.mark.parametrize(
    ("configured_interval", "expected_interval"),
    [
        (MIN_SCAN_INTERVAL - 1, MIN_SCAN_INTERVAL),
        (DEFAULT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        (90, 90),
    ],
)
def test_coordinator_polling_interval(hass, configured_interval, expected_interval):
    """Apply configured polling intervals with the 30-second minimum guard."""
    entry = Mock()
    entry.options = {CONF_SCAN_INTERVAL: configured_interval}

    coordinator = DirisDigiwareCoordinator(hass, entry)

    assert coordinator.update_interval.total_seconds() == expected_interval
