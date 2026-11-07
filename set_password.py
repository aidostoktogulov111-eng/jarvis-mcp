# -*- coding: utf-8 -*-
"""Окно смены пароля: пароль виден при вводе."""
import base64, hashlib, json, secrets, subprocess, time
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

BASE = Path(__file__).resolve().parent
CFG = BASE / "config.json"


def save():
    pw = e.get().strip()
    if len(pw) < 10:
        messagebox.showerror("Jarvis", "Пароль должен быть не короче 10 символов.")
        return
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    salt = secrets.token_bytes(16)
    cfg["password_salt"] = base64.b64encode(salt).decode()
    cfg["password_hash"] = base64.b64encode(hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 300000)).decode()
    cfg["password_iter"] = 300000
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    # перезапуск сервера (launcher сам поднимет его заново)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*Jarvis*server.py*' } | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"], creationflags=0x08000000)
    time.sleep(2)
    (BASE / "data" / "state.json").unlink(missing_ok=True)
    messagebox.showinfo("Jarvis", "Пароль сохранён:\n\n" + pw + "\n\nЗапишите его. Через 15 секунд подключайте коннектор в Claude заново.")
    root.destroy()


root = tk.Tk()
root.title("Jarvis — новый пароль")
root.geometry("460x200")
tk.Label(root, text="Введите новый пароль (латиницей, не короче 10 символов).\nОн виден при вводе — проверьте, что набрали правильно.",
         font=("Segoe UI", 11)).pack(pady=12)
e = tk.Entry(root, font=("Consolas", 16), width=28)
e.pack(pady=6)
e.focus()
tk.Button(root, text="Сохранить", font=("Segoe UI", 12), command=save, bg="#1f6feb", fg="white").pack(pady=10)
root.bind("<Return>", lambda _: save())
root.mainloop()
