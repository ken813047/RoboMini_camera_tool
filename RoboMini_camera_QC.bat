@echo off
rem Double-click to open the RoboMini_camera_QC window.
setlocal
cd /d "%~dp0"
title RoboMini_camera_QC
call "%~dp0scripts\env.bat" || goto :fail
echo [RoboMini_camera_QC] Starting GUI ... (close the Windows Camera app first)
"%VENV_PY%" -m stereocam gui %*
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo [RoboMini_camera_QC] Something went wrong. See the messages above.
pause
exit /b 1
