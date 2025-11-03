# Configuración de Metadata por Bot

Cada bot en la tabla `gestion_whatsappbot` puede tener configuración personalizada en el campo `metadata` (JSON).

## Campos de Metadata Disponibles

### 1. `horizon_api_token` (string)
Token de autenticación para la API de Horizon Manager específico de este cliente.

**Ejemplo:**
```json
"horizon_api_token": "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO"
```

### 2. `twilio_template_sid` (string)
Content SID del template aprobado en Twilio para enviar notificaciones a sucursales.

**Ejemplo:**
```json
"twilio_template_sid": "HXa1b2c3d4e5f6g7h8i9j0k1l2m3n4o5"
```

### 3. `twilio_messaging_service_sid` (string)
Messaging Service SID de Twilio para este bot (opcional, también puede estar en el campo principal).

**Ejemplo:**
```json
"twilio_messaging_service_sid": "MG76bf87ef6cc85272131b6e8511ff1a8f"
```

### 4. `sucursal_phone_map` (object)
Mapeo de comunas/palabras clave a números de WhatsApp de sucursales para notificaciones.

**Ejemplo:**
```json
"sucursal_phone_map": {
  "santiago": "+56978493528",
  "rm": "+56978493528",
  "región metropolitana": "+56978493528",
  "providencia": "+56978493528",
  "las condes": "+56978493528",
  "la florida": "+56978493528",
  "macul": "+56978493528",
  "curico": "+56945678901",
  "curicó": "+56945678901",
  "talca": "+56912345678"
}
```

## Ejemplo Completo de Metadata

```json
{
  "horizon_api_token": "MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO",
  "twilio_template_sid": "HXa1b2c3d4e5f6g7h8i9j0k1l2m3n4o5",
  "twilio_messaging_service_sid": "MG76bf87ef6cc85272131b6e8511ff1a8f",
  "sucursal_phone_map": {
    "santiago": "+56978493528",
    "rm": "+56978493528",
    "providencia": "+56978493528",
    "las condes": "+56978493528",
    "curico": "+56945678901",
    "talca": "+56912345678"
  }
}
```

## SQL para Actualizar Metadata de un Bot

### Actualizar metadata completo:
```sql
UPDATE gestion_whatsappbot
SET metadata = '{
  "horizon_api_token": "TU_TOKEN_AQUI",
  "twilio_template_sid": "HXxxxxxxxxxxxx",
  "sucursal_phone_map": {
    "santiago": "+56978493528",
    "curico": "+56945678901"
  }
}'::jsonb
WHERE id = 'cc6b403d499043da9f68e9604db5ab65';
```

### Agregar/actualizar solo un campo del metadata (sin borrar los demás):
```sql
-- Agregar horizon_api_token sin borrar otros campos
UPDATE gestion_whatsappbot
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"horizon_api_token": "TU_TOKEN_AQUI"}'::jsonb
WHERE id = 'cc6b403d499043da9f68e9604db5ab65';

-- Agregar twilio_template_sid
UPDATE gestion_whatsappbot
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"twilio_template_sid": "HXxxxxxxxxxxxx"}'::jsonb
WHERE id = 'cc6b403d499043da9f68e9604db5ab65';

-- Agregar mapeo de sucursales
UPDATE gestion_whatsappbot
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{
  "sucursal_phone_map": {
    "santiago": "+56978493528",
    "curico": "+56945678901"
  }
}'::jsonb
WHERE id = 'cc6b403d499043da9f68e9604db5ab65';
```

### Ver metadata actual de un bot:
```sql
SELECT id, external_ref, metadata
FROM gestion_whatsappbot
WHERE id = 'cc6b403d499043da9f68e9604db5ab65';
```

### Ver solo el mapeo de sucursales:
```sql
SELECT id, external_ref, metadata->'sucursal_phone_map' as sucursal_phones
FROM gestion_whatsappbot
WHERE id = 'cc6b403d499043da9f68e9604db5ab65';
```

## Flujo de Trabajo

