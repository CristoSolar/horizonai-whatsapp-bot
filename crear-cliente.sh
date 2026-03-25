#!/bin/bash

# 🚀 Script Automatizado para Crear Nuevo Cliente
# Sistema Multi-Cliente: Un servidor, múltiples clientes independientes
# 
# Uso: ./crear-cliente.sh "Nombre Cliente" "+número" "assistant_id"
#
# ⚠️  IMPORTANTE: NO necesitas crear asistentes aquí
#    El asistente debe estar YA CREADO en tu plataforma OpenAI
#    Este script solo registra el bot con el número de teléfono

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Configuración
API_BASE="https://whatsapp.horizonai.cl"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo -e "${PURPLE}┌─────────────────────────────────────────────────┐${NC}"
echo -e "${PURPLE}│  🤖 HorizonAI WhatsApp Bot - Nuevo Cliente     │${NC}"
echo -e "${PURPLE}│  Sistema Multi-Cliente Escalable               │${NC}"
echo -e "${PURPLE}└─────────────────────────────────────────────────┘${NC}"

# Función para mostrar ayuda
show_help() {
    echo -e "${BLUE}🤖 Script para Crear Nuevo Cliente WhatsApp Bot${NC}"
    echo -e "${BLUE}Sistema Multi-Cliente: Un servidor → Múltiples clientes${NC}"
    echo ""
    echo -e "${YELLOW}⚠️  IMPORTANTE:${NC}"
    echo -e "${YELLOW}   • NO modifiques el archivo .env para cada cliente${NC}"
    echo -e "${YELLOW}   • Cada cliente tiene su número independiente${NC}"
    echo -e "${YELLOW}   • Un solo servidor maneja todos los clientes${NC}"
    echo ""
    echo "Uso:"
    echo "  $0 \"Nombre Cliente\" \"+número\" \"assistant_id\""
    echo "  $0   # modo interactivo"
    echo ""
    echo "Ejemplo:"
    echo "  $0 \"CFMoto\" \"+15559015856\" \"asst_kxjxMdZC8E0z539yukkqK0oH\""
    echo ""
    echo "Parámetros:"
    echo "  1. Nombre del cliente (entre comillas)"
    echo "  2. Número de WhatsApp (con código de país)"
    echo "  3. Assistant ID de OpenAI (ya existente en tu plataforma)"
    echo ""
    echo -e "${GREEN}Clientes actuales:${NC}"
    if [ -f "clientes_creados.log" ]; then
        echo "$(cat clientes_creados.log | cut -d'|' -f2,3 | head -5)"
    else
        echo "  (Ningún cliente creado aún)"
    fi
    exit 1
}

  prompt_interactive() {
    echo -e "${BLUE}Modo interactivo activado${NC}"
    echo ""

    read -r -p "Nombre del cliente: " CLIENTE_NOMBRE
    read -r -p "Numero de WhatsApp (formato +569XXXXXXXX): " NUMERO_WHATSAPP
    read -r -p "Assistant ID de OpenAI (ya existente): " ASSISTANT_ID

    if [ -z "${CLIENTE_NOMBRE}" ] || [ -z "${NUMERO_WHATSAPP}" ] || [ -z "${ASSISTANT_ID}" ]; then
      echo -e "${RED}❌ Nombre, numero y assistant_id son obligatorios${NC}"
      exit 1
    fi
  }

