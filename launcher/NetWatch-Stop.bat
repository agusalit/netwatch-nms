@echo off
set DISTRO=Ubuntu-26.04
wsl -d %DISTRO% -e bash -c "pkill -f '[u]vicorn app.main:app'"
echo NetWatch stopped.
timeout /t 2 /nobreak >nul
