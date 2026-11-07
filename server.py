# -*- coding: utf-8 -*-
"""
Jarvis для Claude — свой MCP-сервер удалённого доступа к компьютеру.

Работает как коннектор Claude (чат, телефон, голосовой режим).
Защита:
  * OAuth 2.1 с паролем: подключить коннектор можно только зная ваш пароль;
  * только белый список папок; запись в защищённые папки запрещена;
  * перед перезаписью файла — резервная копия;
  * запуск команд и запись вне белого списка — только после подтверждения окном на ПК;
  * журнал всех действий.
"""
from __future__ import annotations

import asyncio
import base64
import csv
import fnmatch
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import secrets
import shutil
import struct
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

# ----------------------------------------------------------------------------
# Настройки
# ----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("PC_MCP_CONFIG", BASE_DIR / "config.json"))
IS_WINDOWS = os.name == "nt"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        sys.exit(f"Нет файла настроек {CONFIG_PATH}. Сначала запустите setup.bat")
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg.setdefault("port", 8765)
    cfg.setdefault("data_dir", str(BASE_DIR / "data"))
    cfg.setdefault("allowed_folders", [])
    cfg.setdefault("read_only_folders", [])
    cfg.setdefault("writable_exceptions", [])
    cfg.setdefault("backup_dir", str(Path(__file__).resolve().parent / "backups"))
    cfg.setdefault("confirm_mode", "chat")  # chat | popup | deny
    cfg.setdefault("confirm_timeout_sec", 60)
    cfg.setdefault("access_token_hours", 1)
    cfg.setdefault("refresh_token_days", 30)
    cfg.setdefault(
        "allowed_redirect_uris",
        ["https://claude.ai/api/mcp/auth_callback", "https://claude.com/api/mcp/auth_callback"],
    )
    cfg["public_url"] = cfg["public_url"].rstrip("/")
    return cfg


CFG = load_config()
DATA_DIR = Path(CFG["data_dir"])
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------
# Журнал
# ----------------------------------------------------------------------------
log = logging.getLogger("jarvis")
log.setLevel(logging.INFO)
_fh = RotatingFileHandler(DATA_DIR / "actions.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s"))
log.addHandler(_fh)
log.addHandler(logging.StreamHandler(sys.stdout))


def audit(event: str, **kw: Any) -> None:
    short = {k: (v if not isinstance(v, str) or len(v) < 300 else v[:300] + "…") for k, v in kw.items()}
    log.info("%s %s", event, json.dumps(short, ensure_ascii=False))


# ----------------------------------------------------------------------------
# Пароль и OAuth (один пользователь — вы)
# ----------------------------------------------------------------------------
def check_password(pw: str) -> bool:
    salt = base64.b64decode(CFG["password_salt"])
    want = base64.b64decode(CFG["password_hash"])
    got = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, int(CFG.get("password_iter", 300_000)))
    return hmac.compare_digest(got, want)


STATE_PATH = DATA_DIR / "state.json"
_state_lock = threading.Lock()


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


