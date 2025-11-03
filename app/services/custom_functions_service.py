"""Custom function handlers for bot actions that don't call external APIs."""
from __future__ import annotations

import logging
import requests
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CustomFunctionsService:
    """Handles custom function calls that execute internal logic."""
    
    def __init__(self, twilio_service=None, redis_client=None, horizon_api_token: Optional[str] = None):
        self.twilio_service = twilio_service
        self.redis_client = redis_client
        self.horizon_api_token = horizon_api_token or "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO"
        self.horizon_api_base = "https://api.horizonai.cl"
        
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
        }
        
        handler = handlers.get(function_name)
        if not handler:
            return {"error": f"No handler found for function '{function_name}'"}
        
        try:
            return handler(arguments, bot_context or {})
        except Exception as e:
            logger.error(f"Error executing custom function {function_name}: {e}")
            return {"error": str(e), "success": False}
    
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
            
            # Map comuna to WhatsApp numbers
            sucursal_phones = {
                "santiago": "+56978493528",
                "rm": "+56978493528",
                "región metropolitana": "+56978493528",
                "curico": "+56978493528",  # Por ahora usa el mismo, ajustar según necesidad
                "curicó": "+56978493528",
            }
            
            # Find matching sucursal
            target_phone = None
            for key, phone in sucursal_phones.items():
                if key in comuna:
                    target_phone = phone
                    break
            
            if not target_phone:
                # Default to Santiago if no match
                target_phone = "+56978493528"
            
            # Format message with extracted data
            message_parts = [
                "🚗 *NUEVO SERVICIO - BateriasYa*",
                "",
                "📍 *Servicio:*",
                f"   Comuna: {servicio.get('comuna', 'N/A')}",
                "",
                "🚙 *Vehículo:*",
                f"   Marca: {vehiculo.get('marca', 'N/A')}",
                f"   Modelo: {vehiculo.get('modelo', 'N/A')}",
                f"   Año: {vehiculo.get('anio', 'N/A')}",
                f"   Combustible: {vehiculo.get('combustible', 'N/A')}",
                f"   Start-Stop: {vehiculo.get('start_stop', 'N/A')}",
            ]
            
            # Add client data if available
            if cliente and cliente.get("nombre"):
                message_parts.extend([
                    "",
                    "👤 *Cliente:*",
                    f"   Nombre: {cliente.get('nombre', '')} {cliente.get('apellido', '')}",
                    f"   RUT: {cliente.get('rut', 'N/A')}",
                    f"   Teléfono: {cliente.get('telefono', 'N/A')}",
                    f"   Email: {cliente.get('correo', 'N/A')}",
                    f"   Dirección: {cliente.get('direccion', 'N/A')}",
                    f"   Referencia: {cliente.get('referencia', 'N/A')}",
                ])
            
            message_parts.extend([
                "",
                f"📊 *Estado:* {estado_flujo}",
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
            # Send WhatsApp message to sucursal
            whatsapp_sent = False
            message_sid = None
            if self.twilio_service:
                try:
                    from_number = bot_context.get("twilio_phone_number")
                    message_sid = self.twilio_service.send_whatsapp_message(
                        to_number=target_phone,
                        body=message_body,
                        from_number=from_number,
                    )
                    logger.info(f"WhatsApp notification sent to {target_phone}, SID: {message_sid}")
                    whatsapp_sent = True
                except Exception as e:
                    logger.error(f"Error sending WhatsApp notification: {e}")
            
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
