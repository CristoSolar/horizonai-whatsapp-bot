# 🧪 Guía de Prueba - Base de Datos de Clientes

## 🎯 **¿Qué resuelve?**

**Problema anterior**: Bot preguntaba siempre los mismos datos (marca, modelo, año, etc.)
**Solución nueva**: Bot recuerda información del cliente y no la vuelve a preguntar

## 🚀 **Actualizar en Servidor**

### 1️⃣ **Actualizar código:**
```bash
cd ~/horizonai-whatsapp-bot
git pull origin main
sudo systemctl restart horizonai-whatsapp-bot
sudo systemctl status horizonai-whatsapp-bot
```

### 2️⃣ **Verificar logs:**
```bash
sudo journalctl -u horizonai-whatsapp-bot -f
```

## 🧪 **Pruebas Funcionales**

### **Prueba 1: Primera conversación**
```
👤 Usuario: "Hola, necesito una batería"
🤖 Bot: "¡Hola! Te ayudo con la batería. ¿Qué vehículo tienes?"

👤 Usuario: "Es un Volkswagen Gol 2021 bencinero sin start stop"
🤖 Bot: "Perfecto, tengo la info del VW Gol 2021. ¿En qué comuna necesitas el servicio?"

👤 Usuario: "En La Florida"
🤖 Bot: "Excelente. Con esta información busco la batería adecuada..."
```

### **Prueba 2: Segunda conversación (mismo número)**
```
👤 Usuario: "Hola, ¿tienes disponibilidad hoy?"
🤖 Bot: "¡Hola! Claro, para tu Volkswagen Gol 2021 bencinero en La Florida..."
```

**✅ Resultado esperado**: Bot recuerda TODA la información previa.

### **Prueba 3: Verificar datos almacenados**
```bash
# Ver datos de un cliente específico
curl https://whatsapp.horizonai.cl/bots/clients/+56912345678

# Ver todos los clientes
curl https://whatsapp.horizonai.cl/bots/clients

# Limpiar datos de un cliente (para probar de nuevo)
curl -X DELETE https://whatsapp.horizonai.cl/bots/clients/+56912345678
```

## 📊 **¿Qué información extrae automáticamente?**

| Campo | Ejemplos detectados |
|-------|-------------------|
| **Marca** | volkswagen, vw, toyota, chevrolet, ford |
| **Modelo** | gol, corolla, aveo, fiesta, sentra |
| **Año** | 2021, 2020, 2019, etc. (1990-2025) |
| **Combustible** | bencinero, diesel, gasolina |
| **Start-Stop** | "sin start stop" → No, "con start stop" → Sí |
| **Comuna** | la florida, curicó, santiago, maipu |

## 🔍 **Monitoreo y Debug**

### **Ver logs específicos:**
```bash
# Logs del cliente específico
sudo journalctl -u horizonai-whatsapp-bot -f | grep "+56912345678"

# Ver extracciones de datos
sudo journalctl -u horizonai-whatsapp-bot -f | grep "extracted"
```

### **Verificar Redis:**
```bash
# Si tienes acceso a Redis
redis-cli keys "client_data:*"
redis-cli get "client_data:56912345678"
```

### **Endpoints de administración:**
```bash
# API para ver datos
curl https://whatsapp.horizonai.cl/bots/clients/

# API para ver cliente específico
curl https://whatsapp.horizonai.cl/bots/clients/56912345678

# API para limpiar cliente
curl -X DELETE https://whatsapp.horizonai.cl/bots/clients/56912345678
```

## 🎯 **Flujo de Prueba Completo**

### **Escenario: Cliente de Baterías**

1. **Primera conversación:**
   ```
   Usuario: "Hola, necesito una batería para mi auto"
   Bot: "¡Hola! Te ayudo. ¿Qué auto tienes?"
   
   Usuario: "Volkswagen Gol 2014 bencinero sin start stop"
   Bot: "Perfecto. ¿En qué comuna?"
   
   Usuario: "La Florida"
   Bot: "Excelente. Busco opciones para tu VW Gol 2014..."
   ```

2. **Esperar unos minutos y enviar:**
   ```
   Usuario: "¿Cuánto demora la instalación?"
   Bot: "Para tu Volkswagen Gol 2014 en La Florida, la instalación toma..."
   ```

3. **Al día siguiente:**
   ```
   Usuario: "Hola, ¿ya llegó mi batería?"
   Bot: "¡Hola! Verifico el estado de tu pedido para el VW Gol 2014..."
   ```

**✅ En cada mensaje, el bot debe recordar TODA la información previa.**

## 🔧 **Solución de Problemas**

### **Si bot sigue preguntando lo mismo:**
1. Verificar que se actualizó el código: `git log --oneline -1`
2. Revisar logs: `sudo journalctl -u horizonai-whatsapp-bot -f`
3. Verificar Redis: `curl https://whatsapp.horizonai.cl/bots/clients/`

### **Si no extrae información:**
1. Verificar formato de mensaje (debe contener marca, modelo, año)
2. Revisar logs de extracción
3. Probar con diferentes formatos:
   - "Volkswagen Gol 2021"
   - "VW Gol año 2021"
   - "tengo un gol 2021 de volkswagen"

### **Para resetear cliente:**
```bash
curl -X DELETE https://whatsapp.horizonai.cl/bots/clients/+56912345678
```

## 📈 **Métricas de Éxito**

- ✅ Bot no repite preguntas sobre datos ya conocidos
- ✅ Información persiste entre conversaciones
- ✅ Extracción automática funciona
- ✅ API de clientes responde correctamente
- ✅ Datos se almacenan por 30 días

¡El bot ahora tiene memoria persistente de clientes! 🧠💾