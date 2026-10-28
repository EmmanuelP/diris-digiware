"""Sensors for Socomec DIRIS Digiware."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import CircuitKey, CircuitReading, DirisDigiwareCoordinator

ENERGY_DESCRIPTION = SensorEntityDescription(
    key="active_energy",
    name="Active energy",
    device_class=SensorDeviceClass.ENERGY,
    state_class=SensorStateClass.TOTAL_INCREASING,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    suggested_display_precision=4,
)
POWER_DESCRIPTION = SensorEntityDescription(
    key="active_power",
    name="Active power",
    device_class=SensorDeviceClass.POWER,
    state_class=SensorStateClass.MEASUREMENT,
    native_unit_of_measurement=UnitOfPower.WATT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from the initially discovered circuit table."""
    coordinator: DirisDigiwareCoordinator = hass.data[DOMAIN][entry.entry_id]
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"DIRIS Digiware ({entry.data['host']})",
        manufacturer="Socomec",
        model="DIRIS Digiware",
    )
    entities: list[DirisDigiwareSensor] = []
    for key, reading in coordinator.data.items():
        entities.extend(
            (
                DirisDigiwareSensor(
                    coordinator, entry, key, reading, ENERGY_DESCRIPTION, device_info
                ),
                DirisDigiwareSensor(
                    coordinator, entry, key, reading, POWER_DESCRIPTION, device_info
                ),
            )
        )
    async_add_entities(entities)


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
        """Return the shared DIRIS Digiware device."""
        return self._device_info

    @property
    def native_value(self) -> float | int | None:
        """Return the latest reading for this circuit."""
        reading = self.coordinator.data.get(self._circuit_key)
        if reading is None:
            return None
        if self.entity_description.key == ENERGY_DESCRIPTION.key:
            return reading.active_energy_kwh
        return reading.active_power_w

    @property
    def available(self) -> bool:
        """Keep entities available when one measurement is temporarily absent."""
        return self.coordinator.last_update_success
