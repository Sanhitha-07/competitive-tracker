@echo off
cd /d "%~dp0"
echo This deletes ALL data and creates the 3 demo clients with fresh RSS + YouTube data.
choice /m "Continue"
if errorlevel 2 exit /b
env\Scripts\python.exe seed_demo.py
pause
