#!/bin/bash

# Server Disk Cleanup Script for HorizonAI WhatsApp Bot Installation
# This script cleans up common space-consuming files on Ubuntu servers

set -e

echo "🧹 Starting server disk cleanup..."

# Check current disk usage
echo "📊 Current disk usage:"
df -h

echo ""
echo "🗑️  Cleaning up package cache and temporary files..."

# Clean package cache
sudo apt-get clean
sudo apt-get autoclean
sudo apt-get autoremove -y

# Clean package lists (can be regenerated)
sudo rm -rf /var/lib/apt/lists/*

# Clean temporary files
sudo rm -rf /tmp/*
sudo rm -rf /var/tmp/*

# Clean old log files
sudo journalctl --vacuum-time=7d
sudo find /var/log -name "*.log" -type f -mtime +7 -delete 2>/dev/null || true
sudo find /var/log -name "*.gz" -type f -delete 2>/dev/null || true

# Clean Docker if installed
if command -v docker &> /dev/null; then
    echo "🐳 Cleaning Docker resources..."
    sudo docker system prune -af --volumes 2>/dev/null || true
fi

# Clean snap cache if snapd is installed
if command -v snap &> /dev/null; then
    echo "📦 Cleaning snap cache..."
    sudo rm -rf /var/lib/snapd/cache/* 2>/dev/null || true
fi

# Clean kernel packages (keep only current and one previous)
echo "🔧 Cleaning old kernel packages..."
sudo apt-get autoremove --purge -y

# Clean pip cache if exists
if command -v pip3 &> /dev/null; then
    echo "🐍 Cleaning pip cache..."
    pip3 cache purge 2>/dev/null || true
fi

# Clean npm cache if exists
if command -v npm &> /dev/null; then
    echo "📦 Cleaning npm cache..."
    npm cache clean --force 2>/dev/null || true
fi

echo ""
echo "✅ Cleanup completed!"
echo "📊 Disk usage after cleanup:"
df -h

echo ""
echo "💡 If you still need more space, consider:"
echo "   - Removing unused applications with: sudo apt-get remove <package>"
echo "   - Checking large files with: sudo du -sh /* | sort -hr | head -10"
echo "   - Expanding disk space in your cloud provider if possible"

echo ""
echo "🚀 Ready to retry the installation!"
echo "Run: wget https://raw.githubusercontent.com/CristoSolar/horizonai-whatsapp-bot/main/install-server-fixed.sh && chmod +x install-server-fixed.sh && ./install-server-fixed.sh"