"""
build_dashboard.py — Genera docs/index.html (dashboard autocontenido) a partir
de los datos curados en hidroalerta-dashboard/data/.

Es una interfaz de monitoreo (no un documento): resumen antes que detalle,
estado codificado en forma (pills/chips), color semántico separado del acento.

Secciones:
  1. Header fino y sticky con pill de estado (umbral Q90).
  2. Fila de KPI cards (resumen).
  3. Mapa interactivo Folium (cuenca + 9 subcuencas + estación de aforo).
  4. Serie de pronóstico interactiva (selector de modelo + horizonte, Plotly.react).
  5. Gráfico animado "Habilidad vs horizonte" (frames + slider Plotly sobre lead).
  6. Tabla de métricas por horizonte (mejor valor por columna resaltado).
  7. Producto mensual de disponibilidad hídrica (obs vs P50 + climatología).
  8. Zoom al evento de crecida (feb-2024): modelos frente al pico observado.
  9. Señal ENSO (Niño costero vs ONI global; efecto de signo opuesto).
 10. Análisis exploratorio (ACF del caudal, CCF lluvia→caudal).
 11. Conclusiones y limitaciones.
 12. Footer (equipo, fuentes, licencia).

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

# ── Paleta (hidrología, considerada) ─────────────────────────────────────────
# Ground / superficie / tinta / borde-grid con sesgo azul frío (elegido).
COL_BG = "#F5F7FA"
COL_SURF = "#FFFFFF"
COL_INK = "#12212E"
COL_BORDER = "#DDE3EA"
# Acento (agua) — NO usar semánticos como acento.
COL_ACCENT = "#0B6E8C"      # agua
COL_DEEP = "#134E6F"        # azul profundo
# Semánticos SOLO para estado.
COL_CRIT = "#C0392B"        # alerta / crítico (umbral, días en alerta)
COL_OK = "#2E8B6F"          # normal
COL_WARN = "#D68910"        # aviso
COL_MUTED = "#5B6B78"       # texto secundario

# Trazas de la serie.
COL_OBS = "#12212E"                       # observado (tinta)
COL_P50 = COL_ACCENT                      # mediana
COL_BAND = "rgba(11,110,140,0.16)"        # banda P10–P90
COL_GAP = "rgba(19,78,111,0.06)"          # sombreado tramos sin aforo


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
    return serie, metr, meta, subs, lim, fcast, mens, enso, acf, ccf


# ── Recursos gráficos (imágenes) → data URI, con degradación tipográfica ──────
def cargar_imagenes():
    """Lee assets/ y devuelve {clave: data_uri}. Ignora placeholders/no-imágenes.

    Claves: 'logo' (utec_logo.png) y 'foto_1'..'foto_4' (foto_*.jpg por orden).
    Si no hay imágenes válidas, el HTML usa un respaldo tipográfico (sin roturas).
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

    logo = ASSETS / "utec_logo.png"
    if logo.is_file():
        uri = a_data_uri(logo)
        if uri:
            recursos["logo"] = uri

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
def construir_mapa(meta, subs, lim) -> str:
    est = meta["estacion"]
    m = folium.Map(
        location=[-11.30, -76.85],
        zoom_start=10,
        tiles=None,
        control_scale=True,
    )
    folium.TileLayer(
        "CartoDB positron", name="Mapa claro", control=True).add_to(m)
    folium.TileLayer(
        "OpenStreetMap", name="OpenStreetMap", control=True).add_to(m)
    folium.TileLayer(
        "Esri.WorldImagery", name="Satélite (Esri)", control=True,
        attr="Tiles © Esri").add_to(m)

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

    # Color por elevación (costa → cabecera) — rampa azul-verde-arena.
    def color_elev(e):
        if e < 1000:
            return "#2E6E8E"
        if e < 2500:
            return "#4FA3B8"
        if e < 3800:
            return "#9CCBB4"
        return "#E7D8A6"

    grp_sub = folium.FeatureGroup(name="Subcuencas (9)", show=True)
    for feat in subs["features"]:
        p = feat["properties"]
        outlet_line = (
            "<br><b style=\"color:#C0392B\">Subcuenca de salida (outlet)</b>"
            if p["outlet"] else "")
        popup = folium.Popup(
            f"<div style='font-family:system-ui;font-size:13px;min-width:180px'>"
            f"<b style='color:{COL_DEEP}'>{p['nombre']}</b><br>"
            f"<span style='color:#5B6B78'>Elevación:</span> {p['elev_m']:,} m<br>"
            f"<span style='color:#5B6B78'>Área:</span> {p['area_km2']:,} km²"
            f"{outlet_line}"
            f"</div>",
            max_width=260,
        )
        folium.GeoJson(
            feat,
            style_function=lambda _f, e=p["elev_m"]: {
                "fillColor": color_elev(e), "color": "#37474F",
                "weight": 1.2, "fillOpacity": 0.60,
            },
            highlight_function=lambda _f: {"weight": 3, "fillOpacity": 0.80},
            tooltip=folium.Tooltip(
                f"<b>{p['nombre']}</b> · {p['elev_m']:,} m"),
            popup=popup,
        ).add_to(grp_sub)
        # Etiqueta del nombre en el centroide
        folium.map.Marker(
            [p["cy"], p["cx"]],
            icon=folium.DivIcon(
                html=(
                    f"<div style='font-family:system-ui;font-size:11px;"
                    f"font-weight:600;color:#12212E;text-shadow:0 0 3px #fff,"
                    f"0 0 3px #fff,0 0 3px #fff;white-space:nowrap'>"
                    f"{p['nombre']}</div>"),
                icon_size=(0, 0), icon_anchor=(0, 0),
            ),
        ).add_to(grp_sub)
    grp_sub.add_to(m)

    # Estación de aforo (marcador destacado)
    folium.Marker(
        [est["lat"], est["lon"]],
        icon=folium.Icon(color="red", icon="tint", prefix="fa"),
        tooltip=f"Estación de aforo {est['nombre']}",
        popup=folium.Popup(
            f"<div style='font-family:system-ui;font-size:13px;min-width:200px'>"
            f"<b style='color:{COL_CRIT}'>Estación de aforo</b><br>"
            f"<b>{est['nombre']}</b><br>"
            f"<span style='color:#5B6B78'>Código:</span> {est['codigo']}<br>"
            f"<span style='color:#5B6B78'>Elevación:</span> {est['elev_m']:,} m<br>"
            f"<span style='color:#5B6B78'>Fuente:</span> {est['fuente']}<br>"
            f"<span style='color:#5B6B78'>Coord.:</span> {est['lat']}, {est['lon']}"
            f"</div>",
            max_width=300,
        ),
    ).add_to(m)
    folium.CircleMarker(
        [est["lat"], est["lon"]], radius=15, color=COL_CRIT,
        fill=False, weight=2, opacity=0.85,
    ).add_to(m)

    Fullscreen(title="Pantalla completa",
               title_cancel="Salir", position="topleft").add_to(m)
    folium.LayerControl(collapsed=True, position="topright").add_to(m)

    # Leyenda de elevación
    leyenda = """
    <div style="position:absolute;bottom:18px;left:12px;z-index:9999;
      background:rgba(255,255,255,0.94);padding:9px 12px;border-radius:8px;
      box-shadow:0 1px 6px rgba(15,40,60,.22);font-family:system-ui;font-size:12px;
      line-height:1.55;color:#12212E;border:1px solid #DDE3EA">
      <b style="color:#134E6F;letter-spacing:.03em">ELEVACIÓN (m)</b><br>
      <span style="display:inline-block;width:12px;height:12px;background:#2E6E8E;
        border:1px solid #37474F;vertical-align:middle"></span> &lt; 1 000<br>
      <span style="display:inline-block;width:12px;height:12px;background:#4FA3B8;
        border:1px solid #37474F;vertical-align:middle"></span> 1 000 – 2 500<br>
      <span style="display:inline-block;width:12px;height:12px;background:#9CCBB4;
        border:1px solid #37474F;vertical-align:middle"></span> 2 500 – 3 800<br>
      <span style="display:inline-block;width:12px;height:12px;background:#E7D8A6;
        border:1px solid #37474F;vertical-align:middle"></span> &gt; 3 800<br>
      <span style="color:#C0392B;font-size:15px;vertical-align:middle">&#9679;</span>
        Estación de aforo
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
            textfont=dict(family="IBM Plex Mono, monospace", size=13,
                          color=COL_INK),
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
                         textfont=dict(family="IBM Plex Mono, monospace",
                                       size=13, color=COL_INK),
                         cliponaxis=False, width=0.62)],
        ))
    fig.frames = frames

    steps = [dict(method="animate", label=f"{ld}",
                  args=[[str(ld)], dict(mode="immediate",
                        frame=dict(duration=0, redraw=True),
                        transition=dict(duration=350, easing="cubic-in-out"))])
             for ld in leads]

    fig.update_layout(
        template="plotly_white",
        height=430,
        margin=dict(l=54, r=20, t=20, b=96),
        font=dict(family="IBM Plex Sans, sans-serif", size=13, color=COL_INK),
        yaxis=dict(title="NSE (eficiencia Nash–Sutcliffe)", range=[0, 1.0],
                   gridcolor=COL_BORDER, zeroline=False,
                   tickfont=dict(family="IBM Plex Mono, monospace")),
        xaxis=dict(title="", tickfont=dict(size=13)),
        plot_bgcolor=COL_SURF, paper_bgcolor=COL_SURF,
        showlegend=False,
        updatemenus=[dict(
            type="buttons", direction="left", showactive=False,
            x=0, xanchor="left", y=-0.30, yanchor="top",
            pad=dict(t=0, r=8),
            bgcolor="#EEF2F6", bordercolor=COL_BORDER,
            font=dict(size=12, family="IBM Plex Sans, sans-serif"),
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
                                        family="IBM Plex Mono, monospace")),
            tickcolor=COL_BORDER,
            font=dict(size=11, family="IBM Plex Mono, monospace"),
            steps=steps,
        )],
    )
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

    fig.update_layout(
        template="plotly_white", hovermode="x unified",
        margin=dict(l=58, r=18, t=18, b=36), height=420,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left",
                    x=0, font=dict(size=12, family="IBM Plex Sans, sans-serif")),
        font=dict(family="IBM Plex Sans, sans-serif", size=13, color=COL_INK),
        yaxis=dict(title="Caudal medio mensual (m³/s)", gridcolor=COL_BORDER,
                   zeroline=False, rangemode="tozero"),
        xaxis=dict(title="", gridcolor=COL_BORDER),
        plot_bgcolor=COL_SURF, paper_bgcolor=COL_SURF,
        hoverlabel=dict(font=dict(family="IBM Plex Mono, monospace", size=12)))

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
        annotation_font=dict(color=COL_CRIT, size=12,
                             family="IBM Plex Mono, monospace"))

    # Conmutador lead 1 / lead 7 (botones que alternan visibilidad).
    def vis_para(lead):
        v = []
        for i in range(n_modelos_traza):
            v.append(i in vis_lead[lead])
        v.append(True)     # observado siempre visible
        return v

    fig.update_layout(
        template="plotly_white", hovermode="x unified",
        margin=dict(l=58, r=18, t=54, b=36), height=440,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left",
                    x=0, font=dict(size=12, family="IBM Plex Sans, sans-serif")),
        font=dict(family="IBM Plex Sans, sans-serif", size=13, color=COL_INK),
        yaxis=dict(title="Caudal (m³/s)", gridcolor=COL_BORDER, zeroline=False,
                   rangemode="tozero"),
        xaxis=dict(title="", gridcolor=COL_BORDER),
        plot_bgcolor=COL_SURF, paper_bgcolor=COL_SURF,
        hoverlabel=dict(font=dict(family="IBM Plex Mono, monospace", size=12)),
        updatemenus=[dict(
            type="buttons", direction="left", showactive=True,
            x=0, xanchor="left", y=1.16, yanchor="top", pad=dict(t=0, r=8),
            bgcolor="#EEF2F6", bordercolor=COL_BORDER, active=0,
            font=dict(size=12, family="IBM Plex Sans, sans-serif"),
            buttons=[
                dict(label="Horizonte 1 día", method="update",
                     args=[{"visible": vis_para(1)}]),
                dict(label="Horizonte 7 días", method="update",
                     args=[{"visible": vis_para(7)}]),
            ])])

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

    fig.update_layout(
        template="plotly_white", hovermode="x unified",
        margin=dict(l=52, r=18, t=18, b=36), height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left",
                    x=0, font=dict(size=12, family="IBM Plex Sans, sans-serif")),
        font=dict(family="IBM Plex Sans, sans-serif", size=13, color=COL_INK),
        yaxis=dict(title="Anomalía (°C)", gridcolor=COL_BORDER, zeroline=False,
                   tickfont=dict(family="IBM Plex Mono, monospace")),
        xaxis=dict(title="", gridcolor=COL_BORDER),
        plot_bgcolor=COL_SURF, paper_bgcolor=COL_SURF,
        hoverlabel=dict(font=dict(family="IBM Plex Mono, monospace", size=12)))

    return fig.to_html(
        include_plotlyjs=False, full_html=False, div_id="grafico-enso",
        config={"displayModeBar": False, "responsive": True})


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

    fig.update_layout(
        template="plotly_white", height=380, showlegend=False,
        margin=dict(l=52, r=18, t=42, b=44),
        font=dict(family="IBM Plex Sans, sans-serif", size=13, color=COL_INK),
        plot_bgcolor=COL_SURF, paper_bgcolor=COL_SURF,
        hoverlabel=dict(font=dict(family="IBM Plex Mono, monospace", size=12)),
        xaxis=dict(domain=[0.0, 0.46], title="Rezago (días)",
                   gridcolor=COL_BORDER, zeroline=False,
                   tickfont=dict(family="IBM Plex Mono, monospace")),
        yaxis=dict(title="ACF del caudal", gridcolor=COL_BORDER, zeroline=False,
                   range=[0, 1.05], tickfont=dict(family="IBM Plex Mono, monospace")),
        xaxis2=dict(domain=[0.56, 1.0], title="Rezago lluvia→caudal (días)",
                    gridcolor=COL_BORDER, zeroline=False,
                    tickfont=dict(family="IBM Plex Mono, monospace")),
        yaxis2=dict(title="CCF lluvia→caudal", anchor="x2", gridcolor=COL_BORDER,
                    zeroline=False, tickfont=dict(family="IBM Plex Mono, monospace")),
        annotations=[
            dict(text="<b>ACF del caudal</b> (lags 0–30)", xref="paper",
                 yref="paper", x=0.0, y=1.12, showarrow=False, xanchor="left",
                 font=dict(size=12.5, color=COL_INK)),
            dict(text="<b>CCF lluvia→caudal</b> (lags 0–15)", xref="paper",
                 yref="paper", x=0.56, y=1.12, showarrow=False, xanchor="left",
                 font=dict(size=12.5, color=COL_INK)),
        ])
    # Anotaciones didácticas (tras fijar layout.annotations para no perderlas).
    fig.add_annotation(
        xref="x", yref="y", x=1, y=float(a[a["lag"] == 1]["acf"].iloc[0]),
        text="lag-1 ≈ 0.99", showarrow=True, arrowhead=2, ax=36, ay=-24,
        font=dict(size=11, color=COL_DEEP, family="IBM Plex Mono, monospace"),
        arrowcolor=COL_DEEP)
    fig.add_annotation(
        xref="x2", yref="y2", x=int(pico["lag"]), y=float(pico["ccf"]),
        text=f"pico en lag ≈ {int(pico['lag'])} d", showarrow=True, arrowhead=2,
        ax=28, ay=-34,
        font=dict(size=11, color=COL_DEEP, family="IBM Plex Mono, monospace"),
        arrowcolor=COL_DEEP)

    return fig.to_html(
        include_plotlyjs=False, full_html=False, div_id="grafico-eda",
        config={"displayModeBar": False, "responsive": True})


# ── KPI cards (resumen) ────────────────────────────────────────────────────────
def kpi_cards(serie: pd.DataFrame) -> str:
    dias_alerta = int((serie["obs"] >= UMBRAL_Q90).sum())
    tarjetas = [
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
    for lab, val, uni, desc, estado in tarjetas:
        uni_html = f"<span class='kpi-uni'>{uni}</span>" if uni else ""
        out.append(
            f"<article class='kpi kpi-{estado}' tabindex='0'>"
            f"<p class='kpi-lab'>{lab}</p>"
            f"<p class='kpi-val'>{val}{uni_html}</p>"
            f"<p class='kpi-desc'>{desc}</p>"
            f"</article>")
    return f"<div class='kpi-grid'>{''.join(out)}</div>"


# ── Ensamblado del HTML final ─────────────────────────────────────────────────
def ensamblar(mapa_html, serie_div, anim_div, tabla_html, kpi_html,
              mensual_div, evento_div, enso_div, eda_div, imgs, meta,
              serie) -> str:
    est = meta["estacion"]
    area = meta["cuenca_area_km2"]
    nsub = meta["n_subcuencas"]
    mapa_srcdoc = mapa_html.replace("&", "&amp;").replace('"', "&quot;")

    # Logo (header): imagen embebida si existe; si no, respaldo tipográfico.
    if imgs.get("logo"):
        logo_html = (
            f'<img class="brand-logo" src="{imgs["logo"]}" alt="UTEC" '
            f'height="40" loading="lazy">')
    else:
        logo_html = '<span class="brand-logo-txt" aria-hidden="true">UTEC</span>'

    integrantes = [
        ("Luis Alonzo Contreras Perez", "Datos, modelado y evaluación"),
        ("Diego Alonso Javier Mijahuanca Quispe", "Análisis exploratorio, visualización y dashboard"),
    ]

    def _iniciales(nombre: str) -> str:
        partes = [p for p in nombre.split() if p and p[0].isalpha()]
        if not partes:
            return "·"
        if len(partes) == 1:
            return partes[0][:2].upper()
        return (partes[0][0] + partes[-1][0]).upper()

    filas_eq = []
    for i, (n, r) in enumerate(integrantes, start=1):
        foto = imgs.get(f"foto_{i}")
        if foto:
            avatar = (f"<img class='eq-foto' src='{foto}' alt='' "
                      f"loading='lazy'>")
        else:
            avatar = (f"<span class='eq-foto eq-foto-txt' aria-hidden='true'>"
                      f"{_iniciales(n)}</span>")
        filas_eq.append(
            f"<li>{avatar}<span class='eq-text'>"
            f"<span class='eq-nombre'>{n}</span>"
            f"<span class='eq-rol'>{r}</span></span></li>")
    equipo_html = "".join(filas_eq)

    return f"""
