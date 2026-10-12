@echo off
cd /d "%~dp0"
echo This deletes ALL competitors and stories from the database.
choice /m "Continue"
if errorlevel 2 exit /b
env\Scripts\python.exe reset_data.py
pause
