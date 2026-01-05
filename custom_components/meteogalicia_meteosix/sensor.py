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
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_CONCELLO_ID,
    CONF_CONCELLO_NAME,
    CONF_ENABLE_ALERTS,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_NAME,
    DOMAIN,
)


@dataclass(frozen=True)
class StationSensorDescription(SensorEntityDescription):
    code: str | None = None
    fallback_codes: tuple[str, ...] = ()


SENSORS: tuple[StationSensorDescription, ...] = (
    StationSensorDescription(
        key="temperature",
        translation_key="temperature",
        code="TA_AVG_1.5m",
        fallback_codes=("TA_AVG_2m", "TA_INS_1.5m", "TA_INS_2m"),
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StationSensorDescription(
        key="humidity",
        translation_key="humidity",
        code="HR_AVG_1.5m",
        fallback_codes=("HR_AVG_2m", "HR_INS_1.5m", "HR_INS_2m"),
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StationSensorDescription(
        key="pressure",
        translation_key="pressure",
        code="PR_AVG_1.5m",
        fallback_codes=("PR_AVG_2m", "PR_INS_1.5m", "PR_INS_2m"),
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StationSensorDescription(
        key="wind_speed",
        translation_key="wind_speed",
        code="VV_AVG_10m",
        fallback_codes=("VV_INS_10m", "VV_AVG_2m", "VV_INS_2m"),
        device_class=SensorDeviceClass.WIND_SPEED,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    StationSensorDescription(
        key="wind_bearing",
        translation_key="wind_bearing",
        code="DV_AVG_10m",
        fallback_codes=("DV_INS_10m", "DV_AVG_2m", "DV_INS_2m"),
        device_class=SensorDeviceClass.WIND_DIRECTION,
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT_ANGLE,
    ),
    StationSensorDescription(
        key="rain",
        translation_key="rain_10min",
        code="PP_SUM_1.5m",
        fallback_codes=("PP_SUM_2m", "PP_SUM_10m"),
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
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        v = float(value)
        # Common sentinel for missing values
        if v == -9999.0:
            return None
        return v
    except (TypeError, ValueError):
        return None


class MeteoGaliciaStationSensor(CoordinatorEntity, SensorEntity):
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

        super().__init__(self._coordinator)

        self._attr_unique_id = (
            f"{entry.entry_id}_station_{station_id}_{description.key}"
        )

        self._last_used_code: str | None = None

    @property
    def device_info(self) -> DeviceInfo:
        station_id = str(self._entry.data.get(CONF_STATION_ID) or "")
        station_name = str(
            self._entry.data.get(CONF_STATION_NAME) or station_id
        )
        device_name = (
            f"{self._entry.title or DEFAULT_NAME} - Estación {station_name}"
        )
        return DeviceInfo(
            identifiers={
                (DOMAIN, f"{self._entry.entry_id}_station_{station_id}")
            },
            name=device_name,
            manufacturer="MeteoGalicia",
            model="mgrss/observacion",
            configuration_url="https://www.meteogalicia.gal",
            via_device=(DOMAIN, self._entry.entry_id),
        )

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    def _iter_codes(self) -> tuple[str, ...]:
        primary = self.entity_description.code
        fallbacks = self.entity_description.fallback_codes
        codes = tuple(
            c
            for c in (primary, *fallbacks)
            if isinstance(c, str) and c
        )
        return codes

    def _get_measures(self) -> dict[str, Any] | None:
        data = self._coordinator.data or {}
        measures = data.get("measures") if isinstance(data, dict) else None
        if not isinstance(measures, dict):
            return None
        return measures

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        measures = self._get_measures()
        if measures is None:
            return None

        attrs: dict[str, Any] = {
            "meteogalicia_station_id": str(
                self._entry.data.get(CONF_STATION_ID) or ""
            ),
            "meteogalicia_expected_codes": list(self._iter_codes()),
        }

        if self._last_used_code:
            attrs["meteogalicia_code"] = self._last_used_code
            m = measures.get(self._last_used_code)
            if isinstance(m, dict):
                attrs["meteogalicia_validation_code"] = m.get(
                    "lnCodigoValidacion"
                )

        # When value is missing, expose available codes to aid debugging.
        if self.native_value is None:
            attrs["meteogalicia_available_codes"] = sorted(measures.keys())

        return attrs

    @property
    def native_value(self) -> float | None:
        measures = self._get_measures()
        if measures is None:
            return None

        for code in self._iter_codes():
            m = measures.get(code)
            if not isinstance(m, dict):
                continue
            if not _is_valid_measure(m):
                continue
            value = _as_float(m.get("valor"))
            if value is None:
                continue
            self._last_used_code = code
            return value

        self._last_used_code = None
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[SensorEntity] = []

    if CONF_STATION_ID in entry.data and entry.data[CONF_STATION_ID]:
        entities.extend(
            [MeteoGaliciaStationSensor(entry, d) for d in SENSORS]
        )

    enable_alerts = bool(entry.data.get(CONF_ENABLE_ALERTS, False))
    concello_id = entry.data.get(CONF_CONCELLO_ID)
    if enable_alerts and concello_id:
        # Today (compat) + tomorrow
        entities.append(MeteoGaliciaConcelloAlertsSensor(entry, day_offset=0))
        entities.append(MeteoGaliciaConcelloAlertsSensor(entry, day_offset=1))

    if entities:
        async_add_entities(entities)


_ALERT_LEVEL_KEY: dict[int, str] = {
    0: "normal",
    1: "yellow",
    2: "orange",
    3: "red",
}

_ALERT_LEVEL_COLOR: dict[int, str] = {
    0: "green",
    1: "yellow",
    2: "orange",
    3: "red",
}


class MeteoGaliciaConcelloAlertsSensor(CoordinatorEntity, SensorEntity):
    """Sensor exposing concello adverse warnings (avisos)."""

    _attr_has_entity_name = True

    def __init__(self, entry: ConfigEntry, *, day_offset: int = 0) -> None:
        self._entry = entry
        self._day_offset = int(day_offset)
        self._coordinator = entry.runtime_data["alerts_coordinator"]
        super().__init__(self._coordinator)

        concello_id = str(entry.data.get(CONF_CONCELLO_ID) or "")
        # Keep today's unique_id stable for backwards compatibility.
        if self._day_offset == 0:
            self._attr_unique_id = (
                f"{entry.entry_id}_concello_{concello_id}_alerts"
            )
        else:
            self._attr_unique_id = (
                f"{entry.entry_id}_concello_{concello_id}_alerts_d"
                f"{self._day_offset}"
            )

        self._attr_translation_key = (
            "concello_alerts_today"
            if self._day_offset == 0
            else "concello_alerts_tomorrow"
        )

    @property
    def device_info(self) -> DeviceInfo:
        # Attach to the main integration device.
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
        )

    @property
    def native_value(self) -> int | None:
        data = self._coordinator.data or {}
        if not isinstance(data, dict):
            return None

        try:
            max_by_day = data.get("max_level_by_day")
            if isinstance(max_by_day, dict) and self._day_offset in max_by_day:
                return int(max_by_day.get(self._day_offset) or 0)
            return int(data.get("max_level") or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._coordinator.data or {}
        if not isinstance(data, dict):
            return None

        concello_id = str(self._entry.data.get(CONF_CONCELLO_ID) or "")
        concello_name = (
            self._entry.data.get(CONF_CONCELLO_NAME)
            or data.get("concello_name")
        )

        alerts_by_day = data.get("alerts_by_day")
        alerts: list[Any]
        if (
            isinstance(alerts_by_day, dict)
            and self._day_offset in alerts_by_day
        ):
            alerts = alerts_by_day.get(self._day_offset)
        else:
            alerts = data.get("alerts")

        if not isinstance(alerts, list):
            alerts = []

        try:
            max_level_int = int(self.native_value or 0)
        except (TypeError, ValueError):
            max_level_int = 0

        level_key = _ALERT_LEVEL_KEY.get(max_level_int, "normal")
        level_color = _ALERT_LEVEL_COLOR.get(max_level_int, "green")

        return {
            "concello_id": concello_id,
            "concello_name": concello_name,
            "nivel_max": max_level_int,
            "level_key": level_key,
            "level_color": level_color,
            "day_offset": self._day_offset,
            "num_avisos": len(alerts),
            "avisos": alerts,
        }
