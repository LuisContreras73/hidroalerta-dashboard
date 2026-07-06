#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Storymap inmersivo «El viaje del agua» — Chancay-Huaral (seguridad hídrica).

Escenografía full-screen sobre un TERRENO 3D real (deck.gl TerrainLayer + nuestro DEM 30/90 m),
con transición 2D→3D por inclinación de cámara, órbita sobre los Andes, red de ríos que se
dibuja, cabeceras resaltadas, y timelapses drapeados (climatología, ERA5 suelo/nieve/vegetación,
y el Ciclón Yaku 2023 con hidrograma OBSERVADO sincronizado).

Este módulo NO lee datos privados: los assets (PNG/GeoJSON/JSON) ya viven curados en el repo
público (docs/media/terrain|clima|evento|era5, data/*.geojson, data/*_meta.json, data/evento.json)
y el JS los carga por fetch relativo en tiempo de ejecución.

Expone:  CDN_HEAD, CSS, JS  (cadenas)  y  recorrido_html(meta, leaderboard_div, forecast_div).
"""
from __future__ import annotations
import json

# CDN: deck.gl (terreno 3D, sin token) + globe.gl (globo del capítulo 1). Autoalojado en unpkg
# (mismo host ya usado por el dashboard). La textura de la Tierra del globo también de unpkg.
CDN_HEAD = """
<!-- Storymap inmersivo: deck.gl (terreno 3D) + globe.gl (globo del cap. 1), por CDN. -->
<script src="https://unpkg.com/deck.gl@8.9.36/dist.min.js" crossorigin=""></script>
<script src="https://unpkg.com/globe.gl@2.32.2/dist/globe.gl.min.js" crossorigin=""></script>
""".strip()


# ── Capítulos ("El viaje del agua"). El texto es legible sin JS (semántico).
# Cada capítulo lleva data-cap=<id>; el JS mapea id → escena (cámara/capas/timelapse).
def _capitulos(meta) -> list:
    est = meta["estacion"]
    area = meta.get("cuenca_area_km2", 3062.6)
    nsub = meta.get("n_subcuencas", 9)
    umbral = meta.get("umbral_q90", meta.get("umbral", 40.9))
    return [
        dict(id="origen", num="01", eyebrow="Seguridad hídrica · Chancay–Huaral",
             titulo="El viaje del agua empieza en el cielo",
             parrafos=[
                 "Al norte de Lima, en la costa central del Perú, un río nace de la lluvia "
                 "andina y baja hasta el Pacífico atravesando el valle de Huaral. De ese "
                 "viaje dependen una ciudad, miles de hectáreas de cultivo y la vida de "
                 "toda una provincia.",
                 "Sígalo con nosotros: desde las nubes sobre los Andes hasta la crecida que "
                 "amenaza el valle. Entender ese recorrido es el primer paso para "
                 "<b>pronosticarla y dar el aviso a tiempo</b>.",
             ]),
        dict(id="cuenca", num="02", eyebrow="La cuenca, vista desde arriba",
             titulo="Tres mil kilómetros cuadrados de montaña y valle",
             parrafos=[
                 "Este es el territorio completo, como lo ve un satélite — y sus números "
                 "hablan solos, a la derecha. Desde aquí parece un mapa plano; pero su "
                 "historia se cuenta en la <b>tercera dimensión</b>.",
                 "Del litoral a la cabecera hay más de <b>5 000 m</b> de desnivel. Esa altura "
                 "lo decide todo: dónde cae la lluvia, cuánto tarda en bajar y quién queda "
                 "expuesto cuando el río crece.",
             ]),
        dict(id="relieve", num="03", eyebrow="La tercera dimensión",
             titulo="El relieve se levanta",
             parrafos=[
                 "Inclinemos la mirada. El mismo territorio, ahora en <b>relieve real</b> "
                 "reconstruido a partir de un modelo de elevación de 30 m: quebradas "
                 "profundas, laderas empinadas y una cabecera que roza los <b>5 242 m</b>.",
                 "Esta forma del terreno es la que gobierna el agua. La gravedad hace el "
                 "resto: cada gota buscará el fondo del valle siguiendo la pendiente.",
             ]),
        dict(id="cabeceras", num="04", eyebrow="Donde nace el agua",
             titulo="Las cabeceras que alimentan al río",
             parrafos=[
                 "La red de drenaje se dibuja sola sobre el relieve: cientos de quebradas "
                 "que confluyen en un cauce principal de <b>casi 122 km</b> hasta el mar.",
                 "Tres subcuencas de altura —<b>Alto Chancay, Baños y Carac</b>, todas sobre "
                 "los 4 000 m— concentran cerca del <b>56 % del rendimiento hídrico</b> de "
                 "la cuenca. Ahí, en las cabeceras, empieza de verdad el viaje del agua.",
             ]),
        dict(id="clima", num="05", eyebrow="El pulso del clima",
             titulo="Un año de lluvia sobre la montaña",
             parrafos=[
                 "Recorra los <b>doce meses</b> sobre el terreno. La <b>temporada húmeda "
                 "(diciembre–abril)</b> descarga la lluvia sobre la cabecera andina y llena "
                 "el cauce; el resto del año la cuenca se seca y el caudal cae.",
                 "Cambie entre <b>precipitación</b> y <b>temperatura</b> y pulse reproducir. "
                 "Ese ritmo estacional es la base de la seguridad hídrica: define cuándo hay "
                 "recarga y cuándo llega el estiaje.",
             ]),
        dict(id="invisible", num="06", eyebrow="El agua que no se ve",
             titulo="Suelo, nieve y vegetación",
             parrafos=[
                 "No toda el agua corre por el río. Parte se guarda en el <b>suelo</b>, se "
                 "acumula como <b>nieve</b> en las cumbres y se refleja en el <b>verdor</b> "
                 "de la vegetación, que se enciende con las lluvias y se apaga en el estiaje.",
                 "Estas capas (reanálisis ERA5-Land) le dan al modelo memoria de la cuenca: "
                 "el agua almacenada hoy es el caudal de mañana.",
             ]),
        dict(id="integracion", num="07", eyebrow="La integración de los datos",
             titulo="El modelo ve la cuenca por capas",
             parrafos=[
                 "Ningún dato basta por sí solo. El pronóstico nace de <b>fusionar</b> capas "
                 "de información sobre el mismo territorio: el relieve, la red de ríos, la "
                 "lluvia, la temperatura, el agua del suelo y la vegetación.",
                 "Aquí se <b>separan y se vuelven a integrar</b>. Cada plano cubre la misma "
                 "cuenca; apilados, son la memoria física que el modelo aprende a leer para "
                 "pronosticar el caudal.",
             ]),
        dict(id="yaku", num="08", eyebrow="Marzo 2023 · Ciclón Yaku",
             titulo="Cuando el río creció de verdad",
             parrafos=[
                 "En marzo de 2023 el <b>Ciclón Yaku</b> descargó lluvias extraordinarias "
                 "sobre la costa central. <b>Siga desplazándose</b>: el scroll recorre los "
                 "46 días del evento — la lluvia se enciende sobre la cuenca, los pulsos del "
                 "río se aceleran y el <b>caudal observado</b> en Santo Domingo se dispara.",
                 "De un caudal habitual cercano a <b>17 m³/s</b>, el río llegó a "
                 "<b>113 m³/s el 15 de marzo</b> —más de seis veces lo normal, nivel "
                 "<b>Fuerte</b> (naranja) del protocolo RM-049—. Aguas abajo, una crecida así "
                 "es la que desborda los cultivos del valle, como ya ocurrió en <b>Manchuria "
                 "en 2017</b>. Es exactamente el tipo de evento que un sistema de alerta debe "
                 "ver venir.",
             ]),
        dict(id="alerta", num="09", eyebrow="Del pronóstico al aviso",
             titulo="Del viaje del agua a la alerta temprana",
             parrafos=[
                 f"A la salida de la cuenca, la estación <b>{est.get('nombre','Santo Domingo')}</b> "
                 f"mide el caudal que llega al valle. Sobre el nivel de <b>vigilancia "
                 f"(P90 = {umbral:.0f} m³/s)</b> arranca el seguimiento; los niveles "
                 f"<b>Moderado · Fuerte · Extremo</b> (RM-049) escalan el aviso de crecida.",
                 "El modelo <b>RA-TFT</b> sostiene la habilidad de pronóstico con varios días de "
                 "ventaja: cada día ganado es tiempo para alertar, evacuar o manejar el "
                 "riego. Ese es el destino del viaje: <b>convertir el agua en información y la "
                 "información en protección</b>.",
             ]),
    ]


# ── "Dato destacado" por capítulo: un stat / mini-visual que responde la pregunta
#    del capítulo de un vistazo (para que las tarjetas no sean solo texto). ──
def _sm_stats(items):
    return ("<div class='sm-stats'>" + "".join(
        f"<div class='sm-stat'><span class='sm-stat-num'>{n}</span>"
        f"<span class='sm-stat-lab'>{l}</span></div>" for n, l in items) + "</div>")

def _sm_tags(items):
    return ("<div class='sm-tags'>" + "".join(f"<span class='sm-tag'>{t}</span>" for t in items) + "</div>")

def _sm_elev_bar():
    return ("<div class='sm-fig'><svg viewBox='0 0 320 30' preserveAspectRatio='none'"
            " role='img' aria-label='Rango de elevación de 0 a 5242 m'>"
            "<defs><linearGradient id='smelev' x1='0' y1='0' x2='1' y2='0'>"
            "<stop offset='0' stop-color='#0A3D54'/><stop offset='0.5' stop-color='#4D93A6'/>"
            "<stop offset='1' stop-color='#E7F1F5'/></linearGradient></defs>"
            "<rect x='0' y='2' width='320' height='11' rx='5.5' fill='url(#smelev)'/>"
            "<text x='2' y='26' fill='#9fb8c2' font-size='10' font-family='IBM Plex Mono,monospace'>0 m · litoral</text>"
            "<text x='318' y='26' fill='#cfe2ea' font-size='10' font-family='IBM Plex Mono,monospace'"
            " text-anchor='end'>5 242 m · cabecera</text></svg></div>")

def _sm_yaku_bar():
    h17 = round(17/113*46); h113 = 46
    return ("<div class='sm-fig'><svg viewBox='0 0 300 74' role='img'"
            " aria-label='De 17 a 113 m3/s, seis veces'>"
            f"<rect x='42' y='{58-h17}' width='56' height='{h17}' rx='3' fill='#4D93A6'/>"
            f"<rect x='150' y='{58-h113}' width='56' height='{h113}' rx='3' fill='#C0392B'/>"
            f"<text x='70' y='{54-h17}' fill='#cfe2ea' font-size='11' text-anchor='middle' font-family='IBM Plex Mono,monospace'>17</text>"
            f"<text x='178' y='{53-h113}' fill='#fff' font-size='13' text-anchor='middle' font-family='IBM Plex Mono,monospace' font-weight='600'>113</text>"
            "<text x='70' y='70' fill='#9fb8c2' font-size='10' text-anchor='middle' font-family='IBM Plex Sans,sans-serif'>habitual</text>"
            "<text x='178' y='70' fill='#e78a7f' font-size='10' text-anchor='middle' font-family='IBM Plex Sans,sans-serif'>Yaku</text>"
            "<text x='250' y='34' fill='#e78a7f' font-size='15' font-family='IBM Plex Mono,monospace' font-weight='600'>×6.6</text>"
            "<text x='250' y='49' fill='#9fb8c2' font-size='9' font-family='IBM Plex Sans,sans-serif'>m³/s</text></svg></div>")

def _card_extras(meta):
    area = f"{meta.get('cuenca_area_km2', 3062.6):,.0f}".replace(",", " ")
    nsub = meta.get("n_subcuencas", 9)
    return {
        # cap 02: los números grandes viven FUERA de la tarjeta (overlay #sm-bigstats)
        "cuenca": "",
        "relieve": _sm_elev_bar(),
        # tiempo de concentración: Giandotti 9,9 h · Témez 21,3 h (L=121,9 km,
        # ΔH=4 833 m, S=0,0396, A=3 062,7 km², Hm≈2 622 m) → «10–21 horas».
        "cabeceras": _sm_stats([("10–21 h", "viaje de una gota: cabecera → mar"),
                                ("122 km", "río principal"),
                                ("56 %", "del rendimiento hídrico")]),
        "clima": _sm_stats([("Dic–Abr", "temporada húmeda"), ("&gt;700 mm", "al año en la cabecera")]),
        "invisible": _sm_tags(["Humedad de suelo", "Nieve", "Vegetación", "ERA5-Land"]),
        "integracion": _sm_stats([("6", "capas de datos"), ("1", "misma cuenca")]),
        "yaku": _sm_yaku_bar(),
        # honestidad (auditoría): a 1 día iguala al mejor baseline; su ventaja real
        # es sostener la habilidad a multi-día — el KPI lo dice así.
        "alerta": _sm_stats([("71 %", "detección de crecida · 1 día"),
                             ("7–14 d", "donde el modelo gana"),
                             ("0.95", "NSE · 1 día (≈ baseline)")]),
    }


def recorrido_html(meta, leaderboard_div: str, forecast_div: str,
                   data_json: str) -> str:
    """HTML de la pestaña «Recorrido»: escenario 3D full-screen (sticky) + narrativa scroll.

    leaderboard_div / forecast_div: figuras Plotly (server) que se muestran en el cap. 08.
    data_json: JSON embebido con terrain/timelapse/evento + GeoJSON de ríos/subcuencas/puntos
    (los PNG se referencian relativos a media/). Se embebe inline (autocontenido, como el resto
    del dashboard); el JS lo lee de #sm-data."""
    caps = _capitulos(meta)
    extras = _card_extras(meta)

    pasos = []
    for c in caps:
        parr = "".join(f"<p class='sm-p'>{p}</p>" for p in c["parrafos"])
        pasos.append(
            f"<section class='sm-step' data-cap='{c['id']}' "
            f"aria-labelledby='sm-h-{c['id']}'>"
            f"<div class='sm-card'>"
            f"<p class='sm-eyebrow'><span class='sm-num'>{c['num']}</span>{c['eyebrow']}</p>"
            f"<h3 class='sm-h h-serif' id='sm-h-{c['id']}'>{c['titulo']}</h3>"
            f"{parr}"
            f"{extras.get(c['id'], '')}"
            f"</div></section>")
    narrativa = "\n".join(pasos)

    # Config mínima al JS (colores + parámetros del terreno). Todo lo demás por fetch.
    cfg = {
        "bounds": None,          # lo trae terrain_meta.json
        "exag": 2.4,             # exageración vertical del relieve (suave, cuenca tallada)
        "tex": {
            "dem": "media/terrain/dem_rgb.png",
            "satellite": "media/terrain/satellite.png",
            "relief": "media/terrain/relief.png",
        },
        "col": {"accent": "#0B6E8C", "deep": "#0A3D54", "cyan": "#1BA8C4",
                "crit": "#C0392B", "warn": "#D68910", "ok": "#2E8B6F",
                "ink": "#0C1E2A", "paper": "#F7F9FB"},
    }
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    # 9 fichas de subcuenca; las 3 de cabecera (>4 000 m) resaltadas en cian.
    sm_sub_dots = "".join(
        f'<rect x="{i*21}" y="2" width="16" height="12" rx="2" '
        f'fill="{"#35C8E8" if i < 3 else "#3A5666"}"></rect>' for i in range(9))

    return f"""
    <div class="sm-immersive" aria-label="Recorrido inmersivo: el viaje del agua">
      <!-- Escenario pegajoso a pantalla completa: terreno 3D + globo + controles + overlays. -->
      <div class="sm-stage" aria-hidden="true">
        <div id="sm-deck" class="sm-deck"></div>
        <div id="sm-globe" class="sm-globe"></div>
        <img class="sm-fallback" id="sm-fallback" alt="" src="media/terrain/relief.png">
        <div class="sm-vignette"></div>

        <!-- HUD: título de capítulo (sincronizado por JS) + brújula/atribución. -->
        <div class="sm-hud" id="sm-hud" hidden>
          <span class="sm-hud-num mono" id="sm-hud-num">01</span>
          <span class="sm-hud-title" id="sm-hud-title"></span>
        </div>
        <div class="sm-attrib" id="sm-attrib">Relieve: DEM 30 m · Imagen: Esri, Maxar</div>

        <!-- Control de timelapse (clima / ERA5 / evento): el JS lo adapta por capítulo. -->
        <div class="sm-ctrl" id="sm-ctrl" hidden>
          <div class="sm-ctrl-seg" id="sm-ctrl-seg" role="group" aria-label="Variable"></div>
          <div class="sm-ctrl-row">
            <button type="button" class="sm-ctrl-play" id="sm-ctrl-play"
                    aria-label="Reproducir la animación">
              <span class="sm-ctrl-ico" aria-hidden="true">&#9654;</span>
              <span id="sm-ctrl-play-lab">Reproducir</span>
            </button>
            <input type="range" class="sm-ctrl-slider" id="sm-ctrl-slider"
                   min="0" max="11" step="1" value="0" aria-label="Paso de la animación">
            <span class="sm-ctrl-lab mono" id="sm-ctrl-lab" aria-live="polite">Ene</span>
          </div>
          <div class="sm-legend" id="sm-legend" aria-hidden="true"></div>
        </div>

        <!-- Hidrograma del evento Yaku (Plotly cliente), visible solo en el cap. 08.
             HUD inmersivo: valor grande coloreado por nivel RM-049 + chip de nivel + fecha. -->
        <div class="sm-hydro" id="sm-hydro" hidden>
          <span class="sm-hydro-t">Caudal observado · Santo Domingo (47E214D2)</span>
          <div class="sm-hydro-val">
            <span class="sm-hydro-q mono" id="sm-hydro-q">—</span>
            <span class="sm-hydro-lvl mono" id="sm-hydro-lvl" hidden></span>
            <span class="sm-hydro-date mono" id="sm-hydro-date"></span>
          </div>
          <div class="sm-mile" id="sm-mile" aria-live="polite"></div>
          <div id="sm-hydro-plot" class="sm-hydro-plot"></div>
        </div>

        <!-- Panel de evidencia (Plotly server), visible solo en el cap. 08. -->
        <div class="sm-plots" id="sm-plots" hidden>
          <div class="sm-plot-card">
            <p class="sm-plot-cap">Habilidad (NSE) sostenida según el horizonte de pronóstico</p>
            {leaderboard_div}
          </div>
          <div class="sm-plot-card">
            <p class="sm-plot-cap">Pronóstico probabilístico frente al umbral de alerta de crecida</p>
            {forecast_div}
          </div>
        </div>

        <!-- Botón de la visualización estratificada (exploded layers), solo cap. 07. -->
        <button type="button" class="sm-stack-btn" id="sm-stack-btn" hidden
                aria-label="Separar o integrar las capas de datos">
          <span class="sm-stack-ico" aria-hidden="true">&#8645;</span>
          <span id="sm-stack-lab">Integrar capas</span>
        </button>

        <!-- Girar la cuenca (órbita a demanda). Visible cuando hay terreno 3D. -->
        <button type="button" class="sm-spin-btn" id="sm-spin-btn" hidden
                aria-pressed="false" aria-label="Girar o detener la vista de la cuenca">
          <span class="sm-spin-ico" aria-hidden="true">&#8635;</span>
          <span id="sm-spin-lab">Girar</span>
        </button>
        <div class="sm-drag-hint" id="sm-drag-hint" aria-hidden="true">Arrastre para rotar · rueda del ratón bloqueada</div>

        <!-- Puntos de progreso: un punto clicable por capítulo (los construye el JS). -->
        <nav class="sm-dots" id="sm-dots" aria-label="Capítulos del recorrido"></nav>

        <!-- Ficha de la cuenca (cap. 02): cada cifra con su micro-visual y su porqué;
             el perfil del río lo dibuja el JS con los datos reales del DEM. -->
        <div class="sm-bigstats" id="sm-bigstats" hidden aria-label="La cuenca en números">
          <p class="sm-bs-eyebrow">La cuenca en números</p>

          <div class="sm-bs-row">
            <div class="sm-bs-head"><span class="sm-big-n mono">3&#8239;063</span><span class="sm-big-u">km²</span></div>
            <svg class="sm-bs-viz" viewBox="0 0 210 26" preserveAspectRatio="none" aria-hidden="true">
              <rect x="0" y="2" width="190" height="8" rx="2" fill="#35C8E8"></rect>
              <rect x="0" y="15" width="166" height="8" rx="2" fill="#5B7686"></rect>
            </svg>
            <p class="sm-bs-say">mayor que toda la <b>provincia de Lima</b> (2&#8239;672 km²)</p>
          </div>

          <div class="sm-bs-row">
            <div class="sm-bs-head"><span class="sm-big-n mono">9</span><span class="sm-big-u">subcuencas</span></div>
            <svg class="sm-bs-viz" viewBox="0 0 190 16" aria-hidden="true">{sm_sub_dots}</svg>
            <p class="sm-bs-say">las <b>3</b> más altas concentran el <b>56&#8239;%</b> del agua</p>
          </div>

          <div class="sm-bs-row">
            <div class="sm-bs-head"><span class="sm-big-n mono">122</span><span class="sm-big-u">km de río</span></div>
            <svg class="sm-bs-viz sm-bs-perfil" id="sm-perfil-spark" viewBox="0 0 190 44"
                 preserveAspectRatio="none" aria-hidden="true">
              <defs><linearGradient id="pfg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stop-color="#35C8E8" stop-opacity="0.4"></stop>
                <stop offset="1" stop-color="#35C8E8" stop-opacity="0"></stop></linearGradient></defs>
            </svg>
            <p class="sm-bs-say">cae <b>4&#8239;833 m</b> desde la cabecera andina hasta el Pacífico</p>
          </div>
        </div>

        <!-- Pista de scroll (desaparece tras el primer avance). -->
        <div class="sm-scroll-hint" id="sm-scroll-hint" aria-hidden="true">
          <span>Desplácese para viajar</span>
          <span class="sm-scroll-ico">&#8595;</span>
        </div>
      </div>

      <!-- Narrativa: una tarjeta por capítulo, legible sin JS. -->
      <div class="sm-steps">
{narrativa}
      </div>
    </div>
    <script id="sm-cfg" type="application/json">{cfg_json}</script>
    <script id="sm-data" type="application/json">{data_json}</script>"""


# ── CSS (se inyecta como <style> aparte; reutiliza las CSS vars del dashboard). ──
CSS = r"""
/* STORYMAP INMERSIVO «El viaje del agua» */
.sm-immersive{position:relative;width:100vw;margin-left:calc(50% - 50vw);
  background:#06121a;color:#EAF2F6;}
/* [hidden] debe ganar a los display:flex/block de abajo (control/hidro/plots). */
.sm-immersive [hidden]{display:none!important;}
.sm-stage{position:sticky;top:0;height:100vh;overflow:hidden;z-index:0;
  background:radial-gradient(120% 90% at 50% 8%,#0e2836 0%,#06121a 70%);}
.sm-deck,.sm-globe,.sm-fallback{position:absolute;inset:0;width:100%;height:100%;}
/* el gesto vertical hace scroll de página (avanza capítulos); el horizontal gira el 3D */
.sm-deck,.sm-globe{touch-action:pan-y;}
.sm-deck canvas{outline:none!important;}
.sm-globe{display:none;}
.sm-fallback{object-fit:cover;opacity:0;transition:opacity .6s ease;pointer-events:none;}
.sm-immersive.is-fallback .sm-fallback{opacity:.92;}
.sm-vignette{position:absolute;inset:0;pointer-events:none;z-index:1;
  background:radial-gradient(130% 120% at 50% 42%,transparent 55%,rgba(3,10,16,.55) 100%);}
.sm-hud{position:absolute;top:calc(var(--nav-h,60px) + 18px);left:36px;z-index:3;
  display:flex;align-items:baseline;gap:12px;pointer-events:none;
  text-shadow:0 1px 14px rgba(0,0,0,.55);max-width:min(60vw,640px);}
.sm-hud-num{font-size:13px;letter-spacing:.16em;color:var(--cyan,#1BA8C4);opacity:.9;}
.sm-hud-title{font-family:var(--serif,'Source Serif 4',Georgia,serif);
  font-size:clamp(1.1rem,2.4vw,1.9rem);font-weight:600;line-height:1.1;color:#fff;
  opacity:0;transform:translateY(6px);transition:opacity .5s ease,transform .5s ease;}
.sm-hud.is-on .sm-hud-title{opacity:1;transform:none;}
.sm-attrib{position:absolute;right:12px;bottom:10px;z-index:3;font-size:10.5px;
  color:rgba(230,240,246,.62);letter-spacing:.02em;pointer-events:none;}
.sm-ctrl{position:absolute;left:50%;bottom:26px;transform:translateX(-50%);z-index:4;
  width:min(560px,88vw);padding:12px 14px 13px;border-radius:16px;
  background:rgba(9,22,31,.72);backdrop-filter:blur(10px) saturate(1.1);
  -webkit-backdrop-filter:blur(10px) saturate(1.1);
  border:1px solid rgba(120,170,190,.28);box-shadow:0 12px 40px rgba(0,0,0,.42);}
.sm-ctrl-seg{display:flex;gap:6px;justify-content:center;margin-bottom:10px;flex-wrap:wrap;}
.sm-ctrl-var{font-family:var(--sans,'IBM Plex Sans',sans-serif);font-size:12.5px;
  padding:5px 13px;border-radius:999px;cursor:pointer;color:#cfe2ea;
  background:rgba(255,255,255,.06);border:1px solid rgba(140,180,200,.28);transition:.18s;}
.sm-ctrl-var:hover{background:rgba(255,255,255,.13);}
.sm-ctrl-var.is-active{background:var(--cyan,#1BA8C4);color:#05171f;border-color:transparent;
  font-weight:600;}
.sm-ctrl-row{display:flex;align-items:center;gap:12px;}
.sm-ctrl-play{display:inline-flex;align-items:center;gap:7px;flex:0 0 auto;cursor:pointer;
  font-family:var(--sans,sans-serif);font-size:12.5px;color:#eaf2f6;padding:6px 13px;
  border-radius:999px;background:rgba(255,255,255,.09);
  border:1px solid rgba(140,180,200,.30);transition:.18s;}
.sm-ctrl-play:hover{background:rgba(255,255,255,.16);}
.sm-ctrl-ico{font-size:11px;line-height:1;color:var(--cyan,#1BA8C4);}
.sm-ctrl-slider{flex:1 1 auto;-webkit-appearance:none;appearance:none;height:4px;border-radius:3px;
  background:rgba(200,224,234,.3);outline:none;}
.sm-ctrl-slider::-webkit-slider-thumb{-webkit-appearance:none;width:15px;height:15px;border-radius:50%;
  background:var(--cyan,#1BA8C4);cursor:pointer;border:2px solid #eaf6fa;box-shadow:0 1px 6px rgba(0,0,0,.4);}
.sm-ctrl-slider::-moz-range-thumb{width:15px;height:15px;border-radius:50%;background:var(--cyan,#1BA8C4);
  cursor:pointer;border:2px solid #eaf6fa;}
.sm-ctrl-lab{flex:0 0 auto;min-width:64px;text-align:right;font-size:12.5px;color:#eaf2f6;}
.sm-legend{margin-top:10px;position:relative;}
.sm-legend-bar{height:8px;border-radius:4px;}
.sm-legend-scale{display:flex;justify-content:space-between;font-size:10px;color:#b9cdd6;margin-top:3px;}
.sm-legend-unit{position:absolute;right:0;top:-14px;font-size:10px;color:#b9cdd6;}
/* HUD inmersivo (sin caja dura): vidrio con degradado, sin borde, hairline superior. */
.sm-hydro{position:absolute;right:22px;bottom:96px;z-index:4;width:min(470px,92vw);
  padding:14px 16px 4px;border-radius:20px;
  background:linear-gradient(155deg,rgba(7,19,27,.86),rgba(7,19,27,.5));
  backdrop-filter:blur(14px) saturate(1.15);-webkit-backdrop-filter:blur(14px) saturate(1.15);
  box-shadow:0 18px 54px rgba(0,0,0,.46),inset 0 1px 0 rgba(180,220,235,.14);}
.sm-hydro-t{display:block;font-family:var(--sans,sans-serif);font-size:10px;
  letter-spacing:.13em;text-transform:uppercase;color:#9fb8c2;margin-bottom:3px;}
.sm-hydro-val{display:flex;align-items:baseline;gap:10px;}
.sm-hydro-q{font-size:31px;font-weight:700;color:#35C8E8;line-height:1.05;
  transition:color .35s,text-shadow .35s;}
.sm-hydro-un{font-size:13px;font-weight:500;color:#9fb8c2;}
.sm-hydro-lvl{font-size:9.5px;letter-spacing:.11em;padding:3px 9px;border:1px solid;
  border-radius:999px;transition:color .35s,border-color .35s;transform:translateY(-4px);}
.sm-hydro-date{margin-left:auto;font-size:11px;color:#9fb8c2;}
.sm-mile{font-family:var(--sans,sans-serif);font-size:11.5px;line-height:1.45;color:#cfe2ea;
  border-left:2px solid #35C8E8;padding:2px 0 2px 9px;margin:6px 0 2px;min-height:16px;
  transition:opacity .4s;}
.sm-mile b{color:#7FD3E3;}
.sm-hydro-plot{height:158px;margin:0 -6px;}
.sm-plots{position:absolute;right:22px;top:calc(var(--nav-h,60px) + 30px);z-index:4;
  width:min(560px,92vw);max-height:calc(100vh - var(--nav-h,60px) - 130px);overflow:auto;
  display:flex;flex-direction:column;gap:14px;}
.sm-plot-card{padding:14px 16px 8px;border-radius:20px;
  background:linear-gradient(155deg,rgba(7,19,27,.86),rgba(7,19,27,.5));
  backdrop-filter:blur(14px) saturate(1.15);-webkit-backdrop-filter:blur(14px) saturate(1.15);
  box-shadow:0 18px 54px rgba(0,0,0,.5),inset 0 1px 0 rgba(180,220,235,.14);}
.sm-plot-cap{font-family:var(--sans,sans-serif);font-size:10px;letter-spacing:.12em;
  text-transform:uppercase;color:#9fb8c2;margin:0 0 8px;font-weight:600;}
/* Anula la tarjeta blanca genérica de .js-plotly-plot (estilos del dashboard):
   dentro del recorrido los gráficos van a ras sobre el vidrio oscuro del HUD. */
.sm-hydro-plot.js-plotly-plot,.sm-hydro-plot .js-plotly-plot,
.sm-plot-card .js-plotly-plot{background:transparent!important;border:0!important;
  border-radius:0!important;box-shadow:none!important;padding:0!important;}
.sm-stack-btn{position:absolute;left:50%;bottom:30px;transform:translateX(-50%);z-index:4;
  display:inline-flex;align-items:center;gap:8px;cursor:pointer;
  font-family:var(--sans,sans-serif);font-size:13px;color:#eaf2f6;padding:9px 18px;
  border-radius:999px;background:rgba(9,22,31,.72);backdrop-filter:blur(10px);
  -webkit-backdrop-filter:blur(10px);border:1px solid rgba(120,170,190,.30);
  box-shadow:0 10px 34px rgba(0,0,0,.4);transition:.18s;}
.sm-stack-btn:hover{background:rgba(16,38,50,.85);}
.sm-stack-ico{font-size:15px;color:var(--cyan,#1BA8C4);}
.sm-spin-btn{position:absolute;right:20px;bottom:24px;z-index:5;
  display:inline-flex;align-items:center;gap:7px;cursor:pointer;
  font-family:var(--sans,sans-serif);font-size:12.5px;color:#eaf2f6;padding:8px 15px;
  border-radius:999px;background:rgba(9,22,31,.72);backdrop-filter:blur(10px);
  -webkit-backdrop-filter:blur(10px);border:1px solid rgba(120,170,190,.30);
  box-shadow:0 8px 26px rgba(0,0,0,.38);transition:.18s;}
.sm-spin-btn:hover{background:rgba(16,38,50,.85);border-color:rgba(27,168,196,.55);}
.sm-spin-btn.is-on{background:rgba(11,110,140,.55);border-color:rgba(27,168,196,.7);}
.sm-spin-ico{font-size:16px;color:var(--cyan,#1BA8C4);display:inline-block;}
.sm-spin-btn.is-on .sm-spin-ico{animation:sm-rot 2.2s linear infinite;}
@keyframes sm-rot{to{transform:rotate(360deg);}}
.sm-drag-hint{position:absolute;right:20px;bottom:58px;z-index:4;font-size:10.5px;
  letter-spacing:.03em;color:rgba(214,228,236,.62);pointer-events:none;transition:opacity .5s;text-align:right;}
.sm-immersive.is-moved .sm-drag-hint{opacity:0;}
.sm-dots{position:absolute;right:16px;top:50%;transform:translateY(-50%);z-index:5;
  display:flex;flex-direction:column;gap:9px;}
.sm-dot{width:9px;height:9px;border-radius:50%;border:1px solid rgba(190,225,240,.55);
  background:rgba(9,22,31,.5);cursor:pointer;padding:0;transition:.2s;}
.sm-dot:hover{border-color:#7FD3E3;transform:scale(1.25);}
.sm-dot.is-on{background:#35C8E8;border-color:#35C8E8;box-shadow:0 0 8px rgba(53,200,232,.6);}
@media (max-width:760px){.sm-dots{display:none;}}
/* Ficha de la cuenca (cap. 02): cifra grande + micro-visual + porqué. No es una
   caja dura: vidrio muy tenue con filo de acento a la izquierda, tipografía manda. */
.sm-bigstats{position:absolute;right:clamp(28px,5vw,88px);top:50%;transform:translateY(-50%);
  z-index:3;width:clamp(280px,26vw,360px);display:flex;flex-direction:column;
  gap:16px;padding:20px 22px 20px 24px;border-radius:16px;pointer-events:none;
  background:linear-gradient(150deg,rgba(7,20,29,.42),rgba(7,20,29,.10));
  border-left:2px solid rgba(53,200,232,.5);
  -webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px);}
.sm-bs-eyebrow{font-family:var(--sans,sans-serif);font-size:10.5px;font-weight:600;
  letter-spacing:.16em;text-transform:uppercase;color:#35C8E8;margin:0 0 2px;
  text-shadow:0 1px 10px rgba(4,14,20,.9);}
.sm-bs-row{opacity:0;transform:translateX(14px);animation:sm-big-in .7s ease forwards;
  padding-top:13px;border-top:1px solid rgba(150,190,205,.16);}
.sm-bs-row:first-of-type{border-top:0;padding-top:0;}
.sm-bs-row:nth-of-type(2){animation-delay:.14s;}
.sm-bs-row:nth-of-type(3){animation-delay:.28s;}
.sm-bs-row:nth-of-type(4){animation-delay:.42s;}
@keyframes sm-big-in{to{opacity:1;transform:none;}}
@media (prefers-reduced-motion:reduce){.sm-bs-row{animation:none;opacity:1;transform:none;}}
.sm-bs-head{display:flex;align-items:baseline;gap:8px;}
.sm-big-n{font-size:clamp(30px,4.2vw,50px);font-weight:700;color:#EAF6FB;line-height:1;
  letter-spacing:-.01em;text-shadow:0 2px 22px rgba(4,14,20,.9),0 0 2px rgba(4,14,20,.95);}
.sm-big-u{font-family:var(--sans,sans-serif);font-size:13px;font-weight:500;color:#9fc5d2;}
.sm-bs-viz{display:block;width:100%;height:22px;margin:8px 0 6px;overflow:visible;}
.sm-bs-perfil{height:38px;}
.sm-bs-say{font-family:var(--sans,sans-serif);font-size:12.5px;line-height:1.5;
  color:#c3d7e0;margin:0;text-shadow:0 1px 8px rgba(4,14,20,.85);}
.sm-bs-say b{color:#EAF6FB;font-weight:600;}
@media (max-width:960px){.sm-bigstats{display:none;}}
@media (prefers-reduced-motion:reduce){.sm-spin-btn.is-on .sm-spin-ico{animation:none;}}
.sm-scroll-hint{position:absolute;left:50%;bottom:20px;transform:translateX(-50%);z-index:3;
  display:flex;flex-direction:column;align-items:center;gap:4px;font-size:11.5px;
  letter-spacing:.08em;color:rgba(230,240,246,.8);pointer-events:none;transition:opacity .5s;}
.sm-scroll-ico{font-size:16px;animation:sm-bob 1.6s ease-in-out infinite;}
@keyframes sm-bob{0%,100%{transform:translateY(0);}50%{transform:translateY(6px);}}
.sm-immersive.is-moved .sm-scroll-hint{opacity:0;}
.sm-steps{position:relative;z-index:2;margin-top:-100vh;pointer-events:none;}
.sm-step{min-height:100vh;display:flex;align-items:center;padding:0 36px;pointer-events:none;}
/* Capítulo Yaku: paso alto (scroll-scrub) — el scroll recorre los 46 días del evento. */
.sm-step[data-cap="yaku"]{min-height:340vh;align-items:flex-start;}
.sm-step[data-cap="yaku"] .sm-card{position:sticky;top:14vh;}
.sm-card{pointer-events:auto;max-width:430px;padding:26px 28px;border-radius:18px;
  background:rgba(8,20,28,.60);backdrop-filter:blur(14px) saturate(1.2);
  -webkit-backdrop-filter:blur(14px) saturate(1.2);border:1px solid rgba(120,170,190,.24);
  box-shadow:0 18px 60px rgba(0,0,0,.5);
  opacity:.04;transform:translateY(26px) scale(.99);transition:opacity .6s ease,transform .6s ease;}
.sm-step.is-active .sm-card{opacity:1;transform:none;}
.sm-eyebrow{display:flex;align-items:center;gap:10px;font-family:var(--sans,sans-serif);
  font-size:11.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--cyan,#1BA8C4);margin:0 0 12px;}
.sm-num{font-family:var(--mono,'IBM Plex Mono',monospace);font-size:12px;color:#eaf2f6;
  background:rgba(27,168,196,.16);border:1px solid rgba(27,168,196,.4);border-radius:6px;
  padding:2px 7px;letter-spacing:.05em;}
.sm-h{font-family:var(--serif,'Source Serif 4',Georgia,serif);font-weight:600;color:#fff;
  font-size:clamp(1.5rem,3vw,2.15rem);line-height:1.08;margin:0 0 14px;text-wrap:balance;}
.sm-p{font-family:var(--sans,sans-serif);font-size:15px;line-height:1.62;color:#d6e4ea;margin:0 0 12px;}
.sm-p:last-child{margin-bottom:0;}
.sm-p b{color:#fff;font-weight:600;}
/* Dato destacado / mini-visual por tarjeta */
.sm-card .sm-stats,.sm-card .sm-fig,.sm-card .sm-tags{margin-top:16px;padding-top:14px;
  border-top:1px solid rgba(120,170,190,.18);}
.sm-stats{display:flex;gap:22px;flex-wrap:wrap;}
.sm-stat{display:flex;flex-direction:column;gap:3px;}
.sm-stat-num{font-family:var(--mono,'IBM Plex Mono',monospace);font-size:1.55rem;font-weight:600;
  line-height:1;color:var(--cyan,#1BA8C4);font-variant-numeric:tabular-nums;}
.sm-stat-lab{font-family:var(--sans,sans-serif);font-size:10.5px;text-transform:uppercase;
  letter-spacing:.06em;color:#9fb8c2;max-width:140px;line-height:1.25;}
.sm-tags{display:flex;gap:7px;flex-wrap:wrap;}
.sm-tag{font-family:var(--sans,sans-serif);font-size:11px;color:#cfe2ea;
  background:rgba(27,168,196,.14);border:1px solid rgba(27,168,196,.32);border-radius:999px;padding:3px 10px;}
.sm-fig svg{display:block;width:100%;height:auto;max-width:340px;}
@media (max-width:760px){
  .sm-step{padding:0 16px;align-items:flex-end;}
  .sm-card{max-width:none;width:100%;margin-bottom:15vh;padding:20px 20px;}
  .sm-hud{left:16px;}
  .sm-hydro,.sm-plots{right:8px;left:8px;width:auto;}
  .sm-plots{top:auto;bottom:96px;max-height:52vh;}
}
@media (prefers-reduced-motion:reduce){
  .sm-card,.sm-hud-title,.sm-fallback{transition:none;}
  .sm-scroll-ico{animation:none;}
}
"""


# ── JS: motor deck.gl (terreno 3D) + scrollytelling «El viaje del agua». ─────────
JS = r"""
(function(){
  var CFG=null, D=null;                       // config + datos embebidos
  try{ CFG=JSON.parse(document.getElementById('sm-cfg').textContent); }catch(e){ return; }
  var reduce = matchMedia('(prefers-reduced-motion:reduce)').matches;
  var EXAG=CFG.exag||4, TEX=CFG.tex, COL=CFG.col;
  var deckgl=null, globe=null, inited=false, active=false, obs=null;
  var BOUNDS=null, DECODER=null, EMAX=5000;
  var view=null, tweenRAF=null, orbitRAF=null, orbit=false, spin=false, curCap=null;
  var reveal=0, revRAF=null, spread=0, spreadRAF=null;
  var tripsOn=false, tripsRAF=null, tripsT=0, tripsSpeed=1, tripsLast=0;
  var scene={};                               // flags del capítulo actual
  var tl={kind:null,sub:null,idx:0,n:12,playing:false,timer:null};
  var hydroInit=false;

  // Rampas de color (== matplotlib) para las leyendas.
  var STOPS={
    YlGnBu:['#FFFFD9','#EDF8B1','#C6E9B4','#7ECDBB','#40B5C4','#1D90C0','#225DA8','#243392','#081D58'],
    RdYlBu_r:['#313695','#5183BB','#90C3DD','#D4EDF4','#FFFEBE','#FED283','#F88C51','#DD3D2D','#A50026'],
    Blues:['#F7FBFF','#DEEBF7','#C6DBEF','#9ECAE1','#6BAED6','#4292C6','#2171B5','#08519C','#08306B'],
    YlGn:['#FFFFE5','#F7FCB9','#D9F0A3','#ADDD8E','#78C679','#41AB5D','#238443','#006837','#004529'],
    suelo:['#8C6A3F','#C9A66B','#BEE0C2','#2E8B6F','#0B6E8C']
  };
  var MESES=['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];

  // Iconos SVG (billboards) con halo blanco para legibilidad sobre cualquier base.
  function svg(s){ return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(s); }
  var PIN=function(fill,glyph){return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 60" width="48" height="60">'+
    '<path d="M24 2C13 2 4 11 4 22c0 14 20 34 20 34s20-20 20-34C44 11 35 2 24 2z" fill="'+fill+'" stroke="#fff" stroke-width="3"/>'+glyph+'</svg>';};
  var ICON={
    aforo: svg(PIN('#C0392B','<circle cx="24" cy="15" r="3.2" fill="#fff"/><path d="M13 25c3.5-3.2 7 3 11 0s7.5-3.2 11 0" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round"/>')),
    meteo: svg(PIN('#2E8B6F','<path d="M17 24h13a4.5 4.5 0 0 0 .3-9 6.5 6.5 0 0 0-12.3-1.6A4.5 4.5 0 0 0 17 24z" fill="#fff"/><path d="M19 27l-1.5 4M25 27l-1.5 4M31 27l-1.5 4" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>')),
    ciudad:svg(PIN('#0C1E2A','<path d="M14 30V17l6-3v6l6-3v13z" fill="#fff"/><rect x="28" y="16" width="6" height="14" fill="#fff"/>')),
    cabecera: svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 48" width="56" height="48"><path d="M3 45 L22 9 L33 27 L40 17 L53 45 Z" fill="#D68910" stroke="#fff" stroke-width="2.6" stroke-linejoin="round"/><path d="M17.5 18 L22 9 L26.5 18 L23 21.5 L20.5 19 Z" fill="#fff"/></svg>')
  };

  // Escenas por capítulo: cámara + capas + timelapse.
  var SCENES={
    origen:   {globe:true},
    cuenca:   {flat2d:true, pitch:0, bearing:0,  view:'basin', reveal:0, subs:true, bigstats:true},
    relieve:  {tex:'satellite',pitch:52,bearing:-18,view:'basin', reveal:0.4, rivers:true,rivnames:true, orbit:true, trips:true},
    cabeceras:{tex:'satellite',pitch:50,bearing:-18,view:'head',  reveal:1, rivers:true,rivnames:true,points:true,heads:true,orbit:true,trips:true},
    clima:    {tex:'relief',   pitch:50,bearing:-10,view:'basin', reveal:0.7,rivers:true,rivnames:true,heads:true,tl:'clima'},
    invisible:{tex:'relief',   pitch:50,bearing:-10,view:'basin', reveal:0.6,rivers:true,rivnames:true,tl:'era5'},
    integracion:{stack:true,   pitch:54,bearing:22, view:'stack'},
    yaku:     {tex:'relief',   pitch:54,bearing:-6, view:'valley',reveal:0.85,rivers:true,rivnames:true,points:true,tl:'evento',trips:true},
    alerta:   {tex:'satellite',pitch:42,bearing:0,  view:'basin', reveal:0.55,rivers:true,rivnames:true,points:true,plots:true,trips:true}
  };
  // Sub-variables del timelapse: cmap/campo por tipo.
  var TLSUB={ clima:['precip','temp'], era5:['suelo','nieve','veg'], evento:['pr'] };
  var CMAP={ precip:'YlGnBu',temp:'RdYlBu_r', suelo:'suelo',nieve:'Blues',veg:'YlGn', pr:'Blues' };
  var SUBLAB={ precip:'Precipitación',temp:'Temperatura', suelo:'Humedad de suelo',nieve:'Nieve',veg:'Vegetación' };
  // Exploded layer stack (visualización estratificada de las fuentes de datos que integra el modelo).
  var STACK=[
    {img:'media/terrain/relief.png', lab:'Relieve'},
    {img:'media/terrain/rios.png',   lab:'Red hídrica'},
    {img:'media/clima/precip_03.png',lab:'Precipitación'},
    {img:'media/clima/temp_03.png',  lab:'Temperatura'},
    {img:'media/era5/suelo_03.png',  lab:'Humedad de suelo'},
    {img:'media/era5/veg_01.png',    lab:'Vegetación'}
  ];
  var SEP=8500, GAP=350;   // separación (m) entre planos a spread=1, y colchón mínimo

  function $(id){ return document.getElementById(id); }
  function pad(n){ return (n<10?'0':'')+n; }

  function views(){
    var w=BOUNDS[0],s=BOUNDS[1],e=BOUNDS[2],n=BOUNDS[3];
    return {
      basin: {longitude:(w+e)/2, latitude:(s+n)/2-0.01, zoom:9.5},
      head:  {longitude:-76.80,  latitude:-11.27,        zoom:9.7},
      valley:{longitude:-77.02,  latitude:-11.40,        zoom:9.85},
      stack: {longitude:(w+e)/2+0.06, latitude:(s+n)/2-0.05, zoom:8.4}
    };
  }

  // Textura del drape con DEBOUNCE: durante un scrub rápido el PNG del día solo se
  // intercambia al pausar ~130 ms (cambiarla cada frame rompe la carga del TerrainLayer).
  var texCur=null, texPend=null, texTimer=null;
  function setDrapeTex(p){
    if(p===texPend) return;   // ya en camino: NO reinicies el timer (los pulsos
    texPend=p;                // llaman aquí a 25 fps y lo dejaban congelado)
    if(texTimer) clearTimeout(texTimer);
    texTimer=setTimeout(function(){ texTimer=null; texCur=texPend; relayers(); },130);
  }
  function currentTexture(){
    var p=null;
    if(tl.kind==='clima')       p='media/clima/'+tl.sub+'_'+pad(tl.idx+1)+'.png';
    else if(tl.kind==='era5')   p='media/era5/'+tl.sub+'_'+pad(tl.idx+1)+'.png';
    else if(tl.kind==='evento') p='media/evento/pr_'+pad(tl.idx)+'.png';
    else { texCur=null; return scene.tex==='relief'? TEX.relief : TEX.satellite; }
    if(texCur===null){ texCur=p; }
    else if(p!==texCur){ setDrapeTex(p); }
    return texCur;
  }

  function buildLayers(){
    if(!D) return [];
    var L=[];
    if(scene.stack) return stackLayers();
    // Capítulo 2: mapa 2D plano (satélite + subcuencas al mismo z=0 → alinean perfecto).
    if(scene.flat2d){
      L.push(new deck.BitmapLayer({id:'flatbase', image:TEX.satellite, bounds:BOUNDS,
        opacity:1, material:false}));   // material:false = sin iluminación (evita sobreexposición)
      if(scene.subs && D.subs){
        L.push(new deck.GeoJsonLayer({id:'subs2d', data:D.subs, stroked:true, filled:true, material:false,
          getFillColor:function(f){var e=f.properties.elev||0;
            var c=e<1500?[127,211,227]:e<3000?[63,169,196]:e<4200?[11,110,140]:[10,61,84];
            return [c[0],c[1],c[2],64];},
          getLineColor:[255,255,255,210], lineWidthUnits:'pixels', getLineWidth:1.5}));
      }
      return L;
    }
    L.push(new deck.TerrainLayer({
      id:'terrain', minZoom:0, maxZoom:14, bounds:BOUNDS,
      elevationData:TEX.dem, texture:currentTexture(),
      elevationDecoder:DECODER, meshMaxError:1.0,
      material:{ambient:0.72,diffuse:0.82,shininess:16,specularColor:[42,60,68]},
      color:[255,255,255], wireframe:false,
      loadOptions:{image:{type:'image'}}, parameters:{depthTest:true}
    }));
    // Subcuencas (solo capítulos planos): overlay sin depth-test.
    if(scene.subs && D.subs){
      L.push(new deck.GeoJsonLayer({
        id:'subs', data:D.subs, stroked:true, filled:true,
        getFillColor:function(f){var e=f.properties.elev||0;
          var c=e<1500?[127,211,227]:e<3000?[63,169,196]:e<4200?[11,110,140]:[10,61,84];
          return [c[0],c[1],c[2],48];},
        getLineColor:[255,255,255,190], lineWidthUnits:'pixels', getLineWidth:1.2,
        parameters:{depthTest:false}
      }));
    }
    // Ríos (PathLayer, z bakeado × EXAG); revelado progresivo por 'w' (log-acumulación).
    if(scene.rivers && D.rios){
      L.push(new deck.PathLayer({
        id:'rios', data:D.rios.features,
        getPath:function(f){return f.geometry.coordinates.map(function(c){return [c[0],c[1],(c[2]||0)*EXAG+40];});},
        getColor:function(f){
          var main=f.properties.main; var w=f.properties.w||0;
          var vis = main || (w >= (1-reveal));
          if(!vis) return [0,0,0,0];
          return main? [175,240,255,245] : [130,216,242,220];
        },
        getWidth:function(f){return f.properties.main? 4.4 : (0.8+3.0*(f.properties.w||0));},
        widthUnits:'pixels', widthMinPixels:0.9, capRounded:true, jointRounded:true,
        updateTriggers:{getColor:[reveal]}, parameters:{depthTest:true}
      }));
    }
    // Pulsos de agua (TripsLayer): frentes que recorren la red D8 aguas abajo.
    // Timestamps horneados = distancia a la salida → todos los tramos pulsan en
    // sincronía (el frente es una iso-distancia que viaja hacia la salida).
    if(scene.trips && D.trips && !reduce){
      L.push(new deck.TripsLayer({
        id:'agua', data:D.trips.trips,
        getPath:function(d){return d.p.map(function(c){return [c[0],c[1],(c[2]||0)*EXAG+55];});},
        getTimestamps:function(d){return d.t;},
        getColor:[150,230,255,235],
        getWidth:function(d){return 1.4+4.2*(d.w||0.3);},
        widthUnits:'pixels', widthMinPixels:1.2, capRounded:true, jointRounded:true,
        trailLength:3.2, currentTime:tripsT, fadeTrail:true, opacity:0.9,
        pickable:false, parameters:{depthTest:true}
      }));
    }
    // Ríos con NOMBRE (ANA) etiquetados sobre el terreno 3D.
    if(scene.rivnames && D.rios_nombres){
      var segs=[];
      D.rios_nombres.features.forEach(function(f){
        f.geometry.coordinates.forEach(function(seg){ segs.push({p:seg, main:f.properties.main}); });
      });
      L.push(new deck.PathLayer({id:'rionom', data:segs,
        getPath:function(d){return d.p.map(function(c){return [c[0],c[1],(c[2]||0)*EXAG+60];});},
        getColor:function(d){return d.main?[185,242,255,255]:[140,220,244,240];},
        getWidth:function(d){return d.main?4.8:2.8;}, widthUnits:'pixels', widthMinPixels:1.4,
        capRounded:true, jointRounded:true, parameters:{depthTest:true}}));
      var seen={}, labs=[];
      D.rios_nombres.features.forEach(function(f){var n=f.properties.nombre;
        if(!seen[n]){seen[n]=1; labs.push(f.properties);}});
      // Etiquetas TENDIDAS sobre el suelo y orientadas al sentido del cauce (getAngle=la).
      L.push(new deck.TextLayer({id:'rionom-lbl', data:labs, billboard:false, characterSet:'auto',
        getPosition:function(d){return [d.lx, d.ly, (d.lz||0)*EXAG+120];},
        getText:function(d){return d.nombre;},
        getAngle:function(d){return d.la||0;},
        getSize:function(d){return d.main?15:12.5;}, sizeUnits:'pixels',
        getColor:function(d){return d.main?[210,244,252,255]:[168,224,244,245];},
        fontFamily:'IBM Plex Sans, sans-serif', fontWeight:600, fontSettings:{sdf:true},
        background:true, getBackgroundColor:[7,20,29,175], backgroundPadding:[5,2],
        outlineWidth:3.0, outlineColor:[6,18,26,245], getTextAnchor:'middle',
        getAlignmentBaseline:'center', parameters:{depthTest:false}}));
    }
    // Cabeceras (iconos montaña + etiqueta con % de aporte).
    if(scene.heads && D.subs){
      var heads=D.subs.features.filter(function(f){return f.properties.cabecera;});
      L.push(new deck.IconLayer({
        id:'heads', data:heads, billboard:true, sizeUnits:'pixels',
        getPosition:function(f){return [f.properties.cx,f.properties.cy,(f.properties.cz||0)*EXAG+250];},
        getIcon:function(){return {url:ICON.cabecera,width:56,height:48,anchorY:48,mask:false};},
        getSize:46
      }));
      L.push(new deck.TextLayer({
        id:'heads-lbl', data:heads, billboard:true, characterSet:'auto',
        getPosition:function(f){return [f.properties.cx,f.properties.cy,(f.properties.cz||0)*EXAG+250];},
        getText:function(f){return f.properties.nombre+'  ·  '+(f.properties.yield_pct||'')+'%';},
        getSize:12, getColor:[255,255,255,235], getPixelOffset:[0,-42],
        fontFamily:'IBM Plex Sans, sans-serif', fontWeight:600, fontSettings:{sdf:true},
        outlineWidth:2.6, outlineColor:[6,18,26,235], getTextAnchor:'middle', getAlignmentBaseline:'bottom'
      }));
    }
    // Estaciones + ciudad (iconos + etiquetas).
    if(scene.points && D.puntos){
      L.push(new deck.IconLayer({
        id:'pts', data:D.puntos.features, billboard:true, sizeUnits:'pixels', pickable:true,
        getPosition:function(f){var c=f.geometry.coordinates;return [c[0],c[1],(c[2]||0)*EXAG+180];},
        getIcon:function(f){return {url:ICON[f.properties.tipo]||ICON.aforo,width:48,height:60,anchorY:60,mask:false};},
        getSize:function(f){return f.properties.tipo==='ciudad'?40:34;}
      }));
      L.push(new deck.TextLayer({
        id:'pts-lbl', data:D.puntos.features, billboard:true, characterSet:'auto',
        getPosition:function(f){var c=f.geometry.coordinates;return [c[0],c[1],(c[2]||0)*EXAG+180];},
        getText:function(f){return f.properties.nombre;},
        getSize:11.5, getColor:[240,248,252,230], getPixelOffset:[0,-40],
        fontFamily:'IBM Plex Sans, sans-serif', fontWeight:500, fontSettings:{sdf:true},
        outlineWidth:2.6, outlineColor:[6,18,26,225], getTextAnchor:'middle', getAlignmentBaseline:'bottom'
      }));
    }
    return L;
  }

  // Exploded layer stack: planos flotantes (BitmapLayer) por fuente de dato + conectores + etiquetas.
  function stackLayers(){
    var L=[], n=STACK.length;
    var W0=BOUNDS[0],S0=BOUNDS[1],E0=BOUNDS[2],N0=BOUNDS[3];
    function zAt(i){ return i*(GAP+SEP*spread); }
    STACK.forEach(function(s,i){
      var z=zAt(i);
      L.push(new deck.BitmapLayer({id:'st'+i, image:s.img,
        bounds:[[W0,S0,z],[W0,N0,z],[E0,N0,z],[E0,S0,z]],
        opacity:0.97, parameters:{depthTest:true}}));
    });
    var top=zAt(n-1), corners=[[W0,S0],[W0,N0],[E0,N0],[E0,S0]];
    L.push(new deck.PathLayer({id:'stconn',
      data:corners.map(function(c){return {path:[[c[0],c[1],0],[c[0],c[1],top]]};}),
      getPath:function(d){return d.path;}, getColor:[130,205,228,110], getWidth:1.1,
      widthUnits:'pixels', updateTriggers:{getPath:[spread]}}));
    L.push(new deck.TextLayer({id:'stlbl',
      data:STACK.map(function(s,i){return {z:zAt(i),lab:s.lab};}),
      getPosition:function(d){return [E0+0.012,N0,d.z];}, getText:function(d){return d.lab;},
      getSize:12.5, getColor:[240,248,252,245], getTextAnchor:'start', getAlignmentBaseline:'center',
      fontFamily:'IBM Plex Sans, sans-serif', fontWeight:500, fontSettings:{sdf:true},
      outlineWidth:2.6, outlineColor:[6,18,26,235],
      characterSet:'auto', billboard:true, getPixelOffset:[14,0], parameters:{depthTest:false},
      updateTriggers:{getPosition:[spread]}}));
    return L;
  }

  function apply(){ if(deckgl) deckgl.setProps({viewState:Object.assign({},view)}); }
  function relayers(){ if(deckgl) deckgl.setProps({layers:buildLayers()}); }

  function tweenTo(t,dur){
    if(tweenRAF) cancelAnimationFrame(tweenRAF); tweenRAF=null;
    if(reduce||!view){ ['longitude','latitude','zoom','pitch','bearing'].forEach(function(p){ if(t[p]!=null) view[p]=t[p]; }); apply(); if(orbit) startOrbit(); return; }
    var from=Object.assign({},view), t0=performance.now();
    function step(now){
      var k=Math.min(1,(now-t0)/dur), e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
      ['longitude','latitude','zoom','pitch','bearing'].forEach(function(p){ if(t[p]!=null) view[p]=from[p]+(t[p]-from[p])*e; });
      apply();
      if(k<1){ tweenRAF=requestAnimationFrame(step); } else { tweenRAF=null; if(orbit) startOrbit(); }
    }
    tweenRAF=requestAnimationFrame(step);
  }
  function tweenReveal(target){
    if(revRAF) cancelAnimationFrame(revRAF); revRAF=null;
    if(reduce){ reveal=target; relayers(); return; }
    var from=reveal, t0=performance.now(), dur=1400;
    function step(now){
      var k=Math.min(1,(now-t0)/dur); reveal=from+(target-from)*k; relayers();
      if(k<1) revRAF=requestAnimationFrame(step); else revRAF=null;
    }
    revRAF=requestAnimationFrame(step);
  }
  function tweenSpread(target){
    if(spreadRAF) cancelAnimationFrame(spreadRAF); spreadRAF=null;
    if(reduce){ spread=target; relayers(); return; }
    var from=spread, t0=performance.now(), dur=1800;
    function step(now){ var k=Math.min(1,(now-t0)/dur), e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
      spread=from+(target-from)*e; relayers();
      if(k<1) spreadRAF=requestAnimationFrame(step); else spreadRAF=null; }
    spreadRAF=requestAnimationFrame(step);
  }
  function startOrbit(){ if(reduce) return; if(orbitRAF) cancelAnimationFrame(orbitRAF);
    (function turn(){ if(!orbit){orbitRAF=null;return;} view.bearing=((view.bearing||0)+0.12)%360; apply(); orbitRAF=requestAnimationFrame(turn); })(); }
  function stopOrbit(){ orbit=false; if(orbitRAF) cancelAnimationFrame(orbitRAF); orbitRAF=null; }
  // Animación de los pulsos de agua (~25 fps; dt acumulativo para poder variar la
  // velocidad sin saltos — en el capítulo Yaku la velocidad sigue al caudal del día).
  function startTrips(){ if(reduce||tripsRAF) return; tripsLast=performance.now();
    (function tick(now){ if(!tripsOn){tripsRAF=null;return;}
      if(now-tripsLast>=40){ tripsT=(tripsT+(now-tripsLast)/1000*tripsSpeed)%((D.trips&&D.trips.T)||10);
        tripsLast=now; relayers(); }
      tripsRAF=requestAnimationFrame(tick); })(performance.now()); }
  function stopTrips(){ tripsOn=false; if(tripsRAF) cancelAnimationFrame(tripsRAF); tripsRAF=null; }
  // Botón "Girar cuenca": órbita a demanda en cualquier capítulo (además del auto-orbit de escena).
  function updateSpinBtn(){ var b=$('sm-spin-btn'); if(!b) return;
    var lab=$('sm-spin-lab'); b.setAttribute('aria-pressed', orbit?'true':'false');
    b.classList.toggle('is-on', !!orbit); if(lab) lab.textContent=orbit?'Detener':'Girar'; }
  function toggleSpin(){ spin=!orbit; orbit=spin; if(orbit) startOrbit(); else stopOrbit(); updateSpinBtn(); }

  // ── Globo (cap. 1) ────────────────────────────────────────────────────────
  function initGlobe(){
    if(globe || typeof Globe==='undefined') return;
    try{
      globe=Globe()(document.getElementById('sm-globe'))
        .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg')
        .backgroundColor('rgba(0,0,0,0)').showAtmosphere(true)
        .atmosphereColor('#4CC4E0').atmosphereAltitude(0.22)
        .ringsData([{lat:-11.34,lng:-76.9}]).ringColor(function(){return function(t){return 'rgba(27,168,196,'+(1-t)+')';};})
        .ringMaxRadius(4).ringPropagationSpeed(3).ringRepeatPeriod(900)
        .pointsData([{lat:-11.34,lng:-76.9}]).pointColor(function(){return '#1BA8C4';})
        .pointAltitude(0.09).pointRadius(0.95);
      globe.pointOfView({lat:-11.3,lng:-77,altitude:2.3},0);
      if(!reduce){ var c=globe.controls(); c.autoRotate=true; c.autoRotateSpeed=0.55; c.enableZoom=false; }
    }catch(e){ globe=null; }
  }
  function showGlobe(on){
    var g=$('sm-globe'), d=$('sm-deck');
    if(g) g.style.display=on?'block':'none';
    if(d) d.style.opacity=on?'0':'1';
    if(on && globe){ globe.pointOfView({lat:-11.3,lng:-77,altitude:2.3},1200); }
    else if(globe){ globe.pointOfView({lat:-11.34,lng:-76.9,altitude:0.6},1600); }
  }

  // ── Control de timelapse ──────────────────────────────────────────────────
  function stopPlay(){ if(tl.timer) clearInterval(tl.timer); tl.timer=null; tl.playing=false;
    var b=$('sm-ctrl-play'); if(b){ b.querySelector('.sm-ctrl-ico').innerHTML='&#9654;'; $('sm-ctrl-play-lab').textContent='Reproducir'; } }
  function startPlay(){ if(reduce) return; stopPlay(); tl.playing=true;
    var b=$('sm-ctrl-play'); if(b){ b.querySelector('.sm-ctrl-ico').innerHTML='&#10073;&#10073;'; $('sm-ctrl-play-lab').textContent='Pausa'; }
    var ms = tl.kind==='evento'?520:750;
    tl.timer=setInterval(function(){ setFrame((tl.idx+1)%tl.n); }, ms);
  }
  function togglePlay(){ tl.playing?stopPlay():startPlay(); }

  function legendHtml(sub){
    var cmap=CMAP[sub], stops=STOPS[cmap]||STOPS.YlGnBu;
    var info = tl.kind==='clima'? D.timelapse.clima[sub]
             : tl.kind==='era5' ? D.timelapse.era5[sub]
             : {vmin:0,vmax:D.evento.vmaxPr,unidad:'mm/día'};
    var grad='linear-gradient(90deg,'+stops.join(',')+')';
    return '<div class="sm-legend-unit">'+(info.label||SUBLAB[sub]||'')+' · '+(info.unidad||'')+'</div>'+
      '<div class="sm-legend-bar" style="background:'+grad+'"></div>'+
      '<div class="sm-legend-scale"><span>'+(+info.vmin).toFixed(info.vmin<1?2:0)+'</span><span>'+
      (+info.vmax).toFixed(info.vmax<1?2:0)+'</span></div>';
  }

  function setFrame(i){
    tl.idx=i;
    if(tl.kind==='evento'){ $('sm-ctrl-lab').textContent = D.evento.fechas[i]||''; updateHydro(i);
      // los pulsos de agua corren al ritmo del caudal observado del día
      var q=D.evento.q[i]; if(q!=null){ tripsSpeed=0.4+2.6*Math.min(1,q/(D.evento.picoQ||113)); } }
    else { $('sm-ctrl-lab').textContent = MESES[i%12]; }
    var sl=$('sm-ctrl-slider'); if(sl && +sl.value!==i) sl.value=i;
    relayers();
  }

  function setupControl(kind){
    var ctrl=$('sm-ctrl'); if(!ctrl) return;
    ctrl.hidden=false; tl.kind=kind; stopPlay();
    var subs=TLSUB[kind]; tl.sub=subs[0];
    tl.n = (kind==='evento')? D.evento.n : 12;
    // segmentos (oculto si una sola variable)
    var seg=$('sm-ctrl-seg'); seg.innerHTML='';
    if(subs.length>1){
      seg.style.display='flex';
      subs.forEach(function(s){
        var b=document.createElement('button'); b.type='button';
        b.className='sm-ctrl-var'+(s===tl.sub?' is-active':''); b.textContent=SUBLAB[s]||s;
        b.setAttribute('data-sub',s);
        b.onclick=function(){ tl.sub=s; Array.prototype.forEach.call(seg.children,function(x){x.classList.toggle('is-active',x===b);});
          $('sm-legend').innerHTML=legendHtml(s); relayers(); };
        seg.appendChild(b);
      });
    } else { seg.style.display='none'; }
    var start = (kind==='clima')?2:0;   // clima arranca en Marzo (temporada húmeda, vívido)
    var sl=$('sm-ctrl-slider'); sl.max=tl.n-1; sl.value=start;
    sl.oninput=function(){ stopPlay(); setFrame(+sl.value); };
    $('sm-ctrl-play').onclick=togglePlay;
    $('sm-legend').innerHTML=legendHtml(tl.sub);
    setFrame(start);
  }
  function hideControl(){ var c=$('sm-ctrl'); if(c) c.hidden=true; stopPlay(); tl.kind=null; }

  // ── Hidrograma del evento (Plotly cliente) ───────────────────────────────
  function initHydro(){
    if(hydroInit || typeof Plotly==='undefined' || !D.evento) return;
    var ev=D.evento, x=ev.fechas, q=ev.q, pr=ev.pr;
    var trQ={x:x,y:q,type:'scatter',mode:'lines',line:{color:'#1BA8C4',width:2.4},
             fill:'tozeroy',fillcolor:'rgba(27,168,196,0.18)',name:'Caudal',hoverinfo:'skip'};
    var trPr={x:x,y:pr,type:'bar',yaxis:'y2',marker:{color:'rgba(127,211,230,0.5)'},name:'Lluvia',hoverinfo:'skip'};
    // niveles de peligro RM-049 (Yaku alcanza 'Fuerte') + vigilancia Q90
    var lvl=[], ann=[];
    (D.niveles||[]).forEach(function(nv){
      lvl.push({type:'line',xref:'paper',x0:0,x1:1,y0:nv.u,y1:nv.u,line:{color:nv.hex,width:1.2,dash:'dot'}});
      ann.push({xref:'paper',x:0.99,y:nv.u,xanchor:'right',yanchor:'bottom',text:nv.n,showarrow:false,font:{size:8,color:nv.hex}});
    });
    if(D.q90!=null) lvl.push({type:'line',xref:'paper',x0:0,x1:1,y0:D.q90,y1:D.q90,line:{color:'#8aa0ac',width:1,dash:'dot'}});
    // ventana de aviso: los 7 días previos al pico — el margen que un pronóstico
    // a 7 días habría dado para alertar (anotación factual, no un hindcast).
    if(ev.picoIdx!=null && ev.picoIdx>=7){
      lvl.push({type:'rect',xref:'x',yref:'paper',x0:x[ev.picoIdx-7],x1:x[ev.picoIdx],
        y0:0,y1:1,fillcolor:'rgba(214,137,16,0.10)',line:{width:0},layer:'below'});
      ann.push({x:x[ev.picoIdx-3],y:0.97,yref:'paper',showarrow:false,
        text:'ventana de aviso · 7 días',font:{size:8.5,color:'#e8b25c'}});
    }
    // marca del pico del evento (comunica el máximo aunque el usuario no llegue a él)
    if(ev.picoIdx!=null && q[ev.picoIdx]!=null){
      ann.push({x:x[ev.picoIdx],y:q[ev.picoIdx],text:'pico '+Math.round(q[ev.picoIdx]),
        showarrow:true,arrowhead:0,arrowcolor:'rgba(230,244,248,.6)',ax:0,ay:-16,
        font:{size:9,color:'#e8f4f8'}});
    }
    var qv=q.filter(function(v){return v!=null;});
    var ymax=Math.max(128,(qv.length?Math.max.apply(null,qv):100)*1.12);
    var dayMk={type:'line',x0:x[0],x1:x[0],y0:0,y1:1,yref:'paper',line:{color:'#ffffff',width:1.8,dash:'dot'}};
    var lay={margin:{l:30,r:40,t:10,b:20},height:158,paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
      showlegend:false,font:{color:'#cfe2ea',size:9,family:'IBM Plex Sans'},
      xaxis:{showgrid:false,tickfont:{size:8},nticks:5,color:'#9fb8c2'},
      yaxis:{range:[0,ymax],gridcolor:'rgba(150,180,195,.16)',zeroline:false,tickfont:{size:8}},
      yaxis2:{overlaying:'y',side:'right',autorange:'reversed',showgrid:false,tickfont:{size:8},color:'#9fb8c2',
        title:{text:'lluvia mm/día',font:{size:8.5,color:'#9fb8c2'}}},
      shapes:[dayMk].concat(lvl), annotations:ann};
    Plotly.newPlot('sm-hydro-plot',[trQ,trPr],lay,{displayModeBar:false,responsive:true,staticPlot:reduce});
    hydroInit=true;
  }
  // nivel RM-049 del caudal (para colorear el valor y el chip del HUD)
  function nivelDe(q){
    if(q==null) return null;
    var lv=null;
    (D.niveles||[]).forEach(function(nv){ if(q>=nv.u) lv=nv; });
    // 'disp' = variante CLARA para texto sobre tinta (contraste ≥4.5:1, WCAG);
    // Extremo va como chip granate relleno con texto blanco (auditoría de color).
    if(lv){ var disp={Moderado:'#F5A05C',Fuerte:'#FF7088',Extremo:'#FF9C8A'}[lv.n]||lv.hex;
      return {t:lv.n,hex:lv.hex,disp:disp,fill:(lv.n==='Extremo')?'#7B1E12':null}; }
    if(D.q90!=null && q>=D.q90) return {t:'Vigilancia',hex:'#F2C744',disp:'#F2C744'};
    return {t:'Normal',hex:'#35C8E8',disp:'#35C8E8'};
  }
  // Hitos narrativos del evento (índice de día → texto); se muestran en el HUD.
  var MILES=[
    {i:0,  t:'<b>Verano normal</b>: el río oscila en torno a lo habitual.'},
    {i:10, t:'<b>28 feb</b> · primer desborde en la cuenca alta (San José de Baños, INDECI).'},
    {i:18, t:'<b>8 mar</b> · el Ciclón Yaku se organiza frente a la costa central.'},
    {i:22, t:'<b>12 mar</b> · la lluvia se generaliza sobre la cuenca; el río empieza a subir.'},
    {i:25, t:'<b>15 mar</b> · PICO: 113,4 m³/s — nivel Fuerte del protocolo RM-049.'},
    {i:29, t:'<b>19 mar</b> · la escena satelital del comparador (pestaña Clima) se toma este día.'},
    {i:36, t:'<b>Fin de marzo</b> · el río baja; la huella queda en el valle.'}
  ];
  function updateHydro(i){
    if(!hydroInit) return; var ev=D.evento, x=ev.fechas[i];
    var me=$('sm-mile');
    if(me){ var m=null; for(var k=0;k<MILES.length;k++){ if(i>=MILES[k].i) m=MILES[k]; }
      if(m && me.getAttribute('data-i')!==String(m.i)){ me.setAttribute('data-i',String(m.i));
        me.style.opacity=0; (function(mm){ setTimeout(function(){ me.innerHTML=mm.t; me.style.opacity=1; },180); })(m); } }
    try{ Plotly.relayout('sm-hydro-plot',{'shapes[0].x0':x,'shapes[0].x1':x}); }catch(e){}
    var q=ev.q[i], nv=nivelDe(q);
    var qe=$('sm-hydro-q'), le=$('sm-hydro-lvl'), de=$('sm-hydro-date');
    if(qe){ qe.innerHTML=(q==null?'—':q.toFixed(0)+'<span class="sm-hydro-un"> m³/s</span>');
      if(nv){ qe.style.color=nv.disp||nv.hex; qe.style.textShadow='0 0 20px '+(nv.disp||nv.hex)+'55'; } }
    if(le){ if(nv&&q!=null){ le.hidden=false; le.textContent=nv.t.toUpperCase();
      if(nv.fill){ le.style.background=nv.fill; le.style.color='#fff'; le.style.borderColor=nv.fill; }
      else { le.style.background='transparent'; le.style.color=nv.disp||nv.hex; le.style.borderColor=nv.disp||nv.hex; } }
    else { le.hidden=true; } }
    if(de) de.textContent=x||'';
  }

  // ── Panel de evidencia (cap. 08) ──────────────────────────────────────────
  function showPlots(on){
    var p=$('sm-plots'); if(!p) return; p.hidden=!on;
    if(on && typeof Plotly!=='undefined'){
      ['grafico-story-leaderboard','grafico-story-evento'].forEach(function(id){
        var d=document.getElementById(id); if(d){ try{ Plotly.Plots.resize(d); }catch(e){} }});
      setTimeout(function(){ p.querySelectorAll('.js-plotly-plot').forEach(function(d){try{Plotly.Plots.resize(d);}catch(e){}}); },260);
    }
  }

  // ── Activar capítulo ──────────────────────────────────────────────────────
  function setScene(id){
    if(id===curCap) return; curCap=id;
    writeHash(id); updateDots(id);
    var s=SCENES[id]||SCENES.cuenca; scene=s;
    // HUD
    var stepEl=document.querySelector('.sm-step[data-cap="'+id+'"]');
    var h=stepEl?stepEl.querySelector('.sm-h'):null, num=stepEl?stepEl.querySelector('.sm-num'):null;
    var hud=$('sm-hud'); if(hud && h){ hud.hidden=false; hud.classList.add('is-on');
      $('sm-hud-title').textContent=h.textContent; $('sm-hud-num').textContent=num?num.textContent:''; }
    // botón de la visualización estratificada (solo en el capítulo 'integracion')
    var stackBtn=$('sm-stack-btn'); if(stackBtn) stackBtn.hidden=!s.stack;
    // globo vs deck
    showGlobe(!!s.globe);
    var spb=$('sm-spin-btn'); if(spb) spb.hidden=!!s.globe;
    var bs=$('sm-bigstats'); if(bs) bs.hidden=!s.bigstats;
    if(s.globe){ hideControl(); $('sm-hydro').hidden=true; showPlots(false); orbit=false; stopOrbit(); updateSpinBtn(); if(hud) hud.classList.remove('is-on'); return; }
    // exploded layer stack (capas de datos que se separan y se integran)
    if(s.stack){
      hideControl(); $('sm-hydro').hidden=true; showPlots(false); orbit=spin; if(!orbit) stopOrbit();
      spread=0;
      var vs=views().stack;
      tweenTo({longitude:vs.longitude,latitude:vs.latitude,zoom:vs.zoom,pitch:s.pitch,bearing:s.bearing}, curCap? 1900:0);
      tweenSpread(1);
      if($('sm-stack-lab')) $('sm-stack-lab').textContent='Integrar capas';
      updateSpinBtn(); return;
    }
    // timelapse / controles
    if(s.tl){ setupControl(s.tl); } else { hideControl(); }
    $('sm-hydro').hidden = (s.tl!=='evento');
    if(s.tl==='evento'){ initHydro(); updateHydro(0); }
    showPlots(!!s.plots);
    // pulsos de agua
    var wantTrips=(!!s.trips)&&!reduce;
    if(wantTrips&&!tripsOn){ tripsOn=true; startTrips(); }
    else if(!wantTrips){ stopTrips(); }
    if(s.tl!=='evento') tripsSpeed=1;
    // órbita (auto por escena o giro manual persistente)
    orbit=(!!s.orbit)||spin; if(!orbit) stopOrbit();
    // cámara + revelado + capas
    var v=views()[s.view]||views().basin;
    tweenTo({longitude:v.longitude,latitude:v.latitude,zoom:v.zoom,pitch:s.pitch||0,bearing:s.bearing||0}, curCap? 1900:0);
    tweenReveal(s.reveal!=null?s.reveal:0);
    relayers(); updateSpinBtn();
    // robustez de enlace-profundo: si se salta en frío a un capítulo con drape, re-aplica
    // las capas una vez cargada la textura (evita terreno en blanco al aterrizar directo).
    if(s.tl){ setTimeout(function(){ if(curCap===id) relayers(); }, 650); }
  }
  // Hash compartible por capítulo (#recorrido/<id>) + puntos de progreso.
  function writeHash(id){
    if(!active || !history.replaceState) return;
    try{ history.replaceState(null,'','#recorrido/'+id); }catch(e){}
  }
  function updateDots(id){
    var dots=document.querySelectorAll('.sm-dot');
    dots.forEach(function(d){ d.classList.toggle('is-on', d.getAttribute('data-cap')===id); });
  }
  // Perfil longitudinal REAL del río (cabecera→mar) como sparkline de la ficha cap.02.
  function buildPerfil(){
    var el=$('sm-perfil-spark'); if(!el || !D.terrain || !D.terrain.perfil) return;
    var pf=D.terrain.perfil, W=190, H=44, pad=3;
    var xmax=pf[pf.length-1][0]||1, ys=pf.map(function(p){return p[1];});
    var ymin=Math.min.apply(null,ys), ymax=Math.max.apply(null,ys), rng=(ymax-ymin)||1;
    function X(d){return (d/xmax*W).toFixed(1);}
    function Y(e){return (H-pad-(e-ymin)/rng*(H-2*pad)).toFixed(1);}
    var line=pf.map(function(p){return X(p[0])+','+Y(p[1]);}).join(' ');
    el.insertAdjacentHTML('beforeend',
      '<polygon points="0,'+H+' '+line+' '+W+','+H+'" fill="url(#pfg)"></polygon>'+
      '<polyline points="'+line+'" fill="none" stroke="#7FD3E3" stroke-width="1.6"'+
      ' vector-effect="non-scaling-stroke"></polyline>');
  }
  function buildDots(){
    buildPerfil();
    var wrap=$('sm-dots'); if(!wrap) return;
    document.querySelectorAll('.sm-step').forEach(function(st){
      var id=st.getAttribute('data-cap');
      var h=st.querySelector('.sm-h'), num=st.querySelector('.sm-num');
      var b=document.createElement('button'); b.type='button'; b.className='sm-dot';
      b.setAttribute('data-cap',id);
      b.setAttribute('aria-label','Capítulo '+(num?num.textContent+' · ':'')+(h?h.textContent:id));
      b.title=(num?num.textContent+' · ':'')+(h?h.textContent:id);
      b.addEventListener('click',function(){ st.scrollIntoView({behavior:reduce?'instant':'smooth',block:'center'}); });
      wrap.appendChild(b);
    });
  }

  // ── Inicialización deck + observer (perezosa al mostrar la pestaña) ────────
  function init(){
    if(inited) return; inited=true;
    // captura el destino del enlace profundo ANTES de que el primer setScene
    // reescriba el hash (#recorrido/origen pisaría el capítulo pedido).
    var deepTarget=null;
    if(location.hash.indexOf('#recorrido/')===0){ deepTarget=location.hash.slice(11).replace(/[^a-z]/g,''); }
    if(!deepTarget){ deepTarget=(location.search.match(/smcap=([a-z]+)/)||[])[1]||null; }
    D=null; try{ D=JSON.parse(document.getElementById('sm-data').textContent); }catch(e){}
    if(!D || typeof deck==='undefined' || !D.terrain){ document.querySelector('.sm-immersive').classList.add('is-fallback'); return; }
    BOUNDS=D.terrain.bounds; DECODER=D.terrain.elevationDecoder; EMAX=D.terrain.elevMax||5000;
    // exagera el relieve: escala los decoders y (en buildLayers) la z de vectores.
    DECODER={rScaler:DECODER.rScaler*EXAG, gScaler:DECODER.gScaler*EXAG, bScaler:DECODER.bScaler*EXAG, offset:(DECODER.offset||0)*EXAG};
    view=Object.assign({}, views().basin, {pitch:0,bearing:0,minZoom:7.2,maxZoom:12.5,minPitch:0,maxPitch:78});
    var lighting=new deck.LightingEffect({
      amb:new deck.AmbientLight({color:[236,246,252],intensity:1.1}),
      sun:new deck.DirectionalLight({color:[255,244,224],intensity:1.45,direction:[-0.8,-2.6,-1.2]})
    });
    try{
      deckgl=new deck.DeckGL({
        container:'sm-deck', views:[new deck.MapView({repeat:false})],
        viewState:view, controller:{dragRotate:true,touchRotate:true,dragPan:true,doubleClickZoom:false,scrollZoom:false,touchZoom:false,inertia:220},
        effects:[lighting], layers:buildLayers(),
        parameters:{clearColor:[0.024,0.07,0.10,0]},
        onViewStateChange:function(e){ view=e.viewState; if(tweenRAF){cancelAnimationFrame(tweenRAF);tweenRAF=null;} spin=false; stopOrbit(); updateSpinBtn(); apply(); },
        getTooltip:function(o){ if(o&&o.object&&o.object.properties&&o.object.properties.desc)
          return {text:o.object.properties.nombre+'\n'+o.object.properties.desc}; return null; }
      });
    }catch(e){ document.querySelector('.sm-immersive').classList.add('is-fallback'); return; }
    initGlobe();
    // botón separar/integrar del exploded stack
    var sb=$('sm-stack-btn');
    if(sb) sb.onclick=function(){ var t=spread>0.5?0:1; tweenSpread(t);
      if($('sm-stack-lab')) $('sm-stack-lab').textContent=(t>0.5?'Integrar capas':'Separar capas'); };
    var spb=$('sm-spin-btn'); if(spb) spb.onclick=toggleSpin;   // girar/detener la cuenca
    // observer de capítulos
    obs=new IntersectionObserver(function(ents){
      ents.forEach(function(en){ if(en.isIntersecting){
        var el=en.target; document.querySelectorAll('.sm-step').forEach(function(s){s.classList.toggle('is-active',s===el);});
        setScene(el.getAttribute('data-cap'));
      }});
    }, {threshold:0, rootMargin:'-45% 0px -45% 0px'});
    document.querySelectorAll('.sm-step').forEach(function(s){ obs.observe(s); });
    // primer capítulo
    var first=document.querySelector('.sm-step'); if(first){ first.classList.add('is-active'); setScene(first.getAttribute('data-cap')); }
    // pista de scroll: ocultar tras primer scroll dentro del recorrido
    window.addEventListener('scroll', function(){ var im=document.querySelector('.sm-immersive'); if(im) im.classList.add('is-moved'); }, {passive:true,once:true});
    buildDots();
    // Scroll-scrub del capítulo Yaku: el avance dentro del paso alto (340vh) mapea
    // al día 0–45 del evento (cuantizado; rAF-throttled). El slider sigue activo.
    var scrubRAF=null;
    window.addEventListener('scroll', function(){
      if(scrubRAF || !active || curCap!=='yaku' || tl.kind!=='evento' || tl.playing) return;
      scrubRAF=requestAnimationFrame(function(){
        scrubRAF=null;
        var st=document.querySelector('.sm-step[data-cap="yaku"]'); if(!st) return;
        var r=st.getBoundingClientRect(), total=r.height-window.innerHeight;
        if(total<=0) return;
        var p=Math.min(1,Math.max(0,-r.top/total));
        var i=Math.round(p*(tl.n-1));
        if(i!==tl.idx) setFrame(i);
      });
    }, {passive:true});
    // Enlace profundo a un capítulo (#recorrido/<id> o ?smcap=<id>). Si el destino
    // usa drape (timelapse), se precalienta el terreno pasando primero por 'relieve'
    // (evita la malla en blanco del primer render con textura de timelapse).
    var qp=deepTarget;
    if(qp && SCENES[qp]){
      var go=function(id,delay){ setTimeout(function(){
        var st=document.querySelector('.sm-step[data-cap="'+id+'"]');
        if(st) st.scrollIntoView({block:'center'}); }, delay); };
      if(SCENES[qp].tl){ go('relieve',400); go(qp,1500); } else { go(qp,500); }
    }
  }

  function pause(){ stopOrbit(); stopPlay(); stopTrips(); if(globe){ try{globe.controls().autoRotate=false;}catch(e){} } }
  function resume(){ if(!inited){ init(); return; } if(scene && scene.orbit){ orbit=true; startOrbit(); }
    if(scene && scene.trips && !reduce){ tripsOn=true; startTrips(); }
    if(globe && !reduce){ try{globe.controls().autoRotate=true;}catch(e){} } }

  // Enganche al sistema de pestañas del dashboard.
  document.addEventListener('hidroalerta:tabshown', function(e){
    var p=e.detail&&e.detail.panel; var on=p&&p.id==='tab-recorrido';
    active=on; if(on){ setTimeout(resume,60); } else { pause(); }
  });
  // Si ya está activa al cargar (deep-link #recorrido).
  function boot(){ var p=document.getElementById('tab-recorrido'); if(p && !p.hidden){ setTimeout(init,80); } }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',boot); else boot();
})();
"""