<a class="skip-link" href="#contenido">Saltar al contenido</a>

<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true"></span>
      <span class="brand-text">
        <span class="brand-title">HidroAlerta Chancay–Huaral</span>
        <span class="brand-sub">Sistema de pronóstico de caudal y alerta de crecidas</span>
      </span>
    </div>
    <div class="topbar-right">
      <div class="status-pill" role="status" aria-label="Umbral de alerta">
        <span class="status-dot" aria-hidden="true"></span>
        <span class="status-txt">Umbral de alerta Q90</span>
        <span class="status-num">{UMBRAL_Q90} m³/s</span>
      </div>
      <span class="brand-logo-wrap" title="Universidad de Ingeniería y Tecnología">
        {logo_html}
      </span>
    </div>
  </div>
</header>

<main id="contenido" class="wrap">

  <section class="intro reveal">
    <p class="eyebrow">Concurso ANA 2026 · Río Chancay–Huaral, Perú</p>
    <h1 class="titulo">Monitoreo de pronóstico de caudal y alerta temprana de crecidas</h1>
    <p class="subtitulo">Estación de aforo {est['nombre']} (código {est['codigo']}).
    Cuenca de {area:,.0f} km² con {nsub} subcuencas. El pronóstico probabilístico
    (mediana y banda de incertidumbre) se emite de forma continua; el caudal
    observado se compara donde existe aforo.</p>
  </section>

  <section class="reveal" aria-label="Indicadores resumen">
    {kpi_html}
  </section>

  <section class="panel reveal">
    <div class="panel-head">
      <span class="sec-idx">01</span>
      <div>
        <h2>Cuenca y estación de aforo</h2>
        <p class="lead">Las {nsub} subcuencas están coloreadas por elevación, de
        la costa a la cabecera andina. La estación de aforo {est['nombre']} marca
        el punto de salida de la cuenca; active las capas y consulte cada
        subcuenca en el mapa.</p>
      </div>
    </div>
    <div class="mapa-box">
      <iframe title="Mapa interactivo de la cuenca Chancay–Huaral"
              class="mapa-iframe" srcdoc="{mapa_srcdoc}" loading="lazy"></iframe>
    </div>
  </section>

  <section class="panel reveal">
    <div class="panel-head">
      <span class="sec-idx">02</span>
      <div>
        <h2>Serie de caudal: observado frente a pronóstico</h2>
        <p class="lead">Elija el <b>modelo</b> y el <b>horizonte</b> de pronóstico:
        el gráfico muestra la mediana P50 y la banda de incertidumbre P10–P90
        para 2024–2025. Los puntos marcan el caudal observado, solo donde hay
        aforo; los tramos sombreados señalan periodos sin observación, durante los
        cuales el pronóstico continúa (valor operacional). La línea punteada roja
        es el umbral de alerta. HydroST solo dispone de horizonte a 1 día;
        Persistencia es un baseline puntual (sin banda).</p>
      </div>
    </div>
    {serie_div}
  </section>

  <section class="panel reveal">
    <div class="panel-head">
      <span class="sec-idx">03</span>
      <div>
        <h2>Habilidad predictiva según el horizonte</h2>
        <p class="lead">Eficiencia (NSE) de cada modelo al aumentar el horizonte de
        pronóstico. Mueva el deslizador o pulse reproducir: la Persistencia (naive)
        parte alta a 1 día pero decae con rapidez, mientras que el modelo propuesto
        sostiene mejor la habilidad a varios días.</p>
      </div>
    </div>
    {anim_div}
    <p class="nota">Barras de NSE por modelo; la línea base en cero indica ausencia
    de habilidad respecto a la media. HydroST solo se evalúa a 2 días de
    horizonte, por lo que aparece únicamente en ese paso.</p>
  </section>

  <section class="panel reveal">
    <div class="panel-head">
      <span class="sec-idx">04</span>
      <div>
        <h2>Métricas por horizonte</h2>
        <p class="lead">Exactitud (NSE, KGE, MAE), calidad probabilística (CRPS) y
        capacidad de alerta (CSI, POD, FAR) para horizontes de 1 a 14 días.</p>
      </div>
    </div>
    {tabla_html}
  </section>

  <section class="panel reveal">
    <div class="panel-head">
      <span class="sec-idx">05</span>
      <div>
        <h2>Producto mensual de disponibilidad hídrica</h2>
        <p class="lead">Producto de gestión a escala mensual, complementario a la
        alerta diaria de crecidas: caudal medio mensual observado frente al
        pronóstico (P50 y banda P10–P90) y la climatología estacional. El techo de
        habilidad a esta escala lo fija la climatología (la marcada estacionalidad
        de la cuenca); el modelo aporta valor sobre todo en las anomalías, cuando
        el año se aparta del régimen típico.</p>
      </div>
    </div>
    {mensual_div}
    <p class="nota">Serie mensual 2021–2026. Los círculos abiertos son el caudal
    medio mensual observado; la línea discontinua gris es la climatología (media
    del mes). Meses sin observación quedan como pronóstico activo.</p>
  </section>

  <section class="panel reveal">
    <div class="panel-head">
      <span class="sec-idx">06</span>
      <div>
        <h2>Zoom al evento de crecida (febrero de 2024)</h2>
        <p class="lead">Detalle de enero a marzo de 2024, la temporada húmeda con
        el pico de crecida más marcado del periodo de prueba. Se superponen el
        caudal observado y la mediana de cada modelo para comparar quién sigue el
        pico. Use los botones para alternar entre horizonte de 1 y 7 días: a un día
        el seguimiento es estrecho; a siete, la anticipación depende de la lluvia
        pronosticada y las trazas se separan del observado.</p>
      </div>
    </div>
    {evento_div}
    <p class="nota">La línea gruesa (agua) es el modelo propuesto RA-TFT; las
    demás, de referencia. La línea punteada roja es el umbral de alerta Q90.</p>
  </section>

  <section class="panel reveal">
    <div class="panel-head">
      <span class="sec-idx">07</span>
      <div>
        <h2>Señal ENSO: Niño costero frente a ONI global</h2>
        <p class="lead">Índices de El Niño–Oscilación del Sur relevantes para la
        cuenca: el <b>Niño costero</b> (anomalía frente a la costa peruana) y el
        <b>ONI global</b> (región Niño 3.4, Pacífico central). Su efecto sobre el
        caudal es de <b>signo opuesto</b>: un Niño costero cálido intensifica la
        lluvia en la vertiente occidental (más caudal), mientras que un ONI global
        cálido tiende a secar la sierra que alimenta la cabecera (menos caudal).
        Distinguir ambos es clave para interpretar los pronósticos estacionales.</p>
      </div>
    </div>
    {enso_div}
    <p class="nota">Anomalías mensuales (°C). La banda gris central marca el rango
    neutro (±0,5 °C); por encima se considera condición cálida (El Niño) y por
    debajo, fría (La Niña). El pico costero de 2017 y el evento 2023–2024 ilustran
    episodios de fuerte impacto local.</p>
  </section>

  <section class="panel reveal">
    <div class="panel-head">
      <span class="sec-idx">08</span>
      <div>
        <h2>Análisis exploratorio: memoria y tiempo de respuesta</h2>
        <p class="lead">Dos correlogramas que sustentan el diseño del modelo. La
        <b>autocorrelación (ACF)</b> del caudal mide su memoria propia; la
        <b>correlación cruzada (CCF)</b> lluvia→caudal mide cuánto tarda la
        precipitación en traducirse en escorrentía a la salida de la cuenca.</p>
      </div>
    </div>
    {eda_div}
    <p class="nota">La ACF cae muy despacio y el <b>lag-1 ≈ 0,99</b>: el caudal de
    hoy explica casi por completo el de mañana, lo que sustenta la fuerte
    persistencia y el techo del baseline a 1 día. La CCF alcanza su máximo hacia
    el <b>lag ≈ 4 días</b>, una estimación del tiempo de concentración de la
    cuenca: la lluvia se refleja en el caudal con unos días de retardo, margen que
    habilita la alerta temprana.</p>
  </section>

  <section class="panel reveal">
    <div class="panel-head">
      <span class="sec-idx">09</span>
      <div>
        <h2>Conclusiones y limitaciones</h2>
      </div>
    </div>
    <div class="conc-grid">
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
    </div>
  </section>

