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
    MgrssAdversosClient,
    MgrssObservationsClient,
    StationInfo,
)
from .const import (
    CONF_API_KEY,
    CONF_CONCELLO_ID,
    CONF_CONCELLO_NAME,
    CONF_ENABLE_ALERTS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DEFAULT_NAME,
    DOMAIN,
)


def _normalize_place_name(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _parse_concellos_from_nivel_max(payload: Any) -> list[tuple[str, str]]:
    if not isinstance(payload, dict):
        return []
    dia_list = payload.get("listaDiaConcellos")
    if not isinstance(dia_list, list) or not dia_list:
        return []
    first = dia_list[0]
    if not isinstance(first, dict):
        return []
    items = first.get("listaNiveisMaximos")
    if not isinstance(items, list):
        return []

    out: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        cid = item.get("idConcello")
        cname = item.get("nomeConcello")
        if cid is None or cname is None:
            continue
        out.append((str(cid), str(cname)))
    return out


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
        # Station selection is automatic based on coordinates.
        # We still keep this step in the flow to keep a stable UX and allow
        # future extension (e.g., optional overrides) without breaking entries.
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

        if stations:
            nearest = _nearest(stations, lat, lon, n=1)
            if nearest:
                station = nearest[0]
                self._data[CONF_STATION_ID] = station.station_id
                self._data[CONF_STATION_NAME] = station.name

        return await self.async_step_alerts()

    async def async_step_alerts(
        self,
        user_input: dict[str, Any] | None = None,
    ):
        errors: dict[str, str] = {}

        if user_input is not None:
            enable_alerts = bool(user_input.get(CONF_ENABLE_ALERTS, True))
            self._data[CONF_ENABLE_ALERTS] = enable_alerts

            concello_id = str(user_input.get(CONF_CONCELLO_ID) or "").strip()
            if enable_alerts and concello_id:
                self._data[CONF_CONCELLO_ID] = concello_id

                # Persist concello name if possible (nice UX in attributes).
                session = async_get_clientsession(self.hass)
                obs_client = MgrssObservationsClient(session)
                try:
                    for cid, cname in await obs_client.list_concellos():
                        if cid == concello_id:
                            self._data[CONF_CONCELLO_NAME] = cname
                            break
                except MeteoGaliciaConnectionError:
                    pass

            return self.async_create_entry(
                title=self._data[CONF_NAME],
                data=self._data,
            )

        # Best-effort: use HA location_name to pick concello.
        session = async_get_clientsession(self.hass)
        obs_client = MgrssObservationsClient(session)

        concellos: list[tuple[str, str]] = []
        try:
            concellos = await obs_client.list_concellos()
        except MeteoGaliciaConnectionError:
            concellos = []

        # Fallback: the concellos observation endpoint can be empty; the
        # adverse warnings endpoint provides a full concello catalog.
        if not concellos:
            adv_client = MgrssAdversosClient(session)
            try:
                payload = await adv_client.concellos_nivel_max(dia=0)
                concellos = _parse_concellos_from_nivel_max(payload)
            except MeteoGaliciaConnectionError:
                concellos = []

        options: dict[str, str] = {}
        for cid, cname in sorted(concellos, key=lambda x: x[1]):
            options[cid] = cname

        default_concello_id = ""
        default_name = getattr(self.hass.config, "location_name", "") or ""
        if default_name and options:
            target = _normalize_place_name(str(default_name))
            for cid, cname in concellos:
                normalized = _normalize_place_name(cname)
                if normalized == target or target in normalized or normalized in target:
                    default_concello_id = cid
                    self._data[CONF_CONCELLO_NAME] = cname
                    break

        if default_concello_id:
            self._data[CONF_ENABLE_ALERTS] = True
            self._data[CONF_CONCELLO_ID] = default_concello_id
            return self.async_create_entry(
                title=self._data[CONF_NAME],
                data=self._data,
            )

        # No confident match: ask user.
        schema = vol.Schema(
            {
                vol.Optional(CONF_ENABLE_ALERTS, default=True): bool,
                vol.Optional(
                    CONF_CONCELLO_ID,
                    default="",
                ): vol.In(options) if options else str,
            }
        )

        return self.async_show_form(
            step_id="alerts",
            data_schema=schema,
            errors=errors,
        )
