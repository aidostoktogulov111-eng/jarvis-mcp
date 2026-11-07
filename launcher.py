# -*- coding: utf-8 -*-
"""Запускает сервер и туннель ngrok в фоне, перезапускает их, если упали.
Запускается без окна: pythonw.exe launcher.py (так его запускает автозапуск)."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
CFG.pop("ngrok_path", None) if CFG.get("ngrok_path") and not Path(CFG["ngrok_path"]).exists() else None
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
LOG = open(DATA / "launcher.log", "a", encoding="utf-8", buffering=1)


def say(msg):
    LOG.write(time.strftime("%Y-%m-%d %H:%M:%S  ") + msg + "\n")


def find_ngrok():
    p = CFG.get("ngrok_path") or shutil.which("ngrok")
    if p:
        return p
    for c in (
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ngrok.exe",
        BASE / "ngrok.exe",
    ):
        if c.exists():
            return str(c)
    return None


def start_server():
    py = sys.executable.replace("pythonw.exe", "python.exe")
    out = open(DATA / "server.log", "a", encoding="utf-8")
    return subprocess.Popen([py, str(BASE / "server.py")], cwd=str(BASE), stdout=out, stderr=out,
                            creationflags=NO_WINDOW)


def start_ngrok():
    ng = find_ngrok()
    out = open(DATA / "ngrok.log", "a", encoding="utf-8")
    if not ng:
        py = sys.executable.replace("pythonw.exe", "python.exe")
        return subprocess.Popen([py, str(BASE / "tunnel.py")], cwd=str(BASE), stdout=out, stderr=out,
                                creationflags=NO_WINDOW)
    return subprocess.Popen([ng, "http", f"127.0.0.1:{CFG.get('port', 8765)}", f"--url={CFG['ngrok_domain']}",
                             "--log=stdout"], stdout=out, stderr=out, creationflags=NO_WINDOW)


def start_wa():
    if not CFG.get("whatsapp"):
        return None
    py = sys.executable.replace("pythonw.exe", "python.exe")
    out = open(DATA / "whatsapp.log", "a", encoding="utf-8")
    return subprocess.Popen([py, str(BASE / "wa_service.py")], cwd=str(BASE), stdout=out, stderr=out,
                            creationflags=NO_WINDOW)


def main():
    (DATA / "launcher.pid").write_text(str(os.getpid()))
    say("старт")
    srv, ng, wa = start_server(), start_ngrok(), start_wa()
    wa_next = 0
    try:
        while True:
            time.sleep(10)
            if (DATA / "STOP").exists():
                break
            if srv.poll() is not None:
                say(f"сервер остановился (код {srv.returncode}), перезапуск")
                time.sleep(5)
                srv = start_server()
            if ng is not None and ng.poll() is not None:
                say(f"ngrok остановился (код {ng.returncode}), перезапуск")
                time.sleep(15)
                ng = start_ngrok()
            if wa is not None and wa.poll() is not None:
                if not wa_next:
                    say(f"whatsapp остановился (код {wa.returncode}), перезапуск через 2 мин")
                    wa_next = time.time() + 120
                elif time.time() >= wa_next:
                    wa, wa_next = start_wa(), 0
    finally:
        for p in (srv, ng, wa):
            if p and p.poll() is None:
                p.terminate()
        (DATA / "STOP").unlink(missing_ok=True)
        say("остановлен")


if __name__ == "__main__":
    main()