# Verificar parámetros
  if [ $# -eq 0 ]; then
    prompt_interactive
  elif [ $# -eq 3 ]; then
    CLIENTE_NOMBRE="$1"
    NUMERO_WHATSAPP="$2"
    ASSISTANT_ID="$3"
  else
    echo -e "${RED}❌ Error: Usa 0 parámetros (interactivo) o 3 parámetros (nombre, número, assistant_id)${NC}"
    show_help
  fi

echo ""
echo -e "${BLUE}🚀 Creando nuevo cliente: ${CLIENTE_NOMBRE}${NC}"
echo -e "${YELLOW}📱 Número independiente: ${NUMERO_WHATSAPP}${NC}"
echo -e "${GREEN}🔧 Sistema: Multi-cliente sin conflictos${NC}"
echo ""

# Verificar si el número ya existe
echo -e "${YELLOW}🔍 Verificando si el número ya está en uso...${NC}"
EXISTING_BOT=$(curl -s "${API_BASE}/bots/" | grep -o "\"twilio_phone_number\":\"${NUMERO_WHATSAPP}\"" || echo "")
if [ ! -z "$EXISTING_BOT" ]; then
    echo -e "${RED}❌ Error: El número ${NUMERO_WHATSAPP} ya está asignado a otro bot${NC}"
    echo -e "${YELLOW}💡 Usa un número diferente o verifica los bots existentes:${NC}"
    echo "   curl ${API_BASE}/bots/ | grep twilio_phone_number"
    exit 1
fi
echo -e "${GREEN}✅ Número disponible${NC}"

# Paso 1: Crear Bot en el Sistema
echo -e "${YELLOW}📋 Paso 1: Creando bot en el sistema...${NC}"

BOT_RESPONSE=$(curl -s -X POST "${API_BASE}/bots/" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"${CLIENTE_NOMBRE}\",
    \"twilio_phone_number\": \"${NUMERO_WHATSAPP}\",
    \"assistant_id\": \"${ASSISTANT_ID}\",
    \"metadata\": {
      \"cliente\": \"${CLIENTE_NOMBRE}\",
      \"fecha_creacion\": \"${TIMESTAMP}\",
      \"creado_por\": \"script_automatico\"
    }
  }")

# Extraer Bot ID usando jq (más confiable con JSON)
if command -v jq &> /dev/null; then
    BOT_ID=$(echo "$BOT_RESPONSE" | jq -r '.data.id // empty')
else
    # Fallback si jq no está disponible
    BOT_ID=$(echo "$BOT_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
fi

if [ -z "$BOT_ID" ]; then
    echo -e "${RED}❌ Error creando bot. Respuesta completa:${NC}"
    echo "$BOT_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ Bot creado: ${BOT_ID}${NC}"

# Paso 2: Test del Webhook
echo -e "${YELLOW}🧪 Paso 2: Probando webhook...${NC}"

TEST_RESPONSE=$(curl -s -X POST "${API_BASE}/webhook/whatsapp" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "From=whatsapp:+1234567890&To=${NUMERO_WHATSAPP}&Body=Hola, soy un test&MessageSid=test_${BOT_ID}")

if [[ "$TEST_RESPONSE" == *"error"* ]]; then
    echo -e "${YELLOW}⚠️  Test webhook con advertencias:${NC}"
    echo "$TEST_RESPONSE"
else
    echo -e "${GREEN}✅ Webhook funcionando correctamente${NC}"
fi

# Paso 3: Generar Reporte
echo ""
echo -e "${BLUE}📊 REPORTE DE CREACIÓN COMPLETADO${NC}"
echo -e "${BLUE}=================================${NC}"
echo -e "${GREEN}Cliente:${NC} ${CLIENTE_NOMBRE}"
echo -e "${GREEN}Número WhatsApp:${NC} ${NUMERO_WHATSAPP}"
echo -e "${GREEN}Assistant ID:${NC} ${ASSISTANT_ID}"
echo -e "${GREEN}Bot ID:${NC} ${BOT_ID}"
echo -e "${GREEN}Fecha:${NC} ${TIMESTAMP}"
echo ""

# Paso 4: Instrucciones para Twilio
echo -e "${YELLOW}📱 CONFIGURACIÓN PENDIENTE EN TWILIO:${NC}"
echo -e "${YELLOW}===================================${NC}"
echo "1. Ve a Twilio Console → WhatsApp → Senders"
echo "2. Encuentra el número: ${NUMERO_WHATSAPP}"
echo "3. Configura Webhook URL:"
echo "   ${API_BASE}/webhook/whatsapp"
echo "4. Método: HTTP Post"
echo ""

# Paso 5: Comandos útiles
echo -e "${BLUE}🔧 COMANDOS ÚTILES PARA ESTE CLIENTE:${NC}"
echo -e "${BLUE}====================================${NC}"
echo "# Ver detalles del bot:"
echo "curl ${API_BASE}/bots/${BOT_ID} | jq ."
echo ""
echo "# Actualizar instrucciones:"
echo "curl -X PUT ${API_BASE}/bots/${BOT_ID} \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"instructions\": \"nuevas instrucciones\"}'"
echo ""
echo "# Ver logs SOLO de este cliente:"
echo "sudo journalctl -u horizonai-whatsapp-bot -f | grep \"${NUMERO_WHATSAPP}\""
echo ""
echo "# Test manual para este cliente:"
echo "curl -X POST ${API_BASE}/webhook/whatsapp \\"
echo "  -H \"Content-Type: application/x-www-form-urlencoded\" \\"
echo "  -d 'From=whatsapp:+1234567890&To=${NUMERO_WHATSAPP}&Body=Hola'"
echo ""
echo "# Ver TODOS los clientes:"
echo "curl ${API_BASE}/bots/ | jq '.[] | {name, twilio_phone_number, assistant_id}'"
echo ""

# Paso 6: Recordatorios importantes
echo -e "${PURPLE}📋 RECORDATORIOS IMPORTANTES:${NC}"
echo -e "${PURPLE}============================${NC}"
echo -e "${GREEN}✅ El archivo .env NO se modifica para este cliente${NC}"
echo -e "${GREEN}✅ Este número (${NUMERO_WHATSAPP}) es independiente${NC}"
echo -e "${GREEN}✅ Puedes crear más clientes sin conflictos${NC}"
echo -e "${YELLOW}⚠️  Configura el webhook en Twilio para ${NUMERO_WHATSAPP}${NC}"
echo -e "${YELLOW}⚠️  URL webhook: ${API_BASE}/webhook/whatsapp${NC}"
echo ""

# Paso 7: Guardar en archivo de log
LOG_FILE="clientes_creados.log"
echo "${TIMESTAMP} | ${CLIENTE_NOMBRE} | ${NUMERO_WHATSAPP} | ${ASSISTANT_ID} | ${BOT_ID}" >> "$LOG_FILE"
echo -e "${GREEN}📝 Información guardada en: ${LOG_FILE}${NC}"

echo ""
echo -e "${GREEN}🎉 ¡Cliente creado exitosamente!${NC}"
echo -e "${YELLOW}📞 Recuerda configurar el webhook en Twilio Console${NC}"