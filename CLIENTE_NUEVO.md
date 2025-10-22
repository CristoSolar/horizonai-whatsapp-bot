# 📋 Guía para Agregar Nuevos Clientes - HorizonAI WhatsApp Bot

## 🎯 **Sistema Multi-Cliente**

Este sistema está diseñado para manejar **múltiples clientes** con **números independientes** y **asistentes personalizados**, todo desde una sola instalación.

### 🏗️ **Arquitectura:**
```
┌─ Cliente A (+15551111111) ─ Bot A ─ Assistant A
├─ Cliente B (+15552222222) ─ Bot B ─ Assistant B  
├─ Cliente C (+15553333333) ─ Bot C ─ Assistant C
└─ .env (credenciales comunes + número fallback)
```

### ✅ **Ventajas:**
- Un servidor maneja todos los clientes
- Cada cliente tiene su número y personalidad únicas
- Sin conflictos entre números
- Gestión centralizada y escalable

**Credenciales necesarias:**
- Twilio Account SID: `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (ejemplo)
- Twilio Auth Token: `tu_auth_token_aqui`
- OpenAI API Key: `sk-proj-xxxxxxxxxxxxxxxxxx`

## 🎯 **Proceso para Cada Cliente Nuevo**

## 📱 **PASO 1: Configurar Número de WhatsApp en Twilio**

### 1.1 Comprar/Configurar Número
```bash
# Opción A: Usar Twilio Console
1. Ve a Twilio Console → Phone Numbers → Manage → Buy a number
2. Selecciona un número con capacidades de WhatsApp
3. Configura el número para WhatsApp Business

# Opción B: Usar número existente del cliente
1. Ve a Twilio Console → WhatsApp → Senders
2. Click "Create new sender"
3. Registra el número del cliente
```

### 1.2 Configurar Webhook
```bash
# En Twilio Console → Messaging → WhatsApp senders
1. Selecciona el nuevo número
2. En "Webhook URL for incoming messages":
   https://whatsapp.horizonai.cl/webhook/whatsapp
3. Método: HTTP Post
4. Guarda la configuración
```

---

## 🤖 **PASO 2: Crear Asistente Personalizado en OpenAI**

### 2.1 Crear Asistente (OpenAI Console)
```bash
1. Ve a https://platform.openai.com/assistants
2. Click "Create Assistant"
3. Configura:
   - Name: "Bot para [Nombre Cliente]"
   - Instructions: [Prompt personalizado del cliente]
   - Model: gpt-4o-mini
   - Tools: [Según necesidades del cliente]
4. Guarda y copia el Assistant ID (ej: asst_abc123...)
```

### 2.2 Crear Asistente (vía API)
```bash
curl -X POST https://whatsapp.horizonai.cl/assistants/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bot Restaurante La Cocina",
    "instructions": "Eres un asistente para el restaurante La Cocina. Ayudas con reservas, menú y información general. Responde siempre en español de manera amigable.",
    "model": "gpt-4o-mini",
    "tools": []
  }'
```

---

## 🔧 **PASO 3: Crear Bot en el Sistema**

### 3.1 Crear Bot con Asistente
```bash
curl -X POST https://whatsapp.horizonai.cl/bots/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bot Restaurante La Cocina",
    "instructions": "Bot para atención al cliente del restaurante",
    "model": "gpt-4o-mini",
    "twilio_phone_number": "+15551234567",
    "assistant_id": "asst_abc123def456",
    "metadata": {
      "cliente": "Restaurante La Cocina",
      "industria": "Restaurantes",
      "fecha_creacion": "2025-10-22"
    }
  }'
```

### 3.2 Verificar Creación
```bash
# Listar todos los bots
curl https://whatsapp.horizonai.cl/bots/

# Ver bot específico
curl https://whatsapp.horizonai.cl/bots/[BOT_ID]
```

---

## 🧪 **PASO 4: Probar el Nuevo Bot**

### 4.1 Test Manual del Webhook
```bash
curl -X POST https://whatsapp.horizonai.cl/webhook/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'From=whatsapp:+56912345678&To=whatsapp:+15551234567&Body=Hola&MessageSid=test123'
```

### 4.2 Test Real por WhatsApp
```bash
1. Envía un mensaje al nuevo número desde WhatsApp
2. Verifica que responda con la personalidad correcta
3. Monitorea logs: sudo journalctl -u horizonai-whatsapp-bot -f
```

---

## 📊 **PASO 5: Monitoreo y Gestión**

### 5.1 Ver Logs del Cliente
```bash
# Logs en tiempo real
sudo journalctl -u horizonai-whatsapp-bot -f | grep "+15551234567"

# Logs históricos del número
sudo journalctl -u horizonai-whatsapp-bot --since "1 hour ago" | grep "+15551234567"
```

### 5.2 Estadísticas del Bot
```bash
# Health check general
curl https://whatsapp.horizonai.cl/health

