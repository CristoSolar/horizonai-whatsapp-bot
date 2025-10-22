#!/bin/bash

# Lightweight Installation Script for HorizonAI WhatsApp Bot (No Docker)
# For servers with limited disk space

set -e

APP_NAME="horizonai-whatsapp-bot"
APP_DIR="$HOME/horizonai-whatsapp-bot"
REPO_URL="https://github.com/CristoSolar/horizonai-whatsapp-bot.git"
SERVICE_NAME="horizonai-whatsapp-bot"

echo "🚀 Installing $APP_NAME (Lightweight - No Docker)..."

# Check disk space
echo "📊 Current disk usage:"
df -h

# Update package list only
echo "📦 Updating package list..."
sudo apt-get update

# Install only essential packages
echo "🔧 Installing essential packages..."
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    nginx \
    redis-server \
    curl \
    nano

# Clone repository
echo "📥 Cloning repository..."
if [ -d "$APP_DIR" ]; then
    echo "Directory exists, pulling latest changes..."
    cd "$APP_DIR"
    git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# Create virtual environment
echo "🐍 Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy environment template
echo "⚙️  Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "🔧 Please edit .env file with your credentials"
fi

# Create systemd service
echo "🔧 Creating systemd service..."
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=HorizonAI WhatsApp Bot
After=network.target redis.service

[Service]
Type=exec
User=ubuntu
Group=ubuntu
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/gunicorn --bind 127.0.0.1:5000 wsgi:app --workers 2 --timeout 120
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Start Redis
echo "🟥 Starting Redis..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Create Nginx configuration
echo "🌐 Configuring Nginx..."
sudo tee /etc/nginx/sites-available/${SERVICE_NAME} > /dev/null <<EOF
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    location /webhook/ {
        proxy_pass http://127.0.0.1:5000/webhook/;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable Nginx site
sudo ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

# Enable and start service
echo "🚀 Starting application..."
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl start ${SERVICE_NAME}

echo ""
echo "✅ Installation completed!"
echo ""
echo "📊 Final disk usage:"
df -h
echo ""
echo "🔧 Next steps:"
echo "1. Edit environment file: nano $APP_DIR/.env"
echo "2. Check service status: sudo systemctl status ${SERVICE_NAME}"
echo "3. View logs: sudo journalctl -u ${SERVICE_NAME} -f"
echo "4. Test webhook: curl http://localhost/health"
echo ""
echo "🌐 Your bot is running on port 80"
echo "📝 Remember to configure your domain and SSL certificates"