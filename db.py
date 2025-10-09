from __future__ import annotations
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, select
from sqlalchemy import Column, BigInteger  # ← добавь это

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession  # важно: из SQLModel, не из SQLAlchemy

# ================================================================
# Модели базы данных
# ================================================================


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # Telegram ID спокойно вылетает за пределы int32, поэтому BIGINT
    tg_id: int = Field(sa_column=Column(BigInteger, unique=True, index=True))
    name: Optional[str] = None
    goal: Optional[str] = None           #  ← добавили
    gender: Optional[str] = None
    age: Optional[int] = None
    height_cm: Optional[int] = None
    weight_kg: Optional[float] = None

class Feedback(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    user_tg_id: int = Field(index=True)
    username: Optional[str] = Field(default=None, max_length=255)
    full_name: Optional[str] = Field(default=None, max_length=255)
    type: str = Field(max_length=16)  # bug | idea | free
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
class MuscleGroup(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str


class Exercise(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    type: str = Field(default="strength")  # strength | cardio | mobility
    primary_muscle_id: Optional[int] = Field(default=None, foreign_key="musclegroup.id")
    tip: Optional[str] = None


class Equipment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None


class Workout(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)  # автодата создания


class WorkoutItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    workout_id: int = Field(foreign_key="workout.id")
    exercise_id: int = Field(foreign_key="exercise.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)  # автодата создания

    # Силовые
    weight: Optional[float] = None
    reps: Optional[int] = None

    # Кардио
    duration_sec: Optional[int] = None
    distance_m: Optional[float] = None


# ================================================================
# Сессия и инициализация
# ================================================================
async def init_db(db_url: str):
    engine = create_async_engine(db_url, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session(db_url: str) -> AsyncSession:
    engine = create_async_engine(db_url, echo=False, future=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return async_session()
