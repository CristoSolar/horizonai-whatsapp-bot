# HorizonAI WhatsApp Bot - URLs y Configuración

## 📡 URLs del Servicio

### Webhook de Twilio
```
https://whatsapp.tudominio.com/webhook/whatsapp
```

### API Endpoints
```
# Listar bots
GET https://whatsapp.tudominio.com/bots/

# Crear bot
POST https://whatsapp.tudominio.com/bots/

# Obtener bot específico
GET https://whatsapp.tudominio.com/bots/{bot_id}

# Actualizar bot
PUT https://whatsapp.tudominio.com/bots/{bot_id}

# Eliminar bot
DELETE https://whatsapp.tudominio.com/bots/{bot_id}

# Refrescar bots desde base de datos
POST https://whatsapp.tudominio.com/bots/refresh

# Health check
GET https://whatsapp.tudominio.com/health
```

## 🔧 Configuración en Twilio

1. **Ir a Twilio Console**: https://console.twilio.com/
2. **Messaging → Settings → WhatsApp sandbox settings**
3. **Webhook URL**: `https://whatsapp.tudominio.com/webhook/whatsapp`
4. **HTTP Method**: POST
5. **Webhook events**: Receive incoming messages

## 📋 Variables de Entorno Requeridas

```bash
# Flask
FLASK_ENV=production
SECRET_KEY=your-super-secret-key

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_DEFAULT_MODEL=gpt-4o-mini

# Twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# Horizon
HORIZON_API_KEY=...
HORIZON_BASE_URL=https://api.horizon.local

# Redis
REDIS_URL=redis://localhost:6379/0
```

## 🚀 Comandos de Despliegue

```bash
# Subir archivos al servidor
scp -r . user@server:/opt/horizonai-bots/

# Desplegar actualizaciones
./deploy.sh

# Ver logs en el servidor
sudo journalctl -u horizonai-bots -f

# Reiniciar servicio
sudo systemctl restart horizonai-bots

# Estado del servicio
sudo systemctl status horizonai-bots
```

## 🧪 Pruebas

```bash
# Test de conectividad
curl https://whatsapp.tudominio.com/health

# Crear bot de prueba
curl -X POST https://whatsapp.tudominio.com/bots/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bot de Prueba",
    "twilio_phone_number": "+14847491194",
    "instructions": "Eres un asistente de WhatsApp en español",
    "assistant_config": {
      "name": "Asistente WhatsApp",
      "model": "gpt-4o-mini"
    }
  }'
```