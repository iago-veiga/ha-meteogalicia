"""Weather platform for MeteoGalicia (MeteoSIX forecast)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import sun as sun_helper
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

_SKY_STATE_TO_HA: dict[str, str] = {
    # MeteoSIX v5 documented values (plus a few common aliases).
    "SUNNY": "sunny",
    "CLEAR": "sunny",
    "CLOUDY": "cloudy",
    "HIGH_CLOUDS": "partlycloudy",
    "MID_CLOUDS": "partlycloudy",
    "PARTLY_CLOUDY": "partlycloudy",
    "OVERCAST": "cloudy",
    "OVERCAST_AND_SHOWERS": "rainy",
    "FOG": "fog",
    "MIST": "fog",
    "FOG_BANK": "fog",
    "RAIN": "rainy",
    "WEAK_RAIN": "rainy",
    "DRIZZLE": "rainy",
    "SHOWERS": "rainy",
    "WEAK_SHOWERS": "rainy",
    "SNOW": "snowy",
    "INTERMITENT_SNOW": "snowy",
    "MELTED_SNOW": "snowy-rainy",
    "SLEET": "snowy-rainy",
    "STORMS": "lightning-rainy",
    "RAIN_HAIL": "hail",
    "STORM": "lightning-rainy",
    "THUNDERSTORM": "lightning-rainy",
    "STORM_THEN_CLOUDY": "lightning-rainy",
}


def _normalize_sky_code(code: str) -> str:
    return code.strip().upper().replace("-", "_").replace(" ", "_")


_UNMAPPED_SKY_CODES: set[str] = set()


def _map_sky_state(code: str) -> str | None:
    normalized = _normalize_sky_code(code)
    mapped = _SKY_STATE_TO_HA.get(normalized)
    if mapped is None and normalized not in _UNMAPPED_SKY_CODES:
        _UNMAPPED_SKY_CODES.add(normalized)
        _LOGGER.warning(
            "Unmapped MeteoSIX sky_state code: %s (normalized). "
            "Update _SKY_STATE_TO_HA to improve icons.",
            normalized,
        )
    return mapped


def _apply_day_night(
    hass: HomeAssistant | None,
    solar_coordinator: Any | None,
    when_utc: datetime,
    condition: str | None,
) -> str | None:
    """Adjust condition for day/night-aware icons.

    Home Assistant provides a dedicated condition for clear nights.
    Frontends typically show a moon icon for "clear-night".
    """

    if condition != "sunny":
        return condition

    # Prefer provider solar info when available.
    try:
        if solar_coordinator is not None and hasattr(
            solar_coordinator, "get_sunrise_sunset"
        ):
            local_when = dt_util.as_local(when_utc)
            sunrise, sunset = solar_coordinator.get_sunrise_sunset(
                local_when.date()
            )
            if sunrise is not None and sunset is not None:
                local_when_naive = local_when.replace(tzinfo=None)
                if local_when_naive < sunrise or local_when_naive >= sunset:
                    return "clear-night"
    except Exception:  # noqa: BLE001
        pass

    if hass is None:
        return condition

    try:
        if not sun_helper.is_up(hass, utc_point_in_time=when_utc):
            return "clear-night"
    except Exception:  # noqa: BLE001
        return condition

    return condition


def _extract_features(data: dict[str, Any]) -> list[dict[str, Any]]:
    features = data.get("features")
    if isinstance(features, list):
        return [f for f in features if isinstance(f, dict)]
    return []


def _iter_values_by_variable(
    data: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """Return variable name -> list of values.

    Each value typically contains timeInstant plus fields.
    """

    out: dict[str, list[dict[str, Any]]] = {}

    features = _extract_features(data)
    if not features:
        return out

    props = (
        features[0].get("properties")
        if isinstance(features[0], dict)
        else None
    )
    if not isinstance(props, dict):
        return out

    days = props.get("days")
    if not isinstance(days, list):
        return out

    for day in days:
        if not isinstance(day, dict):
            continue
        variables = day.get("variables")
        if not isinstance(variables, list):
            continue

        for var in variables:
            if not isinstance(var, dict):
                continue
            name = var.get("name")
            values = var.get("values")
            if not name or not isinstance(values, list):
                continue

            bucket = out.setdefault(str(name), [])
            for v in values:
                if isinstance(v, dict):
                    bucket.append(v)

    return out


def _pick_nearest(
    values: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any] | None:
    best: tuple[float, dict[str, Any]] | None = None
    for v in values:
        time_raw = v.get("timeInstant")
        if not isinstance(time_raw, str):
            continue
        dt = dt_util.parse_datetime(time_raw)
        if dt is None:
            continue
        dt = dt_util.as_utc(dt)
        diff = abs((dt - now).total_seconds())
        if best is None or diff < best[0]:
            best = (diff, v)
    return best[1] if best else None


def _pick_nearest_with_dt(
    values: list[dict[str, Any]],
    now: datetime,
) -> tuple[datetime, dict[str, Any]] | None:
    best: tuple[float, datetime, dict[str, Any]] | None = None
    for v in values:
        time_raw = v.get("timeInstant")
        if not isinstance(time_raw, str):
            continue
        dt = dt_util.parse_datetime(time_raw)
        if dt is None:
            continue
        dt = dt_util.as_utc(dt)
        diff = abs((dt - now).total_seconds())
        if best is None or diff < best[0]:
            best = (diff, dt, v)
    if best is None:
        return None
    return (best[1], best[2])


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class MeteoGaliciaWeather(WeatherEntity):
    _attr_has_entity_name = True
    _attr_name = "Forecast"
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._coordinator = entry.runtime_data["forecast_coordinator"]
        self._solar_coordinator = entry.runtime_data.get("solar_coordinator")

        self._attr_unique_id = f"{entry.entry_id}_forecast"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title or DEFAULT_NAME,
            manufacturer="MeteoGalicia",
            model="MeteoSIX v5",
        )

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success

    @property
    def condition(self) -> str | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)

        # Align the current condition to the nearest hourly slot we use for
        # temperatures (to avoid mismatches and "unknown" condition).
        now = dt_util.utcnow()
        temps = by_var.get("temperature") or []
        nearest_temp = _pick_nearest_with_dt(temps, now)
        if nearest_temp is None:
            return None
        slot_dt, _ = nearest_temp

        # Index sky_state by timestamp for an exact join.
        sky = by_var.get("sky_state") or []
        sky_by_dt: dict[datetime, dict[str, Any]] = {}
        for v in sky:
            time_raw = v.get("timeInstant")
            if not isinstance(time_raw, str):
                continue
            dt = dt_util.parse_datetime(time_raw)
            if dt is None:
                continue
            sky_by_dt[dt_util.as_utc(dt)] = v

        sky_val = sky_by_dt.get(slot_dt) or _pick_nearest(sky, now)
        if not sky_val:
            return None

        code = sky_val.get("value")
        if not isinstance(code, str):
            return None

        return _apply_day_night(
            self.hass,
            self._solar_coordinator,
            slot_dt,
            _map_sky_state(code),
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose raw MeteoSIX codes to make mapping/debugging easier."""

        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        now = dt_util.utcnow()

        temps = by_var.get("temperature") or []
        nearest_temp = _pick_nearest_with_dt(temps, now)
        if nearest_temp is None:
            return None
        slot_dt, _ = nearest_temp

        sky = by_var.get("sky_state") or []
        sky_by_dt: dict[datetime, dict[str, Any]] = {}
        for v in sky:
            time_raw = v.get("timeInstant")
            if not isinstance(time_raw, str):
                continue
            dt = dt_util.parse_datetime(time_raw)
            if dt is None:
                continue
            sky_by_dt[dt_util.as_utc(dt)] = v

        sky_val = sky_by_dt.get(slot_dt) or _pick_nearest(sky, now)
        raw_code = sky_val.get("value") if isinstance(sky_val, dict) else None

        attrs: dict[str, Any] = {
            "meteosix_slot_time_utc": slot_dt.isoformat(),
        }
        if isinstance(raw_code, str):
            attrs["meteosix_sky_state"] = raw_code
            attrs["meteosix_sky_state_normalized"] = _normalize_sky_code(
                raw_code
            )

        # Helpful for validating day/night switching.
        try:
            if self._solar_coordinator is not None:
                local_when = dt_util.as_local(slot_dt)
                sunrise, sunset = self._solar_coordinator.get_sunrise_sunset(
                    local_when.date()
                )
                if sunrise is not None:
                    attrs["meteosix_sunrise_local"] = sunrise.isoformat()
                if sunset is not None:
                    attrs["meteosix_sunset_local"] = sunset.isoformat()
        except Exception:  # noqa: BLE001
            pass

        return attrs

    @property
    def native_temperature(self) -> float | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        temps = by_var.get("temperature") or []
        now = dt_util.utcnow()
        nearest = _pick_nearest(temps, now)
        if not nearest:
            return None
        return _as_float(nearest.get("value"))

    @property
    def humidity(self) -> float | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        hums = by_var.get("relative_humidity") or []
        now = dt_util.utcnow()
        nearest = _pick_nearest(hums, now)
        if not nearest:
            return None
        return _as_float(nearest.get("value"))

    @property
    def wind_speed(self) -> float | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        winds = by_var.get("wind") or []
        now = dt_util.utcnow()
        nearest = _pick_nearest(winds, now)
        if not nearest:
            return None
        return _as_float(nearest.get("moduleValue"))

    @property
    def wind_bearing(self) -> float | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        winds = by_var.get("wind") or []
        now = dt_util.utcnow()
        nearest = _pick_nearest(winds, now)
        if not nearest:
            return None
        return _as_float(nearest.get("directionValue"))

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)

        temps = by_var.get("temperature") or []
        sky = by_var.get("sky_state") or []
        winds = by_var.get("wind") or []
        prec = by_var.get("precipitation_amount") or []

        # Index by timestamp for quick join.
        def index(
            values: list[dict[str, Any]],
        ) -> dict[datetime, dict[str, Any]]:
            out: dict[datetime, dict[str, Any]] = {}
            for v in values:
                time_raw = v.get("timeInstant")
                if not isinstance(time_raw, str):
                    continue
                dt = dt_util.parse_datetime(time_raw)
                if dt is None:
                    continue
                dt = dt_util.as_utc(dt)
                out[dt] = v
            return out

        t_idx = index(temps)
        s_idx = index(sky)
        w_idx = index(winds)
        p_idx = index(prec)

        hours = sorted(t_idx.keys())[:48]
        if not hours:
            return None

        forecasts: list[Forecast] = []
        for dt in hours:
            t = t_idx.get(dt)
            s = s_idx.get(dt)
            w = w_idx.get(dt)
            p = p_idx.get(dt)

            cond: str | None = None
            if s and isinstance(s.get("value"), str):
                cond = _map_sky_state(str(s.get("value")))
                cond = _apply_day_night(
                    self.hass,
                    self._solar_coordinator,
                    dt,
                    cond,
                )

            forecasts.append(
                {
                    "datetime": dt_util.as_local(dt).isoformat(),
                    "temperature": _as_float(t.get("value")) if t else None,
                    "condition": cond,
                    "precipitation": _as_float(p.get("value")) if p else None,
                    "wind_speed": (
                        _as_float(w.get("moduleValue"))
                        if w
                        else None
                    ),
                    "wind_bearing": (
                        _as_float(w.get("directionValue"))
                        if w
                        else None
                    ),
                }
            )

        return forecasts


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MeteoGaliciaWeather(entry)])
