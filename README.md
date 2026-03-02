# Horizon WhatsApp Bot Service

Servicio Flask para administrar bots de WhatsApp que se integran con OpenAI (Assistants), Twilio y la API de Horizon. La aplicación expone endpoints REST para administrar bots y un webhook compatible con Twilio para manejar mensajes entrantes de WhatsApp. Redis se utiliza como capa de persistencia temporal para sesiones y estados conversacionales.

## Características principales

- Gestión de bots (crear, actualizar, listar y eliminar) con metadatos de asistentes de OpenAI.
- Webhook de Twilio que enruta los mensajes de WhatsApp hacia OpenAI y ejecuta acciones en la API de Horizon.
- Integración modular con OpenAI, Twilio y Horizon mediante servicios desacoplados.
- Redis como almacenamiento efímero de sesiones y contexto conversacional.
- Soporte para despliegue en producción con Nginx y SSL.
- Dockerfile y `docker-compose.yml` para desarrollo local.

## 🚀 Despliegue en Producción

### Requisitos del Servidor
- Ubuntu/Debian 20.04+
- Python 3.8+
- Nginx
- Redis
- SSL certificate (Let's Encrypt)
- Dominio configurado

### Instalación Rápida

1. **Subir archivos al servidor**:
   ```bash
   scp -r . user@your-server:/opt/horizonai-bots/
   ```

2. **Ejecutar script de instalación**:
   ```bash
   chmod +x install-server.sh
   ./install-server.sh
   ```

3. **Configurar tu dominio**:
   - Edita `/etc/nginx/sites-available/horizonai-bots`
   - Cambia `whatsapp.tudominio.com` por tu subdominio
   - Apunta tu DNS al servidor

4. **Activar el sitio**:
   ```bash
   sudo ln -s /etc/nginx/sites-available/horizonai-bots /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

5. **Obtener certificado SSL**:
   ```bash
   sudo certbot --nginx -d whatsapp.tudominio.com
   ```

6. **Configurar variables de entorno**:
   ```bash
   cp .env.production .env
   # Editar .env con tus credenciales reales
   ```

7. **Iniciar el servicio**:
   ```bash
   sudo systemctl start horizonai-bots
   sudo systemctl status horizonai-bots
   ```

### URL del Webhook
Una vez desplegado, configura en Twilio:
```
https://whatsapp.tudominio.com/webhook/whatsapp
```

### Despliegues Futuros
```bash
# Edita deploy.sh con tus datos del servidor
chmod +x deploy.sh
./deploy.sh
```

## 🛠️ Desarrollo Local

## Estructura del proyecto

```
app/
  __init__.py           # Factoría de la aplicación Flask
  config.py             # Configuración por entorno
  extensions.py         # Clientes Redis, OpenAI, Twilio, Horizon
  repositories/         # Repositorios (Redis)
  routes/               # Blueprints Flask (bots y webhook)
  services/             # Lógica de negocio (OpenAI, Twilio, Horizon, conversaciones)
  utils/                # Utilidades de validación
wsgi.py                 # Punto de entrada para WSGI/Gunicorn
requirements.txt        # Dependencias del proyecto
Dockerfile              # Imagen de la aplicación Flask
docker-compose.yml      # Orquestación del servicio + Redis
.env.example            # Variables de entorno de referencia
```

## Requisitos previos

- Docker y Docker Compose
- Python 3.11+ (solo si deseas ejecutar sin contenedores)

## Configuración de variables de entorno

Crea un archivo `.env` en la raíz basado en `.env.example` y completa las credenciales necesarias:

- **OpenAI**: `OPENAI_API_KEY`
- **Twilio**: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- **Horizon**: `HORIZON_BASE_URL`, `HORIZON_API_KEY`
- **Base de datos Horizon (opcional para carga dinámica)**: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` o bien `DATABASE_URL` completa.

## Puesta en marcha con Docker

```bash
docker-compose up --build
```

El servicio Flask estará disponible por defecto en `http://localhost:8001` (puedes cambiarlo con `HOST_WEB_PORT`). Redis se expone por defecto en el puerto definido por `HOST_REDIS_PORT` (6380 en este ejemplo) para evitar conflictos con instalaciones locales (`localhost:6380`).

## Ejecución local sin Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
export FLASK_APP=wsgi.py
flask --app wsgi.py run --host 0.0.0.0 --port 8000
```

## Endpoints principales

- `GET /bots/` — listar bots registrados.
- `POST /bots/` — crear un bot (puede crear asistentes en OpenAI si se envía `assistant_config`).
- `GET /bots/<bot_id>` — obtener un bot específico.
- `PUT /bots/<bot_id>` — actualizar metadatos de un bot.
- `DELETE /bots/<bot_id>` — borrar un bot.
- `POST /bots/<bot_id>/refresh` — fuerza la recarga del bot desde la base de datos Horizon hacia Redis.
- `POST /webhook/whatsapp` — webhook consumido por Twilio para mensajes entrantes.

Todas las respuestas son JSON salvo el webhook, que devuelve TwiML (XML) para Twilio.

Health checks:
- `GET /health` incluye campo `db` indicando si la conexión a base responde.
- `GET /health/db` valida específicamente el motor SQL.

## Pruebas

```bash
pytest
```

Las pruebas unitarias utilizan `fakeredis` para simular Redis y stubs para OpenAI/Twilio, por lo que no se requieren credenciales reales.

## 👥 Gestión Multi-Cliente

### 🚀 **Sistema Multi-Cliente**
Este sistema está diseñado para manejar múltiples clientes WhatsApp desde un solo servidor:

- **Un servidor**: Maneja todos los clientes
- **Múltiples números**: Cada cliente tiene su número independiente  
- **Asistentes únicos**: Cada cliente tiene su propio asistente de OpenAI
- **Sin conflictos**: Los mensajes se enrutan automáticamente al bot correcto

### 📋 **Scripts de Gestión:**

#### 🔧 **Servidor:**
- `cleanup-server.sh`: Limpia logs y archivos temporales
- `fix-server-installation.sh`: Repara problemas de instalación
- `install-server-fixed.sh`: Instalación optimizada del servidor
- `install-server-lightweight.sh`: Instalación minimalista

#### 👥 **Multi-Cliente:**
- `crear-cliente.sh`: Script automatizado para crear nuevos clientes
- `monitor-clientes.sh`: Herramienta de monitoreo y gestión de múltiples clientes

#### 📚 **Documentación:**
- `CLIENTE_NUEVO.md`: Guía completa para agregar nuevos clientes
- `ARQUITECTURA_MULTICLIENTE.md`: Documentación técnica del sistema multi-cliente
- `DEPLOYMENT.md`: Proceso de despliegue en producción
- `GIT_SETUP.md`: Configuración del repositorio Git

### 🏗️ **Agregar Nuevo Cliente**

Para agregar un nuevo cliente, simplemente ejecuta:

```bash
./crear-cliente.sh
```

El script te guiará a través del proceso:
1. Configurar número en Twilio
2. Crear asistente en OpenAI
3. Crear bot en el sistema
4. Probar funcionamiento
5. Documentar configuración

### 📊 **Monitoreo Multi-Cliente**

Para monitorear todos los clientes:

```bash
./monitor-clientes.sh
```

Opciones disponibles:
- Ver todos los clientes activos
- Monitorear cliente específico  
- Logs en tiempo real
- Buscar en logs
- Estadísticas de uso
- Probar bots
- Crear backups
- Estado del servidor

## Próximos pasos sugeridos

- Añadir autenticación y autorización para los endpoints de administración.
- Persistir configuración de bots en una base de datos permanente.
- Implementar manejadores de errores y trazabilidad añadida para integraciones externas.
- Extender el soporte de herramientas para Horizon con catálogos dinámicos.
- Añadir endpoint para forzar sincronización de un bot desde la base de datos.
