@echo off
cd /d "%~dp0"
echo === EMERGENCY OFF ===
if not exist data mkdir data
echo stop> data\STOP
timeout /t 3 /nobreak >nul
if exist data\launcher.pid for /f %%p in (data\launcher.pid) do taskkill /F /T /PID %%p >nul 2>nul
taskkill /F /IM ngrok.exe >nul 2>nul
if exist data\state.json del /f data\state.json
schtasks /Delete /TN "Jarvis_MCP" /F >nul 2>nul
echo Server stopped, all access revoked, autostart removed.
echo To turn on again: 2_zapusk.bat and reconnect the connector in Claude with your password.
pause
