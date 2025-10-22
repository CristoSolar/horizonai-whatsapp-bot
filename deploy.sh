#!/bin/bash

# HorizonAI WhatsApp Bot - Git-based Deployment Script
# Run this script to deploy updates to your server using Git

set -e

SERVER_USER="your-server-user"
SERVER_HOST="your-server-ip"
SERVER_PATH="\$HOME/horizonai-whatsapp-bot"
GIT_REPO="https://github.com/CristoSolar/horizonai-whatsapp-bot.git"  # Update with your repo URL

echo "🚀 Deploying HorizonAI WhatsApp Bot to $SERVER_HOST..."

# Push latest changes to Git repository
echo "� Pushing latest changes to Git repository..."
git add .
git status
read -p "Do you want to commit and push changes? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "Enter commit message: " commit_message
    git commit -m "$commit_message" || echo "No changes to commit"
    git push origin main 2>/dev/null || git push origin master 2>/dev/null || echo "Please push manually"
fi

echo "🔧 Deploying to server..."
ssh "$SERVER_USER@$SERVER_HOST" << EOF
    set -e
    cd $SERVER_PATH
    
    # Backup current version
    if [ -d "backup" ]; then
        rm -rf backup.old
        mv backup backup.old
    fi
    mkdir -p backup
    cp -r app requirements.txt wsgi.py backup/ 2>/dev/null || true
    
    # Pull latest changes from Git
    echo "📥 Pulling latest changes from Git..."
    git fetch origin
    git reset --hard origin/main 2>/dev/null || git reset --hard origin/master 2>/dev/null
    
    # Update dependencies
    echo "🔧 Updating dependencies..."
    source venv/bin/activate
    pip install -r requirements.txt
    
    # Restart service
    echo "🔄 Restarting service..."
    sudo systemctl restart horizonai-bots
    
    # Check status
    sleep 3
    sudo systemctl status horizonai-bots --no-pager
    
    echo "✅ Deployment complete!"
    echo "🔍 Check logs with: sudo journalctl -u horizonai-bots -f"
EOF

echo "🎉 Deployment finished successfully!"
echo "🌐 Your bot should be available at: https://whatsapp.yourdomain.com"