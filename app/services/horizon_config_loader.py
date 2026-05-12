"""Loader that fetches bot configuration from HorizonAI Manager API.

Uses Redis as a short-lived cache (TTL 5 min) so the per-request overhead is
minimal.  Redis is no longer the source of truth; Horizon is.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutos


class HorizonConfigLoader:
    """
    Carga la configuración del bot desde HorizonAI Manager.
    Usa Redis como cache temporal con TTL de 5 minutos.
    """

    def __init__(self, horizon_base_url: str, api_token: str, redis_client=None):
        self.horizon_base_url = horizon_base_url.rstrip("/")
        self.api_token = api_token
        self.redis = redis_client

    def get_bot_config(self, phone_number: str) -> Optional[dict]:
        """
        Obtiene config del bot. Primero busca en cache Redis,
        si no está o expiró, va a Horizon y actualiza el cache.
        """
        cache_key = f"horizon_bot_config:{phone_number}"

        # 1. Intentar cache Redis
        if self.redis:
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    logger.debug(
                        "[HorizonConfigLoader] Cache hit para phone=%s",
                        phone_number,
                    )
                    return json.loads(cached)
            except Exception as e:
                logger.warning(
                    "[HorizonConfigLoader] Error leyendo cache Redis: %s", e
                )

        # 2. Llamar a Horizon
        config = self._fetch_from_horizon(phone_number)
        if not config:
            return None

        # 3. Guardar en cache Redis con TTL
        if self.redis:
            try:
                self.redis.setex(
                    cache_key,
                    CACHE_TTL_SECONDS,
                    json.dumps(config, ensure_ascii=False),
                )
                logger.debug(
                    "[HorizonConfigLoader] Config cacheada para phone=%s TTL=%ds",
                    phone_number,
                    CACHE_TTL_SECONDS,
                )
            except Exception as e:
                logger.warning(
                    "[HorizonConfigLoader] Error guardando cache Redis: %s", e
                )

        return config

    def _fetch_from_horizon(self, phone_number: str) -> Optional[dict]:
        """Llama al endpoint de Horizon para obtener la config."""
        url = f"{self.horizon_base_url}/api/bot/config/"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        params = {"phone": phone_number}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                config = response.json()
                logger.info(
                    "[HorizonConfigLoader] Config obtenida de Horizon para phone=%s",
                    phone_number,
                )
                return config
            elif response.status_code == 404:
                logger.error(
                    "[HorizonConfigLoader] Bot no encontrado en Horizon para phone=%s",
                    phone_number,
                )
            else:
                logger.error(
                    "[HorizonConfigLoader] Error Horizon %s para phone=%s: %s",
                    response.status_code,
                    phone_number,
                    response.text[:200],
                )
        except requests.exceptions.Timeout:
            logger.error(
                "[HorizonConfigLoader] Timeout al conectar con Horizon para phone=%s",
                phone_number,
            )
        except requests.exceptions.ConnectionError:
            logger.error(
                "[HorizonConfigLoader] No se pudo conectar con Horizon en %s",
                self.horizon_base_url,
            )
        except Exception as e:
            logger.error("[HorizonConfigLoader] Error inesperado: %s", e)
        return None

    def invalidate_cache(self, phone_number: str) -> None:
        """Invalida el cache de un bot específico."""
        if self.redis:
            cache_key = f"horizon_bot_config:{phone_number}"
            self.redis.delete(cache_key)
            logger.info(
                "[HorizonConfigLoader] Cache invalidado para phone=%s", phone_number
            )

    def report_evento(
        self,
        tipo: str,
        phone: str,
        lead_id=None,
        datos=None,
    ) -> None:
        """Reporta un evento al endpoint de Horizon."""
        url = f"{self.horizon_base_url}/api/bot/eventos/"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }
        body = {
            "tipo": tipo,
            "phone": phone,
            "lead_id": lead_id,
            "datos": datos or {},
        }
        try:
            response = requests.post(url, headers=headers, json=body, timeout=5)
            if response.status_code == 200:
                logger.debug("[HorizonConfigLoader] Evento reportado: %s", tipo)
            else:
                logger.warning(
                    "[HorizonConfigLoader] Error reportando evento %s: %s",
                    tipo,
                    response.status_code,
                )
        except Exception as e:
            logger.warning(
                "[HorizonConfigLoader] No se pudo reportar evento %s: %s", tipo, e
            )
