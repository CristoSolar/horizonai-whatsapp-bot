# Changelog - Sistema de Metadata por Bot

## Cambios Realizados (2025-11-03)

### 🎯 Objetivo
Permitir que cada bot tenga su propia configuración de:
- Token de Horizon API
- Template de Twilio para notificaciones
- Mapeo de comunas a números de WhatsApp de sucursales

### ✅ Archivos Modificados

#### 1. `app/services/conversation_service.py`
- ✅ Modificado `_execute_tool_calls()` para leer metadata del bot
- ✅ Extrae configuración bot-específica de `metadata` JSONB
- ✅ Pasa configuración a `CustomFunctionsService`
- ✅ Agregado parámetro `user_number` para contexto

**Campos extraídos del metadata:**
```python
horizon_api_token = bot_metadata.get("horizon_api_token")
twilio_template_sid = bot_metadata.get("twilio_template_sid")
twilio_messaging_service_sid = bot_metadata.get("twilio_messaging_service_sid")
sucursal_phone_map = bot_metadata.get("sucursal_phone_map")
```

#### 2. `app/services/custom_functions_service.py`
- ✅ Actualizado `__init__()` para recibir parámetros bot-específicos:
  - `twilio_template_sid`
  - `twilio_messaging_service_sid`
  - `sucursal_phone_map`
- ✅ Usa `self.sucursal_phone_map` en vez de mapeo hardcodeado
- ✅ Usa `self.twilio_template_sid` para enviar con template
- ✅ Agregado import de `current_app` desde Flask

#### 3. `app/services/twilio_service.py`
- ✅ Agregado método `send_whatsapp_template()` para enviar usando Content Templates
- ✅ Soporte para `content_sid`, `content_variables`, `messaging_service_sid`
- ✅ Manejo de templates aprobados de WhatsApp

#### 4. `app/services/openai_service.py`
- ✅ Modificado `_generate_assistant_reply()` para detectar `requires_action` status
- ✅ Extrae function calls cuando OpenAI assistant los requiere
- ✅ Agregado método `submit_tool_outputs_and_wait()` para enviar resultados
- ✅ Actualizado dataclass `AssistantResponse` con `thread_id`, `run_id`, `tool_call_ids`

### 📄 Archivos Nuevos

#### 1. `BOT_METADATA_CONFIG.md`
Documentación completa de:
- ✅ Campos disponibles en metadata
- ✅ Ejemplos de configuración
- ✅ Queries SQL para actualizar
- ✅ Flujo de trabajo para nuevos clientes
- ✅ Instrucciones para crear templates en Twilio

#### 2. `update_bot_metadata.py`
Script helper para:
- ✅ Actualizar metadata de bots
- ✅ Buscar bots por assistant_id
- ✅ Ver configuración actual
- ✅ Merge de metadata (preserva campos existentes)

#### 3. `CHANGELOG_METADATA.md` (este archivo)
Resumen de todos los cambios realizados

### 🔧 Configuración en Base de Datos

#### Tabla: `gestion_whatsappbot`
El sistema usa la tabla `gestion_whatsappbot` (no `whatsapp_bots`).

#### Estructura del Metadata (JSON)
```json
{
  "horizon_api_token": "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO",
  "twilio_template_sid": "HXxxxxxxxxxxxx",
  "twilio_messaging_service_sid": "MGxxxxxxxxxxxx",
  "sucursal_phone_map": {
    "santiago": "+56978493528",
    "macul": "+56978493528",
    "curico": "+56945678901"
  }
}
```

#### SQL para Aplicar
```sql
-- Bot de BateriasYa
UPDATE gestion_whatsappbot
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{
  "horizon_api_token": "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO",
  "sucursal_phone_map": {
    "santiago": "+56978493528",
    "rm": "+56978493528",
    "macul": "+56978493528",
    "la florida": "+56978493528"
  }
}'::jsonb
WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';
```

### 🚀 Despliegue

#### 1. Actualizar código en servidor:
```bash
cd ~/horizonai-whatsapp-bot
git pull origin main
```

#### 2. Actualizar metadata del bot en BD:
```bash
# Opción A: Usar script Python
python update_bot_metadata.py

# Opción B: SQL directo
psql $DATABASE_URL -c "UPDATE whatsapp_bots SET metadata = ..."
```

#### 3. Reiniciar servicio:
```bash
sudo systemctl restart horizonai-whatsapp-bot
sudo journalctl -u horizonai-whatsapp-bot -f
```

### ⚠️ Pendientes

#### 1. ⏳ Crear y Aprobar Template en Twilio
- [ ] Ir a: https://console.twilio.com/us1/develop/sms/content-editor
- [ ] Crear template "bateriasya_nuevo_servicio"
- [ ] Esperar aprobación de WhatsApp
- [ ] Copiar Content SID (HX...)
- [ ] Actualizar metadata del bot con el SID

#### 2. ⏳ Token de Horizon Válido
El token actual está dando 401. Necesitas:
- [ ] Obtener token válido desde Horizon Manager
- [ ] Actualizar metadata del bot con el token correcto

#### 3. ✅ Testing Completo
Una vez configurado:
- [ ] Probar creación de lead en Horizon
- [ ] Verificar notificación con template
- [ ] Confirmar mapeo de sucursales

### 📋 Ventajas del Sistema Actual

1. **✅ Multi-tenant:** Cada bot puede tener su propia configuración
2. **✅ Flexible:** Fácil agregar nuevos campos de configuración
3. **✅ Escalable:** No requiere cambios de código para nuevos clientes
4. **✅ Centralizado:** Todo en la base de datos
5. **✅ Fallbacks:** Valores por defecto si metadata no está configurado

### 🔄 Flujo Actual

```
Usuario → WhatsApp → Twilio → Bot
                                 ↓
                         OpenAI Assistant
                                 ↓
                         Function Call: extract_hori_bateriasya_data
                                 ↓
                         CustomFunctionsService
                                 ├→ Lee metadata del bot
                                 ├→ Crea lead en Horizon (con token del bot)
                                 ├→ Guarda lead_id en Redis
                                 └→ Envía notificación WhatsApp
                                     ├→ Intenta con template (si está configurado)
                                     └→ Fallback a freeform (requiere ventana 24h)
```

### 📞 Soporte

Para dudas o problemas:
1. Revisar logs: `sudo journalctl -u horizonai-whatsapp-bot -f`
2. Ver metadata actual: `SELECT metadata FROM gestion_whatsappbot WHERE assistant_id = '...'`
3. Verificar mensajes en Twilio: https://console.twilio.com/us1/monitor/logs/whatsapp

---

**Estado:** ✅ Implementado, ⏳ Pendiente configurar template y token válido
**Fecha:** 2025-11-03
