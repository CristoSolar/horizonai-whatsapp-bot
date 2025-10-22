#!/bin/bash

# 📦 Script para commitear documentación multi-cliente

# Colores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}📦 Commiteando documentación y scripts multi-cliente...${NC}"

# Verificar si estamos en un repositorio Git
if [ ! -d ".git" ]; then
    echo -e "${YELLOW}⚠️  No es un repositorio Git. Inicializando...${NC}"
    git init
    git remote add origin https://github.com/tu-usuario/HorizonaiBots.git
fi

# Agregar archivos nuevos y modificados
echo -e "${BLUE}📋 Agregando archivos...${NC}"
git add .

# Verificar qué archivos se van a commitear
echo -e "${BLUE}📄 Archivos a commitear:${NC}"
git status --porcelain

# Crear commit con mensaje descriptivo
echo -e "${BLUE}💾 Creando commit...${NC}"
git commit -m "📚 Documentación y herramientas multi-cliente

✨ Nuevos archivos:
- CLIENTE_NUEVO.md: Guía completa para agregar nuevos clientes
- ARQUITECTURA_MULTICLIENTE.md: Documentación técnica del sistema
- crear-cliente.sh: Script automatizado para crear clientes
- monitor-clientes.sh: Herramienta de monitoreo multi-cliente

🔄 Archivos actualizados:
- README.md: Documentación de gestión multi-cliente
- Documentación mejorada con flujos y arquitectura

🎯 Funcionalidades:
- Sistema multi-cliente con un solo servidor
- Scripts de automatización para crear clientes
- Herramientas de monitoreo y gestión
- Documentación completa del proceso
- Arquitectura escalable para múltiples clientes

💡 El sistema ahora puede manejar múltiples clientes WhatsApp
   con números independientes y asistentes únicos desde
   un solo servidor, sin conflictos ni interferencias."

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Commit creado exitosamente${NC}"
    
    # Preguntar si hacer push
    echo -e "${YELLOW}🚀 ¿Deseas hacer push al repositorio remoto? (y/n):${NC} "
    read -r push_confirm
    
    if [[ $push_confirm =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}🚀 Haciendo push...${NC}"
        git push origin main
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ Push completado exitosamente${NC}"
            echo -e "${GREEN}🎉 Documentación multi-cliente actualizada en GitHub${NC}"
        else
            echo -e "${YELLOW}⚠️  Error en push. Verifica la configuración del repositorio remoto${NC}"
        fi
    else
        echo -e "${YELLOW}📋 Commit local creado. Puedes hacer push más tarde con: git push origin main${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Error al crear commit${NC}"
fi

echo -e "${BLUE}📊 Estado final del repositorio:${NC}"
git log --oneline -5

echo ""
echo -e "${GREEN}🎯 RESUMEN DE CAMBIOS:${NC}"
echo -e "${GREEN}✅${NC} Documentación multi-cliente completa"
echo -e "${GREEN}✅${NC} Scripts de automatización listos"
echo -e "${GREEN}✅${NC} Herramientas de monitoreo implementadas"
echo -e "${GREEN}✅${NC} Arquitectura escalable documentada"
echo ""
echo -e "${BLUE}📚 Archivos principales:${NC}"
echo -e "   📄 CLIENTE_NUEVO.md - Guía paso a paso"
echo -e "   📄 ARQUITECTURA_MULTICLIENTE.md - Documentación técnica"
echo -e "   🔧 crear-cliente.sh - Automatización de creación"
echo -e "   📊 monitor-clientes.sh - Herramientas de gestión"
echo ""
echo -e "${GREEN}🚀 El sistema está listo para manejar múltiples clientes!${NC}"