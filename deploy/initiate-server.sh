#!/bin/bash

set -e

echo "=== Updating system packages ==="
sudo apt update

echo "=== Installing Nginx ==="
sudo apt install -y nginx

echo "=== Installing Python 3, pip, and venv ==="
sudo apt install -y python3 python3-venv python3-pip

echo "=== Creating virtual environment for Django ==="
python3 -m venv ~/vitamova-venv

echo "=== Activating virtual environment ==="
source ~/vitamova-venv/bin/activate

echo "=== Installing Python dependencies ==="
pip install -r ~/vitamova/deploy/requirements.txt

echo "=== Applying Django migrations ==="
cd ~/vitamova/webapp
python manage.py migrate
cd ~/vitamova

echo "=== Copying Nginx configuration ==="
if [ ! -f /home/ubuntu/vitamova/webapp/nginx/sites-available.conf ]; then
    echo "❌ ERROR: /home/ubuntu/vitamova/webapp/nginx/sites-available.conf not found!"
    exit 1
fi

sudo cp /home/ubuntu/vitamova/deploy/nginx.conf /etc/nginx/sites-available/default

echo "=== Testing Nginx configuration ==="
if ! sudo nginx -t; then
    echo "❌ ERROR: Nginx configuration test failed!"
    exit 1
fi

echo "=== Reloading Nginx ==="
sudo systemctl reload nginx

echo "=== Making Static files accessible ==="
sudo chmod o+x /home
sudo chmod o+x /home/ubuntu
sudo chmod o+x /home/ubuntu/vitamova
sudo chmod o+x /home/ubuntu/vitamova/webapp
sudo chmod o+x /home/ubuntu/vitamova/webapp/static

echo "✅ Setup complete!"
echo "🧪 Django virtual environment located at: ~/vesper-venv"