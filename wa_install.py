# -*- coding: utf-8 -*-
"""Подключение WhatsApp к «Jarvis»."""
import json, subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
LOG = open(BASE / "wa_install_log.txt", "w", encoding="utf-8", buffering=1)


def say(m):
    print(m); LOG.write(m + "\n")


say("=== Подключение WhatsApp ===")
say("[1/4] Останавливаю сервер...")
(DATA / "STOP").write_text("stop")
time.sleep(12)
subprocess.run(["powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*Jarvis*' -and "
                "$_.CommandLine -notlike '*wa_install*' -and $_.Name -like 'python*' } | "
                "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], capture_output=True)
(DATA / "STOP").unlink(missing_ok=True)

say("[2/4] Ставлю библиотеку WhatsApp...")
r = subprocess.run([str(BASE / ".venv" / "Scripts" / "python.exe"), "-m", "pip", "install", "--no-index",
                    "--find-links", str(BASE / "wawheels"), "neonize", "python-magic-bin"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
LOG.write(r.stdout + r.stderr)
if r.returncode:
    say("ОШИБКА установки, подробности в wa_install_log.txt"); input("Enter..."); sys.exit(1)

say("[3/4] Включаю WhatsApp в настройках...")
cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
cfg["whatsapp"] = True
(BASE / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

say("[4/4] Запускаю сервер заново...")
subprocess.Popen([str(BASE / ".venv" / "Scripts" / "pythonw.exe"), str(BASE / "launcher.py")], cwd=str(BASE),
                 creationflags=0x00000008 | 0x00000200)
st = DATA / "wa" / "status.json"
for _ in range(40):
    time.sleep(3)
    if st.exists():
        s = json.loads(st.read_text(encoding="utf-8")).get("state")
        if s in ("need_qr", "connected"):
            break
s = json.loads(st.read_text(encoding="utf-8")).get("state") if st.exists() else "нет ответа"
say(f"   WhatsApp: {s}")
if s == "need_qr":
    say("")
    say("На экране открылся QR-код. На телефоне: WhatsApp -> Настройки -> Связанные устройства ->")
    say("Привязка устройства -> наведите камеру на QR-код.")
elif s != "connected":
    say("Модуль не ответил. Напишите Claude, он посмотрит data\\whatsapp.log")
say("")
say("Готово, окно можно закрыть.")
input("Нажмите Enter...")
