#!/bin/bash

# HorizonAI WhatsApp Bot - Fix Dependencies and Install
# Run this script to fix broken dependencies and install the bot

set -e

echo "🔧 Fixing broken dependencies first..."

# Fix broken dependencies
sudo apt --fix-broken install -y

# Remove problematic kernel headers if they continue to cause issues
sudo apt remove --purge linux-headers-6.14.0-1014-aws -y 2>/dev/null || true

# Update package lists
sudo apt update

# Upgrade existing packages
sudo apt upgrade -y

echo "🚀 Installing HorizonAI WhatsApp Bot..."

# Configuration
GIT_REPO="https://github.com/CristoSolar/horizonai-whatsapp-bot.git"
APP_DIR="$HOME/horizonai-whatsapp-bot"

# Install required packages
sudo apt install -y python3 python3-pip python3-venv nginx redis-server certbot python3-certbot-nginx git

# Create application directory and clone repository
mkdir -p $APP_DIR

echo "📥 Cloning repository from Git..."
git clone $GIT_REPO $APP_DIR
cd $APP_DIR

# Set up Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Configure environment
cp .env.production .env
echo "⚙️  Edit $APP_DIR/.env with your actual credentials"

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Configure Nginx
sudo cp nginx.conf /etc/nginx/sites-available/horizonai-bots
echo "🌐 Edit /etc/nginx/sites-available/horizonai-bots and update your domain"
echo "   Then run: sudo ln -s /etc/nginx/sites-available/horizonai-bots /etc/nginx/sites-enabled/"

# Test Nginx configuration
echo "🔧 After editing nginx config, test with: sudo nginx -t"

# SSL Certificate (after DNS is configured)
echo "🔒 Once DNS points to this server, run:"
echo "   sudo certbot --nginx -d whatsapp.yourdomain.com"

# Create systemd service
sudo tee /etc/systemd/system/horizonai-bots.service > /dev/null <<EOF
[Unit]
Description=HorizonAI WhatsApp Bot
After=network.target

[Service]
Type=exec
User=$USER
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 2 --timeout 60 wsgi:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable horizonai-bots

echo "✅ Installation complete!"
echo ""
echo "📋 Next steps:"
echo "1. Edit $APP_DIR/.env with your credentials"
echo "2. Edit /etc/nginx/sites-available/horizonai-bots with your domain"
echo "3. Enable nginx site: sudo ln -s /etc/nginx/sites-available/horizonai-bots /etc/nginx/sites-enabled/"
echo "4. Test nginx: sudo nginx -t"
echo "5. Restart nginx: sudo systemctl restart nginx"
echo "6. Configure DNS: whatsapp.yourdomain.com -> your server IP"
echo "7. Get SSL certificate: sudo certbot --nginx -d whatsapp.yourdomain.com"
echo "8. Start the service: sudo systemctl start horizonai-bots"
echo "9. Check logs: sudo journalctl -u horizonai-bots -f"