</main>

<footer class="foot">
  <div class="foot-inner">
    <div class="foot-col">
      <h4>Equipo</h4>
      <ul class="equipo">{equipo_html}</ul>
    </div>
    <div class="foot-col">
      <h4>Fuentes de datos</h4>
      <ul class="fuentes">
        <li><span class="fu-k">Caudal observado</span>
          <span class="fu-v">SENAMHI / ANA — estación {est['nombre']} (SNIRH,
          código {est['codigo']}). Descarga: julio 2026.</span></li>
        <li><span class="fu-k">Forzantes meteorológicas</span>
          <span class="fu-v">ERA5-Land (Copernicus / ECMWF). Descarga: junio 2026.</span></li>
        <li><span class="fu-k">Precipitación grillada</span>
          <span class="fu-v">PISCOp v3.0 (SENAMHI). Descarga: junio 2026.</span></li>
      </ul>
    </div>
    <div class="foot-col">
      <h4>Sobre el proyecto</h4>
      <p class="foot-p">HidroAlerta Chancay–Huaral integra modelos de aprendizaje
      automático con hidrología de la cuenca para anticipar crecidas y apoyar la
      gestión del riesgo. Presentado al Concurso ANA 2026.</p>
    </div>
  </div>
  <p class="copyright">Todos los derechos reservados © 2026 — Equipo HidroAlerta.
  La metodología está en publicación en preparación y no se incluye aquí.
  Actualizado el {FECHA_ACTUALIZACION}.</p>
