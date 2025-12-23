"""Coordinators for MeteoGalicia data updates."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    MeteoGaliciaApiError,
    MeteoGaliciaAuthError,
    MeteoGaliciaConnectionError,
    MeteoSixClient,
    MgrssObservationsClient,
)
from .const import (
    DOMAIN,
    FORECAST_UPDATE_INTERVAL_MINUTES,
    STATION_UPDATE_INTERVAL_MINUTES,
)


def _parse_station_measurements(
    payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return mapping codigoParametro -> measurement dict.

    The mgrss "ultimos10min" response includes a list of readings.
    We use the newest.
    """

    readings = payload.get("listUltimos10min")
    if not isinstance(readings, list) or not readings:
        return {}

    newest = readings[0]
    if not isinstance(newest, dict):
        return {}

    measures = newest.get("listaMedidas")
    if not isinstance(measures, list):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for m in measures:
        if not isinstance(m, dict):
            continue

        code = m.get("codigoParametro")
        if not code:
            continue

        out[str(code)] = m

    return out


class ForecastCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches MeteoSIX numeric forecast for a single point."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MeteoSixClient,
        latitude: float,
        longitude: float,
        *,
        lang: str = "en",
        tz: str = "Europe/Madrid",
        variables: list[str] | None = None,
    ) -> None:
        self._client = client
        self._latitude = latitude
        self._longitude = longitude
        self._lang = lang
        self._tz = tz
        self._variables = variables

        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"{DOMAIN}_forecast",
            update_interval=timedelta(
                minutes=FORECAST_UPDATE_INTERVAL_MINUTES
            ),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self._client.get_numeric_forecast(
                latitude=self._latitude,
                longitude=self._longitude,
                lang=self._lang,
                tz=self._tz,
                variables=self._variables,
            )
        except MeteoGaliciaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MeteoGaliciaConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except MeteoGaliciaApiError as err:
            raise UpdateFailed(str(err)) from err


class SolarCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for solar info (sunrise/sunset) for configured coordinates.

    We fetch a small window (today..today+2) and cache it.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        client: MeteoSixClient,
        latitude: float,
        longitude: float,
    ) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"{DOMAIN}_solar",
            update_interval=timedelta(hours=12),
        )
        self._client = client
        self._latitude = latitude
        self._longitude = longitude

    async def _async_update_data(self) -> dict[str, Any]:
        # API expects local wall time string; tz param is provided.
        start = datetime.now()
        end = start + timedelta(days=3)
        try:
            return await self._client.get_solar_info(
                latitude=self._latitude,
                longitude=self._longitude,
                start_time=start,
                end_time=end,
            )
        except MeteoGaliciaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MeteoGaliciaConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except MeteoGaliciaApiError as err:
            raise UpdateFailed(str(err)) from err

    def get_sunrise_sunset(
        self, day: date
    ) -> tuple[datetime | None, datetime | None]:
        """Return (sunrise, sunset) datetimes (naive) for the requested day."""

        data = self.data
        if not isinstance(data, dict):
            return None, None

        features = data.get("features")
        if not isinstance(features, list):
            return None, None

        target_day = day.isoformat()
        for feat in features:
            if not isinstance(feat, dict):
                continue
            props = feat.get("properties")
            if not isinstance(props, dict):
                continue
            if props.get("day") != target_day:
                continue

            sunrise = _parse_day_time(target_day, props.get("sunrise"))
            sunset = _parse_day_time(target_day, props.get("sunset"))
            return sunrise, sunset

        return None, None


def _parse_day_time(day_str: str, time_str: Any) -> datetime | None:
    if not isinstance(time_str, str) or not time_str:
        return None
    try:
        return datetime.fromisoformat(f"{day_str}T{time_str}")
    except ValueError:
        return None


class StationCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches mgrss station observations."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MgrssObservationsClient,
        station_id: str,
    ) -> None:
        self._client = client
        self._station_id = station_id

        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"{DOMAIN}_station_{station_id}",
            update_interval=timedelta(minutes=STATION_UPDATE_INTERVAL_MINUTES),
        )

    @property
    def station_id(self) -> str:
        return self._station_id

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            payload = await self._client.latest_10min_observations(
                self._station_id
            )
            measures = _parse_station_measurements(payload)
            return {
                "raw": payload,
                "measures": measures,
            }
        except MeteoGaliciaConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except MeteoGaliciaApiError as err:
            raise UpdateFailed(str(err)) from err