# Ver todos los bots activos
curl https://whatsapp.horizonai.cl/bots/ | jq '.'
```

---

## 🔄 **PASO 6: Mantenimiento del Cliente**

### 6.1 Actualizar Asistente
```bash
# Cambiar instrucciones del bot
curl -X PUT https://whatsapp.horizonai.cl/bots/[BOT_ID] \
  -H "Content-Type: application/json" \
  -d '{
    "instructions": "Nuevas instrucciones actualizadas"
  }'

# Cambiar a un asistente diferente
curl -X PUT https://whatsapp.horizonai.cl/bots/[BOT_ID] \
  -H "Content-Type: application/json" \
  -d '{
    "assistant_id": "asst_nuevo123"
  }'
```

### 6.2 Desactivar/Eliminar Bot
```bash
# Eliminar bot (cuidado, es permanente)
curl -X DELETE https://whatsapp.horizonai.cl/bots/[BOT_ID]
```

---

## 📋 **PLANTILLA DE CHECKLIST**

### ✅ Checklist para Nuevo Cliente

```markdown
Cliente: ___________________
Fecha: ____________________

□ 1. Número WhatsApp configurado en Twilio
   - Número: ________________
   - Webhook configurado: □

□ 2. Asistente OpenAI creado
   - Assistant ID: ___________
   - Prompt personalizado: □
   - Tools configuradas: □

□ 3. Bot creado en sistema
   - Bot ID: ________________
   - Test webhook: □
   - Test WhatsApp real: □

□ 4. Documentación entregada
   - Instrucciones de uso: □
   - Números de contacto: □
   - Proceso de soporte: □

□ 5. Monitoreo configurado
   - Logs funcionando: □
   - Alertas configuradas: □
```

---

## 🚨 **Troubleshooting Común**

### Problema: Bot no responde
```bash
# 1. Verificar que el bot existe
curl https://whatsapp.horizonai.cl/bots/ | grep "numero_cliente"

# 2. Verificar logs
sudo journalctl -u horizonai-whatsapp-bot -n 50

# 3. Test manual del webhook
curl -X POST https://whatsapp.horizonai.cl/webhook/whatsapp \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'From=whatsapp:+cliente&To=whatsapp:+numero_bot&Body=test'
```

### Problema: Respuestas incorrectas
```bash
# Verificar asistente
curl https://whatsapp.horizonai.cl/bots/[BOT_ID] | jq '.assistant_id'

# Actualizar instrucciones
curl -X PUT https://whatsapp.horizonai.cl/bots/[BOT_ID] \
  -H "Content-Type: application/json" \
  -d '{"instructions": "nuevas_instrucciones"}'
```

---

## 💰 **Consideraciones de Costos**

### Twilio
- **Número WhatsApp**: ~$1/mes por número
- **Mensajes**: ~$0.005 por mensaje
- **Números adicionales**: Según región

### OpenAI
- **Assistant API**: ~$0.01 por 1K tokens
- **gpt-4o-mini**: Más económico que GPT-4

### Servidor
- **Un servidor**: Maneja múltiples clientes
- **Escalabilidad**: Agregar workers según carga

---

## 📞 **Plantilla de Propuesta para Cliente**

```markdown
## Propuesta Bot WhatsApp para [Cliente]

### Incluye:
✅ Número WhatsApp dedicado
✅ Asistente IA personalizado
✅ Integración con su marca
✅ Respuestas 24/7
✅ Monitoreo y reportes
✅ Soporte técnico

### Proceso:
1. Configuración inicial (1-2 días)
2. Personalización del asistente
3. Testing y ajustes
4. Lanzamiento
5. Capacitación del equipo

### Costo mensual:
- Setup inicial: $[X]
- Mensualidad: $[Y]
- Por mensaje: $[Z]
```

---

## ❓ **FAQ - Preguntas Frecuentes**

### 🤔 **¿El número del .env genera conflictos?**

**NO**, el sistema está diseñado correctamente:

- **Respuestas automáticas**: Usan TwiML (Twilio responde desde el mismo número que recibió)
- **Número del .env**: Solo es fallback para mensajes proactivos sin número específico
- **Múltiples clientes**: Cada uno tiene su número independiente

### 🔄 **¿Cómo funcionan múltiples números?**

```bash
Cliente A: +15551111111 → Bot A (assistant_1)
Cliente B: +15552222222 → Bot B (assistant_2) 
Cliente C: +15553333333 → Bot C (assistant_3)

.env: TWILIO_WHATSAPP_FROM=+15550000000 (solo fallback)
```

**Flujo real:**
1. Usuario envía a `+15551111111`
2. Sistema encuentra "Bot A" 
3. Procesa con "assistant_1"
4. Responde DESDE `+15551111111` (automático)

### 📱 **¿Necesito cambiar el .env para cada cliente?**

**NO**, mantén un solo `.env` con:
- Las credenciales de Twilio (comunes)
- Un número de fallback (opcional)
- Cada bot usa su número específico automáticamente

---