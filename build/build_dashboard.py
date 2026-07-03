"""
build_dashboard.py — Genera docs/index.html (dashboard autocontenido) a partir
de los datos curados en hidroalerta-dashboard/data/.

Reportaje científico interactivo con navegación por pestañas: tipografía
protagonista (serif editorial), hero como tesis, estado codificado en forma
(pills/chips), color semántico separado del acento (agua).

Navegación por pestañas (6 pestañas):
  · Resumen         — hero + mini-strip de fuentes + KPIs + mapa (6 estaciones) + tesis.
  · Pronóstico      — serie interactiva (modelo+horizonte) + zoom crecida feb-2024.
  · Modelos         — habilidad vs horizonte (animada) + tabla de métricas.
  · Clima           — señal ENSO (costero vs ONI) + ablación de índices (NSE) + R².
  · Datos & repr.   — análisis exploratorio (ACF/CCF) + embeddings interactivos.
  · Gestión mensual — producto mensual de disponibilidad hídrica.
Equipo, fuentes (con logos) y licencia viven en un footer persistente.

Uso:
    python build/build_dashboard.py
Salida:
    docs/index.html   (un solo archivo, publicable en GitHub Pages /docs)
"""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from folium.plugins import Fullscreen

# ── Rutas ──────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
PUB = HERE.parent
DATA = PUB / "data"
DOCS = PUB / "docs"
ASSETS = PUB / "assets"
DOCS.mkdir(parents=True, exist_ok=True)

UMBRAL_Q90 = 40.89                       # m3/s — umbral de alerta de crecidas
FECHA_ACTUALIZACION = "2 de julio de 2026"

# ── Sistema de diseño (paleta fría científica; tokens exactos) ────────────────
# Papel / superficie / tinta / muted / hairlines con sesgo azul frío.
COL_BG = "#F7F9FB"          # papel
COL_SURF = "#FFFFFF"        # superficie
COL_INK = "#0C1E2A"         # tinta
COL_MUTED = "#5B6B78"       # texto secundario
COL_BORDER = "#E2E8EE"      # hairlines / bordes
# Acento (agua) — NO usar semánticos como acento.
COL_ACCENT = "#0B6E8C"      # agua / primario
COL_DEEP = "#0A3D54"        # azul profundo
COL_CYAN = "#1BA8C4"        # cian expresivo (acento, uso limitado: hero/eyebrows)
# Semánticos SOLO para estado.
COL_CRIT = "#C0392B"        # alerta / crítico (umbral, días en alerta)
COL_OK = "#2E8B6F"          # normal
COL_WARN = "#D68910"        # aviso

# Trazas de la serie.
COL_OBS = COL_INK                         # observado (tinta)
COL_P50 = COL_ACCENT                      # mediana
COL_BAND = "rgba(11,110,140,0.16)"        # banda P10–P90
COL_GAP = "rgba(10,61,84,0.05)"           # sombreado tramos sin aforo


# ── Template Plotly propio compartido ─────────────────────────────────────────
# En vez de plotly_white: paper/plot transparentes, grid en hairline, fuentes
# del proyecto, colorway con la paleta y hover unificado sobrio. Se aplica a los
# 6 gráficos para una identidad visual coherente (editorial científica).
FONT_SANS = "IBM Plex Sans, -apple-system, Segoe UI, sans-serif"
FONT_MONO = "IBM Plex Mono, SFMono-Regular, Consolas, monospace"
COLORWAY = [COL_ACCENT, COL_DEEP, COL_CYAN, "#8B6F47", "#8FA0AC", COL_OK]


def layout_base(**overrides):
    """Layout Plotly compartido (dict). Transparente, hairlines, tipografía del
    proyecto. Se combina con overrides por-gráfico (axes, márgenes, leyenda)."""
    base = dict(
        colorway=COLORWAY,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_SANS, size=13, color=COL_INK),
        margin=dict(l=54, r=18, t=20, b=40),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=COL_SURF, bordercolor=COL_BORDER,
            font=dict(family=FONT_MONO, size=12, color=COL_INK)),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
            font=dict(size=12, family=FONT_SANS, color=COL_MUTED)),
        modebar=dict(bgcolor="rgba(0,0,0,0)", color=COL_MUTED,
                     activecolor=COL_ACCENT),
    )
    for k, v in overrides.items():
        base[k] = v
    return base


def axis_x(**kw):
    a = dict(gridcolor=COL_BORDER, zeroline=False, linecolor=COL_BORDER,
             tickfont=dict(family=FONT_MONO, size=11, color=COL_MUTED),
             title=dict(font=dict(family=FONT_SANS, size=12, color=COL_MUTED)))
    a.update(kw)
    return a


def axis_y(**kw):
    a = dict(gridcolor=COL_BORDER, zeroline=False,
             tickfont=dict(family=FONT_MONO, size=11, color=COL_MUTED),
             title=dict(font=dict(family=FONT_SANS, size=12, color=COL_MUTED)))
    a.update(kw)
    return a


# ── Carga de datos curados ──────────────────────────────────────────────────
def cargar():
    serie = pd.read_csv(DATA / "serie_diaria.csv", parse_dates=["date"])
    metr = pd.read_csv(DATA / "metricas_modelos.csv")
    meta = json.loads((DATA / "metadatos.json").read_text(encoding="utf-8"))
    subs = json.loads((DATA / "subcuencas.geojson").read_text(encoding="utf-8"))
    lim = json.loads((DATA / "cuenca_limite.geojson").read_text(encoding="utf-8"))
    fcast = pd.read_csv(DATA / "forecast_multimodelo.csv", parse_dates=["date"])
    mens = pd.read_csv(DATA / "mensual.csv", parse_dates=["date"])
    enso = pd.read_csv(DATA / "enso.csv", parse_dates=["date"])
    acf = pd.read_csv(DATA / "eda_acf.csv")
    ccf = pd.read_csv(DATA / "eda_ccf.csv")
    estaciones = pd.read_csv(DATA / "estaciones.csv")
    enso_abl = pd.read_csv(DATA / "enso_ablacion.csv")
    enso_extra = json.loads((DATA / "enso_extra.json").read_text(encoding="utf-8"))
    emb_coords = pd.read_csv(DATA / "embeddings_coords.csv", parse_dates=["fecha"])
    emb_sil = json.loads((DATA / "embeddings_sil.json").read_text(encoding="utf-8"))
    return (serie, metr, meta, subs, lim, fcast, mens, enso, acf, ccf,
            estaciones, enso_abl, enso_extra, emb_coords, emb_sil)


# ── Recursos gráficos (imágenes) → data URI, con degradación tipográfica ──────
def cargar_imagenes():
    """Lee assets/ y devuelve {clave: data_uri}. Ignora placeholders/no-imágenes.

    Claves:
      · 'logo'                         — utec_logo.png (marca del equipo).
      · 'logo_senamhi/ana/ecmwf/noaa'  — logos de las fuentes de datos.
      · 'tool_python/pytorch/gee'      — logos de herramientas (stack técnico).
      · 'foto_1'..'foto_4'             — foto_*.jpg (avatares del equipo, por orden).
    Si una imagen falta, el HTML degrada con respaldo tipográfico (sin roturas).
    Las figuras de representación (embeddings) ya no se embeben: el bloque de
    embeddings es un gráfico Plotly interactivo (data/embeddings_coords.csv).
    """
    recursos = {}
    if not ASSETS.is_dir():
        return recursos

    def a_data_uri(p: Path) -> str | None:
        mime, _ = mimetypes.guess_type(p.name)
        if not mime or not mime.startswith("image/"):
            return None
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    # Logos por nombre de archivo → clave interna. Fuentes de datos:
    # ANA (caudal/SNIRH), SENAMHI (PISCO + estaciones), ECMWF/Copernicus (ERA5-Land) y NOAA (ENSO).
    # Herramientas / stack tecnológico (sección "Herramientas", distinta de las
    # fuentes): Python, PyTorch, Google Earth Engine.
    for clave, archivos in (
        ("logo", ("utec_logo.png",)),
        ("logo_ana", ("ANA_logo.png", "ana_logo.png")),
        ("logo_senamhi", ("senamhi_logo.png",)),
        ("logo_ecmwf", ("ECMWF_logo.png",)),
        # NOAA: acepta variantes de nombre (guion o guion bajo, mayúsculas).
        ("logo_noaa", ("noaa_logo.png", "noaa-logo.png", "NOAA_logo.png",
                       "NOAA-logo.png")),
        # Logos de herramientas (stack): claves 'tool_*'.
        ("tool_python", ("python_logo.png",)),
        ("tool_pytorch", ("pytorch_logo.png",)),
        ("tool_gee", ("googleearth-engine_logo.png",
                      "googleearth_engine_logo.png", "gee_logo.png")),
    ):
        for archivo in archivos:
            p = ASSETS / archivo
            if p.is_file():
                uri = a_data_uri(p)
                if uri:
                    recursos[clave] = uri
                    break

    fotos = sorted(
        p for p in ASSETS.glob("foto_*")
        if p.is_file() and (mimetypes.guess_type(p.name)[0] or "").startswith("image/"))
    for i, p in enumerate(fotos[:4], start=1):
        uri = a_data_uri(p)
        if uri:
            recursos[f"foto_{i}"] = uri
    return recursos


# ── Utilidades ────────────────────────────────────────────────────────────────
def tramos_sin_aforo(serie: pd.DataFrame):
    """Bloques contiguos [inicio, fin] de días sin observación (obs NaN)."""
    mask = serie["obs"].isna().to_numpy()
    fechas = serie["date"].to_numpy()
    bloques = []
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            bloques.append((fechas[i], fechas[j - 1]))
            i = j
        else:
            i += 1
    return bloques


# ── Mapa Folium ──────────────────────────────────────────────────────────────
def construir_mapa(meta, subs, lim, estaciones) -> str:
    est = meta["estacion"]
    # Sin basemap inicial: la capa base activa por defecto se controla por el
    # ORDEN de los TileLayer (el primero añadido con show=True es el que se ve
    # al cargar). Se añade Esri satélite primero → base por defecto.
    m = folium.Map(
        location=[-11.30, -76.85],
        zoom_start=10,
        tiles=None,
        control_scale=True,
    )
    # Capa base por defecto: Esri World Imagery (satélite).
    folium.TileLayer(
        "Esri.WorldImagery", name="Satélite (Esri)", control=True, show=True,
        attr="Tiles © Esri").add_to(m)
    # Alternativas claras (callejero/positron), disponibles en el control.
    folium.TileLayer(
        "CartoDB positron", name="CartoDB Positron (claro)", control=True,
        show=False).add_to(m)
    folium.TileLayer(
        "OpenStreetMap", name="OpenStreetMap", control=True, show=False).add_to(m)

    # Límite de cuenca
    folium.GeoJson(
        lim,
        name="Límite de cuenca",
        style_function=lambda _f: {
            "color": COL_DEEP, "weight": 2.5, "fill": False,
            "dashArray": "6,4",
        },
        interactive=False,
    ).add_to(m)

    # Color por elevación (costa → cabecera) — rampa de la paleta del proyecto:
    # cian expresivo (costa baja) → agua → profundo → tinta azulada (cabecera).
    def color_elev(e):
        if e < 1000:
            return "#7FD3E3"     # cian claro (costa)
        if e < 2500:
            return "#3FA9C4"     # cian medio
        if e < 3800:
            return COL_ACCENT    # agua
        return COL_DEEP          # profundo (cabecera andina)

    grp_sub = folium.FeatureGroup(name="Subcuencas (9)", show=True)
    for feat in subs["features"]:
        p = feat["properties"]
        outlet_line = (
            "<br><b style=\"color:#C0392B\">Subcuenca de salida (outlet)</b>"
            if p["outlet"] else "")
        popup = folium.Popup(
            f"<div style='font-family:IBM Plex Sans,system-ui;font-size:13px;"
            f"min-width:180px'>"
            f"<b style='color:{COL_DEEP}'>{p['nombre']}</b><br>"
            f"<span style='color:{COL_MUTED}'>Elevación:</span> {p['elev_m']:,} m<br>"
            f"<span style='color:{COL_MUTED}'>Área:</span> {p['area_km2']:,} km²"
            f"{outlet_line}"
            f"</div>",
            max_width=260,
        )
        folium.GeoJson(
            feat,
            style_function=lambda _f, e=p["elev_m"]: {
                "fillColor": color_elev(e), "color": "#FFFFFF",
                "weight": 1.1, "fillOpacity": 0.72,
            },
            highlight_function=lambda _f: {"weight": 2.4, "fillOpacity": 0.88,
                                           "color": COL_DEEP},
            tooltip=folium.Tooltip(
                f"<b>{p['nombre']}</b> · {p['elev_m']:,} m"),
            popup=popup,
        ).add_to(grp_sub)
        # Etiqueta del nombre en el centroide
        folium.map.Marker(
            [p["cy"], p["cx"]],
            icon=folium.DivIcon(
                html=(
                    f"<div style='font-family:IBM Plex Sans,system-ui;"
                    f"font-size:11px;font-weight:600;color:{COL_INK};"
                    f"text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff;"
                    f"white-space:nowrap'>{p['nombre']}</div>"),
                icon_size=(0, 0), icon_anchor=(0, 0),
            ),
        ).add_to(grp_sub)
    grp_sub.add_to(m)

    # ── Estaciones de monitoreo (estaciones.csv) ────────────────────────────
    # Dos categorías diferenciadas por tipo:
    #   · aforo         — caudal observado (SENAMHI/ANA, SNIRH). Gota azul agua.
    #   · meteorologica — precipitación/estado (SENAMHI). Nube naranja (aviso).
    grp_aforo = folium.FeatureGroup(name="Estaciones de aforo (SNIRH)", show=True)
    grp_meteo = folium.FeatureGroup(name="Estaciones meteorológicas (SENAMHI)",
                                    show=True)

    def _popup_est(r, titulo, color):
        return folium.Popup(
            f"<div style='font-family:IBM Plex Sans,system-ui;font-size:13px;"
            f"min-width:200px'>"
            f"<b style='color:{color}'>{titulo}</b><br>"
            f"<b>{r['nombre']}</b><br>"
            f"<span style='color:{COL_MUTED}'>Código:</span> {r['codigo']}<br>"
            f"<span style='color:{COL_MUTED}'>Descripción:</span> {r['desc']}<br>"
            f"<span style='color:{COL_MUTED}'>Coord.:</span> {r['lat']}, {r['lon']}"
            f"</div>",
            max_width=300,
        )

    for _, r in estaciones.iterrows():
        if str(r["tipo"]).strip().lower() == "aforo":
            # Gota azul agua + halo, sobre el basemap claro.
            folium.Marker(
                [r["lat"], r["lon"]],
                icon=folium.Icon(color="cadetblue", icon="tint", prefix="fa"),
                tooltip=f"Aforo · {r['nombre']}",
                popup=_popup_est(r, "Estación de aforo (caudal)", COL_ACCENT),
            ).add_to(grp_aforo)
            folium.CircleMarker(
                [r["lat"], r["lon"]], radius=13, color=COL_ACCENT,
                fill=False, weight=2, opacity=0.85,
            ).add_to(grp_aforo)
        else:
            # Meteorológica: marcador de aviso (naranja) con icono de lluvia.
            folium.Marker(
                [r["lat"], r["lon"]],
                icon=folium.Icon(color="orange", icon="cloud-showers-heavy",
                                 prefix="fa"),
                tooltip=f"Meteorológica · {r['nombre']}",
                popup=_popup_est(r, "Estación meteorológica (lluvia)", COL_WARN),
            ).add_to(grp_meteo)

    grp_aforo.add_to(m)
    grp_meteo.add_to(m)

    Fullscreen(title="Pantalla completa",
               title_cancel="Salir", position="topleft").add_to(m)
    folium.LayerControl(collapsed=True, position="topright").add_to(m)

    # Leyenda de elevación + estaciones (paleta del proyecto, tipografía coherente)
    leyenda = f"""
    <div style="position:absolute;bottom:18px;left:12px;z-index:9999;
      background:rgba(255,255,255,0.95);padding:10px 13px;border-radius:10px;
      box-shadow:0 1px 8px rgba(10,61,84,.16);
      font-family:'IBM Plex Sans',system-ui,sans-serif;font-size:12px;
      line-height:1.6;color:{COL_INK};border:1px solid {COL_BORDER}">
      <b style="color:{COL_DEEP};letter-spacing:.06em;text-transform:uppercase;
        font-size:10.5px">Elevación (m)</b><br>
      <span style="display:inline-block;width:12px;height:12px;background:#7FD3E3;
        border-radius:2px;vertical-align:middle"></span> &lt; 1 000<br>
      <span style="display:inline-block;width:12px;height:12px;background:#3FA9C4;
        border-radius:2px;vertical-align:middle"></span> 1 000 – 2 500<br>
      <span style="display:inline-block;width:12px;height:12px;background:{COL_ACCENT};
        border-radius:2px;vertical-align:middle"></span> 2 500 – 3 800<br>
      <span style="display:inline-block;width:12px;height:12px;background:{COL_DEEP};
        border-radius:2px;vertical-align:middle"></span> &gt; 3 800<br>
      <b style="color:{COL_DEEP};letter-spacing:.06em;text-transform:uppercase;
        font-size:10.5px;display:inline-block;margin-top:6px">Estaciones</b><br>
      <span style="color:{COL_ACCENT};font-size:15px;vertical-align:middle">&#9679;</span>
        Aforo (caudal, SNIRH)<br>
      <span style="color:{COL_WARN};font-size:15px;vertical-align:middle">&#9650;</span>
        Meteorológica (lluvia, SENAMHI)
    </div>"""
    m.get_root().html.add_child(folium.Element(leyenda))

    return m.get_root().render()


# ── Serie de pronóstico interactiva (selector modelo + horizonte) ─────────────
# Modelos de forecast_multimodelo.csv. En la tabla de métricas el modelo
# propuesto figura como "RA-TFT"; aquí y en la interfaz se muestra como
# "RA-TFT" (nombre operacional). Este puente evita mostrar el sufijo interno.
MODELOS_FCAST = ["RA-TFT", "HydroST", "LightGBM", "Persistencia"]
LEADS_FCAST = [1, 3, 7, 14]
MODELO_A_METRICA = {"RA-TFT": "RA-TFT"}     # nombre en metricas_modelos.csv
# Colores por modelo en la serie: el propuesto toma el acento (agua); la
# persistencia, un gris frío de referencia; los demás, tonos neutros.
COL_FCAST = {
    "RA-TFT": COL_ACCENT,
    "HydroST": COL_DEEP,
    "LightGBM": "#8B6F47",       # tierra apagada — se distingue del azul
    "Persistencia": "#8FA0AC",   # gris frío (baseline)
}


def _nse(obs: np.ndarray, sim: np.ndarray) -> float | None:
    """NSE sobre pares finitos; None si no hay varianza o faltan datos."""
    m = np.isfinite(obs) & np.isfinite(sim)
    if m.sum() < 3:
        return None
    o, s = obs[m], sim[m]
    denom = np.sum((o - o.mean()) ** 2)
    if denom <= 0:
        return None
    return float(1.0 - np.sum((o - s) ** 2) / denom)


