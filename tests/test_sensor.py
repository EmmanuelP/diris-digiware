# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

"""Tests for circuit device grouping and existing entity registration."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.diris_digiware.const import (
    ACTIVE_ENERGY_OID,
    ACTIVE_ENERGY_RESIDUAL_OID,
    ACTIVE_POWER_OID,
    CIRCUIT_NAME_OID,
    DOMAIN,
)


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
        assert len(registered) == 6
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
    for entry in entries:
        assert len(er.async_entries_for_config_entry(entities, entry.entry_id)) == 6
        for key in names:
            device = devices.async_get_device_by_identifier(
                (DOMAIN, f"{entry.entry_id}_{key[0]}_{key[1]}"), entry.entry_id
            )
            assert device.id in circuit_device_ids
        assert await hass.config_entries.async_unload(entry.entry_id)
