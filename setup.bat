@echo off
REM One-time setup: creates a virtual environment, installs packages, downloads the voice model.
cd /d "%~dp0"
python -m venv .venv || (echo Python not found. Install Python 3.11+ from python.org first. & pause & exit /b 1)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python scripts\get_voice_model.py
if not exist settings.json copy settings.example.json settings.json
echo.
echo Setup done. Set your API key (see README), then double-click run.bat
pause
