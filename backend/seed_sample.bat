@echo off
rem Adds three made-up "Sample:" workspaces (bakery, news channel, fitness creator) so you can
rem explore the dashboards before adding any API keys. Your real workspaces are not touched.
cd /d "%~dp0"
env\Scripts\python.exe seed_sample.py
pause
