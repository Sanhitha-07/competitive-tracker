@echo off
rem Starts the API and the UI in their own windows, then opens the app in the browser.
cd /d "%~dp0"

netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if %errorlevel%==0 (
  echo API already running.
) else (
  start "Competitive Tracker - API (keep open)" cmd /k "cd /d "%~dp0backend" && env\Scripts\python.exe -m uvicorn main:app --port 8000"
)

netstat -ano | findstr /r /c:":5173 .*LISTENING" >nul
if %errorlevel%==0 (
  echo UI already running.
) else (
  start "Competitive Tracker - UI (keep open)" cmd /k "cd /d "%~dp0frontend" && npm run dev -- --port 5173 --strictPort"
)

echo Waiting for the app to start...
ping -n 7 127.0.0.1 >nul
start "" http://localhost:5173
echo.
echo The app is open at http://localhost:5173
echo Keep the two "keep open" windows running. Close them to stop the app.
ping -n 6 127.0.0.1 >nul
