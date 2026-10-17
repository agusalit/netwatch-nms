@echo off
setlocal

rem ---- Edit these two lines if your setup differs ----
set DISTRO=Ubuntu
set PROJECT_DIR=~/project/git/netwatch-nms
rem -----------------------------------------------------

rem Usage:  NetWatch-Start.bat            start, wait until ready, open the dashboard
rem         NetWatch-Start.bat /background  start silently and return at once (for Windows startup)

set URL=http://127.0.0.1:8000

rem [u]vicorn: the brackets stop pgrep from matching its own command line
wsl -d %DISTRO% -e bash -c "pgrep -f '[u]vicorn app.main:app' >/dev/null"
if %ERRORLEVEL%==0 (
    echo NetWatch is already running.
    goto open
)

echo Starting NetWatch in the background...
wscript //nologo "%~dp0NetWatch-Hidden.vbs" "%DISTRO%" "%PROJECT_DIR%"

if /I "%~1"=="/background" goto end

rem Wait until the app answers (startup runs one polling sweep first, so it can take a few seconds)
set /a tries=0
:wait
curl -s -o nul http://127.0.0.1:8000/health
if %ERRORLEVEL%==0 goto open
set /a tries+=1
if %tries% GEQ 40 goto open
timeout /t 1 /nobreak >nul
goto wait

:open
if /I "%~1"=="/background" goto end
start "" %URL%
:end
endlocal
