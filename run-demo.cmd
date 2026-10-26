@echo off
setlocal
cd /d "%~dp0"
set "CUIDA_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CUIDA_PYTHON%" (
  "%CUIDA_PYTHON%" demo\replay.py
) else (
  py -3 demo\replay.py
)
if errorlevel 1 (
  echo Demo could not run. Install Python 3 or run demo\replay.py with your Python interpreter.
  pause
  exit /b 1
)
echo.
echo Results are saved in the results folder.
pause