def serie_pronostico_datos(fcast: pd.DataFrame, metr: pd.DataFrame):
    """Empaqueta la serie de cada (modelo, lead) para el gráfico interactivo.

    Devuelve (payload_json, tramos_gap_json). El NSE por combinación se toma de
    metricas_modelos.csv cuando existe ese lead; si no, se calcula de la serie.
    """
    f = fcast.sort_values("date")
    fechas_iso = None
    payload = {}
    metr_idx = metr.set_index(["model", "lead"]) if not metr.empty else None

    for mod in MODELOS_FCAST:
        for ld in LEADS_FCAST:
            sub = f[(f["model"] == mod) & (f["lead"] == ld)]
            if sub.empty:
                continue
            if fechas_iso is None:
                # Eje temporal común (todas las combinaciones comparten fechas).
                base = f[f["lead"] == ld]
                fechas_iso = [d.strftime("%Y-%m-%d")
                              for d in sorted(base["date"].unique())]
            sub = sub.set_index("date").reindex(
                pd.to_datetime(fechas_iso)).reset_index()

            def col(c):
                return [None if pd.isna(v) else round(float(v), 3)
                        for v in sub[c]]

            obs_l = col("obs")
            p50_l = col("p50")
            # NSE: preferir métrica publicada; si no, calcular de la serie.
            nse = None
            nm = MODELO_A_METRICA.get(mod, mod)
            if metr_idx is not None and (nm, ld) in metr_idx.index:
                val = metr_idx.loc[(nm, ld), "NSE"]
                nse = round(float(val), 3)
            if nse is None:
                nse = _nse(np.array([np.nan if v is None else v for v in obs_l],
                                    dtype=float),
                           np.array([np.nan if v is None else v for v in p50_l],
                                    dtype=float))
                if nse is not None:
                    nse = round(nse, 3)
            n_obs = int(sub["obs"].notna().sum())
            es_persist = (mod == "Persistencia")
            payload[f"{mod}|{ld}"] = {
                "p10": None if es_persist else col("p10"),
                "p50": p50_l,
                "p90": None if es_persist else col("p90"),
                "obs": obs_l,
                "nse": nse,
                "n": n_obs,
                "band": (not es_persist),
            }

    if fechas_iso is None:
        fechas_iso = []

    # Tramos sin aforo (a partir de la serie diaria de referencia, lead 1 RA-TFT).
    ref = f[(f["model"] == "RA-TFT") & (f["lead"] == 1)].set_index("date").reindex(
        pd.to_datetime(fechas_iso)).reset_index()
    mask = ref["obs"].isna().to_numpy()
    gaps, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            gaps.append([fechas_iso[i], fechas_iso[j - 1]])
            i = j
        else:
            i += 1

    disponibles = {}    # modelo -> lista de leads presentes
    for mod in MODELOS_FCAST:
        disponibles[mod] = [ld for ld in LEADS_FCAST
                            if f"{mod}|{ld}" in payload]

    cfg = {
        "fechas": fechas_iso,
        "series": payload,
        "gaps": gaps,
        "disponibles": disponibles,
        "umbral": UMBRAL_Q90,
        "colores": COL_FCAST,
        "band_fill": COL_BAND,
        "col_gap": COL_GAP,
        "col_obs": COL_OBS,
        "col_crit": COL_CRIT,
        "col_border": COL_BORDER,
        "col_surf": COL_SURF,
        "col_ink": COL_INK,
        "col_deep": COL_DEEP,
        "col_cyan": COL_CYAN,
        "col_muted": COL_MUTED,
    }
    return json.dumps(cfg, ensure_ascii=False)


def bloque_serie_interactiva(cfg_json: str) -> str:
    """Controles (dos <select>) + contenedor del gráfico + script de dibujo."""
    opciones_modelo = "".join(
        f'<option value="{m}">{m}</option>' for m in MODELOS_FCAST)
    opciones_lead = "".join(
        f'<option value="{ld}">{ld} día{"s" if ld != 1 else ""}</option>'
        for ld in LEADS_FCAST)
    return f"""
    <div class="fc-controls" role="group" aria-label="Selección de modelo y horizonte">
      <label class="fc-field">
        <span class="fc-field-lab">Modelo</span>
        <select id="fc-modelo" class="fc-select" aria-label="Modelo de pronóstico">
          {opciones_modelo}
        </select>
      </label>
      <label class="fc-field">
        <span class="fc-field-lab">Horizonte</span>
        <select id="fc-lead" class="fc-select" aria-label="Horizonte de pronóstico">
          {opciones_lead}
        </select>
      </label>
      <div class="fc-readout" aria-live="polite">
        <span class="fc-readout-lab">NSE (horizonte seleccionado)</span>
        <span id="fc-nse" class="fc-readout-val">—</span>
      </div>
    </div>
    <div id="grafico-serie" class="fc-plot"></div>
    <p id="fc-nota" class="nota"></p>
    <script id="fc-data" type="application/json">{cfg_json}</script>
    """


# Orden y color de las barras de habilidad (lee metricas_modelos.csv, que usa
# el nombre interno "RA-TFT"; en el eje se muestra como "RA-TFT").
ORDEN_MODELO = ["Persistencia", "LightGBM", "HydroST", "RA-TFT"]
ETIQUETA_MODELO = {"RA-TFT": "RA-TFT"}
COL_MODELO = {
    "RA-TFT": COL_ACCENT,
    "HydroST": COL_DEEP,
    "LightGBM": "#8FA6B4",
    "Persistencia": "#B7C2CC",
}


def construir_animacion(metr: pd.DataFrame) -> str:
    """Barras de NSE por modelo que se actualizan al mover el slider de horizonte.

    Mensaje: la Persistencia (baseline naive) decae con el horizonte, mientras
    que el RA-TFT sostiene mejor la habilidad a multi-día.
    """
    leads = sorted(metr["lead"].unique())
    modelos = [m for m in ORDEN_MODELO if m in set(metr["model"])]
    etiquetas = [ETIQUETA_MODELO.get(m, m) for m in modelos]

    def barras_para(lead):
        sub = metr[metr["lead"] == lead].set_index("model")
        xs, ys, cols, texto = [], [], [], []
        for mod, lab in zip(modelos, etiquetas):
            xs.append(lab)
            if mod in sub.index:
                v = float(sub.loc[mod, "NSE"])
                ys.append(v)
                texto.append(f"{v:.3f}")
            else:
                ys.append(None)
                texto.append("")
            cols.append(COL_MODELO.get(mod, COL_ACCENT))
        return xs, ys, cols, texto

    x0, y0, c0, t0 = barras_para(leads[0])
    fig = go.Figure(
        data=[go.Bar(
            x=x0, y=y0, marker_color=c0, text=t0, textposition="outside",
            textfont=dict(family=FONT_MONO, size=13, color=COL_INK),
            cliponaxis=False,
            hovertemplate="%{x}: NSE %{y:.3f}<extra></extra>",
            width=0.62,
        )]
    )

    frames = []
    for ld in leads:
        _, y, c, t = barras_para(ld)
        frames.append(go.Frame(
            name=str(ld),
            data=[go.Bar(x=x0, y=y, marker_color=c, text=t,
                         textposition="outside",
                         textfont=dict(family=FONT_MONO, size=13, color=COL_INK),
                         cliponaxis=False, width=0.62)],
        ))
    fig.frames = frames

    steps = [dict(method="animate", label=f"{ld}",
                  args=[[str(ld)], dict(mode="immediate",
                        frame=dict(duration=0, redraw=True),
                        transition=dict(duration=350, easing="cubic-in-out"))])
             for ld in leads]

    fig.update_layout(**layout_base(
        height=430,
        margin=dict(l=54, r=20, t=20, b=96),
        hovermode="closest",
        yaxis=axis_y(title="NSE (eficiencia Nash–Sutcliffe)", range=[0, 1.0]),
        xaxis=axis_x(title="",
                     tickfont=dict(family=FONT_SANS, size=13, color=COL_INK)),
        showlegend=False,
        updatemenus=[dict(
            type="buttons", direction="left", showactive=False,
            x=0, xanchor="left", y=-0.30, yanchor="top",
            pad=dict(t=0, r=8),
            bgcolor="rgba(255,255,255,0.8)", bordercolor=COL_BORDER,
            font=dict(size=12, family=FONT_SANS, color=COL_DEEP),
            buttons=[
                dict(label="▶  Reproducir", method="animate",
                     args=[None, dict(frame=dict(duration=900, redraw=True),
                                      fromcurrent=True, mode="immediate",
                                      transition=dict(duration=350,
                                                      easing="cubic-in-out"))]),
                dict(label="❚❚  Pausa", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        mode="immediate")]),
            ],
        )],
        sliders=[dict(
            active=0, x=0.16, xanchor="left", y=-0.22, yanchor="top",
            len=0.84, pad=dict(t=0, b=0),
            currentvalue=dict(prefix="Horizonte de pronóstico:  ",
                              suffix="  días",
                              font=dict(size=13, color=COL_DEEP,
                                        family=FONT_MONO)),
            tickcolor=COL_BORDER,
            font=dict(size=11, family=FONT_MONO, color=COL_MUTED),
            steps=steps,
        )],
    ))
    # Línea de referencia NSE=0 (sin habilidad respecto a la media).
    fig.add_hline(y=0, line=dict(color=COL_BORDER, width=1))

    return fig.to_html(
        include_plotlyjs=False, full_html=False,
        div_id="grafico-horizonte",
        config={"displayModeBar": False, "responsive": True},
    )


# ── Tabla de métricas por horizonte ───────────────────────────────────────────
LABEL_LEAD = {1: "1 día", 2: "2 días", 3: "3 días",
              5: "5 días", 7: "7 días", 14: "14 días"}
# Sentido de optimización por columna: True = mayor mejor.
MEJOR_MAYOR = {"NSE": True, "KGE": True, "MAE": False, "CRPS": False,
               "CSI": True, "POD": True, "FAR": False}


def tabla_metricas_html(metr: pd.DataFrame) -> str:
    cols = ["NSE", "KGE", "MAE", "CRPS", "CSI", "POD", "FAR"]
    filas = []
    for lead in [1, 2, 3, 5, 7, 14]:
        sub = metr[metr["lead"] == lead]
        if sub.empty:
            continue
        # Mejor valor por columna dentro del bloque (para el chip).
        best = {}
        for c in cols:
            best[c] = sub[c].max() if MEJOR_MAYOR[c] else sub[c].min()
        first = True
        n_mod = len(sub)
        for _, r in sub.iterrows():
            celdas = []
            for c in cols:
                v = r[c]
                if pd.isna(v):
                    celdas.append("<td class='num na'>—</td>")
                    continue
                txt = f"{v:.3f}" if c != "MAE" else f"{v:.2f}"
                chip = " chip-best" if v == best[c] else ""
                celdas.append(f"<td class='num{chip}'>{txt}</td>")
            lead_cell = (
                f"<td rowspan='{n_mod}' class='lead-cell'>"
                f"<span class='lead-lab'>{LABEL_LEAD[lead]}</span>"
                f"<span class='lead-n'>N = {int(r['N'])}</span></td>"
                if first else "")
            es_prop = r["model"] == "RA-TFT"
            es_base = r["model"] == "Persistencia"
            cls_mod = "modelo"
            if es_prop:
                cls_mod += " modelo-prop"
            elif es_base:
                cls_mod += " modelo-base"
            nombre_mod = ETIQUETA_MODELO.get(r["model"], r["model"])
            filas.append(
                f"<tr>{lead_cell}"
                f"<td class='{cls_mod}'>{nombre_mod}</td>{''.join(celdas)}</tr>")
            first = False
    encabezado = "".join(f"<th>{c}</th>" for c in cols)
    return f"""
    <div class="tabla-scroll">
    <table class="metricas">
      <thead><tr><th>Horizonte</th><th>Modelo</th>{encabezado}</tr></thead>
      <tbody>{''.join(filas)}</tbody>
    </table>
    </div>
    <p class="nota">NSE y KGE: 1 = ajuste perfecto. MAE y CRPS: menor es mejor
    (m³/s). CSI y POD: mayor es mejor; FAR (tasa de falsas alarmas): menor es
    mejor. El chip resalta el mejor valor de cada columna dentro del horizonte.
    <b>Persistencia</b> es un baseline de referencia (naive): repite el último
    caudal observado, por lo que domina el NSE a 1 día por construcción sin
    anticipar cambios. <b>RA-TFT</b> es el modelo de pronóstico propuesto,
    evaluado sin contaminación del objetivo.</p>
    """


# ── 07 · Producto mensual (disponibilidad hídrica) ────────────────────────────
def construir_mensual(mens: pd.DataFrame) -> str:
    m = mens.sort_values("date").reset_index(drop=True)
    fig = go.Figure()

    # Banda P10–P90 (relleno continuo).
    fig.add_trace(go.Scatter(
        x=m["date"], y=m["p90"], mode="lines", line=dict(width=0),
        hoverinfo="skip", showlegend=False, name="P90"))
    fig.add_trace(go.Scatter(
        x=m["date"], y=m["p10"], mode="lines", fill="tonexty",
        fillcolor=COL_BAND, line=dict(width=0), name="Banda P10–P90",
        hovertemplate="P10 %{y:.1f} · "))
    # Climatología (estacionalidad) — techo mensual de referencia.
    fig.add_trace(go.Scatter(
        x=m["date"], y=m["clim"], mode="lines",
        line=dict(color=COL_MUTED, width=1.6, dash="dash"),
        name="Climatología (estacional)",
        hovertemplate="Climatología %{y:.1f} m³/s"))
    # Pronóstico mensual P50.
    fig.add_trace(go.Scatter(
        x=m["date"], y=m["p50"], mode="lines+markers",
        line=dict(color=COL_ACCENT, width=2),
        marker=dict(size=4, color=COL_ACCENT),
        name="Pronóstico mensual (P50)",
        hovertemplate="P50 %{y:.1f} m³/s"))
    # Caudal mensual observado (donde existe).
    obs = m.dropna(subset=["obs"])
    fig.add_trace(go.Scatter(
        x=obs["date"], y=obs["obs"], mode="markers",
        marker=dict(color=COL_INK, size=6, symbol="circle-open",
                    line=dict(width=1.6, color=COL_INK)),
        name="Caudal mensual observado",
        hovertemplate="Observado %{y:.1f} m³/s"))

    fig.update_layout(**layout_base(
        margin=dict(l=58, r=18, t=18, b=36), height=420,
        yaxis=axis_y(title="Caudal medio mensual (m³/s)", rangemode="tozero"),
        xaxis=axis_x(title="")))

    return fig.to_html(
        include_plotlyjs=False, full_html=False, div_id="grafico-mensual",
        config={"displayModeBar": False, "responsive": True})


# ── 08 · Zoom al evento de crecida (feb-2024) ─────────────────────────────────
def construir_evento(fcast: pd.DataFrame) -> str:
    """Overlay obs + modelos a lead 1 y lead 7 (conmutables) en ene–mar 2024."""
    ini, fin = pd.Timestamp("2024-01-01"), pd.Timestamp("2024-03-31")
    win = fcast[(fcast["date"] >= ini) & (fcast["date"] <= fin)]

    fig = go.Figure()
    modelos = [m for m in MODELOS_FCAST if m in set(win["model"])]
    # Índices de trazas por lead (para el conmutador de horizonte).
    vis_lead = {1: [], 7: []}
    orden_traza = 0

    def añadir_modelos(lead, visible):
        nonlocal orden_traza
        for mod in modelos:
            sub = win[(win["model"] == mod) & (win["lead"] == lead)]
            if sub.empty:
                continue
            sub = sub.sort_values("date")
            es_prop = (mod == "RA-TFT")
            fig.add_trace(go.Scatter(
                x=sub["date"], y=sub["p50"], mode="lines",
                line=dict(color=COL_FCAST.get(mod, COL_ACCENT),
                          width=2.4 if es_prop else 1.6,
                          dash="solid" if es_prop else "dot"),
                name=mod, legendgroup=mod, visible=visible,
                hovertemplate=f"{mod} · %{{y:.1f}} m³/s"))
            vis_lead[lead].append(orden_traza)
            orden_traza += 1

    añadir_modelos(1, True)
    añadir_modelos(7, False)
    n_modelos_traza = orden_traza

    # Observado (aforo) en la ventana — traza fija, siempre visible.
    obs = win[(win["model"] == "RA-TFT") & (win["lead"] == 1)].dropna(
        subset=["obs"]).sort_values("date")
    fig.add_trace(go.Scatter(
        x=obs["date"], y=obs["obs"], mode="markers",
        marker=dict(color=COL_INK, size=6, line=dict(width=0)),
        name="Observado (aforo)", hovertemplate="Observado %{y:.1f} m³/s"))

    fig.add_hline(
        y=UMBRAL_Q90, line=dict(color=COL_CRIT, width=1.6, dash="dot"),
        annotation_text=f"Umbral Q90 = {UMBRAL_Q90} m³/s",
        annotation_position="top left",
        annotation_font=dict(color=COL_CRIT, size=12, family=FONT_MONO))

    # Conmutador lead 1 / lead 7 (botones que alternan visibilidad).
    def vis_para(lead):
        v = []
        for i in range(n_modelos_traza):
            v.append(i in vis_lead[lead])
        v.append(True)     # observado siempre visible
        return v

    fig.update_layout(**layout_base(
        margin=dict(l=58, r=18, t=92, b=36), height=470,
        yaxis=axis_y(title="Caudal (m³/s)", rangemode="tozero"),
        xaxis=axis_x(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left",
                    x=0, font=dict(size=12, family=FONT_SANS, color=COL_MUTED)),
        updatemenus=[dict(
            type="buttons", direction="left", showactive=True,
            x=0, xanchor="left", y=1.22, yanchor="top", pad=dict(t=0, r=8),
            bgcolor="rgba(255,255,255,0.8)", bordercolor=COL_BORDER, active=0,
            font=dict(size=12, family=FONT_SANS, color=COL_DEEP),
            buttons=[
                dict(label="Horizonte 1 día", method="update",
                     args=[{"visible": vis_para(1)}]),
                dict(label="Horizonte 7 días", method="update",
                     args=[{"visible": vis_para(7)}]),
            ])]))

    return fig.to_html(
        include_plotlyjs=False, full_html=False, div_id="grafico-evento",
        config={"displayModeBar": False, "responsive": True})


# ── 09 · Señal ENSO (Niño costero vs ONI global) ──────────────────────────────
def construir_enso(enso: pd.DataFrame) -> str:
    e = enso.sort_values("date").reset_index(drop=True)
    fig = go.Figure()

    # Umbrales El Niño / La Niña (±0.5) — banda neutra sombreada.
    fig.add_hrect(y0=-0.5, y1=0.5, fillcolor="rgba(91,107,120,0.06)",
                  line_width=0, layer="below")
    fig.add_hline(y=0, line=dict(color=COL_BORDER, width=1))

    fig.add_trace(go.Scatter(
        x=e["date"], y=e["coastal"], mode="lines",
        line=dict(color=COL_CRIT, width=2),
        name="Niño costero (ICEN)",
        hovertemplate="Niño costero %{y:.2f}"))
    fig.add_trace(go.Scatter(
        x=e["date"], y=e["oni"], mode="lines",
        line=dict(color=COL_DEEP, width=2),
        name="ONI global (Niño 3.4)",
        hovertemplate="ONI global %{y:.2f}"))

    fig.update_layout(**layout_base(
        margin=dict(l=52, r=18, t=18, b=36), height=400,
        yaxis=axis_y(title="Anomalía (°C)"),
        xaxis=axis_x(title="")))

    return fig.to_html(
        include_plotlyjs=False, full_html=False, div_id="grafico-enso",
        config={"displayModeBar": False, "responsive": True})


# ── 09b · Ablación ENSO (aporte de los índices al NSE) ─────────────────────────
def construir_enso_ablacion(enso_abl: pd.DataFrame) -> str:
    """Barras horizontales de NSE por configuración de índices ENSO.

    Resalta "+ Ambos índices" (mejor) con el acento agua; las demás en gris frío.
    El eje se enfoca en 0,66–0,70 para que la diferencia (pequeña pero real) se
    aprecie.
    """
    a = enso_abl.copy()
    # Orden de menor a mayor NSE → la mejor barra queda arriba en la lectura
    # (Plotly dibuja el primer registro abajo en barras horizontales).
    a = a.sort_values("NSE").reset_index(drop=True)
    mejor = a["NSE"].idxmax()
    labels = a["config"].tolist()
    vals = a["NSE"].tolist()
    cols = [COL_ACCENT if i == mejor else "#B7C2CC" for i in range(len(a))]
    texto = [f"{v:.3f}" for v in vals]

    fig = go.Figure(go.Bar(
        x=vals, y=labels, orientation="h",
        marker_color=cols, marker_line_width=0,
        text=texto, textposition="outside",
        textfont=dict(family=FONT_MONO, size=13, color=COL_INK),
        cliponaxis=False, width=0.62,
        hovertemplate="%{y}: NSE %{x:.3f}<extra></extra>",
    ))
    fig.update_layout(**layout_base(
        height=300, showlegend=False, hovermode="closest",
        margin=dict(l=8, r=30, t=12, b=40),
        bargap=0.34,
        xaxis=axis_x(title="NSE (validación)", range=[0.66, 0.70],
                     dtick=0.01, tickformat=".2f"),
        yaxis=axis_y(title="",
                     tickfont=dict(family=FONT_SANS, size=13, color=COL_INK),
                     automargin=True),
    ))
    return fig.to_html(
        include_plotlyjs=False, full_html=False, div_id="grafico-enso-ablacion",
        config={"displayModeBar": False, "responsive": True})


