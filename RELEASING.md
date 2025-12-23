# Releases

Este repositorio usa **CalVer**: `YYYY.MM.PATCH` (por ejemplo `2025.12.0`).

La versión que publica HACS se toma del **GitHub Release tag**. Para evitar inconsistencias:

- El tag del Release debe coincidir con `custom_components/meteogalicia_meteosix/manifest.json` → `version`.
- El changelog debe tener una entrada para esa versión.

## Flujo recomendado (PR → merge → release)

1) Crea un PR con los cambios.
2) En ese PR:
   - Actualiza la versión en `custom_components/meteogalicia_meteosix/manifest.json`.
   - Añade una entrada en `CHANGELOG.md`.
3) Espera a que pasen los checks (GitHub Actions) y mergea el PR.
4) Crea un **GitHub Release** con el tag igual a la versión.

> Si tienes branch protection activado, esto es obligatorio (no podrás pushear directo a `main`).

## Cómo elegir la siguiente versión

- Cambios compatibles / fixes: incrementa PATCH
  - `2025.12.0` → `2025.12.1` → `2025.12.2`
- Si cambias de mes, empieza en `.0`
  - `2025.12.3` → `2026.01.0`

## Crear una release en GitHub (paso a paso)

1) Asegúrate de que `main` tiene el commit con la versión correcta.
2) Abre: GitHub → tu repo → **Releases** → **Draft a new release**
3) "Choose a tag": escribe el tag exacto (ej. `2025.12.0`) y crea el tag.
4) "Target": `main`
5) "Release title": `2025.12.0`
6) "Description": copia el bloque de `CHANGELOG.md` correspondiente a esa versión.
7) Publish release.

## Verificar en HACS

- Si el repo está añadido como repositorio personalizado en HACS, tras unos minutos debería aparecer una actualización.
- Si no aparece:
  - Revisa que el release/tag existe y coincide con `manifest.json`.
  - Revisa que `hacs.json` está en la raíz.
  - Revisa que la estructura sea `custom_components/meteogalicia_meteosix/...`.

## Checklist antes del release

- [ ] `manifest.json` → `version` actualizada
- [ ] `CHANGELOG.md` actualizado
- [ ] `hacs.json` presente en la raíz
- [ ] `icon.png` y `logo.png` en la raíz (HACS)
- [ ] `custom_components/meteogalicia_meteosix/icon.png` y `logo.png` (HA UI)
- [ ] Actions en verde (HACS + hassfest + syntax)
