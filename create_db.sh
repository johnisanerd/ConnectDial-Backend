#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# ==============================================================================
# CONFIGURATION (Matches settings.py)
# ==============================================================================
DB_NAME="connectdial_db"
DB_USER="gilly"

# Prompt securely for the password so it isn't hardcoded in plain text
echo -n "Enter password for PostgreSQL user '$DB_USER': "
read -s DB_PASSWORD
echo "" # Clean newline after hidden password input

if [ -z "$DB_PASSWORD" ]; then
    echo "❌ Error: Password cannot be empty."
    exit 1
fi

# ==============================================================================
# DATABASE CREATION
# ==============================================================================
echo "🌀 Connecting to PostgreSQL as 'postgres' user..."

# 1. Create the user if they don't already exist
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 || \
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
echo "✅ PostgreSQL user '$DB_USER' verified/created."

# 2. Create the database if it doesn't already exist
sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME" || \
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
echo "✅ Database '$DB_NAME' verified/created."

# 3. Grant privileges & ensure modern schema access (PostgreSQL 15+)
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
sudo -u postgres psql -d "$DB_NAME" -c "GRANT ALL ON SCHEMA public TO $DB_USER;"
echo "✅ Granted permissions to '$DB_USER' on database '$DB_NAME'."

echo -e "\n🎉 PostgreSQL setup completed successfully!"