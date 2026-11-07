@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Установка «Jarvis для Claude» ===
where python >nul 2>nul || (echo Python не найден. Установите Python 3.12+ с галочкой "Add python.exe to PATH". & pause & exit /b 1)
if not exist .venv python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip >nul
.venv\Scripts\python.exe -m pip install -r requirements.txt || (echo Ошибка установки библиотек. & pause & exit /b 1)
where ngrok >nul 2>nul || winget install --id Ngrok.Ngrok -e --accept-source-agreements --accept-package-agreements
.venv\Scripts\python.exe setup.py
echo.
echo Установка завершена. Теперь запустите 2_zapusk.bat
pause
