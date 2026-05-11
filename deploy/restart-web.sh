#!/bin/bash

set -e

export PYTHONPATH="$HOME/vitamova:$PYTHONPATH"

echo "=== Restarting Vitamova web service ==="

# Step 1: Kill Gunicorn if it's running
echo "🔧 Stopping Gunicorn if running..."
if pgrep gunicorn > /dev/null; then
  pkill gunicorn
  echo "✅ Gunicorn stopped."
else
  echo "ℹ️ Gunicorn was not running."
fi

# Step 2: Remove old project
if [ -d vitamova ]; then
  echo "🗑️ Removing old vitamova directory..."
  sudo rm -rf vitamova
  echo "✅ Old vitamova directory removed."
fi

# Step 3: Clone the latest code
echo "⬇️ Cloning latest vitamova repo..."
if git clone -b dev https://github.com/vitamova/vitamova.git; then
  echo "✅ Git clone successful."
else
  echo "❌ ERROR: Failed to clone repo."
  exit 1
fi

# Step 4: Fix script permissions
echo "🔐 Setting script permissions..."
chmod 755 ~/vitamova/deploy/initiate-server.sh ~/vitamova/deploy/start-services.sh ~/vitamova/deploy/restart-web.sh
echo "✅ Permissions set."

# Step 5: Install Python dependencies
echo "📦 Installing Python dependencies..."
source ~/vitamova-venv/bin/activate
pip install -r ~/vitamova/deploy/requirements.txt
deactivate
echo "✅ Python dependencies installed."

# Step 6: Apply the django migrations
echo "🔄 Applying Django migrations..."
source ~/vitamova-venv/bin/activate
export PYTHONPATH="$HOME/vitamova:$PYTHONPATH"
cd ~/vitamova/webapp
python3 manage.py migrate
if [ $? -ne 0 ]; then
  echo "❌ ERROR: Django migrations failed."
  exit 1
fi
deactivate
cd ~/vitamova
echo "✅ Migrations applied successfully."

# Step 7: Start services
echo "🚀 Starting Vitamova services..."
export PYTHONPATH="$HOME/vitamova:$PYTHONPATH"
if bash ~/vitamova/deploy/start-services.sh; then
  echo "✅ Vitamova services started successfully."
else
  echo "❌ ERROR: Failed to start Vitamova services."
  exit 1
fi

echo "🎉 Restart complete."