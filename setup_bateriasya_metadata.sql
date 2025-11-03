-- ============================================================
-- Configuración Completa para Bot de BateriasYa
-- ============================================================
-- Ejecutar contra la base de datos de Horizon
-- Tabla: gestion_whatsappbot
-- ============================================================

-- 1. Ver si ya existe el bot
SELECT 
  id,
  external_ref,
  assistant_id,
  twilio_phone_number,
  metadata
FROM gestion_whatsappbot
WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';

-- 2. INSERT del bot completo (si no existe)
-- Reemplaza los valores según tu configuración real
INSERT INTO gestion_whatsappbot (
  client_id,
  external_ref,
  twilio_phone_number,
  twilio_messaging_service_sid,
  twilio_account_sid,
  twilio_auth_token,
  assistant_id,
  assistant_model,
  assistant_instructions,
  assistant_functions,
  openai_api_key,
  horizon_actions,
  metadata,
  status,
  created_at,
  updated_at
) VALUES (
  'bateriasya_client_id',  -- Reemplazar con el client_id real
  'BateriasYa Bot',
  'whatsapp:+1555XXXXXXX',  -- Reemplazar con tu número de Twilio real
  'MGxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',  -- Reemplazar con tu Messaging Service SID real
  'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',  -- Reemplazar con tu Account SID real
  'tu_auth_token_aqui',  -- Reemplazar con tu Auth Token real
  'asst_svobnYajdAylQaM5Iqz8Dof3',
  'gpt-4-turbo-preview',
  'Eres un asistente de BateriasYa especializado en ayudar a clientes con servicios de baterías...',
  '[]',  -- JSON array vacío, o agrega las funciones necesarias
  'sk-tu-openai-key-aqui',  -- Reemplazar con tu OpenAI API Key real
  '[]',  -- JSON array vacío para horizon_actions
  '{
    "horizon_api_token": "HORIZON_TOKEN_AQUI",
    "sucursal_phone_map": {
      "santiago": "+56978493528",
      "rm": "+56978493528",
      "región metropolitana": "+56978493528",
      "providencia": "+56978493528",
      "macul": "+56978493528",
      "la florida": "+56978493528",
      "las condes": "+56978493528"
    }
  }',
  'active',
  NOW(),
  NOW()
);

-- 3. O si ya existe, solo actualizar el metadata
UPDATE gestion_whatsappbot
SET 
  metadata = '{
    "horizon_api_token": "HORIZON_TOKEN_AQUI",
    "sucursal_phone_map": {
      "santiago": "+56978493528",
      "rm": "+56978493528",
      "región metropolitana": "+56978493528",
      "providencia": "+56978493528",
      "macul": "+56978493528",
      "la florida": "+56978493528",
      "las condes": "+56978493528"
    }
  }',
  updated_at = NOW()
WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';

-- 4. Verificar que se aplicó correctamente
SELECT 
  id,
  external_ref,
  assistant_id,
  twilio_phone_number,
  metadata
FROM gestion_whatsappbot
WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';

-- ============================================================
-- OPCIONAL: Agregar Template SID cuando esté aprobado en Twilio
-- ============================================================
-- Una vez que hayas creado y aprobado el template en Twilio:
-- 1. Ve a: https://console.twilio.com/us1/develop/sms/content-editor
-- 2. Copia el Content SID (empieza con HX...)
-- 3. Ejecuta el siguiente UPDATE reemplazando el SID:

-- UPDATE gestion_whatsappbot
-- SET metadata = jsonb_set(
--   metadata,
--   '{twilio_template_sid}',
--   '"HXa1b2c3d4e5f6g7h8i9j0k1l2m3n4o5"'
-- )
-- WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';

-- ============================================================
-- NOTAS IMPORTANTES
-- ============================================================
-- 1. El token de Horizon puede ser incorrecto (da 401)
--    Obtén uno válido desde Horizon Manager y actualízalo
--
-- 2. Sin template aprobado, solo funciona si el número destino
--    (+56978493528) envía un mensaje primero (ventana 24h)
--
-- 3. Para agregar más sucursales, actualiza sucursal_phone_map:
--    UPDATE gestion_whatsappbot
--    SET metadata = jsonb_set(
--      metadata,
--      '{sucursal_phone_map,talca}',
--      '"+56912345678"'
--    )
--    WHERE assistant_id = 'asst_svobnYajdAylQaM5Iqz8Dof3';
-- ============================================================
