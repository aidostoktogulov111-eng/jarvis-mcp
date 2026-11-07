@echo off
cd /d "%~dp0"
if exist data\STOP del data\STOP
start "" ".venv\Scripts\pythonw.exe" "%~dp0launcher.py"
echo Server started in background. Wait 15 seconds...
timeout /t 15 /nobreak >nul
.venv\Scripts\python.exe -c "import json,urllib.request as u;c=json.load(open('config.json',encoding='utf-8'));r=u.Request(c['public_url']+'/health',headers={'ngrok-skip-browser-warning':'1','User-Agent':'x'});print('OK' if u.urlopen(r,timeout=10).read()==b'ok' else 'NO');print('Connector URL:',c['public_url']+'/mcp')"
pause
