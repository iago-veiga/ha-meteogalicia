"""Constants for the MeteoGalicia integration."""

from __future__ import annotations

DOMAIN = "meteogalicia_meteosix"

CONF_API_KEY = "api_key"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_CONCELLO_ID = "concello_id"
CONF_CONCELLO_NAME = "concello_name"
CONF_ENABLE_ALERTS = "enable_alerts"

DEFAULT_NAME = "MeteoGalicia (MeteoSIX)"

PLATFORMS: list[str] = ["weather", "sensor"]

# MeteoSIX v5
METEOSIX_BASE_URL = "https://servizos.meteogalicia.gal/apiv5"

# mgrss station observations
MGRSS_BASE_URL = "https://servizos.meteogalicia.gal/mgrss"

# Default polling intervals (keep conservative; can be adjusted later)
FORECAST_UPDATE_INTERVAL_MINUTES = 30
STATION_UPDATE_INTERVAL_MINUTES = 5

# Default polling interval for concello alerts
ALERTS_UPDATE_INTERVAL_MINUTES = 10
