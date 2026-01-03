# Supabase Setup Instructions

## Step 1: Create Supabase Account & Project

1. Go to https://supabase.com
2. Sign up / Log in
3. Click "New Project"
4. Choose a name (e.g., "fitness-tracker")
5. Set a database password (save this!)
6. Select a region close to you
7. Click "Create new project" (takes ~2 min)

## Step 2: Get Connection String

1. In your Supabase project, go to **Settings** (gear icon)
2. Click **Database** in the left sidebar
3. Scroll to **Connection string** section
4. Select **URI** tab
5. Copy the connection string (looks like):
   ```
   postgresql://postgres.[project-id]:[password]@aws-0-us-west-1.pooler.supabase.com:6543/postgres
   ```

## Step 3: Update Railway

Run this command (replace YOUR_CONNECTION_STRING):

```bash
cd /Users/nickchua/Desktop/AI/claude-quickstarts/autonomous-coding/generations/fitness-app/backend
railway variables --set "DATABASE_URL=YOUR_CONNECTION_STRING"
```

Or run the setup script:
```bash
./setup_supabase.sh
```

## Step 4: Run Migrations & Seed Data

```bash
# The app will auto-create tables on first run
# To seed exercises and user data:
railway run python seed_exercises.py
railway run python seed_user_data.py
```

## Step 5: Test

```bash
curl https://backend-production-e316.up.railway.app/
```

Should return: `{"message":"Fitness Tracker API","version":"0.1.0","status":"running"}`
