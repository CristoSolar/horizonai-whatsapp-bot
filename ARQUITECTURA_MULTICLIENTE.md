# 🏗️ Arquitectura Multi-Cliente - HorizonAI WhatsApp Bot

## 🎯 **Cómo Funciona el Sistema Multi-Cliente**

### 📐 **Arquitectura:**

```
                    ┌─────────────────┐
                    │   SERVIDOR      │
                    │  Ubuntu + Flask │
                    └─────────┬───────┘
                              │
                    ┌─────────▼───────┐
                    │  UN SOLO .env   │
                    │ (credenciales)  │
                    └─────────┬───────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
  ┌─────▼─────┐      ┌────────▼────────┐      ┌─────▼─────┐
  │  Bot A    │      │     Bot B       │      │  Bot C    │
  │ +15551111 │      │   +15552222     │      │ +15553333 │
  │ asst_AAA  │      │   asst_BBB      │      │ asst_CCC  │
  └───────────┘      └─────────────────┘      └───────────┘
       │                       │                       │
  ┌────▼────┐          ┌───────▼────────┐         ┌────▼────┐
  │Cliente A│          │   Cliente B    │         │Cliente C│
  │Restau...│          │   Farmacia     │         │ Tienda  │
  └─────────┘          └────────────────┘         └─────────┘
```

## 🔄 **Flujo de Mensajes:**

### 📱 **Cuando un cliente envía mensaje:**

```
1. Usuario → WhatsApp → +15551111 ("Hola")
2. Twilio → Webhook → https://whatsapp.horizonai.cl/webhook/whatsapp
3. Sistema busca bot por número: +15551111 → Bot A
4. Bot A usa → Assistant AAA (Restaurante)
5. Respuesta → Twilio → Usuario (desde +15551111)
```

### 🔧 **Sin conflictos:**

```
Usuario A → +15551111 → Bot A → Asistente Restaurante
Usuario B → +15552222 → Bot B → Asistente Farmacia  
Usuario C → +15553333 → Bot C → Asistente Tienda
```

## 📋 **Configuración Única vs Por Cliente**

### ✅ **Configuración ÚNICA (archivo .env):**
```env
# Estas credenciales sirven para TODOS los clientes
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=tu_auth_token
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxx

# Este número solo es fallback (opcional)
TWILIO_WHATSAPP_FROM=whatsapp:+15550000000
```

### 🤖 **Configuración POR CLIENTE (base de datos):**
```json
Bot A: {
  "name": "Restaurante La Cocina",
  "twilio_phone_number": "+15551111111",
  "assistant_id": "asst_ABC123",
  "instructions": "Eres asistente del restaurante..."
}

Bot B: {
  "name": "Farmacia Salud",
  "twilio_phone_number": "+15552222222", 
  "assistant_id": "asst_DEF456",
  "instructions": "Eres asistente de farmacia..."
}
```

## 🛠️ **Operaciones del Sistema**

### 🔍 **Cómo el sistema encuentra el bot correcto:**

```python
# Webhook recibe:
From: whatsapp:+56912345678  # Cliente
To: whatsapp:+15551111111    # Bot específico
Body: "Hola"

# Sistema busca:
bot = find_bot_by_phone_number("+15551111111")
# Encuentra → Bot A (Restaurante)

# Procesa con asistente específico:
response = assistant_AAA.process_message("Hola")
# Respuesta del restaurante

# Responde automáticamente desde +15551111111
```

### 📊 **Escalabilidad:**

| Clientes | Números | Asistentes | Servidor |
|----------|---------|------------|----------|
| 1-10     | 1-10    | 1-10       | 1 pequeño |
| 10-50    | 10-50   | 10-50      | 1 mediano |
| 50-200   | 50-200  | 50-200     | 1 grande  |
| 200+     | 200+    | 200+       | Cluster   |

## 💰 **Modelo de Costos**

### 📱 **Por cliente:**
- **Número Twilio**: ~$1/mes
- **Mensajes**: ~$0.005 c/u
- **OpenAI**: ~$0.01/1K tokens

### 🖥️ **Infraestructura compartida:**
- **Servidor**: $10-50/mes (todos los clientes)
- **Dominio**: $10/año
- **SSL**: Gratis (Let's Encrypt)

### 💡 **Ejemplo 10 clientes:**
```
Números: 10 × $1 = $10/mes
Servidor: $20/mes (compartido)
Mensajes: Variable según uso
OpenAI: Variable según conversaciones

Total fijo: ~$30/mes para 10 clientes
```

## 🔧 **Gestión Multi-Cliente**

### 📋 **Ver todos los clientes:**
```bash
curl https://whatsapp.horizonai.cl/bots/ | jq '.[] | {
  name, 
  twilio_phone_number, 
  assistant_id,
  metadata.cliente
}'
```

### 📊 **Monitoreo por cliente:**
```bash
# Logs del Cliente A
sudo journalctl -u horizonai-whatsapp-bot -f | grep "+15551111"

# Logs del Cliente B  
sudo journalctl -u horizonai-whatsapp-bot -f | grep "+15552222"

# Logs de todos
sudo journalctl -u horizonai-whatsapp-bot -f
```

### 🔄 **Backup de configuraciones:**
```bash
# Exportar todos los bots
curl https://whatsapp.horizonai.cl/bots/ > backup_bots_$(date +%Y%m%d).json

# Restaurar bot específico
curl -X POST https://whatsapp.horizonai.cl/bots/ \
  -H "Content-Type: application/json" \
  -d @bot_backup.json
```

## 🚀 **Ventajas del Sistema Multi-Cliente**

### ✅ **Para el proveedor (tú):**
- Un solo servidor para todos
- Gestión centralizada
- Economías de escala
- Fácil mantenimiento
- Monitoreo unificado

### ✅ **Para el cliente:**
- Número propio independiente
- Asistente personalizado
- Sin interferencias
- Configuración específica
- Branding propio

### ✅ **Técnicas:**
- Sin conflictos de números
- Escalabilidad horizontal
- Aislamiento de datos
- Configuración granular
- Logs separados

## 🔒 **Aislamiento y Seguridad**

### 🔐 **Datos separados:**
- Cada bot tiene su asistente único
- Conversaciones aisladas por número
- Metadata independiente
- Logs filtrables por cliente

### 🛡️ **Seguridad:**
- Credenciales comunes (Twilio/OpenAI)
- Sin acceso cruzado entre clientes
- Webhook único pero enrutamiento correcto
- Logs auditables por cliente

¡Este sistema está diseñado para crecer desde 1 hasta cientos de clientes! 🚀