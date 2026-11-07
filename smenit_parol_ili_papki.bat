@echo off
cd /d "%~dp0"
call 4_stop.bat
.venv\Scripts\python.exe setup.py
echo After changing the password, click Connect again for the connector in Claude.
call 2_zapusk.bat
