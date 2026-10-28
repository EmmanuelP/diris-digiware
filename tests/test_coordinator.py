# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

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


def _entry() -> Mock:
    entry = Mock()
    entry.data = {
        "host": "meter.local",
        "port": 161,
        "username": "diris-user",
        "auth_key": "auth-secret",
        "priv_key": "priv-secret",
    }
    entry.options = {}
    return entry


def _patch_client(monkeypatch, walk) -> None:
    class MockSnmpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

    MockSnmpClient.walk = lambda self, oid: walk(oid)
    monkeypatch.setattr(
        "custom_components.diris_digiware.coordinator.SnmpClient",
        lambda *_: MockSnmpClient(),
    )


@pytest.mark.asyncio
async def test_poll_timeout_becomes_update_failed(hass, monkeypatch) -> None:
    """A hung device must not block the coordinator forever."""
    import asyncio

    from homeassistant.helpers.update_coordinator import UpdateFailed

    async def hang(_oid):
        await asyncio.sleep(10)

    monkeypatch.setattr(
        "custom_components.diris_digiware.coordinator.POLL_TIMEOUT", 0.01
    )
    _patch_client(monkeypatch, hang)

    with pytest.raises(UpdateFailed):
        await DirisDigiwareCoordinator(hass, _entry())._async_update_data()


@pytest.mark.asyncio
async def test_snmp_error_becomes_update_failed(hass, monkeypatch) -> None:
    """Communication errors are reported as UpdateFailed."""
    from homeassistant.helpers.update_coordinator import UpdateFailed

    from custom_components.diris_digiware.snmp import SnmpCommunicationError

    async def fail(_oid):
        raise SnmpCommunicationError("boom")

    _patch_client(monkeypatch, fail)

    with pytest.raises(UpdateFailed):
        await DirisDigiwareCoordinator(hass, _entry())._async_update_data()


@pytest.mark.asyncio
async def test_malformed_values_are_ignored(hass, monkeypatch) -> None:
    """Non-numeric, missing or wrongly indexed values do not raise."""
    responses = {
        CIRCUIT_NAME_OID: {(3, 1): "Main", (3, 2): "  ", (3,): "Bad", (4, 1): 7},
        ACTIVE_ENERGY_OID: {(3, 1): "noSuchInstance"},
        ACTIVE_ENERGY_RESIDUAL_OID: {(3, 1): "x"},
        ACTIVE_POWER_OID: {(3, 1): "noSuchInstance"},
    }

    async def walk(oid):
        return responses[oid]

    _patch_client(monkeypatch, walk)

    readings = await DirisDigiwareCoordinator(hass, _entry())._async_update_data()

    assert list(readings) == [(3, 1)]
    assert readings[(3, 1)].active_energy_kwh is None
    assert readings[(3, 1)].active_power_w is None


@pytest.mark.asyncio
async def test_setup_retries_when_device_unreachable_then_unloads(
    hass, enable_custom_integrations, monkeypatch
) -> None:
    """An unreachable device gives setup_retry; a working one loads and unloads."""
    from homeassistant.config_entries import ConfigEntryState
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.diris_digiware.const import DOMAIN
    from custom_components.diris_digiware.snmp import SnmpCommunicationError

    state = {"fail": True}
    responses = {
        CIRCUIT_NAME_OID: {(3, 1): "Main"},
        ACTIVE_ENERGY_OID: {(3, 1): 1},
        ACTIVE_ENERGY_RESIDUAL_OID: {(3, 1): 0},
        ACTIVE_POWER_OID: {(3, 1): 5},
    }

    async def walk(oid):
        if state["fail"]:
            raise SnmpCommunicationError("down")
        return responses[oid]

    _patch_client(monkeypatch, walk)
    entry = MockConfigEntry(domain=DOMAIN, data=_entry().data, unique_id="meter:161")
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY

    state["fail"] = False
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
