@echo off
cd /d "%~dp0"
echo Отвязать текущего владельца и разрешить новую привязку?
echo Все подключения будут отключены. Затем снова нажмите "Подключить" коннектор в Claude.
pause
call 4_stop.bat
if exist data\state.json del /f data\state.json
call 2_zapusk.bat
