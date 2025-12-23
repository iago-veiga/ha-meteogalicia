"""Constants for the MeteoGalicia integration."""

from __future__ import annotations

DOMAIN = "meteogalicia_meteosix"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_STATION_ID = "station_id"

DEFAULT_NAME = "MeteoGalicia (MeteoSIX)"

PLATFORMS: list[str] = ["weather", "sensor"]

# MeteoSIX v5
METEOSIX_BASE_URL = "https://servizos.meteogalicia.gal/apiv5"

# mgrss station observations
MGRSS_BASE_URL = "https://servizos.meteogalicia.gal/mgrss"

# Default polling intervals (keep conservative; can be adjusted later)
FORECAST_UPDATE_INTERVAL_MINUTES = 30
STATION_UPDATE_INTERVAL_MINUTES = 5
