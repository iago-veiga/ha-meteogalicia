"""The MeteoGalicia integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import MeteoSixClient, MgrssAdversosClient, MgrssObservationsClient
from .const import (
    CONF_API_KEY,
    CONF_CONCELLO_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_STATION_ID,
    PLATFORMS,
)
from .coordinator import (
    ConcelloAlertsCoordinator,
    ForecastCoordinator,
    SolarCoordinator,
    StationCoordinator,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MeteoGalicia from a config entry."""

    session = async_get_clientsession(hass)

    forecast_client = MeteoSixClient(session, entry.data[CONF_API_KEY])
    obs_client = MgrssObservationsClient(session)
    adversos_client = MgrssAdversosClient(session)

    forecast_coordinator = ForecastCoordinator(
        hass,
        forecast_client,
        latitude=float(entry.data[CONF_LATITUDE]),
        longitude=float(entry.data[CONF_LONGITUDE]),
        variables=[
            "sky_state",
            "temperature",
            "relative_humidity",
            "cloud_area_fraction",
            "air_pressure_at_sea_level",
            "wind",
            "precipitation_amount",
        ],
    )

    solar_coordinator = SolarCoordinator(
        hass,
        client=forecast_client,
        latitude=float(entry.data[CONF_LATITUDE]),
        longitude=float(entry.data[CONF_LONGITUDE]),
    )

    station_coordinator = None
    station_id = entry.data.get(CONF_STATION_ID)
    if station_id:
        station_coordinator = StationCoordinator(
            hass, obs_client, str(station_id)
        )

    alerts_coordinator = None
    concello_id = entry.data.get(CONF_CONCELLO_ID)
    if concello_id:
        alerts_coordinator = ConcelloAlertsCoordinator(
            hass,
            adversos_client,
            str(concello_id),
            dia=-1,
        )

    try:
        await forecast_coordinator.async_config_entry_first_refresh()
        await solar_coordinator.async_config_entry_first_refresh()
        if station_coordinator is not None:
            await station_coordinator.async_config_entry_first_refresh()
        if alerts_coordinator is not None:
            await alerts_coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady from err

    entry.runtime_data = {
        "forecast_coordinator": forecast_coordinator,
        "solar_coordinator": solar_coordinator,
        "station_coordinator": station_coordinator,
        "alerts_coordinator": alerts_coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
