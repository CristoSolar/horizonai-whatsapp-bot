#!/bin/bash

# Fix Server Installation Script for HorizonAI WhatsApp Bot
# This script fixes common issues after installation

set -e

APP_NAME="horizonai-whatsapp-bot"
APP_DIR="$HOME/horizonai-whatsapp-bot"
SERVICE_NAME="horizonai-whatsapp-bot"

echo "🔧 Fixing HorizonAI WhatsApp Bot installation..."

# Ensure we're in the right directory
cd "$APP_DIR"

echo "📍 Current directory: $(pwd)"
echo "📂 Directory contents:"
ls -la

# Activate virtual environment
echo "🐍 Activating virtual environment..."
source venv/bin/activate

# Verify Python dependencies are installed
echo "📦 Checking Python dependencies..."
pip list | grep -E "(flask|openai|twilio|redis)" || echo "Some dependencies might be missing"

# Create or recreate the systemd service file
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

# Check if wsgi.py exists
if [ ! -f "wsgi.py" ]; then
    echo "⚠️  Creating missing wsgi.py file..."
    cat > wsgi.py << 'EOF'
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=False)
EOF
fi

# Ensure .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Creating .env file from template..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
    else
        cat > .env << 'EOF'
# Flask configuration
FLASK_ENV=production
SECRET_KEY=your-secret-key-here
PORT=5000

# Redis
REDIS_URL=redis://localhost:6379/0

# OpenAI
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_DEFAULT_MODEL=gpt-4o-mini
OPENAI_DEFAULT_INSTRUCTIONS=You are a helpful WhatsApp assistant.

# Twilio
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_WHATSAPP_FROM=whatsapp:+your-twilio-number

# Horizon API
HORIZON_BASE_URL=https://api.horizon.local
HORIZON_API_KEY=your-horizon-api-key
EOF
    fi
fi

# Test the application
echo "🧪 Testing application..."
python -c "from app import create_app; app = create_app(); print('✅ App creation successful')" || echo "❌ App creation failed"

# Reload systemd and start services
echo "🚀 Starting services..."
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl start ${SERVICE_NAME}

# Check service status
echo "📊 Service status:"
sudo systemctl status ${SERVICE_NAME} --no-pager -l

# Update Nginx configuration if needed
echo "🌐 Checking Nginx configuration..."
if [ -f "/etc/nginx/sites-available/${SERVICE_NAME}" ]; then
    echo "✅ Nginx configuration exists"
else
    echo "🔧 Creating Nginx configuration..."
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

    # Enable the site
    sudo ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
fi

# Test and reload Nginx
echo "🔄 Reloading Nginx..."
sudo nginx -t && sudo systemctl reload nginx

echo ""
echo "✅ Installation fix completed!"
echo ""
echo "📊 Service statuses:"
echo "🔴 Redis: $(sudo systemctl is-active redis-server)"
echo "🔵 Nginx: $(sudo systemctl is-active nginx)"
echo "🟢 App: $(sudo systemctl is-active ${SERVICE_NAME})"
echo ""
echo "🧪 Test commands:"
echo "curl http://localhost/health"
echo "sudo journalctl -u ${SERVICE_NAME} -f"
echo ""
echo "📝 Next steps:"
echo "1. Edit .env file with your credentials: nano .env"
echo "2. Restart the service: sudo systemctl restart ${SERVICE_NAME}"
echo "3. Test the webhook endpoint"