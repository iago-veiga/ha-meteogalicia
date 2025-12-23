# MeteoGalicia (Home Assistant Custom Integration)

Forecasts are provided by **MeteoSIX v5** (requires an `API_KEY`). Optional live station observations are fetched from MeteoGalicia's public `mgrss/observacion` endpoints.

## API key (MeteoSIX)

MeteoSIX API is public and free, but you must request an API key.

1. Open: [MeteoSIX](https://www.meteogalicia.gal/web/modelos-numericos/meteosix)
2. Request your key by email: `administracion-web.meteogalicia@xunta.gal`
3. Configure the integration in Home Assistant and paste your key.

Official manual (v5):

- [API_MeteoSIX_v5_gl.pdf](https://meteo-estaticos.xunta.gal/datosred/infoweb/meteo/proxectos/meteosix/API_MeteoSIX_v5_gl.pdf)

## Development

This repo currently contains the provider documentation PDFs and the custom component under `custom_components/meteogalicia_meteosix`.

Additional docs:

- [docs/meteosix_sky_state_mapping.md](docs/meteosix_sky_state_mapping.md)
