#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

PROJECT_DIR="/var/www/dtac.io"
CODE_DIR="$PROJECT_DIR/source"
VENV_DIR="$PROJECT_DIR/venv"
GIT_BRANCH="master" # Or your deployment branch
SERVICE_NAME="gunicorn-dtac.service"

echo "Starting deployment for dtac.io..."

# Navigate to code directory
cd $CODE_DIR

# Pull latest changes
echo "Pulling latest code from branch '$GIT_BRANCH'..."
# Ensure you're on the right branch and reset any local changes (optional, use with caution)
# git checkout $GIT_BRANCH
# git fetch origin
# git reset --hard origin/$GIT_BRANCH
# Safer: Just pull assuming clean working dir
git checkout $GIT_BRANCH # Ensure correct branch
git pull origin $GIT_BRANCH

# Activate virtual environment
echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# Install/update dependencies
echo "Installing/updating dependencies..."
pip install -r requirements.txt

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Deactivate (optional here, script ends anyway)
# deactivate

# Restart Gunicorn service
echo "Restarting application server ($SERVICE_NAME)..."
sudo systemctl restart $SERVICE_NAME
# Or: sudo systemctl reload $SERVICE_NAME

echo "Deployment finished successfully!"

exit 0
