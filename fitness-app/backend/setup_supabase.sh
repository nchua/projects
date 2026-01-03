#!/bin/bash
# Setup script for Supabase + Railway

echo "==================================="
echo "Supabase + Railway Setup"
echo "==================================="
echo ""
echo "Paste your Supabase DATABASE_URL connection string:"
echo "(Get it from: Supabase Dashboard > Settings > Database > Connection string > URI)"
echo ""
read -p "DATABASE_URL: " DATABASE_URL

if [ -z "$DATABASE_URL" ]; then
    echo "Error: No DATABASE_URL provided"
    exit 1
fi

echo ""
echo "Setting DATABASE_URL on Railway..."
railway variables --set "DATABASE_URL=$DATABASE_URL"

echo ""
echo "Triggering redeploy..."
railway redeploy

echo ""
echo "==================================="
echo "Setup complete!"
echo "==================================="
echo ""
echo "Your API is at: https://backend-production-e316.up.railway.app"
echo ""
echo "Next steps:"
echo "1. Wait ~2 min for deploy to complete"
echo "2. Test: curl https://backend-production-e316.up.railway.app/"
echo "3. Seed data: railway run python seed_exercises.py"
echo ""
