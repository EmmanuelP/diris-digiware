# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

"""Sensors for Socomec DIRIS Digiware."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfApparentPower,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfReactiveEnergy,
    UnitOfReactivePower,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import (
    MEASUREMENTS,
    CircuitKey,
    CircuitReading,
    DirisDigiwareCoordinator,
)

_ENABLED_BY_DEFAULT = {m.key: m.enabled_by_default for m in MEASUREMENTS}


def _energy(
    key: str, name: str, device_class: SensorDeviceClass | None, unit: str
) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        name=name,
        device_class=device_class,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=unit,
        suggested_display_precision=4,
        entity_registry_enabled_default=_ENABLED_BY_DEFAULT[key],
    )


def _power(
    key: str, name: str, device_class: SensorDeviceClass | None, unit: str
) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        name=name,
        device_class=device_class,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=unit,
        entity_registry_enabled_default=_ENABLED_BY_DEFAULT[key],
    )


SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    _energy(
        "active_energy",
        "Active energy",
        SensorDeviceClass.ENERGY,
        UnitOfEnergy.KILO_WATT_HOUR,
    ),
    _energy(
        "active_energy_production",
        "Active energy production",
        SensorDeviceClass.ENERGY,
        UnitOfEnergy.KILO_WATT_HOUR,
    ),
    _energy(
        "reactive_energy",
        "Reactive energy",
        SensorDeviceClass.REACTIVE_ENERGY,
        UnitOfReactiveEnergy.KILO_VOLT_AMPERE_REACTIVE_HOUR,
    ),
    _energy(
        "reactive_energy_production",
        "Reactive energy production",
        SensorDeviceClass.REACTIVE_ENERGY,
        UnitOfReactiveEnergy.KILO_VOLT_AMPERE_REACTIVE_HOUR,
    ),
    # Home Assistant has no apparent energy device class.
    _energy("apparent_energy", "Apparent energy", None, "kVAh"),
    _power(
        "active_power", "Active power", SensorDeviceClass.POWER, UnitOfPower.WATT
    ),
    _power(
        "reactive_power",
        "Reactive power",
        SensorDeviceClass.REACTIVE_POWER,
        UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
    ),
    _power(
        "apparent_power",
        "Apparent power",
        SensorDeviceClass.APPARENT_POWER,
        UnitOfApparentPower.VOLT_AMPERE,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors and discover additional circuits after each update."""
    coordinator: DirisDigiwareCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_circuits: set[CircuitKey] = set()

    @callback
    def async_discover_circuits() -> None:
        if not coordinator.last_update_success:
            return
        entities: list[DirisDigiwareSensor] = []
        for key, reading in coordinator.data.items():
            if key in known_circuits:
                continue
            known_circuits.add(key)
            device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry.entry_id}_{key[0]}_{key[1]}")},
                name=reading.name,
                manufacturer="Socomec",
                model="DIRIS Digiware",
            )
            entities.extend(
                DirisDigiwareSensor(
                    coordinator, entry, key, reading, description, device_info
                )
                for description in SENSOR_DESCRIPTIONS
            )
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(async_discover_circuits))
    async_discover_circuits()


class DirisDigiwareSensor(
    CoordinatorEntity[DirisDigiwareCoordinator], SensorEntity
):
    """A circuit energy or power sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: DirisDigiwareCoordinator,
        entry: ConfigEntry,
        key: CircuitKey,
        reading: CircuitReading,
        description: SensorEntityDescription,
        device_info: DeviceInfo,
    ) -> None:
        """Initialize the circuit sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._circuit_key = key
        self._circuit_name = reading.name
        self._device_info = device_info
        self._entry_id = entry.entry_id
        self._attr_name = f"{reading.name} {description.name}"
        self._attr_unique_id = (
            f"{self._entry_id}_{slugify(reading.name)}_{key[0]}_{key[1]}_"
            f"{description.key}"
        )
        self._attr_has_entity_name = False

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device shared by this circuit's sensors."""
        return self._device_info

    @property
    def native_value(self) -> float | int | None:
        """Return the latest reading for this circuit."""
        reading = self.coordinator.data.get(self._circuit_key)
        if reading is None:
            return None
        return reading.values.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Keep entities available when one measurement is temporarily absent."""
        return self.coordinator.last_update_success
