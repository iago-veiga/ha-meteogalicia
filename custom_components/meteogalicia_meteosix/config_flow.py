"""Config flow for MeteoGalicia."""

from __future__ import annotations

import math
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    MeteoGaliciaAuthError,
    MeteoGaliciaConnectionError,
    MeteoSixClient,
    MgrssObservationsClient,
    StationInfo,
)
from .const import (
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STATION_ID,
    DEFAULT_NAME,
    DOMAIN,
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _nearest(
    stations: list[StationInfo],
    lat: float,
    lon: float,
    n: int = 20,
) -> list[StationInfo]:
    return sorted(
        stations,
        key=lambda s: _haversine_km(lat, lon, s.latitude, s.longitude),
    )[:n]


class MeteoGaliciaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY]
            lat = user_input[CONF_LATITUDE]
            lon = user_input[CONF_LONGITUDE]

            unique = f"{lat:.4f},{lon:.4f}"
            await self.async_set_unique_id(unique)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            client = MeteoSixClient(session, api_key)

            try:
                # Minimal validation call.
                await client.get_numeric_forecast(
                    latitude=lat,
                    longitude=lon,
                    variables=["temperature"],
                )
            except MeteoGaliciaAuthError:
                errors["base"] = "invalid_auth"
            except MeteoGaliciaConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

            if not errors:
                self._data = {
                    CONF_NAME: user_input.get(CONF_NAME) or DEFAULT_NAME,
                    CONF_API_KEY: api_key,
                    CONF_LATITUDE: lat,
                    CONF_LONGITUDE: lon,
                }
                return await self.async_step_station()

        default_lat = getattr(self.hass.config, "latitude", None)
        default_lon = getattr(self.hass.config, "longitude", None)

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(
                    CONF_LATITUDE,
                    default=(
                        float(default_lat)
                        if default_lat is not None
                        else 0.0
                    ),
                ): float,
                vol.Required(
                    CONF_LONGITUDE,
                    default=(
                        float(default_lon)
                        if default_lon is not None
                        else 0.0
                    ),
                ): float,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_station(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = user_input.get(CONF_STATION_ID) or ""
            if station_id:
                self._data[CONF_STATION_ID] = station_id
            return self.async_create_entry(
                title=self._data[CONF_NAME],
                data=self._data,
            )

        session = async_get_clientsession(self.hass)
        obs_client = MgrssObservationsClient(session)

        stations: list[StationInfo] = []
        try:
            stations = await obs_client.list_stations()
        except MeteoGaliciaConnectionError:
            # Don't block setup for optional station step.
            stations = []

        lat = float(self._data[CONF_LATITUDE])
        lon = float(self._data[CONF_LONGITUDE])

        options: dict[str, str] = {"": "(No station)"}
        for s in _nearest(stations, lat, lon):
            label = s.name
            if s.concello:
                label = f"{label} - {s.concello}"
            options[s.station_id] = label

        schema = vol.Schema(
            {
                vol.Optional(CONF_STATION_ID, default=""): vol.In(
                    options
                )
            }
        )

        return self.async_show_form(
            step_id="station",
            data_schema=schema,
            errors=errors,
        )
