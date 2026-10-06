@echo off
rem Opens a command prompt inside the isolated StereoCam environment.
setlocal
cd /d "%~dp0"
call "%~dp0scripts\env.bat" || (pause & exit /b 1)
call "%VENV_DIR%\Scripts\activate.bat"
set "PYTHONNOUSERSITE=1"
echo ==============================================================
echo  StereoCam CLI  (isolated venv: %VENV_DIR%)
echo.
echo    python -m stereocam list --probe
echo    python -m stereocam preview --left 0 --right 1
echo    python -m stereocam preview --sbs 0 --width 2560 --height 720
echo    python -m stereocam snap --left 0 --right 1 --count 10 --interval 1
echo    python -m stereocam gui
echo    python -m stereocam --help
echo ==============================================================
cmd /k
