# HidroAlerta Chancay–Huaral — Dashboard

Dashboard interactivo del sistema de pronóstico de caudal y alerta temprana de
crecidas del río Chancay–Huaral (Concurso ANA 2026).

El dashboard es un único archivo autocontenido: [`docs/index.html`](docs/index.html).
Combina un mapa interactivo (Folium/Leaflet) de la cuenca y sus 9 subcuencas,
una serie de tiempo interactiva (Plotly) de caudal observado vs. pronóstico
probabilístico, y tablas de desempeño de los modelos.

## Estructura

```
hidroalerta-dashboard/
  docs/index.html          Dashboard final (GitHub Pages sirve /docs)
  build/build_dashboard.py Genera docs/index.html desde data/
  data/                    Datos curados (CSV + GeoJSON + metadatos)
  requirements.txt
```

## Reconstruir

```bash
pip install -r requirements.txt
python build/build_dashboard.py  # regenera docs/index.html desde data/
```

`build_dashboard.py` solo depende de `data/`, por lo que el dashboard se puede
reconstruir sin acceso a datos adicionales.

## Datos curados (`data/`)

| Archivo | Contenido | Fuente |
|---|---|---|
| `serie_diaria.csv` | Caudal observado + pronóstico P10/P50/P90 (m³/s), 2024–2025 | SENAMHI/ANA + modelo |
| `metricas_modelos.csv` | Métricas por horizonte (NSE, KGE, MAE, CRPS, CSI, POD, FAR) | Evaluación del proyecto |
| `subcuencas.geojson` | 9 subcuencas (nombre, elevación, área) | Shapefile UH menores |
| `cuenca_limite.geojson` | Límite de la cuenca Chancay–Huaral | Shapefile ANA/geogpsperu |
| `metadatos.json` | Estación de aforo, umbral de alerta, área | SNIRH/ANA |

## Fuentes

- **Caudal observado:** SENAMHI / ANA — estación Santo Domingo (SNIRH, 47E214D2).
- **Forzantes meteorológicas:** ERA5-Land (Copernicus / ECMWF).
- **Precipitación grillada:** PISCOp v3.0 (SENAMHI).

## Equipo

Proyecto Integrador — Ciencia de Datos (2026). Equipo HidroAlerta:

- Luis Alonzo Contreras Perez — Datos, modelado y evaluación
- Diego Alonso Javier Mijahuanca Quispe — Análisis exploratorio, visualización y dashboard

## Licencia

Todos los derechos reservados © 2026 Equipo HidroAlerta. La metodología y los modelos
del proyecto son objeto de una publicación en preparación y **no** se incluyen en este
repositorio. Este repositorio contiene únicamente el dashboard y datos de resultados.