def bloque_enso_callout(extra: dict) -> str:
    """Tarjeta/callout editorial con R² entre índices y el hallazgo de supresión
    mutua (correlaciones parciales, validación 2023)."""
    r = extra.get("r_indices", 0.625)
    r2 = extra.get("r2_indices", 0.39)
    p_oni = extra.get("parcial_oni_dado_costero", -0.283)
    p_cost = extra.get("parcial_costero_dado_oni", 0.273)
    return f"""
    <aside class="callout" aria-label="Hallazgo sobre los índices ENSO">
      <p class="callout-eyebrow">Hallazgo · supresión mutua</p>
      <div class="callout-stat">
        <span class="callout-num">R² = {r2:.2f}</span>
        <span class="callout-unit">r = {r:.3f}</span>
      </div>
      <p class="callout-body">Los dos índices se correlacionan
      (R²&nbsp;=&nbsp;{r2:.2f}) pero afectan al caudal con <b>signo opuesto</b>
      → <b>supresión mutua</b>: la correlación parcial duplica la señal
      (ONI|costero&nbsp;=&nbsp;{p_oni:+.3f}, costero|ONI&nbsp;=&nbsp;{p_cost:+.3f}).
      Usar <b>ambos</b> índices es lo mejor. En 2023 el índice costero llegó a
      <b>+2,11 (Fuerte)</b> mientras el ONI marcaba +0,16 (neutro).</p>
    </aside>"""


# ── 09d · Dispersión Niño costero vs ONI global (R² entre índices) ─────────────
def construir_enso_r2(enso: pd.DataFrame, extra: dict) -> str:
    """Dispersión Niño costero (x) vs ONI global (y) con recta de regresión y la
    anotación R² = 0.39 (r = 0.625). Sustenta gráficamente la correlación entre
    índices (junto a la ablación ENSO). Columnas de enso.csv: coastal, oni."""
    e = enso.dropna(subset=["coastal", "oni"])
    x = e["coastal"].to_numpy(dtype=float)
    y = e["oni"].to_numpy(dtype=float)
    r = float(extra.get("r_indices", 0.625))
    r2 = float(extra.get("r2_indices", 0.39))

    fig = go.Figure()
    # Nube de puntos mensuales (color agua translúcido).
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="markers",
        marker=dict(color="rgba(11,110,140,0.55)", size=6, line=dict(width=0)),
        name="Mes (anomalías)",
        hovertemplate="Niño costero %{x:.2f} °C<br>ONI global %{y:.2f} °C"
                      "<extra></extra>"))

    # Recta de regresión OLS (ONI ~ costero) sobre el rango observado.
    if len(x) >= 2 and np.ptp(x) > 0:
        b1, b0 = np.polyfit(x, y, 1)
        xr = np.array([float(x.min()), float(x.max())])
        yr = b0 + b1 * xr
        fig.add_trace(go.Scatter(
            x=xr, y=yr, mode="lines",
            line=dict(color=COL_CRIT, width=2.4),
            name="Ajuste lineal",
            hovertemplate="Ajuste: ONI = %{y:.2f} °C<extra></extra>"))

    # Anotación editorial con R² (publicado) y r.
    fig.add_annotation(
        xref="paper", yref="paper", x=0.03, y=0.97, xanchor="left",
        yanchor="top", showarrow=False,
        text=f"<b>R² = {r2:.2f}</b>   (r = {r:.3f})",
        font=dict(family=FONT_MONO, size=14, color=COL_DEEP),
        bgcolor="rgba(255,255,255,0.82)", bordercolor=COL_BORDER,
        borderwidth=1, borderpad=6)

    fig.update_layout(**layout_base(
        height=360, hovermode="closest", showlegend=True,
        margin=dict(l=58, r=18, t=14, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left",
                    x=0, font=dict(size=12, family=FONT_SANS, color=COL_MUTED)),
        xaxis=axis_x(title="Niño costero · ICEN (anomalía °C)", zeroline=True,
                     zerolinecolor=COL_BORDER, zerolinewidth=1),
        yaxis=axis_y(title="ONI global · Niño 3.4 (anomalía °C)", zeroline=True,
                     zerolinecolor=COL_BORDER, zerolinewidth=1)))

    return fig.to_html(
        include_plotlyjs=False, full_html=False, div_id="grafico-enso-r2",
        config={"displayModeBar": False, "responsive": True})


# ── 09c · Representación / embeddings (no supervisado, model-agnóstico) ─────────
# Orden de métodos en el selector. Las claves de la silueta pueden venir con
# flecha ASCII ("DTW->MDS"); se normalizan a la etiqueta con flecha unicode.
EMB_METODOS = ["PCA", "Isomap", "UMAP", "DTW→MDS"]


def embeddings_datos(coords: pd.DataFrame, sil: dict) -> str:
    """Empaqueta las proyecciones por método para los small-multiples 2×2.

    Por método emite arrays PLANOS y paralelos (x, y, q, fecha, regimen,
    temporada) para que el JS construya cualquiera de las tres coloraciones
    (magnitud del caudal, crecida vs base, temporada) sobre el MISMO scatter.
    La `fecha` es la llave del HOVER SINCRONIZADO: al pasar el cursor por un
    punto en un panel se resalta el mismo punto (misma fecha) en los demás.
    PCA/Isomap/UMAP comparten fechas; DTW→MDS es un subconjunto propio, por lo
    que el resalte solo aparece donde esa fecha existe. Incluye la silueta
    (crecida/base) por método. Análisis no supervisado (independiente del
    modelo)."""
    def sil_de(metodo: str):
        # Tolera claves con flecha ASCII o unicode.
        for k in (metodo, metodo.replace("→", "->"), metodo.replace("->", "→")):
            if k in sil:
                return round(float(sil[k]), 3)
        return None

    metodos = {}
    q_todos = []
    for met in EMB_METODOS:
        sub = coords[coords["metodo"] == met].reset_index(drop=True)
        if sub.empty:
            continue
        q_vals = [round(float(v), 1) for v in sub["q"]]
        q_todos.extend(q_vals)
        metodos[met] = {
            "x": [round(float(v), 4) for v in sub["x"]],
            "y": [round(float(v), 4) for v in sub["y"]],
            "q": q_vals,
            "fecha": [d.strftime("%Y-%m-%d") for d in sub["fecha"]],
            "regimen": [str(v) for v in sub["regimen"]],      # base / crecida
            "temporada": [str(v) for v in sub["temporada"]],  # humeda / seca
            "sil": sil_de(met),
        }

    # Rango global de caudal para una escala de color continua comparable
    # entre métodos (colorbar azul→rojo).
    q_min = round(min(q_todos), 1) if q_todos else 0.0
    q_max = round(max(q_todos), 1) if q_todos else 1.0

    cfg = {
        "metodos": metodos,
        "orden": [m for m in EMB_METODOS if m in metodos],
        "umbral": UMBRAL_Q90,
        "q_min": q_min,
        "q_max": q_max,
        # Colores semánticos para los conmutadores de coloración.
        "col_base": COL_ACCENT,       # régimen base (azul agua)
        "col_crecida": COL_CRIT,      # régimen crecida (rojo)
        "col_humeda": COL_DEEP,       # temporada húmeda (azul profundo)
        "col_seca": "#D68910",        # temporada seca (ocre/aviso)
        "col_border": COL_BORDER,
        "col_surf": COL_SURF,
        "col_ink": COL_INK,
        "col_muted": COL_MUTED,
        "col_deep": COL_DEEP,
    }
    return json.dumps(cfg, ensure_ascii=False)


def bloque_embeddings(cfg_json: str) -> str:
    """Small-multiples 2×2 sincronizados + conmutador único de 3 coloraciones.

    Los cuatro métodos de proyección (PCA, Isomap, UMAP, DTW→MDS) se muestran a
    la vez en una rejilla 2×2 de mini-scatters Plotly (1 columna en móvil). Un
    único conmutador (3 botones toggle) recolorea los cuatro paneles a la vez
    —magnitud del caudal, crecida vs base (Q90) o temporada—. El HOVER está
    SINCRONIZADO: al pasar el cursor por un punto en cualquier panel se resalta
    el mismo punto (misma fecha) en los demás. Model-agnóstico (no supervisado).

    Los divs de los paneles (uno por método) se crean vacíos; el JS
    (JS_EMBED) dibuja cada scatter y cablea el hover cruzado."""
    # Conmutador de coloración (3 opciones tipo segmented control).
    coloraciones = [
        ("q", "Magnitud del caudal"),
        ("reg", "Crecida vs base (Q90)"),
        ("temp", "Temporada"),
    ]
    # Conmutador de coloración: grupo de botones tipo toggle (aria-pressed).
    # No es un tablist real (no controla tabpanels), por eso aria-pressed.
    botones_col = "".join(
        f"<button type='button' class='emb-cbtn{' is-active' if i == 0 else ''}'"
        f" aria-pressed='{'true' if i == 0 else 'false'}'"
        f" data-color='{cid}'>{lab}</button>"
        for i, (cid, lab) in enumerate(coloraciones))

    # Un panel por método: título (nombre + silueta) + div del mini-scatter.
    # El slug ASCII evita caracteres problemáticos en el id del div.
    slug = {"PCA": "pca", "Isomap": "isomap", "UMAP": "umap", "DTW→MDS": "dtw"}
    paneles = "".join(
        f"""      <figure class="emb-panel" data-metodo="{m}">
        <figcaption class="emb-panel-head">
          <span class="emb-panel-name">{m}</span>
          <span class="emb-panel-sil" id="emb-sil-{slug[m]}">silueta —</span>
        </figcaption>
        <div class="emb-panel-plot" id="grafico-embeddings-{slug[m]}"></div>
      </figure>
"""
        for m in EMB_METODOS)

    return f"""
    <div class="emb" aria-label="Métodos de representación (embeddings)">
      <div class="emb-color" role="group"
           aria-label="Esquema de coloración de los cuatro paneles">
        <span class="emb-color-lab">Colorear por</span>
        {botones_col}
      </div>

      <div class="emb-grid" role="group"
           aria-label="Cuatro métodos de proyección (rejilla 2×2)">
{paneles}      </div>
    </div>
    <p class="nota">Cada punto es una ventana temporal del caudal proyectada a 2D;
    los ejes no tienen unidades físicas (son coordenadas de la proyección). El
    objetivo del embedding es ver cómo se <b>agrupan</b> los datos: comparar los
    <b>cuatro métodos</b> y las <b>tres coloraciones</b> —magnitud del caudal,
    crecida vs base (Q90) y temporada— ayuda a juzgar qué estructura capta cada
    uno. Al pasar el cursor por un punto se <b>resalta el mismo instante</b>
    (misma fecha) en los demás paneles. La <b>silueta</b> mide cuán bien se
    separan crecida y base (mayor = mejor). Al ser un análisis <b>no
    supervisado</b> (sin usar el modelo ni el umbral), la estructura crecida/base
    emerge como propiedad <b>intrínseca de los datos</b>: los métodos no lineales
    (Isomap) y basados en la forma temporal (DTW→MDS) la separan mejor que los
    lineales (PCA).</p>
    <script id="emb-data" type="application/json">{cfg_json}</script>"""


# ── 10 · Análisis exploratorio (ACF + CCF) ────────────────────────────────────
def construir_eda(acf: pd.DataFrame, ccf: pd.DataFrame) -> str:
    a = acf.sort_values("lag")
    c = ccf.sort_values("lag")

    def barras(df, ycol, color, hover):
        return go.Bar(
            x=df["lag"], y=df[ycol], marker_color=color,
            marker_line_width=0, width=0.72, hovertemplate=hover)

    # ACF (izquierda) y CCF (derecha) en subplots simples con dominios x.
    fig = go.Figure()
    fig.add_trace(barras(a, "acf", COL_ACCENT,
                         "lag %{x} · ACF %{y:.3f}<extra></extra>"))
    fig.data[0].update(xaxis="x", yaxis="y")
    fig.add_trace(barras(c, "ccf", COL_DEEP,
                         "lag %{x} d · CCF %{y:.3f}<extra></extra>"))
    fig.data[1].update(xaxis="x2", yaxis="y2")
    pico = c.loc[c["ccf"].idxmax()]

    fig.update_layout(**layout_base(
        height=380, showlegend=False, hovermode="closest",
        margin=dict(l=52, r=18, t=42, b=44),
        xaxis=axis_x(domain=[0.0, 0.46], title="Rezago (días)"),
        yaxis=axis_y(title="ACF del caudal", range=[0, 1.05]),
        xaxis2=axis_x(domain=[0.56, 1.0], title="Rezago lluvia→caudal (días)"),
        yaxis2=axis_y(title="CCF lluvia→caudal", anchor="x2"),
        annotations=[
            dict(text="<b>ACF del caudal</b> (lags 0–30)", xref="paper",
                 yref="paper", x=0.0, y=1.12, showarrow=False, xanchor="left",
                 font=dict(size=12.5, color=COL_INK, family=FONT_SANS)),
            dict(text="<b>CCF lluvia→caudal</b> (lags 0–15)", xref="paper",
                 yref="paper", x=0.56, y=1.12, showarrow=False, xanchor="left",
                 font=dict(size=12.5, color=COL_INK, family=FONT_SANS)),
        ]))
    # Anotaciones didácticas (tras fijar layout.annotations para no perderlas).
    fig.add_annotation(
        xref="x", yref="y", x=1, y=float(a[a["lag"] == 1]["acf"].iloc[0]),
        text="lag-1 ≈ 0.99", showarrow=True, arrowhead=2, ax=36, ay=-24,
        font=dict(size=11, color=COL_DEEP, family=FONT_MONO),
        arrowcolor=COL_DEEP)
    fig.add_annotation(
        xref="x2", yref="y2", x=int(pico["lag"]), y=float(pico["ccf"]),
        text=f"pico en lag ≈ {int(pico['lag'])} d", showarrow=True, arrowhead=2,
        ax=28, ay=-34,
        font=dict(size=11, color=COL_DEEP, family=FONT_MONO),
        arrowcolor=COL_DEEP)

    return fig.to_html(
        include_plotlyjs=False, full_html=False, div_id="grafico-eda",
        config={"displayModeBar": False, "responsive": True})


# ── KPIs editoriales (resumen) ────────────────────────────────────────────────
def kpi_cards(serie: pd.DataFrame) -> str:
    """Fila de indicadores editoriales: números mono grandes separados por
    hairlines (sin cajas). El estado (agua vs. crítico) se codifica en el color
    del número y una pequeña etiqueta, no en un borde de tarjeta."""
    dias_alerta = int((serie["obs"] >= UMBRAL_Q90).sum())
    indicadores = [
        # (etiqueta, valor, unidad, descripción, estado)
        ("NSE · 1 día", "0.966", "", "Eficiencia Nash–Sutcliffe del mejor "
         "modelo a un día de horizonte", "acc"),
        ("POD", "0.824", "", "Probabilidad de detección de crecidas "
         "(alertas correctas sobre el total de eventos)", "acc"),
        ("FAR", "0.176", "", "Tasa de falsas alarmas (alertas emitidas sin "
         "evento observado)", "acc"),
        ("Umbral Q90", "40.9", "m³/s", "Caudal de alerta de crecidas "
         "(percentil 90 de la serie observada)", "crit"),
        ("Días en alerta", f"{dias_alerta}", "días", "Días observados con "
         "caudal en o sobre el umbral (2024–2025)", "crit"),
    ]
    out = []
    for lab, val, uni, desc, estado in indicadores:
        uni_html = f"<span class='kpi-uni'>{uni}</span>" if uni else ""
        out.append(
            f"<div class='kpi kpi-{estado}' tabindex='0'>"
            f"<p class='kpi-lab'>{lab}</p>"
            f"<p class='kpi-val'>{val}{uni_html}</p>"
            f"<p class='kpi-desc'>{desc}</p>"
            f"</div>")
    return f"<div class='kpi-row'>{''.join(out)}</div>"


# ── Banda de contadores animados ("Por los números") ──────────────────────────
def banda_contadores() -> str:
    """Franja de cifras del proyecto con contadores que suben al entrar en vista
    (IntersectionObserver, ver JS_COUNTERS). El número final se escribe como
    contenido de texto para que sea correcto sin JS y bajo prefers-reduced-motion;
    la animación solo reinicia a 0 y cuenta cuando el movimiento está permitido.
    Números grandes en mono tabular + etiqueta pequeña debajo."""
    # (valor_final, sufijo, etiqueta). El sufijo no se anima (p.ej. rango de años).
    contadores = [
        (45, "", "años de datos", "1981–2025"),
        (9, "", "subcuencas", ""),
        (6, "", "estaciones", "aforo + meteo"),
        (14, "", "días de horizonte", ""),
        (4, "", "modelos comparados", ""),
    ]
    items = []
    for val, suf, lab, sub in contadores:
        sub_html = f"<span class='cnt-sub'>{sub}</span>" if sub else ""
        items.append(
            f"<div class='cnt'>"
            f"<span class='cnt-num' data-target='{val}'>{val}</span>"
            f"<span class='cnt-lab'>{lab}</span>"
            f"{sub_html}"
            f"</div>")
    return (
        "<section class='numeros reveal' aria-label='El proyecto en cifras'>"
        "<p class='eyebrow'>Por los números</p>"
        f"<div class='cnt-row'>{''.join(items)}</div>"
        "</section>")


# ── Hidrograma ambiental del hero (SVG polyline a partir de la serie real) ────
def _hero_hidrograma(serie: pd.DataFrame, w: int = 1280, h: int = 380) -> str:
    """Devuelve dos polilíneas SVG (área + línea) normalizadas a un lienzo w×h
    a partir del P50 diario observado/pronosticado. Es el fondo del hero: los
    datos como identidad visual, muy tenue."""
    s = serie.sort_values("date").reset_index(drop=True)
    y = s["p50"].to_numpy(dtype=float)
    y = np.where(np.isfinite(y), y, np.nan)
    if not np.isfinite(y).any():
        return "", ""
    ymin = float(np.nanmin(y))
    ymax = float(np.nanmax(y))
    rng = (ymax - ymin) or 1.0
    n = len(y)
    pts = []
    for i, v in enumerate(y):
        if not np.isfinite(v):
            continue
        px = w * i / max(n - 1, 1)
        # Deja aire arriba (12%) y abajo (18%) para el titular.
        py = h - (0.18 * h) - ((v - ymin) / rng) * (0.70 * h)
        pts.append((px, py))
    if len(pts) < 2:
        return "", ""
    linea = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    area = (f"0,{h:.0f} " + linea + f" {w},{h:.0f}")
    return linea, area


# ── Fuentes de datos (para la franja de logos: metadatos declarativos) ─────────
# Cada entrada: (clave_logo, alt, nombre corto, aporte). El logo se embebe como
# data URI si existe; si no, degrada a una etiqueta tipográfica.
# Atribución correcta por institución de origen (verificada):
#   · ANA      → caudal observado y red hidrométrica (SNIRH).
#   · SENAMHI / IGP → PISCOp v2.1 (precipitación) y PISCOt v1.2 (Tmax/Tmin);
#                     extensión CHIRPS-QM (2016+).
#   · ECMWF / Copernicus → ERA5-Land (humedad de suelo, evapotranspiración PET).
#   · NOAA     → índices ENSO (ONI global y Niño costero, ERSSTv5). Sin logo:
#                degrada a etiqueta tipográfica.
FUENTES_LOGOS = [
    ("logo_ana", "ANA — Autoridad Nacional del Agua",
     "ANA", "Caudal observado y red hidrométrica (SNIRH)"),
    ("logo_senamhi", "SENAMHI / IGP — Meteorología e Hidrología",
     "SENAMHI · IGP",
     "PISCOp v2.1 (precipitación) y PISCOt v1.2 (temperatura Tmax/Tmin); "
     "extensión CHIRPS-QM (2016+)"),
    ("logo_ecmwf", "ECMWF / Copernicus — Centro Europeo de Predicción",
     "ECMWF · Copernicus",
     "ERA5-Land: humedad de suelo y evapotranspiración de referencia (PET)"),
    ("logo_noaa", "NOAA — National Oceanic and Atmospheric Administration",
     "NOAA", "Índices ENSO: ONI global y Niño costero (ERSSTv5)"),
]


