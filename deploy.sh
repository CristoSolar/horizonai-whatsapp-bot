#!/bin/bash

# HorizonAI WhatsApp Bot - Deployment Script
# Run this script to deploy updates to your server

set -e

SERVER_USER="your-server-user"
SERVER_HOST="your-server-ip"
SERVER_PATH="/opt/horizonai-bots"
PROJECT_PATH="/Users/cristobalsolar/Desktop/Proyectos_Pega/HorizonaiBots"

echo "🚀 Deploying HorizonAI WhatsApp Bot to $SERVER_HOST..."

# Create deployment package
echo "📦 Creating deployment package..."
cd "$PROJECT_PATH"

# Create temporary deployment directory
TEMP_DIR=$(mktemp -d)
cp -r . "$TEMP_DIR/"

# Remove unnecessary files
cd "$TEMP_DIR"
rm -rf .git __pycache__ app/__pycache__ app/*/__pycache__ tests/__pycache__ .env .DS_Store
rm -f install-server.sh deploy.sh

# Create archive
tar -czf horizonai-bots.tar.gz *

echo "📤 Uploading to server..."
scp horizonai-bots.tar.gz "$SERVER_USER@$SERVER_HOST:/tmp/"

echo "🔧 Installing on server..."
ssh "$SERVER_USER@$SERVER_HOST" << 'EOF'
    set -e
    cd /opt/horizonai-bots
    
    # Backup current version
    if [ -d "backup" ]; then
        rm -rf backup.old
        mv backup backup.old
    fi
    mkdir -p backup
    cp -r app requirements.txt wsgi.py backup/ 2>/dev/null || true
    
    # Extract new version
    tar -xzf /tmp/horizonai-bots.tar.gz
    rm /tmp/horizonai-bots.tar.gz
    
    # Update dependencies
    source venv/bin/activate
    pip install -r requirements.txt
    
    # Restart service
    sudo systemctl restart horizonai-bots
    
    # Check status
    sleep 3
    sudo systemctl status horizonai-bots --no-pager
    
    echo "✅ Deployment complete!"
    echo "🔍 Check logs with: sudo journalctl -u horizonai-bots -f"
EOF

# Cleanup
rm -rf "$TEMP_DIR"

echo "🎉 Deployment finished successfully!"
echo "🌐 Your bot should be available at: https://whatsapp.yourdomain.com"