"""Sensor platform for MeteoGalicia station observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    DEGREE,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_STATION_ID, DEFAULT_NAME, DOMAIN


@dataclass(frozen=True)
class StationSensorDescription(SensorEntityDescription):
    code: str | None = None


SENSORS: tuple[StationSensorDescription, ...] = (
    StationSensorDescription(
        key="temperature",
        name="Temperature",
        code="TA_AVG_1.5m",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StationSensorDescription(
        key="humidity",
        name="Humidity",
        code="HR_AVG_1.5m",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StationSensorDescription(
        key="pressure",
        name="Pressure",
        code="PR_AVG_1.5m",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StationSensorDescription(
        key="wind_speed",
        name="Wind speed",
        code="VV_AVG_10m",
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StationSensorDescription(
        key="wind_bearing",
        name="Wind bearing",
        code="DV_AVG_10m",
        device_class=SensorDeviceClass.WIND_DIRECTION,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
    ),
    StationSensorDescription(
        key="rain",
        name="Rain (10 min)",
        code="PP_SUM_1.5m",
        device_class=SensorDeviceClass.PRECIPITATION,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


def _is_valid_measure(measure: dict[str, Any]) -> bool:
    # The service uses validation codes; 1 commonly means OK.
    code = measure.get("lnCodigoValidacion")
    try:
        if code is None:
            return True
        return int(code) == 1
    except (TypeError, ValueError):
        return True


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        v = float(value)
        # Common sentinel for missing values
        if v == -9999.0:
            return None
        return v
    except (TypeError, ValueError):
        return None


class MeteoGaliciaStationSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        description: StationSensorDescription,
    ) -> None:
        self.entity_description = description
        self._entry = entry
        self._coordinator = entry.runtime_data["station_coordinator"]
        station_id = entry.data[CONF_STATION_ID]

        self._attr_unique_id = (
            f"{entry.entry_id}_station_{station_id}_{description.code}"
        )

    @property
    def device_info(self) -> DeviceInfo:
        station_id = str(self._entry.data.get(CONF_STATION_ID) or "")
        return DeviceInfo(
            identifiers={
                (DOMAIN, f"{self._entry.entry_id}_station_{station_id}")
            },
            name=f"{self._entry.title or DEFAULT_NAME} - Station {station_id}",
            manufacturer="MeteoGalicia",
            model="mgrss/observacion",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    @property
    def native_value(self) -> float | None:
        data = self._coordinator.data or {}
        measures = data.get("measures") if isinstance(data, dict) else None
        if not isinstance(measures, dict):
            return None

        m = measures.get(self.entity_description.code or "")
        if not isinstance(m, dict):
            return None

        if not _is_valid_measure(m):
            return None

        return _as_float(m.get("valor"))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if CONF_STATION_ID not in entry.data or not entry.data[CONF_STATION_ID]:
        return

    async_add_entities([MeteoGaliciaStationSensor(entry, d) for d in SENSORS])