</footer>
"""


# ── CSS ────────────────────────────────────────────────────────────────────────
def estilos() -> str:
    return f"""
:root {{
  --bg:{COL_BG}; --surf:{COL_SURF}; --ink:{COL_INK}; --border:{COL_BORDER};
  --accent:{COL_ACCENT}; --deep:{COL_DEEP};
  --crit:{COL_CRIT}; --ok:{COL_OK}; --warn:{COL_WARN}; --muted:{COL_MUTED};
  --sans:'IBM Plex Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  --mono:'IBM Plex Mono','SFMono-Regular',Consolas,monospace;
  --shadow:0 1px 2px rgba(18,33,46,.05),0 4px 16px rgba(18,33,46,.05);
  --radius:12px;
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:var(--sans); line-height:1.6; font-size:16px;
  -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility;
}}
h1,h2,h3,h4 {{ margin:0; line-height:1.2; text-wrap:balance; color:var(--ink); }}
p {{ margin:0; }}
.mono {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}

.skip-link {{
  position:absolute; left:-9999px; top:0; z-index:1000; background:var(--deep);
  color:#fff; padding:10px 16px; border-radius:0 0 8px 0; font-size:14px;
}}
.skip-link:focus {{ left:0; }}

/* ── Header sticky ────────────────────────────────────────────────── */
.topbar {{
  position:sticky; top:0; z-index:50; background:rgba(255,255,255,.92);
  backdrop-filter:saturate(160%) blur(8px);
  border-bottom:1px solid var(--border);
}}
.topbar-inner {{
  max-width:1180px; margin:0 auto; padding:11px 24px;
  display:flex; align-items:center; justify-content:space-between; gap:16px;
}}
.brand {{ display:flex; align-items:center; gap:12px; min-width:0; }}
.brand-mark {{
  width:12px; height:26px; border-radius:3px; flex:none;
  background:linear-gradient(180deg,var(--accent),var(--deep));
}}
.brand-text {{ display:flex; flex-direction:column; line-height:1.25; min-width:0; }}
.brand-title {{ font-weight:600; font-size:16px; letter-spacing:-.01em; }}
.brand-sub {{ font-size:12.5px; color:var(--muted);
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.status-pill {{
  display:inline-flex; align-items:center; gap:8px; flex:none;
  background:#FCEEEC; border:1px solid #F0CFC9; color:var(--crit);
  padding:6px 12px; border-radius:999px; font-size:12.5px; font-weight:500;
}}
.status-dot {{ width:8px; height:8px; border-radius:50%; background:var(--crit);
  box-shadow:0 0 0 3px rgba(192,57,43,.16); }}
.status-txt {{ text-transform:uppercase; letter-spacing:.05em; font-size:11px;
  font-weight:600; }}
.status-num {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-weight:600; }}
.topbar-right {{ display:flex; align-items:center; gap:14px; flex:none; }}
.brand-logo-wrap {{ display:inline-flex; align-items:center; }}
.brand-logo {{ display:block; height:40px; width:auto; }}
.brand-logo-txt {{ font-family:var(--mono); font-weight:600; font-size:15px;
  letter-spacing:.06em; color:var(--deep); border:1.5px solid var(--border);
  border-radius:8px; padding:5px 10px; line-height:1; }}

/* ── Layout ───────────────────────────────────────────────────────── */
.wrap {{ max-width:1180px; margin:0 auto; padding:34px 24px 20px;
  display:flex; flex-direction:column; gap:26px; }}
.eyebrow {{ text-transform:uppercase; letter-spacing:.09em; font-size:12px;
  font-weight:600; color:var(--accent); margin-bottom:10px; }}
.titulo {{ font-size:clamp(1.7rem,3.4vw,2.35rem); font-weight:600;
  letter-spacing:-.02em; max-width:20ch; }}
.subtitulo {{ font-size:16px; color:var(--muted); margin-top:12px; max-width:70ch; }}

/* ── KPI cards ────────────────────────────────────────────────────── */
.kpi-grid {{ display:grid; gap:14px;
  grid-template-columns:repeat(5,minmax(0,1fr)); }}
.kpi {{
  background:var(--surf); border:1px solid var(--border);
  border-radius:var(--radius); padding:16px 16px 15px; box-shadow:var(--shadow);
  position:relative; overflow:hidden;
  transition:transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}}
.kpi::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
  background:var(--accent); }}
