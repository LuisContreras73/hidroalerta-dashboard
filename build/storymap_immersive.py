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
                 "<b>anticiparlo</b>.",
             ]),
        dict(id="cuenca", num="02", eyebrow="La cuenca, vista desde arriba",
             titulo="Tres mil kilómetros cuadrados de montaña y valle",
             parrafos=[
                 f"La cuenca del Chancay–Huaral abarca <b>{area:,.0f} km²</b> organizados en "
                 f"<b>{nsub} subcuencas</b>. Desde aquí, a vista de satélite, parece un mapa "
                 "plano; pero su historia se cuenta en la <b>tercera dimensión</b>.",
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
                 "anticipar el caudal.",
             ]),
        dict(id="yaku", num="08", eyebrow="Marzo 2023 · Ciclón Yaku",
             titulo="Cuando el río creció de verdad",
             parrafos=[
                 "En marzo de 2023 el <b>Ciclón Yaku</b> descargó lluvias extraordinarias "
                 "sobre la costa central. Avance día a día: la lluvia se enciende sobre la "
                 "cuenca mientras el <b>caudal observado</b> en Santo Domingo se dispara.",
                 "De un caudal habitual cercano a <b>17 m³/s</b>, el río llegó a "
                 "<b>113 m³/s el 15 de marzo</b> —más de seis veces lo normal—. Es "
                 "exactamente el tipo de crecida que un sistema de alerta debe ver venir.",
             ]),
        dict(id="alerta", num="09", eyebrow="Anticipar el agua",
             titulo="Del viaje del agua a la alerta temprana",
             parrafos=[
                 f"A la salida de la cuenca, la estación <b>{est.get('nombre','Santo Domingo')}</b> "
                 f"mide el caudal que llega al valle. Cuando supera el <b>umbral Q90 = "
                 f"{umbral:.1f} m³/s</b>, hablamos de crecida peligrosa.",
                 "El modelo <b>RA-TFT</b> sostiene la habilidad de pronóstico a varios días de "
                 "anticipación: cada día ganado es tiempo para alertar, evacuar o manejar el "
                 "riego. Ese es el destino del viaje: <b>convertir el agua en información y la "
                 "información en protección</b>.",
             ]),
    ]


