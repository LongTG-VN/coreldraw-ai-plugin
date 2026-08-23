@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo STARTUP BLOCKED: Python is not available on PATH.
  pause
  exit /b 1
)

if not exist "training\workspace\company_archive\archive.sqlite" (
  echo STARTUP BLOCKED: company archive inventory is missing.
  echo Expected: training\workspace\company_archive\archive.sqlite
  pause
  exit /b 1
)

python -m training.tools.corel_codex_ui --ensure-corel --open-browser --port 8004
set "COREL_AI_EXIT=%ERRORLEVEL%"
if not "%COREL_AI_EXIT%"=="0" (
  echo.
  echo Corel AI Operator stopped with an error. Review the READY/OFFLINE messages above.
  pause
)
exit /b %COREL_AI_EXIT%
