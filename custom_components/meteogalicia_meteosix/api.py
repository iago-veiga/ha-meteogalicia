"""HTTP clients for MeteoGalicia services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncio
import async_timeout

from aiohttp import ClientError, ClientSession

from .const import METEOSIX_BASE_URL, MGRSS_BASE_URL


class MeteoGaliciaError(Exception):
    """Base error for MeteoGalicia."""


class MeteoGaliciaConnectionError(MeteoGaliciaError):
    """Network-level error."""


class MeteoGaliciaAuthError(MeteoGaliciaError):
    """Authentication error (API_KEY invalid/missing)."""


class MeteoGaliciaApiError(MeteoGaliciaError):
    """API returned an error payload."""

    def __init__(self, code: str | None, message: str | None) -> None:
        super().__init__(f"API error {code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class StationInfo:
    station_id: str
    name: str
    concello: str | None
    provincia: str | None
    latitude: float
    longitude: float


def _try_parse_exception(payload: Any) -> tuple[str | None, str | None]:
    """Parse MeteoGalicia exception payload.

    The MeteoSIX v5 manual describes a top-level object with 'exception'.
    """

    if not isinstance(payload, dict):
        return None, None

    exc = payload.get("exception")
    if not isinstance(exc, dict):
        return None, None

    code = exc.get("code")
    message = exc.get("message")

    return (
        str(code) if code is not None else None,
        str(message) if message is not None else None,
    )


class MeteoSixClient:
    """Client for MeteoSIX v5 endpoints."""

    def __init__(self, session: ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def get_numeric_forecast(
        self,
        *,
        latitude: float,
        longitude: float,
        lang: str = "en",
        tz: str = "Europe/Madrid",
        variables: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch numeric forecast for a point using coords (lon,lat)."""

        vars_param = None
        if variables:
            vars_param = ",".join(variables)

        params = {
            "API_KEY": self._api_key,
            "coords": f"{longitude},{latitude}",
            "lang": lang,
            "tz": tz,
            "format": "application/json",
        }
        if vars_param:
            params["variables"] = vars_param

        url = f"{METEOSIX_BASE_URL}/getNumericForecastInfo"

        try:
            async with async_timeout.timeout(15):
                resp = await self._session.get(url, params=params)
                data = await resp.json(content_type=None)
        except (TimeoutError, asyncio.TimeoutError) as err:
            raise MeteoGaliciaConnectionError("Timeout") from err
        except ClientError as err:
            raise MeteoGaliciaConnectionError("Client error") from err

        code, message = _try_parse_exception(data)
        if code in {"005", "006"}:
            raise MeteoGaliciaAuthError(message or "Invalid API key")
        if code is not None:
            raise MeteoGaliciaApiError(code, message)

        if not isinstance(data, dict):
            raise MeteoGaliciaApiError(None, "Unexpected response")

        return data

    async def get_solar_info(
        self,
        *,
        latitude: float,
        longitude: float,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        lang: str = "en",
        tz: str = "Europe/Madrid",
    ) -> dict[str, Any]:
        """Fetch solar info for a point using coords (lon,lat).

        The API expects startTime/endTime as yyyy-MM-ddTHH:mm:ss (no TZ).
        """

        params: dict[str, str] = {
            "API_KEY": self._api_key,
            "coords": f"{longitude},{latitude}",
            "lang": lang,
            "tz": tz,
            "format": "application/json",
        }

        if start_time is not None:
            params["startTime"] = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        if end_time is not None:
            params["endTime"] = end_time.strftime("%Y-%m-%dT%H:%M:%S")

        url = f"{METEOSIX_BASE_URL}/getSolarInfo"

        try:
            async with async_timeout.timeout(15):
                resp = await self._session.get(url, params=params)
                data = await resp.json(content_type=None)
        except (TimeoutError, asyncio.TimeoutError) as err:
            raise MeteoGaliciaConnectionError("Timeout") from err
        except ClientError as err:
            raise MeteoGaliciaConnectionError("Client error") from err

        code, message = _try_parse_exception(data)
        if code in {"005", "006"}:
            raise MeteoGaliciaAuthError(message or "Invalid API key")
        if code is not None:
            raise MeteoGaliciaApiError(code, message)

        if not isinstance(data, dict):
            raise MeteoGaliciaApiError(None, "Unexpected response")

        return data


class MgrssObservationsClient:
    """Client for public mgrss station observation endpoints."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list_stations(self) -> list[StationInfo]:
        url = f"{MGRSS_BASE_URL}/observacion/listaEstacionsMeteo.action"
        try:
            async with async_timeout.timeout(15):
                resp = await self._session.get(url)
                data = await resp.json(content_type=None)
        except (TimeoutError, asyncio.TimeoutError) as err:
            raise MeteoGaliciaConnectionError("Timeout") from err
        except ClientError as err:
            raise MeteoGaliciaConnectionError("Client error") from err

        stations: list[StationInfo] = []
        raw = (
            data.get("listaEstacionsMeteo")
            if isinstance(data, dict)
            else None
        )
        if not isinstance(raw, list):
            return stations

        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                station_id = str(item.get("idEstacion"))
                name = str(item.get("estacion"))
                lat = float(item.get("lat"))
                lon = float(item.get("lon"))
            except (TypeError, ValueError):
                continue

            stations.append(
                StationInfo(
                    station_id=station_id,
                    name=name,
                    concello=item.get("concello"),
                    provincia=item.get("provincia"),
                    latitude=lat,
                    longitude=lon,
                )
            )

        return stations

    async def latest_10min_observations(
        self, station_id: str
    ) -> dict[str, Any]:
        url = f"{MGRSS_BASE_URL}/observacion/ultimos10minEstacionsMeteo.action"
        params = {"idEst": station_id}
        try:
            async with async_timeout.timeout(15):
                resp = await self._session.get(url, params=params)
                data = await resp.json(content_type=None)
        except (TimeoutError, asyncio.TimeoutError) as err:
            raise MeteoGaliciaConnectionError("Timeout") from err
        except ClientError as err:
            raise MeteoGaliciaConnectionError("Client error") from err

        if not isinstance(data, dict):
            raise MeteoGaliciaApiError(None, "Unexpected response")

        return data
