"""Weather platform for MeteoGalicia (MeteoSIX forecast)."""

from __future__ import annotations

import logging
from datetime import datetime, time
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
from homeassistant.const import UnitOfLength, UnitOfPressure, UnitOfSpeed

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


def _get_var_values(
    by_var: dict[str, list[dict[str, Any]]],
    *names: str,
    prefix: str | None = None,
) -> list[dict[str, Any]]:
    for name in names:
        values = by_var.get(name)
        if values:
            return values
    if prefix:
        for key, values in by_var.items():
            if key.startswith(prefix) and values:
                return values
    return []


def _get_first_float(d: dict[str, Any], *keys: str) -> float | None:
    for k in keys:
        if k in d:
            v = _as_float(d.get(k))
            if v is not None:
                return v
    return None


def _percent_int(value: Any) -> int | None:
    v = _as_float(value)
    if v is None:
        return None
    v = max(0.0, min(100.0, v))
    return int(round(v))


class MeteoGaliciaWeather(WeatherEntity):
    _attr_has_entity_name = True
    _attr_name = "Forecast"
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.METERS_PER_SECOND
    _attr_native_precipitation_unit = UnitOfLength.MILLIMETERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY
        | WeatherEntityFeature.FORECAST_DAILY
    )

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
            configuration_url="https://www.meteogalicia.gal",
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

        # Quick sanity-checks for extra variables.
        try:
            attrs["meteosix_pressure_hpa"] = self.native_pressure
            attrs["meteosix_cloud_coverage_pct"] = self.cloud_coverage
        except Exception:  # noqa: BLE001
            pass

        # Minimal payload introspection to debug missing values.
        try:
            available = sorted(by_var.keys())
            attrs["meteosix_available_variables"] = available[:50]

            winds = _get_var_values(by_var, "wind")
            now = dt_util.utcnow()
            w_near = _pick_nearest(winds, now) if winds else None
            if isinstance(w_near, dict):
                attrs["meteosix_wind_keys"] = sorted(w_near.keys())

            pressures = _get_var_values(
                by_var,
                "air_pressure_at_sea_level",
                prefix="air_pressure",
            )
            p_near = _pick_nearest(pressures, now) if pressures else None
            if isinstance(p_near, dict):
                attrs["meteosix_pressure_keys"] = sorted(p_near.keys())
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
    def native_pressure(self) -> float | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        pressures = _get_var_values(
            by_var,
            "air_pressure_at_sea_level",
            prefix="air_pressure",
        )
        now = dt_util.utcnow()
        nearest = _pick_nearest(pressures, now)
        if not nearest:
            return None
        return _get_first_float(nearest, "value", "moduleValue")

    @property
    def pressure(self) -> float | None:
        # Backwards-compatible alias for older HA frontends.
        return self.native_pressure

    @property
    def cloud_coverage(self) -> int | None:
        """Current cloud coverage in %.

        Per HA docs this is a non-native int property.
        MeteoSIX returns cloud_area_fraction in percent.
        """

        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        clouds = _get_var_values(by_var, "cloud_area_fraction", prefix="cloud")
        now = dt_util.utcnow()
        nearest = _pick_nearest(clouds, now)
        if not nearest:
            return None
        return _percent_int(
            _get_first_float(nearest, "value", "moduleValue"),
        )

    @property
    def native_wind_speed(self) -> float | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        winds = _get_var_values(by_var, "wind")
        now = dt_util.utcnow()
        nearest = _pick_nearest(winds, now)
        if not nearest:
            return None
        return _get_first_float(
            nearest,
            "moduleValue",
            "value",
            "speedValue",
            "speed",
        )

    @property
    def wind_speed(self) -> float | None:
        # Backwards-compatible alias.
        return self.native_wind_speed

    @property
    def wind_bearing(self) -> float | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        winds = _get_var_values(by_var, "wind")
        now = dt_util.utcnow()
        nearest = _pick_nearest(winds, now)
        if not nearest:
            return None
        return _get_first_float(
            nearest,
            "directionValue",
            "direction",
            "bearing",
        )

    @property
    def native_precipitation(self) -> float | None:
        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)
        prec = _get_var_values(by_var, "precipitation_amount", prefix="precip")
        now = dt_util.utcnow()
        nearest = _pick_nearest(prec, now)
        if not nearest:
            return None
        return _get_first_float(nearest, "value", "moduleValue")

    @property
    def precipitation(self) -> float | None:
        # Backwards-compatible alias.
        return self.native_precipitation

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

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Build a daily forecast by summarizing hourly values.

        The MeteoSIX JSON response is hourly; the manual notes daily summaries
        exist in the HTML format, but we keep JSON and synthesize daily values.
        """

        data = self._coordinator.data or {}
        by_var = _iter_values_by_variable(data)

        temps = by_var.get("temperature") or []
        sky = by_var.get("sky_state") or []
        winds = by_var.get("wind") or []
        prec = by_var.get("precipitation_amount") or []

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
                out[dt_util.as_utc(dt)] = v
            return out

        t_idx = index(temps)
        s_idx = index(sky)
        w_idx = index(winds)
        p_idx = index(prec)

        hours = sorted(t_idx.keys())
        if not hours:
            return None

        # Group by local date.
        by_day: dict[datetime.date, list[datetime]] = {}
        for dt in hours:
            d = dt_util.as_local(dt).date()
            by_day.setdefault(d, []).append(dt)

        severity: dict[str, int] = {
            "exceptional": 100,
            "lightning-rainy": 90,
            "lightning": 85,
            "hail": 80,
            "snowy-rainy": 70,
            "snowy": 60,
            "pouring": 55,
            "rainy": 50,
            "fog": 40,
            "cloudy": 30,
            "partlycloudy": 20,
            "sunny": 10,
            "clear-night": 10,
        }

        def pick_daily_condition(day_hours: list[datetime]) -> str | None:
            best: tuple[int, str] | None = None
            for dt in day_hours:
                s = s_idx.get(dt)
                if not s or not isinstance(s.get("value"), str):
                    continue
                cond = _map_sky_state(str(s.get("value")))
                if cond is None:
                    continue
                # Daily forecast should be day-oriented; treat clear-night as
                # sunny.
                if cond == "clear-night":
                    cond = "sunny"
                score = severity.get(cond, 0)
                if best is None or score > best[0]:
                    best = (score, cond)
            return best[1] if best else None

        forecasts: list[Forecast] = []
        for d in sorted(by_day.keys())[:7]:
            day_hours = by_day[d]
            t_vals = [
                _as_float(t_idx[h].get("value"))
                for h in day_hours
                if h in t_idx
            ]
            t_vals = [v for v in t_vals if v is not None]
            if not t_vals:
                continue

            p_sum = 0.0
            p_any = False
            for h in day_hours:
                v = p_idx.get(h)
                if not v:
                    continue
                pv = _as_float(v.get("value"))
                if pv is None:
                    continue
                p_sum += pv
                p_any = True

            w_max: float | None = None
            w_dir: float | None = None
            # Prefer wind direction around local noon if available.
            noon_local = datetime.combine(
                d,
                time(12, 0),
                tzinfo=dt_util.DEFAULT_TIME_ZONE,
            )
            noon_utc = dt_util.as_utc(noon_local)
            nearest_wind = _pick_nearest(
                [w_idx[h] for h in day_hours if h in w_idx],
                noon_utc,
            )
            if nearest_wind is not None:
                w_dir = _as_float(nearest_wind.get("directionValue"))

            for h in day_hours:
                w = w_idx.get(h)
                if not w:
                    continue
                wm = _as_float(w.get("moduleValue"))
                if wm is None:
                    continue
                w_max = wm if w_max is None else max(w_max, wm)

            # Use local noon as the datetime anchor.
            local_noon = datetime.combine(
                d,
                time(12, 0),
                tzinfo=dt_util.DEFAULT_TIME_ZONE,
            )
            forecasts.append(
                {
                    "datetime": local_noon.isoformat(),
                    "temperature": max(t_vals),
                    "templow": min(t_vals),
                    "condition": pick_daily_condition(day_hours),
                    "precipitation": p_sum if p_any else None,
                    "wind_speed": w_max,
                    "wind_bearing": w_dir,
                }
            )

        return forecasts


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([MeteoGaliciaWeather(entry)])
