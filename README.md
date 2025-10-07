# Fitness Bot TG — актуальная краткая инструкция

## Стек и запуск
- aiogram v3, FastAPI, uvicorn
- SQLModel + async (asyncpg/aiosqlite)

Локально (polling):
```
python bot.py
```

Продакшн (webhook):
```
uvicorn server:app --host 0.0.0.0 --port 8080
```

## ENV (используются в config.py)
- `BOT_TOKEN`
- `RAILWAY_PUBLIC_DOMAIN`
- `WEBHOOK_PATH`
- `DATABASE_URL`
- `LOG_LEVEL` (опц.)
- `WEBHOOK_SECRET` (опц.)

`WEBHOOK_PATH` должен совпадать с переменной окружения на Railway и быть единственным источником пути.

## Сид
`ensure_seed_data()` добавляет группу `cardio` и кардио-упражнения: `treadmill`, `bike`, `elliptical`, `rower`, `jump_rope`.
Силовые и примеры базовых мышечных групп включены.