class Store:
    """Клиенты и токены. Токены хранятся только в виде хешей."""

    def __init__(self) -> None:
        self.clients: dict[str, dict] = {}
        self.access: dict[str, dict] = {}
        self.refresh: dict[str, dict] = {}
        if STATE_PATH.exists():
            try:
                d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                self.clients, self.access, self.refresh = d["clients"], d["access"], d["refresh"]
            except Exception:  # повреждённый файл — начинаем заново
                pass
        self.codes: dict[str, AuthorizationCode] = {}
        self.pending: dict[str, tuple[str, AuthorizationParams, float]] = {}

    def save(self) -> None:
        now = time.time()
        self.access = {k: v for k, v in self.access.items() if v["expires_at"] > now}
        self.refresh = {k: v for k, v in self.refresh.items() if v["expires_at"] > now}
        with _state_lock:
            tmp = STATE_PATH.with_suffix(".tmp")
            tmp.write_text(
                json.dumps({"clients": self.clients, "access": self.access, "refresh": self.refresh}, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, STATE_PATH)


STORE = Store()
_login_fail: list[float] = []


class SingleUserOAuth:
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        c = STORE.clients.get(client_id)
        return OAuthClientInformationFull.model_validate(c) if c else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        allowed = CFG["allowed_redirect_uris"]
        for uri in client_info.redirect_uris or []:
            if str(uri) not in allowed:
                audit("REGISTER_REJECTED", redirect_uri=str(uri))
                raise RegistrationError(
                    error="invalid_redirect_uri", error_description="Этот адрес возврата не разрешён"
                )
        STORE.clients[client_info.client_id] = client_info.model_dump(mode="json")
        STORE.save()
        audit("CLIENT_REGISTERED", name=client_info.client_name or "", client_id=client_info.client_id)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        req = secrets.token_urlsafe(24)
        STORE.pending[req] = (client.client_id, params, time.time() + 600)
        return f"{CFG['public_url']}/login?req={req}"

    async def load_authorization_code(self, client, authorization_code: str):
        c = STORE.codes.get(authorization_code)
        if c and c.client_id == client.client_id and c.expires_at > time.time():
            return c
        return None

    def _issue(self, client_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        at, rt = secrets.token_urlsafe(40), secrets.token_urlsafe(48)
        at_exp = int(time.time() + CFG["access_token_hours"] * 3600)
        rt_exp = int(time.time() + CFG["refresh_token_days"] * 86400)
        STORE.access[_sha(at)] = {"client_id": client_id, "scopes": scopes, "expires_at": at_exp, "resource": resource}
        STORE.refresh[_sha(rt)] = {"client_id": client_id, "scopes": scopes, "expires_at": rt_exp, "resource": resource}
        STORE.save()
        return OAuthToken(
            access_token=at, expires_in=at_exp - int(time.time()), refresh_token=rt, scope=" ".join(scopes) or None
        )

    async def exchange_authorization_code(self, client, authorization_code: AuthorizationCode) -> OAuthToken:
        STORE.codes.pop(authorization_code.code, None)
        audit("TOKEN_ISSUED", client_id=client.client_id)
        return self._issue(client.client_id, authorization_code.scopes, authorization_code.resource)

    async def load_refresh_token(self, client, refresh_token: str):
        r = STORE.refresh.get(_sha(refresh_token))
        if r and r["client_id"] == client.client_id and r["expires_at"] > time.time():
            return RefreshToken(token=refresh_token, client_id=r["client_id"], scopes=r["scopes"],
                                expires_at=r["expires_at"], resource=r.get("resource"))
        return None

    async def exchange_refresh_token(self, client, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        if STORE.refresh.pop(_sha(refresh_token.token), None) is None:
            raise TokenError(error="invalid_grant", error_description="refresh token уже использован")
        return self._issue(client.client_id, scopes or refresh_token.scopes, refresh_token.resource)

    async def load_access_token(self, token: str) -> AccessToken | None:
        a = STORE.access.get(_sha(token))
        if a and a["expires_at"] > time.time():
            return AccessToken(token=token, client_id=a["client_id"], scopes=a["scopes"],
                               expires_at=a["expires_at"], resource=a.get("resource"))
        return None

    async def revoke_token(self, token) -> None:
        STORE.access.pop(_sha(token.token), None)
        STORE.refresh.pop(_sha(token.token), None)
        STORE.save()


PROVIDER = SingleUserOAuth()

mcp = MCPServer(
    name="Jarvis",
    instructions=(
        "Доступ к компьютеру пользователя (Windows). "
        "Работай только в разрешённых папках (allowed_folders). Папки из read_only_folders не изменяй, "
        "кроме исключений writable_exceptions. "
        "run_command и запись вне белого списка выполняй только по прямой просьбе пользователя."
    ),
    auth_server_provider=PROVIDER,
    auth=AuthSettings(
        issuer_url=CFG["public_url"],
        resource_server_url=CFG["public_url"] + "/mcp",
        validate_token_resource=False,
        client_registration_options=ClientRegistrationOptions(enabled=True),
        revocation_options=RevocationOptions(enabled=True),
    ),
)

LOGIN_PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Jarvis — вход</title>
<style>body{{font-family:system-ui,Segoe UI,sans-serif;max-width:420px;margin:60px auto;padding:0 20px;color:#222}}
input,button{{font-size:18px;width:100%;padding:12px;margin:8px 0;box-sizing:border-box;border-radius:8px;border:1px solid #bbb}}
button{{background:#1f6feb;color:#fff;border:0}} .e{{color:#c00}}</style></head><body>
<h2>Разрешить доступ к компьютеру</h2>
<p>Приложение <b>{client}</b> просит доступ к вашему ПК.<br>Введите пароль, который вы задали в setup.</p>
<p class="e">{error}</p>
<form method="post"><input type="hidden" name="req" value="{req}">
<input type="password" name="password" placeholder="Пароль" autofocus required>
<button type="submit">Разрешить</button></form>
<p style="color:#777;font-size:14px">Если вы этого не запрашивали — закройте страницу.</p></body></html>"""


@mcp.custom_route("/login", methods=["GET", "POST"])
async def login(request: Request) -> Response:
    if request.method == "GET":
        req = request.query_params.get("req", "")
        error = ""
    else:
        form = await request.form()
        req, pw = str(form.get("req", "")), str(form.get("password", ""))
        now = time.time()
        _login_fail[:] = [t for t in _login_fail if now - t < 900]
        if len(_login_fail) >= 5:
            audit("LOGIN_LOCKED")
            return HTMLResponse("<h3>Слишком много неверных попыток. Подождите 15 минут.</h3>", status_code=429)
        pend = STORE.pending.get(req)
        if pend and pend[2] > now and check_password(pw):
            client_id, params, _ = STORE.pending.pop(req)
            code = secrets.token_urlsafe(32)
            STORE.codes[code] = AuthorizationCode(
                code=code, scopes=params.scopes or [], expires_at=now + 300, client_id=client_id,
                code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=params.resource, subject="owner",
            )
            audit("LOGIN_OK", client_id=client_id, ip=request.client.host if request.client else "")
            return RedirectResponse(
                construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state), status_code=302
            )
        _login_fail.append(now)
        audit("LOGIN_FAIL", ip=request.client.host if request.client else "")
        error = "Неверный пароль или ссылка устарела (начните подключение заново)."
    pend = STORE.pending.get(req)
    client = "неизвестно"
    if pend and pend[0] in STORE.clients:
        client = STORE.clients[pend[0]].get("client_name") or "Claude"
    return HTMLResponse(LOGIN_PAGE.format(client=html.escape(client), error=error, req=html.escape(req)))


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> Response:
    return Response("ok")


# ----------------------------------------------------------------------------
# Проверка путей
# ----------------------------------------------------------------------------
def _norm(p: str | Path) -> str:
    return os.path.normcase(os.path.realpath(os.path.expandvars(os.path.expanduser(str(p)))))


def _inside(path: str, folders: list[str]) -> bool:
    for f in folders:
        f = _norm(f)
        if path == f or path.startswith(f.rstrip("\\/") + os.sep):
            return True
    return False


def resolve_read(path: str) -> Path:
    p = _norm(path)
    if not _inside(p, CFG["allowed_folders"]):
        raise PermissionError(
            f"Папка не в белом списке: {path}. Разрешены: {', '.join(CFG['allowed_folders'])}. "
            "Добавить папку можно в config.json (allowed_folders)."
        )
    return Path(p)


def needs_confirm_for_write(p: str) -> str | None:
    """None — можно писать; иначе причина, почему нужно подтверждение. PermissionError — нельзя."""
    if _inside(p, CFG["read_only_folders"]) and not _inside(p, CFG["writable_exceptions"]):
        raise PermissionError(
            "Эта папка защищена от записи (read_only_folders). Писать сюда нельзя — "
            "пишите в папки из writable_exceptions."
        )
    if not _inside(p, CFG["allowed_folders"]):
        return "запись вне белого списка папок"
    return None


# ----------------------------------------------------------------------------
# Подтверждение на ПК (окно Windows)
# ----------------------------------------------------------------------------
def _messagebox(text: str, title: str, timeout_sec: int) -> bool:
    if not IS_WINDOWS:
        return os.environ.get("PC_MCP_TEST_AUTO_CONFIRM") == "1"
    import ctypes

    MB_YESNO, MB_ICONWARNING, MB_TOPMOST, MB_SETFOREGROUND, MB_SYSTEMMODAL = 0x4, 0x30, 0x40000, 0x10000, 0x1000
    IDYES = 6
    flags = MB_YESNO | MB_ICONWARNING | MB_TOPMOST | MB_SETFOREGROUND | MB_SYSTEMMODAL
    user32 = ctypes.windll.user32
    try:
        f = user32.MessageBoxTimeoutW
        f.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_ushort, ctypes.c_uint]
        res = f(None, text, title, flags, 0, timeout_sec * 1000)
    except AttributeError:
        res = user32.MessageBoxW(None, text, title, flags)
    return res == IDYES


_confirm_lock = asyncio.Lock()


async def confirm(action: str, details: str) -> bool:
    if CFG["confirm_mode"] == "chat":
        # подтверждение делает сам Claude: у инструмента стоит «Спрашивать» в настройках коннектора
        audit("CONFIRM_IN_CHAT", what=action, details=details)
        return True
    if CFG["confirm_mode"] != "popup":
        audit("CONFIRM_AUTO_DENY", what=action, details=details)
        return False
    text = (
        f"Claude просит выполнить действие на этом компьютере:\n\n{action}\n\n{details[:1500]}\n\n"
        f"Разрешить? (окно закроется через {CFG['confirm_timeout_sec']} сек — это будет «Нет»)"
    )
    async with _confirm_lock:
        ok = await asyncio.to_thread(_messagebox, text, "Jarvis — подтверждение", int(CFG["confirm_timeout_sec"]))
    audit("CONFIRM_YES" if ok else "CONFIRM_NO", what=action, details=details)
    return ok


def tool(fn):
    """Регистрирует инструмент; ошибки возвращаются Claude понятным текстом."""
    import functools
    import inspect as _insp

    if _insp.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def w(*a, **k):
            try:
                return await fn(*a, **k)
            except Exception as e:  # noqa: BLE001
                audit("TOOL_ERROR", tool=fn.__name__, error=str(e))
                return f"Ошибка: {e}"
    else:
        @functools.wraps(fn)
        def w(*a, **k):
            try:
                return fn(*a, **k)
            except Exception as e:  # noqa: BLE001
                audit("TOOL_ERROR", tool=fn.__name__, error=str(e))
                return f"Ошибка: {e}"
    return mcp.tool()(w)


# ----------------------------------------------------------------------------
# Чтение форматов
# ----------------------------------------------------------------------------
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".xml", ".htm", ".html", ".ini", ".log", ".py", ".bat", ".ps1", ".sql"}


def decode_text(b: bytes) -> str:
    for enc in ("utf-8-sig", "cp1251", "cp866"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", "replace")


def read_dbf_bytes(data: bytes) -> tuple[list[str], list[dict[str, bytes]]]:
    n, hlen, rlen = struct.unpack("<IHH", data[4:12])
    fields: list[tuple[str, int]] = []
    p = 32
    while p < hlen and data[p] != 0x0D:
        fields.append((data[p:p + 11].split(b"\0")[0].decode("ascii", "replace"), data[p + 16]))
        p += 32
    rows = []
    for i in range(n):
        r = data[hlen + i * rlen: hlen + (i + 1) * rlen]
        if not r or r[:1] == b"*":
            continue
        rec, q = {}, 1
        for name, ln in fields:
            rec[name] = r[q:q + ln]
            q += ln
        rows.append(rec)
    return [f[0] for f in fields], rows


def dec(b: bytes, enc: str) -> str:
    return b.decode(enc, "replace").rstrip()


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    return html.unescape(re.sub(r"<[^>]+>", "", xml))


def file_to_text(path: Path, sheet: str | None, dbf_encoding: str) -> str:
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        names = [sheet] if sheet else wb.sheetnames
        out = [f"Листы: {', '.join(wb.sheetnames)}"]
        for nm in names:
            ws = wb[nm]
            out.append(f"\n=== Лист «{nm}» ===")
            for i, row in enumerate(ws.iter_rows(values_only=True), 1):
                if any(v is not None for v in row):
                    out.append(f"{i}\t" + "\t".join("" if v is None else str(v) for v in row))
        return "\n".join(out)
    if ext == ".pdf":
        from pypdf import PdfReader

        rd = PdfReader(str(path))
        return "\n".join(f"\n=== Стр. {i} ===\n{pg.extract_text() or ''}" for i, pg in enumerate(rd.pages, 1))
    if ext == ".docx":
        return read_docx(path)
    if ext == ".dbf":
        names, rows = read_dbf_bytes(path.read_bytes())
        lines = ["\t".join(names)]
        for r in rows:
            lines.append("\t".join(dec(r[n], dbf_encoding) for n in names))
        return f"Записей: {len(rows)}\n" + "\n".join(lines)
    if ext == ".zip":
        with zipfile.ZipFile(path) as z:
            return "Архив. Файлы внутри:\n" + "\n".join(f"{i.filename}\t{i.file_size} байт" for i in z.infolist())
    if ext in TEXT_EXT or path.stat().st_size < 2_000_000:
        raw = path.read_bytes()
        if b"\0" in raw[:4096] and ext not in TEXT_EXT:
            return f"Это двоичный файл ({ext}, {len(raw)} байт), его нельзя прочитать как текст."
        t = decode_text(raw)
        if ext in (".htm", ".html"):
            t = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", "", t)))
            t = re.sub(r"[ \t]+", " ", t)
        return t
    return f"Файл {ext} слишком большой или неизвестного формата ({path.stat().st_size} байт)."


def page(text: str, offset: int, max_chars: int) -> str:
    total = len(text)
    part = text[offset: offset + max_chars]
    if offset + max_chars < total:
        part += f"\n\n[… показано {offset}–{offset + len(part)} из {total} символов. Дальше: offset={offset + max_chars}]"
    return part


# ----------------------------------------------------------------------------
# Инструменты: файлы
# ----------------------------------------------------------------------------
@tool
def list_allowed_folders() -> str:
    """Показать папки, к которым есть доступ, и защищённые от записи папки."""
    audit("list_allowed_folders")
    return (
        "Чтение разрешено: " + "; ".join(CFG["allowed_folders"])
        + "\nЗащищено от записи: " + "; ".join(CFG["read_only_folders"])
        + "\nИсключения (можно писать): " + "; ".join(CFG["writable_exceptions"])
    )


@tool
def list_dir(path: str) -> str:
    """Показать содержимое папки (папки и файлы с размером и датой изменения)."""
    p = resolve_read(path)
    audit("list_dir", path=str(p))
    if not p.is_dir():
        return f"Это не папка: {p}"
    items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    out = []
    for it in items[:1000]:
        try:
            st = it.stat()
            dt = datetime.fromtimestamp(st.st_mtime).strftime("%d.%m.%Y %H:%M")
            out.append(f"[папка] {it.name}\t{dt}" if it.is_dir() else f"{it.name}\t{st.st_size} байт\t{dt}")
        except OSError:
            out.append(f"{it.name}\t(нет доступа)")
    if len(items) > 1000:
        out.append(f"… и ещё {len(items) - 1000}")
    return f"{p}\n" + ("\n".join(out) or "(пусто)")


@tool
def read_file(path: str, offset: int = 0, max_chars: int = 30000, sheet: str | None = None,
              dbf_encoding: str = "cp866") -> str:
    """Прочитать файл: текст, Excel (.xlsx), PDF, Word (.docx), DBF (dbf_encoding cp866 или cp1251),
    список файлов в .zip. Большие файлы читаются частями: offset — с какого символа."""
    p = resolve_read(path)
    audit("read_file", path=str(p), offset=offset)
    if not p.is_file():
        return f"Файл не найден: {p}"
    return page(file_to_text(p, sheet, dbf_encoding), max(0, offset), min(max(1000, max_chars), 100_000))


@tool
def search_files(folder: str, pattern: str = "*", contains: str | None = None, max_results: int = 100) -> str:
    """Найти файлы в папке и всех подпапках по маске имени (например *.xlsx, *Талас*).
    contains — дополнительно искать текст внутри (только текстовые файлы до 5 МБ)."""
    root = resolve_read(folder)
    audit("search_files", folder=str(root), pattern=pattern, contains=contains or "")
    res, start = [], time.time()
    low = contains.lower() if contains else None
    for dp, dns, fns in os.walk(root):
        for fn in fns:
            if not fnmatch.fnmatch(fn.lower(), pattern.lower()):
                continue
            fp = Path(dp) / fn
            if low:
                try:
                    if fp.stat().st_size > 5_000_000 or low not in decode_text(fp.read_bytes()).lower():
                        continue
                except OSError:
                    continue
            res.append(str(fp))
            if len(res) >= max_results:
                return "\n".join(res) + f"\n[достигнут предел {max_results}]"
        if time.time() - start > 60:
            return "\n".join(res) + "\n[поиск остановлен через 60 сек — уточните папку]"
    return "\n".join(res) or "Ничего не найдено."


@tool
async def write_file(path: str, content: str, encoding: str = "utf-8") -> str:
    """Записать текстовый файл. Если файл уже есть — сначала делается резервная копия.
    В защищённые папки (read_only_folders) писать нельзя. Запись вне белого списка — только с подтверждением на ПК."""
    p = _norm(path)
    reason = needs_confirm_for_write(p)
    if reason and not await confirm("Запись файла (" + reason + ")", p):
        return "Отклонено: на компьютере не подтвердили запись."
    target = Path(p)
    backup = ""
    if target.exists():
        bdir = Path(CFG["backup_dir"]) / datetime.now().strftime("%Y-%m-%d")
        bdir.mkdir(parents=True, exist_ok=True)
        bpath = bdir / f"{datetime.now():%H%M%S}_{target.name}"
        shutil.copy2(target, bpath)
        backup = f" Резервная копия: {bpath}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding=encoding)
    audit("write_file", path=p, size=len(content), backup=backup)
    return f"Записано: {p} ({len(content)} символов).{backup}"


@tool
async def run_command(command: str, cwd: str | None = None, timeout_sec: int = 120) -> str:
    """Выполнить команду Windows (cmd) или скрипт, например: python C:\\...\\script.py.
    Каждая команда выполняется ТОЛЬКО после того, как человек нажмёт «Да» в окне на ПК."""
    workdir = str(resolve_read(cwd)) if cwd else None
    if not await confirm("Выполнить команду", f"{command}\n\nПапка: {workdir or '(по умолчанию)'}"):
        return "Отклонено: на компьютере не подтвердили команду (или никого нет у ПК)."
    audit("run_command", command=command, cwd=workdir or "")
    try:
        r = await asyncio.to_thread(
            subprocess.run, command, shell=True, cwd=workdir, capture_output=True,
            timeout=min(max(5, timeout_sec), 1800),
        )
    except subprocess.TimeoutExpired:
        return "Команда не уложилась во время и была остановлена."
    out = decode_text(r.stdout or b"")
    err = decode_text(r.stderr or b"")
    return page(f"Код выхода: {r.returncode}\n--- вывод ---\n{out}\n--- ошибки ---\n{err}", 0, 50_000)


# ----------------------------------------------------------------------------
# Запуск
# ----------------------------------------------------------------------------
def build_app():
    host = urlparse(CFG["public_url"]).netloc
    sec = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[host, "127.0.0.1:*", "localhost:*"],
        allowed_origins=["https://claude.ai", "https://claude.com", CFG["public_url"],
                         "http://127.0.0.1:*", "http://localhost:*"],
    )
    return mcp.streamable_http_app(transport_security=sec, host="127.0.0.1")


app = build_app()

if __name__ == "__main__":
    import uvicorn

    audit("SERVER_START", url=CFG["public_url"], folders=CFG["allowed_folders"])
    uvicorn.run(app, host="127.0.0.1", port=int(CFG["port"]), proxy_headers=True, forwarded_allow_ips="127.0.0.1",
                log_level="warning")
