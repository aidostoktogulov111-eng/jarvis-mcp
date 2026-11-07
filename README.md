<p align="center"><b>Jarvis</b> — a self-hosted MCP server that lets Claude work with files on your Windows PC from chat, phone or voice mode.</p>

<p align="center">
<img alt="Python" src="https://img.shields.io/badge/python-3.12%2B-blue">
<img alt="Platform" src="https://img.shields.io/badge/platform-Windows-lightgrey">
<img alt="MCP" src="https://img.shields.io/badge/MCP-server-8A2BE2">
<img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

## English summary

**Jarvis** is a remote [Model Context Protocol](https://modelcontextprotocol.io) connector for [Claude](https://claude.ai). It runs on your own Windows computer and is exposed through an ngrok tunnel, so Claude can list, read, search and write files in folders you allow, and run commands only after you press **Allow** in the chat.

- **Read anything useful:** text, Excel, Word, PDF, DBF, zip listings; large files in chunks.
- **Safe by default:** password login (OAuth, hashed), folder whitelist, read-only folders, automatic backups before overwrite, no delete tool, action log.
- **Confirm from your phone:** commands and writes ask for approval in the Claude chat.

Quick start (Windows): install Python 3.12+, create a free ngrok account with a static domain, download this repo, run `1_ustanovka.bat`, then `2_zapusk.bat`, and add `https://<your-domain>/mcp` as a custom connector in Claude. Detailed instructions below are in Russian.

---

# «Jarvis для Claude»: свой коннектор к компьютеру

Это свой MCP-сервер. Он даёт Claude доступ к вашему компьютеру из чата, с телефона и, если поддерживается, из голосового режима. Работает он так:

```
Claude (облако) → https://ваш-адрес.ngrok-free.dev/mcp → туннель ngrok → сервер на вашем ПК → ваши папки
```

**Компьютер должен быть включён**, а Windows должна быть открыта под вашим пользователем.

---

## Что умеет

| Инструмент | Что делает |
|---|---|
| `list_allowed_folders` | показывает, к каким папкам есть доступ |
| `list_dir` | содержимое папки |
| `read_file` | читает текст, Excel, PDF, Word, DBF (cp866/cp1251), список файлов в zip; большие файлы читает частями |
| `search_files` | ищет файлы по маске (`*.xlsx`, `*Талас*`) и по тексту внутри |
| `write_file` | записывает файл; если файл уже есть, сначала делает резервную копию |
| `run_command` | выполняет команду или скрипт Python, **только после вашей кнопки «Разрешить» в чате** |


## Защита

- **Пароль.** Подключить коннектор можно только через страницу входа с вашим паролем. Пароль хранится только в виде хеша. После 5 неверных попыток вход блокируется на 15 минут.
- **Только Claude.** Сервер принимает подключение только с адресов возврата claude.ai и claude.com.
- **Белый список папок.** По умолчанию это Рабочий стол, Документы и Загрузки, остальное закрыто. Список меняется в `config.json`, поле `allowed_folders`.
- **Папки только для чтения** — можно указать в `config.json`, поле `read_only_folders` (исключения — `writable_exceptions`).
- **Резервные копии** перед каждой перезаписью: папка `backups\<дата>` рядом с сервером.
- **Подтверждение в чате** для команд и записи: в настройках коннектора у `run_command` и `write_file` ставится «Спрашивать», и Claude перед каждым таким действием показывает кнопку «Разрешить», в том числе на телефоне. Удалять файлы сервер не умеет вообще. Если хотите подтверждать окном на ноутбуке, поставьте в `config.json` `"confirm_mode": "popup"`.
- **Журнал** всех действий: `data\actions.log`.

---

## Установка (один раз, около 15 минут)

### 1. Python
Скачайте Python 3.12 или новее с https://www.python.org/downloads/. При установке **поставьте галочку «Add python.exe to PATH»**.

### 2. ngrok (туннель с постоянным адресом)
1. Зарегистрируйтесь на https://dashboard.ngrok.com/signup, это бесплатно.
2. Откройте **Your Authtoken** и держите страницу открытой: токен понадобится при установке.
3. Откройте **Domains** и получите бесплатный постоянный домен, вида `что-то.ngrok-free.dev`. Скопируйте его.

### 3. Файлы
Скачайте репозиторий (Code → Download ZIP) и распакуйте в папку **без русских букв и пробелов**, например `C:\Jarvis`.

### 4. Установка
Запустите **`1_ustanovka.bat`**. Он:
- создаст отдельное окружение Python и поставит библиотеки;
- поставит ngrok (если его нет);
- спросит домен ngrok, Authtoken, **пароль** и дополнительные папки.

### 5. Запуск и проверка
Запустите **`2_zapusk.bat`**. Через 10 секунд должно появиться `ok`, а ниже адрес коннектора вида `https://…/mcp`.

### 6. Автозапуск
Запустите **`3_avtozapusk_vkl.bat`**. Теперь сервер будет сам запускаться через 30 секунд после входа в Windows, без окон.

---

## Подключение к Claude

1. На компьютере откройте claude.ai: **Настройки → Коннекторы → Добавить свой коннектор**.
2. Название: `Jarvis`. URL: `https://ваш-домен.ngrok-free.dev/mcp`. Расширенные настройки (Client ID и Secret) оставьте **пустыми**.
3. Нажмите **Добавить**, затем **Подключить**.
4. Откроется браузер. Если ngrok покажет страницу-предупреждение, нажмите **Visit Site**. На странице «Разрешить доступ к компьютеру» введите пароль и нажмите **Разрешить**.
5. Коннектор станет «Подключён». С телефона он появится сам, потому что добавленные на сайте коннекторы видны и в приложении.

### Проверка
- В обычном чате напишите: *«Покажи разрешённые папки на моём ПК»*, а потом *«Найди на рабочем столе все файлы Excel»*.
- На телефоне повторите то же в чате, затем в голосовом режиме.
- Если голосовой режим не вызывает коннектор, это ограничение самого голосового режима, а не сервера. Тогда пользуйтесь текстовым чатом на телефоне: там коннектор работает.

---

## Как быстро отключить доступ

| Ситуация | Что сделать |
|---|---|
| Просто остановить | `4_stop.bat` |
| **Что-то пошло не так** | **`5_OTKLYUCHIT_VSYO.bat`**: останавливает сервер, аннулирует все выданные доступы и выключает автозапуск |
| Вы не у компьютера | В Claude: Настройки → Коннекторы → «Jarvis» → Отключить. Потом на ПК запустите `5_OTKLYUCHIT_VSYO.bat` |
| Сменить пароль или папки | `smenit_parol_ili_papki.bat`, затем снова «Подключить» коннектор в Claude |
| Выключить только автозапуск | `6_avtozapusk_vykl.bat` |

**Никому не сообщайте пароль.** С ним можно читать ваши папки.

---

## Если не работает

| Признак | Где смотреть |
|---|---|
| `2_zapusk.bat` пишет «НЕ ОТВЕЧАЕТ» | `data\ngrok.log` (неверный Authtoken или домен) и `data\server.log` (ошибка сервера) |
| Claude пишет «не удалось подключиться» | Откройте в браузере `https://ваш-домен/health`, должно быть `ok`. Проверьте, что URL в Claude заканчивается на `/mcp` |
| «Папка не в белом списке» | добавьте папку в `config.json` → `allowed_folders` и перезапустите (`4_stop.bat`, потом `2_zapusk.bat`) |
| Команды выполняются без вопроса | в Claude: Коннекторы → «Jarvis» → у `run_command` и `write_file` поставьте «Спрашивать» |
| ngrok перестал давать бесплатный домен | можно использовать Cloudflare Tunnel со своим доменом (около $10 в год). Сервер тот же, меняется только туннель и адрес в `setup` |

Файлы: `server.py` — сервер; `launcher.py` — фоновый запуск сервера и ngrok с перезапуском при падении; `setup.py` — настройка; `config.json` — настройки (создаётся при установке); `data\` — журналы и выданные доступы.


## Безопасность репозитория

`config.json` (пароль, токен ngrok) и папка `data\` (выданные доступы) **не загружаются на GitHub** — они в `.gitignore`. Шаблон настроек — `config.example.json`. Никогда не выкладывайте свой `config.json`.

## Лицензия

MIT — см. файл [LICENSE](LICENSE). Используете на свой риск: сервер даёт удалённый доступ к вашему компьютеру.

## Контакты

Вопросы и предложения: **aidostoktogulov111@gmail.com**
