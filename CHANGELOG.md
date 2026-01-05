# Changelog

El formato de versiones sigue CalVer: `YYYY.MM.PATCH`.

## 2025.12.0 - 2025-12-23

- Primera versión pública.
- Pronóstico MeteoSIX v5 (horario) y pronóstico diario sintetizado.
- Mapeo completo de `sky_state` a `condition` de Home Assistant, con ajuste día/noche usando `getSolarInfo`.
- Soporte opcional de observaciones de estación (endpoints públicos `mgrss/observacion`).
- Propiedades meteorológicas adicionales cuando están disponibles (p. ej. presión y nubosidad).
- Dispositivos agrupados con `DeviceInfo` y enlace a MeteoGalicia.

## 2026.01.0 - 2026-01-05

- i18n: traducciones en ES/GL y uso de `translation_key` en entidades.
- Observaciones de estación más fiables (entidades basadas en `DataUpdateCoordinator`).
- Selección automática de estación cercana por coordenadas.
- Avisos por concello: sensor para hoy y mañana (derivado de `dia=-1`) con mapping 0–3.