# Logos de la cinta (marquee) bajo el hero. Incluye UTEC (equipo) junto a las
# fuentes de datos. (clave_logo, nombre visible, alt). Si un logo falta, degrada
# a una etiqueta tipográfica (sin romper la cinta).
MARQUEE_LOGOS = [
    ("logo_ana", "ANA", "ANA — Autoridad Nacional del Agua"),
    ("logo_senamhi", "SENAMHI", "SENAMHI — Meteorología e Hidrología"),
    ("logo_ecmwf", "ECMWF · Copernicus",
     "ECMWF / Copernicus — Centro Europeo de Predicción"),
    ("logo_noaa", "NOAA",
     "NOAA — National Oceanic and Atmospheric Administration"),
    ("logo", "UTEC", "UTEC — Universidad de Ingeniería y Tecnología"),
]


def _marquee_logo_item(clave: str, nombre: str, alt: str, imgs: dict) -> str:
    """Un logo de la cinta (imagen data-URI o respaldo tipográfico)."""
    uri = imgs.get(clave)
    if uri:
        logo = (f"<img class='mq-logo' src='{uri}' alt='{alt}' "
                f"loading='lazy'>")
    else:
        logo = f"<span class='mq-logo-txt' aria-hidden='true'>{nombre}</span>"
    return f"<span class='mq-item'>{logo}</span>"


def franja_fuentes_marquee(imgs: dict) -> str:
    """Cinta «Fuentes de datos»: los logos se desplazan solos en bucle continuo
    (marquee) bajo el hero. La fila se duplica 2× para un bucle sin costura;
    máscara de desvanecimiento en los bordes; se atenúan/desaturan en reposo y
    reviven a color al pasar el cursor. Pausa en hover. Bajo
    prefers-reduced-motion queda estática y centrada (ver CSS)."""
    items = "".join(
        _marquee_logo_item(clave, nombre, alt, imgs)
        for clave, nombre, alt in MARQUEE_LOGOS)
    # Duplicado 2× (aria-hidden en la copia) → translateX(-50%) reinicia sin salto.
    grupo = f"<div class='mq-group' aria-hidden='false'>{items}</div>"
    grupo_dup = f"<div class='mq-group' aria-hidden='true'>{items}</div>"
    aria = ("Fuentes de datos: ANA, SENAMHI, ECMWF/Copernicus, NOAA, UTEC")
    return (
        "<div class='src-marquee'>"
        "<span class='src-marquee-lab'>Fuentes de datos</span>"
        f"<div class='mq-viewport' role='img' aria-label='{aria}'>"
        f"<div class='mq-track'>{grupo}{grupo_dup}</div>"
        "</div>"
        "</div>")


def franja_fuentes(imgs: dict, variante: str = "foot") -> str:
    """Franja «Fuentes de datos» con los logos + etiqueta de aporte.

    variante='foot'  → bloque para el footer (oscuro), con textos de aporte.
    variante='strip' → cinta en movimiento (marquee) bajo el hero.
    """
    if variante == "strip":
        return franja_fuentes_marquee(imgs)
    items = []
    for clave, alt, nombre, aporte in FUENTES_LOGOS:
        uri = imgs.get(clave)
        if uri:
            logo = (f"<img class='src-logo' src='{uri}' alt='{alt}' "
                    f"loading='lazy'>")
        else:
            logo = f"<span class='src-logo-txt' aria-hidden='true'>{nombre}</span>"
        items.append(
            f"<div class='src-item'>{logo}"
            f"<span class='src-aporte'>{aporte}</span></div>")
    return (
        "<div class='src-foot'>"
        "<h4>Fuentes de datos</h4>"
        f"<div class='src-foot-grid'>{''.join(items)}</div>"
        "</div>")


# ── Herramientas (stack tecnológico) — DISTINTO de las fuentes de datos ────────
# Las fuentes de datos son INSTITUCIONES (ANA/SENAMHI/…); esto es el STACK
# TÉCNICO con el que se construyó el proyecto. Se muestra estático (sin marquee):
# el movimiento ya lo aporta la cinta de fuentes. Badges con logo (Python,
# PyTorch, Google Earth Engine) + badges de texto para las que no tienen logo.
# Cada entrada de logo: (clave_logo, nombre visible, alt). Si el logo falta,
# degrada a un badge de texto (sin romper la fila).
TOOLS_LOGO = [
    ("tool_python", "Python", "Logo de Python"),
    ("tool_pytorch", "PyTorch", "Logo de PyTorch"),
    ("tool_gee", "Google Earth Engine", "Logo de Google Earth Engine"),
]
# Herramientas sin logo → badge de texto (pill tenue con acento agua).
TOOLS_TEXTO = ["Plotly", "Folium", "Pandas", "Optuna", "LightGBM"]


def franja_herramientas(imgs: dict) -> str:
    """Sección «Herramientas» (stack tecnológico): fila estática de badges.

    Badges con logo (logo + nombre) para Python, PyTorch y Google Earth Engine;
    badges de texto (pill) para Plotly, Folium, Pandas, Optuna y LightGBM.
    Claramente etiquetada como herramientas y separada de la franja de fuentes
    de datos (que son instituciones). Envuelve en móvil (flex-wrap)."""
    badges = []
    for clave, nombre, alt in TOOLS_LOGO:
        uri = imgs.get(clave)
        if uri:
            badges.append(
                f"<span class='tool-badge tool-badge-logo'>"
                f"<img class='tool-logo' src='{uri}' alt='{alt}' "
                f"loading='lazy'>"
                f"<span class='tool-name'>{nombre}</span></span>")
        else:
            # Degradación: si falta el logo, badge de texto (no rompe la fila).
            badges.append(
                f"<span class='tool-badge tool-badge-txt'>{nombre}</span>")
    for nombre in TOOLS_TEXTO:
        badges.append(
            f"<span class='tool-badge tool-badge-txt'>{nombre}</span>")
    return (
        "<div class='tools'>"
        "<h4 class='tools-eyebrow'>Herramientas</h4>"
        f"<div class='tools-row'>{''.join(badges)}</div>"
        "</div>")


# ── Ensamblado del HTML final ─────────────────────────────────────────────────
def ensamblar(mapa_html, serie_div, anim_div, tabla_html, kpi_html,
              mensual_div, evento_div, enso_div, eda_div, enso_abl_div,
              enso_callout, enso_r2_div, embed_div, imgs, meta, serie) -> str:
    est = meta["estacion"]
    area = meta["cuenca_area_km2"]
    nsub = meta["n_subcuencas"]
    contadores_html = banda_contadores()
    mapa_srcdoc = mapa_html.replace("&", "&amp;").replace('"', "&quot;")
    hidro_linea, hidro_area = _hero_hidrograma(serie)

    # Logo (header): imagen embebida si existe; si no, respaldo tipográfico.
    # Altura aumentada a 60px para dar presencia a la marca en la barra.
    if imgs.get("logo"):
        logo_html = (
            f'<img class="brand-logo" src="{imgs["logo"]}" alt="UTEC" '
            f'height="60" loading="lazy">')
        # Logo del footer: más grande (la altura efectiva la fija .foot-logo).
        logo_foot_html = (
            f'<img class="foot-logo" src="{imgs["logo"]}" alt="UTEC" '
            f'loading="lazy">')
    else:
        logo_html = '<span class="brand-logo-txt" aria-hidden="true">UTEC</span>'
        logo_foot_html = ('<span class="brand-logo-txt foot-logo-txt" '
                          'aria-hidden="true">UTEC</span>')

    strip_fuentes = franja_fuentes(imgs, "strip")
    foot_fuentes = franja_fuentes(imgs, "foot")
    herramientas_html = franja_herramientas(imgs)

    # Pestañas: (id, etiqueta). El orden define tablist y navegación.
    tabs = [
        ("resumen", "Resumen"),
        ("pronostico", "Pronóstico"),
        ("modelos", "Modelos"),
        ("clima", "Clima"),
        ("datos", "Datos & representación"),
        ("mensual", "Gestión mensual"),
    ]
    nav_tabs = "".join(
        f'<button role="tab" class="tab" id="tab-btn-{tid}" '
        f'aria-controls="tab-{tid}" aria-selected="false" tabindex="-1" '
        f'data-tab="{tid}">{lab}</button>'
        for tid, lab in tabs)

    # Integrantes: presentación que "vende" en dos bloques por tarjeta —
    #   1) fila superior: FOTO cuadrada 116px (izquierda) + identidad
    #      (nombre serif + rol + bio con gancho) al costado;
    #   2) banda inferior full-width (ocupa también bajo la foto): chips de
    #      habilidades + íconos de contacto.
    # La foto (foto_N por orden) es cuadrada, object-fit:cover, sin distorsión.
    # Los correos se abren con mailto; LinkedIn y GitHub como enlaces externos
    # (target=_blank rel=noopener). Solo SVG inline (nada de imágenes externas).
    GITHUB_REPO = "https://github.com/LuisContreras73/hidroalerta-dashboard"
    integrantes = [
        {
            "nombre": "Luis Alonzo Contreras Perez",
            "rol": "Deep Learning · Desarrollo del dashboard",
            "bio": ("Diseñó la arquitectura propia RA-TFT (transformer de "
                    "pronóstico multi-horizonte) y el sistema de alerta; "
                    "construyó el dashboard interactivo."),
            "chips": ["PyTorch", "Transformers", "Series temporales",
                      "Optuna", "Plotly"],
            "correos": ["luis.contreras@utec.edu.pe",
                        "luis.alonzo.contreras.perez@gmail.com"],
            "linkedin": "https://www.linkedin.com/in/luis-alonzo-contreras-perez",
            "github": GITHUB_REPO,
        },
        {
            "nombre": "Diego Alonso Javier Mijahuanca Quispe",
            "rol": "Desarrollo del dashboard · Análisis de datos",
            "bio": ("Desarrollo del dashboard interactivo, análisis "
                    "exploratorio y visualización de los resultados "
                    "hidroclimáticos."),
            "chips": ["Python", "EDA", "Folium", "Pandas", "Earth Engine"],
            "correos": ["diego.mijahuanca@utec.edu.pe"],
            "linkedin": ("https://www.linkedin.com/in/"
                         "diego-alonso-javier-mijahuanca-quispe-5546882aa"),
            "github": GITHUB_REPO,
        },
    ]

    def _iniciales(nombre: str) -> str:
        partes = [p for p in nombre.split() if p and p[0].isalpha()]
        if not partes:
            return "·"
        if len(partes) == 1:
            return partes[0][:2].upper()
        return (partes[0][0] + partes[-1][0]).upper()

    # Íconos de contacto en línea (SVG monocromo, heredan color vía
    # currentColor). Solo inline —sin imágenes externas—. La <svg> es
    # aria-hidden porque el <a> ya lleva aria-label descriptivo.
    ICO_MAIL = (
        "<svg viewBox='0 0 24 24' width='17' height='17' aria-hidden='true' "
        "focusable='false' fill='none' stroke='currentColor' stroke-width='1.9' "
        "stroke-linecap='round' stroke-linejoin='round'>"
        "<rect x='3' y='5' width='18' height='14' rx='2'/>"
        "<path d='M3.5 6.5l8.5 6 8.5-6'/></svg>")
    ICO_LI = (
        "<svg viewBox='0 0 24 24' width='17' height='17' aria-hidden='true' "
        "focusable='false' fill='currentColor'>"
        "<path d='M20.45 20.45h-3.55v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 "
        "1.45-2.14 2.94v5.67H9.36V9h3.41v1.56h.05c.47-.9 1.63-1.85 3.36-1.85 "
        "3.6 0 4.27 2.37 4.27 5.45v6.29zM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 "
        "2.06 0 0 1 0 4.12zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.8 0 0 "
        ".78 0 1.74v20.51C0 23.22.8 24 1.77 24h20.45c.98 0 1.78-.78 "
        "1.78-1.75V1.74C24 .78 23.2 0 22.22 0z'/></svg>")
    ICO_GH = (
        "<svg viewBox='0 0 24 24' width='17' height='17' aria-hidden='true' "
        "focusable='false' fill='currentColor'>"
        "<path d='M12 .5C5.73.5.5 5.73.5 12c0 5.08 3.29 9.39 7.86 10.91.58.1.79-.25"
        ".79-.56 0-.28-.01-1.02-.02-2-3.2.69-3.88-1.54-3.88-1.54-.52-1.33-1.28-1.68"
        "-1.28-1.68-1.05-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7"
        " 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.68 0-1.25.45"
        "-2.28 1.19-3.08-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.03 11.03"
        " 0 0 1 2.9-.39c.98 0 1.97.13 2.9.39 2.2-1.49 3.17-1.18 3.17-1.18.63 1.59"
        ".23 2.76.12 3.05.74.8 1.18 1.83 1.18 3.08 0 4.41-2.69 5.38-5.25 5.67.41.36"
        ".78 1.07.78 2.16 0 1.56-.01 2.82-.01 3.2 0 .31.21.67.8.56A11.51 11.51 0 0 0"
        " 23.5 12C23.5 5.73 18.27.5 12 .5z'/></svg>")

    def _contactos(p):
        n = p["nombre"]
        items = []
        for c in p["correos"]:
            items.append(
                f"<a class='eq-ico' href='mailto:{c}' "
                f"aria-label='Escribir a {n} ({c})'>{ICO_MAIL}</a>")
        if p.get("linkedin"):
            items.append(
                f"<a class='eq-ico' href='{p['linkedin']}' target='_blank' "
                f"rel='noopener' aria-label='LinkedIn de {n} "
                f"(abre en una pestaña nueva)'>{ICO_LI}</a>")
        if p.get("github"):
            items.append(
                f"<a class='eq-ico' href='{p['github']}' target='_blank' "
                f"rel='noopener' aria-label='GitHub del proyecto "
                f"(abre en una pestaña nueva)'>{ICO_GH}</a>")
        return f"<span class='eq-contact'>{''.join(items)}</span>"

    filas_eq = []
    for i, p in enumerate(integrantes, start=1):
        n = p["nombre"]
        foto = imgs.get(f"foto_{i}")
        if foto:
            # Contenedor cuadrado fijo (flex:0 0 auto) → la <img> lo llena con
            # object-fit:cover, sin comprimirse ni distorsionarse.
            avatar = (f"<span class='eq-foto'>"
                      f"<img class='eq-foto-img' src='{foto}' "
                      f"alt='Foto de {n}' loading='lazy'></span>")
        else:
            avatar = (f"<span class='eq-foto eq-foto-txt' aria-hidden='true'>"
                      f"{_iniciales(n)}</span>")
        # Chips de habilidades (pills sobrias, en fila que envuelve).
        chips_html = "".join(
            f"<span class='eq-chip'>{c}</span>" for c in p["chips"])
        # Estructura en dos bloques:
        #   · Fila superior (.eq-top): foto + identidad (nombre/rol/bio).
        #   · Banda inferior (.eq-band, full-width): chips + contactos.
        # La banda ocupa también bajo la foto → tarjeta equilibrada y aireada.
        filas_eq.append(
            f"<li class='eq-card'>"
            f"<div class='eq-top'>"
            f"{avatar}"
            f"<div class='eq-ident'>"
            f"<span class='eq-nombre'>{n}</span>"
            f"<span class='eq-rol'>{p['rol']}</span>"
            f"<p class='eq-bio'>{p['bio']}</p>"
            f"</div>"
            f"</div>"
            f"<div class='eq-band'>"
            f"<span class='eq-chips'>{chips_html}</span>"
            f"{_contactos(p)}"
            f"</div>"
            f"</li>")
    equipo_html = "".join(filas_eq)

    hidro_svg = (
        f'<svg class="hero-hidro" viewBox="0 0 1280 380" preserveAspectRatio="none" '
        f'aria-hidden="true" focusable="false">'
        f'<polygon class="hero-hidro-area" points="{hidro_area}"></polygon>'
        f'<polyline class="hero-hidro-line" points="{hidro_linea}"></polyline>'
        f'</svg>') if hidro_linea else ""

    return f"""
<a class="skip-link" href="#contenido">Saltar al contenido</a>

<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">
      <span class="brand-logo-wrap" title="Universidad de Ingeniería y Tecnología">
        {logo_html}
      </span>
      <span class="brand-divider" aria-hidden="true"></span>
      <span class="brand-text">
        <span class="brand-title">HidroAlerta Chancay–Huaral</span>
        <span class="brand-sub">Pronóstico de caudal y alerta de crecidas</span>
      </span>
    </div>
    <div class="status-pill" role="status" aria-label="Umbral de alerta">
      <span class="status-dot" aria-hidden="true"></span>
      <span class="status-txt">Umbral Q90</span>
      <span class="status-num">{UMBRAL_Q90} m³/s</span>
    </div>
  </div>
  <nav class="tabbar" aria-label="Secciones del reportaje">
    <div class="tabbar-inner">
      <div role="tablist" aria-label="Secciones" class="tablist">
        {nav_tabs}
      </div>
    </div>
  </nav>
</header>

<main id="contenido">

  <!-- ══ Pestaña 1 · Resumen ══════════════════════════════════════════════ -->
  <section role="tabpanel" id="tab-resumen" aria-labelledby="tab-btn-resumen"
           class="tabpanel" tabindex="0">

    <div class="hero">
      {hidro_svg}
      <div class="hero-inner">
        <p class="eyebrow eyebrow-cyan hero-rev" data-rev="1">Concurso ANA 2026 · Río Chancay–Huaral, Perú</p>
        <h1 class="hero-title hero-rev" data-rev="2">Anticipar la crecida:
          pronóstico de caudal y alerta temprana en una cuenca andino-costera.</h1>
        <p class="hero-sub hero-rev" data-rev="3">Un sistema que emite pronóstico
          probabilístico de caudal de forma continua sobre la estación de aforo
          {est['nombre']} y verifica su habilidad frente al aforo observado, con la
          mira puesta en detectar crecidas con días de anticipación.</p>
      </div>
      {strip_fuentes}
    </div>

    <div class="tab-body">
      <section class="reveal" aria-label="Indicadores resumen">
        <p class="eyebrow">Cifras clave · periodo de prueba 2024–2025</p>
        {kpi_html}
      </section>

      <section class="split reveal">
        <div class="split-main">
          <div class="mapa-box">
            <iframe title="Mapa interactivo de la cuenca Chancay–Huaral"
                    class="mapa-iframe" srcdoc="{mapa_srcdoc}" loading="lazy"></iframe>
          </div>
        </div>
        <aside class="split-aside">
          <p class="eyebrow">01 · Cuenca y estación</p>
          <h2 class="h-serif">La cuenca, de la costa a la cabecera andina</h2>
          <p class="prose">Las {nsub} subcuencas se colorean por elevación, del
          litoral (cian) a la cabecera de más de 4 500 m (azul profundo). La
          estación {est['nombre']} (código {est['codigo']}) marca la salida de una
          cuenca de {area:,.0f} km².</p>
          <p class="prose">Active las capas del mapa (satélite, callejero) y
          consulte cada subcuenca para ver su elevación y área.</p>
        </aside>
      </section>

      <section class="thesis reveal">
        <p class="eyebrow">La tesis</p>
        <p class="thesis-body">A un día de horizonte, la <b>persistencia</b> del
        caudal fija un techo de exactitud difícil de superar; el modelo propuesto
        lo iguala y mejora la calidad probabilística. El valor real aparece a
        <b>varios días</b>, donde los forzantes meteorológicos permiten sostener la
        habilidad y anticipar crecidas —el margen que da la respuesta hidrológica
        de la cuenca, de unos cuatro días entre lluvia y caudal.</p>
      </section>

      {contadores_html}
    </div>
  </section>

  <!-- ══ Pestaña 2 · Pronóstico ═══════════════════════════════════════════ -->
  <section role="tabpanel" id="tab-pronostico" aria-labelledby="tab-btn-pronostico"
           class="tabpanel" tabindex="0" hidden>
    <div class="tab-body">
      <header class="tab-head reveal">
        <p class="eyebrow">Pronóstico operacional</p>
        <h2 class="h-serif">Serie de caudal: observado frente a pronóstico</h2>
        <p class="prose prose-wide">Elija el <b>modelo</b> y el <b>horizonte</b>:
        el gráfico muestra la mediana P50 y la banda de incertidumbre P10–P90 para
        2024–2025. Los puntos son el caudal observado, solo donde hay aforo; los
        tramos sombreados señalan periodos sin observación, durante los cuales el
        pronóstico continúa (valor operacional). La línea punteada roja es el
        umbral de alerta. HydroST solo dispone de horizonte a 1 día; Persistencia
        es un baseline puntual (sin banda).</p>
      </header>
      <div class="reveal">{serie_div}</div>

      <section class="split split-flip reveal">
        <div class="split-main">{evento_div}</div>
        <aside class="split-aside">
          <p class="eyebrow">Zoom · febrero 2024</p>
          <h2 class="h-serif">El pico de crecida, de cerca</h2>
          <p class="prose">Enero a marzo de 2024: la temporada húmeda con el pico
          más marcado del periodo de prueba. Se superponen el caudal observado y la
          mediana de cada modelo para comparar quién sigue el pico.</p>
          <p class="prose">Alterne entre 1 y 7 días con los botones: a un día el
          seguimiento es estrecho; a siete, la anticipación depende de la lluvia
          pronosticada y las trazas se separan del observado.</p>
          <p class="nota">Línea gruesa (agua): modelo propuesto RA-TFT; las demás,
          de referencia. Punteada roja: umbral Q90.</p>
        </aside>
      </section>
    </div>
  </section>

  <!-- ══ Pestaña 3 · Modelos ══════════════════════════════════════════════ -->
  <section role="tabpanel" id="tab-modelos" aria-labelledby="tab-btn-modelos"
           class="tabpanel" tabindex="0" hidden>
    <div class="tab-body">
      <header class="tab-head reveal">
        <p class="eyebrow">Evaluación comparativa</p>
        <h2 class="h-serif">Habilidad predictiva según el horizonte</h2>
        <p class="prose prose-wide">Eficiencia (NSE) de cada modelo al aumentar el
        horizonte. Mueva el deslizador o pulse reproducir: la Persistencia (naive)
        parte alta a 1 día pero decae con rapidez, mientras que el modelo propuesto
        sostiene mejor la habilidad a varios días.</p>
      </header>
      <div class="reveal">{anim_div}</div>
      <p class="nota reveal">Barras de NSE por modelo; la línea base en cero indica
      ausencia de habilidad respecto a la media. HydroST solo se evalúa a 2 días de
      horizonte, por lo que aparece únicamente en ese paso.</p>

      <header class="tab-head tab-head-sep reveal">
        <p class="eyebrow">02 · Métricas</p>
        <h2 class="h-serif">Métricas por horizonte</h2>
        <p class="prose prose-wide">Exactitud (NSE, KGE, MAE), calidad
        probabilística (CRPS) y capacidad de alerta (CSI, POD, FAR) para horizontes
        de 1 a 14 días.</p>
      </header>
      <div class="reveal">{tabla_html}</div>

      <section class="conc-grid reveal">
        <div class="conc-col">
          <h3 class="conc-h conc-ok">Lo que aporta</h3>
          <ul class="conc-list">
            <li>La persistencia fija el techo de exactitud a 1 día; el modelo
            propuesto lo iguala en NSE y mejora la calidad probabilística (CRPS).</li>
            <li>A multi-día, los forzantes meteorológicos aportan valor: el modelo
            propuesto sostiene mejor la habilidad conforme crece el horizonte.</li>
            <li>El pronóstico se mantiene continuo aunque falte aforo, lo que da
            valor operacional para vigilancia permanente.</li>
          </ul>
        </div>
        <div class="conc-col">
          <h3 class="conc-h conc-warn">Limitaciones</h3>
          <ul class="conc-list">
            <li>La alerta de crecidas a más de 2 días depende de la lluvia
            pronosticada; sin ella, la anticipación fiable es limitada.</li>
            <li>La serie 2025 presenta amplios vacíos de aforo, que reducen los
            eventos disponibles para verificar la detección de crecidas.</li>
            <li>La evaluación cubre un año de prueba independiente; conviene ampliar
            el periodo para consolidar las métricas de alerta.</li>
          </ul>
        </div>
      </section>
    </div>
  </section>

  <!-- ══ Pestaña 4 · Clima (ENSO + ablación) ══════════════════════════════ -->
  <section role="tabpanel" id="tab-clima" aria-labelledby="tab-btn-clima"
           class="tabpanel" tabindex="0" hidden>
    <div class="tab-body">
      <header class="tab-head reveal">
        <p class="eyebrow">Contexto climático · El Niño</p>
        <h2 class="h-serif">Señal ENSO: Niño costero frente a ONI global</h2>
        <p class="prose prose-wide">Índices de El Niño–Oscilación del Sur relevantes
        para la cuenca: el <b>Niño costero</b> (anomalía frente a la costa peruana) y
        el <b>ONI global</b> (región Niño 3.4, Pacífico central). Su efecto sobre el
        caudal es de <b>signo opuesto</b>: un Niño costero cálido intensifica la
        lluvia en la vertiente occidental (más caudal), mientras que un ONI global
        cálido tiende a secar la sierra que alimenta la cabecera (menos caudal).</p>
      </header>
      <div class="reveal">{enso_div}</div>
      <p class="nota reveal">Anomalías mensuales (°C). La banda gris central marca el
      rango neutro (±0,5 °C); por encima, condición cálida (El Niño) y por debajo,
      fría (La Niña). El pico costero de 2017 y el evento 2023–2024 ilustran
      episodios de fuerte impacto local.</p>

      <header class="tab-head tab-head-sep reveal">
        <p class="eyebrow">Ablación · aporte de los índices</p>
        <h2 class="h-serif">¿Cuánto aporta cada índice ENSO al modelo?</h2>
        <p class="prose prose-wide">Eficiencia (NSE) de validación al añadir cada
        índice como forzante. La ganancia es pequeña pero consistente y máxima con
        <b>ambos índices</b>; el eje se enfoca en el rango 0,66–0,70 para apreciar la
        diferencia.</p>
      </header>
      <section class="split split-flip reveal">
        <div class="split-main">{enso_abl_div}</div>
        {enso_callout}
      </section>
      <p class="nota reveal">NSE por configuración de forzantes. Barra resaltada
      (agua): <b>+ Ambos índices</b> (NSE = 0,691), la mejor. Las demás, en gris frío.
      La aparente redundancia entre índices esconde una supresión mutua: por separado
      su efecto casi se cancela; juntos, la señal se refuerza.</p>

      <section class="split reveal">
        <div class="split-main">{enso_r2_div}</div>
        <aside class="split-aside">
          <p class="eyebrow">Correlación entre índices</p>
          <h2 class="h-serif">Niño costero frente a ONI global</h2>
          <p class="prose">Cada punto es un mes: el Niño costero (eje X) frente al
          ONI global (eje Y). La recta de regresión y el coeficiente
          <b>R² = 0,39 (r = 0,625)</b> cuantifican cuánto <b>comparten</b> ambos
          índices.</p>
          <p class="prose">Comparten menos de la mitad de su varianza: por eso
          <b>no</b> son redundantes. Añadido a su efecto de signo opuesto sobre el
          caudal, esto explica por qué usar <b>ambos</b> índices supera a cualquiera
          por separado.</p>
        </aside>
      </section>
    </div>
  </section>

  <!-- ══ Pestaña 5 · Datos & representación (EDA + embeddings) ═════════════ -->
  <section role="tabpanel" id="tab-datos" aria-labelledby="tab-btn-datos"
           class="tabpanel" tabindex="0" hidden>
    <div class="tab-body">
      <header class="tab-head reveal">
        <p class="eyebrow">Análisis exploratorio</p>
        <h2 class="h-serif">Memoria y tiempo de respuesta</h2>
        <p class="prose prose-wide">Dos correlogramas que sustentan el diseño del
        modelo. La <b>autocorrelación (ACF)</b> del caudal mide su memoria propia; la
        <b>correlación cruzada (CCF)</b> lluvia→caudal mide cuánto tarda la
        precipitación en traducirse en escorrentía a la salida de la cuenca.</p>
      </header>
      <div class="reveal">{eda_div}</div>
      <p class="nota reveal">La ACF cae muy despacio y el <b>lag-1 ≈ 0,99</b>: el
      caudal de hoy explica casi por completo el de mañana, lo que sustenta la fuerte
      persistencia y el techo del baseline a 1 día. La CCF alcanza su máximo hacia el
      <b>lag ≈ 4 días</b>, una estimación del tiempo de concentración de la cuenca:
      la lluvia se refleja en el caudal con unos días de retardo, margen que habilita
      la alerta temprana.</p>

      <header class="tab-head tab-head-sep reveal">
        <p class="eyebrow">Representación · embeddings</p>
        <h2 class="h-serif">La estructura de regímenes es intrínseca a los datos</h2>
        <p class="prose prose-wide">Análisis no supervisado (independiente del modelo)
        que muestra que la estructura de regímenes (crecida vs base) es intrínseca a
        los datos; los métodos que respetan la forma temporal (DTW) y la no-linealidad
        (Isomap) la separan mejor.</p>
      </header>
      <div class="reveal">{embed_div}</div>
    </div>
  </section>

  <!-- ══ Pestaña 6 · Gestión mensual ══════════════════════════════════════ -->
  <section role="tabpanel" id="tab-mensual" aria-labelledby="tab-btn-mensual"
           class="tabpanel" tabindex="0" hidden>
    <div class="tab-body">
      <header class="tab-head reveal">
        <p class="eyebrow">Producto de gestión</p>
        <h2 class="h-serif">Disponibilidad hídrica a escala mensual</h2>
        <p class="prose prose-wide">Producto de gestión complementario a la alerta
        diaria de crecidas: caudal medio mensual observado frente al pronóstico (P50
        y banda P10–P90) y la climatología estacional. El techo de habilidad a esta
        escala lo fija la climatología (la marcada estacionalidad de la cuenca); el
        modelo aporta valor sobre todo en las anomalías, cuando el año se aparta del
        régimen típico.</p>
      </header>
      <div class="reveal">{mensual_div}</div>
      <p class="nota reveal">Serie mensual 2021–2026. Los círculos abiertos son el
      caudal medio mensual observado; la línea discontinua gris es la climatología
      (media del mes). Meses sin observación quedan como pronóstico activo.</p>
    </div>
  </section>

</main>

<div class="foot-transition" aria-hidden="true"></div>
<footer class="foot">
  <div class="foot-inner">
    <div class="foot-col foot-col-eq">
      <h4 class="foot-h">Equipo</h4>
      <ul class="equipo">{equipo_html}</ul>
    </div>
    <div class="foot-col foot-col-src">
      {foot_fuentes}
      <ul class="fuentes">
        <li><span class="fu-k">Caudal observado</span>
          <span class="fu-v">ANA — caudal observado y red hidrométrica (SNIRH);
          estación {est['nombre']}, código {est['codigo']}.</span></li>
        <li><span class="fu-k">Precipitación y temperatura</span>
          <span class="fu-v">SENAMHI / IGP — <b>PISCOp v2.1</b> (precipitación) y
          <b>PISCOt v1.2</b> (temperatura Tmax/Tmin); extensión CHIRPS-QM
          (2016+).</span></li>
        <li><span class="fu-k">Humedad de suelo y PET</span>
          <span class="fu-v">ECMWF / Copernicus — ERA5-Land (humedad de suelo,
          evapotranspiración de referencia PET).</span></li>
        <li><span class="fu-k">Índices ENSO</span>
          <span class="fu-v">NOAA — ONI global y Niño costero (ERSSTv5).</span></li>
        <li><span class="fu-k">Satélite (Google Earth Engine)</span>
          <span class="fu-v"><b>MODIS y Landsat</b> (índices de vegetación/nieve y
          agua) usados por <b>HydroST</b>; Sentinel-1/2 y SMAP evaluados pero
          descartados por cobertura insuficiente.</span></li>
      </ul>
    </div>
    <div class="foot-col foot-col-about">
      <h4 class="foot-h">Sobre el proyecto</h4>
      <p class="foot-p">HidroAlerta Chancay–Huaral integra modelos de aprendizaje
      automático con hidrología de la cuenca para anticipar crecidas y apoyar la
      gestión del riesgo. Presentado al <b>Concurso ANA 2026</b>.</p>
      {herramientas_html}
    </div>
    <div class="foot-col foot-col-lic">
      <h4 class="foot-h">Licencia</h4>
      <p class="foot-p">Reportaje científico de acceso público con fines de
      investigación y difusión. La metodología completa está en una publicación
      en preparación y no se incluye aquí.</p>
      <p class="foot-meta">Actualizado el {FECHA_ACTUALIZACION}.</p>
    </div>
  </div>
  <div class="foot-bar">
    <p class="copyright">Todos los derechos reservados © 2026 — Equipo
      HidroAlerta Chancay–Huaral.</p>
    <a class="foot-logo-wrap"
       href="https://utec.edu.pe" target="_blank" rel="noopener"
       aria-label="Universidad de Ingeniería y Tecnología (UTEC), abre en una pestaña nueva">
      {logo_foot_html}
    </a>
  </div>
</footer>
"""


