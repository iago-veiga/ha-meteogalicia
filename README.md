# MeteoGalicia (MeteoSIX) — Integración personalizada para Home Assistant

Integración de Home Assistant para obtener previsión meteorológica desde **MeteoSIX v5** (MeteoGalicia). Opcionalmente, puede añadir sensores con observaciones en vivo desde estaciones (endpoint público `mgrss/observacion`).

- Pronóstico **cada hora** (MeteoSIX JSON)
- Pronóstico **diario** (sintetizado a partir del horario)
- Condiciones (`condition`) con mapeo completo de `sky_state` + soporte día/noche usando `getSolarInfo`

## Requisitos

- Home Assistant con soporte de integraciones personalizadas
- Una **API key** de MeteoSIX

## Obtener API key (MeteoSIX)

MeteoSIX es público y gratuito, pero requiere API key.

1. Página de MeteoSIX: [meteogalicia.gal/web/modelos-numericos/meteosix](https://www.meteogalicia.gal/web/modelos-numericos/meteosix)
2. Solicita la clave por email: `administracion-web.meteogalicia@xunta.gal`
3. En Home Assistant, configura la integración e introduce la clave.

Manual oficial (v5):

- [API_MeteoSIX_v5_gl.pdf](https://meteo-estaticos.xunta.gal/datosred/infoweb/meteo/proxectos/meteosix/API_MeteoSIX_v5_gl.pdf)

## Instalación (HACS)

Este repositorio está preparado para usarse como **repositorio personalizado** en HACS.

1. En HACS → Integraciones → Menú (⋮) → Repositorios personalizados
2. Añade `https://github.com/iago-veiga/ha-meteogalicia` como tipo **Integración**
3. Instala “MeteoGalicia (MeteoSIX)”
4. Reinicia Home Assistant

Enlace “My Home Assistant” (añadir repo a HACS):

- [Añadir repositorio a HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=iago-veiga&repository=ha-meteogalicia&category=integration)

## Instalación (manual)

1. Copia `custom_components/meteogalicia_meteosix` a `/config/custom_components/`
2. Reinicia Home Assistant
3. Ajustes → Dispositivos y servicios → Añadir integración → “MeteoGalicia (MeteoSIX)”

## Configuración

La configuración se realiza desde la UI (Config Flow):

- `api_key`: API key de MeteoSIX
- `latitude` / `longitude`: coordenadas para el pronóstico (por defecto usa la ubicación de Home Assistant)
- Estación (opcional): añade sensores de observación (viento/temperatura/lluvia, etc.)

## Entidades

- `weather.*`: previsión MeteoSIX (horaria + diaria)
- `sensor.*` (opcional): observaciones de estación (endpoint público)

Nota: el panel estándar de “Clima” no siempre muestra todas las propiedades (p. ej. nubosidad o presión). Aunque existan como atributos, puede que no aparezcan en esa UI. Para verlos siempre, añádelos a una tarjeta “Entidades” o crea sensores dedicados.

## Solución de problemas

- Tras actualizar la integración, **reinicia Home Assistant**. Con solo “recargar” a veces quedan módulos cacheados.
- Si ves `condition` desconocida, revisa los atributos `meteosix_sky_state*` y los logs para detectar códigos no mapeados.

## Versionado y releases

Este proyecto usa CalVer: `YYYY.MM.PATCH`.

Para que HACS muestre versiones correctamente, publica un **GitHub Release** con una etiqueta (tag) que coincida con la versión del `manifest.json` (por ejemplo `2025.12.0`).

## Iconos / branding

Este repositorio incluye arte para:

- HACS (raíz del repositorio): `icon.png` y `logo.png`
- Home Assistant (directorio de la integración): `custom_components/meteogalicia_meteosix/icon.png` y `custom_components/meteogalicia_meteosix/logo.png`

## Desarrollo

El componente vive en `custom_components/meteogalicia_meteosix`.

Documentación adicional:

- [docs/meteosix_sky_state_mapping.md](docs/meteosix_sky_state_mapping.md)
