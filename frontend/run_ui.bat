@echo off
cd /d "%~dp0"
echo UI starting... open http://localhost:5173
echo (Start backend\run_api.bat too, and keep both windows open.)
npm run dev
pause
