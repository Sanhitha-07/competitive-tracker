@echo off
rem Stops the API (port 8000) and the UI (port 5173).
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING" /c:":5173 .*LISTENING"') do (
  taskkill /f /t /pid %%p >nul 2>&1
)
echo Competitive Tracker stopped.
ping -n 4 127.0.0.1 >nul
