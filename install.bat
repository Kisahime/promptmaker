@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title PromptMaker installer
echo.
echo  ==============================
echo    PromptMaker - installer
echo  ==============================
echo.

rem --- 1. Find Python 3.10+ ------------------------------------------------
set "PY="
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=py -3")
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=python")
)
if not defined PY (
  echo  [X] Python 3.10 or newer was not found.
  echo.
  echo      Download it from https://www.python.org/downloads/
  echo      During setup, tick "Add python.exe to PATH", then run install.bat again.
  echo.
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% -c "import platform; print(platform.python_version())"') do set "PYVER=%%v"
echo  [OK] Python !PYVER! found

rem --- 2. Virtual environment + dependencies -------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo  [..] Creating virtual environment in .venv
  %PY% -m venv .venv || (echo  [X] Could not create .venv & pause & exit /b 1)
)
echo  [..] Installing dependencies (PySide6 is about 100 MB, please wait)
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check -q || (echo  [X] pip install failed - check your internet connection. & pause & exit /b 1)
".venv\Scripts\python.exe" -c "import PySide6; print('  [OK] PySide6', PySide6.__version__)" || (echo  [X] PySide6 did not install correctly & pause & exit /b 1)

rem --- 3. Optional desktop shortcut -----------------------------------------
if /i not "%~1"=="/noshortcut" (
  set "ANS=Y"
  if /i not "%~1"=="/yes" set /p "ANS=  Create a desktop shortcut? [Y/n] "
  if /i not "!ANS!"=="n" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\PromptMaker.lnk'); $s.TargetPath='%~dp0run.bat'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.IconLocation='%~dp0promptmaker\assets\icon.ico,0'; $s.Save()" && echo  [OK] Desktop shortcut created
  )
)

rem --- 4. Ollama check (optional, for AI features) --------------------------
set "OLL="
where ollama >nul 2>nul && set "OLL=1"
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLL=1"
if defined OLL (
  echo  [OK] Ollama found - AI features available. Pull a model once with:  ollama pull llama3.2
) else (
  echo  [i] Ollama not found. PromptMaker works without it, but for the AI features
  echo      install it from https://ollama.com/download and run:  ollama pull llama3.2
)

echo.
echo  Done. Start PromptMaker with run.bat or the desktop shortcut.
echo.
if /i not "%~1"=="/yes" if /i not "%~1"=="/noshortcut" pause
exit /b 0
