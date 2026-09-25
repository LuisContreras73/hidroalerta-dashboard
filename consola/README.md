# Receptor de suelo y nivel de la consola

## Estado de entrega (25 de septiembre de 2026)

Implementado y probado en localhost. La versión pública actual sigue pendiente de reemplazo:
la primera publicación devuelve `500 FUNCTION_INVOCATION_FAILED`. PostgreSQL Neon ya está
provisionado, su esquema fue creado, y Vercel quedó conectado al repositorio
`LuisContreras73/hidroalerta-dashboard` con `consola` como raíz de despliegue. El siguiente
commit dentro de `consola/` debe activar la compilación automática corregida. Aún falta
configurar `CONSOLE_CONFIG_JSON` como secreto y verificar el despliegue público con
`https://hidroalerta-telemetria.vercel.app/health`.
No se han publicado claves ni mediciones. La clave de GitHub no forma parte del proyecto.

Única página existente modificada: `docs/consola.html`. `docs/consola-live.js` es su cliente.
Todo el receptor, despliegue y pruebas están en `consola/`. No se regenera `docs/index.html`
ni se cambian otras páginas, datos, modelos, imágenes o generadores.

## Contrato para el compañero IoT

Transporte: HTTPS. Endpoint: **POST `<ORIGEN_PUBLICADO>/v1/telemetry`**.
`<ORIGEN_PUBLICADO>` es un marcador; se reemplaza después de publicar y probar.

Cabeceras:

```http
Content-Type: application/json
Authorization: Bearer <CLAVE_DEL_SENSOR>
```

Nodo de nivel:

```json
{"device":"nivel_01","ts":"2026-09-25T12:00:00Z","nivel_cm":123.4,"temp_c":20.1,"bateria_v":3.9,"rssi":-82}
```

Nodo de suelo:

```json
{"device":"suelo_01","ts":"2026-09-25T12:00:00Z","suelo":42.5,"bateria_v":3.8,"rssi":-85}
```

Son ejemplos sintéticos. Usar la fecha real de medición, reloj sincronizado por NTP y
zona horaria explícita. `nivel_cm` es **nivel calibrado**, no distancia ultrasónica sin convertir.
`suelo` es humedad en porcentaje **calibrada**, no la lectura ADC cruda.
Omitir campos no medidos; cero es una medición válida. No enviar `null`, texto ni NaN.
Nunca colocar el token GitHub en el dispositivo o en la consola.

Cada sensor tiene una clave distinta y campos permitidos. Las lecturas se unen por estación
y conservan fecha y procedencia por campo. La batería, señal y temperatura se muestran con
la última lectura de ese campo; no son promedios de los dos dispositivos.

Respuestas: 201 almacenado, 200 repetición idéntica, 400 contenido inválido,
401 clave inválida, 413 tamaño superior a 8 KiB, 415 tipo incorrecto y 503 almacenamiento
temporalmente indisponible en Vercel. Ante timeout/503 reintentar el mismo mensaje
con espera creciente. Una repetición idéntica es idempotente mientras siga en el historial.
Las lecturas atrasadas quedan en el historial pero no reemplazan un campo más reciente.
Para dos valores del mismo campo con la misma fecha, se conserva el primero como último.
Se retienen hasta 10 000 mensajes por estación; **no es un archivo científico permanente**.

Cadencia inicial: 30 segundos por nodo. El cliente consulta cada 3 segundos después de
cada respuesta (no son WebSockets). Tras 120 segundos sin una nueva medición, marca el
campo como antiguo y deja de mostrarlo como actual. Ajustar estos valores al protocolo real
y a las cuotas del proveedor antes de una operación permanente.

Lectura: `GET <ORIGEN_PUBLICADO>/v1/stations/est_santo_domingo_01/latest`
con `Authorization: Bearer <CLAVE_SOLO_LECTURA>`.
Devuelve `station`, `server_time`, `latest` por campo y hasta 120 mensajes de `history`.
Comprobación de proceso: `GET <ORIGEN_PUBLICADO>/health` (no comprueba la base de datos).

## Ejecución local

