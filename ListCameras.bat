@echo off
rem List all cameras and probe their default resolution.
setlocal
cd /d "%~dp0"
call "%~dp0scripts\env.bat" || goto :end
"%VENV_PY%" -m stereocam list --probe
:end
echo.
pause
