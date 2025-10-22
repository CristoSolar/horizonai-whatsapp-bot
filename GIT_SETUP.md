# 🚀 Configuración del Repositorio Git

## 📋 Pasos para Crear el Repositorio en GitHub

### 1. Crear repositorio en GitHub
1. Ve a [GitHub](https://github.com) e inicia sesión
2. Haz clic en "New repository" (botón verde)
3. Nombre sugerido: `horizonai-whatsapp-bot`
4. Descripción: `WhatsApp Bot Service with OpenAI, Twilio, and Horizon integration`
5. Marca como **Private** (por seguridad)
6. **NO** marques "Add a README file" (ya tenemos uno)
7. Haz clic en "Create repository"

### 2. Conectar repositorio local con GitHub
```bash
# En tu terminal, desde el directorio del proyecto:
git branch -M main
git remote add origin https://github.com/TU-USUARIO/horizonai-whatsapp-bot.git
git push -u origin main
```

### 3. Actualizar scripts con tu URL
Después de crear el repositorio, actualiza estos archivos:

**deploy.sh** (línea 8):
```bash
GIT_REPO="https://github.com/TU-USUARIO/horizonai-whatsapp-bot.git"
```

**install-server.sh** (línea 8):
```bash
GIT_REPO="https://github.com/TU-USUARIO/horizonai-whatsapp-bot.git"
```

### 4. Commit y push de los cambios
```bash
git add .
git commit -m "Update deployment scripts with correct repository URL"
git push origin main
```

## 🔒 Configuración para Repositorio Privado

Si tu repositorio es privado, necesitarás configurar acceso en el servidor:

### Opción 1: Personal Access Token (Recomendado)
1. Ve a GitHub → Settings → Developer settings → Personal access tokens
2. Genera un token con permisos de "repo"
3. En el servidor, clona usando:
```bash
git clone https://TOKEN@github.com/TU-USUARIO/horizonai-whatsapp-bot.git
```

### Opción 2: SSH Keys
1. Genera SSH key en el servidor:
```bash
ssh-keygen -t ed25519 -C "tu-email@ejemplo.com"
```
2. Agrega la clave pública a GitHub: Settings → SSH and GPG keys
3. Clona usando SSH:
```bash
git clone git@github.com:TU-USUARIO/horizonai-whatsapp-bot.git
```

## 🛠️ Comandos Útiles de Git

```bash
# Ver estado del repositorio
git status

# Agregar cambios
git add .

# Commit con mensaje
git commit -m "Descripción de los cambios"

# Push al repositorio remoto
git push origin main

# Pull cambios del repositorio remoto
git pull origin main

# Ver historial de commits
git log --oneline

# Ver ramas
git branch -a
```

## 📝 Flujo de Desarrollo Recomendado

1. **Desarrollo local**: Hacer cambios y probar con Docker
2. **Commit**: `git add . && git commit -m "Descripción"`
3. **Push**: `git push origin main`
4. **Deploy**: `./deploy.sh` (script automatizado)

## 🔄 Comandos de Despliegue

Una vez configurado el repositorio:

```bash
# Despliegue completo desde cero (primera vez)
./install-server.sh

# Despliegues posteriores (actualizaciones)
./deploy.sh
```