# Configuración de la Función extract_hori_bateriasya_data

## 📋 Resumen

Se ha implementado una función personalizada que permite al bot de BateriasYa extraer datos del servicio, vehículo y cliente, y automáticamente:

1. **Enviar notificación por WhatsApp** a la sucursal correspondiente
2. **Crear un lead en Horizon Manager** con toda la información del cliente
3. **Guardar el ID del lead en Redis** para futuras actualizaciones

## 🎯 Funcionalidad

Cuando el asistente de OpenAI (ID: `asst_svobnYajdAylQaM5Iqz8Dof3`) ejecuta la función `extract_hori_bateriasya_data`, el sistema:

1. **Extrae** los datos del mensaje del cliente:
   - Servicio: comuna de atención
   - Vehículo: marca, modelo, año, combustible, sistema start-stop
   - Cliente: nombre, apellido, RUT, dirección, teléfono, correo

2. **Determina** la sucursal según la comuna del servicio

3. **Crea un lead en Horizon Manager**:
   - Nombre completo del cliente
   - Correo y teléfono
   - Mensaje con datos del vehículo, servicio y dirección
   - Procedencia: "whatsapp_bateriasya"
   - Guarda el ID del lead en Redis (clave: `lead_id:{telefono}`)

4. **Formatea** un mensaje con toda la información

5. **Envía** el mensaje por WhatsApp a la sucursal correspondiente

## 📱 Números de Sucursales

| Sucursal | Número WhatsApp |
|----------|-----------------|
| Santiago / RM | +56978493528 |
| Curicó | +56978493528 |

## 🔗 Integración con Horizon Manager

### API de Leads
- **Endpoint**: `https://api.horizonai.cl/api/leads/`
- **Token**: `MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO`
- **Procedencia**: `whatsapp_bateriasya`

### Almacenamiento de Lead ID
- Se guarda en Redis con clave: `lead_id:{telefono_cliente}`
- Expiración: 30 días
- Permite futuras actualizaciones del lead

## 🔧 Archivos Modificados/Creados

### 1. `app/services/custom_functions_service.py` (NUEVO)
Servicio que maneja las funciones personalizadas del bot.

**Ubicación del handler**: `_handle_bateriasya_extraction()`

**Funciones principales**:
- `_handle_bateriasya_extraction()`: Procesa datos extraídos
- `_create_horizon_lead()`: Crea lead en Horizon Manager API
- `_save_lead_id_to_redis()`: Guarda ID del lead en Redis
- `_get_lead_id_from_redis()`: Recupera ID del lead desde Redis
- Extrae y valida los datos recibidos
- Mapea comuna → sucursal
- Crea lead en Horizon Manager con datos del cliente y vehículo
- Formatea el mensaje de notificación
- Envía mensaje vía Twilio

### 2. `app/services/conversation_service.py` (MODIFICADO)
Integración de funciones custom en el flujo de conversación.

**Cambios**:
- Import de `CustomFunctionsService`
- Modificación de `_execute_tool_calls()` para:
  - Detectar y ejecutar funciones custom antes de intentar acciones de Horizon
  - Pasar `redis_client` y `horizon_api_token` al servicio custom
  - Incluir contexto del bot para acceso al número de Twilio

### 3. `setup_bateriasya_function.py` (NUEVO)
Script de referencia con la definición completa de la función y ejemplos de configuración.

## 📝 Definición de la Función

```json
{
  "name": "extract_hori_bateriasya_data",
  "description": "Extrae datos del servicio, vehículo y cliente, y envía notificación a sucursal",
  "parameters": {
    "type": "object",
    "properties": {
      "servicio": {
        "type": "object",
        "properties": {
          "comuna": {"type": "string"}
        },
        "required": ["comuna"]
      },
      "vehiculo": {
        "type": "object",
        "properties": {
          "marca": {"type": "string"},
          "modelo": {"type": "string"},
          "anio": {"type": "integer"},
          "combustible": {"type": "string", "enum": ["bencinero", "diésel"]},
          "start_stop": {"type": "string", "enum": ["si", "no", "desconocido"]}
        },
        "required": ["marca", "modelo", "anio", "combustible", "start_stop"]
      },
      "cliente": {
        "type": "object",
        "properties": {
          "nombre": {"type": "string"},
          "apellido": {"type": "string"},
          "rut": {"type": "string"},
          "direccion": {"type": "string"},
          "referencia": {"type": "string"},
          "telefono": {"type": "string"},
          "correo": {"type": "string", "format": "email"}
        },
        "required": ["nombre", "apellido", "rut", "direccion", "referencia", "telefono", "correo"]
      },
      "estado_flujo": {
        "type": "string",
        "enum": ["pre_cotizacion", "cotizacion_enviada", "agendando", "agendado"]
      }
    },
    "required": ["servicio", "vehiculo", "cliente", "estado_flujo"]
  }
}
```

## 🚀 Cómo Verificar que Está Funcionando

### 1. Verificar que el asistente tiene la función configurada

```bash
curl https://api.openai.com/v1/assistants/asst_svobnYajdAylQaM5Iqz8Dof3 \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -H "OpenAI-Beta: assistants=v2"
```

Verificar que en `tools` aparece la función `extract_hori_bateriasya_data`.

### 2. Probar el flujo completo

Enviar un mensaje al bot con todos los datos:

```
Hola, necesito una batería para mi Toyota Corolla 2018 bencinero sin start-stop.
Soy en La Florida, Santiago.

Mis datos:
Juan Pérez
RUT: 12.345.678-9
Teléfono: +56912345678
Email: juan@email.com
Dirección: Av. Principal 123
Referencia: Edificio azul, depto 401
```

### 3. Verificar logs