.kpi-crit::before {{ background:var(--crit); }}
.kpi:hover, .kpi:focus-visible {{
  transform:translateY(-3px);
  box-shadow:0 6px 22px rgba(18,33,46,.10); border-color:#C9D3DC; outline:none;
}}
.kpi:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
.kpi-lab {{ font-size:11px; font-weight:600; text-transform:uppercase;
  letter-spacing:.06em; color:var(--muted); }}
.kpi-val {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:2.05rem; font-weight:600; color:var(--deep); line-height:1.1;
  margin-top:8px; letter-spacing:-.02em; }}
.kpi-crit .kpi-val {{ color:var(--crit); }}
.kpi-uni {{ font-size:.9rem; font-weight:500; color:var(--muted);
  margin-left:5px; letter-spacing:0; }}
.kpi-desc {{ font-size:12px; color:var(--muted); margin-top:9px; line-height:1.45; }}

/* ── Paneles ──────────────────────────────────────────────────────── */
.panel {{ background:var(--surf); border:1px solid var(--border);
  border-radius:var(--radius); padding:24px 26px; box-shadow:var(--shadow); }}
.panel-head {{ display:flex; gap:16px; align-items:flex-start; margin-bottom:18px; }}
.sec-idx {{ font-family:var(--mono); font-size:13px; font-weight:600;
  color:var(--accent); background:#E8F1F4; border:1px solid #CFE2E8;
  border-radius:8px; padding:5px 9px; flex:none; line-height:1; margin-top:3px; }}
