# -*- coding: utf-8 -*-
"""Первичная настройка: адрес ngrok, токен, пароль, папки. Запускается из 1_ustanovka.bat."""
import base64, getpass, hashlib, json, os, secrets, subprocess, sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CFG = BASE / "config.json"
EXAMPLE = BASE / "config.example.json"


def ask(q, default=""):
    v = input(f"{q}" + (f" [{default}]" if default else "") + ": ").strip()
    return v or default


def main():
    print("=== Настройка «Jarvis для Claude» ===\n")
    if CFG.exists():
        old = json.loads(CFG.read_text(encoding="utf-8"))
    elif EXAMPLE.exists():
        old = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        old["public_url"] = ""
    else:
        old = {}

    url = ask("Постоянный домен из ngrok (например my-pc.ngrok-free.dev)",
              old.get("public_url", "").replace("YOUR-DOMAIN", "") if "YOUR-DOMAIN" not in old.get("public_url", "") else "")
    url = "https://" + url.replace("https://", "").replace("http://", "").strip("/")
    domain = url.replace("https://", "")

    token = old.get("ngrok_authtoken", "")
    t = getpass.getpass("Authtoken из ngrok (Enter — оставить прежний, ввод не виден): ").strip()
    if t:
        token = t
    if token:
        try:
            subprocess.run(["ngrok", "config", "add-authtoken", token], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            pass

    while True:
        pw = getpass.getpass("Придумайте пароль для подключения (минимум 10 символов, ввод не виден): ")
        if len(pw) < 10:
            print("Слишком короткий."); continue
        if getpass.getpass("Повторите пароль: ") != pw:
            print("Не совпадает, ещё раз."); continue
        break
    salt = secrets.token_bytes(16); it = 300_000
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, it)

    home = os.path.expanduser("~")
    folders = [f for f in (old.get("allowed_folders") or []) if "USERNAME" not in f and os.path.isdir(f)]
    if not folders:
        folders = [os.path.join(home, x) for x in ("Desktop", "Documents", "Downloads")]
    print("\nПапки с доступом:")
    for f in folders:
        print("  ", f)
    extra = ask("Добавить ещё папки через ; (Enter — оставить как есть)")
    folders += [x.strip() for x in extra.split(";") if x.strip()]

    cfg = dict(old)
    cfg.update({
        "public_url": url, "ngrok_domain": domain, "ngrok_authtoken": token,
        "port": old.get("port", 8765),
        "password_salt": base64.b64encode(salt).decode(),
        "password_hash": base64.b64encode(h).decode(), "password_iter": it,
        "allowed_folders": folders,
        "read_only_folders": old.get("read_only_folders", []),
        "writable_exceptions": old.get("writable_exceptions", []),
        "backup_dir": str(BASE / "backups"),
        "confirm_mode": old.get("confirm_mode", "chat"),
        "confirm_timeout_sec": old.get("confirm_timeout_sec", 60),
    })
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    state = BASE / "data" / "state.json"
    if state.exists():
        state.unlink()  # смена пароля — все старые подключения отключаются
    print(f"\nГотово. Настройки сохранены в {CFG}")
    print(f"Адрес коннектора для Claude:  {url}/mcp")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
