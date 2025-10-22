"""Blueprint registration helpers."""
from __future__ import annotations

from flask import Flask

from . import bots, whatsapp


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(bots.blueprint, url_prefix="/bots")
    app.register_blueprint(whatsapp.blueprint, url_prefix="")