.panel-head h2 {{ font-size:1.3rem; font-weight:600; letter-spacing:-.01em; }}
.lead {{ color:var(--muted); font-size:14.5px; margin-top:7px; max-width:82ch; }}
.nota {{ font-size:12.5px; color:var(--muted); margin-top:14px; max-width:92ch;
  line-height:1.55; }}
.nota b {{ color:var(--ink); font-weight:600; }}

.mapa-box {{ border-radius:10px; overflow:hidden; border:1px solid var(--border); }}
.mapa-iframe {{ width:100%; height:560px; border:0; display:block; }}

/* ── Serie de pronóstico interactiva (selectores) ─────────────────── */
.fc-controls {{ display:flex; flex-wrap:wrap; align-items:flex-end; gap:16px;
  margin-bottom:14px; padding:14px 16px; background:#F7FAFC;
  border:1px solid var(--border); border-radius:10px; }}
.fc-field {{ display:flex; flex-direction:column; gap:5px; }}
.fc-field-lab {{ font-size:11px; font-weight:600; text-transform:uppercase;
  letter-spacing:.06em; color:var(--muted); }}
.fc-select {{
  appearance:none; -webkit-appearance:none; font-family:var(--sans);
  font-size:14px; font-weight:500; color:var(--ink); background:var(--surf);
  border:1.5px solid var(--border); border-radius:8px; padding:8px 34px 8px 12px;
  min-width:170px; cursor:pointer; line-height:1.3;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%235B6B78' d='M1 1l5 5 5-5'/%3E%3C/svg%3E");
  background-repeat:no-repeat; background-position:right 12px center;
  transition:border-color .16s ease, box-shadow .16s ease;
}}
.fc-select:hover {{ border-color:#B9C6D0; }}
.fc-select:focus-visible {{ outline:none; border-color:var(--accent);
  box-shadow:0 0 0 3px rgba(11,110,140,.18); }}
.fc-select:disabled {{ opacity:.5; cursor:not-allowed; }}
.fc-readout {{ display:flex; flex-direction:column; gap:3px; margin-left:auto;
  text-align:right; }}
.fc-readout-lab {{ font-size:11px; font-weight:600; text-transform:uppercase;
  letter-spacing:.05em; color:var(--muted); }}
.fc-readout-val {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:1.5rem; font-weight:600; color:var(--deep); line-height:1.1; }}
.fc-plot {{ width:100%; min-height:460px; }}

/* ── Tabla de métricas ────────────────────────────────────────────── */
.tabla-scroll {{ overflow-x:auto; border:1px solid var(--border);
  border-radius:10px; }}
table.metricas {{ width:100%; border-collapse:collapse; font-size:13.5px;
  min-width:680px; }}
table.metricas th {{ background:var(--deep); color:#fff; padding:10px 12px;
  text-align:right; font-weight:600; font-size:12.5px; letter-spacing:.02em;
  position:sticky; top:0; white-space:nowrap; }}
table.metricas th:nth-child(1), table.metricas th:nth-child(2) {{ text-align:left; }}
table.metricas td {{ padding:9px 12px; border-bottom:1px solid #EDF1F5; }}
table.metricas tbody tr:last-child td {{ border-bottom:0; }}
table.metricas td.num {{ text-align:right; font-family:var(--mono);
  font-variant-numeric:tabular-nums; color:#33424E; }}
table.metricas td.modelo {{ font-weight:500; white-space:nowrap; }}
table.metricas td.modelo-prop {{ font-weight:700; color:var(--accent); }}
table.metricas td.modelo-base {{ color:var(--muted); }}
table.metricas td.lead-cell {{ background:#F4F8FA; vertical-align:middle;
  border-right:1px solid var(--border); white-space:nowrap; }}
.lead-lab {{ display:block; font-weight:600; color:var(--deep); }}
.lead-n {{ display:block; font-family:var(--mono); font-size:11px;
  color:var(--muted); margin-top:2px; }}
td.chip-best {{ position:relative; }}
td.chip-best::after {{ content:""; position:absolute; inset:4px 6px;
  background:rgba(46,139,111,.12); border:1px solid rgba(46,139,111,.35);
  border-radius:6px; z-index:0; }}
td.chip-best {{ color:var(--ok); font-weight:700; }}

/* ── Conclusiones ─────────────────────────────────────────────────── */
.conc-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:26px; }}
.conc-h {{ font-size:13px; text-transform:uppercase; letter-spacing:.05em;
  font-weight:700; padding-bottom:8px; margin-bottom:10px;
  border-bottom:2px solid var(--border); }}
.conc-ok {{ color:var(--ok); border-color:rgba(46,139,111,.35); }}
.conc-warn {{ color:var(--warn); border-color:rgba(214,137,16,.35); }}
.conc-list {{ margin:0; padding-left:1.15em; display:flex; flex-direction:column;
  gap:9px; }}
.conc-list li {{ font-size:14px; color:#33424E; line-height:1.5; }}

/* ── Footer ───────────────────────────────────────────────────────── */
.foot {{ background:#0E2A38; color:#C7D5DD; margin-top:14px; }}
.foot-inner {{ max-width:1180px; margin:0 auto; padding:38px 24px 26px;
  display:grid; grid-template-columns:1fr 1.3fr 1.3fr; gap:38px; }}
.foot h4 {{ color:#8FCBDC; font-size:12px; text-transform:uppercase;
  letter-spacing:.07em; margin-bottom:14px; font-weight:600; }}
.equipo {{ list-style:none; padding:0; margin:0; display:flex;
  flex-direction:column; gap:2px; }}
.equipo li {{ padding:9px 0; border-bottom:1px solid #1C3E4D; display:flex;
  flex-direction:row; align-items:center; gap:12px; }}
.equipo li:last-child {{ border-bottom:0; }}
.eq-foto {{ width:44px; height:44px; border-radius:50%; flex:none;
  object-fit:cover; display:inline-flex; align-items:center;
  justify-content:center; border:1.5px solid #2A5464; background:#123240; }}
.eq-foto-txt {{ font-family:var(--mono); font-weight:600; font-size:15px;
  color:#8FCBDC; letter-spacing:.02em; }}
.eq-text {{ display:flex; flex-direction:column; min-width:0; }}
.eq-nombre {{ color:#fff; font-weight:600; font-size:14px; }}
.eq-rol {{ color:#9DB3BF; font-size:12.5px; }}
.fuentes {{ list-style:none; padding:0; margin:0; display:flex;
  flex-direction:column; gap:11px; }}
.fuentes li {{ display:flex; flex-direction:column; gap:2px; }}
.fu-k {{ font-size:11px; text-transform:uppercase; letter-spacing:.05em;
  color:#8FCBDC; font-weight:600; }}
.fu-v {{ font-size:13px; color:#B4C6D0; line-height:1.45; }}
.foot-p {{ font-size:13px; color:#B4C6D0; line-height:1.55; }}
.copyright {{ max-width:1180px; margin:0 auto; padding:16px 24px 30px;
  font-size:12px; color:#7E97A4; border-top:1px solid #1C3E4D; line-height:1.55; }}

/* ── Movimiento con propósito ─────────────────────────────────────── */
/* Solo se oculta si hay JS (clase js-on en <html>); sin JS todo es visible. */
.js-on .reveal {{ opacity:0; transform:translateY(14px);
  transition:opacity .55s ease, transform .55s ease; }}
.js-on .reveal.is-visible {{ opacity:1; transform:none; }}

@media (prefers-reduced-motion:reduce) {{
  html {{ scroll-behavior:auto; }}
  .reveal {{ opacity:1; transform:none; transition:none; }}
  .kpi {{ transition:none; }}
  .kpi:hover, .kpi:focus-visible {{ transform:none; }}
}}

/* ── Responsive ───────────────────────────────────────────────────── */
@media (max-width:960px) {{
  .kpi-grid {{ grid-template-columns:repeat(2,1fr); }}
  .foot-inner {{ grid-template-columns:1fr 1fr; }}
}}
@media (max-width:680px) {{
  .topbar-inner {{ padding:10px 16px; }}
  .brand-sub {{ display:none; }}
  .topbar-right {{ gap:10px; }}
  .brand-logo, .brand-logo-txt {{ display:none; }}
  .wrap {{ padding:24px 16px 14px; }}
  .panel {{ padding:18px 16px; }}
  .panel-head {{ gap:12px; }}
  .kpi-grid {{ grid-template-columns:1fr 1fr; }}
  .conc-grid {{ grid-template-columns:1fr; gap:20px; }}
  .foot-inner {{ grid-template-columns:1fr; gap:26px; }}
  .mapa-iframe {{ height:440px; }}
  .fc-controls {{ gap:12px; }}
  .fc-select {{ min-width:0; width:100%; }}
  .fc-field {{ flex:1 1 44%; }}
  .fc-readout {{ margin-left:0; text-align:left; flex:1 1 100%; }}
}}
"""


# ── Script de interacción (reveal on load, respeta reduced-motion) ────────────
JS_REVEAL = """
(function(){
  // Marca que hay JS: solo entonces las secciones parten ocultas (sin JS, visibles).
  document.documentElement.className += ' js-on';
  function run(){
    var reduce = window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var els = Array.prototype.slice.call(document.querySelectorAll('.reveal'));
    var showAll = function(){ els.forEach(function(el){ el.classList.add('is-visible'); }); };
    if (reduce || !('IntersectionObserver' in window)) { showAll(); return; }
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){
        if (e.isIntersecting){ e.target.classList.add('is-visible'); io.unobserve(e.target); }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });
    els.forEach(function(el){ io.observe(el); });
    // Salvaguarda: si algo impide el observer, revela todo pasados 2.5 s.
    setTimeout(showAll, 2500);
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

    var baseLayout = {
      template:'plotly_white', hovermode:'x unified',
      margin:{l:58,r:18,t:18,b:36}, height:460,
      legend:{orientation:'h', yanchor:'bottom', y:1.02, xanchor:'left', x:0,
        font:{size:12, family:'IBM Plex Sans, sans-serif'}},
      font:{family:'IBM Plex Sans, sans-serif', size:13, color:CFG.col_ink},
      yaxis:{title:'Caudal (m³/s)', gridcolor:CFG.col_border, zeroline:false,
        rangemode:'tozero'},
      xaxis:{title:'', gridcolor:CFG.col_border,
        rangeslider:{visible:true, thickness:0.07},
        rangeselector:{ buttons:[
          {count:1,label:'1 m',step:'month',stepmode:'backward'},
          {count:3,label:'3 m',step:'month',stepmode:'backward'},
          {count:6,label:'6 m',step:'month',stepmode:'backward'},
          {count:1,label:'1 a',step:'year',stepmode:'backward'},
          {step:'all',label:'Todo'} ],
          font:{size:11, family:'IBM Plex Sans, sans-serif'},
          bgcolor:'#EEF2F6', activecolor:CFG.colores['RA-TFT'] }},
      plot_bgcolor:CFG.col_surf, paper_bgcolor:CFG.col_surf,
      hoverlabel:{font:{family:'IBM Plex Mono, monospace', size:12}},
      transition:{duration: reduce ? 0 : 350, easing:'cubic-in-out'},
      shapes: shapes.concat([{ type:'line', xref:'paper', yref:'y',
        x0:0, x1:1, y0:CFG.umbral, y1:CFG.umbral,
        line:{color:CFG.col_crit, width:1.6, dash:'dot'}, layer:'above' }]),
      annotations:[{ xref:'paper', yref:'y', x:0.01, y:CFG.umbral, yanchor:'bottom',
        xanchor:'left', showarrow:false,
        text:'Umbral de alerta Q90 = '+CFG.umbral.toFixed(2)+' m³/s',
        font:{color:CFG.col_crit, size:12, family:'IBM Plex Mono, monospace'} }]
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


def main():
    serie, metr, meta, subs, lim, fcast, mens, enso, acf, ccf = cargar()
    imgs = cargar_imagenes()
    print("Datos cargados. Construyendo componentes...")
    if imgs:
        print(f"  Recursos de imagen embebidos: {', '.join(sorted(imgs))}")
    else:
        print("  Sin imágenes en assets/: se usa respaldo tipográfico.")
    mapa_html = construir_mapa(meta, subs, lim)
    cfg_fcast = serie_pronostico_datos(fcast, metr)
    serie_div = bloque_serie_interactiva(cfg_fcast)
    anim_div = construir_animacion(metr)
    tabla_html = tabla_metricas_html(metr)
    kpi_html = kpi_cards(serie)
    mensual_div = construir_mensual(mens)
    evento_div = construir_evento(fcast)
    enso_div = construir_enso(enso)
    eda_div = construir_eda(acf, ccf)
    print("Ensamblando index.html...")
    cuerpo = ensamblar(mapa_html, serie_div, anim_div, tabla_html, kpi_html,
                       mensual_div, evento_div, enso_div, eda_div, imgs,
                       meta, serie)

    doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HidroAlerta Chancay–Huaral · Pronóstico y alerta de caudal</title>
<meta name="description" content="Dashboard de monitoreo: pronóstico de caudal y alerta temprana de crecidas del río Chancay–Huaral (Concurso ANA 2026).">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>{estilos()}</style>
</head>
<body>
{cuerpo}
<script>{JS_REVEAL}</script>
<script>{JS_FORECAST}</script>
</body>
</html>
"""
    out = DOCS / "index.html"
    out.write_text(doc, encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"Generado: {out}  ({kb:.0f} KB)")


if __name__ == "__main__":
    main()
