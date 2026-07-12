@echo off
rem ============================================================================
rem  Salon.JP Daily Fetcher launcher  (ASCII only: cmd parses .bat as cp932)
rem  - Double-click from a desktop shortcut to run.
rem  - Uses the conda env python (default env: 202606_salon_fetcher).
rem  - Override the interpreter with  SDF_PYTHON=<full path to python.exe>.
rem  - For unattended runs set  SDF_NO_PAUSE=1  to skip the pause on error.
rem  - On success, the fetcher exports newly fetched articles into the newsletter
rem    import inbox (and archives the local copies under data\exported\), then
rem    this script runs  npm run import  inside the newsletter-ai-chat project.
rem  - Override the project dir with  SDF_NEWSLETTER_DIR=<full path>  and the
rem    export inbox with  SDF_EXPORT_DIR=<full path to import folder>.
rem  - Japanese usage notes are in README.md.
rem ============================================================================
setlocal enableextensions
chcp 65001 >nul
cd /d "%~dp0"

set "CONDA_ENV=202606_salon_fetcher"

rem newsletter-ai-chat project that consumes the fetched articles.
set "NEWSLETTER_DIR=D:\Public\github\yo16\newsletter-ai-chat"
if defined SDF_NEWSLETTER_DIR set "NEWSLETTER_DIR=%SDF_NEWSLETTER_DIR%"

rem Export inbox handed to the fetcher via env: it copies new article markdown
rem there (date\id.md tree is preserved) and archives local copies afterwards.
if not defined SDF_EXPORT_DIR set "SDF_EXPORT_DIR=%NEWSLETTER_DIR%\import"

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
if not "%EXITCODE%"=="0" goto :fetch_failed

rem --- Post-processing (only after a successful fetch) -------------------------
rem The fetcher already copied newly fetched articles into "%SDF_EXPORT_DIR%" and
rem archived the local copies, so here we only trigger the newsletter import.
rem "call" is required so control returns here; pushd/popd restore this directory.
echo.
echo [run.bat] Running "npm run import" in "%NEWSLETTER_DIR%" ...
pushd "%NEWSLETTER_DIR%"
if errorlevel 1 goto :no_newsletter_dir
call npm run import
set "EXITCODE=%ERRORLEVEL%"
popd
if not "%EXITCODE%"=="0" goto :import_failed
goto :done

:fetch_failed
echo.
echo [run.bat] Fetch failed with exit code %EXITCODE%. See the logs\ folder for details.
if not defined SDF_NO_PAUSE pause
goto :done

:no_newsletter_dir
echo [run.bat] ERROR: cannot enter "%NEWSLETTER_DIR%". Set SDF_NEWSLETTER_DIR if it moved.
set "EXITCODE=1"
if not defined SDF_NO_PAUSE pause
goto :done

:import_failed
echo.
echo [run.bat] "npm run import" failed with exit code %EXITCODE%.
if not defined SDF_NO_PAUSE pause
goto :done

:done
endlocal & exit /b %EXITCODE%
