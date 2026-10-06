@echo off
rem ==========================================================================
rem  StereoCam isolated environment
rem  - venv lives in .venv inside this project (never touches global Python)
rem  - ignores user site-packages / PYTHONPATH / PYTHONHOME from other projects
rem  - reinstalls packages automatically when requirements.txt changes
rem  Usage: call "%~dp0scripts\env.bat"   (sets VENV_PY for the caller)
rem ==========================================================================

for %%I in ("%~dp0..") do set "PROJECT_DIR=%%~fI"
set "VENV_DIR=%PROJECT_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

rem ---- isolation: drop anything other projects may have set ----
set "PYTHONPATH="
set "PYTHONHOME="
set "PYTHONSTARTUP="
set "VIRTUAL_ENV="
set "CONDA_PREFIX="
set "PYTHONNOUSERSITE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_REQUIRE_VIRTUALENV=1"
set "PIP_CACHE_DIR=%PROJECT_DIR%\.pip-cache"

if exist "%VENV_PY%" goto :check_reqs

echo [StereoCam] First run: creating isolated Python environment in .venv ...
set "BASE_PY="
py -3.11 -c "import sys" >nul 2>&1 && set "BASE_PY=py -3.11"
if not defined BASE_PY (py -3 -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1 && set "BASE_PY=py -3")
if not defined BASE_PY (python -c "import sys; assert sys.version_info >= (3, 9)" >nul 2>&1 && set "BASE_PY=python")
if not defined BASE_PY (
    echo [StereoCam] ERROR: Python 3.9+ not found. Install it from https://www.python.org/downloads/
    exit /b 1
)
%BASE_PY% -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo [StereoCam] ERROR: failed to create venv.
    exit /b 1
)
"%VENV_PY%" -m pip install --upgrade pip
if exist "%VENV_DIR%\requirements.installed" del "%VENV_DIR%\requirements.installed"

:check_reqs
if exist "%VENV_DIR%\requirements.installed" (
    fc /b "%PROJECT_DIR%\requirements.txt" "%VENV_DIR%\requirements.installed" >nul 2>&1 && exit /b 0
)
echo [StereoCam] Installing packages from requirements.txt ...
"%VENV_PY%" -m pip install -r "%PROJECT_DIR%\requirements.txt"
if errorlevel 1 (
    echo [StereoCam] ERROR: pip install failed. Check network / proxy settings.
    exit /b 1
)
copy /y "%PROJECT_DIR%\requirements.txt" "%VENV_DIR%\requirements.installed" >nul
exit /b 0