```bash
sudo journalctl -u horizonai-whatsapp-bot -f | grep "extract_hori_bateriasya_data"
```

Deberías ver:
- `Executing custom function: extract_hori_bateriasya_data`
- `Lead created in Horizon: ID=123`
- `Lead ID 123 saved for phone +56912345678`
- `WhatsApp notification sent to +56978493528, SID: SM...`

### 4. Verificar que llegó el mensaje a la sucursal

El número +56978493528 debería recibir un mensaje formateado como:

```
🚗 *NUEVO SERVICIO - BateriasYa*

📍 *Servicio:*
   Comuna: La Florida

🚙 *Vehículo:*
   Marca: Toyota
   Modelo: Corolla
   Año: 2018
   Combustible: bencinero
   Start-Stop: no

👤 *Cliente:*
   Nombre: Juan Pérez
   RUT: 12.345.678-9
   Teléfono: +56912345678
   Email: juan@email.com
   Dirección: Av. Principal 123
   Referencia: Edificio azul, depto 401

📊 *Estado:* agendando
```

### 5. Verificar que el lead se creó en Horizon

```bash
# Verificar en Redis que se guardó el ID del lead
redis-cli
> GET lead_id:56912345678
"123"

# O verificar directamente en Horizon Manager
curl https://api.horizonai.cl/api/leads/123/ \
  -H "Authorization: Bearer MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO"
```

## 🔄 Cómo Agregar Nuevas Sucursales

Editar el diccionario en `app/services/custom_functions_service.py` (línea ~36):

```python
sucursal_phones = {
    "santiago": "+56978493528",
    "rm": "+56978493528",
    "región metropolitana": "+56978493528",
    "curico": "+56978493528",
    "curicó": "+56978493528",
    "valparaiso": "+56900000000",  # Nueva sucursal
}
```

## 🐛 Troubleshooting

### El asistente no llama a la función

- Verificar que la función está registrada en OpenAI para ese asistente
- Revisar que el prompt del asistente instruya cuándo usar la función

### El mensaje no se envía

- Verificar que `TWILIO_ACCOUNT_SID` y `TWILIO_AUTH_TOKEN` están configurados en `.env`
- Verificar que el número `TWILIO_WHATSAPP_FROM` del bot está aprobado para enviar mensajes
- Revisar logs: `sudo journalctl -u horizonai-whatsapp-bot -f`

### El lead no se crea en Horizon

- Verificar que `HORIZON_API_KEY` está configurado en `.env` o usar el token hardcoded
- Verificar conectividad con `https://api.horizonai.cl`
- Revisar logs para ver el error específico de la API
- Verificar que los datos del cliente están completos (nombre, correo, teléfono)

### No se guarda el lead ID en Redis

- Verificar que Redis está funcionando: `redis-cli ping`
- Verificar que `REDIS_URL` está configurado correctamente
- Revisar logs para errores de Redis

### Error "redis_client not found"

Ya fue corregido en `app/services/openai_service.py` - usar `redis_extension.client`

## 📞 Formato del Mensaje Enviado

### A la Sucursal (WhatsApp)
El mensaje enviado a la sucursal incluye:
- 🚗 Encabezado con nombre del servicio
- 📍 Datos del servicio (comuna)
- 🚙 Datos del vehículo completos
- 👤 Datos del cliente (solo si ya aceptó cotización/agendamiento)
- 📊 Estado del flujo de atención

### Al Horizon Manager (Lead)
El lead creado incluye:
- **Nombre**: Nombre completo del cliente
- **Correo**: Email del cliente
- **Teléfono**: Número de contacto
- **Mensaje**: Información concatenada del vehículo, servicio y dirección
- **Procedencia**: "whatsapp_bateriasya"
- **ID del lead**: Se guarda en Redis para futuras actualizaciones

## ✅ Checklist de Implementación

- [x] Crear `CustomFunctionsService` con handler para `extract_hori_bateriasya_data`
- [x] Integrar en `conversation_service.py` para detectar y ejecutar funciones custom
- [x] Configurar mapeo de comunas a números de sucursales
- [x] Implementar formateo del mensaje de notificación
- [x] Integrar con `TwilioMessagingService` para envío de WhatsApp
- [x] Implementar creación de leads en Horizon Manager API
- [x] Guardar ID del lead en Redis para futuras actualizaciones
- [x] Agregar logging para debugging
- [x] Documentar configuración y uso

## 🎯 Próximos Pasos Sugeridos

1. **Verificar** que el asistente en OpenAI tiene la función configurada
2. **Probar** el flujo completo con un mensaje real
3. **Verificar** que los leads se crean correctamente en Horizon Manager
4. **Revisar** los IDs guardados en Redis: `redis-cli KEYS "lead_id:*"`
5. **Ajustar** el prompt del asistente si es necesario para que use la función en el momento correcto
6. **Agregar** más sucursales al diccionario si es necesario
7. **Implementar** endpoint para actualizar estado del lead cuando cambie el flujo
8. **Considerar** webhook desde Horizon para sincronización bidireccional

## 🔄 Flujo Completo de Datos

```
Usuario (WhatsApp) 
    ↓
Bot BateriasYa (OpenAI Assistant)
    ↓
extract_hori_bateriasya_data()
    ↓
CustomFunctionsService
    ├─→ Crea Lead en Horizon Manager API
    │   └─→ Guarda lead_id en Redis (lead_id:{telefono})
    └─→ Envía notificación WhatsApp a sucursal
```

## 📚 Recursos

- OpenAI Assistants API: https://platform.openai.com/docs/assistants
- Twilio WhatsApp API: https://www.twilio.com/docs/whatsapp
- Script de referencia: `setup_bateriasya_function.py`
