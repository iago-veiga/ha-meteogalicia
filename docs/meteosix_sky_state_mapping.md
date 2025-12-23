# MeteoSIX `sky_state` → Home Assistant `condition`

Este documento resume los valores posibles de `sky_state` (según el manual de MeteoSIX v5 y lo observado en la integración), cómo los normalizamos y cómo se correlacionan con el estado `condition` de Home Assistant.

## 1) Qué devuelve MeteoSIX

En el endpoint `getNumericForecastInfo`, la variable `sky_state` llega como un string (p. ej. `"SUNNY"`) asociado a una hora (`timeInstant`).

### Lista de valores documentados (manual MeteoSIX v5)

Estos son los valores enumerados en el manual (v5):

- `SUNNY`
- `HIGH_CLOUDS`
- `MID_CLOUDS`
- `PARTLY_CLOUDY`
- `CLOUDY`
- `OVERCAST`
- `FOG`
- `MIST`
- `FOG_BANK`
- `SHOWERS`
- `WEAK_SHOWERS`
- `DRIZZLE`
- `RAIN`
- `WEAK_RAIN`
- `SNOW`
- `INTERMITENT_SNOW`
- `MELTED_SNOW`
- `STORMS`
- `STORM_THEN_CLOUDY`
- `OVERCAST_AND_SHOWERS`
- `RAIN_HAIL`

> Nota: El manual también menciona que `sky_state` tiene un símbolo asociado (`iconURL`), pero Home Assistant no usa ese icono directamente: la UI depende de `condition`.

### Día / noche

MeteoSIX no expone un `sky_state` distinto “de noche” (no hay un `CLEAR_NIGHT` equivalente). En Home Assistant, el icono de luna aparece principalmente con `condition = clear-night`.

Por eso la integración aplica una regla adicional:

- Si MeteoSIX devuelve algo equivalente a “cielo despejado” (`SUNNY`) y para esa hora es de noche, se convierte a `clear-night`.
- Para decidir noche/día se prefiere `getSolarInfo` (sunrise/sunset) para las coordenadas configuradas; si no hay datos, se hace fallback al cálculo solar de Home Assistant.

## 2) Normalización de códigos

Antes de mapear, el código se normaliza:

- Se hace `strip()`
- Se pasa a mayúsculas
- Se sustituyen guiones y espacios por `_`

Ejemplos:

- `"weak-showers"` → `WEAK_SHOWERS`
- `"Storm then cloudy"` → `STORM_THEN_CLOUDY`

## 3) Tabla de correlación (lo que usa la integración)

La integración traduce MeteoSIX → `condition` de Home Assistant así:

| MeteoSIX `sky_state` | HA `condition` | Comentario |
|---|---|---|
| `SUNNY` | `sunny` (o `clear-night` si es noche) | Noche según sunrise/sunset |
| `HIGH_CLOUDS` | `partlycloudy` | Nubes altas |
| `MID_CLOUDS` | `partlycloudy` | Nubes medias |
| `PARTLY_CLOUDY` | `partlycloudy` | Parcialmente nuboso |
| `CLOUDY` | `cloudy` | Nuboso (más cerrado que partly) |
| `OVERCAST` | `cloudy` | Cubierto |
| `FOG` | `fog` | Niebla |
| `MIST` | `fog` | Bruma/niebla ligera |
| `FOG_BANK` | `fog` | Banco de niebla |
| `SHOWERS` | `rainy` | Chubascos |
| `WEAK_SHOWERS` | `rainy` | Chubascos débiles |
| `DRIZZLE` | `rainy` | Llovizna |
| `RAIN` | `rainy` | Lluvia |
| `WEAK_RAIN` | `rainy` | Lluvia débil |
| `OVERCAST_AND_SHOWERS` | `rainy` | Cubierto con chubascos |
| `SNOW` | `snowy` | Nieve |
| `INTERMITENT_SNOW` | `snowy` | Nieve intermitente |
| `MELTED_SNOW` | `snowy-rainy` | Aguanieve / mezcla |
| `STORMS` | `lightning-rainy` | Tormenta con precipitación |
| `STORM_THEN_CLOUDY` | `lightning-rainy` | Se prioriza la tormenta |
| `RAIN_HAIL` | `hail` | Lluvia con granizo |

### Qué pasa con códigos no mapeados

Si aparece un valor nuevo/no previsto, la integración:

- Lo normaliza.
- Lo registra en logs como “unmapped” (una vez por código).
- Devuelve `None` en `condition`, lo que suele verse como “desconocido”/sin icono específico.

## 4) Condiciones disponibles en Home Assistant (y posibles mejoras)

Home Assistant soporta un conjunto fijo de `condition` (las más comunes):

- `clear-night` (noche despejada)
- `sunny`
- `partlycloudy`
- `cloudy`
- `fog`
- `rainy`
- `pouring`
- `snowy`
- `snowy-rainy`
- `hail`
- `lightning`
- `lightning-rainy`
- `windy`
- `windy-variant`
- `exceptional`

### Cuáles NO estamos usando ahora (y cuándo tendría sentido)

- `pouring`: si el API distinguiese lluvia intensa (no lo hace explícito con estos `sky_state`). Podría considerarse si en el futuro se combina con `precipitation_amount`/intensidad.
- `lightning` (sin lluvia): si existiese un estado de tormenta sin precipitación (no aparece en la lista del manual v5).
- `windy` / `windy-variant`: si quisieras que el icono refleje viento fuerte (no es un `sky_state`; habría que decidirlo en base a `wind.moduleValue`).
- `exceptional`: reservado para condiciones extremas; normalmente no se usa para un parte meteorológico estándar.

## 5) Validación recomendada

1. En la entidad weather, revisa los atributos:
   - `meteosix_sky_state` / `meteosix_sky_state_normalized`
   - `meteosix_sunrise_local` / `meteosix_sunset_local` (si aparecen, está entrando `getSolarInfo`)
2. Comprueba por la noche si, con `SUNNY`, el `condition` pasa a `clear-night`.
3. Si ves un icono “desconocido”, busca en logs el “Unmapped MeteoSIX sky_state code: …” para añadirlo.
