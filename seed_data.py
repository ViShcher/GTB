from typing import List, Tuple
from sqlmodel import select
from db import MuscleGroup, Exercise, get_session
from config import settings

# Базовые группы
GROUPS: List[Tuple[str, str]] = [
    ("Грудь", "chest"),
    ("Спина", "back"),
    ("Ноги", "legs"),
    ("Плечи", "shoulders"),
    ("Руки", "arms"),
    ("Пресс", "abs"),
    ("Кардио", "cardio"),
]

# Упражнения: name, slug, type, group_slug, tip
EXERCISES: List[Tuple[str, str, str, str, str]] = [
    # Грудь
    ("Жим лёжа штанги", "bench_press", "strength", "chest", "Лопатки сведены, стопы в пол, касание груди контролируем."),
    ("Жим гантелей лёжа", "db_bench_press", "strength", "chest", "Движение по дуге, не теряй напряжение в груди."),
    ("Разводка гантелей", "db_fly", "strength", "chest", "Локти слегка согнуты, амплитуда без боли в плечах."),

    # Спина
    ("Тяга штанги в наклоне", "bb_row", "strength", "back", "Спина ровная, тянем локтём назад, не рвём корпус."),
    ("Тяга верхнего блока", "lat_pulldown", "strength", "back", "Тяни к верхней груди, плечи вниз и назад."),
    ("Подтягивания", "pull_up", "strength", "back", "Полный провис и подбор груди к перекладине."),

    # Ноги
    ("Приседания со штангой", "back_squat", "strength", "legs", "Колени по носкам, спина нейтральная, глубина комфортная."),
    ("Жим ногами", "leg_press", "strength", "legs", "Стопы на платформе, колени не сводим внутрь."),
    ("Выпады", "lunges", "strength", "legs", "Шаг назад/вперёд, корпус вертикально, толчок пяткой."),

    # Плечи
    ("Жим штанги стоя", "ohp", "strength", "shoulders", "Сжатый корпус, не прогибай поясницу, штанга над головой."),
    ("Жим гантелей сидя", "db_shoulder_press", "strength", "shoulders", "Полный контроль, не бросай вниз."),
    ("Махи гантелей в стороны", "lateral_raise", "strength", "shoulders", "Малый вес, локоть выше кисти, без читинга."),

    # Руки
    ("Подъём штанги на бицепс", "bb_curl", "strength", "arms", "Локти у корпуса, не раскачивайся."),
    ("Французский жим", "skullcrusher", "strength", "arms", "Локти неподвижны, не бей по лбу, пожалуйста."),
    ("Отжимания на брусьях", "dips", "strength", "arms", "Лопатки сведены, глубину держим в комфорте."),

    # Пресс
    ("Скручивания", "crunch", "strength", "abs", "Поясница прижата, работаем короткой амплитудой."),
    ("Планка", "plank", "strength", "abs", "Корпус прямой, не провисай в пояснице."),

    # Кардио (для выбора тренажёра)
    ("Беговая дорожка", "treadmill", "cardio", "cardio", "Не держись за поручни, держи темп и дыхание."),
    ("Велотренажёр", "bike", "cardio", "cardio", "Колени по оси, не заваливай внутрь."),
    ("Гребной тренажёр", "rower", "cardio", "cardio", "Тяни спиной, не только руками."),
]

async def ensure_seed_data():
    async with await get_session(settings.database_url) as session:
        # группы
        existing_groups = {g.slug for g in (await session.exec(select(MuscleGroup))).all()}
        created = 0
        for name, slug in GROUPS:
            if slug not in existing_groups:
                session.add(MuscleGroup(name=name, slug=slug))
                created += 1
        if created:
            await session.commit()

        # карта slug группы -> id
        res = await session.exec(select(MuscleGroup))
        groups = {g.slug: g.id for g in res.all()}

        # упражнения
        existing_ex = {e.slug for e in (await session.exec(select(Exercise))).all()}
        created_ex = 0
        for name, slug, typ, group_slug, tip in EXERCISES:
            if slug in existing_ex:
                continue
            mg_id = groups.get(group_slug)
            if not mg_id:
                continue
            session.add(Exercise(
                name=name,
                slug=slug,
                type=typ,
                primary_muscle_id=mg_id,
                tip=tip,
                is_active=True,
            ))
            created_ex += 1
        if created_ex:
            await session.commit()
