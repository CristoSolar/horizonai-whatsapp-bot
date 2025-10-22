#!/bin/bash

# 📊 HorizonAI WhatsApp Bot - Monitor Multi-Cliente
# Este script facilita el monitoreo y gestión de múltiples clientes

# Colores para mejor visualización
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Configuración
API_BASE="https://whatsapp.horizonai.cl"
LOG_LINES=20

# Función para mostrar el encabezado
show_header() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                🤖 HORIZONAI MONITOR MULTI-CLIENTE            ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Función para mostrar el menú principal
show_menu() {
    echo -e "${WHITE}📋 OPCIONES DISPONIBLES:${NC}"
    echo -e "${GREEN}  1)${NC} 📊 Ver todos los clientes/bots"
    echo -e "${GREEN}  2)${NC} 📱 Monitorear cliente específico"
    echo -e "${GREEN}  3)${NC} 📜 Ver logs en tiempo real"
    echo -e "${GREEN}  4)${NC} 🔍 Buscar en logs"
    echo -e "${GREEN}  5)${NC} 📈 Estadísticas de uso"
    echo -e "${GREEN}  6)${NC} 🧪 Probar bot específico"
    echo -e "${GREEN}  7)${NC} 💾 Backup de configuraciones"
    echo -e "${GREEN}  8)${NC} 🔧 Ver estado del servidor"
    echo -e "${GREEN}  9)${NC} 📋 Ver configuración .env"
    echo -e "${RED}  0)${NC} 🚪 Salir"
    echo ""
    echo -e "${YELLOW}Selecciona una opción (0-9):${NC} "
}

# Función para obtener todos los bots
get_all_bots() {
    echo -e "${BLUE}📊 Obteniendo lista de todos los clientes...${NC}"
    echo ""
    
    response=$(curl -s "$API_BASE/bots/")
    
    if [ $? -eq 0 ] && [ "$response" != "null" ] && [ "$response" != "" ]; then
        echo -e "${GREEN}✅ Clientes activos:${NC}"
        echo ""
        
        # Cabecera de la tabla
        printf "${WHITE}%-25s %-18s %-20s %-15s${NC}\n" "NOMBRE" "TELÉFONO" "ASSISTANT ID" "CLIENTE"
        echo -e "${CYAN}─────────────────────────────────────────────────────────────────────────────${NC}"
        
        # Procesar cada bot
        echo "$response" | jq -r '.[] | "\(.name // "Sin nombre")|\(.twilio_phone_number // "Sin número")|\(.assistant_id // "Sin assistant")|\(.metadata.cliente // "Sin cliente")"' | while IFS='|' read -r name phone assistant cliente; do
            printf "%-25s %-18s %-20s %-15s\n" "$name" "$phone" "$assistant" "$cliente"
        done
        
        echo ""
        total=$(echo "$response" | jq '. | length')
        echo -e "${GREEN}📊 Total de clientes activos: $total${NC}"
        
    else
        echo -e "${RED}❌ Error al obtener la lista de bots o no hay bots configurados${NC}"
        echo -e "${YELLOW}💡 Usa el script crear-cliente.sh para crear tu primer cliente${NC}"
    fi
}

# Función para monitorear cliente específico
monitor_specific_client() {
    echo -e "${BLUE}📱 Ingresa el número de teléfono del cliente (ej: +15551111111):${NC} "
    read phone_number
    
    if [ -z "$phone_number" ]; then
        echo -e "${RED}❌ Número de teléfono requerido${NC}"
        return
    fi
    
    echo -e "${BLUE}🔍 Buscando información del cliente $phone_number...${NC}"
    echo ""
    
    # Buscar bot específico
    response=$(curl -s "$API_BASE/bots/")
    bot_info=$(echo "$response" | jq -r ".[] | select(.twilio_phone_number == \"$phone_number\")")
    
    if [ "$bot_info" != "" ]; then
        echo -e "${GREEN}✅ Cliente encontrado:${NC}"
        echo "$bot_info" | jq .
        echo ""
        
        echo -e "${YELLOW}📜 Últimos logs del cliente:${NC}"
        sudo journalctl -u horizonai-whatsapp-bot -n $LOG_LINES | grep "$phone_number" || echo -e "${YELLOW}No hay logs recientes para este número${NC}"
    else
        echo -e "${RED}❌ Cliente no encontrado con número: $phone_number${NC}"
    fi
}

