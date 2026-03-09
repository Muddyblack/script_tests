@echo off
cd /d "%~dp0"
call venv\Scripts\activate
call pythonw nexus_app.py