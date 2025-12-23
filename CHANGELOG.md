# Changelog

El formato de versiones sigue CalVer: `YYYY.MM.PATCH`.

## 2025.12.0 - 2025-12-23

- Primera versión pública.
- Pronóstico MeteoSIX v5 (horario) y pronóstico diario sintetizado.
- Mapeo completo de `sky_state` a `condition` de Home Assistant, con ajuste día/noche usando `getSolarInfo`.
- Soporte opcional de observaciones de estación (endpoints públicos `mgrss/observacion`).
- Propiedades meteorológicas adicionales cuando están disponibles (p. ej. presión y nubosidad).
- Dispositivos agrupados con `DeviceInfo` y enlace a MeteoGalicia.
