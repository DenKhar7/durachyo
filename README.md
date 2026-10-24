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

Схема: `git push` → GitHub Actions прогоняет тесты → собирает образ → кладёт в приватный GHCR → по SSH дёргает VPS → VPS делает `docker pull` нужного коммита и перезапускает бота.

На VPS **нет исходников и нет доступа к репо**. Ключ CI на сервере умеет ровно одно: запустить `deploy.sh` с SHA коммита. Ни шелла, ни проброса портов.

| Что утекло | Что может атакующий |
|---|---|
| ключ CI из GitHub Secrets | передеплоить уже собранный тобой образ |
| токен GHCR с VPS | скачать образ бота (код и так на VPS) |
| пользователь `sglypa` на VPS | через docker — весь сервер, включая другие проекты; репо и GitHub не тронуть |

### 4.1. Сервер (один раз)

На VPS живут и другие проекты, поэтому здесь **ничего не ломаем глобально**: каждая команда сначала проверяет состояние. Боту входящие порты не нужны (long polling) — фаервол и SSH-настройки ему не требуются, это общая гигиена сервера.

**Docker** — ставить, только если его ещё нет:

```bash
docker --version || curl -fsSL https://get.docker.com | sh
docker compose version     # нужен Compose v2 (плагин), не старый docker-compose
```

**Пользователь проекта** — отдельный под каждый проект, чтобы не трогать чужие ключи и папки:

```bash
id sglypa 2>/dev/null || sudo adduser --disabled-password --gecos "" sglypa
sudo usermod -aG docker sglypa
sudo install -d -o sglypa -g sglypa -m 700 /opt/sglypa
```

Членство в группе `docker` фактически равно root на всём сервере. Поэтому ключ CI жёстко ограничен `deploy.sh` (шаг 4.4) — по нему нельзя получить шелл.

**Гигиена сервера (проверить, не применять вслепую):**

```bash
# SSH: должно быть "passwordauthentication no" и "permitrootlogin no" (или prohibit-password)
sudo sshd -T | grep -Ei '^(passwordauthentication|permitrootlogin)'

# фаервол: посмотреть, что уже открыто для других сервисов
sudo ufw status verbose 2>/dev/null || sudo iptables -S | head -50

# автообновления безопасности и защита от перебора SSH
dpkg -l unattended-upgrades fail2ban 2>/dev/null | grep ^ii
```

Если что-то из этого не настроено — настраивай отдельно и аккуратно:
- **SSH-пароли**: сначала убедись, что заходишь по ключу (`ssh -o PasswordAuthentication=no user@IP` в **новом** окне), и только потом ставь `PasswordAuthentication no` в `/etc/ssh/sshd_config` → `sudo systemctl reload ssh`. Текущую сессию не закрывай, пока не проверишь вход.
- **ufw**: если он выключен, а на сервере крутятся сайты/сервисы, сначала разреши их порты (`sudo ufw allow OpenSSH`, `sudo ufw allow 80,443/tcp` и т.д. по `sudo ss -tlnp`), и только потом `sudo ufw enable`. Учти: Docker публикует порты контейнеров в обход ufw.
- **fail2ban / unattended-upgrades**: `sudo apt install -y fail2ban unattended-upgrades` — безопасно для других сервисов.

### 4.2. Файлы на сервер

С ПК (из папки проекта):

```cmd
scp docker-compose.yml deploy\deploy.sh example.env user@VPS:/tmp/
```

На VPS:

```bash
sudo install -o root -g root -m 755 /tmp/deploy.sh /opt/sglypa/deploy.sh
sudo install -o sglypa -g sglypa -m 644 /tmp/docker-compose.yml /opt/sglypa/
sudo install -o sglypa -g sglypa -m 600 /tmp/example.env /opt/sglypa/.env
rm /tmp/deploy.sh /tmp/docker-compose.yml /tmp/example.env
sudo -u sglypa nano /opt/sglypa/.env      # вписать BOT_TOKEN и остальное
```

`deploy.sh` принадлежит root — пользователь `sglypa` не может его подменить.

### 4.3. Доступ VPS к образам (только чтение)

GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)** → Generate. Галочка только `read:packages`, срок — год. (GHCR пока не поддерживает fine-grained токены.)

```bash
sudo -iu sglypa docker login ghcr.io -u DenKhar7    # пароль = этот токен
```

### 4.4. Ключ для CI

На ПК:

```cmd
ssh-keygen -t ed25519 -f %USERPROFILE%\.ssh\durachyo_ci -N "" -C "gha-deploy"
type %USERPROFILE%\.ssh\durachyo_ci.pub
```

На VPS — разрешить этому ключу только `deploy.sh`:

```bash
sudo -u sglypa mkdir -p -m 700 /home/sglypa/.ssh
echo 'restrict,command="/opt/sglypa/deploy.sh" ssh-ed25519 AAAA...ВСТАВИТЬ... gha-deploy' \
  | sudo -u sglypa tee -a /home/sglypa/.ssh/authorized_keys
sudo chmod 600 /home/sglypa/.ssh/authorized_keys
```

Секреты в репо (с ПК):

```cmd
gh secret set DEPLOY_SSH_KEY < %USERPROFILE%\.ssh\durachyo_ci
gh secret set DEPLOY_HOST -b "IP_VPS"
ssh-keyscan -t ed25519 IP_VPS > known_hosts.tmp && gh secret set DEPLOY_KNOWN_HOSTS < known_hosts.tmp && del known_hosts.tmp
del %USERPROFILE%\.ssh\durachyo_ci
```

Приватный ключ CI после загрузки в GitHub удаляется с ПК — он нужен только Actions. Если SSH не на 22 порту: `gh secret set DEPLOY_PORT -b "2222"`.

### 4.5. Деплой

Просто `git push`. Ход смотреть: `gh run watch`. Логи бота на VPS:

```bash
sudo -iu sglypa sh -c 'cd /opt/sglypa && docker compose logs -f'
```

Текущая версия — в `/opt/sglypa/.deployed`. Откат: Actions → нужный старый запуск → Re-run jobs.

### Бэкап

БД живёт в docker volume и попадает в ежедневный бэкап OVH. Ручная копия:

```bash
sudo -iu sglypa sh -c 'cd /opt/sglypa && docker compose cp bot:/app/data/sglypa.db ./backup.db'
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
