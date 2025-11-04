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
        self.horizon_api_token = horizon_api_token or "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO"
        self.horizon_api_base = "https://api.horizonai.cl"
        self.twilio_template_sid = twilio_template_sid
        self.twilio_messaging_service_sid = twilio_messaging_service_sid
        self.sucursal_phone_map = sucursal_phone_map or {
            "santiago": "+56978493528",
            "rm": "+56978493528",
            "región metropolitana": "+56978493528",
            "curico": "+56978493528",
            "curicó": "+56978493528",
            "macul": "+56978493528",
            "la florida": "+56978493528",
        }
        # Defaults for agenda logic
        self.slot_minutes_default = 60
        self.max_slots_per_vendedor = 5
        self.request_timeout = 15
        
    def execute_custom_function(
        self,
        *,
        function_name: str,
        arguments: Dict[str, Any],
        bot_context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Route custom function calls to their handlers."""
        
        handlers = {
            "extract_hori_bateriasya_data": self._handle_bateriasya_extraction,
            # Agenda/CRM orchestration functions
            "listar_vendedores": self._handle_listar_vendedores,
            "buscar_disponibilidad": self._handle_buscar_disponibilidad,
            "agendar_cita": self._handle_agendar_cita,
        }
        
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
    def _format_iso(dt_obj) -> str:
        # Always return ISO 8601
        return dt_obj.isoformat()

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
            # Aceptar tanto 'inicio'/'fin' como 'fecha_inicio'/'fecha_fin'
            inicio_arg = arguments.get("inicio") or arguments.get("fecha_inicio")
            fin_arg = arguments.get("fin") or arguments.get("fecha_fin")
            vendedor_id = arguments.get("vendedor_id")
            if not vendedor_id:
                return {"success": False, "error": "Falta 'vendedor_id'"}
            if not inicio_arg:
                return {"success": False, "error": "Falta 'inicio' o 'fecha_inicio'"}
            # Nombre y teléfono son requeridos por el flujo
            if not arguments.get("cliente_nombre") or not arguments.get("cliente_telefono"):
                return {"success": False, "error": "Faltan datos del cliente (nombre y teléfono)"}

            token = arguments.get("horizon_token") or None
            inicio = self._parse_iso(inicio_arg)
            # Si 'fin' no viene, calcular según duración de slot
            if not fin_arg:
                from datetime import timedelta
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

            # Crear la cita
            # El API reportó que espera 'fecha_inicio', por compatibilidad usamos ese naming
            payload = {
                "vendedor_id": vendedor_id,
                "fecha_inicio": self._format_iso(inicio),
                "fecha_fin": self._format_iso(fin),
                "cliente_nombre": arguments.get("cliente_nombre"),
                "cliente_telefono": arguments.get("cliente_telefono"),
                "cliente_email": arguments.get("cliente_email"),
                "canal": arguments.get("canal") or "whatsapp",
                "nota": arguments.get("nota") or "Agendado por asistente HORI",
            }

            try:
                created = self._api_post("/api/agendamientos/", payload, token_override=token)
            except requests.exceptions.HTTPError as http_err:
                # Si la API valida y entrega mensajes, retornarlos
                msg = getattr(http_err, "response", None)
                detail = msg.text if msg is not None else str(http_err)
                logger.error(f"Error creando agendamiento: {detail}")
                return {"success": False, "error": "No se pudo crear la cita", "detail": detail}

            event_id = (created or {}).get("id") or (created or {}).get("pk")
            event_link = (created or {}).get("link") or (created or {}).get("url")

            result = {
                "success": True,
                "evento": {
                    "id": event_id,
                    "inicio": payload["fecha_inicio"],
                    "fin": payload["fecha_fin"],
                    "vendedor_id": vendedor_id,
                    "link": event_link,
                },
                "mensaje_confirmacion": (
                    f"Cita agendada para {payload['fecha_inicio']} con vendedor {vendedor_id}."
                    + (f" Enlace: {event_link}" if event_link else "")
                ),
            }
            return result

        except ValueError as ve:
            return {"success": False, "error": str(ve)}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de red al agendar cita: {e}")
            return {"success": False, "error": "Error de conexión con CRM"}
    
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
        """Handle extract_hori_bateriasya_data function call."""
        
        try:
            # Extract data from arguments
            servicio = arguments.get("servicio", {})
            vehiculo = arguments.get("vehiculo", {})
            cliente = arguments.get("cliente", {})
            estado_flujo = arguments.get("estado_flujo", "pre_cotizacion")
            
            # Determine target phone based on comuna (sucursal)
            comuna = servicio.get("comuna", "").lower()
            
            # Use bot-specific phone mapping
            target_phone = None
            for key, phone in self.sucursal_phone_map.items():
                if key in comuna:
                    target_phone = phone
                    break
            
            if not target_phone:
                # Default to first phone in map or fallback
                target_phone = next(iter(self.sucursal_phone_map.values())) if self.sucursal_phone_map else "+56978493528"
            
            # Format message with extracted data
            message_parts = [
                "NUEVO SERVICIO - BateriasYa",
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
            if cliente and cliente.get("nombre") and cliente.get("correo") and cliente.get("telefono"):
                # Format vehicle info for mensaje field
                vehiculo_info = f"Vehículo: {vehiculo.get('marca', 'N/A')} {vehiculo.get('modelo', 'N/A')} {vehiculo.get('anio', 'N/A')} - Combustible: {vehiculo.get('combustible', 'N/A')}, Start-Stop: {vehiculo.get('start_stop', 'N/A')}"
                servicio_info = f"Servicio en: {servicio.get('comuna', 'N/A')}"
                direccion_info = f"Dirección: {cliente.get('direccion', 'N/A')}, Ref: {cliente.get('referencia', 'N/A')}"
                
                mensaje_lead = f"{vehiculo_info}. {servicio_info}. {direccion_info}. Estado: {estado_flujo}"
                
                lead_data = self._create_horizon_lead(
                    nombre=f"{cliente.get('nombre', '')} {cliente.get('apellido', '')}".strip(),
                    correo=cliente.get("correo", ""),
                    telefono=cliente.get("telefono", ""),
                    mensaje=mensaje_lead,
                    procedencia="whatsapp_bateriasya",
                )
                
                if lead_data and lead_data.get("id"):
                    lead_id = lead_data.get("id")
                    # Save lead ID to Redis for future updates
                    self._save_lead_id_to_redis(cliente.get("telefono", ""), lead_id)
                    logger.info(f"Lead created successfully: ID={lead_id}")
                else:
                    lead_creation_error = "No se pudo crear el lead en Horizon"
                    logger.warning(lead_creation_error)
            
            # Send WhatsApp message to sucursal
            whatsapp_sent = False
            message_sid = None
            if self.twilio_service:
                try:
                    from_number = bot_context.get("twilio_phone_number")
                    logger.info(f"Attempting to send WhatsApp to {target_phone} from {from_number}")
                    
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
                                messaging_service_sid=self.twilio_messaging_service_sid,
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
                        )
                        logger.info(f"WhatsApp freeform notification sent to {target_phone}, SID: {message_sid}")
                        whatsapp_sent = True
                        
                except Exception as e:
                    logger.error(f"Error sending WhatsApp notification: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
            
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
                response["message"] = "Datos extraídos, notificación enviada a sucursal"
                response["target_phone"] = target_phone
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
            logger.error(f"Error in _handle_bateriasya_extraction: {e}")
            return {
                "success": False,
                "error": str(e),
            }