# ── CSS ────────────────────────────────────────────────────────────────────────
def estilos() -> str:
    return f"""
:root {{
  --bg:{COL_BG}; --surf:{COL_SURF}; --ink:{COL_INK}; --border:{COL_BORDER};
  --accent:{COL_ACCENT}; --deep:{COL_DEEP}; --cyan:{COL_CYAN};
  --crit:{COL_CRIT}; --ok:{COL_OK}; --warn:{COL_WARN}; --muted:{COL_MUTED};
  --serif:'Source Serif 4',Georgia,'Times New Roman',serif;
  --sans:'IBM Plex Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --mono:'IBM Plex Mono','SFMono-Regular',Consolas,monospace;
  --shadow-sm:0 1px 2px rgba(12,30,42,.04);
  --shadow:0 1px 2px rgba(12,30,42,.04),0 6px 22px rgba(12,30,42,.05);
  --radius:10px;
  --maxw:1240px;
  --pad-x:clamp(20px,5vw,48px);
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:var(--sans); line-height:1.62; font-size:16px;
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
  overflow-x:hidden;
}}
h1,h2,h3,h4 {{ margin:0; line-height:1.15; text-wrap:balance; color:var(--ink); }}
p {{ margin:0; }}
b {{ font-weight:600; }}
.mono {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}
.h-serif {{ font-family:var(--serif); font-weight:500; font-size:clamp(1.3rem,2.4vw,1.75rem);
  letter-spacing:-.01em; color:var(--ink); }}

.skip-link {{
  position:absolute; left:-9999px; top:0; z-index:1000; background:var(--deep);
  color:#fff; padding:10px 16px; border-radius:0 0 8px 0; font-size:14px;
}}
.skip-link:focus {{ left:0; }}

/* ── Eyebrows (mayúsculas con tracking) ───────────────────────────── */
.eyebrow {{ text-transform:uppercase; letter-spacing:.13em; font-size:11.5px;
  font-weight:600; color:var(--accent); margin:0 0 12px; }}
.eyebrow-cyan {{ color:var(--cyan); }}

/* ── Barra superior sticky (marca + estado) ───────────────────────── */
.topbar {{
  position:sticky; top:0; z-index:60; background:rgba(247,249,251,.86);
  backdrop-filter:saturate(150%) blur(10px);
  -webkit-backdrop-filter:saturate(150%) blur(10px);
  border-bottom:1px solid var(--border);
}}
.topbar-inner {{
  max-width:var(--maxw); margin:0 auto; padding:9px var(--pad-x) 8px;
  display:flex; align-items:center; justify-content:space-between; gap:16px;
}}
.brand {{ display:flex; align-items:center; gap:14px; min-width:0; }}
.brand-logo-wrap {{ display:inline-flex; align-items:center; flex:none; }}
.brand-logo {{ display:block; height:60px; width:auto; }}
.brand-logo-txt {{ font-family:var(--mono); font-weight:600; font-size:15px;
  letter-spacing:.06em; color:var(--deep); border:1.5px solid var(--border);
  border-radius:8px; padding:7px 12px; line-height:1; }}
.brand-divider {{ width:1px; height:40px; background:var(--border); flex:none; }}
.brand-text {{ display:flex; flex-direction:column; line-height:1.25; min-width:0; }}
.brand-title {{ font-family:var(--serif); font-weight:600; font-size:16.5px;
  letter-spacing:-.01em; color:var(--ink); }}
.brand-sub {{ font-size:12px; color:var(--muted);
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.status-pill {{
  display:inline-flex; align-items:center; gap:8px; flex:none;
  background:#FBEEEC; border:1px solid #F0CFC9; color:var(--crit);
  padding:6px 13px; border-radius:999px; font-size:12.5px; font-weight:500;
}}
.status-dot {{ width:8px; height:8px; border-radius:50%; background:var(--crit);
  box-shadow:0 0 0 3px rgba(192,57,43,.16); }}
.status-txt {{ text-transform:uppercase; letter-spacing:.06em; font-size:11px;
  font-weight:600; }}
.status-num {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-weight:600; }}

/* ── Barra de pestañas (tablist) ──────────────────────────────────── */
.tabbar {{ border-top:1px solid rgba(226,232,238,.6);
  background:rgba(247,249,251,.72); }}
.tabbar-inner {{ max-width:var(--maxw); margin:0 auto; padding:0 var(--pad-x);
  overflow-x:auto; scrollbar-width:none; }}
.tabbar-inner::-webkit-scrollbar {{ display:none; }}
.tablist {{ display:flex; gap:4px; }}
.tab {{
  appearance:none; border:0; background:transparent; cursor:pointer;
  font-family:var(--sans); font-size:14px; font-weight:500; color:var(--muted);
  padding:14px 6px 13px; margin:0 12px 0 0; position:relative; white-space:nowrap;
  letter-spacing:.005em; transition:color .18s ease;
}}
.tab:first-child {{ margin-left:0; }}
.tab::after {{ content:""; position:absolute; left:0; right:0; bottom:-1px;
  height:2px; background:var(--cyan); transform:scaleX(0); transform-origin:left;
  transition:transform .22s cubic-bezier(.4,0,.2,1); border-radius:2px 2px 0 0; }}
.tab:hover {{ color:var(--ink); }}
.tab[aria-selected="true"] {{ color:var(--ink); font-weight:600; }}
.tab[aria-selected="true"]::after {{ transform:scaleX(1); }}
.tab:focus-visible {{ outline:2px solid var(--accent); outline-offset:-3px;
  border-radius:4px; }}

/* ── Paneles de pestaña ───────────────────────────────────────────── */
main {{ display:block; }}
.tabpanel[hidden] {{ display:none; }}
.tabpanel {{ animation:panelIn .28s cubic-bezier(.4,0,.2,1) both; }}
.tabpanel:focus {{ outline:none; }}
@keyframes panelIn {{ from {{ opacity:0; transform:translateY(8px); }}
  to {{ opacity:1; transform:none; }} }}
.tab-body {{ max-width:var(--maxw); margin:0 auto;
  padding:clamp(28px,4vw,52px) var(--pad-x) 40px;
  display:flex; flex-direction:column; gap:clamp(30px,4.4vw,56px); }}

/* ── Hero (full-bleed, Resumen) ───────────────────────────────────── */
.hero {{ position:relative; overflow:hidden; isolation:isolate;
  background:
    radial-gradient(120% 140% at 82% -10%, rgba(27,168,196,.16), transparent 55%),
    linear-gradient(180deg,#FFFFFF 0%,#F1F6F9 62%,var(--bg) 100%);
  border-bottom:1px solid var(--border); }}
.hero-inner {{ max-width:var(--maxw); margin:0 auto;
  padding:clamp(40px,6vw,88px) var(--pad-x) clamp(44px,6vw,84px);
  position:relative; z-index:2; }}
.hero-hidro {{ position:absolute; left:0; right:0; bottom:0; width:100%;
  height:62%; z-index:1; pointer-events:none; }}
.hero-hidro-area {{ fill:rgba(11,110,140,.06); }}
.hero-hidro-line {{ fill:none; stroke:rgba(11,110,140,.30); stroke-width:1.4;
  vector-effect:non-scaling-stroke; }}
.hero-title {{ font-family:var(--serif); font-weight:600;
  font-size:clamp(2rem,4.6vw,3.35rem); line-height:1.08; letter-spacing:-.02em;
  max-width:19ch; color:var(--ink); }}
.hero-sub {{ font-size:clamp(15px,1.5vw,18px); color:var(--muted);
  margin-top:20px; max-width:60ch; line-height:1.62; }}

/* ── KPIs editoriales (números mono, hairlines, sin cajas) ────────── */
.kpi-row {{ display:flex; flex-wrap:wrap; gap:0 clamp(20px,3vw,40px);
  border-top:1px solid var(--border); border-bottom:1px solid var(--border); }}
.kpi {{ flex:1 1 150px; min-width:140px; padding:22px 0 20px; position:relative; }}
.kpi + .kpi::before {{ content:""; position:absolute; left:clamp(-20px,-1.5vw,-20px);
  top:22px; bottom:20px; width:1px; background:var(--border); }}
.kpi-lab {{ font-family:var(--sans); font-size:11px; font-weight:600;
  text-transform:uppercase; letter-spacing:.09em; color:var(--muted); }}
.kpi-val {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:clamp(2.1rem,3.4vw,2.75rem); font-weight:500; color:var(--deep);
  line-height:1.05; margin-top:10px; letter-spacing:-.03em; }}
.kpi-crit .kpi-val {{ color:var(--crit); }}
.kpi-uni {{ font-family:var(--sans); font-size:.9rem; font-weight:500;
  color:var(--muted); margin-left:5px; letter-spacing:0; }}
.kpi-desc {{ font-size:12px; color:var(--muted); margin-top:11px; line-height:1.5;
  max-width:26ch; }}
.kpi:focus-visible {{ outline:2px solid var(--accent); outline-offset:4px;
  border-radius:4px; }}

/* ── Banda de contadores animados ("Por los números") ─────────────── */
.numeros {{ border-top:1px solid var(--border);
  padding-top:clamp(24px,3vw,36px); }}
.cnt-row {{ display:flex; flex-wrap:wrap; gap:clamp(20px,3vw,40px);
  margin-top:6px; }}
.cnt {{ flex:1 1 120px; min-width:110px; display:flex; flex-direction:column;
  gap:5px; }}
.cnt-num {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:clamp(2.4rem,4.2vw,3.4rem); font-weight:500; color:var(--deep);
  line-height:1; letter-spacing:-.03em; }}
.cnt-lab {{ font-family:var(--sans); font-size:12.5px; font-weight:600;
  color:var(--ink); line-height:1.35; }}
.cnt-sub {{ font-size:11.5px; color:var(--muted); line-height:1.35; }}

/* ── Paneles asimétricos (gráfico dominante + notas) ──────────────── */
.split {{ display:grid; grid-template-columns:minmax(0,1.62fr) minmax(0,1fr);
  gap:clamp(24px,3vw,44px); align-items:start; }}
/* min-width:0 permite que la columna del gráfico se encoja por debajo del
   ancho intrínseco del Plotly (que, dibujado oculto, arranca ~700px). */
.split-main {{ min-width:0; grid-column:1; }}
.split-aside {{ position:relative; padding-left:22px; min-width:0; grid-column:2; }}
/* Variante espejo: aside a la izquierda (estrecha), gráfico a la derecha
   (ancha). Se asignan por columna explícita, no con order (order reordena la
   colocación automática del grid y mandaría el gráfico a la pista estrecha). */
.split-flip {{ grid-template-columns:minmax(0,1fr) minmax(0,1.62fr); }}
.split-flip .split-main {{ grid-column:2; }}
.split-flip .split-aside {{ grid-column:1; padding-left:0; padding-right:22px; }}
.split-flip .split-aside::before {{ left:auto; right:0; }}
.split-aside::before {{ content:""; position:absolute; left:0; top:4px; bottom:4px;
  width:2px; background:linear-gradient(180deg,var(--cyan),var(--accent));
  border-radius:2px; }}
.split-aside .h-serif {{ margin-bottom:12px; }}

/* ── Encabezado de sección dentro de pestaña ──────────────────────── */
.tab-head {{ max-width:none; }}
.tab-head .h-serif {{ margin-bottom:12px; }}
.tab-head-sep {{ padding-top:clamp(20px,3vw,36px);
  border-top:1px solid var(--border); }}

/* ── Prosa ────────────────────────────────────────────────────────── */
.prose {{ color:var(--muted); font-size:15px; line-height:1.66; max-width:62ch;
  margin-top:12px; }}
.prose + .prose {{ margin-top:14px; }}
.prose-wide {{ max-width:86ch; }}
.prose b {{ color:var(--ink); }}
.nota {{ font-size:12.5px; color:var(--muted); margin-top:14px; max-width:94ch;
  line-height:1.6; }}
.nota b {{ color:var(--ink); font-weight:600; }}

/* ── Tesis (bloque destacado) ─────────────────────────────────────── */
.thesis {{ border-top:1px solid var(--border); padding-top:clamp(24px,3vw,36px); }}
.thesis-body {{ font-family:var(--serif); font-weight:400;
  font-size:clamp(1.15rem,2vw,1.5rem); line-height:1.5; color:var(--ink);
  max-width:44ch; }}
.thesis-body b {{ font-weight:600; color:var(--deep); }}

/* ── Mapa ─────────────────────────────────────────────────────────── */
.mapa-box {{ border-radius:var(--radius); overflow:hidden;
  border:1px solid var(--border); box-shadow:var(--shadow-sm); }}
.mapa-iframe {{ width:100%; height:min(600px,64vh); border:0; display:block; }}

/* ── Serie de pronóstico interactiva (selectores) ─────────────────── */
.fc-controls {{ display:flex; flex-wrap:wrap; align-items:flex-end; gap:18px;
  margin-bottom:18px; padding:16px 18px; background:var(--surf);
  border:1px solid var(--border); border-radius:var(--radius);
  box-shadow:var(--shadow-sm); }}
.fc-field {{ display:flex; flex-direction:column; gap:6px; }}
.fc-field-lab {{ font-size:11px; font-weight:600; text-transform:uppercase;
  letter-spacing:.08em; color:var(--muted); }}
.fc-select {{
  appearance:none; -webkit-appearance:none; font-family:var(--sans);
  font-size:14px; font-weight:500; color:var(--ink); background:var(--surf);
  border:1.5px solid var(--border); border-radius:8px; padding:9px 34px 9px 13px;
  min-width:180px; cursor:pointer; line-height:1.3;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%235B6B78' d='M1 1l5 5 5-5'/%3E%3C/svg%3E");
  background-repeat:no-repeat; background-position:right 12px center;
  transition:border-color .16s ease, box-shadow .16s ease;
}}
.fc-select:hover {{ border-color:#B4C4CE; }}
.fc-select:focus-visible {{ outline:none; border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(11,110,140,.18); }}
.fc-select:disabled {{ opacity:.5; cursor:not-allowed; }}
.fc-readout {{ display:flex; flex-direction:column; gap:3px; margin-left:auto;
  text-align:right; }}
.fc-readout-lab {{ font-size:11px; font-weight:600; text-transform:uppercase;
  letter-spacing:.06em; color:var(--muted); }}
.fc-readout-val {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:1.6rem; font-weight:600; color:var(--deep); line-height:1.1; }}
.fc-plot {{ width:100%; min-height:460px; }}

/* ── Gráficos Plotly: sobre superficie con hairline ───────────────── */
.js-plotly-plot {{ background:var(--surf); border:1px solid var(--border);
  border-radius:var(--radius); box-shadow:var(--shadow-sm);
  padding:14px 12px 8px; max-width:100%; }}
#grafico-serie.fc-plot {{ background:var(--surf); border:1px solid var(--border);
  border-radius:var(--radius); box-shadow:var(--shadow-sm); padding:6px 8px; }}
#grafico-embeddings.emb-plot {{ background:var(--surf);
  border:1px solid var(--border); border-radius:var(--radius);
  box-shadow:var(--shadow-sm); padding:6px 8px; }}

/* ── Tabla de métricas (editorial) ────────────────────────────────── */
.tabla-scroll {{ overflow-x:auto; border:1px solid var(--border);
  border-radius:var(--radius); box-shadow:var(--shadow-sm); background:var(--surf); }}
table.metricas {{ width:100%; border-collapse:collapse; font-size:13.5px;
  min-width:700px; }}
table.metricas th {{ background:var(--deep); color:#EAF3F6; padding:11px 13px;
  text-align:right; font-weight:600; font-size:11.5px; letter-spacing:.05em;
  text-transform:uppercase; position:sticky; top:0; white-space:nowrap; }}
table.metricas th:nth-child(1), table.metricas th:nth-child(2) {{ text-align:left; }}
table.metricas td {{ padding:10px 13px; border-bottom:1px solid #EDF1F5; }}
table.metricas tbody tr:last-child td {{ border-bottom:0; }}
table.metricas tbody tr:hover td {{ background:#F5F9FB; }}
table.metricas td.num {{ text-align:right; font-family:var(--mono);
  font-variant-numeric:tabular-nums; color:#33424E; }}
table.metricas td.modelo {{ font-weight:500; white-space:nowrap; }}
table.metricas td.modelo-prop {{ font-weight:700; color:var(--accent); }}
table.metricas td.modelo-base {{ color:var(--muted); }}
table.metricas td.lead-cell {{ background:#F3F8FA; vertical-align:middle;
  border-right:1px solid var(--border); white-space:nowrap; }}
.lead-lab {{ display:block; font-weight:600; color:var(--deep);
  font-family:var(--serif); }}
.lead-n {{ display:block; font-family:var(--mono); font-size:11px;
  color:var(--muted); margin-top:2px; }}
td.chip-best {{ position:relative; color:var(--ok); font-weight:700; }}
td.chip-best::after {{ content:""; position:absolute; inset:4px 6px;
  background:rgba(46,139,111,.10); border:1px solid rgba(46,139,111,.32);
  border-radius:6px; z-index:0; }}

/* ── Conclusiones ─────────────────────────────────────────────────── */
.conc-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:clamp(24px,3vw,44px); }}
.conc-h {{ font-size:12px; text-transform:uppercase; letter-spacing:.07em;
  font-weight:700; padding-bottom:9px; margin-bottom:12px;
  border-bottom:2px solid var(--border); }}
.conc-ok {{ color:var(--ok); border-color:rgba(46,139,111,.35); }}
.conc-warn {{ color:var(--warn); border-color:rgba(214,137,16,.35); }}
.conc-list {{ margin:0; padding-left:1.15em; display:flex; flex-direction:column;
  gap:11px; }}
.conc-list li {{ font-size:14px; color:#33424E; line-height:1.55; }}

/* ── Footer (transición suave papel → tinta profunda, estilo corporativo) ── */
/* Franja de transición: degradado del papel al tono del footer, sin corte. */
.foot-transition {{ height:clamp(72px,9vw,132px);
  background:linear-gradient(180deg,var(--bg) 0%,#EAF1F5 24%,
    #6E8895 62%,#123a4e 100%);
  margin-bottom:-1px; }}
.foot {{ position:relative; color:#C7D5DD;
  background:linear-gradient(180deg,#123a4e 0%,#0C3346 34%,#082431 100%); }}
.foot-inner {{ max-width:var(--maxw); margin:0 auto;
  padding:clamp(40px,4.6vw,60px) var(--pad-x) clamp(30px,3.4vw,42px);
  display:grid;
  grid-template-columns:1.7fr 1.3fr 1fr 1fr; gap:clamp(26px,3vw,44px);
  align-items:start; }}
/* Encabezados de columna: serif editorial con hairline inferior. */
.foot-h {{ font-family:var(--serif); font-weight:600; color:#EAF3F6;
  font-size:15px; letter-spacing:.01em; margin:0 0 18px;
  padding-bottom:11px; position:relative; }}
.foot-h::after {{ content:""; position:absolute; left:0; bottom:0;
  width:34px; height:2px; border-radius:2px;
  background:linear-gradient(90deg,var(--cyan),var(--accent)); }}
/* Equipo: tarjetas en DOS bloques para que respiren —
   · Fila superior (.eq-top): foto CUADRADA fija (flex:0 0 auto) + identidad
     (nombre serif + rol + bio con gancho). Solo estos dos bloques van al lado
     de la foto.
   · Banda inferior (.eq-band): full-width (ocupa también bajo la foto) con los
     chips de habilidades a la izquierda y los íconos de contacto a la derecha,
     separada por un hairline tenue.
   Micro-interacción de elevación al hover (respeta prefers-reduced-motion). */
.equipo {{ list-style:none; padding:0; margin:0; display:flex;
  flex-direction:column; gap:16px; }}
.eq-card {{ display:flex; flex-direction:column; gap:16px;
  padding:22px 24px; border-radius:14px;
  background:rgba(255,255,255,.035); border:1px solid rgba(255,255,255,.08);
  transition:background .2s ease, border-color .2s ease, transform .2s ease,
    box-shadow .2s ease; }}
.eq-card:hover {{ background:rgba(255,255,255,.07);
  border-color:rgba(27,168,196,.4); transform:translateY(-3px);
  box-shadow:0 12px 30px rgba(0,0,0,.32); }}
/* Fila superior: foto + identidad, al costado. */
.eq-top {{ display:flex; align-items:flex-start; gap:20px; }}
/* Contenedor CUADRADO fijo: NUNCA se comprime ni se estira (flex:0 0 auto +
   aspect-ratio de refuerzo) → la foto no se distorsiona. */
.eq-foto {{ flex:0 0 auto; width:116px; height:116px; aspect-ratio:1/1;
  border-radius:12px; overflow:hidden; position:relative;
  display:inline-flex; align-items:center; justify-content:center;
  background:#0E3345; box-shadow:0 6px 20px rgba(0,0,0,.34);
  outline:2px solid rgba(27,168,196,.45); outline-offset:3px;
  border:3px solid #123a4e; transition:outline-color .2s ease; }}
.eq-card:hover .eq-foto {{ outline-color:rgba(27,168,196,.75); }}
/* La imagen llena el contenedor cuadrado sin deformarse. */
.eq-foto-img {{ width:100%; height:100%; object-fit:cover;
  object-position:center; display:block; }}
.eq-foto-txt {{ font-family:var(--mono); font-weight:600;
  font-size:clamp(28px,3vw,36px); color:var(--cyan); letter-spacing:.02em; }}
/* Identidad (nombre/rol/bio): flex:1 + min-width:0 para que respire. */
.eq-ident {{ flex:1 1 auto; display:flex; flex-direction:column; min-width:0;
  gap:5px; }}
.eq-nombre {{ font-family:var(--serif); color:#fff; font-weight:600;
  font-size:16.5px; line-height:1.28; letter-spacing:-.005em; }}
.eq-rol {{ color:var(--cyan); font-size:11.5px; font-weight:600;
  text-transform:uppercase; letter-spacing:.06em; line-height:1.4; }}
/* Bio con gancho: presentación breve que "vende". */
.eq-bio {{ color:#B4C6D0; font-size:13px; line-height:1.55; margin:7px 0 0;
  max-width:52ch; }}
/* Banda inferior full-width: chips (izquierda) + contactos (derecha),
   separada del bloque superior por un hairline tenue. */
.eq-band {{ display:flex; flex-wrap:wrap; align-items:center;
  justify-content:space-between; gap:12px 16px;
  padding-top:15px; border-top:1px solid rgba(255,255,255,.09); }}
/* Chips de habilidades: pills sobrias (borde/relleno tenue, acento agua) en
   fila que envuelve. */
.eq-chips {{ display:flex; flex-wrap:wrap; gap:6px; min-width:0; }}
.eq-chip {{ font-family:var(--sans); font-size:11px; font-weight:500;
  color:#CBE4EC; background:rgba(27,168,196,.1);
  border:1px solid rgba(27,168,196,.28); border-radius:999px;
  padding:3px 10px; line-height:1.4; white-space:nowrap; }}
/* Íconos de contacto: botones circulares sobrios con acento agua al hover. */
.eq-contact {{ display:flex; flex-wrap:wrap; align-items:center; gap:9px;
  flex:none; }}
.eq-ico {{ display:inline-flex; align-items:center; justify-content:center;
  width:34px; height:34px; border-radius:50%; color:#9DB3BF;
  background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.12);
  text-decoration:none;
  transition:color .16s ease, border-color .16s ease, background .16s ease,
    transform .16s ease; }}
.eq-ico:hover {{ color:#fff; background:rgba(27,168,196,.22);
  border-color:rgba(27,168,196,.55); transform:translateY(-2px); }}
.eq-ico:focus-visible {{ outline:2px solid var(--cyan); outline-offset:3px; }}
/* Fuentes: metadatos con clave (mono/mayúscula) + valor. */
.fuentes {{ list-style:none; padding:0; margin:16px 0 0; display:flex;
  flex-direction:column; gap:13px; }}
.fuentes li {{ display:flex; flex-direction:column; gap:3px; }}
.fu-k {{ font-family:var(--mono); font-size:10.5px; text-transform:uppercase;
  letter-spacing:.07em; color:var(--cyan); font-weight:600; }}
.fu-v {{ font-size:13px; color:#B4C6D0; line-height:1.5; }}
.foot-p {{ font-size:13.5px; color:#BACAD4; line-height:1.65; }}
.foot-p b {{ color:#EAF3F6; font-weight:600; }}
.foot-p + .foot-p {{ margin-top:12px; }}
.foot-meta {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:11.5px; color:#8AA4B1; margin-top:16px; }}
/* Barra inferior: copyright + logo UTEC grande, separada por hairline. */
.foot-bar {{ max-width:var(--maxw); margin:0 auto;
  padding:22px var(--pad-x) clamp(30px,3.4vw,40px);
  border-top:1px solid rgba(255,255,255,.10);
  display:flex; align-items:center; justify-content:space-between;
  gap:20px; flex-wrap:wrap; }}
.copyright {{ font-size:12.5px; color:#8AA4B1; line-height:1.6; margin:0;
  max-width:62ch; }}
.foot-logo-wrap {{ display:inline-flex; align-items:center; flex:none;
  opacity:.92; filter:brightness(0) invert(1);
  transition:opacity .18s ease; }}
.foot-logo-wrap:hover {{ opacity:1; }}
.foot-logo-wrap:focus-visible {{ outline:2px solid var(--cyan);
  outline-offset:4px; border-radius:6px; opacity:1; }}
.foot-logo {{ display:block; height:clamp(64px,7vw,72px); width:auto; }}
.foot-logo-txt {{ color:#fff; }}

/* ── Franja «Fuentes de datos» ────────────────────────────────────── */
/* Cinta en movimiento (marquee) bajo el hero: los logos se desplazan solos en
   bucle continuo, se atenúan/desaturan en reposo y reviven a color al pasar el
   cursor. Máscara de desvanecimiento en los bordes; pausa en hover. */
.src-marquee {{ max-width:var(--maxw); margin:0 auto;
  padding:18px var(--pad-x) 20px; border-top:1px solid var(--border); }}
.src-marquee-lab {{ display:block; font-size:11px; font-weight:600;
  text-transform:uppercase; letter-spacing:.11em; color:var(--muted);
  margin:0 0 14px; }}
/* Viewport: recorta el desbordamiento y desvanece los extremos con una máscara. */
.mq-viewport {{ position:relative; overflow:hidden; width:100%;
  -webkit-mask-image:linear-gradient(90deg, transparent 0, #000 6%,
    #000 94%, transparent 100%);
  mask-image:linear-gradient(90deg, transparent 0, #000 6%,
    #000 94%, transparent 100%); }}
/* Pista: dos grupos idénticos en fila; translateX(-50%) reinicia sin costura. */
.mq-track {{ display:flex; width:max-content;
  animation:marquee 32s linear infinite; }}
.mq-group {{ display:flex; align-items:center; flex:none; }}
.mq-item {{ display:inline-flex; align-items:center; justify-content:center;
  margin:0 28px; flex:none; }}
.mq-logo {{ height:40px; width:auto; display:block;
  filter:grayscale(1); opacity:.6;
  transition:filter .22s ease, opacity .22s ease, transform .22s ease; }}
.mq-item:hover .mq-logo {{ filter:none; opacity:1; transform:translateY(-1px); }}
.mq-logo-txt {{ font-family:var(--mono); font-size:14px; font-weight:600;
  color:var(--muted); letter-spacing:.02em; border:1px solid var(--border);
  border-radius:7px; padding:9px 13px; line-height:1;
  filter:grayscale(1); opacity:.6;
  transition:color .22s ease, border-color .22s ease, opacity .22s ease,
    transform .22s ease; }}
.mq-item:hover .mq-logo-txt {{ color:var(--deep); border-color:#B4C4CE;
  filter:none; opacity:1; transform:translateY(-1px); }}
/* Pausa la cinta al pasar el cursor por el conjunto. */
.src-marquee:hover .mq-track {{ animation-play-state:paused; }}
@keyframes marquee {{ from {{ transform:translateX(0); }}
  to {{ transform:translateX(-50%); }} }}
/* Sin animación: fila estática centrada (solo el primer grupo, ancho auto). */
@media (prefers-reduced-motion:reduce) {{
  .mq-track {{ animation:none; width:100%; justify-content:center;
    flex-wrap:wrap; }}
  .mq-group[aria-hidden="true"] {{ display:none; }}
  .mq-item {{ margin:8px 20px; }}
}}

/* Bloque de fuentes en el footer (fondo oscuro). */
.src-foot h4 {{ color:var(--cyan); font-size:11.5px; text-transform:uppercase;
  letter-spacing:.09em; margin-bottom:16px; font-weight:600; }}
.src-foot-grid {{ display:flex; flex-direction:column; gap:15px;
  margin-bottom:20px; }}
.src-foot .src-item {{ display:flex; align-items:center; gap:13px; }}
.src-foot .src-logo {{ height:36px; width:auto; flex:none;
  background:#fff; border-radius:6px; padding:5px 8px; box-sizing:content-box;
  opacity:.94; }}
.src-foot .src-logo-txt {{ font-family:var(--mono); font-weight:600;
  font-size:13px; color:var(--cyan); letter-spacing:.02em; flex:none;
  border:1px solid rgba(255,255,255,.18); border-radius:6px; padding:9px 11px;
  line-height:1; min-width:96px; text-align:center; }}
.src-aporte {{ font-size:12.5px; color:#B4C6D0; line-height:1.45; }}

/* ── Herramientas (stack tecnológico, en el footer oscuro) ────────── */
/* Fila estática de badges (sin marquee): logos + nombre para Python/PyTorch/
   GEE, y pills de texto (acento agua) para las demás. Distinta de las fuentes
   de datos (instituciones). Envuelve en móvil. */
.tools {{ margin-top:22px; }}
.tools-eyebrow {{ font-family:var(--sans); color:var(--cyan); font-size:11px;
  font-weight:600; text-transform:uppercase; letter-spacing:.11em;
  margin:0 0 13px; }}
.tools-row {{ display:flex; flex-wrap:wrap; align-items:center; gap:9px; }}
/* Badge base (pill sobria sobre el footer oscuro). */
.tool-badge {{ display:inline-flex; align-items:center;
  border-radius:999px; line-height:1; white-space:nowrap;
  border:1px solid rgba(255,255,255,.14);
  background:rgba(255,255,255,.05); }}
/* Badge con logo: logo (~28px) alineado con su etiqueta. */
.tool-badge-logo {{ gap:8px; padding:6px 13px 6px 10px; }}
.tool-logo {{ height:28px; width:auto; display:block; flex:none;
  object-fit:contain; }}
.tool-name {{ font-family:var(--sans); font-size:12.5px; font-weight:600;
  color:#EAF3F6; letter-spacing:.005em; }}
/* Badge de texto: pill tenue con acento agua. */
.tool-badge-txt {{ font-family:var(--sans); font-size:12px; font-weight:500;
  color:#CBE4EC; padding:7px 13px;
  background:rgba(27,168,196,.1); border-color:rgba(27,168,196,.3); }}

/* ── Callout editorial (hallazgo ENSO: R² + supresión mutua) ──────── */
.callout {{ position:relative; grid-column:1;
  background:linear-gradient(180deg,#F1F7FA 0%,var(--surf) 100%);
  border:1px solid var(--border); border-left:3px solid var(--accent);
  border-radius:var(--radius); box-shadow:var(--shadow-sm);
  padding:20px 22px; align-self:start; }}
.split-flip .callout {{ grid-column:1; }}
.callout-eyebrow {{ text-transform:uppercase; letter-spacing:.1em;
  font-size:10.5px; font-weight:700; color:var(--accent); margin-bottom:12px; }}
.callout-stat {{ display:flex; align-items:baseline; gap:12px;
  padding-bottom:14px; margin-bottom:14px; border-bottom:1px solid var(--border); }}
.callout-num {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:clamp(1.9rem,3vw,2.4rem); font-weight:600; color:var(--deep);
  letter-spacing:-.02em; line-height:1; }}
.callout-unit {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:14px; color:var(--muted); }}
.callout-body {{ font-size:14px; color:#33424E; line-height:1.6; }}
.callout-body b {{ color:var(--ink); font-weight:600; }}

/* ── Representación / embeddings (small-multiples 2×2 + 3 coloraciones) ── */
/* Conmutador de coloración único (segmented control de 3 opciones) que
   recolorea los CUATRO paneles a la vez. */
.emb-color {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px;
  margin-bottom:16px; }}
.emb-color-lab {{ font-size:11px; font-weight:600; text-transform:uppercase;
  letter-spacing:.08em; color:var(--muted); margin-right:4px; }}
.emb-cbtn {{ appearance:none; cursor:pointer; font-family:var(--sans);
  font-size:12.5px; font-weight:600; color:var(--muted);
  background:var(--surf); border:1.5px solid var(--border); border-radius:999px;
  padding:7px 15px; line-height:1.2;
  transition:color .16s ease, border-color .16s ease, background .16s ease; }}
.emb-cbtn:hover {{ color:var(--deep); border-color:#B4C4CE; }}
.emb-cbtn.is-active {{ color:#fff; background:var(--accent);
  border-color:var(--accent); }}
.emb-cbtn:focus-visible {{ outline:none;
  box-shadow:0 0 0 3px rgba(11,110,140,.20); }}
/* Rejilla 2×2 de mini-scatters (1 columna en móvil, ver responsive). */
.emb-grid {{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr));
  gap:clamp(12px,1.6vw,20px); }}
.emb-panel {{ margin:0; min-width:0; background:var(--surf);
  border:1px solid var(--border); border-radius:var(--radius);
  box-shadow:var(--shadow-sm); padding:12px 12px 8px;
  display:flex; flex-direction:column; }}
.emb-panel-head {{ display:flex; align-items:baseline; justify-content:space-between;
  gap:10px; margin:0 2px 4px; }}
.emb-panel-name {{ font-family:var(--serif); font-weight:600; font-size:1.02rem;
  color:var(--deep); line-height:1.1; }}
.emb-panel-sil {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:11px; font-weight:500; color:var(--muted); letter-spacing:.01em;
  white-space:nowrap; }}
.emb-panel-plot {{ width:100%; min-height:300px; }}

/* ── Movimiento con propósito ─────────────────────────────────────── */
/* Solo se oculta si hay JS (clase js-on en <html>); sin JS todo es visible. */
.js-on .reveal {{ opacity:0; transform:translateY(16px);
  transition:opacity .6s ease, transform .6s ease; }}
.js-on .reveal.is-visible {{ opacity:1; transform:none; }}
/* Secuencia de carga del hero */
.js-on .hero-rev {{ opacity:0; transform:translateY(14px);
  transition:opacity .7s ease, transform .7s ease; }}
.js-on .hero-rev.is-visible {{ opacity:1; transform:none; }}
.js-on .hero-rev[data-rev="2"] {{ transition-delay:.09s; }}
.js-on .hero-rev[data-rev="3"] {{ transition-delay:.18s; }}

@media (prefers-reduced-motion:reduce) {{
  html {{ scroll-behavior:auto; }}
  .reveal, .hero-rev {{ opacity:1 !important; transform:none !important;
    transition:none !important; }}
  .tabpanel {{ animation:none; }}
  .tab::after {{ transition:none; }}
  /* Sin desplazamientos de elevación en hover (equipo/íconos/contadores). */
  .eq-card:hover, .eq-ico:hover {{ transform:none; }}
}}

/* ── Responsive ───────────────────────────────────────────────────── */
@media (max-width:900px) {{
  .split, .split-flip {{ grid-template-columns:1fr; }}
  /* En una sola columna, todo ocupa la pista 1 y fluye por orden de fuente
     (gráfico y luego notas). Reinicia paddings/acento del borde. */
  .split-main, .split-aside,
  .split-flip .split-main, .split-flip .split-aside {{ grid-column:1; }}
  .split-flip .split-aside {{ padding-left:22px; padding-right:0; }}
  .split-flip .split-aside::before {{ left:0; right:auto; }}
  .callout, .split-flip .callout {{ grid-column:1; }}
  .foot-inner {{ grid-template-columns:1fr 1fr; }}
  .foot-col-eq {{ grid-column:1 / -1; }}
  .equipo {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
}}
@media (max-width:640px) {{
  .brand-logo {{ height:48px; }}
  .brand-sub {{ display:none; }}
  .brand-divider {{ display:none; }}
  .status-txt {{ display:none; }}
  .kpi {{ flex:1 1 45%; min-width:44%; }}
  .kpi + .kpi::before {{ display:none; }}
  .kpi-row {{ gap:0; }}
  .conc-grid {{ grid-template-columns:1fr; gap:22px; }}
  .foot-inner {{ grid-template-columns:1fr; gap:30px; }}
  .foot-col-eq {{ grid-column:auto; }}
  .equipo {{ grid-template-columns:1fr; }}
  .foot-bar {{ flex-direction:column-reverse; align-items:flex-start; gap:18px; }}
  .mapa-iframe {{ height:440px; }}
  .fc-select {{ min-width:0; width:100%; }}
  .fc-field {{ flex:1 1 44%; }}
  .fc-readout {{ margin-left:0; text-align:left; flex:1 1 100%; }}
  .mq-logo {{ height:32px; }}
  .mq-item {{ margin:0 20px; }}
  /* Small-multiples de embeddings: una sola columna en móvil. */
  .emb-grid {{ grid-template-columns:1fr; }}
}}
/* Tarjeta de equipo en móvil: apila (foto centrada arriba, luego nombre/rol/bio,
   y finalmente chips + contactos centrados). En ningún ancho el texto se monta
   sobre la foto ni se corta. */
@media (max-width:560px) {{
  .eq-card {{ gap:14px; padding:20px 18px; }}
  .eq-top {{ flex-direction:column; align-items:center; text-align:center;
    gap:14px; }}
  .eq-ident {{ align-items:center; width:100%; }}
  .eq-band {{ flex-direction:column; align-items:center; text-align:center;
    gap:14px; }}
  .eq-chips {{ justify-content:center; }}
  .eq-contact {{ justify-content:center; }}
}}
"""


