# Guía para Agente AI: uso de endpoints outbound WhatsApp (mensajes libres)

Esta guía describe cómo otro agente AI debe interactuar con el servicio Flask para enviar mensajes WhatsApp salientes usando:

- `POST /outbound/whatsapp/send`
- `POST /outbound/whatsapp/status`

El objetivo es enviar mensajes **libres** cuando la ventana de 24h está abierta y hacer fallback a **template** cuando está cerrada.

---

## 1) Endpoint principal de envío

`POST /outbound/whatsapp/send`

### Headers obligatorios

- `Content-Type: application/json`
- `X-Api-Key: <api_key_compartida>`
- `X-Timestamp: <ISO8601 UTC o epoch>`
- `X-Signature: <hex_hmac_sha256>`

### Firma HMAC (obligatoria)

La firma se calcula sobre:

`<timestamp>.<raw_body_json>`

Donde `raw_body_json` es el JSON exacto enviado (sin cambiar orden/espacios una vez firmado).

Pseudocódigo:

```text
signature = HMAC_SHA256(OUTBOUND_HMAC_SECRET, f"{timestamp}.{raw_body_json}")
```

Se envía en `X-Signature` como hex (opcionalmente con prefijo `sha256=`).

### Anti-replay

- El backend rechaza firmas repetidas dentro de la ventana de skew (`OUTBOUND_MAX_TIMESTAMP_SKEW_SECONDS`, default 300s).
- Si reintentas, genera nuevo timestamp y nueva firma.

---

## 2) Payload de request

Campos esperados:

- `tenant_id` (string, requerido)
- `lead_id` (string, requerido)
- `execution_id` (string, requerido)
- `client_message_id` (string UUID, opcional; recomendado para correlación cruzada Horizon)
- `to_e164` (string, requerido)
- `mode` (`free|template`, requerido)
- `idempotency_key` (string, requerido)
- `twilio_account_sid` (string, opcional si viene por tenant)
- `twilio_auth_token_ref` (string, opcional si hay mapa en config)
- `twilio_from_whatsapp` (string, opcional si viene por tenant)
- `text` (string, requerido si `mode=free`)
- `template_sid` (string, requerido si `mode=template`)
- `template_vars` (objeto, opcional para template)

Notas de credenciales:

- `twilio_auth_token_ref` puede resolverse desde `TWILIO_AUTH_TOKEN_REFS`.
- Alternativamente, credenciales por tenant en Redis (`tenant:twilio:<tenant_id>`).

---

## 3) Regla crítica de ventana 24h para mensajes libres

Si `mode=free`, el backend solo envía cuando existe último inbound del usuario en <=24h (almacenado por `tenant_id + to_e164`).

Si NO cumple:

- no envía a Twilio
- responde:
  - `status = blocked_window_closed`
  - `reason_code = requires_template`

---

## 4) Estrategia recomendada para el Agente AI

Flujo robusto para envío:

1. Intentar `mode=free` con `idempotency_key` único por paso de flujo.
2. Si respuesta `blocked_window_closed` + `requires_template`:
   - reenviar con `mode=template`
   - usar **nuevo** `idempotency_key` (payload distinto).
3. Si `status=error`, revisar `reason_code` y `reason_message`.

Importante de idempotencia:

- Mismo `idempotency_key` + mismo payload => retorna misma respuesta sin duplicar envío.
- Mismo `idempotency_key` + payload distinto => `409 idempotency_conflict`.

---

## 5) Respuesta estándar

El endpoint `/outbound/whatsapp/send` devuelve:

- `status`: `sent_free | sent_template | blocked_window_closed | error`
- `twilio_message_sid`: SID de Twilio si aplica
- `client_message_id`: eco del UUID de Horizon (si fue enviado)
- `provider_status`: estado inicial proveedor
- `reason_code`: código de negocio/error
- `reason_message`: detalle de error/bloqueo
- `window_open`: `true|false`
- `conversation_expires_at`: timestamp de expiración de ventana (si disponible)