Desde la raíz del repositorio:

```powershell
python consola/init_config.py
python consola/server.py
```

El inicializador crea `consola/credentials.local.json`, excluido de Git. No lo vuelve a
generar si existe. Proporcionar privadamente a cada nodo sólo su clave; la clave de lectura
se introduce mediante **Conectar sensores**. Las claves no se imprimen ni se guardan en HTML.

En otra terminal:

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory docs
```

Abrir `http://127.0.0.1:8765/consola.html`, conectar al origen `http://127.0.0.1:8787`.
La API está limitada a localhost de forma predeterminada. Esta URL no sirve a un compañero
en otra red. No exponer el servidor HTTP directamente a Internet: usar TLS y límites de
tráfico en el alojamiento. La base SQLite local se guarda en `consola/telemetry.db` (ignorada).

## Despliegue recomendado: Vercel + PostgreSQL

Vercel admite el handler Python en `api/index.py`; SQLite local no es persistente allí.
El adaptador PostgreSQL comparte exactamente la validación y los permisos del receptor local.
El SQL usa transacciones y bloqueo por estación para escrituras concurrentes.

1. Iniciar sesión en Vercel. Importar el repositorio con **Root Directory = `consola`** y
   Framework Preset **Other**, sin cambiar el alojamiento GitHub Pages del dashboard.
2. Crear/conectar PostgreSQL (por ejemplo Neon desde el Marketplace) tras revisar su plan
   y condiciones. No se ha autorizado contratar un servicio de pago.
3. Ejecutar `schema.sql` en esa base dedicada. Configurar `DATABASE_URL` con conexión TLS.
4. Añadir `CONSOLE_CONFIG_JSON` como variable secreta de Vercel con el contenido de
   `credentials.local.json`. Su `allowed_origins` debe incluir
   `https://luiscontreras73.github.io` y el origen real si se usa un dominio personalizado.
5. Desplegar. La API usa `vercel.json` para `/v1/telemetry`, `/v1/stations/.../latest` y
   `/health`. Excluir archivos privados con `.vercelignore` incluso al desplegar por CLI.
6. Verificar HTTPS, error 401 sin clave, POST de ambos nodos, lectura combinada, CORS desde
   GitHub Pages y persistencia tras redeploy. La clave de lectura no debe autorizar POST.
   Revisar que la protección de despliegue no exija una sesión Vercel a los sensores.
7. Entregar el origen público y las claves de cada nodo por canal privado. Abrir la consola,
   pulsar Conectar sensores e ingresar origen, estación y clave de lectura.

La consola recuerda origen y estación; la clave vive sólo en memoria y se solicita de nuevo
al recargar. No se ha fijado una URL ficticia como valor predeterminado.

Alternativas evaluadas: Firebase Realtime Database admite escritura REST y sincronización,
pero requiere crear un proyecto y configurar identidad/reglas. Un servidor con disco
persistente puede ejecutar `server.py` detrás de HTTPS. GitHub Pages sólo sirve la interfaz;
un token de GitHub no crea un receptor HTTP de telemetría.

Fuentes oficiales:
- https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages
- https://vercel.com/kb/guide/is-sqlite-supported-in-vercel
- https://vercel.com/docs/functions/runtimes/python/api-directory
- https://vercel.com/docs/marketplace-storage
- https://firebase.google.com/docs/database/rest/start

## Validación

```powershell
python consola/test_server.py
node consola/test_console.cjs
```

Probado: autenticación y permisos por sensor, suelo=0, unidades, mensajes antiguos,
idempotencia, CORS, persistencia SQLite, cambio demo/en vivo, respuestas tardías y errores
de conexión sin regresar a simulación. Revisión real en navegador local: 1.23 m y 42.0 %
de una estación sintética aislada; caudal/probabilidad se mantienen sin inventar valores.
`browser_fixture.py` sirve únicamente para esa prueba en localhost, estación `test`.

Pendiente de infraestructura: integración PostgreSQL real, build y rutas de Vercel,
prueba pública HTTPS, publicación GitHub y prueba con hardware del compañero.
