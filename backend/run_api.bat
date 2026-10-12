@echo off
cd /d "%~dp0"
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul
if %errorlevel%==0 (
  echo The API is already running on http://localhost:8000 - nothing to do.
  echo To restart it, close the other API window first.
  pause
  exit /b
)
echo API starting... keep this window open. Docs: http://localhost:8000/docs
env\Scripts\python.exe -m uvicorn main:app --port 8000
pause
