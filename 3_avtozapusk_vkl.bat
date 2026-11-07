@echo off
cd /d "%~dp0"
schtasks /Create /TN "Jarvis_MCP" /SC ONLOGON /DELAY 0000:30 /RL LIMITED /F /TR "wscript.exe \"%~dp0Jarvis_avtozapusk.vbs\"" && echo Autostart ON.
pause
