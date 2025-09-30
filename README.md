# TG Fitness Bot — Railway-ready MVP


Минимальный бот с вебхуком (aiogram v3 + FastAPI). База на SQLite через SQLModel.


## Быстрый старт локально
1. Python 3.12
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -r requirements.txt`
4. Скопируй `.env.example` в `.env`, пропиши `BOT_TOKEN`.
5. Запусти локально поллинг: `python bot.py`.


## Деплой на Railway
1. Новый проект, подключи репозиторий.
2. В переменных окружения установи:
- `BOT_TOKEN`
- `WEBHOOK_SECRET_PATH` (например, `webhook/ShlaSaSha`)
3. Ничего менять не нужно: `railway.toml`, `railpack-plan.json` и `Procfile` уже на месте.
4. После деплоя проверь логи: должно быть что-то вроде:
