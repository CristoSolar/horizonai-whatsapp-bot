"""Custom function handlers for bot actions that don't call external APIs."""
from __future__ import annotations

import logging
import requests
from typing import Any, Dict, Optional
from flask import current_app

logger = logging.getLogger(__name__)


class CustomFunctionsService:
    """Handles custom function calls that execute internal logic."""
    
    def __init__(
        self,
        twilio_service=None,
        redis_client=None,
        horizon_api_token: Optional[str] = None,
        twilio_template_sid: Optional[str] = None,
        twilio_messaging_service_sid: Optional[str] = None,
        sucursal_phone_map: Optional[Dict[str, str]] = None,
    ):
        self.twilio_service = twilio_service
        self.redis_client = redis_client
        self.horizon_api_token = horizon_api_token or self._resolve_default_horizon_token()
        self.horizon_api_base = "https://api.horizonai.cl"
        self.twilio_template_sid = twilio_template_sid
        self.twilio_messaging_service_sid = twilio_messaging_service_sid
        self.sucursal_phone_map = sucursal_phone_map if sucursal_phone_map is not None else {}
        # Defaults for agenda logic
        self.slot_minutes_default = 60
        self.max_slots_per_vendedor = 5
        self.request_timeout = 15

    @staticmethod
    def _resolve_default_horizon_token() -> Optional[str]:
        try:
            return current_app.config.get("HORIZON_API_KEY")
        except Exception:
            return None

    def _get_handlers(self):
        return {
            # Backward-compatible aliases for lead extraction
            "extract_hori_bateriasya_data": self._handle_service_lead_extraction,
            "extract_hori_service_data": self._handle_service_lead_extraction,
            # Agenda/CRM orchestration functions
            "listar_vendedores": self._handle_listar_vendedores,
            "buscar_disponibilidad": self._handle_buscar_disponibilidad,
            "agendar_cita": self._handle_agendar_cita,
        }

    def supports_function(self, function_name: str) -> bool:
        return function_name in self._get_handlers()
        
    def execute_custom_function(
        self,
        *,
        function_name: str,
        arguments: Dict[str, Any],
        bot_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Route custom function calls to their handlers."""
        handlers = self._get_handlers()
        
        handler = handlers.get(function_name)
        if not handler:
            return {"error": f"No handler found for function '{function_name}'"}
        
        try:
            return handler(arguments, bot_context or {})
        except Exception as e:
            logger.error(f"Error executing custom function {function_name}: {e}")
            return {"error": str(e), "success": False}

    # ---------------------------------------------------------------------
    # HORIZON API HELPERS (Vendedores, Agendas, Agendar)
    # ---------------------------------------------------------------------
    def _api_get(self, path: str, token_override: Optional[str] = None, params: Optional[Dict[str, Any]] = None):
        headers = {
            "Authorization": f"Bearer {token_override or self.horizon_api_token}",
            "Content-Type": "application/json",
        }
        url = f"{self.horizon_api_base}{path}"
        resp = requests.get(url, headers=headers, params=params, timeout=self.request_timeout)
        resp.raise_for_status()
        return resp.json()

    def _api_post(self, path: str, payload: Dict[str, Any], token_override: Optional[str] = None):
        headers = {
            "Authorization": f"Bearer {token_override or self.horizon_api_token}",
            "Content-Type": "application/json",
        }
        url = f"{self.horizon_api_base}{path}"
        resp = requests.post(url, headers=headers, json=payload, timeout=self.request_timeout)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    @staticmethod
    def _parse_iso(dt_str: str):
        from datetime import datetime
        # Accept "Z" by translating to +00:00
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except Exception:
            raise ValueError(f"Fecha/hora inválida: {dt_str}")

    @staticmethod
    def _format_iso(dt_obj, to_utc: bool = False) -> str:
        # Return ISO 8601; optionally convert to UTC with Z suffix
        try:
            from datetime import timezone
            if to_utc:
                if dt_obj.tzinfo is None:
                    # assume local offset -03:00 if naive (Chile typical); adjust if needed
                    from datetime import timedelta
                    dt_obj = dt_obj.replace(tzinfo=timezone(timedelta(hours=-3)))
                dt_obj = dt_obj.astimezone(timezone.utc)
                return dt_obj.isoformat().replace('+00:00', 'Z')
        except Exception:
            pass
        return dt_obj.isoformat()

    @staticmethod
    def _format_local_naive(dt_obj) -> str:
        """Format datetime in America/Santiago as naive ISO yyyy-mm-ddTHH:MM:SS (no tz).
        Falls back to naive without conversion if zoneinfo not available.
        """
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("America/Santiago")
            if dt_obj.tzinfo is None:
                # assume already local; just make naive with seconds
                return dt_obj.replace(microsecond=0).isoformat()
            local_dt = dt_obj.astimezone(tz)
            return local_dt.replace(tzinfo=None, microsecond=0).isoformat()
        except Exception:
            return dt_obj.replace(tzinfo=None, microsecond=0).isoformat()

    # ----------------------------
    # listar_vendedores
    # ----------------------------
    def _handle_listar_vendedores(self, arguments: Dict[str, Any], bot_context: Dict[str, Any]) -> Dict[str, Any]:
        """Devuelve lista de vendedores activos desde Horizon."""
        try:
            token = arguments.get("horizon_token") or None
            data = self._api_get("/api/vendedores/", token_override=token)
            vendedores = []
            for v in data if isinstance(data, list) else data.get("results", []):
                vendedores.append({
                    "id": v.get("id") or v.get("pk") or v.get("vendedor_id"),
                    "nombre": v.get("nombre") or v.get("name") or v.get("full_name"),
                    "username": v.get("username") or v.get("user") or None,
                })
            return {"success": True, "vendedores": vendedores}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listando vendedores: {e}")
            return {"success": False, "error": "No se pudo obtener la lista de vendedores"}

    @staticmethod
    def _normalize_phone_number(phone: Any) -> Optional[str]:
        if not phone:
            return None
        normalized = str(phone).strip()
        if not normalized:
            return None
        if not normalized.startswith("+"):
            if normalized.startswith("56"):
                normalized = f"+{normalized}"
            elif normalized.startswith("9") and len(normalized) == 9:
                normalized = f"+56{normalized}"
        return normalized

    def _extract_phone_from_vendedor(self, vendedor: Dict[str, Any]) -> Optional[str]:
        phone = (
            vendedor.get("telefono")
            or vendedor.get("phone")
            or vendedor.get("celular")
            or vendedor.get("mobile")
            or vendedor.get("telefono_movil")
            or vendedor.get("telefono1")
            or vendedor.get("telefono_1")
            or vendedor.get("phone_number")
            or vendedor.get("whatsapp")
        )
        if phone:
            return self._normalize_phone_number(phone)

        # Algunos esquemas retornan datos anidados en user/usuario
        user_payload = vendedor.get("user") or vendedor.get("usuario")
        if isinstance(user_payload, dict):
            nested_phone = (
                user_payload.get("telefono")
                or user_payload.get("phone")
                or user_payload.get("celular")
                or user_payload.get("mobile")
                or user_payload.get("telefono_movil")
                or user_payload.get("telefono1")
                or user_payload.get("telefono_1")
                or user_payload.get("phone_number")
                or user_payload.get("whatsapp")
            )
            if nested_phone:
                return self._normalize_phone_number(nested_phone)
        return None

    def _resolve_fallback_phone(self, comuna: Any) -> Optional[str]:
        if not self.sucursal_phone_map:
            return None

        comuna_text = str(comuna or "").strip().lower()
        for key, phone in self.sucursal_phone_map.items():
            if key and key.lower() in comuna_text:
                return self._normalize_phone_number(phone)

        first_phone = next(iter(self.sucursal_phone_map.values()), None)
        return self._normalize_phone_number(first_phone)

    def _get_vendedor_phone(self, vendedor_ref: Any, token: Optional[str] = None) -> Optional[str]:
        """Obtiene el teléfono del vendedor asignado aceptando id, username o payload."""
        try:
            # Si ya viene payload del vendedor en el lead
            if isinstance(vendedor_ref, dict):
                phone = self._extract_phone_from_vendedor(vendedor_ref)
                if phone:
                    logger.info("Teléfono encontrado directamente en payload de vendedor")
                    return phone
                vendedor_ref = (
                    vendedor_ref.get("id")
                    or vendedor_ref.get("pk")
                    or vendedor_ref.get("vendedor_id")
                    or vendedor_ref.get("username")
                )

            if not vendedor_ref:
                return None

            # Intento directo por detalle /api/vendedores/{id}/
            if isinstance(vendedor_ref, int) or (isinstance(vendedor_ref, str) and vendedor_ref.isdigit()):
                vendedor = self._api_get(f"/api/vendedores/{vendedor_ref}/", token_override=token)
                phone = self._extract_phone_from_vendedor(vendedor if isinstance(vendedor, dict) else {})
                if phone:
                    logger.info(f"Teléfono encontrado para vendedor {vendedor_ref}: {phone}")
                    return phone

            # Fallback por listado (útil cuando vendedor_ref es username)
            data = self._api_get("/api/vendedores/", token_override=token)
            vendedores = data if isinstance(data, list) else data.get("results", [])
            ref_text = str(vendedor_ref).strip().lower()
            for vendedor in vendedores:
                if not isinstance(vendedor, dict):
                    continue

                user_payload = vendedor.get("user")
                nested_username = user_payload.get("username") if isinstance(user_payload, dict) else None
                nested_user_id = user_payload.get("id") if isinstance(user_payload, dict) else None

                candidates = [
                    vendedor.get("id"),
                    vendedor.get("pk"),
                    vendedor.get("vendedor_id"),
                    vendedor.get("username"),
                    nested_username,
                    nested_user_id,
                ]
                if any(str(candidate).strip().lower() == ref_text for candidate in candidates if candidate is not None):
                    phone = self._extract_phone_from_vendedor(vendedor)
                    if phone:
                        logger.info(f"Teléfono encontrado para vendedor {vendedor_ref}: {phone}")
                        return phone

            logger.warning(f"No se encontró teléfono para vendedor {vendedor_ref}")
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Error obteniendo teléfono del vendedor {vendedor_ref}: {e}")
            return None

    # ----------------------------
    # buscar_disponibilidad
    # ----------------------------
    def _handle_buscar_disponibilidad(self, arguments: Dict[str, Any], bot_context: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula slots libres por vendedor entre 'desde' y 'hasta'."""
        from datetime import timedelta
        try:
            desde_str = arguments.get("desde")
            hasta_str = arguments.get("hasta")
            preferencia_usuario = arguments.get("preferencia_usuario")
            slot_minutes = int(arguments.get("slot_minutos") or self.slot_minutes_default)
            token = arguments.get("horizon_token") or None

            if not desde_str or not hasta_str:
                return {"success": False, "error": "Parámetros 'desde' y 'hasta' son requeridos (ISO 8601)"}

            desde = self._parse_iso(desde_str)
            hasta = self._parse_iso(hasta_str)
            if hasta <= desde:
                return {"success": False, "error": "Rango de fechas inválido"}

            # Obtener vendedores
            vend_resp = self._handle_listar_vendedores({"horizon_token": token}, bot_context)
            if not vend_resp.get("success"):
                return vend_resp
            vendedores = vend_resp.get("vendedores", [])

            disponibilidad = []
            for vendedor in vendedores:
                vid = vendedor.get("id")
                try:
                    # Obtener todos los agendamientos del vendedor
                    agendas = self._api_get("/api/agendamientos/", token_override=token, params={"vendedor_id": vid})
                    eventos = agendas if isinstance(agendas, list) else agendas.get("results", [])

                    # Normalizar y filtrar por rango
                    busy = []
                    for ev in eventos:
                        inicio = ev.get("inicio") or ev.get("start") or ev.get("fecha_inicio")
                        fin = ev.get("fin") or ev.get("end") or ev.get("fecha_fin")
                        if not inicio or not fin:
                            continue
                        try:
                            di = self._parse_iso(inicio)
                            df = self._parse_iso(fin)
                        except Exception:
                            continue
                        if df <= desde or di >= hasta:
                            continue
                        busy.append((max(di, desde), min(df, hasta)))

                    # Unir intervalos ocupados y ordenar
                    busy.sort(key=lambda x: x[0])
                    merged = []
                    for b in busy:
                        if not merged or b[0] > merged[-1][1]:
                            merged.append(list(b))
                        else:
                            merged[-1][1] = max(merged[-1][1], b[1])

                    # Calcular gaps libres entre [desde, hasta]
                    free_slots = []
                    cursor = desde
                    for b in merged:
                        if b[0] - cursor >= timedelta(minutes=slot_minutes):
                            free_slots.append((cursor, b[0]))
                        cursor = max(cursor, b[1])
                    if hasta - cursor >= timedelta(minutes=slot_minutes):
                        free_slots.append((cursor, hasta))

                    # Proponer inicios de slot de tamaño slot_minutes dentro de cada gap
                    proposals = []
                    step = timedelta(minutes=slot_minutes)
                    for (g_start, g_end) in free_slots:
                        s = g_start
                        while s + step <= g_end:
                            proposals.append(self._format_iso(s))
                            s = s + step

                    # Tomar los 3–5 más cercanos
                    propuestas_cortas = proposals[: self.max_slots_per_vendedor]

                    disponibilidad.append({
                        "vendedor_id": vid,
                        "vendedor_nombre": vendedor.get("nombre"),
                        "slot_minutos": slot_minutes,
                        "propuestas": propuestas_cortas,
                        "total_en_rango": len(proposals),
                    })

                except requests.exceptions.RequestException as e:
                    logger.warning(f"Error obteniendo agendas para vendedor {vid}: {e}")
                    disponibilidad.append({
                        "vendedor_id": vid,
                        "vendedor_nombre": vendedor.get("nombre"),
                        "error": "No se pudo consultar la agenda de este vendedor",
                    })

            return {"success": True, "disponibilidad": disponibilidad, "desde": desde_str, "hasta": hasta_str, "preferencia_usuario": preferencia_usuario}

        except ValueError as ve:
            return {"success": False, "error": str(ve)}
        except Exception as e:
            logger.error(f"Error en buscar_disponibilidad: {e}")
            return {"success": False, "error": "No se pudo calcular la disponibilidad"}

    # ----------------------------
    # agendar_cita
    # ----------------------------
    def _handle_agendar_cita(self, arguments: Dict[str, Any], bot_context: Dict[str, Any]) -> Dict[str, Any]:
        """Crea una cita si el slot sigue disponible. Devuelve detalle del evento."""
        try:
            logger.info(f"🗓️ _handle_agendar_cita called with arguments: {arguments}")
            
            # Aceptar tanto 'inicio'/'fin' como 'fecha_inicio'/'fecha_fin'
            inicio_arg = arguments.get("inicio") or arguments.get("fecha_inicio")
            fin_arg = arguments.get("fin") or arguments.get("fecha_fin")
            vendedor_id = arguments.get("vendedor_id")
            
            logger.info(f"   vendedor_id: {vendedor_id}")
            logger.info(f"   inicio_arg: {inicio_arg}")
            logger.info(f"   fin_arg: {fin_arg}")
            
            if not vendedor_id:
                logger.error("❌ Falta 'vendedor_id'")
                return {"success": False, "error": "Falta 'vendedor_id'"}
            if not inicio_arg:
                logger.error("❌ Falta 'inicio' o 'fecha_inicio'")
                return {"success": False, "error": "Falta 'inicio' o 'fecha_inicio'"}
            # Nombre y teléfono son requeridos por el flujo
            if not arguments.get("cliente_nombre") or not arguments.get("cliente_telefono"):
                logger.error(f"❌ Faltan datos del cliente - nombre: {arguments.get('cliente_nombre')}, telefono: {arguments.get('cliente_telefono')}")
                return {"success": False, "error": "Faltan datos del cliente (nombre y teléfono)"}

            token = arguments.get("horizon_token") or None
            inicio = self._parse_iso(inicio_arg)
            logger.info(f"   inicio parsed: {inicio} (year: {inicio.year})")
            
            # VALIDACIÓN: Rechazar fechas en el pasado o años anteriores
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo
            chile_tz = ZoneInfo("America/Santiago")
            now = datetime.now(chile_tz)
            
            logger.info(f"   now (Chile): {now} (year: {now.year})")
            
            # Validar que la fecha de inicio no sea de un año anterior
            if inicio.year < now.year:
                error_msg = f"La fecha proporcionada ({inicio.date()}) es de un año anterior. Por favor, proporciona una fecha del año actual ({now.year})."
                logger.error(f"❌ {error_msg}")
                return {
                    "success": False, 
                    "error": error_msg
                }
            
            # Validar que la fecha no sea en el pasado (con margen de 1 hora)
            if inicio < now - timedelta(hours=1):
                error_msg = f"La fecha proporcionada ({inicio.date()}) ya pasó. Por favor, proporciona una fecha futura."
                logger.error(f"❌ {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
            
            # Si 'fin' no viene, calcular según duración de slot
            if not fin_arg:
                slot_minutes = int(arguments.get("slot_minutos") or self.slot_minutes_default)
                fin = inicio + timedelta(minutes=slot_minutes)
            else:
                fin = self._parse_iso(fin_arg)
            if fin <= inicio:
                return {"success": False, "error": "El fin debe ser mayor al inicio"}

            # Validar disponibilidad del vendedor justo antes de crear
            agendas = self._api_get("/api/agendamientos/", token_override=token, params={"vendedor_id": vendedor_id})
            eventos = agendas if isinstance(agendas, list) else agendas.get("results", [])
            for ev in eventos:
                ev_ini = ev.get("inicio") or ev.get("start") or ev.get("fecha_inicio")
                ev_fin = ev.get("fin") or ev.get("end") or ev.get("fecha_fin")
                if not ev_ini or not ev_fin:
                    continue
                try:
                    di = self._parse_iso(ev_ini)
                    df = self._parse_iso(ev_fin)
                except Exception:
                    continue
                # Overlap check
                if not (df <= inicio or di >= fin):
                    return {"success": False, "error": "El horario seleccionado ya no está disponible"}

            # Crear la cita - intento 1: payload según especificación "crear agendamiento creando lead"
            # Preferido por el CRM: vendedor_id + fecha_inicio (naive local) + motivo + lead_* básicos
            preferred_payload = {
                "vendedor_id": vendedor_id,
                "fecha_inicio": self._format_local_naive(inicio),
                "motivo": arguments.get("motivo") or "Videollamada de asesoría",
                "lead_correo": arguments.get("cliente_email"),
                "lead_nombre": arguments.get("cliente_nombre"),
                "lead_producto_servicio": arguments.get("lead_producto_servicio") or "Asesoría",
            }
            
            logger.info(f"📤 Sending preferred_payload to CRM: {preferred_payload}")

            created = None
            try:
                created = self._api_post("/api/agendamientos/", preferred_payload, token_override=token)
                logger.info(f"✅ Agendamiento created successfully: {created}")
            except requests.exceptions.HTTPError as http_err:
                # Fallback: payload mínimo
                msg = getattr(http_err, "response", None)
                detail = msg.text if msg is not None else str(http_err)
                logger.error(f"Error creando agendamiento (full): {detail}")
                # Fallback 1: intentar con usuario_id + fechas UTC
                usuario_id = arguments.get("usuario_id") or vendedor_id
                minimal_payload = {
                    "usuario_id": usuario_id,
                    "fecha_inicio": self._format_iso(inicio, to_utc=True),
                    "fecha_termino": self._format_iso(fin, to_utc=True),
                    "motivo": arguments.get("motivo") or "Videollamada de asesoría",
                    "interno": False,
                }
                try:
                    created = self._api_post("/api/agendamientos/", minimal_payload, token_override=token)
                    logger.info("Agendamiento creado con payload mínimo tras fallback")
                except requests.exceptions.RequestException as e2:
                    detail2 = getattr(e2, "response", None)
                    detail_text = detail2.text if detail2 is not None else str(e2)
                    return {"success": False, "error": "No se pudo crear la cita", "detail": detail_text}

            event_id = (created or {}).get("id") or (created or {}).get("pk")
            event_link = (created or {}).get("link") or (created or {}).get("url")

            result = {
                "success": True,
                "evento": {
                    "id": event_id,
                    "inicio": (created or {}).get("fecha_inicio") or preferred_payload["fecha_inicio"],
                    "fin": (created or {}).get("fecha_termino") or (created or {}).get("fecha_fin"),
                    "vendedor_id": vendedor_id,
                    "usuario_id": arguments.get("usuario_id") or vendedor_id,
                    "link": event_link,
                },
                "mensaje_confirmacion": (
                    f"Cita agendada para {((created or {}).get('fecha_inicio') or preferred_payload['fecha_inicio'])} con vendedor {vendedor_id}."
                    + (f" Enlace: {event_link}" if event_link else "")
                ),
            }
            logger.info(f"✅ _handle_agendar_cita returning success: {result}")
            return result
        except ValueError as ve:
            logger.error(f"❌ ValueError in _handle_agendar_cita: {ve}")
            return {"success": False, "error": str(ve)}
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ RequestException in _handle_agendar_cita: {e}")
            return {"success": False, "error": "Error de conexión con CRM"}
        except Exception as e:
            logger.error(f"❌ Unexpected error in _handle_agendar_cita: {e}", exc_info=True)
            return {"success": False, "error": f"Error inesperado: {str(e)}"}

    def _create_horizon_lead(
        self,
        *,
        nombre: str,
        correo: str,
        telefono: str,
        mensaje: str,
        procedencia: str = "whatsapp",
        vendedor_username: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create a lead in Horizon Manager API."""
        try:
            url = f"{self.horizon_api_base}/api/leads/"
            headers = {
                "Authorization": f"Bearer {self.horizon_api_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "procedencia": procedencia,
                "nombre": nombre,
                "correo": correo,
                "telefono": telefono,
                "mensaje": mensaje,
            }
            if vendedor_username:
                payload["vendedor_username"] = vendedor_username
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            lead_data = response.json()
            logger.info(f"Lead created in Horizon: ID={lead_data.get('id')}")
            return lead_data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating lead in Horizon: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return None

    def _get_horizon_lead(self, lead_id: Any) -> Optional[Dict[str, Any]]:
        try:
            lead_value = str(lead_id).strip()
            if not lead_value:
                return None
            return self._api_get(f"/api/leads/{lead_value}/")
        except requests.exceptions.RequestException as e:
            logger.warning(f"No se pudo consultar detalle del lead {lead_id}: {e}")
            return None

    @staticmethod
    def _extract_vendedor_ref_from_lead(lead_payload: Optional[Dict[str, Any]]) -> Any:
        if not isinstance(lead_payload, dict):
            return None

        candidates = [
            lead_payload.get("vendedor_id"),
            lead_payload.get("vendedor"),
            lead_payload.get("assigned_to"),
            lead_payload.get("usuario_asignado_id"),
            lead_payload.get("vendedor_username"),
            lead_payload.get("usuario_asignado"),
            lead_payload.get("vendedor_asignado"),
            lead_payload.get("assigned_user"),
            lead_payload.get("usuario"),
        ]
        for candidate in candidates:
            if candidate:
                return candidate
        return None

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "si", "sí", "on"}
    
    def _save_lead_id_to_redis(self, phone_number: str, lead_id: int) -> bool:
        """Save lead ID to Redis for future reference."""
        
        if not self.redis_client:
            logger.warning("Redis client not available, cannot save lead ID")
            return False
        
        try:
            # Clean phone number for key
            clean_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "")
            key = f"lead_id:{clean_phone}"
            
            # Store lead ID with 30 days expiration
            self.redis_client.setex(key, 2592000, str(lead_id))  # 30 days
            logger.info(f"Lead ID {lead_id} saved for phone {phone_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving lead ID to Redis: {e}")
            return False
    
    def _get_lead_id_from_redis(self, phone_number: str) -> Optional[int]:
        """Get lead ID from Redis if exists."""
        
        if not self.redis_client:
            return None
        
        try:
            clean_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "")
            key = f"lead_id:{clean_phone}"
            lead_id = self.redis_client.get(key)
            
            if lead_id:
                if isinstance(lead_id, bytes):
                    lead_id = lead_id.decode('utf-8')
                return int(lead_id)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting lead ID from Redis: {e}")
            return None
    
    def _handle_bateriasya_extraction(
        self,
        arguments: Dict[str, Any],
        bot_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Backward-compatible wrapper for legacy function name."""
        return self._handle_service_lead_extraction(arguments, bot_context)

    def _handle_service_lead_extraction(
        self,
        arguments: Dict[str, Any],
        bot_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle lead extraction + Horizon lead creation + WhatsApp notification."""

        try:
            # Extract data from arguments
            servicio = arguments.get("servicio", {})
            vehiculo = arguments.get("vehiculo", {})
            cliente = arguments.get("cliente", {})
            estado_flujo = arguments.get("estado_flujo", "pre_cotizacion")
            allow_sucursal_fallback = self._as_bool(bot_context.get("allow_sucursal_fallback"))
            
            # Target phone will be determined from lead's assigned vendedor
            target_phone = None
            vendedor_id = None
            service_title = str(bot_context.get("service_notification_title") or "NUEVO SERVICIO").strip()
            service_name = str(bot_context.get("service_display_name") or "").strip()
            lead_procedencia = str(bot_context.get("lead_procedencia") or "whatsapp").strip() or "whatsapp"
            header_line = f"{service_title} - {service_name}" if service_name else service_title
            
            # Format message with extracted data
            message_parts = [
                header_line,
                "",
                "Servicio:",
                f"  Comuna: {servicio.get('comuna', 'N/A')}",
                "",
                "Vehiculo:",
                f"  Marca: {vehiculo.get('marca', 'N/A')}",
                f"  Modelo: {vehiculo.get('modelo', 'N/A')}",
                f"  Año: {vehiculo.get('anio', 'N/A')}",
                f"  Combustible: {vehiculo.get('combustible', 'N/A')}",
                f"  Start-Stop: {vehiculo.get('start_stop', 'N/A')}",
            ]
            
            # Add client data if available
            if cliente and cliente.get("nombre"):
                message_parts.extend([
                    "",
                    "Cliente:",
                    f"  Nombre: {cliente.get('nombre', '')} {cliente.get('apellido', '')}",
                    f"  RUT: {cliente.get('rut', 'N/A')}",
                    f"  Telefono: {cliente.get('telefono', 'N/A')}",
                    f"  Email: {cliente.get('correo', 'N/A')}",
                    f"  Direccion: {cliente.get('direccion', 'N/A')}",
                    f"  Referencia: {cliente.get('referencia', 'N/A')}",
                ])
            
            message_parts.extend([
                "",
                f"Estado: {estado_flujo}",
            ])
            
            message_body = "\n".join(message_parts)
            
            # Create lead in Horizon if cliente data is available
            lead_id = None
            lead_creation_error = None
            lead_data = None
            
            if cliente and cliente.get("nombre") and cliente.get("telefono"):
                # Format vehicle info for mensaje field
                vehiculo_info = f"Vehículo: {vehiculo.get('marca', 'N/A')} {vehiculo.get('modelo', 'N/A')} {vehiculo.get('anio', 'N/A')} - Combustible: {vehiculo.get('combustible', 'N/A')}, Start-Stop: {vehiculo.get('start_stop', 'N/A')}"
                servicio_info = f"Servicio en: {servicio.get('comuna', 'N/A')}"
                direccion_info = f"Dirección: {cliente.get('direccion', 'N/A')}, Ref: {cliente.get('referencia', 'N/A')}"
                
                mensaje_lead = f"{vehiculo_info}. {servicio_info}. {direccion_info}. Estado: {estado_flujo}"
                correo_cliente = (
                    cliente.get("correo")
                    or bot_context.get("lead_default_email")
                    or "sin-correo@pendiente.cl"
                )
                
                lead_data = self._create_horizon_lead(
                    nombre=f"{cliente.get('nombre', '')} {cliente.get('apellido', '')}".strip(),
                    correo=correo_cliente,
                    telefono=cliente.get("telefono", ""),
                    mensaje=mensaje_lead,
                    procedencia=lead_procedencia,
                )
                
                if lead_data and lead_data.get("id"):
                    lead_id = lead_data.get("id")
                    # Save lead ID to Redis for future updates
                    self._save_lead_id_to_redis(cliente.get("telefono", ""), lead_id)
                    logger.info(f"Lead created successfully: ID={lead_id}")

                    lead_detail = self._get_horizon_lead(lead_id)
                    if isinstance(lead_detail, dict):
                        lead_data = lead_detail
                        logger.info(f"Lead detail fetched for ID={lead_id}")
                    
                    # Get vendedor assigned to the lead
                    vendedor_ref = self._extract_vendedor_ref_from_lead(lead_data)
                    if isinstance(vendedor_ref, dict):
                        vendedor_id = (
                            vendedor_ref.get("id")
                            or vendedor_ref.get("pk")
                            or vendedor_ref.get("vendedor_id")
                            or vendedor_ref.get("usuario_id")
                            or vendedor_ref.get("username")
                        )
                    else:
                        vendedor_id = vendedor_ref

                    if vendedor_ref:
                        logger.info(f"Lead asignado a vendedor: {vendedor_ref}")
                        # Get vendedor's phone number
                        target_phone = self._get_vendedor_phone(vendedor_ref, token=self.horizon_api_token)
                        
                        if not target_phone:
                            logger.warning(f"No se pudo obtener teléfono del vendedor {vendedor_ref}")
                            if allow_sucursal_fallback:
                                logger.info("Fallback por sucursal habilitado, intentando ruta sucursal")
                                target_phone = self._resolve_fallback_phone(servicio.get("comuna", ""))
                    else:
                        logger.warning("Lead creado sin vendedor asignado")
                        if allow_sucursal_fallback:
                            logger.info("Fallback por sucursal habilitado, intentando ruta sucursal")
                            target_phone = self._resolve_fallback_phone(servicio.get("comuna", ""))
                else:
                    lead_creation_error = "No se pudo crear el lead en Horizon"
                    logger.warning(lead_creation_error)
                    if allow_sucursal_fallback:
                        target_phone = self._resolve_fallback_phone(servicio.get("comuna", ""))
            else:
                logger.info("Datos de cliente incompletos")
                if allow_sucursal_fallback:
                    logger.info("Fallback por sucursal habilitado, intentando ruta sucursal")
                    target_phone = self._resolve_fallback_phone(servicio.get("comuna", ""))
            
            # Send WhatsApp message to sucursal
            whatsapp_sent = False
            message_sid = None
            if self.twilio_service and target_phone:
                try:
                    from_number = bot_context.get("twilio_from_whatsapp") or bot_context.get("twilio_phone_number")
                    twilio_account_sid = bot_context.get("twilio_account_sid")
                    twilio_auth_token = bot_context.get("twilio_auth_token")
                    twilio_messaging_service_sid = bot_context.get("twilio_messaging_service_sid") or self.twilio_messaging_service_sid

                    logger.info(
                        "Attempting to send WhatsApp to %s from %s (account_sid=%s, has_auth_token=%s, messaging_service_sid=%s)",
                        target_phone,
                        from_number,
                        twilio_account_sid or "ENV_DEFAULT",
                        "yes" if twilio_auth_token else "no",
                        twilio_messaging_service_sid or "NONE",
                    )
                    
                    # Try to use template first (for initiating conversations)
                    # Template variables (adjust based on your approved template)
                    template_vars = {
                        "1": servicio.get('comuna', 'N/A'),  # Comuna
                        "2": f"{vehiculo.get('marca', 'N/A')} {vehiculo.get('modelo', 'N/A')}",  # Vehículo
                        "3": cliente.get('nombre', 'N/A') if cliente else 'N/A',  # Nombre cliente
                        "4": cliente.get('telefono', 'N/A') if cliente else 'N/A',  # Teléfono cliente
                    }
                    
                    # Try template method if bot has template configured
                    if self.twilio_template_sid and hasattr(self.twilio_service, 'send_whatsapp_template'):
                        logger.info(f"Using Content Template: {self.twilio_template_sid}")
                        try:
                            message_sid = self.twilio_service.send_whatsapp_template(
                                to_number=target_phone,
                                content_sid=self.twilio_template_sid,
                                content_variables=template_vars,
                                from_number=from_number,
                                messaging_service_sid=twilio_messaging_service_sid,
                                twilio_account_sid=twilio_account_sid,
                                twilio_auth_token=twilio_auth_token,
                            )
                            logger.info(f"WhatsApp template notification sent to {target_phone}, SID: {message_sid}")
                            whatsapp_sent = True
                        except Exception as template_error:
                            logger.warning(f"Template send failed, trying freeform: {template_error}")
                            # Fall through to try freeform
                    
                    # Fallback to freeform message (only works within 24h window)
                    if not whatsapp_sent:
                        logger.info(f"Sending freeform message (requires 24h window)")
                        logger.info(f"Message body length: {len(message_body)} characters")
                        
                        message_sid = self.twilio_service.send_whatsapp_message(
                            to_number=target_phone,
                            body=message_body,
                            from_number=from_number,
                            messaging_service_sid=twilio_messaging_service_sid,
                            twilio_account_sid=twilio_account_sid,
                            twilio_auth_token=twilio_auth_token,
                        )
                        logger.info(f"WhatsApp freeform notification sent to {target_phone}, SID: {message_sid}")
                        whatsapp_sent = True
                        
                except Exception as e:
                    logger.error(f"Error sending WhatsApp notification: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
            elif self.twilio_service and not target_phone:
                logger.warning("No se envió WhatsApp: no se pudo resolver teléfono destino (vendedor/sucursal)")
            
            # Build response
            response = {
                "success": True,
                "extracted_data": {
                    "servicio": servicio,
                    "vehiculo": vehiculo,
                    "cliente": cliente,
                    "estado_flujo": estado_flujo,
                },
            }
            
            # Add WhatsApp info
            if whatsapp_sent:
                if vendedor_id:
                    response["message"] = f"Datos extraídos, notificación enviada al vendedor (ID: {vendedor_id})"
                else:
                    response["message"] = "Datos extraídos, notificación enviada a sucursal"
                response["target_phone"] = target_phone
                response["vendedor_id"] = vendedor_id
                response["message_sid"] = message_sid
            else:
                response["message"] = "Datos extraídos (notificación WhatsApp no enviada)"
            
            # Add lead info
            if lead_id:
                response["lead_id"] = lead_id
                response["lead_status"] = "created"
                response["message"] += " y lead creado en Horizon"
            elif lead_creation_error:
                response["lead_status"] = "error"
                response["lead_error"] = lead_creation_error
            elif not cliente or not cliente.get("nombre"):
                response["lead_status"] = "skipped"
                response["lead_note"] = "Datos de cliente incompletos para crear lead"
            
            return response
                
        except Exception as e:
            logger.error(f"Error in _handle_service_lead_extraction: {e}")
            return {
                "success": False,
                "error": str(e),
            }
