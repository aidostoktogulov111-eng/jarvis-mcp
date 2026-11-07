# -*- coding: utf-8 -*-
"""WhatsApp для «Jarvis»: ТОЛЬКО чтение и скачивание файлов, без отправки.

Подключается к вашему WhatsApp как «связанное устройство» (как WhatsApp Web).
Пишет:
  data/wa/status.json     — состояние (need_qr / connected / logged_out)
  data/wa/qr.png          — QR-код для первого подключения
  data/wa/messages.jsonl  — входящие сообщения (кто, когда, текст, имя файла)
  data/wa/files/<дата>/   — автоматически скачанные документы, фото и видео
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
WA = BASE / "data" / "wa"
FILES = WA / "files"
FILES.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 300 * 1024 * 1024

from neonize.client import NewClient  # noqa: E402
from neonize.events import ConnectedEv, LoggedOutEv, MessageEv, PairStatusEv  # noqa: E402


def status(state, **kw):
    d = {"state": state, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **kw}
    (WA / "status.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def safe(s):
    return re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", s or "").strip(" .")[:120] or "file"


client = NewClient(str(WA / "session.sqlite3"))


@client.event.qr
def on_qr(_, data):
    import segno

    p = WA / "qr.png"
    segno.make_qr(data).save(str(p), scale=10, border=4)
    status("need_qr", qr=str(p))
    try:
        os.startfile(str(p))  # покажет QR на экране ноутбука
    except Exception:
        pass


@client.event(ConnectedEv)
def on_connected(_, __):
    (WA / "qr.png").unlink(missing_ok=True)
    status("connected")


@client.event(PairStatusEv)
def on_pair(_, ev):
    status("paired", info=str(ev)[:200])


@client.event(LoggedOutEv)
def on_logout(_, __):
    status("logged_out")


def media_of(m):
    """Возвращает (proto для скачивания, вид, имя файла, размер, подпись)."""
    if m.HasField("documentWithCaptionMessage"):
        inner = m.documentWithCaptionMessage.message
        d = inner.documentMessage
        return inner, "документ", d.fileName or d.title, d.fileLength, d.caption
    if m.HasField("documentMessage"):
        d = m.documentMessage
        return m, "документ", d.fileName or d.title, d.fileLength, d.caption
    if m.HasField("imageMessage"):
        return m, "фото", "", m.imageMessage.fileLength, m.imageMessage.caption
    if m.HasField("videoMessage"):
        return m, "видео", "", m.videoMessage.fileLength, m.videoMessage.caption
    return None, "", "", 0, ""


EXT = {"фото": ".jpg", "видео": ".mp4"}


@client.event(MessageEv)
def on_message(c, msg):
    try:
        info, m = msg.Info, msg.Message
        src = info.MessageSource
        text = m.conversation or m.extendedTextMessage.text
        proto, kind, fname, size, caption = media_of(m)
        ts = datetime.fromtimestamp(info.Timestamp) if info.Timestamp else datetime.now()
        rec = {
            "time": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "chat": src.Chat.User,
            "group": bool(src.IsGroup),
            "from_me": bool(src.IsFromMe),
            "sender": src.Sender.User,
            "name": info.Pushname,
            "text": (text or caption or "")[:2000],
            "kind": kind or "текст",
        }
        if proto is not None and not src.IsFromMe:
            if size and size > MAX_BYTES:
                rec["file_error"] = f"файл слишком большой ({size // 1048576} МБ), не скачан"
            else:
                day = FILES / ts.strftime("%Y-%m-%d")
                day.mkdir(exist_ok=True)
                name = safe(fname) if fname else f"{kind}{EXT.get(kind, '')}"
                who = safe(info.Pushname or src.Sender.User)[:40]
                path = day / f"{ts:%H%M%S}_{who}_{name}"
                c.download_any(proto, str(path))
                rec["file"] = str(path)
                rec["file_name"] = fname or name
        with open(WA / "messages.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        with open(WA / "errors.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()} {e!r}\n")


if __name__ == "__main__":
    status("starting")
    client.connect()
