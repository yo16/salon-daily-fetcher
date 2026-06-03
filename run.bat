@echo off
rem ============================================================================
rem  Salon.JP Daily Fetcher launcher  (ASCII only: cmd parses .bat as cp932)
rem  - Double-click from a desktop shortcut to run.
rem  - Uses the conda env python (default env: 202606_salon_fetcher).
rem  - Override the interpreter with  SDF_PYTHON=<full path to python.exe>.
rem  - For unattended runs set  SDF_NO_PAUSE=1  to skip the pause on error.
rem  - Japanese usage notes are in README.md.
rem ============================================================================
setlocal enableextensions
chcp 65001 >nul
cd /d "%~dp0"

set "CONDA_ENV=202606_salon_fetcher"

if defined SDF_PYTHON (
  set "PY=%SDF_PYTHON%"
) else if exist "%USERPROFILE%\anaconda3\envs\%CONDA_ENV%\python.exe" (
  set "PY=%USERPROFILE%\anaconda3\envs\%CONDA_ENV%\python.exe"
) else if exist "%USERPROFILE%\miniconda3\envs\%CONDA_ENV%\python.exe" (
  set "PY=%USERPROFILE%\miniconda3\envs\%CONDA_ENV%\python.exe"
) else (
  set "PY=python"
)

"%PY%" -m src.main
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
  echo.
  echo [run.bat] Failed with exit code %EXITCODE%. See the logs\ folder for details.
  if not defined SDF_NO_PAUSE pause
)

endlocal & exit /b %EXITCODE%