# Función para ver logs en tiempo real
view_realtime_logs() {
    echo -e "${BLUE}📜 Mostrando logs en tiempo real...${NC}"
    echo -e "${YELLOW}💡 Presiona Ctrl+C para salir${NC}"
    echo ""
    sleep 2
    sudo journalctl -u horizonai-whatsapp-bot -f --no-pager
}

# Función para buscar en logs
search_logs() {
    echo -e "${BLUE}🔍 Ingresa el término a buscar en los logs:${NC} "
    read search_term
    
    if [ -z "$search_term" ]; then
        echo -e "${RED}❌ Término de búsqueda requerido${NC}"
        return
    fi
    
    echo -e "${BLUE}🔍 Buscando '$search_term' en los logs...${NC}"
    echo ""
    
    sudo journalctl -u horizonai-whatsapp-bot | grep -i "$search_term" | tail -20
}

# Función para mostrar estadísticas
show_statistics() {
    echo -e "${BLUE}📈 Generando estadísticas de uso...${NC}"
    echo ""
    
    # Estadísticas del servidor
    echo -e "${GREEN}🖥️  ESTADO DEL SERVIDOR:${NC}"
    echo -e "   CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)% en uso"
    echo -e "   RAM: $(free -h | awk '/^Mem:/ {print $3 "/" $2}')"
    echo -e "   Disco: $(df -h / | awk 'NR==2 {print $3 "/" $2 " (" $5 " usado)"}')"
    echo ""
    
    # Estadísticas de la aplicación
    echo -e "${GREEN}📊 ESTADÍSTICAS DE LA APLICACIÓN:${NC}"
    
    # Contar bots activos
    total_bots=$(curl -s "$API_BASE/bots/" | jq '. | length' 2>/dev/null || echo "0")
    echo -e "   Clientes activos: $total_bots"
    
    # Estadísticas de logs (últimas 24h)
    log_messages=$(sudo journalctl -u horizonai-whatsapp-bot --since "24 hours ago" | wc -l)
    echo -e "   Logs últimas 24h: $log_messages líneas"
    
    # Verificar estado del servicio
    service_status=$(systemctl is-active horizonai-whatsapp-bot)
    if [ "$service_status" = "active" ]; then
        echo -e "   Estado del servicio: ${GREEN}✅ Activo${NC}"
    else
        echo -e "   Estado del servicio: ${RED}❌ Inactivo${NC}"
    fi
    
    # Uptime del servicio
    uptime=$(systemctl show horizonai-whatsapp-bot --property=ActiveEnterTimestamp --value | xargs -I {} date -d {} +%s 2>/dev/null)
    if [ "$uptime" != "" ]; then
        current=$(date +%s)
        duration=$((current - uptime))
        days=$((duration / 86400))
        hours=$(((duration % 86400) / 3600))
        echo -e "   Uptime: ${days}d ${hours}h"
    fi
}

# Función para probar bot específico
test_specific_bot() {
    echo -e "${BLUE}🧪 Ingresa el número de teléfono del bot a probar:${NC} "
    read phone_number
    
    if [ -z "$phone_number" ]; then
        echo -e "${RED}❌ Número de teléfono requerido${NC}"
        return
    fi
    
    echo -e "${BLUE}💬 Ingresa el mensaje de prueba:${NC} "
    read test_message
    
    if [ -z "$test_message" ]; then
        test_message="Hola, prueba de funcionamiento"
    fi
    
    echo -e "${BLUE}🧪 Enviando mensaje de prueba al bot $phone_number...${NC}"
    echo ""
    
    # Simular webhook de Twilio
    curl -X POST "$API_BASE/webhook/whatsapp" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "From=whatsapp%3A%2B56900000000" \
        -d "To=whatsapp%3A%2B${phone_number//+/}" \
        -d "Body=${test_message// /%20}" \
        -d "MessageSid=TEST$(date +%s)" \
        -v
    
    echo ""
    echo -e "${GREEN}✅ Prueba enviada. Revisa los logs para ver la respuesta.${NC}"
}