# ── Script de interacción (reveal on load/scroll, respeta reduced-motion) ─────
JS_REVEAL = """
(function(){
  // Marca que hay JS: solo entonces las secciones parten ocultas (sin JS, visibles).
  document.documentElement.className += ' js-on';
  function run(){
    var reduce = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // Secuencia del hero: se revela nada más cargar (está sobre el pliegue).
    var hero = Array.prototype.slice.call(document.querySelectorAll('.hero-rev'));
    var revealHero = function(){ hero.forEach(function(el){ el.classList.add('is-visible'); }); };
    if (reduce) { revealHero(); }
    else { requestAnimationFrame(function(){ requestAnimationFrame(revealHero); }); }

    // Reveal-on-scroll dentro de las pestañas. Elementos en paneles ocultos
    // no intersectan; se revelan cuando su pestaña se muestra (ver JS_TABS,
    // que dispara 'hidroalerta:tabshown').
    var els = Array.prototype.slice.call(document.querySelectorAll('.reveal'));
    var showAll = function(){ els.forEach(function(el){ el.classList.add('is-visible'); }); };
    if (reduce || !('IntersectionObserver' in window)) { showAll(); return; }
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){
        if (e.isIntersecting){ e.target.classList.add('is-visible'); io.unobserve(e.target); }
      });
    }, { threshold: 0.06, rootMargin: '0px 0px -30px 0px' });
    els.forEach(function(el){ io.observe(el); });

    // Al mostrarse una pestaña, revela de inmediato sus elementos .reveal
    // (los que estaban ocultos nunca intersectaron mientras el panel tenía
    // display:none) y deja de observarlos.
    document.addEventListener('hidroalerta:tabshown', function(ev){
      var panel = ev.detail && ev.detail.panel;
      if (!panel) return;
      Array.prototype.slice.call(panel.querySelectorAll('.reveal')).forEach(function(el){
        el.classList.add('is-visible'); io.unobserve(el);
      });
    });
    // Salvaguarda: si algo impide el observer, revela todo pasados 2.5 s.
    setTimeout(showAll, 2500);
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', run);
  else run();
})();
"""


