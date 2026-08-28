# Informe técnico completo — `horizonai-whatsapp-bot`
### Documento base para migrar el servicio dentro del Manager principal (Horizon Manager)

Fecha: 2026-08-03 · Rama analizada: `fix/cfmoto-history-sync-token` (HEAD `e937e71`) · 74 commits · ~2.700 LOC de aplicación

---

## 1. Resumen ejecutivo

`horizonai-whatsapp-bot` es un **microservicio Flask stateless-ish** que actúa de puente entre Twilio WhatsApp, OpenAI Assistants y la API del Horizon Manager (CRM). Es **multi-cliente (multi-tenant) por número de WhatsApp**: un único proceso atiende N bots, cada uno con su assistant de OpenAI, su token de Horizon, su número Twilio y su metadata de comportamiento.

Cumple 6 funciones de negocio:

| # | Función | Punto de entrada |
|---|---------|------------------|
| 1 | Recibir mensajes WhatsApp y responder con IA | `POST /webhook/whatsapp` |
| 2 | Extraer leads de la conversación y crearlos/actualizarlos en el CRM | function-calling → `/api/leads/` |
| 3 | Notificar por WhatsApp al vendedor/sucursal asignado al lead | Twilio Content Template |
| 4 | Agendar citas contra la agenda de vendedores del CRM | function-calling → `/api/agendamientos/` |
| 5 | Respetar el *human handoff* del CRM (si un humano toma el chat, el bot calla) | `GET /api/bot/control-status/` |
| 6 | Enviar mensajes salientes iniciados por Horizon Flow (free/template + ventana 24 h) | `POST /outbound/whatsapp/send` |

