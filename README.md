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
INFO:gtb:Deleting old webhook (drop_pending_updates=True) INFO:gtb:Setting webhook to https://.up.railway.app/webhook/... Running on http://0.0.0.0:8080
5. Напиши боту в Telegram `/start`.


## Структура БД
- `MuscleGroup`: группы мышц
- `Equipment`: инвентарь
- `Exercise`: упражнения
- `Workout`: тренировки пользователя
- `WorkoutItem`: элементы тренировки с параметрами (sets/reps/weight/duration/distance)


## Дальше по плану
- Добавить `/add_set ex_id sets reps weight` и карточки результата
- Импорт справочника упражнений (CSV/JSON)
- Категоризация по типам тренировок: strength/cardio/mobility/stretch/circuit
- Экспорт отчётов в CSV
Если локально хочешь вебхук: поставь `BASE_URL_OVERRIDE` на публичный туннель и дерни `uvicorn server:app`.
