@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo PromptMaker is not installed yet - running install.bat first...
  call install.bat /noshortcut || exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" main.py