**Implicancia clave para la migración:** hoy el bot es *cliente HTTP* del Manager para casi todo (leads, vendedores, agendamientos, flow-history, control-status, config del bot) **y además** lee directo la base de datos del Manager por SQL (`gestion_whatsappbot`, `gestion_empresa`, `api_apitoken`). Al migrar dentro del Manager, **la mayoría de esas llamadas HTTP se convierten en llamadas internas ORM/servicio** y desaparecen los problemas de tokens per-company (hoy la fuente #1 de bugs, ver §11).

---

## 2. Stack tecnológico

### 2.1 Runtime y dependencias (`requirements.txt`, versiones exactas)

| Componente | Versión | Uso |
|---|---|---|
| Python | 3.11-slim (Dockerfile) | Runtime. Usa `zoneinfo`, `datetime.UTC` (requiere ≥3.11) |
| Flask | 3.0.3 | Framework web, app factory + blueprints |
| gunicorn | 21.2.0 | WSGI server (`gunicorn wsgi:app --bind 0.0.0.0:8000`) |
| redis | 5.0.7 | Cliente Redis (`decode_responses=True`) |
| requests | 2.32.3 | Todas las llamadas HTTP salientes a Horizon |
| httpx | 0.27.0 | Sólo como `http_client` explícito del SDK de OpenAI |
| openai | 1.51.0 | **Assistants API v2 (beta)** + Chat Completions + Responses API |
| twilio | 9.3.1 | REST client + `MessagingResponse` (TwiML) |
| SQLAlchemy | 2.0.35 | Acceso read-only a la BD del Manager (Core, no ORM) |
| psycopg2-binary | 2.9.9 | Driver PostgreSQL |
| PyMySQL | 1.1.1 | Driver MySQL (se elige por puerto 3306) |
| python-dotenv | 1.0.1 | Carga de `.env` |
| pytest | 8.3.2 | Tests (23 tests, todos pasan) |
| fakeredis | 2.23.2 | Redis en memoria para tests |

No hay ORM propio, no hay migraciones, no hay modelos: **el servicio no tiene base de datos propia**. Todo su estado vive en Redis (efímero) o en el Manager (persistente).

### 2.2 Infraestructura

- **Docker Compose** (`docker-compose.yml`): servicio `web` (gunicorn, host `:8001` → contenedor `:8000`) + `redis:7-alpine` (host `:6380` → `:6379`, volumen `redis-data`).
- Requiere red Docker externa **`horizonaimanager_horizonai-internal`** (para alcanzar al Manager) y `host.docker.internal:host-gateway` (túneles SSH a la BD).
- **Nginx** (`nginx.conf`): TLS Let's Encrypt, rate-limit sólo en `/webhook/` (`1r/s`, burst 10), proxy a `localhost:8001` para `/webhook/`, `/bots/`, `/outbound/`, `/health`; **todo lo demás → 404**.
- **Despliegue alternativo systemd**: `deploy.sh` hace `git reset --hard origin/main` + `pip install` + `systemctl restart horizonai-bots`; logs vía `journalctl -u horizonai-bots`. `logging_config.py` está escrito para stdout/journald.
- Scripts operativos: `crear-cliente.sh` (onboarding vía API), `monitor-clientes.sh`, `install-server*.sh`, `cleanup-server.sh`, `fix-server-installation.sh`.
- Dominio productivo documentado: `https://whatsapp.horizonai.cl`.

### 2.3 Estructura del código

```
wsgi.py                            # create_app()
app/__init__.py                    # app factory, extensiones, /health, /debug/routes
app/config.py                      # BaseConfig + Development/Testing/Production (FLASK_ENV)
app/extensions.py                  # RedisExtension, OpenAIExtension, TwilioExtension,
                                   # HorizonExtension (requests.Session), DatabaseExtension (SQLAlchemy)
app/logging_config.py              # logging a stdout, nivel INFO
app/routes/
  whatsapp.py    (186 L)           # POST/GET /webhook/whatsapp  → TwiML XML
  bots.py        (225 L)           # CRUD de bots + client_data (JSON)
  outbound.py    (257 L)           # /outbound/whatsapp/send + /status (HMAC)
app/services/
  conversation_service.py  (865 L) # Orquestador principal del turno de conversación
  custom_functions_service.py (1372 L) # Function-calling: leads, vendedores, agenda, notificaciones
  openai_service.py        (611 L) # Assistants API: threads, runs, tool outputs
  twilio_service.py        (141 L) # Envío de mensajes y templates
  horizon_service.py        (66 L) # Ejecutor genérico de "horizon_actions" declarativas
  horizon_config_loader.py (159 L) # GET /api/bot/config/ + cache Redis 5 min
  client_data_service.py   (214 L) # Slots del cliente en Redis + extracción por regex
  outbound_whatsapp_service.py (285 L) # Ventana 24 h, idempotencia, correlación de status
app/repositories/
  bot_repository.py         (43 L) # Hash Redis `bots:registry`
  sql_bot_repository.py     (52 L) # SELECT sobre gestion_whatsappbot
app/utils/validation.py     (14 L)
tests/                             # 7 archivos, 23 tests (fakeredis + stubs)
```

Scripts sueltos en la raíz (utilidades one-off, **no** parte del servicio): `setup_bateriasya_bot.py`, `setup_bateriasya_function.py`, `update_assistant_instructions.py`, `update_bot_metadata.py`, `update_redis_template.py`, `manage_leads_example.py`, `setup_bateriasya_metadata.sql`.

---

## 3. Arquitectura y flujo de datos

```
   Cliente WhatsApp
        │  (mensaje)
        ▼
   ┌──────────┐   POST /webhook/whatsapp (form-urlencoded)
   │  Twilio  │ ─────────────────────────────────────────────┐
   └──────────┘   ◄── respuesta TwiML (application/xml)      │
        ▲                                                    ▼
        │                                    ┌───────────────────────────────┐
        │                                    │  Flask :8000 (gunicorn)       │
        │  Twilio REST (notificar vendedor)  │                               │
        └────────────────────────────────────┤  1. resolver bot por To:      │
                                             │     Redis → SQL → Horizon API │
                                             │  2. control-status (handoff)  │
        ┌───────────────┐                    │  3. slots del cliente (Redis) │
        │    Redis      │◄───────────────────┤  4. auto-dispatch de lead     │
        │ sesiones,     │                    │  5. OpenAI Assistant run      │
        │ threads,      │                    │  6. tool calls → CRM          │
        │ lead_id,      │                    │  7. sync flow_history         │
        │ idempotencia  │                    └──────┬───────────────┬────────┘
        └───────────────┘                           │               │
                                     HTTPS (Bearer) │               │ SQLAlchemy (read-only)
                                                    ▼               ▼
                                    ┌───────────────────────┐  ┌──────────────────┐
                                    │  Horizon Manager API  │  │ BD del Manager   │
                                    │  api.horizonai.cl     │  │ gestion_*, api_* │
                                    └───────────────────────┘  └──────────────────┘
                                                    ▲
                              POST /outbound/whatsapp/send (HMAC)
                                                    │
                                          Horizon Flow / Agente AI
```

### 3.1 Flujo detallado de un mensaje entrante (`app/routes/whatsapp.py:91`)

1. **Log completo** de `From`, `To`, `Body` y todos los params.
2. **Resolución del bot** (3 niveles):
   - `bot_id` explícito por query `?bot_id=` o campo `BotId` → `BotRepository.get_bot()` (hash Redis `bots:registry`).
   - Si no, por número destino `To` → recorre **todos** los bots de Redis comparando `twilio_phone_number` (O(n), `list_bots()`).
   - Fallback: `HorizonConfigLoader.get_bot_config(phone)` → `GET {HORIZON_BASE_URL}/api/bot/config/?phone=` y **persiste** el resultado en Redis.
   - Si nada resuelve → `400 BadRequest`.
3. `_register_last_inbound()` → marca `wa:last_inbound:{tenant}:{from}` (abre la ventana de 24 h para outbound).
4. Si `Body` vacío → `400`.
5. **Chequeo de handoff**: `human_agent_has_control(bot, from)`. Si `control_mode == "human"`:
   - graba el mensaje entrante en `flow_history` del lead (`record_inbound_during_handoff`),
   - responde **TwiML vacío** → Twilio no envía nada. Fin del turno.
6. `handle_incoming_message()` (ver §3.2). Cualquier excepción → responde `"Lo siento, hubo un error al procesar tu mensaje."`.
7. Responde `MessagingResponse` con el texto → **XML TwiML obligatorio**.

### 3.2 `handle_incoming_message()` (`conversation_service.py:34`)

1. Carga el bot: Redis → **SQL** (`SQLBotRepository.get`) → **Horizon API** (`/api/bot/config/`, usando `TWILIO_WHATSAPP_FROM` como teléfono). Cada nivel cachea en Redis.
2. **Enriquecimiento desde SQL** si al snapshot de Redis le falta `client_id`, `metadata`, `twilio_account_sid`, o el ruteo de notificaciones (`notification_target_whatsapp` / `sucursal_phone_map`).
3. `ClientDataManager` (namespaced por `bot_id`): extrae info del mensaje por **regex/listas hardcodeadas** (marcas, modelos, año, combustible, start-stop, comunas, teléfono chileno) y actualiza los slots en Redis.
4. `_try_auto_dispatch_lead_notification()`: si `metadata.auto_dispatch_enabled` (o el bot es el legacy BateriasYa) y ya están todos los `auto_dispatch_required_fields`, ejecuta la función de extracción de lead **sin pasar por el LLM**, marcando `omitir_workflow_lead_creado=True`.
5. Carga el historial de Redis (`session:{bot_id}:{user_number}`, últimos 20 mensajes) y añade el turno del usuario.
6. Inyecta un mensaje `system` con "ESTADO ACTUAL DEL CLIENTE" (slots conocidos) para que el modelo no vuelva a preguntar.
7. `openai_service.generate_reply()`:
   - Si el bot tiene `assistant_id` → **Assistants API** con thread persistente por usuario.
   - Si no → **Chat Completions** con `tools=assistant_functions`.
8. Si hay tool calls → `_execute_tool_calls()`: primero funciones custom (`CustomFunctionsService`), si no las soporta, `HorizonService.execute_action()` (acciones declarativas del bot).
9. Con Assistants: `submit_tool_outputs_and_wait()` (soporta múltiples rondas de tools). Sin Assistants: `summarize_tool_results()`.
10. Guarda la conversación (TTL `REDIS_SESSION_TTL_SECONDS`, default 86400) y llama `_sync_lead_flow_history()`.

### 3.3 Sincronización de historial al CRM (`_sync_lead_flow_history`, línea 797)

- Requiere `lead_id` cacheado en Redis (`lead_id:{solo_dígitos}`); si no existe, no hace nada.
- Pregunta a Horizon cuántas entradas ya tiene: `GET /api/leads/<id>/flow-history/` → cuenta `results`.
- Envía **sólo los mensajes nuevos**: `PATCH /api/leads/<id>/` con `{"flow_history": [...]}`.
- Diseño explícito **sin estado en Redis**: Horizon es la fuente de verdad, sobrevive reinicios del contenedor.
- Si el PATCH devuelve 404 → borra el `lead_id` cacheado.
- El token usado debe ser **el mismo con que se creó el lead** (de ahí el override CFMOTO, ver §11.1).

---

## 4. Superficie HTTP expuesta (endpoints propios)

| Método | Ruta | Auth | Content-Type resp. | Función |
|---|---|---|---|---|
| POST | `/webhook/whatsapp` | **Ninguna** ⚠️ | `application/xml` (TwiML) | Webhook principal de Twilio |
| GET | `/webhook/whatsapp` | Ninguna | `text/plain` | Health del webhook |
| POST | `/outbound/whatsapp/send` | `X-Api-Key` + HMAC-SHA256 + anti-replay | JSON | Envío saliente (free/template) |
| POST | `/outbound/whatsapp/status` | **Ninguna** ⚠️ | JSON | Callback de estado de Twilio |
| GET | `/bots/` | **Ninguna** ⚠️ | JSON | Listar bots |
| POST | `/bots/` | Ninguna ⚠️ | JSON | Crear bot (opcionalmente crea el Assistant en OpenAI) |
| GET | `/bots/<bot_id>` | Ninguna ⚠️ | JSON | Detalle de bot |
| PUT | `/bots/<bot_id>` | Ninguna ⚠️ | JSON | Actualizar bot (y opcionalmente el Assistant) |
| DELETE | `/bots/<bot_id>` | Ninguna ⚠️ | 204 | Borrar bot de Redis |
| POST | `/bots/<bot_id>/refresh` | Ninguna ⚠️ | JSON | Re-sincronizar bot desde la BD del Manager a Redis |
| GET | `/bots/clients` | Ninguna ⚠️ | JSON | Listar todos los `client_data:*` de Redis |
| GET | `/bots/clients/<phone>` | Ninguna ⚠️ | JSON | Slots guardados de un cliente |
| DELETE | `/bots/clients/<phone>` | Ninguna ⚠️ | JSON | Borrar slots de un cliente |
| GET | `/health` | Ninguna | JSON | `{status, db}` |
| GET | `/health/db` | Ninguna | JSON | 200/503/500 según la BD |
| GET | `/debug/routes` | Ninguna ⚠️ | JSON | Dump del url_map (**definido 2 veces**, gana el primero) |
| GET | `/test/log` | Ninguna | JSON | Prueba de logging |

⚠️ **Toda la superficie salvo `/outbound/whatsapp/send` está sin autenticar.** Hoy la única protección es Nginx (`location /` → 404 deja fuera `/debug/routes`, `/test/log`, `/health/db`, pero **`/bots/*` sí está publicado sin auth**). Además **el webhook de Twilio no valida la firma `X-Twilio-Signature`**: cualquiera que conozca la URL puede inyectar mensajes falsos y provocar creación de leads y notificaciones a vendedores. Esto es un ítem obligatorio del plan de migración (§12).

Notas de ruteo: `/bots/clients` y `/bots/<bot_id>` conviven; Flask prioriza la regla estática, así que un bot con id literal `clients` sería inalcanzable. `DEPLOYMENT.md` documenta `POST /bots/refresh` que **no existe** (la real es `/bots/<bot_id>/refresh`).

---

## 5. Servicios y endpoints externos consumidos

### 5.1 Horizon Manager API (destino de la migración)

Host: `CustomFunctionsService.horizon_api_base = "https://api.horizonai.cl"` **hardcodeado** (`custom_functions_service.py:29`). Auth: `Authorization: Bearer <token per-company>`. Timeout: 15 s (10 s en creación de lead, 8 s en control-status).

| Método | Path | Usado en | Propósito |
|---|---|---|---|
| POST | `/api/leads/` | `_create_horizon_lead` | Crear lead. Payload: `procedencia, nombre, correo, telefono, mensaje` + opcionales `omitir_workflow_lead_creado`, `vendedor_username`, `sucursal`, `custom_fields`. **`flow_history` se omite deliberadamente** (Horizon lo duplicaría) |
| GET | `/api/leads/<id>/` | `_get_horizon_lead` | Leer el lead recién creado para conocer el vendedor asignado |
| PATCH | `/api/leads/<id>/` | `_update_horizon_lead` | Actualizar lead existente / enviar `flow_history` incremental. 404 → invalida cache |
| GET | `/api/leads/<id>/flow-history/` | `_get_horizon_flow_history_count` | Contar entradas ya registradas (deduplicación) |
| GET | `/api/vendedores/` | `_handle_listar_vendedores`, `_get_vendedor_phone` | Listar vendedores activos (acepta lista o `{results:[]}`) |
| GET | `/api/vendedores/<id>/` | `_get_vendedor_phone` | Detalle de vendedor. **Tolera 404** y cae al listado |
| GET | `/api/agendamientos/?vendedor_id=` | `_handle_buscar_disponibilidad`, `_handle_agendar_cita` | Leer agenda para calcular huecos y validar solapamiento |
| POST | `/api/agendamientos/` | `_handle_agendar_cita` | Crear cita. Payload preferido `vendedor_id + fecha_inicio (naive local) + motivo + lead_*`; fallback `usuario_id + fechas UTC + interno:false` |
| GET | `/api/bot/config/?phone=` | `HorizonConfigLoader._fetch_from_horizon` | Config del bot (fuente de verdad; cache Redis 5 min). Host: `HORIZON_BASE_URL` |
| POST | `/api/bot/eventos/` | `HorizonConfigLoader.report_evento` | Reportar eventos. **Definido pero nunca invocado** (código muerto) |
| GET | `/api/bot/control-status/?telefono=` | `human_agent_has_control` | Handoff: `{"control_mode": "human"\|"bot"}`. Host: `HORIZON_CONTROL_BASE_URL` |
| * | acciones declarativas | `HorizonService.execute_action` | Ejecuta `bot.horizon_actions` (`{name, method, path, query, body}` con `.format(**arguments)`) sobre `HORIZON_BASE_URL` |

**Tres hosts distintos conviven** para el mismo Manager: `HORIZON_BASE_URL` (config del bot y horizon_actions), `HORIZON_CONTROL_BASE_URL` (control-status, default `api.horizonai.cl`) y el hardcode `api.horizonai.cl` (leads/vendedores/agenda). Unificar es parte de la migración.

### 5.2 Base de datos del Manager (acceso SQL directo, read-only)

`DatabaseExtension` construye la URL desde `DATABASE_URL` o `DB_HOST/PORT/USER/PASSWORD/NAME`; el driver se infiere: **puerto 3306 → `mysql+pymysql`, resto → `postgresql+psycopg2`** (con `?sslmode=`). `pool_pre_ping=True`.

| Tabla | Columnas leídas | Dónde |
|---|---|---|
| `gestion_whatsappbot` | `id, client_id, external_ref, twilio_phone_number, twilio_messaging_service_sid, twilio_account_sid, assistant_id, assistant_model, assistant_instructions, assistant_functions, openai_api_key, horizon_actions, metadata, status, created_at, updated_at` | `sql_bot_repository.py` (`get`, `list`, `find_by_twilio_number`) |
| `gestion_empresa` | `id, twilio_whatsapp_from, twilio_account_sid, twilio_auth_token` | `_resolve_twilio_from_gestion_empresa` (por `client_id` o por número) |
| `api_apitoken` | `` `key` ``, filtrado `empresa_id` + `activo=1`, orden `ultimo_uso DESC, creado_en DESC` | `_resolve_horizon_token_for_bot` |

⚠️ La query de `api_apitoken` usa **backticks (sintaxis MySQL)**, mientras `BOT_METADATA_CONFIG.md` documenta `::jsonb` (PostgreSQL). Hay que confirmar cuál motor es el real en producción; en Postgres esa query falla y el token cae al placeholder `HORIZON_API_KEY` → 401 (ver §11.1).

Nota: `openai_api_key` por bot **se lee de la BD pero nunca se usa**: el cliente OpenAI es global (`OPENAI_API_KEY`).

### 5.3 OpenAI

- SDK `openai==1.51.0`, cliente único global con `httpx.Client(timeout=60, max_connections=10)`; fallback a `OpenAI(api_key, max_retries=0)` si falla la inicialización.
- **Assistants API (beta v2)**: `beta.assistants.create/update`, `beta.threads.create/retrieve`, `beta.threads.messages.create/list`, `beta.threads.runs.create/retrieve/submit_tool_outputs`.
- **Chat Completions** (`chat.completions.create`) cuando el bot no tiene `assistant_id`.
- **Responses API** (`responses.create`) en `summarize_tool_results`.
- Modelo default `OPENAI_DEFAULT_MODEL=gpt-4.1-mini` (el `.env.example` y docs mencionan también `gpt-4o-mini`).
- Threads persistentes: `thread:{assistant_id}:{user_phone}` en Redis, TTL 7 días, verificados contra la API antes de reusar.
- **Polling síncrono**: `time.sleep(1)` hasta 60 iteraciones esperando el run → **hasta 60 s bloqueando un worker de gunicorn** dentro de un request de Twilio (que tiene timeout propio de 15 s en TwiML). Riesgo real de timeout/duplicados.
- Guard de concurrencia: `oa:thread:{thread_id}:active_run` (TTL 300 s); si hay run activo, espera 5 s y si sigue vivo responde *"Estoy finalizando la acción anterior…"*.
- Inyecta `additional_instructions` con fecha/hora actual de `America/Santiago` en cada run (para que el modelo no invente años pasados).

### 5.4 Twilio

- **Inbound**: recibe `From`, `To`, `Body`, `BotId` (form-urlencoded). Responde TwiML (`MessagingResponse`).
- **Outbound**: `client.messages.create()` con `body` (free) o `content_sid` + `content_variables` (JSON string) para templates; `from_` o `messaging_service_sid`.
- **Credenciales por tenant**: `TwilioMessagingService._resolve_client()` crea un `TwilioClient` per-request si llegan `account_sid` + `auth_token` del bot; si no, usa el cliente global. Falla explícitamente si viene uno sin el otro.
- Resolución de credenciales (`_resolve_bot_twilio_credentials`, cadena de fallbacks): `metadata.twilio_*` → `metadata.twilio_auth_token_ref` en `TWILIO_AUTH_TOKEN_REFS` (JSON en env) → hash Redis `tenant:twilio:{tenant_id}` → tabla `gestion_empresa` → campos del bot.
- **Content Template de notificación al vendedor hardcodeado**: `VENDOR_TEMPLATE_SID = "HX00cc715f046b866ef1306d7aa03d5f77"` con **10 variables** posicionales (`custom_functions_service.py:1292`), a pesar de que existe `metadata.twilio_template_sid` documentado y sin usar en ese punto.
- Callback de estados: `OUTBOUND_STATUS_CALLBACK_URL` → `POST /outbound/whatsapp/status`.

### 5.5 Redis

Único almacén de estado del servicio. `decode_responses=True`. **No hay persistencia crítica**: todo es cache o estado reconstruible, salvo `bots:registry` cuando la BD/API no están disponibles.

| Clave | Tipo | TTL | Contenido |
|---|---|---|---|
| `bots:registry` | hash (`bot_id` → JSON) | ∞ | Registro/cache de definiciones de bots |
| `session:{bot_id}:{user_number}` | string JSON | `REDIS_SESSION_TTL_SECONDS` (86400) | Últimos 20 mensajes de la conversación |
| `client_data:{bot_id}:{phone}` / `client_data:{phone}` | string JSON | 30 días | Slots del cliente (marca, modelo, año, combustible, start_stop, comuna, teléfono, flags de dispatch) |
| `lead_id:{solo_dígitos}` | string | 30 días | `lead_id` de Horizon por teléfono (se guarda bajo varias normalizaciones) |
| `thread:{assistant_id}:{user_phone}` | string | 7 días | `thread_id` de OpenAI |
| `oa:thread:{thread_id}:active_run` | string | 300 s | Lock de run activo |
| `horizon_bot_config:{phone}` | string JSON | 300 s | Cache de `/api/bot/config/` |
| `wa:last_inbound:{tenant_id}:{to_e164}` | string (epoch) | ∞ | Base de la ventana de 24 h |
| `wa:outbound:message:{sid}` | string JSON | 48 h | Correlación sid → tenant/lead/execution |
| `wa:outbound:status:{sid}` | string JSON | 48 h | Último estado de entrega |
| `wa:outbound:idempotency:{tenant}:{key}` | string JSON | 48 h | `request_hash` + respuesta + status |
| `auth:replay:{ts}:{sig}` | string | = skew (300 s) | Anti-replay HMAC |
| `tenant:twilio:{tenant_id}` | hash | ∞ | Credenciales Twilio por tenant (`twilio_account_sid`, `twilio_auth_token`, `twilio_from_whatsapp`, `twilio_messaging_service_sid`) |

---

## 6. Funciones de negocio en detalle

### 6.1 Conversación con IA
Historial en Redis (20 mensajes) + thread persistente de OpenAI por usuario/assistant. Inyección de slots como mensaje `system` e inyección de fecha actual (`America/Santiago`) como `additional_instructions`. Si no hay `OPENAI_API_KEY`, degrada a una respuesta fija ("el asistente aún no está configurado").

### 6.2 Extracción y gestión de leads (`_handle_service_lead_extraction`, línea 1028)
Es el corazón del servicio. Secuencia:

1. **Validación de teléfono**: si el LLM no capturó un teléfono válido (`_looks_like_phone` = ≥8 dígitos; rechaza prosa tipo *"el mismo que le escribo"*), usa el `user_number` de WhatsApp. Normalización chilena en `_normalize_phone_number` (`9XXXXXXXX` → `+569…`, `56…` → `+56…`).
2. **Construcción del mensaje** para el vendedor (encabezado `service_notification_title - service_display_name`, servicio, vehículo omitiendo `N/A`, cliente, estado, "Contexto adicional").
3. **Contexto adicional automático**: `_extract_non_horizon_fields` aplana todo el payload (`a.b[0].c`) y adjunta todo lo que no sea un campo mapeado conocido — así datos específicos de cada vertical llegan al CRM sin cambiar código.
4. **Upsert del lead**: busca `lead_id` en Redis por teléfono normalizado y, como fallback, por `user_number`; si existe → `PATCH`, si no → `POST`. Guarda el `lead_id` bajo ambas claves. `flow_history` se excluye de POST y de PATCH (lo maneja §3.3).
5. **Resolución del destinatario de la notificación** (orden de prioridad): `metadata.notification_target_whatsapp` → teléfono del vendedor asignado al lead (`vendedor_asignado_id`, `vendedor_id`, `vendedor`, `assigned_to`, `usuario_asignado_id`, `vendedor_username`, … buscando el teléfono en ~9 alias de campo, con anidado `user`/`usuario`) → `sucursal_phone_map` por coincidencia de substring con la comuna → primer teléfono del mapa.
6. **Notificación**: Twilio Content Template (SID hardcodeado, 10 variables) con las credenciales del tenant.
7. Respuesta estructurada al LLM: `success`, `extracted_data`, `message`, `lead_id`, `lead_status` (`created|updated|error|skipped`), `target_phone`, `vendedor_id`, `message_sid`.

**Adaptador CFMOTO** (`_handle_cfmoto_lead_extraction`, línea 948): traduce un payload de motos (`moto_interes`, `preferencias_compra`, `contexto_adicional`) al formato genérico — `marca="CFMOTO"`, `comuna = sucursal_preferencia`, `procedencia="whatsapp_cfmoto"`, `custom_fields.modelo` — y mapea la sucursal a id de Horizon con un diccionario **hardcodeado**: `{"santiago": 2, "concepcion": 1}` (`custom_functions_service.py:1020`). Si la sucursal no matchea, el lead queda sin sucursal y Horizon lo asigna al pool default.

**Auto-dispatch** (`conversation_service.py:668`): crea el lead sin intervención del LLM cuando los slots requeridos están completos. Configurable por metadata (`auto_dispatch_enabled`, `_function_name`, `_required_fields`, `_sent_flag`); por defecto activo sólo para el bot legacy BateriasYa (detectado por nombre o por `assistant_id == "asst_svobnYajdAylQaM5Iqz8Dof3"`, **hardcodeado**). Marca `omitir_workflow_lead_creado=True` para no disparar workflows del CRM con un lead placeholder.

### 6.3 Agenda de vendedores
- `listar_vendedores` → `GET /api/vendedores/`, normaliza `id/nombre/username`.
- `buscar_disponibilidad(desde, hasta, slot_minutos)` → por cada vendedor lee sus agendamientos, **fusiona intervalos ocupados**, calcula gaps y propone hasta 5 inicios de slot por vendedor. Tolera múltiples nombres de campo (`inicio|start|fecha_inicio`).
- `agendar_cita` → valida `vendedor_id`, nombre y teléfono del cliente; **rechaza fechas de años anteriores y fechas pasadas** (margen 1 h, zona `America/Santiago`); re-verifica solapamiento justo antes de crear; POST con payload preferido y fallback.

### 6.4 Human handoff (`human_agent_has_control`, línea 476)
`GET {HORIZON_CONTROL_BASE_URL}/api/bot/control-status/?telefono=<numero>` con Bearer per-company, timeout 8 s. Política **fail-open con 1 reintento**: ante 4xx/5xx o error de red reintenta una vez y, si falla, deja que el bot responda (un caído del CRM no silencia a todos). Loguea teléfono, status, `control_mode` y los últimos 4 caracteres del token. Cuando devuelve `human`, el webhook igualmente registra el mensaje entrante en el CRM para que el agente humano no quede ciego.

### 6.5 Outbound iniciado por Horizon Flow
- **Auth en 4 capas**: `X-Api-Key` (comparación en tiempo constante) + HMAC-SHA256 de `"{timestamp}.{raw_body}"` con `OUTBOUND_HMAC_SECRET` + ventana de skew (`OUTBOUND_MAX_TIMESTAMP_SKEW_SECONDS`, 300 s) + anti-replay en Redis (`SET NX EX`).
- **Ventana de 24 h**: `mode=free` sólo si hay inbound del usuario en las últimas 24 h; si no → `blocked_window_closed` / `requires_template` (HTTP 200).
- **Idempotencia**: misma key + mismo payload → devuelve la respuesta almacenada; misma key + payload distinto → `409 idempotency_conflict`.
- Campos requeridos: `tenant_id, lead_id, execution_id, to_e164, mode, idempotency_key` (+ `text` o `template_sid`).
- Códigos de error normalizados: `requires_template, invalid_api_key, missing_signature, invalid_signature, invalid_timestamp, timestamp_out_of_skew, replay_detected, missing_credentials, invalid_credentials_*, twilio_error_*, idempotency_conflict, invalid_payload, internal_error`.
- `POST /outbound/whatsapp/status` correlaciona el `MessageSid` con `execution_id`/`tenant_id` y persiste el estado 48 h. Contrato completo en `GUIA_OUTBOUND_WHATSAPP_AI_AGENT.md`.

### 6.6 Extracción por regex (`client_data_service.py:123`)
Heurística **independiente del LLM** y **hardcodeada al dominio automotriz chileno**: 21 marcas, 7 modelos, año 1990-2039, combustible, start-stop, 7 comunas, teléfono chileno, y un parser posicional para mensajes de ≥5 líneas. Al migrar hay que decidir si se mantiene (es útil como red de seguridad para BateriasYa) o si se reemplaza por extracción del modelo.

---

## 7. Configuración (variables de entorno completas)

| Variable | Default | Requerida | Uso |
|---|---|---|---|
| `FLASK_ENV` | `development` | no | Selecciona `DevelopmentConfig`/`TestingConfig`/`ProductionConfig` |
| `SECRET_KEY` | `change-me` | prod | Flask secret |
| `PORT` | 8000 | no | Sólo informativo (gunicorn fija el bind) |
| `HOST_WEB_PORT` | 8001 | no | Puerto del host en compose |
| `HOST_REDIS_PORT` | 6379 (`.env.example`: 6380) | no | Puerto del host para Redis |
| `REDIS_URL` | `redis://redis:6379/0` | **sí** | Redis (obligatorio si no hay fakeredis) |
| `REDIS_SESSION_TTL_SECONDS` | 86400 | no | TTL del historial |
| `OPENAI_API_KEY` | — | **sí** | Sin ella el bot degrada a respuesta fija |
| `OPENAI_DEFAULT_MODEL` | `gpt-4.1-mini` | no | Modelo fallback |
| `OPENAI_DEFAULT_INSTRUCTIONS` | prompt en español | no | Instrucciones fallback |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | — | **sí** (global) | Cliente Twilio por defecto |
| `TWILIO_WHATSAPP_FROM` | — | **sí** | Remitente fallback; **también** se usa como teléfono en el fallback tier-3 de config del bot |
| `TWILIO_AUTH_TOKEN_REFS` | `{}` | no | JSON `{ref: token}` para credenciales por tenant |
| `HORIZON_BASE_URL` | `https://api.horizon.local` | **sí** | `/api/bot/config/` + `horizon_actions` |
| `HORIZON_API_KEY` | — | **sí** | Token genérico / último fallback |
| `HORIZON_CONTROL_BASE_URL` | `https://api.horizonai.cl` | no | Host de control-status |
| `CFMOTO_HORIZON_API_TOKEN` | — | sólo CFMOTO | Workaround per-company (ver §11.1) |
| `DATABASE_URL` | — | opcional | URL SQLAlchemy completa |
| `DB_HOST`/`DB_PORT`/`DB_USER`/`DB_PASSWORD`/`DB_NAME`/`DB_SSL_MODE`/`DB_DRIVER` | port 5432, ssl `prefer` | opcional | Alternativa a `DATABASE_URL` |
| `LOG_LEVEL` | `INFO` | no | **Leído en config pero nunca aplicado** (`logging_config` fija INFO) |
| `OUTBOUND_API_KEY` | — | para outbound | API key compartida |
| `OUTBOUND_HMAC_SECRET` | — | para outbound | Secreto HMAC |
| `OUTBOUND_MAX_TIMESTAMP_SKEW_SECONDS` | 300 | no | Ventana de firma y anti-replay |
| `OUTBOUND_STATUS_CALLBACK_URL` | — | no | Callback de estados de Twilio |

**El `.env` actual del repo no define** `HORIZON_CONTROL_BASE_URL`, las variables de BD ni las `OUTBOUND_*` → en ese entorno el acceso SQL está deshabilitado (`"DATABASE_URL not configured; DB features disabled"`) y `/outbound/whatsapp/send` responde `401 service_auth_not_configured`.

---

## 8. Contratos de function-calling (schemas que espera el servicio)

Nombres registrados en `CustomFunctionsService._get_handlers()`:

| Nombre de función | Handler | Payload esperado |
|---|---|---|
| `extract_hori_bateriasya_data` | `_handle_service_lead_extraction` | `{servicio:{comuna}, vehiculo:{marca,modelo,anio,combustible,start_stop}, cliente:{nombre,apellido,rut,telefono,correo,direccion,referencia}, estado_flujo}` |
| `extract_hori_service_data` | idem (alias genérico) | idem |
| `extract_hori_cfmoto_data` | `_handle_cfmoto_lead_extraction` | `{moto_interes:{familia,modelo}, preferencias_compra:{sucursal_preferencia,metodo_pago}, cliente:{…}, estado_flujo, contexto_adicional:{…}}` |
| `listar_vendedores` | `_handle_listar_vendedores` | `{horizon_token?}` |
| `buscar_disponibilidad` | `_handle_buscar_disponibilidad` | `{desde, hasta, slot_minutos?, preferencia_usuario?, horizon_token?}` (ISO 8601) |
| `agendar_cita` | `_handle_agendar_cita` | `{vendedor_id, inicio|fecha_inicio, fin|fecha_fin?, cliente_nombre, cliente_telefono, cliente_email?, motivo?, lead_producto_servicio?, usuario_id?, slot_minutos?}` |

Cualquier otro nombre de tool se resuelve como **acción declarativa** del bot (`bot.horizon_actions`): `{name, method, path, query, body}` con interpolación `.format(**arguments)` — ojo, es interpolación de strings sin sanitizar sobre la URL y el body.

`bot_context` que recibe cada handler: `bot_id, twilio_phone_number, user_number, tenant_id, twilio_account_sid, twilio_auth_token, twilio_messaging_service_sid, twilio_from_whatsapp, allow_sucursal_fallback, notification_target_whatsapp, service_notification_title, service_display_name, lead_procedencia, lead_default_email, horizon_api_token, cfmoto_horizon_api_token, conversation_history` (+ `omitir_workflow_lead_creado`, `lead_sucursal_id` según el camino).

---

## 9. Contrato de configuración por cliente (`metadata` del bot)

Campos consumidos por el código (documentados en `BOT_METADATA_CONFIG.md`):

| Campo | Tipo | Efecto |
|---|---|---|
| `horizon_api_token` | string | Token del CRM para ese cliente (máxima prioridad) |
| `cfmoto_horizon_api_token` | string | Override CFMOTO (además marca al bot como CFMOTO) |
| `tenant_id` | string | Namespace para ventana 24 h y credenciales Twilio |
| `client_id` | string | `empresa_id` para resolver token en `api_apitoken` |
| `twilio_account_sid` / `twilio_auth_token` / `twilio_auth_token_ref` / `twilio_from_whatsapp` / `twilio_messaging_service_sid` | string | Credenciales Twilio por bot |
| `twilio_template_sid` | string | Template de notificación (**hoy ignorado** en la notificación al vendedor) |
| `sucursal_phone_map` | objeto | comuna/keyword → teléfono de sucursal (match por substring) |
| `notification_target_whatsapp` | string | Destino fijo de notificaciones (gana sobre el vendedor) |
| `allow_sucursal_fallback` | bool | Habilita fallback a sucursal (se activa implícitamente si hay `sucursal_phone_map`) |
| `service_notification_title` / `service_display_name` | string | Encabezado del mensaje al vendedor |
| `lead_procedencia` | string | `procedencia` del lead en Horizon |
| `lead_default_email` | string | Correo por defecto |
| `auto_dispatch_enabled` | bool | Activa auto-dispatch |
| `auto_dispatch_function_name` / `lead_extraction_function_name` | string | Función a invocar en auto-dispatch |
| `auto_dispatch_required_fields` | array | Slots obligatorios |
| `auto_dispatch_sent_flag` | string | Flag anti-duplicado (default `notification_sent`) |

Al migrar, esta metadata JSON debería promoverse a **campos/modelos explícitos del Manager** (o al menos a un schema validado), porque hoy es un contrato implícito sin validación: una key mal escrita degrada silenciosamente el comportamiento.

---

## 10. Testing

`pytest` con `fakeredis` y stubs (sin credenciales reales). **23 tests, todos pasan** (verificado: `23 passed in 0.70s`).

| Archivo | Cubre |
|---|---|
| `tests/test_app.py` | CRUD de `/bots`, webhook TwiML, ejecución de horizon_actions |
| `tests/test_outbound.py` | HMAC, skew, replay, idempotencia, ventana 24 h, status webhook |
| `tests/test_custom_functions_service.py` | Extracción de lead, resolución de teléfono, exclusión de `flow_history` |
| `tests/test_control_status.py` | Handoff: `human`, `bot`, error → fail-open, token faltante |
| `tests/test_phone_validation.py` | `_looks_like_phone` |
| `tests/test_is_cfmoto_bot.py` | Detección de bot CFMOTO |

**Sin cobertura**: `openai_service.py` (toda la lógica de threads/runs/polling), agenda (`buscar_disponibilidad`/`agendar_cita`), `sql_bot_repository`, `horizon_config_loader`, la cadena de resolución de credenciales Twilio.

---

## 11. Deuda técnica, bugs conocidos y hardcodes (crítico para planificar)

### 11.1 Resolución de tokens per-company — la fuente principal de incidentes
Existen **cuatro** mecanismos superpuestos para obtener el token de Horizon:

1. `metadata.horizon_api_token`
2. `metadata.cfmoto_horizon_api_token`
3. SQL `api_apitoken` por `empresa_id` (sintaxis MySQL)
4. env `CFMOTO_HORIZON_API_TOKEN` (workaround, con detección de placeholders)
5. Último fallback: `HORIZON_API_KEY` (genérico → **401 en endpoints per-company**)

`_resolve_control_status_token` (línea 441) existe **sólo** porque el resolver genérico caía al placeholder para CFMOTO y devolvía 401, lo que activaba el fail-open y el bot seguía respondiendo pese al handoff. Tres de los cinco últimos commits son intentos sucesivos de arreglar esto. **Al migrar dentro del Manager esto desaparece por completo**: no hace falta token, el acceso es interno y la empresa se conoce por FK. Es el mayor beneficio del cambio.

### 11.2 Hardcodes que deben parametrizarse
| Valor | Ubicación |
|---|---|
| `https://api.horizonai.cl` (host del CRM) | `custom_functions_service.py:29` |
| `HX00cc715f046b866ef1306d7aa03d5f77` (template de vendedor, 10 vars) | `custom_functions_service.py:1292` |
| `{"santiago": 2, "concepcion": 1}` (ids de sucursal CFMOTO) | `custom_functions_service.py:1020` |
| `asst_svobnYajdAylQaM5Iqz8Dof3` (bot legacy BateriasYa) | `conversation_service.py:340` |
| Detección de cliente por substring del nombre (`"cfmoto" in bot_name`) | `conversation_service.py:343` |
| Listas de marcas/modelos/comunas chilenas | `client_data_service.py:132-176` |
| Zona `America/Santiago` y offset `-03:00` | `custom_functions_service.py`, `openai_service.py` |

### 11.3 Seguridad
- **Sin validación de `X-Twilio-Signature`** en `/webhook/whatsapp` → inyección de mensajes falsos ⇒ leads y notificaciones fraudulentas.
- **`/bots/*` sin autenticación y publicado en Nginx** → cualquiera puede listar, crear, modificar o borrar bots, y leer `client_data` (datos personales de clientes finales: nombre, teléfono, dirección).
- `/outbound/whatsapp/status` sin auth (aceptable si Twilio es la única fuente, pero permite falsear estados de entrega).
- `/debug/routes`, `/test/log`, `/health/db` expuestos en la app (bloqueados sólo por el `location /` de Nginx).
- Tokens del CRM y auth tokens de Twilio almacenados en claro en `metadata` (JSON en BD) y en hashes de Redis.
- `HorizonService.execute_action` interpola argumentos del LLM en la URL y el body con `.format()` sin sanitizar.

### 11.4 Correctitud y rendimiento
- **Polling bloqueante de OpenAI** hasta 60 s dentro del request de Twilio (que corta antes) → riesgo de timeout, reintentos de Twilio y respuestas duplicadas. En el Manager debería ser una tarea asíncrona (Celery/RQ) + respuesta TwiML vacía + envío posterior vía API de Twilio.
- `_find_bot_by_number` hace `hvals` de **todos** los bots y compara en Python (O(n) por mensaje). Debería ser un índice/consulta por número.
- `/debug/routes` **definido dos veces** (`app/__init__.py:62` y `:83`); gana el primero.
- **Código muerto**: bloque duplicado tras el `return` en `config.SQLALCHEMY_URL` (líneas 56-63); `HorizonConfigLoader.report_evento` nunca se llama; `_handle_bateriasya_extraction` sin referencias; `openai_api_key` por bot se lee y se ignora; `LOG_LEVEL` nunca se aplica.
- `bots.py:list_all_clients` hace `redis_client.keys("client_data:*")` (**bloquea Redis**) y luego `key.decode()`/`data.decode()` sobre valores que ya vienen decodificados (`decode_responses=True`) → ese endpoint **falla con `AttributeError`** en runtime real.
- `print()` en vez de `logger` en varios caminos de error de `openai_service.py`.
- Ambigüedad de motor de BD: backticks MySQL en `api_apitoken` vs `::jsonb` PostgreSQL en la documentación.
- `DEPLOYMENT.md` documenta `POST /bots/refresh` (inexistente).
- Sin `docker-compose` healthcheck, sin límites de recursos, sin `--workers/--timeout` explícitos en gunicorn.

---

## 12. Plan de migración al Manager principal

### 12.1 Mapeo componente → destino en el Manager

| Hoy (Flask) | Al migrar (Manager) |
|---|---|
| `BotRepository` (Redis `bots:registry`) | **Eliminar.** El modelo `WhatsAppBot` (`gestion_whatsappbot`) ya es la fuente de verdad; opcionalmente cache local |
| `SQLBotRepository` (SQL crudo) | **Eliminar.** Reemplazar por el ORM del Manager |
| `HorizonConfigLoader` (`/api/bot/config/`) | **Eliminar.** Lectura directa del modelo |
| `_resolve_horizon_token_for_bot`, `_resolve_control_status_token`, `_resolve_cfmoto_token_from_env`, `CFMOTO_HORIZON_API_TOKEN` | **Eliminar por completo.** Sin HTTP no hay tokens |
| `human_agent_has_control` (HTTP) | Consulta interna al estado de control del lead/chat |
| `_create_horizon_lead` / `_update_horizon_lead` / `_get_horizon_lead` | Servicio interno de leads (respetando las señales de workflow y `omitir_workflow_lead_creado`) |
| `_get_horizon_flow_history_count` + PATCH incremental | Escritura directa a `FlowInteractionLog`; la deduplicación por conteo puede simplificarse a append idempotente |
| `/api/vendedores/`, `/api/agendamientos/` | Consultas ORM; la lógica de merge de intervalos y propuesta de slots se **conserva tal cual** (es pura y ya está probada en producción) |
| `HorizonService.execute_action` (horizon_actions) | Evaluar si sigue teniendo sentido; en el Manager la mayoría de acciones son internas. Si se conserva, **sanitizar** la interpolación |
| `TwilioMessagingService` + `OutboundWhatsAppService` | Se migran casi sin cambios (dependen sólo de Twilio y Redis) |
| `OpenAIAssistantService` | Se migra, pero el polling debe pasar a **tarea asíncrona** |
| `ClientDataManager` | Se migra tal cual (Redis) o se promueve a modelo si se quiere persistencia real |
| Blueprints `/webhook/whatsapp`, `/outbound/*` | Vistas del Manager (mantener rutas y contratos **byte a byte** para no reconfigurar Twilio ni Horizon Flow) |
| Endpoints `/bots/*` | Reemplazar por el admin/API del Manager, **con autenticación** |
| `Config`/`extensions` | Settings del Manager; Redis como cache/broker compartido |

### 12.2 Invariantes que NO se pueden romper

1. **`POST /webhook/whatsapp` debe seguir respondiendo TwiML XML válido** (`application/xml`); si no, Twilio descarta el mensaje. Respuesta vacía = "no contestar" (usado por el handoff).
2. **La ruta y el contrato de `/outbound/whatsapp/send` y `/outbound/whatsapp/status`** están consumidos por Horizon Flow y configurados en Twilio: mantener paths, headers (`X-Api-Key`, `X-Timestamp`, `X-Signature`), semántica de idempotencia y todos los `reason_code`.
3. **Nombres de las funciones del assistant** (`extract_hori_*`, `listar_vendedores`, `buscar_disponibilidad`, `agendar_cita`): están grabados en los Assistants ya creados en OpenAI. Cambiarlos exige actualizar cada assistant.
4. **Claves de Redis**: si se migra en caliente, conservar los patrones (`thread:*`, `lead_id:*`, `wa:last_inbound:*`) o los usuarios pierden contexto, se duplican leads y se cierra la ventana de 24 h de golpe.
5. **`flow_history` no debe enviarse en la creación del lead** (Horizon lo duplicaría) — es un acuerdo explícito entre ambos lados.
6. **Fail-open del handoff**: si el chequeo de control falla, el bot responde. Mantener esa política (o decidirla explícitamente) para no silenciar todos los bots ante un error.

### 12.3 Fases sugeridas

**Fase 0 — Preparación (sin cambios funcionales)**
- Confirmar el motor real de BD y arreglar la query de `api_apitoken`.
- Parametrizar los hardcodes de §11.2 (host, template SID, ids de sucursal) — reduce el diff de la migración.
- Añadir autenticación a `/bots/*` y validación de `X-Twilio-Signature`.
- Inventariar bots activos en producción (`GET /bots/`) y sus metadata como baseline de migración.

**Fase 1 — Reemplazar HTTP por acceso interno**
- Mover el código a la app del Manager conservando rutas y servicios.
- Sustituir `_create/_update/_get_horizon_lead`, vendedores, agendamientos, flow-history, control-status y config del bot por llamadas internas.
- Borrar toda la maquinaria de tokens. **Aquí se elimina la clase entera de bugs de §11.1.**

**Fase 2 — Corregir la arquitectura del turno de conversación**
- Convertir el ciclo de OpenAI en tarea asíncrona: responder TwiML vacío de inmediato y enviar la respuesta por la API de Twilio al terminar (elimina el bloqueo de hasta 60 s y los timeouts de Twilio).
- Reemplazar el escaneo O(n) de bots por índice/consulta por número.

**Fase 3 — Consolidar el modelo de configuración**
- Promover `metadata` a campos/schema validado del Manager.
- Unificar la resolución de credenciales Twilio (hoy 5 fuentes) en una sola.

**Fase 4 — Corte**
- Desplegar en paralelo; apuntar **un** número de Twilio al Manager y validar los 6 flujos (§1) end-to-end.
- Migrar números uno por uno (el webhook es per-número en Twilio: rollback = revertir la URL).
- Mantener Redis compartido durante la transición para no perder threads ni ventanas de 24 h.
- Apagar el servicio Flask cuando el último número esté migrado.

### 12.4 Checklist de validación por bot migrado
- [ ] Mensaje entrante → respuesta del assistant correcto (no cruzado entre clientes)
- [ ] Historial persiste entre mensajes (thread reusado)
- [ ] Lead creado en el CRM con `procedencia`, sucursal y `custom_fields` correctos
- [ ] Segundo mensaje **actualiza** el lead (no crea uno nuevo)
- [ ] `flow_history` completo y **sin duplicados** en el CRM
- [ ] Notificación WhatsApp al vendedor/sucursal correcto
- [ ] Handoff: con control humano el bot calla y el inbound queda registrado
- [ ] `agendar_cita` rechaza fechas pasadas y detecta solapamiento
- [ ] Outbound `free` dentro de 24 h, `template` fuera de 24 h, idempotencia y `409` en conflicto
- [ ] Webhook de estados correlaciona `execution_id`/`tenant_id`

---

## 13. Anexo — documentación existente en el repo

| Archivo | Contenido |
|---|---|
| `AGENTS.md` / `CLAUDE.md` | Guía canónica para agentes: comandos, arquitectura, gotchas |
| `ARQUITECTURA_MULTICLIENTE.md` | Modelo multi-cliente, escalabilidad, costos |
| `BOT_METADATA_CONFIG.md` | Contrato completo de `metadata` + SQL de ejemplo + creación de templates en Twilio |
| `GUIA_OUTBOUND_WHATSAPP_AI_AGENT.md` | Contrato outbound completo (HMAC, ventana 24 h, códigos de error, timeouts) |
| `DEPLOYMENT.md` | URLs, variables, configuración de Twilio, comandos de despliegue |
| `CLIENTE_NUEVO.md`, `GUIA_RAPIDA.md`, `GUIA_PRUEBA_CLIENTES.md` | Onboarding y pruebas |
| `FUNCION_BATERIASYA.md`, `CHANGELOG_METADATA.md`, `RESUMEN_FINAL.md` | Historia del cliente legacy y de la metadata |
| `GIT_SETUP.md` | Flujo de git y despliegue |
