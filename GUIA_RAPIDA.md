# 🚀 Guía Rápida - Sistema Multi-Cliente HorizonAI

## 📋 **Para Nuevos Usuarios**

### ✅ **1. Configuración Inicial (Solo una vez)**

```bash
# Clonar el proyecto
git clone https://github.com/tu-usuario/HorizonaiBots.git
cd HorizonaiBots

# Configurar variables de entorno
cp .env.production .env
# Editar .env con tus credenciales de Twilio y OpenAI

# Instalar en servidor (Ubuntu/Debian)
./install-server-fixed.sh
```

### 🤖 **2. Crear Primer Cliente**

```bash
# Ejecutar script de creación automática
./crear-cliente.sh

# El script te preguntará:
# - Nombre del cliente
# - Número de teléfono de Twilio
# - Tipo de negocio
# - Instrucciones del asistente
```

## 👥 **Para Gestión Diaria**

### 📊 **Monitorear Todos los Clientes**

```bash
./monitor-clientes.sh
```

**Opciones disponibles:**
- `1` - Ver todos los clientes activos
- `2` - Monitorear cliente específico  
- `3` - Ver logs en tiempo real
- `4` - Buscar en logs
- `5` - Estadísticas del servidor
- `6` - Probar bot específico
- `7` - Crear backup
- `8` - Estado del servidor
- `9` - Ver configuración

### 🆕 **Agregar Nuevo Cliente**

```bash
./crear-cliente.sh
```

**Datos que necesitas:**
- Número de WhatsApp Business (de Twilio)
- Nombre del cliente/negocio
- Tipo de negocio (restaurante, farmacia, etc.)
- Instrucciones específicas para el asistente

## 🛠️ **Comandos Útiles**

### 📱 **Ver todos los clientes:**
```bash
curl https://whatsapp.horizonai.cl/bots/ | jq .
```

### 📜 **Ver logs específicos:**
```bash
sudo journalctl -u horizonai-whatsapp-bot -f | grep "+15551111111"
```

### 🧪 **Probar un bot:**
```bash
curl -X POST https://whatsapp.horizonai.cl/webhook/whatsapp \
  -d "From=whatsapp:+56900000000" \
  -d "To=whatsapp:+15551111111" \
  -d "Body=Hola prueba"
```

### 💾 **Crear backup:**
```bash
curl https://whatsapp.horizonai.cl/bots/ > backup_$(date +%Y%m%d).json
```

## 🔧 **Solución de Problemas**

### ❌ **Bot no responde:**
```bash
# Verificar servicio
sudo systemctl status horizonai-whatsapp-bot

# Revisar logs
sudo journalctl -u horizonai-whatsapp-bot -n 50

# Reiniciar servicio
sudo systemctl restart horizonai-whatsapp-bot
```

### 🔍 **Verificar configuración:**
```bash
# Ver bots activos
curl https://whatsapp.horizonai.cl/bots/

# Verificar webhook
curl -I https://whatsapp.horizonai.cl/webhook/whatsapp
```

### 🛡️ **Verificar SSL:**
```bash
curl -I https://whatsapp.horizonai.cl/
```

## 📞 **Flujo de Trabajo Típico**

### 🆕 **Cliente Nuevo:**
1. Cliente compra número WhatsApp Business en Twilio
2. Ejecutar `./crear-cliente.sh`
3. Configurar webhook en Twilio → `https://whatsapp.horizonai.cl/webhook/whatsapp`
4. Probar bot enviando mensaje
5. Cliente está listo para usar

### 📊 **Monitoreo Diario:**
1. Ejecutar `./monitor-clientes.sh`
2. Revisar estadísticas (opción 5)
3. Verificar logs si hay problemas
4. Crear backup semanal (opción 7)

### 🔧 **Mantenimiento:**
1. Verificar estado del servidor
2. Limpiar logs antiguos: `./cleanup-server.sh`
3. Actualizar sistema si es necesario
4. Verificar certificados SSL

## 📚 **Documentación Completa**

- `CLIENTE_NUEVO.md` - Proceso detallado de creación de clientes
- `ARQUITECTURA_MULTICLIENTE.md` - Documentación técnica
- `DEPLOYMENT.md` - Proceso de despliegue
- `README.md` - Documentación general

## 💡 **Consejos Pro**

### 🎯 **Para eficiencia:**
- Usa `monitor-clientes.sh` como herramienta principal
- Crea backups regulares de configuraciones
- Monitorea logs en tiempo real durante problemas
- Mantén documentación de cada cliente

### 🔒 **Para seguridad:**
- Nunca compartas el archivo `.env`
- Mantén actualizados Twilio y OpenAI APIs
- Revisa logs regularmente por actividad sospechosa
- Usa certificados SSL válidos

### 📈 **Para escalabilidad:**
- Un servidor puede manejar 50-100 clientes fácilmente
- Cada cliente es completamente independiente
- Los costos se distribuyen eficientemente
- Fácil agregar/quitar clientes

---

**🎉 ¡Sistema listo para crecer desde 1 hasta cientos de clientes!**

*Para soporte: revisa los logs, usa las herramientas de monitoreo y consulta la documentación completa.*