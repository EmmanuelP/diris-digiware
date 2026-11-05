# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

"""Tests for circuit device grouping and existing entity registration."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.diris_digiware.const import (
    ACTIVE_ENERGY_OID,
    ACTIVE_ENERGY_RESIDUAL_OID,
    ACTIVE_POWER_OID,
    CIRCUIT_NAME_OID,
    DOMAIN,
)
from custom_components.diris_digiware.snmp import SnmpCommunicationError


@pytest.mark.parametrize("initial_circuits", [{}, {(3, 1): "Main"}])
async def test_discovers_circuits_during_polling(
    hass, enable_custom_integrations, monkeypatch, initial_circuits
):
    """Discover circuits even from an empty setup, without duplicates or leaks."""
    responses = {
        CIRCUIT_NAME_OID: dict(initial_circuits),
        ACTIVE_ENERGY_OID: {(3, 1): 12, (3, 2): 15},
        ACTIVE_ENERGY_RESIDUAL_OID: {},
        ACTIVE_POWER_OID: {(3, 1): 100, (3, 2): 200},
    }
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.walk.side_effect = lambda oid: responses[oid]
    monkeypatch.setattr(
        "custom_components.diris_digiware.coordinator.SnmpClient", lambda *_: client
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "meter.local",
            "port": 161,
            "username": "user",
            "auth_key": "auth-secret",
            "priv_key": "priv-secret",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    registry = er.async_get(hass)
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == (
        8 * len(initial_circuits)
    )

    responses[CIRCUIT_NAME_OID] = {(3, 1): "Main", (3, 2): "Main"}
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    registered = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(registered) == 16
    assert len({entity.device_id for entity in registered}) == 2
    original_ids = {entity.entity_id for entity in registered}
    for key, power in ((1, "100"), (2, "200")):
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_main_3_{key}_active_power"
        )
        assert hass.states.get(entity_id).state == power

    client.walk.side_effect = SnmpCommunicationError("offline")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert all(
        hass.states.get(entity.entity_id).state == "unavailable"
        for entity in registered
        if not entity.disabled
    )
    client.walk.side_effect = lambda oid: responses[oid]
    responses[CIRCUIT_NAME_OID] = {}
    await coordinator.async_refresh()
    responses[CIRCUIT_NAME_OID] = {(3, 1): "Main", (3, 2): "Main"}
    responses[ACTIVE_POWER_OID][(3, 2)] = 300
    for _ in range(2):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    } == original_ids
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_main_3_2_active_power"
    )
    assert hass.states.get(entity_id).state == "300"

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert not coordinator._listeners
    assert {
        entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
    } == original_ids
    reloaded = hass.data[DOMAIN][entry.entry_id]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not reloaded._listeners


@pytest.mark.parametrize("existing_entities", [False, True])
async def test_circuit_devices(
    hass, enable_custom_integrations, monkeypatch, existing_entities
):
    """Pair measurements per circuit without merging names or replacing entities."""
    names = {(3, 1): "Main", (3, 2): "Main", (4, 1): "Main"}
    responses = {
        CIRCUIT_NAME_OID: names,
        ACTIVE_ENERGY_OID: dict.fromkeys(names, 12),
        ACTIVE_ENERGY_RESIDUAL_OID: dict.fromkeys(names, 2500),
        ACTIVE_POWER_OID: dict.fromkeys(names, 1800),
    }
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.walk.side_effect = lambda oid: responses[oid]
    monkeypatch.setattr(
        "custom_components.diris_digiware.coordinator.SnmpClient", lambda *_: client
    )
    devices = dr.async_get(hass)
    entities = er.async_get(hass)
    entries = []
    original_entity_ids = {}
    for host in ("first.local", "second.local"):
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=f"{host}:161",
            data={
                "host": host,
                "port": 161,
                "username": "diris-user",
                "auth_key": "auth-secret",
                "priv_key": "priv-secret",
            },
        )
        entry.add_to_hass(hass)
        entries.append(entry)
        if existing_entities:
            gateway = devices.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, entry.entry_id)},
                name=f"DIRIS Digiware ({host})",
            )
            for key in names:
                for measurement in ("active_energy", "active_power"):
                    unique_id = f"{entry.entry_id}_main_{key[0]}_{key[1]}_{measurement}"
                    entity = entities.async_get_or_create(
                        "sensor",
                        DOMAIN,
                        unique_id,
                        suggested_object_id=f"custom_{host}_{key}_{measurement}",
                        config_entry=entry,
                        device_id=gateway.id,
                    )
                    original_entity_ids[unique_id] = entity.entity_id
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    circuit_device_ids = set()
    for entry in entries:
        registered = er.async_entries_for_config_entry(entities, entry.entry_id)
        assert len(registered) == 24
        for key in names:
            device = devices.async_get_device_by_identifier(
                (DOMAIN, f"{entry.entry_id}_{key[0]}_{key[1]}"), entry.entry_id
            )
            assert device is not None
            assert device.name == "Main"
            circuit_device_ids.add(device.id)
            for measurement, state in (
                ("active_energy", "12.25"),
                ("active_power", "1800"),
            ):
                unique_id = f"{entry.entry_id}_main_{key[0]}_{key[1]}_{measurement}"
                entity_id = entities.async_get_entity_id("sensor", DOMAIN, unique_id)
                entity = entities.async_get(entity_id)
                assert entity.device_id == device.id
                assert hass.states.get(entity_id).state == state
                if existing_entities:
                    assert entity_id == original_entity_ids[unique_id]
        assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(circuit_device_ids) == 6
    responses[ACTIVE_ENERGY_OID] = dict.fromkeys(names, 13)
    responses[ACTIVE_POWER_OID] = dict.fromkeys(names, 2400)
    calls_before = client.walk.await_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert client.walk.await_count == calls_before + 8
    for entry in entries:
        for key in names:
            for measurement, state in (
                ("active_energy", "13.25"),
                ("active_power", "2400"),
            ):
                unique_id = f"{entry.entry_id}_main_{key[0]}_{key[1]}_{measurement}"
                entity_id = entities.async_get_entity_id("sensor", DOMAIN, unique_id)
                assert hass.states.get(entity_id).state == state
        assert len(er.async_entries_for_config_entry(entities, entry.entry_id)) == 24
        for key in names:
            device = devices.async_get_device_by_identifier(
                (DOMAIN, f"{entry.entry_id}_{key[0]}_{key[1]}"), entry.entry_id
            )
            assert device.id in circuit_device_ids
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_optional_measurements_are_polled_only_when_enabled(
    hass, enable_custom_integrations, monkeypatch
):
    """Register optional sensors disabled and skip their columns until enabled."""
    from custom_components.diris_digiware.const import (
        ACTIVE_ENERGY_NEG_OID,
        ACTIVE_ENERGY_NEG_RESIDUAL_OID,
        REACTIVE_POWER_OID,
    )

    responses = {
        CIRCUIT_NAME_OID: {(3, 1): "Main"},
        ACTIVE_ENERGY_OID: {(3, 1): 12},
        ACTIVE_ENERGY_RESIDUAL_OID: {(3, 1): 0},
        ACTIVE_POWER_OID: {(3, 1): 100},
        ACTIVE_ENERGY_NEG_OID: {(3, 1): 7},
        ACTIVE_ENERGY_NEG_RESIDUAL_OID: {(3, 1): 5000},
        REACTIVE_POWER_OID: {(3, 1): -650},
    }
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.walk.side_effect = lambda oid: responses[oid]
    monkeypatch.setattr(
        "custom_components.diris_digiware.coordinator.SnmpClient", lambda *_: client
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "meter.local",
            "port": 161,
            "username": "user",
            "auth_key": "auth-secret",
            "priv_key": "priv-secret",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    enabled = {
        entity.unique_id.removeprefix(f"{entry.entry_id}_main_3_1_")
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
        if not entity.disabled
    }
    assert enabled == {"active_energy", "active_power"}

    def walked() -> set[str]:
        return {call.args[0] for call in client.walk.await_args_list}

    client.walk.reset_mock()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert walked() == {
        CIRCUIT_NAME_OID,
        ACTIVE_ENERGY_OID,
        ACTIVE_ENERGY_RESIDUAL_OID,
        ACTIVE_POWER_OID,
    }

    for measurement in ("active_energy_production", "reactive_power"):
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_main_3_1_{measurement}"
        )
        registry.async_update_entity(entity_id, disabled_by=None)
    client.walk.reset_mock()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert walked() == {
        CIRCUIT_NAME_OID,
        ACTIVE_ENERGY_OID,
        ACTIVE_ENERGY_RESIDUAL_OID,
        ACTIVE_POWER_OID,
        ACTIVE_ENERGY_NEG_OID,
        ACTIVE_ENERGY_NEG_RESIDUAL_OID,
        REACTIVE_POWER_OID,
    }
    for measurement, state in (
        ("active_energy_production", "7.5"),
        ("reactive_power", "-650"),
    ):
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_main_3_1_{measurement}"
        )
        assert hass.states.get(entity_id).state == state

    assert await hass.config_entries.async_unload(entry.entry_id)