def recorrido_html(meta, leaderboard_div: str, forecast_div: str,
                   data_json: str) -> str:
    """HTML de la pestaña «Recorrido»: escenario 3D full-screen (sticky) + narrativa scroll.

    leaderboard_div / forecast_div: figuras Plotly (server) que se muestran en el cap. 08.
    data_json: JSON embebido con terrain/timelapse/evento + GeoJSON de ríos/subcuencas/puntos
    (los PNG se referencian relativos a media/). Se embebe inline (autocontenido, como el resto
    del dashboard); el JS lo lee de #sm-data."""
    caps = _capitulos(meta)

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
            f"</div></section>")
    narrativa = "\n".join(pasos)

    # Config mínima al JS (colores + parámetros del terreno). Todo lo demás por fetch.
    cfg = {
        "bounds": None,          # lo trae terrain_meta.json
        "exag": 4.0,             # exageración vertical del relieve
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

        <!-- Hidrograma del evento Yaku (Plotly cliente), visible solo en el cap. 07. -->
        <div class="sm-hydro" id="sm-hydro" hidden>
          <div class="sm-hydro-head">
            <span class="sm-hydro-t">Caudal observado · Santo Domingo (47E214D2)</span>
            <span class="sm-hydro-q mono" id="sm-hydro-q">—</span>
          </div>
          <div id="sm-hydro-plot" class="sm-hydro-plot"></div>
        </div>

        <!-- Panel de evidencia (Plotly server), visible solo en el cap. 08. -->
        <div class="sm-plots" id="sm-plots" hidden>
          <div class="sm-plot-card">
            <p class="sm-plot-cap">Habilidad (NSE) sostenida según el horizonte de pronóstico</p>
            {leaderboard_div}
          </div>
          <div class="sm-plot-card">
            <p class="sm-plot-cap">Pronóstico probabilístico anticipando el cruce del umbral</p>
            {forecast_div}
          </div>
        </div>

        <!-- Botón de la visualización estratificada (exploded layers), solo cap. 07. -->
        <button type="button" class="sm-stack-btn" id="sm-stack-btn" hidden
                aria-label="Separar o integrar las capas de datos">
          <span class="sm-stack-ico" aria-hidden="true">&#8645;</span>
          <span id="sm-stack-lab">Integrar capas</span>
        </button>

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
.sm-hydro{position:absolute;right:22px;bottom:96px;z-index:4;width:min(430px,90vw);
  padding:11px 13px 6px;border-radius:14px;background:rgba(9,22,31,.74);
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  border:1px solid rgba(120,170,190,.28);box-shadow:0 12px 40px rgba(0,0,0,.42);}
.sm-hydro-head{display:flex;justify-content:space-between;align-items:baseline;gap:10px;margin-bottom:4px;}
.sm-hydro-t{font-size:11.5px;color:#cfe2ea;}
.sm-hydro-q{font-size:16px;font-weight:600;color:var(--cyan,#1BA8C4);}
.sm-hydro-plot{height:150px;}
.sm-plots{position:absolute;right:22px;top:calc(var(--nav-h,60px) + 30px);z-index:4;
  width:min(560px,92vw);max-height:calc(100vh - var(--nav-h,60px) - 130px);overflow:auto;
  display:flex;flex-direction:column;gap:14px;}
.sm-plot-card{padding:12px 14px;border-radius:14px;background:rgba(247,249,251,.97);
  border:1px solid var(--border,#E2E8EE);box-shadow:0 12px 40px rgba(0,0,0,.34);}
.sm-plot-cap{font-family:var(--sans,sans-serif);font-size:12.5px;color:var(--ink,#0C1E2A);
  margin:0 0 6px;font-weight:600;}
.sm-stack-btn{position:absolute;left:50%;bottom:30px;transform:translateX(-50%);z-index:4;
  display:inline-flex;align-items:center;gap:8px;cursor:pointer;
  font-family:var(--sans,sans-serif);font-size:13px;color:#eaf2f6;padding:9px 18px;
  border-radius:999px;background:rgba(9,22,31,.72);backdrop-filter:blur(10px);
  -webkit-backdrop-filter:blur(10px);border:1px solid rgba(120,170,190,.30);
  box-shadow:0 10px 34px rgba(0,0,0,.4);transition:.18s;}
.sm-stack-btn:hover{background:rgba(16,38,50,.85);}
.sm-stack-ico{font-size:15px;color:var(--cyan,#1BA8C4);}
.sm-scroll-hint{position:absolute;left:50%;bottom:20px;transform:translateX(-50%);z-index:3;
  display:flex;flex-direction:column;align-items:center;gap:4px;font-size:11.5px;
  letter-spacing:.08em;color:rgba(230,240,246,.8);pointer-events:none;transition:opacity .5s;}
.sm-scroll-ico{font-size:16px;animation:sm-bob 1.6s ease-in-out infinite;}
@keyframes sm-bob{0%,100%{transform:translateY(0);}50%{transform:translateY(6px);}}
.sm-immersive.is-moved .sm-scroll-hint{opacity:0;}
.sm-steps{position:relative;z-index:2;margin-top:-100vh;pointer-events:none;}
.sm-step{min-height:100vh;display:flex;align-items:center;padding:0 36px;pointer-events:none;}
.sm-card{pointer-events:auto;max-width:430px;padding:26px 28px;border-radius:18px;
  background:rgba(8,20,28,.60);backdrop-filter:blur(14px) saturate(1.2);
  -webkit-backdrop-filter:blur(14px) saturate(1.2);border:1px solid rgba(120,170,190,.24);
  box-shadow:0 18px 60px rgba(0,0,0,.5);
  opacity:.14;transform:translateY(26px) scale(.99);transition:opacity .6s ease,transform .6s ease;}
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
  var view=null, tweenRAF=null, orbitRAF=null, orbit=false, curCap=null;
  var reveal=0, revRAF=null, spread=0, spreadRAF=null;
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
    cuenca:   {tex:'satellite',pitch:0, bearing:0,  view:'basin', reveal:0, subs:true},
    relieve:  {tex:'satellite',pitch:52,bearing:-16,view:'basin', reveal:0.35},
    cabeceras:{tex:'satellite',pitch:56,bearing:-22,view:'head',  reveal:1, rivers:true,points:true,heads:true,orbit:true},
    clima:    {tex:'relief',   pitch:50,bearing:-10,view:'basin', reveal:0.7,rivers:true,heads:true,tl:'clima'},
    invisible:{tex:'relief',   pitch:50,bearing:-10,view:'basin', reveal:0.6,rivers:true,tl:'era5'},
    integracion:{stack:true,   pitch:54,bearing:22, view:'stack'},
    yaku:     {tex:'relief',   pitch:54,bearing:-6, view:'valley',reveal:0.85,rivers:true,points:true,tl:'evento'},
    alerta:   {tex:'satellite',pitch:42,bearing:0,  view:'basin', reveal:0.55,rivers:true,points:true,plots:true}
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
      basin: {longitude:(w+e)/2, latitude:(s+n)/2-0.01, zoom:9.6},
      head:  {longitude:-76.66,  latitude:-11.18,        zoom:10.3},
      valley:{longitude:-77.02,  latitude:-11.40,        zoom:9.95},
      stack: {longitude:(w+e)/2+0.06, latitude:(s+n)/2-0.05, zoom:8.4}
    };
  }

  function currentTexture(){
    if(tl.kind==='clima')  return 'media/clima/'+tl.sub+'_'+pad(tl.idx+1)+'.png';
    if(tl.kind==='era5')   return 'media/era5/'+tl.sub+'_'+pad(tl.idx+1)+'.png';
    if(tl.kind==='evento') return 'media/evento/pr_'+pad(tl.idx)+'.png';
    return scene.tex==='relief'? TEX.relief : TEX.satellite;
  }

  function buildLayers(){
    if(!D) return [];
    var L=[];
    if(scene.stack) return stackLayers();
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
        fontFamily:'IBM Plex Sans, sans-serif', fontWeight:600,
        outlineWidth:2, outlineColor:[6,18,26,220], getTextAnchor:'middle', getAlignmentBaseline:'bottom'
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
        fontFamily:'IBM Plex Sans, sans-serif', fontWeight:500,
        outlineWidth:2, outlineColor:[6,18,26,210], getTextAnchor:'middle', getAlignmentBaseline:'bottom'
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
      fontFamily:'IBM Plex Sans, sans-serif', fontWeight:500, outlineWidth:2.5, outlineColor:[6,18,26,235],
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
    (function spin(){ if(!orbit){orbitRAF=null;return;} view.bearing=(view.bearing+0.06)%360; apply(); orbitRAF=requestAnimationFrame(spin); })(); }
  function stopOrbit(){ orbit=false; if(orbitRAF) cancelAnimationFrame(orbitRAF); orbitRAF=null; }

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
    if(tl.kind==='evento'){ $('sm-ctrl-lab').textContent = D.evento.fechas[i]||''; updateHydro(i); }
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
    var lay={margin:{l:36,r:36,t:6,b:20},height:150,paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
      showlegend:false,font:{color:'#cfe2ea',size:9,family:'IBM Plex Sans'},
      xaxis:{showgrid:false,tickfont:{size:8},nticks:5,color:'#9fb8c2'},
      yaxis:{title:{text:'m³/s',font:{size:9}},rangemode:'tozero',gridcolor:'rgba(150,180,195,.18)',zeroline:false},
      yaxis2:{overlaying:'y',side:'right',autorange:'reversed',showgrid:false,tickfont:{size:8},color:'#9fb8c2'},
      shapes:[{type:'line',x0:x[0],x1:x[0],y0:0,y1:1,yref:'paper',line:{color:'#C0392B',width:2,dash:'dot'}}]};
    Plotly.newPlot('sm-hydro-plot',[trQ,trPr],lay,{displayModeBar:false,responsive:true,staticPlot:reduce});
    hydroInit=true;
  }
  function updateHydro(i){
    if(!hydroInit) return; var ev=D.evento, x=ev.fechas[i];
    try{ Plotly.relayout('sm-hydro-plot',{'shapes[0].x0':x,'shapes[0].x1':x}); }catch(e){}
    var q=ev.q[i]; $('sm-hydro-q').textContent=(q==null?'—':q.toFixed(0)+' m³/s');
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
    if(s.globe){ hideControl(); $('sm-hydro').hidden=true; showPlots(false); if(hud) hud.classList.remove('is-on'); return; }
    // exploded layer stack (capas de datos que se separan y se integran)
    if(s.stack){
      hideControl(); $('sm-hydro').hidden=true; showPlots(false); orbit=false; stopOrbit();
      spread=0;
      var vs=views().stack;
      tweenTo({longitude:vs.longitude,latitude:vs.latitude,zoom:vs.zoom,pitch:s.pitch,bearing:s.bearing}, curCap? 1600:0);
      tweenSpread(1);
      if($('sm-stack-lab')) $('sm-stack-lab').textContent='Integrar capas';
      return;
    }
    // timelapse / controles
    if(s.tl){ setupControl(s.tl); } else { hideControl(); }
    $('sm-hydro').hidden = (s.tl!=='evento');
    if(s.tl==='evento'){ initHydro(); updateHydro(0); }
    showPlots(!!s.plots);
    // órbita
    orbit=!!s.orbit; if(!orbit) stopOrbit();
    // cámara + revelado + capas
    var v=views()[s.view]||views().basin;
    tweenTo({longitude:v.longitude,latitude:v.latitude,zoom:v.zoom,pitch:s.pitch||0,bearing:s.bearing||0}, curCap? 1600:0);
    tweenReveal(s.reveal!=null?s.reveal:0);
    relayers();
  }

  // ── Inicialización deck + observer (perezosa al mostrar la pestaña) ────────
  function init(){
    if(inited) return; inited=true;
    D=null; try{ D=JSON.parse(document.getElementById('sm-data').textContent); }catch(e){}
    if(!D || typeof deck==='undefined' || !D.terrain){ document.querySelector('.sm-immersive').classList.add('is-fallback'); return; }
    BOUNDS=D.terrain.bounds; DECODER=D.terrain.elevationDecoder; EMAX=D.terrain.elevMax||5000;
    // exagera el relieve: escala los decoders y (en buildLayers) la z de vectores.
    DECODER={rScaler:DECODER.rScaler*EXAG, gScaler:DECODER.gScaler*EXAG, bScaler:DECODER.bScaler*EXAG, offset:(DECODER.offset||0)*EXAG};
    view=Object.assign({}, views().basin, {pitch:0,bearing:0,minZoom:7.2,maxZoom:12.5,minPitch:0,maxPitch:78});
    var lighting=new deck.LightingEffect({
      amb:new deck.AmbientLight({color:[255,255,255],intensity:1.2}),
      sun:new deck.DirectionalLight({color:[255,246,228],intensity:1.2,direction:[-1,-3,-1.2]})
    });
    try{
      deckgl=new deck.DeckGL({
        container:'sm-deck', views:[new deck.MapView({repeat:false})],
        viewState:view, controller:{dragRotate:true,touchRotate:true,doubleClickZoom:false,scrollZoom:{speed:0.02,smooth:true},inertia:220},
        effects:[lighting], layers:buildLayers(),
        parameters:{clearColor:[0.024,0.07,0.10,0]},
        onViewStateChange:function(e){ view=e.viewState; if(tweenRAF){cancelAnimationFrame(tweenRAF);tweenRAF=null;} stopOrbit(); apply(); },
        getTooltip:function(o){ if(o&&o.object&&o.object.properties&&o.object.properties.desc)
          return {text:o.object.properties.nombre+'\n'+o.object.properties.desc}; return null; }
      });
    }catch(e){ document.querySelector('.sm-immersive').classList.add('is-fallback'); return; }
    initGlobe();
    // botón separar/integrar del exploded stack
    var sb=$('sm-stack-btn');
    if(sb) sb.onclick=function(){ var t=spread>0.5?0:1; tweenSpread(t);
      if($('sm-stack-lab')) $('sm-stack-lab').textContent=(t>0.5?'Integrar capas':'Separar capas'); };
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
    // Enlace profundo a un capítulo (?smcap=<id>): centra ese paso (útil para compartir/QA).
    var qp=(location.search.match(/smcap=([a-z]+)/)||[])[1];
    if(qp){ setTimeout(function(){ var s=document.querySelector('.sm-step[data-cap="'+qp+'"]'); if(s) s.scrollIntoView({block:'center'}); }, 500); }
  }

  function pause(){ stopOrbit(); stopPlay(); if(globe){ try{globe.controls().autoRotate=false;}catch(e){} } }
  function resume(){ if(!inited){ init(); return; } if(scene && scene.orbit){ orbit=true; startOrbit(); }
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

