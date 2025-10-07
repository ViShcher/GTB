# seed_data.py — идемпотентное наполнение БД базовыми группами и упражнениями
from sqlmodel import select
from db import get_session, MuscleGroup, Exercise
from config import settings

# Базовые группы (slug -> имя)
DEFAULT_GROUPS = [
    ("chest", "Грудь"),
    ("back", "Спина"),
    ("legs", "Ноги"),
    ("shoulders", "Плечи"),
    ("biceps", "Бицепс"),
    ("triceps", "Трицепс"),
    ("core", "Кор"),
    ("cardio", "Кардио"),
]

# Базовые упражнения: (name, slug, type, group_slug, tip)
EXERCISES = [
    # ---- strength (минимальный набор-плейсхолдер, ваш справочник остаётся в БД)
    ("Жим лежа", "bench_press", "strength", "chest", "Лопатки сведены, таз не отрывай."),
    ("Приседания со штангой", "back_squat", "strength", "legs", "Спина ровно, колени по носкам."),
    ("Тяга верхнего блока", "lat_pulldown", "strength", "back", "Тяни локтями, не раскачивайся."),

    # ---- cardio (полный набор под текущий бот)
    ("Беговая дорожка", "treadmill", "cardio", "cardio", "Время/дистанция. Пример: 30:00 5км или просто 30"),
    ("Велотренажёр", "bike", "cardio", "cardio", "Время/дистанция. Пример: 20:00 10км или просто 20"),
    ("Эллиптический тренажёр", "elliptical", "cardio", "cardio", "Время. Дистанция опционально."),
    ("Гребной тренажёр", "rower", "cardio", "cardio", "Время/дистанция. Пример: 15:00 3км"),
    ("Скакалка", "jump_rope", "cardio", "cardio", "Только время в минутах: 5, 10, 12"),
]

async def ensure_seed_data():
    async with await get_session(settings.database_url) as session:
        # 1) Группы
        res = await session.exec(select(MuscleGroup))
        existing_groups = {g.slug: g for g in res.all()}
        for slug, name in DEFAULT_GROUPS:
            if slug not in existing_groups:
                session.add(MuscleGroup(slug=slug, name=name))
        await session.commit()

        # перечитать с id
        res = await session.exec(select(MuscleGroup))
        groups = {g.slug: g for g in res.all()}

        # 2) Упражнения (по slug, без апдейтов существующих — идемпотентно)
        res = await session.exec(select(Exercise))
        existing = {e.slug: e for e in res.all() if getattr(e, "slug", None)}
        to_add = []
        for name, slug, etype, gslug, tip in EXERCISES:
            if slug in existing:
                continue
            mg = groups.get(gslug)
            to_add.append(
                Exercise(
                    name=name,
                    slug=slug,
                    type=etype,
                    primary_muscle_id=mg.id if mg else None,
                    tip=tip,
                )
            )
        if to_add:
            for e in to_add:
                session.add(e)
            await session.commit()
