@echo off
echo Checking Docker Desktop status...
docker ps >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Docker Desktop is not running!
    echo.
    echo Please:
    echo 1. Open Docker Desktop from the Start menu
    echo 2. Wait for it to fully start (whale icon in system tray)
    echo 3. Run this script again
    echo.
    pause
    exit /b 1
)

echo Docker Desktop is running!
echo.
echo Starting services...
docker compose up --build

