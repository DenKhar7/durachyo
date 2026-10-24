# Сглыпа 2.0

Мемный Telegram-бот для своих: запоминает фразы чата (до 10 000 на чат), генерирует бред цепью Маркова, цитирует людей их же словами, кривляется и оскорбляет.

Стек: Python 3.12, aiogram 3, SQLite (aiosqlite), Docker.

## Команды

| Команда | Что делает |
|---|---|
| `/sglyp` | бред по мотивам чата |
| `/sglyp @user` или реплаем | бред в стиле человека |
| `/sglyp слово` | бред, начинающийся со слова |
| `/quote [@user]` | достать старую фразу |
| `/mock` (реплаем) | пОвТоРиТь С кРиВлЯнИеМ |
| `/insult [@user]` | оскорбить (без аргумента — случайного) |
| `/all` | пингануть всех, кого бот видел (кулдаун 5 мин) |
| `/stats` | сколько помнит |
| `/forgetme` | стереть свои фразы |
| `/chance N` | шанс влезть в разговор, % (только ADMIN_IDS) |

Бот всегда отвечает, если ему ответили реплаем, упомянули `@бота` или написали триггер-слово (`TRIGGER_WORDS`). В остальных случаях влезает с шансом `/chance`.

## 1. BotFather

1. `/newbot` → получить токен.
2. `/setprivacy` → **Disable**. Без этого бот не видит обычные сообщения и ничему не учится.
3. Добавить бота в свою группу.
4. После добавления: `/setjoingroups` → **Disable**, чтобы бота больше никуда нельзя было добавить.
5. Включить 2FA на своём Telegram-аккаунте (Настройки → Конфиденциальность → Облачный пароль).

## 2. Локально

```cmd
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
copy example.env .env
.venv\Scripts\python -m pytest
.venv\Scripts\python -m bot
```

## 3. Узнать id чата

Оставь `ALLOWED_CHAT_IDS` пустым и запусти бота. При любом сообщении из группы он выйдет из неё и запишет в лог:

```
Foreign chat -1001234567890 ('Наш чат'): leaving
```

Впиши этот id в `ALLOWED_CHAT_IDS`, перезапусти бота и добавь его в группу заново. Свой `user_id` для `ADMIN_IDS` можно узнать у @userinfobot.

## 4. Деплой на VPS (OVH, Ubuntu/Debian)

Один раз, подготовить сервер:

```bash
# вход только по ключу
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/; s/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh

# фаервол: боту входящие порты не нужны (long polling)
sudo apt update && sudo apt install -y ufw fail2ban unattended-upgrades
sudo ufw default deny incoming && sudo ufw allow OpenSSH && sudo ufw enable

# docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # перелогиниться
```

Запуск:

```bash
git clone <repo> sglypa && cd sglypa
cp example.env .env && nano .env
chmod 600 .env
docker compose up -d --build
docker compose logs -f
```

Обновление: `git pull && docker compose up -d --build`.

БД живёт в docker volume `sglypa-data` и попадает в ежедневный бэкап OVH. Ручная копия:

```bash
docker compose cp bot:/app/data/sglypa.db ./backup.db
```

## Безопасность

- **Токен** = полный доступ к боту. Он лежит только в `.env`, а `.env` закрыт в `.gitignore`/`.dockerignore` и имеет `chmod 600`. Если токен утёк, сделай `/revoke` в BotFather и обнови `.env`.
- **Белый список**: бот обрабатывает апдейты только из `ALLOWED_CHAT_IDS` и сам выходит из любых других групп. В личке отвечает только `ADMIN_IDS`.
- **Без входящих портов**: long polling, вебхук не нужен, на сервере открыт только SSH.
- **Контейнер**: непривилегированный пользователь, read-only файловая система, `cap_drop: ALL`, `no-new-privileges`, лимиты памяти и CPU.
- **Код**: SQL только параметризованный, весь текст из чата экранируется перед отправкой в HTML-режиме, никаких eval/shell, длина входа ограничена, есть кулдауны против флуда.
- **Права в группе**: админка боту не нужна. Если всё же выдаёшь, то без бана и без добавления админов.
- Предупреди друзей, что бот хранит переписку. Для удаления своих фраз есть `/forgetme`.

## Как устроена генерация

`bot/markov.py` — цепь Маркова по словам. Порядок задаётся `MARKOV_ORDER`: 1 — шиза, 2 — смешно и полусвязно, 3 — почти цитаты. Цепь строится в памяти из SQLite при первом обращении, дообучается на лету и раз в 500 сообщений пересобирается. 10k фраз — это несколько мегабайт RAM.

Случайные ответы (`bot/responder.py`) выбирают режим по весам: продолжение от слова из сообщения, свободный бред, цитата автора, кривляние, оскорбление.
