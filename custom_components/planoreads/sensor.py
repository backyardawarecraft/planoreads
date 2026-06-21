"""At-a-glance sensors derived from the latest portal scrape.

The hourly/daily *graphs* are driven by the imported long-term statistics
(statistic_id ``planoreads:water_<meter>``), not by these sensors. These exist
for dashboard tiles: today's usage so far, the latest odometer reading, and the
timestamp of the most recent read (so you can see how stale the portal is).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PlanoReadsConfigEntry
from .const import DOMAIN
from .coordinator import PlanoData, PlanoReadsCoordinator


@dataclass(frozen=True, kw_only=True)
class PlanoSensorDescription(SensorEntityDescription):
    """Describes a PlanoReads sensor."""

    value_fn: Callable[[PlanoData], float | object | None]


SENSORS: tuple[PlanoSensorDescription, ...] = (
    PlanoSensorDescription(
        key="today_usage",
        translation_key="today_usage",
        icon="mdi:water",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.today_usage,
    ),
    PlanoSensorDescription(
        key="latest_reading",
        translation_key="latest_reading",
        icon="mdi:gauge",
        native_unit_of_measurement=UnitOfVolume.GALLONS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.latest_reading,
    ),
    PlanoSensorDescription(
        key="last_read",
        translation_key="last_read",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.last_read,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlanoReadsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the PlanoReads sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        PlanoSensor(coordinator, entry, desc) for desc in SENSORS
    )


class PlanoSensor(CoordinatorEntity[PlanoReadsCoordinator], SensorEntity):
    """A derived PlanoReads sensor."""

    entity_description: PlanoSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PlanoReadsCoordinator,
        entry: PlanoReadsConfigEntry,
        description: PlanoSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Plano Water Meter",
            manufacturer="City of Plano",
        )

    @property
    def native_value(self):
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
