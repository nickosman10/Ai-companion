@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m companion
if errorlevel 1 pause
