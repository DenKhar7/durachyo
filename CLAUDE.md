# Сглыпа 2.0

Мемный Telegram-бот для своего чата: учится на сообщениях и отвечает вашими же словами.
Python 3.12, aiogram 3, SQLite (aiosqlite), Pillow. Деплой: push в master → GitHub Actions → GHCR → VPS (см. README, раздел 4).

## Команды

```
.venv\Scripts\python -m pytest -q --cov    # тесты + покрытие
.venv\Scripts\python -m mypy bot tests     # типы, strict
.venv\Scripts\python -m ruff check .       # линтер
.venv\Scripts\python -m ruff format .      # форматирование
.venv\Scripts\pre-commit run --all-files   # всё сразу, как перед коммитом
```

## Где что

- `bot/main.py` - запуск: настройки, БД, бот, роутеры, фоновый revive
- `bot/app.py` - `App`: всё общее состояние; aiogram передаёт его в хендлеры аргументом `app`
- `bot/handlers/collect.py` - каждое сообщение: запомнить, подколоть, реакция, ответ
- `bot/handlers/commands.py`, `admin.py`, `filters.py` - команды и фильтры
- `bot/brain.py` - КОГДА отвечать; `bot/responder.py` - ЧТО отвечать (`ReplyMode` и веса)
- `bot/phrases.py` - старые фразы чата; `bot/wordplay.py` - склейки и оскорбления из слов чата
- `bot/media.py` - стикеры, фото, демотиваторы; `bot/demotivator.py` - рисование картинки
- `bot/markov.py` + `bot/chains.py` - генерация текста; `bot/db.py` - SQLite
- `bot/nicknames.py` - подколы про своих и `/tag`; `bot/voice.py` - стиль речи; `bot/taunts.py` - шаблоны
- `bot/revive.py` - будит заглохший чат
- `tests/` - фикстуры `db`, `app`, `bot` в `conftest.py`, хелперы в `helpers.py`; async-тесты пишутся как обычные `async def`

## Правила

- Секреты только в `.env` на сервере. Не читать и не коммитить `.env`, `data/`, `result.json` (переписка чата).
- Весь текст из чата экранируется (`html.escape`) перед отправкой: бот шлёт в режиме HTML.
- SQL только с параметрами `?`.
- В пользовательских текстах обычный дефис `-`, без длинных тире.
- Новые зависимости хендлеров - полями в `App`, не глобальными переменными модулей.
- Магические строки режимов и медиа - через `ReplyMode` / `MediaKind`.
- После изменений: ruff, mypy и тесты зелёные.
