# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See **[AGENTS.md](AGENTS.md)** — it is the canonical guide for this repo (commands, architecture, gotchas, env vars). Keep both files in sync by editing AGENTS.md; this file only points to it.

Quick reference:
- **Dev:** `docker-compose up --build` (app on `:8001`, Redis on `:6380`). Requires external network `horizonaimanager_horizonai-internal`.
- **Test:** `pytest` (uses `fakeredis` + stubs, no real credentials). Single test: `pytest tests/test_app.py::test_name`.
- **Run local:** `flask --app wsgi.py run --host 0.0.0.0 --port 8000`.

Architecture in one line: Flask webhook routes Twilio WhatsApp messages → OpenAI Assistants → Horizon CRM API; Redis holds bot metadata + conversation sessions; SQLAlchemy read-syncs bot config from Horizon Manager DB. Full breakdown in AGENTS.md.
