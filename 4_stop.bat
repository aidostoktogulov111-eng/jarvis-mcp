@echo off
cd /d "%~dp0"
echo Stopping server and tunnel...
if not exist data mkdir data
echo stop> data\STOP
timeout /t 12 /nobreak >nul
if exist data\launcher.pid for /f %%p in (data\launcher.pid) do taskkill /F /T /PID %%p >nul 2>nul
taskkill /F /IM ngrok.exe >nul 2>nul
echo STOPPED. Nobody can connect to this PC now.
pause
