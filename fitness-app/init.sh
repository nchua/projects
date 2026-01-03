#!/bin/bash

# init.sh - Setup and run fitness-app development environment
# This script initializes both the iOS Swift frontend and Python FastAPI backend

set -e  # Exit on error

echo "🏋️  Fitness App - Development Environment Setup"
echo "================================================"
echo ""

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print status messages
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# ============================================================================
# PREREQUISITES CHECK
# ============================================================================

echo "Checking prerequisites..."
echo ""

# Check for Python 3.11+
if command_exists python3; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [ "$(echo "$PYTHON_VERSION >= 3.11" | bc 2>/dev/null || echo 0)" -eq 1 ]; then
        print_status "Python $PYTHON_VERSION found"
    else
        print_error "Python 3.11+ required, found $PYTHON_VERSION"
        echo "Install Python 3.11+ from https://www.python.org/downloads/"
        exit 1
    fi
else
    print_error "Python 3 not found"
    echo "Install Python 3.11+ from https://www.python.org/downloads/"
    exit 1
fi

# Check for Node.js (optional, for tooling)
if command_exists node; then
    print_status "Node.js $(node --version) found"
else
    print_warning "Node.js not found (optional)"
fi

# Check for Xcode (macOS only)
if [[ "$OSTYPE" == "darwin"* ]]; then
    if command_exists xcodebuild; then
        XCODE_VERSION=$(xcodebuild -version | head -n1)
        print_status "$XCODE_VERSION found"
    else
        print_error "Xcode not found"
        echo "Install Xcode from the Mac App Store"
        exit 1
    fi
else
    print_warning "Not running on macOS - iOS app development requires macOS"
fi

# Check for PostgreSQL
if command_exists psql; then
    print_status "PostgreSQL found"
else
    print_warning "PostgreSQL not found - will use SQLite for development"
    echo "Install PostgreSQL: brew install postgresql (macOS) or apt-get install postgresql (Linux)"
fi

echo ""

# ============================================================================
# BACKEND SETUP
# ============================================================================

echo "Setting up FastAPI backend..."
echo ""

# Create backend directory if it doesn't exist
mkdir -p backend

cd backend

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    print_status "Creating Python virtual environment..."
    python3 -m venv venv
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

# Create requirements.txt if it doesn't exist
if [ ! -f "requirements.txt" ]; then
    print_status "Creating requirements.txt..."
    cat > requirements.txt << EOF
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.25
alembic==1.13.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6
pydantic==2.5.3
pydantic-settings==2.1.0
psycopg2-binary==2.9.9
asyncpg==0.29.0
python-dotenv==1.0.0
pytest==7.4.4
pytest-asyncio==0.23.3
httpx==0.26.0
EOF
fi

# Install dependencies
print_status "Installing Python dependencies..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt > /dev/null 2>&1

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    print_status "Creating .env file..."
    cat > .env << EOF
# Database
DATABASE_URL=sqlite:///./fitness_app.db
# For PostgreSQL, use: postgresql://user:password@localhost:5432/fitness_app

# JWT Secret (generate a secure random string for production)
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# App settings
APP_NAME=Fitness Tracker API
DEBUG=True
EOF
fi

# Create basic FastAPI app structure if it doesn't exist
if [ ! -f "main.py" ]; then
    print_status "Creating basic FastAPI app structure..."
    mkdir -p app/{api,models,schemas,core,services}

    # Create main.py
    cat > main.py << 'EOF'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Fitness Tracker API",
    description="API for fitness tracking iOS app",
    version="0.1.0"
)

# Configure CORS for iOS app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Fitness Tracker API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOF
fi

print_status "Backend setup complete!"
echo ""

# ============================================================================
# FRONTEND SETUP (iOS)
# ============================================================================

cd ..

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "Setting up iOS frontend..."
    echo ""

    # Create iOS directory if it doesn't exist
    mkdir -p ios

    if [ ! -d "ios/FitnessApp.xcodeproj" ] && [ ! -d "ios/FitnessApp.xcworkspace" ]; then
        print_warning "Xcode project not found"
        echo "To create the iOS project:"
        echo "1. Open Xcode"
        echo "2. Create a new iOS App"
        echo "3. Name: FitnessApp"
        echo "4. Interface: SwiftUI"
        echo "5. Language: Swift"
        echo "6. Minimum iOS version: 17.0"
        echo "7. Save in the ios/ directory"
    else
        print_status "Xcode project found"
    fi

    echo ""
fi

# ============================================================================
# DATABASE SETUP
# ============================================================================

echo "Checking database..."
cd backend

if [ -f "fitness_app.db" ]; then
    print_status "SQLite database found"
else
    print_status "Database will be created on first run"
fi

cd ..
echo ""

# ============================================================================
# START SERVERS
# ============================================================================

echo "================================================"
echo "Setup complete! 🎉"
echo "================================================"
echo ""
echo "To start the development environment:"
echo ""
echo "1. Backend (FastAPI):"
echo "   cd backend"
echo "   source venv/bin/activate"
echo "   python main.py"
echo "   → API will be available at http://localhost:8000"
echo "   → API docs at http://localhost:8000/docs"
echo ""
echo "2. Frontend (iOS):"
echo "   cd ios"
echo "   open FitnessApp.xcodeproj"
echo "   → Press Cmd+R to build and run in simulator"
echo ""
echo "Quick start backend:"
echo "   ./start-backend.sh"
echo ""

# Create a quick start script for backend
cat > start-backend.sh << 'EOF'
#!/bin/bash
cd backend
source venv/bin/activate
python main.py
EOF
chmod +x start-backend.sh

print_status "Created start-backend.sh helper script"
echo ""

# Ask if user wants to start backend now
read -p "Start backend server now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd backend
    source venv/bin/activate
    echo ""
    echo "Starting FastAPI backend..."
    echo "Press Ctrl+C to stop"
    echo ""
    python main.py
fi
