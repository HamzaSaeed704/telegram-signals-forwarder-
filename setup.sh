#!/bin/bash

# Telegram Bot Setup Script for Hostinger VPS
# Run this script on your Hostinger server

set -e

echo "🚀 Setting up Telegram Bot on Hostinger..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR"
USER=$(whoami)
SERVICE_NAME="telegram-bot"

echo -e "${GREEN}✓${NC} Project directory: $PROJECT_DIR"
echo -e "${GREEN}✓${NC} User: $USER"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗${NC} Python 3 is not installed. Installing..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-venv
else
    echo -e "${GREEN}✓${NC} Python 3 is installed: $(python3 --version)"
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}✗${NC} pip3 is not installed. Installing..."
    sudo apt-get install -y python3-pip
else
    echo -e "${GREEN}✓${NC} pip3 is installed: $(pip3 --version)"
fi

# Install system dependencies for Pillow
echo -e "${YELLOW}→${NC} Installing system dependencies for image processing..."
sudo apt-get update
sudo apt-get install -y libjpeg-dev zlib1g-dev libtiff-dev libfreetype6-dev liblcms2-dev libwebp-dev libharfbuzz-dev libfribidi-dev libxcb1-dev

# Create virtual environment
if [ ! -d "venv" ] || [ ! -f "venv/bin/activate" ]; then
    echo -e "${YELLOW}→${NC} Creating virtual environment..."
    # Remove incomplete venv if it exists
    if [ -d "venv" ]; then
        rm -rf venv
    fi
    python3 -m venv venv
else
    echo -e "${GREEN}✓${NC} Virtual environment already exists"
fi

# Activate virtual environment and install dependencies
echo -e "${YELLOW}→${NC} Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Create downloads directory
mkdir -p downloads
echo -e "${GREEN}✓${NC} Created downloads directory"

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠${NC} .env file not found. Creating from template..."
    if [ -f "env.template" ]; then
        cp env.template .env
        echo -e "${RED}⚠${NC} IMPORTANT: Please edit .env file with your actual credentials!"
        echo -e "${YELLOW}→${NC} Run: nano .env"
    elif [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${RED}⚠${NC} IMPORTANT: Please edit .env file with your actual credentials!"
        echo -e "${YELLOW}→${NC} Run: nano .env"
    else
        echo -e "${RED}✗${NC} No template found. Please create .env manually."
    fi
else
    echo -e "${GREEN}✓${NC} .env file exists"
fi

# Update systemd service file with actual paths
echo -e "${YELLOW}→${NC} Configuring systemd service..."
sed -i "s|YOUR_USERNAME|$USER|g" telegram-bot.service
sed -i "s|/home/YOUR_USERNAME/telegram-bot|$PROJECT_DIR|g" telegram-bot.service

# Copy service file to systemd directory
sudo cp telegram-bot.service /etc/systemd/system/$SERVICE_NAME.service

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME.service

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your credentials:"
echo "   nano .env"
echo ""
echo "2. Start the service:"
echo "   sudo systemctl start $SERVICE_NAME"
echo ""
echo "3. Check service status:"
echo "   sudo systemctl status $SERVICE_NAME"
echo ""
echo "4. View logs:"
echo "   sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "5. Stop the service:"
echo "   sudo systemctl stop $SERVICE_NAME"
echo ""
echo -e "${YELLOW}Note:${NC} On first run, you'll need to authenticate with Telegram."
echo "Check the logs to see the authentication prompt."

