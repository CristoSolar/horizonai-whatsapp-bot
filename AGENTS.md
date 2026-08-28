# AGENTS.md — Horizon WhatsApp Bot

Flask service that routes WhatsApp messages (via Twilio) through OpenAI Assistants and the Horizon CRM API. Redis stores bot metadata and conversation sessions. SQLAlchemy connects to the Horizon Manager DB for bot config sync.

## Commands

### Docker (primary dev workflow)
```bash
docker-compose up --build          # Start app (port 8001) + Redis
docker-compose down
```
**Gotcha:** `docker-compose.yml` requires an external Docker network named `horizonaimanager_horizonai-internal`. Create it if missing:
```bash
docker network create horizonaimanager_horizonai-internal
```

### Local (no Docker)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # Fill in credentials
flask --app wsgi.py run --host 0.0.0.0 --port 8000
```

### Tests
```bash
pytest                             # No real Redis or API credentials needed
```
Tests use `fakeredis` and stubs for OpenAI/Twilio/Horizon.

## Architecture

```
wsgi.py                  # WSGI entrypoint → create_app()
app/__init__.py          # App factory; registers blueprints and extensions
app/config.py            # Config classes loaded via FLASK_ENV
app/extensions.py        # Initializes Redis, OpenAI, Twilio, Horizon, SQLAlchemy clients
app/repositories/
  bot_repository.py      # Redis CRUD for bot metadata (key: bots:registry hash)
  sql_bot_repository.py  # Read-only sync from Horizon Manager DB via SQLAlchemy
app/routes/
  bots.py                # /bots/* REST endpoints (JSON)
  whatsapp.py            # POST /webhook/whatsapp — returns TwiML (XML), NOT JSON
  outbound.py            # Outbound WhatsApp message endpoints
app/services/
  conversation_service.py       # Thread management with OpenAI
  openai_service.py             # OpenAI Assistants wrapper
  twilio_service.py             # Twilio messaging
  horizon_service.py            # Horizon CRM API calls
  client_data_service.py        # Loads client/bot config from Redis or DB
  custom_functions_service.py   # OpenAI function-calling handlers
  outbound_whatsapp_service.py  # Proactive outbound messages
```

## Key gotchas

- **Webhook returns TwiML (XML)** — `POST /webhook/whatsapp` must respond with valid TwiML or Twilio drops the message.
- **Port mapping:** Flask binds on `:8000` inside the container; host port defaults to `8001` (`HOST_WEB_PORT`). Don't confuse the two.
- **Redis port offset:** Host Redis port defaults to `6380` (`HOST_REDIS_PORT`) to avoid conflicts with local Redis on 6379.
- **Horizon DB access:** If the Horizon Manager DB is only reachable from its container network, use an SSH tunnel and set `DATABASE_URL=postgresql+psycopg2://...@host.docker.internal:<port>/...`. The compose file already adds `host.docker.internal:host-gateway`.
- **Bot config source:** Bots are primarily stored in Redis. `POST /bots/<id>/refresh` forces a re-sync from the Horizon DB into Redis.
- **Two duplicate `/debug/routes` handlers** exist in `app/__init__.py` (lines 62 and 83) — Flask will silently use the first.

## Environment variables

See `.env.example`. Minimum required:
- `OPENAI_API_KEY`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `HORIZON_BASE_URL`, `HORIZON_API_KEY`
- `REDIS_URL` (defaults to `redis://redis:6379/0` inside Docker)

Optional DB sync:
- `DATABASE_URL` (full SQLAlchemy URL) **or** `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`

## Multi-client management scripts

- `./crear-cliente.sh` — interactive wizard to onboard a new WhatsApp client
- `./monitor-clientes.sh` — monitor logs, stats, and health across all clients
- `./deploy.sh` — deploy to production server (edit with server credentials first)
