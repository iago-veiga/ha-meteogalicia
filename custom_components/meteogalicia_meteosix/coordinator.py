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
    MgrssAdversosClient,
)
from .const import (
    DOMAIN,
    ALERTS_UPDATE_INTERVAL_MINUTES,
    FORECAST_UPDATE_INTERVAL_MINUTES,
    STATION_UPDATE_INTERVAL_MINUTES,
)


def _parse_station_payload(
    payload: dict[str, Any],
    station_id: str,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Return (measures_by_code, instanteLecturaUTC) for the given station."""

    items = payload.get("listUltimos10min")
    if not isinstance(items, list) or not items:
        return {}, None

    station_item: dict[str, Any] | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("idEstacion")) == station_id:
            station_item = item
            break

    if station_item is None:
        return {}, None

    instante = station_item.get("instanteLecturaUTC")
    instante_str = str(instante) if isinstance(instante, str) else None

    measures = station_item.get("listaMedidas")
    if not isinstance(measures, list):
        return {}, instante_str

    out: dict[str, dict[str, Any]] = {}
    for m in measures:
        if not isinstance(m, dict):
            continue

        code = m.get("codigoParametro")
        if not code:
            continue

        out[str(code)] = m

    return out, instante_str


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
            payload = await self._client.latest_10min_observations()
            measures, instante = _parse_station_payload(
                payload, self._station_id
            )

            if not measures:
                items = (
                    payload.get("listUltimos10min")
                    if isinstance(payload, dict)
                    else None
                )
                ids: list[str] = []
                if isinstance(items, list):
                    for it in items:
                        if (
                            isinstance(it, dict)
                            and it.get("idEstacion") is not None
                        ):
                            ids.append(str(it.get("idEstacion")))
                raise UpdateFailed(
                    (
                        f"No recent data for station {self._station_id}. "
                        f"Available station ids: {ids[:50]}"
                    )
                )

            return {
                "raw": payload,
                "measures": measures,
                "instanteLecturaUTC": instante,
            }
        except MeteoGaliciaConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except MeteoGaliciaApiError as err:
            raise UpdateFailed(str(err)) from err


class ConcelloAlertsCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches concello adverse warnings (avisos)."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MgrssAdversosClient,
        concello_id: str,
        *,
        dia: int = 0,
    ) -> None:
        self._client = client
        self._concello_id = str(concello_id)
        self._dia = int(dia)

        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=f"{DOMAIN}_concello_{self._concello_id}_avisos",
            update_interval=timedelta(
                minutes=ALERTS_UPDATE_INTERVAL_MINUTES
            ),
        )

    @property
    def concello_id(self) -> str:
        return self._concello_id

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            payload = await self._client.avisos_concellos(
                dia=self._dia,
                concello_id=self._concello_id,
            )

            # Documented payload is nested:
            # {"listaDiaConcellos": [
            #   {"dia": 0, "listaAvisosConcellos": [...]}
            # ]}
            # But we also keep a fallback for alternative shapes.
            avisos_by_day_raw: dict[int, list[Any]] = {}

            if isinstance(payload, dict):
                dia_list = payload.get("listaDiaConcellos")
                if isinstance(dia_list, list):
                    for item in dia_list:
                        if not isinstance(item, dict):
                            continue
                        try:
                            day = int(item.get("dia"))
                        except (TypeError, ValueError):
                            continue
                        raw_avisos = item.get("listaAvisosConcellos")
                        if isinstance(raw_avisos, list):
                            avisos_by_day_raw[day] = raw_avisos

                # Backward/alternative shape fallback.
                if not avisos_by_day_raw:
                    raw_avisos = payload.get("listaAvisosConcellos")
                    if isinstance(raw_avisos, list):
                        avisos_by_day_raw[self._dia] = raw_avisos

            def _normalize_avisos(
                raw_list: list[Any],
            ) -> tuple[list[dict[str, Any]], int, str | None]:
                normalized: list[dict[str, Any]] = []
                max_level = 0
                concello_name: str | None = None
                for a in raw_list:
                    if not isinstance(a, dict):
                        continue

                    concello_id = a.get("idconcello")
                    if concello_id is None:
                        concello_id = a.get("idConcello")

                    if (
                        concello_id is not None
                        and str(concello_id) != self._concello_id
                    ):
                        continue
                    try:
                        level = int(a.get("idNivel"))
                    except (TypeError, ValueError):
                        level = 0

                    max_level = max(max_level, level)
                    if concello_name is None:
                        concello_name = a.get("nomeConcello")

                    normalized.append(
                        {
                            "idconcello": concello_id,
                            "nomeConcello": a.get("nomeConcello"),
                            "idNivel": level,
                            "dataAviso": a.get("dataAviso"),
                            "dataIni": a.get("dataIni"),
                            "dataFin": a.get("dataFin"),
                            "idTipoAlerta": a.get("idTipoAlerta"),
                            "tipoalerta_gl": a.get("tipoalerta_gl"),
                            "tipoalerta_es": a.get("tipoalerta_es"),
                        }
                    )
                return normalized, max_level, concello_name

            alerts_by_day: dict[int, list[dict[str, Any]]] = {}
            max_level_by_day: dict[int, int] = {}
            concello_name: str | None = None

            for day, raw_avisos in avisos_by_day_raw.items():
                normalized, day_max, day_name = _normalize_avisos(raw_avisos)
                alerts_by_day[day] = normalized
                max_level_by_day[day] = day_max
                if concello_name is None and day_name:
                    concello_name = day_name

            # Preserve old keys for compatibility (use day=0 when present).
            if 0 in alerts_by_day:
                alerts_today = alerts_by_day[0]
                max_today = max_level_by_day.get(0, 0)
            else:
                # If upstream doesn't return a day list, fallback to any day.
                only_day = next(iter(alerts_by_day.keys()), self._dia)
                alerts_today = alerts_by_day.get(only_day, [])
                max_today = max_level_by_day.get(only_day, 0)

            return {
                "raw": payload,
                "alerts": alerts_today,
                "max_level": max_today,
                "alerts_by_day": alerts_by_day,
                "max_level_by_day": max_level_by_day,
                "concello_name": concello_name,
            }
        except MeteoGaliciaConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except MeteoGaliciaApiError as err:
            raise UpdateFailed(str(err)) from err