### 1. **Para un nuevo cliente (BateriasYa):**

```sql
-- 1. Obtener el token de Horizon Manager del cliente
-- 2. Crear y aprobar el template en Twilio
-- 3. Actualizar el bot con la configuración:

UPDATE gestion_whatsappbot
SET metadata = '{
  "horizon_api_token": "TOKEN_DEL_CLIENTE",
  "twilio_template_sid": "HXXXXXXXXXXXXXXXXXXXXXXXXX",
  "sucursal_phone_map": {
    "santiago": "+56978493528",
    "la florida": "+56978493528",
    "curico": "+56945678901"
  }
}'::jsonb
WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';
```

### 2. **Verificar configuración:**

```sql
SELECT 
  id,
  external_ref,
  assistant_id,
  metadata->>'horizon_api_token' as horizon_token,
  metadata->>'twilio_template_sid' as template_sid,
  metadata->'sucursal_phone_map' as sucursal_phones
FROM gestion_whatsappbot
WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';
```

## Fallbacks (valores por defecto)

Si el campo `metadata` no tiene estos valores, el sistema usa:

1. **horizon_api_token**: Variable de entorno `HORIZON_API_KEY` o token hardcodeado (no recomendado para producción)
2. **twilio_template_sid**: `None` (intenta envío freeform, requiere ventana de 24h)
3. **twilio_messaging_service_sid**: Valor del campo `twilio_messaging_service_sid` de la tabla
4. **sucursal_phone_map**: Mapeo por defecto a `+56978493528`

## Crear Template en Twilio

### Pasos:
1. Ve a: https://console.twilio.com/us1/develop/sms/content-editor
2. Crea nuevo Content Template:
   - **Tipo:** WhatsApp
   - **Nombre:** `bateriasya_nuevo_servicio` (o similar)
   - **Idioma:** Spanish (es)
   - **Categoría:** UTILITY

3. **Contenido del template:**
```
Nuevo servicio BateriasYa

Comuna: {{1}}
Vehiculo: {{2}}
Cliente: {{3}}
Telefono: {{4}}
```

4. Envía para aprobación (puede tardar horas)
5. Una vez aprobado, copia el Content SID (HX...)
6. Actualiza el metadata del bot con ese SID

## Ejemplo Real para BateriasYa

```sql
-- Bot de BateriasYa (asst_svobnYajdAylQaM5Iqz8Dof3)
UPDATE gestion_whatsappbot
SET metadata = jsonb_set(
  COALESCE(metadata, '{}'::jsonb),
  '{horizon_api_token}',
  '"MAcRfN4JdCvtxNsRiytKWJhE2LlzeyS795Xo53wGRZ4XtplrJGQKhkpi7rGDG2mO"'
)
WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';

-- Agregar template cuando esté aprobado
UPDATE gestion_whatsappbot
SET metadata = jsonb_set(
  metadata,
  '{twilio_template_sid}',
  '"HXa1b2c3d4e5f6g7h8i9j0k1l2m3n4o5"'  -- Reemplazar con el SID real
)
WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';

-- Agregar mapeo de sucursales
UPDATE gestion_whatsappbot
SET metadata = jsonb_set(
  metadata,
  '{sucursal_phone_map}',
  '{
    "santiago": "+56978493528",
    "rm": "+56978493528",
    "providencia": "+56978493528",
    "macul": "+56978493528",
    "la florida": "+56978493528",
    "las condes": "+56978493528"
  }'::jsonb
)
WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';
```

## Notas Importantes

1. **Seguridad:** Los tokens en metadata son visibles en la base de datos. Asegúrate de que solo personal autorizado tenga acceso.
2. **Templates:** Cada template debe ser aprobado por WhatsApp antes de usarse.
3. **Ventana de 24h:** Sin template, solo puedes enviar mensajes dentro de las 24 horas desde que el usuario escribió.
4. **Testing:** Puedes hacer que el número de la sucursal envíe un mensaje al bot primero para abrir la ventana de 24h y probar sin template.