# ── Script de navegación por pestañas (ARIA + teclado + hash + resize Plotly) ─
# Crítico: los gráficos Plotly creados en un panel con display:none tienen
# ancho 0; al activar su pestaña hay que llamar Plotly.Plots.resize(div) para
# cada uno, o quedan colapsados.
JS_TABS = """
(function(){
  function run(){
    var tablist = document.querySelector('[role="tablist"]');
    if (!tablist) return;
    var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
    if (!tabs.length) return;

    function panelOf(tab){
      return document.getElementById(tab.getAttribute('aria-controls'));
    }

    // Redimensiona todos los gráficos Plotly de un panel (arreglo de ancho 0).
    function resizePlots(panel){
      if (!panel || typeof Plotly === 'undefined' || !Plotly.Plots) return;
      var plots = panel.querySelectorAll('.js-plotly-plot');
      Array.prototype.forEach.call(plots, function(div){
        try { Plotly.Plots.resize(div); } catch(e){}
      });
    }

    function activate(tab, opts){
      opts = opts || {};
      tabs.forEach(function(t){
        var sel = (t === tab);
        t.setAttribute('aria-selected', sel ? 'true' : 'false');
        t.tabIndex = sel ? 0 : -1;
        var p = panelOf(t);
        if (p){
          if (sel){ p.hidden = false; }
          else { p.hidden = true; }
        }
      });
      var panel = panelOf(tab);
      if (panel){
        // Avisa al reveal-observer para que muestre el contenido del panel.
        document.dispatchEvent(new CustomEvent('hidroalerta:tabshown',
          { detail: { panel: panel } }));
        // Tras el reflow (panel ya visible), redimensiona los Plotly.
        requestAnimationFrame(function(){
          requestAnimationFrame(function(){ resizePlots(panel); });
        });
        // Segundo pase para casos de fuentes/layout tardíos.
        setTimeout(function(){ resizePlots(panel); }, 240);
      }
      if (opts.focus){ tab.focus(); }
      if (opts.scroll){
        window.scrollTo({ top: 0,
          behavior: (opts.smooth === false ? 'auto' : 'smooth') });
      }
      var id = tab.getAttribute('data-tab');
      if (id && opts.hash !== false){
        if (history.replaceState){ history.replaceState(null, '', '#' + id); }
        else { location.hash = id; }
      }
    }

    // Navegación por teclado: flechas, Home/End.
    tablist.addEventListener('keydown', function(e){
      var i = tabs.indexOf(document.activeElement);
      if (i === -1) return;
      var n = tabs.length, j = -1;
      switch (e.key){
        case 'ArrowRight': case 'ArrowDown': j = (i + 1) % n; break;
        case 'ArrowLeft':  case 'ArrowUp':   j = (i - 1 + n) % n; break;
        case 'Home': j = 0; break;
        case 'End':  j = n - 1; break;
        default: return;
      }
      e.preventDefault();
      activate(tabs[j], { focus: true, scroll: false });
    });

    tabs.forEach(function(tab){
      tab.addEventListener('click', function(){
        activate(tab, { focus: false, scroll: true });
      });
    });

    // Deep-link inicial por hash; si no, primera pestaña ("Resumen").
    function fromHash(){
      var h = (location.hash || '').replace('#','');
      for (var k=0;k<tabs.length;k++){
        if (tabs[k].getAttribute('data-tab') === h) return tabs[k];
      }
      return tabs[0];
    }
    activate(fromHash(), { focus: false, scroll: false, smooth: false, hash: false });

    // Responder a cambios de hash (navegación atrás/adelante, enlaces).
    window.addEventListener('hashchange', function(){
      activate(fromHash(), { focus: false, scroll: false, hash: false });
    });

    // Al redimensionar la ventana, ajusta los gráficos del panel visible.
    var rt;
    window.addEventListener('resize', function(){
      clearTimeout(rt);
      rt = setTimeout(function(){
        var vis = tabs.filter(function(t){ return t.getAttribute('aria-selected') === 'true'; })[0];
        if (vis) resizePlots(panelOf(vis));
      }, 180);
    });
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', run);
  else run();
})();
"""


