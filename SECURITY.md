# Безопасность / Security

Jarvis открывает удалённый доступ к вашему компьютеру. Соблюдайте правила:

- Никому не передавайте пароль подключения и файл `config.json` — в нём токен ngrok и хеш пароля. Он исключён из Git через `.gitignore`, не выкладывайте его вручную.
- Давайте доступ только к нужным папкам (`allowed_folders`); важные папки делайте только для чтения (`read_only_folders`).
- В настройках коннектора в Claude у `run_command` и `write_file` ставьте «Спрашивать».
- Если что-то пошло не так — запустите `5_OTKLYUCHIT_VSYO.bat`: сервер остановится, все выданные доступы будут отозваны.

## Как сообщить об уязвимости / Reporting a vulnerability

Не публикуйте уязвимость в открытых Issues. Напишите на **aidostoktogulov111@gmail.com** с описанием и шагами воспроизведения.
Please do not open a public issue for security problems — email **aidostoktogulov111@gmail.com** instead.
