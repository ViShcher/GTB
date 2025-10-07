🏋️‍♂️ Fitness Bot TG

Телеграм-бот для отслеживания тренировок: учёт подходов, веса и прогресса без ручного ввода текста.
Работает на aiogram 3, FastAPI, PostgreSQL (Async) и деплоится на Railway.

⚙️ Стек

Python 3.12+

aiogram 3 (вебхук режим)

FastAPI — сервер для /webhook и /health

SQLModel / asyncpg / PostgreSQL

Railway CI/CD

📁 Структура проекта
bot.py                — локальный запуск в режиме polling
server.py             — основной сервер под вебхук
config.py             — ENV + автоконвертация URL в asyncpg
db.py                 — ORM-модель и сессии
seed_data.py          — заполнение БД справочником упражнений
routers/
  ├── basic.py        — /help, системные команды
  ├── profile.py      — онбординг и профиль пользователя
  ├── training.py     — логика тренировок и подходов
  └── __init__.py
requirements.txt
README.md

🚀 Развёртывание на Railway

Подключи репозиторий.

В Variables добавь:

BOT_TOKEN=<твой_токен>
RAILWAY_PUBLIC_DOMAIN=<домен_railway>
WEBHOOK_PATH=webhook/ShlaSaSha
DATABASE_URL=postgresql+asyncpg://user:pass@postgres.railway.internal:5432/railway


В requirements.txt присутствует asyncpg — не убирай.

Railway автоматически поднимет Postgres-плагин.

После старта бот логирует Created groups и Seeded exercises — значит БД инициализирована.

Проверить живость:

GET https://<домен>/health  → {"status":"ok"}

🧠 Основные возможности

онбординг с выбором цели и параметров тела;

трекер подходов и веса кнопками (+1 / +2 / +5 повторы, +2.5 кг / +5 кг / +10 кг);

история и итоги тренировок (неделя, месяц, год);

встроенный справочник упражнений;

саркастичные подбадривания;

постоянная база данных (PostgreSQL, async).

🔍 Локальный запуск (для отладки)
pip install -r requirements.txt
export BOT_TOKEN=<твой_токен>
python bot.py


или через uvicorn-сервер:

uvicorn server:app --reload

💾 База данных

PostgreSQL с async-драйвером asyncpg.

Автосоздание таблиц при старте (init_db).

Первичное заполнение (группы + упражнения) через ensure_seed_data().

Поддерживает миграцию без Alembic — структура обновляется автоматом.

🧰 Команды
Команда	Описание
/start	Запуск бота, онбординг
/help	Список доступных действий
/my_profile	Показать профиль
/train	Начать тренировку
📈 В планах

напоминания о тренировках;

таймеры отдыха;

шаблоны программ;

отчёты с графиками;

режим тренера с подопечными.