# ── Script del gráfico de pronóstico interactivo (selector modelo + horizonte) ─
JS_FORECAST = """
(function(){
  function run(){
    var dataEl = document.getElementById('fc-data');
    var plotEl = document.getElementById('grafico-serie');
    if (!dataEl || !plotEl || typeof Plotly === 'undefined') return;
    var CFG;
    try { CFG = JSON.parse(dataEl.textContent); } catch(e){ return; }

    var selMod = document.getElementById('fc-modelo');
    var selLead = document.getElementById('fc-lead');
    var nseEl = document.getElementById('fc-nse');
    var notaEl = document.getElementById('fc-nota');
    var fechas = CFG.fechas;
    var reduce = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function toRGBA(hex, a){
      var h = hex.replace('#',''); if (h.length===3){ h=h[0]+h[0]+h[1]+h[1]+h[2]+h[2]; }
      var n = parseInt(h,16);
      return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+a+')';
    }

    // Rectángulos de fondo para los tramos sin aforo.
    var shapes = CFG.gaps.map(function(g){
      return { type:'rect', xref:'x', yref:'paper', x0:g[0], x1:g[1],
        y0:0, y1:1, fillcolor:CFG.col_gap, line:{width:0}, layer:'below' };
    });

    var FS = 'IBM Plex Sans, -apple-system, Segoe UI, sans-serif';
    var FM = 'IBM Plex Mono, SFMono-Regular, Consolas, monospace';
    var baseLayout = {
      hovermode:'x unified',
      margin:{l:58,r:18,t:64,b:36}, height:470,
      colorway:[CFG.colores['RA-TFT'], CFG.col_deep, CFG.col_cyan],
      legend:{orientation:'h', yanchor:'bottom', y:1.10, xanchor:'left', x:0,
        font:{size:12, family:FS, color:CFG.col_muted}},
      font:{family:FS, size:13, color:CFG.col_ink},
      yaxis:{title:{text:'Caudal (m³/s)', font:{family:FS, size:12, color:CFG.col_muted}},
        gridcolor:CFG.col_border, zeroline:false, rangemode:'tozero',
        tickfont:{family:FM, size:11, color:CFG.col_muted}},
      xaxis:{title:'', gridcolor:CFG.col_border, linecolor:CFG.col_border,
        tickfont:{family:FM, size:11, color:CFG.col_muted},
        rangeslider:{visible:true, thickness:0.07, bgcolor:'rgba(11,110,140,0.05)',
          bordercolor:CFG.col_border},
        rangeselector:{ buttons:[
          {count:1,label:'1 m',step:'month',stepmode:'backward'},
          {count:3,label:'3 m',step:'month',stepmode:'backward'},
          {count:6,label:'6 m',step:'month',stepmode:'backward'},
          {count:1,label:'1 a',step:'year',stepmode:'backward'},
          {step:'all',label:'Todo'} ],
          font:{size:11, family:FS, color:CFG.col_deep},
          bgcolor:'rgba(255,255,255,0.7)', bordercolor:CFG.col_border,
          activecolor:CFG.colores['RA-TFT'] }},
      plot_bgcolor:'rgba(0,0,0,0)', paper_bgcolor:'rgba(0,0,0,0)',
      hoverlabel:{bgcolor:CFG.col_surf, bordercolor:CFG.col_border,
        font:{family:FM, size:12, color:CFG.col_ink}},
      modebar:{bgcolor:'rgba(0,0,0,0)', color:CFG.col_muted, activecolor:CFG.colores['RA-TFT']},
      transition:{duration: reduce ? 0 : 350, easing:'cubic-in-out'},
      shapes: shapes.concat([{ type:'line', xref:'paper', yref:'y',
        x0:0, x1:1, y0:CFG.umbral, y1:CFG.umbral,
        line:{color:CFG.col_crit, width:1.6, dash:'dot'}, layer:'above' }]),
      annotations:[{ xref:'paper', yref:'y', x:0.01, y:CFG.umbral, yanchor:'bottom',
        xanchor:'left', showarrow:false,
        text:'Umbral de alerta Q90 = '+CFG.umbral.toFixed(2)+' m³/s',
        font:{color:CFG.col_crit, size:12, family:FM} }]
    };

    var config = { displayModeBar:true, displaylogo:false, responsive:true,
      modeBarButtonsToRemove:['lasso2d','select2d'] };
    var dibujado = false;

    function tracesFor(model, lead){
      var key = model + '|' + lead;
      var s = CFG.series[key];
      var col = CFG.colores[model] || CFG.colores['RA-TFT'];
      var traces = [];
      if (s && s.band && s.p10 && s.p90){
        traces.push({ x:fechas, y:s.p90, mode:'lines', line:{width:0},
          hoverinfo:'skip', showlegend:false, name:'P90', connectgaps:false });
        traces.push({ x:fechas, y:s.p10, mode:'lines', fill:'tonexty',
          fillcolor:toRGBA(col,0.16), line:{width:0}, name:'Banda P10–P90',
          hovertemplate:'P10 %{y:.1f} · ', connectgaps:false });
      }
      if (s){
        // P50 (línea del modelo).
        traces.push({ x:fechas, y:s.p50, mode:'lines',
          line:{color:col, width:2}, name:'Pronóstico (mediana P50)',
          hovertemplate:'P50 %{y:.1f} m³/s', connectgaps:false });
        // Observado: solo puntos finitos.
        var ox=[], oy=[];
        for (var i=0;i<fechas.length;i++){
          if (s.obs[i] !== null && s.obs[i] !== undefined){ ox.push(fechas[i]); oy.push(s.obs[i]); }
        }
        traces.push({ x:ox, y:oy, mode:'markers',
          marker:{color:CFG.col_obs, size:4.5, line:{width:0}},
          name:'Caudal observado (aforo)', hovertemplate:'Observado %{y:.1f} m³/s' });
      }
      return traces;
    }

    function actualizarNota(model, lead, s){
      if (nseEl){ nseEl.textContent = (s && s.nse !== null && s.nse !== undefined)
        ? s.nse.toFixed(3) : '—'; }
      if (notaEl){
        var n = (s && s.n) ? s.n : 0;
        var extra = (model === 'Persistencia')
          ? ' La persistencia es un baseline puntual: repite el último caudal (sin banda de incertidumbre).'
          : (model === 'HydroST'
              ? ' HydroST es un modelo espacio-temporal disponible solo a 1 día.'
              : '');
        notaEl.textContent = 'Modelo ' + model + ' · horizonte ' + lead +
          (lead==1?' día':' días') + '. Serie 2024–2025; ' + n +
          ' días con caudal observado, el resto son periodos sin aforo con pronóstico activo.' + extra;
      }
    }

    function sincronizarLeads(model){
      var disp = CFG.disponibles[model] || [];
      var opts = selLead.options;
      for (var i=0;i<opts.length;i++){
        var v = parseInt(opts[i].value,10);
        opts[i].disabled = (disp.indexOf(v) === -1);
      }
      // Si el lead actual no está disponible, saltar al primero disponible.
      var cur = parseInt(selLead.value,10);
      if (disp.indexOf(cur) === -1 && disp.length){
        selLead.value = String(disp[0]);
      }
    }

    function render(){
      var model = selMod.value;
      var lead = parseInt(selLead.value,10);
      var s = CFG.series[model + '|' + lead];
      var traces = tracesFor(model, lead);
      if (!dibujado){
        Plotly.newPlot(plotEl, traces, baseLayout, config);
        dibujado = true;
      } else {
        // Plotly.react diffea trazas (añade/quita banda según el modelo) y,
        // con layout.transition, interpola suavemente los valores.
        Plotly.react(plotEl, traces, baseLayout, config);
      }
      actualizarNota(model, lead, s);
    }

    sincronizarLeads(selMod.value);
    render();

    selMod.addEventListener('change', function(){
      sincronizarLeads(selMod.value);
      render();
    });
    selLead.addEventListener('change', function(){ render(); });
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', run);
  else run();
})();
"""


# ── Script de los embeddings: small-multiples 2×2 sincronizados + 3 coloraciones ─
# Análisis no supervisado (model-agnóstico). Los CUATRO métodos (PCA, Isomap,
# UMAP, DTW→MDS) se dibujan a la vez, uno por div, en una rejilla 2×2. Un único
# conmutador cambia la COLORACIÓN (magnitud del caudal · crecida vs base ·
# temporada) y recolorea los cuatro paneles con Plotly.react. HOVER SINCRONIZADO:
# al pasar el cursor por un punto (plotly_hover) se lee su `fecha` (customdata) y
# se resalta el mismo punto (misma fecha) en TODOS los paneles mediante una traza
# de resalte (un aro) que se actualiza con Plotly.restyle; plotly_unhover la
# limpia. PCA/Isomap/UMAP comparten fechas; DTW→MDS es un subconjunto, por lo que
# el aro solo aparece donde esa fecha existe. La traza de resalte NO emite eventos
# de hover, así que no hay bucle de realimentación. Los divs pasan a ser
# .js-plotly-plot, de modo que JS_TABS ya los redimensiona al activar la pestaña
# "Datos & representación"; también se redimensionan al cambiar de coloración.
JS_EMBED = """
(function(){
  function run(){
    var dataEl = document.getElementById('emb-data');
    if (!dataEl || typeof Plotly === 'undefined') return;
    var CFG;
    try { CFG = JSON.parse(dataEl.textContent); } catch(e){ return; }

    var orden = CFG.orden || [];
    if (!orden.length) return;
    var cont = dataEl.parentNode;   // contenedor .tabpanel > .tab-body > <div reveal>
    var cbtns = Array.prototype.slice.call(
      document.querySelectorAll('.emb .emb-cbtn'));
    var reduce = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var FS = 'IBM Plex Sans, -apple-system, Segoe UI, sans-serif';
    var FM = 'IBM Plex Mono, SFMono-Regular, Consolas, monospace';

    var colorMode = 'q';         // 'q' | 'reg' | 'temp'
    var HL_COLOR = CFG.col_ink || '#0C1E2A';

    // Slug ASCII por método (coincide con los id de los divs y las etiquetas).
    var SLUG = { 'PCA':'pca', 'Isomap':'isomap', 'UMAP':'umap', 'DTW→MDS':'dtw' };

    function toRGBA(hex, a){
      var h = hex.replace('#',''); if (h.length===3){ h=h[0]+h[0]+h[1]+h[1]+h[2]+h[2]; }
      var n = parseInt(h,16);
      return 'rgba('+((n>>16)&255)+','+((n>>8)&255)+','+(n&255)+','+a+')';
    }
    // Escala continua azul→rojo para la magnitud del caudal (paleta del proyecto).
    var SCALE_Q = [[0,'#1BA8C4'],[0.3,'#0B6E8C'],[0.6,'#8FA0AC'],
                   [0.8,'#D68910'],[1,'#C0392B']];

    function hoverText(d, i){
      return d.fecha[i] + '<br>Caudal: ' + d.q[i].toFixed(1) +
        ' m³/s<br>Régimen: ' + d.regimen[i] + '<br>Temporada: ' + d.temporada[i];
    }

    // Divide los índices de un método según una clave ('regimen'/'temporada').
    // Emite arrays paralelos, incluida la `fecha` como customdata para el hover.
    function split(d, campo, valor){
      var xs=[], ys=[], tx=[], cd=[];
      for (var i=0;i<d.x.length;i++){
        if (d[campo][i] === valor){ xs.push(d.x[i]); ys.push(d.y[i]);
          tx.push(hoverText(d,i)); cd.push(d.fecha[i]); }
      }
      return { x:xs, y:ys, text:tx, customdata:cd };
    }

    // Traza de resalte (aro) que se sobrepone; arranca vacía. Es SIEMPRE la
    // última traza del panel, para actualizarla por índice con Plotly.restyle.
    function highlightTrace(){
      return { x:[], y:[], mode:'markers', type:'scatter',
        name:'resalte', hoverinfo:'skip', showlegend:false,
        marker:{ color:'rgba(0,0,0,0)', size:15,
          line:{ width:2.4, color:HL_COLOR } } };
    }

    // Trazas de datos para el método `d` según la coloración activa
    // (sin la traza de resalte, que se añade aparte).
    function dataTraces(d){
      if (colorMode === 'q'){
        // (a) Magnitud del caudal: un solo scatter con color continuo + colorbar.
        var tx = [];
        for (var i=0;i<d.x.length;i++){ tx.push(hoverText(d,i)); }
        return [{ x:d.x, y:d.y, mode:'markers', type:'scatter',
          name:'Caudal', text:tx, customdata:d.fecha, hoverinfo:'text',
          showlegend:false,
          marker:{ color:d.q, colorscale:SCALE_Q, cmin:CFG.q_min, cmax:CFG.q_max,
            size:5.5, opacity:0.82, line:{width:0},
            colorbar:{ title:{text:'m³/s', side:'right',
                font:{family:FS, size:10, color:CFG.col_muted}},
              thickness:9, len:0.82, x:1.02, xpad:2,
              tickfont:{family:FM, size:9, color:CFG.col_muted},
              outlinewidth:0 } } }];
      }
      if (colorMode === 'reg'){
        // (b) Crecida vs base (Q90): base azul (debajo), crecida rojo (encima).
        var b = split(d,'regimen','base'), c = split(d,'regimen','crecida');
        return [
          { x:b.x, y:b.y, mode:'markers', type:'scatter', name:'Base',
            text:b.text, customdata:b.customdata, hoverinfo:'text',
            marker:{ color:toRGBA(CFG.col_base,0.42), size:5, line:{width:0} } },
          { x:c.x, y:c.y, mode:'markers', type:'scatter', name:'Crecida',
            text:c.text, customdata:c.customdata, hoverinfo:'text',
            marker:{ color:toRGBA(CFG.col_crecida,0.82), size:7,
              line:{width:0.5, color:'#fff'} } }
        ];
      }
      // (c) Temporada: húmeda vs seca (dos colores).
      var h = split(d,'temporada','humeda'), s = split(d,'temporada','seca');
      return [
        { x:s.x, y:s.y, mode:'markers', type:'scatter', name:'Seca',
          text:s.text, customdata:s.customdata, hoverinfo:'text',
          marker:{ color:toRGBA(CFG.col_seca,0.62), size:5, line:{width:0} } },
        { x:h.x, y:h.y, mode:'markers', type:'scatter', name:'Húmeda',
          text:h.text, customdata:h.customdata, hoverinfo:'text',
          marker:{ color:toRGBA(CFG.col_humeda,0.62), size:5, line:{width:0} } }
      ];
    }

    function tracesFor(d){ return dataTraces(d).concat([highlightTrace()]); }

    function layoutFor(){
      var showleg = (colorMode !== 'q');
      return {
        // Alto compacto: cuatro paneles a la vez en la rejilla 2×2.
        height:300, hovermode:'closest',
        margin:{l:36, r: (colorMode==='q'? 52 : 10), t: (showleg? 30 : 8), b:34},
        font:{family:FS, size:12, color:CFG.col_ink},
        paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
        showlegend:showleg,
        legend:{orientation:'h', yanchor:'bottom', y:1.0, xanchor:'left', x:0,
          font:{size:11, family:FS, color:CFG.col_muted}},
        hoverlabel:{bgcolor:CFG.col_surf, bordercolor:CFG.col_border,
          font:{family:FM, size:11.5, color:CFG.col_ink}},
        xaxis:{ title:{text:'Comp. 1 (sin unidades)',
            font:{family:FS, size:10.5, color:CFG.col_muted}},
          gridcolor:CFG.col_border, zeroline:false, linecolor:CFG.col_border,
          tickfont:{family:FM, size:9, color:CFG.col_muted},
          showticklabels:true },
        yaxis:{ title:{text:'Comp. 2 (sin unidades)',
            font:{family:FS, size:10.5, color:CFG.col_muted}},
          gridcolor:CFG.col_border, zeroline:false, linecolor:CFG.col_border,
          tickfont:{family:FM, size:9, color:CFG.col_muted},
          showticklabels:true, scaleanchor:'x', scaleratio:1 },
        modebar:{bgcolor:'rgba(0,0,0,0)', color:CFG.col_muted,
          activecolor:CFG.col_deep},
        transition:{duration: reduce ? 0 : 260, easing:'cubic-in-out'}
      };
    }

    var config = { displayModeBar:false, displaylogo:false, responsive:true };

    // Estado por panel: div, datos, índice de fecha→fila, índice de traza de
    // resalte y bandera de dibujado.
    var paneles = [];   // [{ met, div, d, fIndex, hlIndex, drawn }]

    orden.forEach(function(met){
      var slug = SLUG[met];
      var div = document.getElementById('grafico-embeddings-' + slug);
      var d = CFG.metodos[met];
      if (!div || !d) return;
      var fIndex = {};                 // fecha (str) -> índice de fila
      for (var i=0;i<d.fecha.length;i++){ fIndex[d.fecha[i]] = i; }
      paneles.push({ met:met, slug:slug, div:div, d:d, fIndex:fIndex,
        hlIndex:0, drawn:false });
      // Etiqueta de silueta del panel.
      var silNode = document.getElementById('emb-sil-' + slug);
      if (silNode){ silNode.textContent = 'silueta ' +
        ((d.sil !== null && d.sil !== undefined) ? d.sil.toFixed(3) : '—'); }
    });
    if (!paneles.length) return;

    // Actualiza el aro de resalte de un panel a la fila `row` (o lo limpia).
    function setHighlight(p, row){
      if (!p.drawn) return;
      var x = [], y = [];
      if (row !== null && row !== undefined && row >= 0){
        x = [p.d.x[row]]; y = [p.d.y[row]];
      }
      try { Plotly.restyle(p.div, { x:[x], y:[y] }, [p.hlIndex]); } catch(e){}
    }

    // Resalta la misma `fecha` en todos los paneles (solo donde exista).
    function highlightAll(fecha){
      paneles.forEach(function(p){
        var row = (fecha in p.fIndex) ? p.fIndex[fecha] : -1;
        setHighlight(p, row);
      });
    }
    function clearAll(){ paneles.forEach(function(p){ setHighlight(p, -1); }); }

    function wireHover(p){
      p.div.on('plotly_hover', function(ev){
        if (!ev || !ev.points || !ev.points.length) return;
        var pt = ev.points[0];
        // La fecha viaja como customdata en cada traza de datos; se ignora la
        // traza de resalte (hoverinfo:skip, no dispara este evento).
        var fecha = pt.customdata;
        if (fecha === null || fecha === undefined) return;
        highlightAll(String(fecha));
      });
      p.div.on('plotly_unhover', function(){ clearAll(); });
    }

    function drawPanel(p){
      var traces = tracesFor(p.d);
      p.hlIndex = traces.length - 1;   // la traza de resalte es la última
      var layout = layoutFor();
      if (!p.drawn){
        Plotly.newPlot(p.div, traces, layout, config);
        p.drawn = true;
        wireHover(p);
      } else {
        Plotly.react(p.div, traces, layout, config);
      }
    }

    function actualizarBotones(){
      cbtns.forEach(function(btn){
        var on = (btn.getAttribute('data-color') === colorMode);
        btn.classList.toggle('is-active', on);
        btn.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }

    function renderTodos(){
      paneles.forEach(drawPanel);
      actualizarBotones();
      // Reajusta anchos (los divs pueden haberse dibujado ocultos o con el
      // ancho anterior a la coloración).
      requestAnimationFrame(function(){
        paneles.forEach(function(p){
          try { Plotly.Plots.resize(p.div); } catch(e){}
        });
      });
    }

    cbtns.forEach(function(btn){
      btn.addEventListener('click', function(){
        var nuevo = btn.getAttribute('data-color') || 'q';
        if (nuevo === colorMode){ return; }
        colorMode = nuevo;
        renderTodos();
      });
    });

    renderTodos();
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', run);
  else run();
})();
"""


# ── Script de los contadores animados ("Por los números") ─────────────────────
# Los números suben de 0 a su valor final al entrar la banda en vista
# (IntersectionObserver). El valor final ya está en el DOM: bajo
# prefers-reduced-motion (o sin IntersectionObserver) se deja tal cual, sin
# animar. La animación (~1.2 s, easeOutCubic) solo se activa cuando el
# movimiento está permitido; se ejecuta una vez y deja de observar.
JS_COUNTERS = """
(function(){
  function run(){
    var nums = Array.prototype.slice.call(
      document.querySelectorAll('.cnt-num'));
    if (!nums.length) return;
    var reduce = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    // Sin animación posible: el número final ya está escrito → no tocar.
    if (reduce || !('IntersectionObserver' in window)) return;

    function animar(el){
      var target = parseInt(el.getAttribute('data-target'), 10);
      if (isNaN(target)) return;
      var dur = 1200, t0 = null;
      el.textContent = '0';
      function paso(ts){
        if (t0 === null) t0 = ts;
        var p = Math.min((ts - t0) / dur, 1);
        var e = 1 - Math.pow(1 - p, 3);   // easeOutCubic
        el.textContent = String(Math.round(e * target));
        if (p < 1){ requestAnimationFrame(paso); }
        else { el.textContent = String(target); }
      }
      requestAnimationFrame(paso);
    }

    var band = document.querySelector('.numeros');
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(en){
        if (en.isIntersecting){
          nums.forEach(animar);
          io.disconnect();
        }
      });
    }, { threshold: 0.35 });
    if (band){ io.observe(band); }
    else { nums.forEach(animar); }
  }
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', run);
  else run();
})();
"""


def main():
    (serie, metr, meta, subs, lim, fcast, mens, enso, acf, ccf,
     estaciones, enso_abl, enso_extra, emb_coords, emb_sil) = cargar()
    imgs = cargar_imagenes()
    print("Datos cargados. Construyendo componentes...")
    if imgs:
        print(f"  Recursos de imagen embebidos: {', '.join(sorted(imgs))}")
    else:
        print("  Sin imágenes en assets/: se usa respaldo tipográfico.")
    mapa_html = construir_mapa(meta, subs, lim, estaciones)
    cfg_fcast = serie_pronostico_datos(fcast, metr)
    serie_div = bloque_serie_interactiva(cfg_fcast)
    anim_div = construir_animacion(metr)
    tabla_html = tabla_metricas_html(metr)
    kpi_html = kpi_cards(serie)
    mensual_div = construir_mensual(mens)
    evento_div = construir_evento(fcast)
    enso_div = construir_enso(enso)
    eda_div = construir_eda(acf, ccf)
    enso_abl_div = construir_enso_ablacion(enso_abl)
    enso_callout = bloque_enso_callout(enso_extra)
    enso_r2_div = construir_enso_r2(enso, enso_extra)
    cfg_embed = embeddings_datos(emb_coords, emb_sil)
    embed_div = bloque_embeddings(cfg_embed)
    print("Ensamblando index.html...")
    cuerpo = ensamblar(mapa_html, serie_div, anim_div, tabla_html, kpi_html,
                       mensual_div, evento_div, enso_div, eda_div, enso_abl_div,
                       enso_callout, enso_r2_div, embed_div, imgs, meta, serie)

    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HidroAlerta Chancay–Huaral · Pronóstico y alerta de caudal</title>
<meta name="description" content="Dashboard de monitoreo: pronóstico de caudal y alerta temprana de crecidas del río Chancay–Huaral (Concurso ANA 2026).">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,500;8..60,600;8..60,700&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>{estilos()}</style>
</head>
<body>
{cuerpo}
<script>{JS_REVEAL}</script>
<script>{JS_TABS}</script>
<script>{JS_FORECAST}</script>
<script>{JS_EMBED}</script>
<script>{JS_COUNTERS}</script>
</body>
</html>
"""
    out = DOCS / "index.html"
    out.write_text(doc, encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"Generado: {out}  ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