# Función para backup
create_backup() {
    echo -e "${BLUE}💾 Creando backup de configuraciones...${NC}"
    
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_file="backup_bots_$timestamp.json"
    
    curl -s "$API_BASE/bots/" > "$backup_file"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Backup creado: $backup_file${NC}"
        ls -lh "$backup_file"
    else
        echo -e "${RED}❌ Error al crear backup${NC}"
    fi
}

# Función para ver estado del servidor
show_server_status() {
    echo -e "${BLUE}🔧 Estado detallado del servidor...${NC}"
    echo ""
    
    echo -e "${GREEN}📊 PROCESOS:${NC}"
    ps aux | grep -E "(python|gunicorn|nginx)" | grep -v grep
    echo ""
    
    echo -e "${GREEN}🌐 PUERTOS:${NC}"
    netstat -tlnp | grep -E ":80|:443|:5000"
    echo ""
    
    echo -e "${GREEN}📡 SERVICIOS:${NC}"
    systemctl status horizonai-whatsapp-bot --no-pager -l
    echo ""
    systemctl status nginx --no-pager -l
}

# Función para ver configuración .env
show_env_config() {
    echo -e "${BLUE}📋 Configuración del archivo .env:${NC}"
    echo ""
    
    if [ -f ".env" ]; then
        echo -e "${GREEN}✅ Archivo .env encontrado${NC}"
        echo ""
        
        # Mostrar configuración ocultando valores sensibles
        cat .env | sed -E 's/(.*_KEY|.*_TOKEN|.*_SECRET)=.*/\1=***OCULTO***/' | \
        while IFS= read -r line; do
            if [[ $line =~ ^[[:space:]]*# ]]; then
                echo -e "${CYAN}$line${NC}"
            elif [[ $line =~ = ]]; then
                echo -e "${WHITE}$line${NC}"
            else
                echo "$line"
            fi
        done
    else
        echo -e "${RED}❌ Archivo .env no encontrado${NC}"
        echo -e "${YELLOW}💡 Crea el archivo .env con las credenciales necesarias${NC}"
    fi
}

# Función principal
main() {
    while true; do
        show_header
        show_menu
        read -r option
        
        case $option in
            1)
                show_header
                get_all_bots
                ;;
            2)
                show_header
                monitor_specific_client
                ;;
            3)
                show_header
                view_realtime_logs
                ;;
            4)
                show_header
                search_logs
                ;;
            5)
                show_header
                show_statistics
                ;;
            6)
                show_header
                test_specific_bot
                ;;
            7)
                show_header
                create_backup
                ;;
            8)
                show_header
                show_server_status
                ;;
            9)
                show_header
                show_env_config
                ;;
            0)
                echo -e "${GREEN}👋 ¡Hasta luego!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}❌ Opción no válida. Intenta de nuevo.${NC}"
                ;;
        esac
        
        echo ""
        echo -e "${YELLOW}Presiona Enter para continuar...${NC}"
        read
    done
}

# Verificar si se está ejecutando como root para ciertos comandos
check_permissions() {
    if [[ $EUID -eq 0 ]]; then
        echo -e "${YELLOW}⚠️  Ejecutándose como root${NC}"
    fi
}

# Verificar conectividad
check_connectivity() {
    if ! curl -s --head "$API_BASE/bots/" > /dev/null; then
        echo -e "${RED}❌ No se puede conectar a $API_BASE${NC}"
        echo -e "${YELLOW}💡 Verifica que el servidor esté funcionando${NC}"
        exit 1
    fi
}

# Ejecutar verificaciones y programa principal
check_permissions
check_connectivity
main