Formato acordado para `conversation_expires_at`:

- UTC ISO8601 con sufijo `Z`
- Ejemplo: `2026-03-02T21:30:00Z`

---

## 6) Ejemplos listos

### 6.1 Envío libre (`mode=free`)

```json
{
  "tenant_id": "tenant-a",
  "lead_id": "lead-123",
  "execution_id": "exec-001",
  "to_e164": "+56911111111",
  "twilio_account_sid": "ACxxxxxxxx",
  "twilio_auth_token_ref": "ref_main",
  "twilio_from_whatsapp": "+56922222222",
  "mode": "free",
  "text": "Hola, continuamos con tu solicitud.",
  "idempotency_key": "tenant-a-lead-123-free-001"
}
```

### 6.2 Fallback template (`mode=template`)

```json
{
  "tenant_id": "tenant-a",
  "lead_id": "lead-123",
  "execution_id": "exec-001",
  "to_e164": "+56911111111",
  "twilio_account_sid": "ACxxxxxxxx",
  "twilio_auth_token_ref": "ref_main",
  "twilio_from_whatsapp": "+56922222222",
  "mode": "template",
  "template_sid": "HXxxxxxxxx",
  "template_vars": {
    "1": "Cristobal",
    "2": "Plaza Brokers"
  },
  "idempotency_key": "tenant-a-lead-123-template-001"
}
```

---

## 7) Webhook de estados (delivery updates)

`POST /outbound/whatsapp/status`

Uso:

- Twilio envía updates de estado (`queued`, `sent`, `delivered`, `failed`, etc.).
- El backend correlaciona por `twilio_message_sid` y recupera `execution_id`/`tenant_id` guardados al enviar.

Respuesta típica:

```json
{
  "status": "received",
  "twilio_message_sid": "SMxxxx",
  "provider_status": "delivered",
  "execution_id": "exec-001",
  "tenant_id": "tenant-a",
  "error_code": null,
  "error_message": null
}
```

---

## 8) Códigos de reason_code útiles

- `requires_template`: ventana cerrada para free text.
- `invalid_api_key`: `X-Api-Key` inválida.
- `missing_signature`: falta `X-Signature`.
- `invalid_signature`: HMAC inválida.
- `invalid_timestamp`: `X-Timestamp` malformado.
- `timestamp_out_of_skew`: timestamp fuera de tolerancia.
- `replay_detected`: firma/timestamp reutilizados (anti-replay).
- `missing_credentials`: faltan credenciales Twilio para tenant/request.
- `invalid_credentials_*`: Twilio rechazó auth (ej. 401).
- `twilio_error_*`: error proveedor no-auth.
- `idempotency_conflict`: misma key con payload distinto.
- `invalid_payload`: body incompleto o inconsistente con `mode`.
- `internal_error`: error no clasificado.

---

## 9) Buenas prácticas para el agente

- Generar `idempotency_key` determinística por paso (`tenant-lead-execution-step-mode`).
- No reutilizar key cuando cambia `mode` o contenido.
- Loggear `execution_id`, `status`, `twilio_message_sid`.
- Nunca loggear ni exponer secretos (`api_key`, `hmac_secret`, auth token).
- Si hay `blocked_window_closed`, no insistir con free text: usar template de inmediato.

---

## 10) Recomendación de timeout y reintentos de cliente

Para el cliente que llama `/outbound/whatsapp/send`:

- `timeout`: **8 segundos**
- reintentos automáticos: **1 reintento** solo para **HTTP 5xx** o timeout de red
- **no** reintentar automáticamente en 4xx (errores de firma, payload, credenciales, replay)

Estrategia sugerida:

1. Primer intento con `idempotency_key` estable.
2. Si timeout/5xx, reintentar 1 vez con **mismo** payload e **igual** `idempotency_key`.
3. Si vuelve a fallar, marcar ejecución como `pending_manual_review`.
